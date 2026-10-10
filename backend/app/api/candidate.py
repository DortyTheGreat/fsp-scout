"""Личный кабинет кандидата: профиль и резюме, опрос, статус категории, приватность, PDF-профиль."""
import logging
import secrets
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, candidate_profile
from app.api.serializers import category, fsp_view, skills_view
from app.core.db import SessionLocal, get_db
from app.core.errors import ServiceError
from app.models import CandidateProfile, Consent, GradeHistory, SurveyResponse, TestAttempt
from app.services import resume as resume_svc
from app.services.llm import get_llm
from app.services.matching.service import candidate_insights
from app.services.testing import service as testing
from app.taxonomy import GRADE_BY_SLUG, INDUSTRIES, SKILL_BY_SLUG, SPEC_BY_SLUG, TESTABLE_GRADES

router = APIRouter(prefix="/candidate", tags=["Кандидат"], responses=AUTH_ERRORS)
log = logging.getLogger("resume")


class ProfileIn(BaseModel):
    full_name: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=40)
    telegram: str | None = Field(None, max_length=64)
    contact_email: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    about: str | None = Field(None, max_length=5000)
    years_experience: float | None = Field(None, ge=0, le=60)
    claimed_skills: list[str] | None = None
    roles: list[str] | None = None
    soft_skills: list[str] | None = None
    experience: list[dict] | None = None
    education: str | None = Field(None, max_length=2000)
    salary_from: int | None = Field(None, ge=0, le=10_000_000)
    salary_to: int | None = Field(None, ge=0, le=10_000_000)
    work_formats: list[Literal["office", "hybrid", "remote"]] | None = None
    relocation: bool | None = None
    open_to_offers: bool | None = None


class SurveyIn(BaseModel):
    """Опрос по отрасли и специализации: определяет, какой тест проходить. На категорию сам по себе не влияет."""
    direction: str = Field(description="Направление: Разработка / Данные и ИИ / Инфраструктура / Качество")
    specialization: str
    primary_stack: str | None = None
    industries: list[str] = Field(default_factory=list, description="Отрасли бизнеса, в которых есть опыт или интерес")
    claimed_grade: Literal["intern", "junior", "middle", "senior"]
    years_experience: float | None = Field(None, ge=0, le=60)
    self_assessment: dict[str, int] = Field(default_factory=dict, description="Самооценка навыков 1–5 (для сравнения с тестом)")
    work_formats: list[Literal["office", "hybrid", "remote"]] = Field(default_factory=list)
    salary_from: int | None = Field(None, ge=0)
    salary_to: int | None = Field(None, ge=0)


class PrivacyIn(BaseModel):
    show_full_name: bool | None = None
    show_city: bool | None = None
    show_about: bool | None = None
    show_experience: bool | None = None
    show_fsp: bool | None = None
    show_salary: bool | None = None


def profile_out(db: Session, p: CandidateProfile) -> dict:
    consent = {}
    for c in db.scalars(select(Consent).where(Consent.user_id == p.user_id).order_by(Consent.id)):
        consent[c.kind] = c.granted
    return {
        "id": p.id, "full_name": p.full_name, "phone": p.phone, "telegram": p.telegram, "contact_email": p.contact_email,
        "city": p.city, "about": p.about, "years_experience": p.years_experience,
        "claimed_skills": p.claimed_skills, "roles": p.roles, "soft_skills": p.soft_skills, "experience": p.experience,
        "education": p.education, "salary_from": p.salary_from, "salary_to": p.salary_to, "work_formats": p.work_formats,
        "relocation": p.relocation, "open_to_offers": p.open_to_offers, "direction": p.direction,
        "specialization": p.specialization, "primary_stack": p.primary_stack, "industries": p.industries,
        "claimed_grade": p.claimed_grade, "category": category(p), "theta": p.theta, "theta_se": p.theta_se,
        "grade_assigned_at": p.grade_assigned_at, "skills": skills_view(p), "fsp": fsp_view(p),
        "privacy": p.privacy, "consents": consent, "resume_parse_meta": p.resume_parse_meta,
        "visible_to_employers": bool(p.grade and p.open_to_offers and consent.get("publication")),
    }


@router.get("/profile", summary="Профиль кандидата целиком")
def get_profile(p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    return profile_out(db, p)


@router.put("/profile", summary="Сохранить анкету/резюме (частичное обновление)")
def put_profile(data: ProfileIn, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    upd = data.model_dump(exclude_unset=True)
    if "claimed_skills" in upd:
        upd["claimed_skills"] = [s for s in upd["claimed_skills"] if s in SKILL_BY_SLUG]
    if upd.get("salary_from") and upd.get("salary_to") and upd["salary_from"] > upd["salary_to"]:
        raise ServiceError(422, "bad_salary", "Нижняя граница зарплаты больше верхней")
    for k, v in upd.items():
        setattr(p, k, v)
    db.commit()
    return profile_out(db, p)


# поле разбора → поле анкеты; ограничения длины — как у колонок и формы профиля
RESUME_MAPPING = {"full_name": "full_name", "email": "contact_email", "phone": "phone", "telegram": "telegram",
                  "city": "city", "years_experience": "years_experience", "roles": "roles", "soft_skills": "soft_skills",
                  "experience": "experience", "education": "education", "about": "about"}
FIELD_LIMITS = {"full_name": 200, "contact_email": 255, "phone": 40, "telegram": 64, "city": 100, "about": 5000,
                "education": 2000}
PARSED_KEYS = ("full_name", "email", "phone", "telegram", "city", "years_experience", "grade", "specialization",
               "skills", "roles", "soft_skills")


def _clean(dst: str, v):
    if isinstance(v, str) and dst in FIELD_LIMITS:
        return v.strip()[:FIELD_LIMITS[dst]] or None
    if dst == "years_experience" and v is not None:
        return min(60.0, max(0.0, float(v)))
    return v


def apply_resume_fields(p: CandidateProfile, fields: dict, applied: dict) -> list[str]:
    """Заполняет анкету из разбора. Пустое поле — заполняется. Поле, которое этот же разбор заполнил раньше и
    кандидат не трогал (значение совпадает с записанным в applied), — уточняется. Остальное не меняется."""
    changed = []
    for src, dst in RESUME_MAPPING.items():
        new, cur = _clean(dst, fields.get(src)), getattr(p, dst)
        if new in (None, "", []) or new == cur:
            continue
        if not cur or (dst in applied and cur == applied[dst]):
            setattr(p, dst, new)
            applied[dst] = new
            changed.append(dst)
    skills = list(dict.fromkeys((p.claimed_skills or []) + (fields.get("skills") or [])))
    if skills != (p.claimed_skills or []):
        p.claimed_skills = skills
        changed.append("claimed_skills")
    return changed


@router.post("/resume", summary="Загрузить PDF-резюме и получить черновик анкеты",
             responses={415: {"description": "Не PDF"}, 422: {"description": "Не удалось извлечь текст"}})
def upload_resume(background: BackgroundTasks, file: UploadFile = File(...), apply: bool = True,
                  p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    """Распознаёт ФИО, контакты, стек, грейд, роли, стаж, софт-скиллы. С apply=true заполняет пустые поля анкеты;
    результат в любом случае возвращается для проверки кандидатом. Черновик по правилам — сразу; если подключена
    LLM, она уточняет черновик фоном (llm_status: pending → done | failed), не трогая поля, исправленные кандидатом."""
    data = file.file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise ServiceError(413, "too_large", "Файл больше 10 МБ")
    if not data.startswith(b"%PDF"):
        raise ServiceError(415, "not_pdf", "Нужен файл в формате PDF")
    try:
        text = resume_svc.pdf_to_text(data)
    except Exception:
        raise ServiceError(422, "bad_pdf", "Не удалось прочитать PDF")
    if len(text) < 30:
        raise ServiceError(422, "no_text", "В PDF нет текстового слоя (скан?). Заполните анкету вручную.")
    llm_on = get_llm().name != "none"
    fields, meta = resume_svc.merge(resume_svc.parse_rules(text), None, get_llm().name)
    applied: dict = {}
    if apply:
        apply_resume_fields(p, fields, applied)
    token = secrets.token_hex(8)
    meta = meta | {"llm_status": "pending" if llm_on else "off", "token": token, "apply": apply, "applied": applied,
                   "parsed": {k: fields.get(k) for k in PARSED_KEYS}}
    p.resume_text = text[:50000]
    p.resume_parse_meta = meta
    db.commit()
    if llm_on:
        background.add_task(refine_resume_with_llm, p.id, token)
    return {"parsed": fields, "meta": meta, "profile": profile_out(db, p)}


def refine_resume_with_llm(profile_id: int, token: str) -> None:
    """Фоновое уточнение черновика моделью: на GTX 1650 около минуты, поэтому не в запросе загрузки."""
    with SessionLocal() as db:
        p = db.get(CandidateProfile, profile_id)
        if not p or (p.resume_parse_meta or {}).get("token") != token:
            return
        text = p.resume_text or ""
    try:
        out = resume_svc.llm_extract(text)  # долго — без открытой транзакции
    except Exception as e:
        log.warning("resume LLM refine failed: %s", e)
        out = None
    with SessionLocal() as db:
        p = db.get(CandidateProfile, profile_id)
        meta = dict(p.resume_parse_meta or {}) if p else {}
        if not p or meta.get("token") != token:  # кандидат уже загрузил другое резюме
            return
        if not out:
            p.resume_parse_meta = meta | {"llm_status": "failed"}
            db.commit()
            return
        fields, m2 = resume_svc.merge(resume_svc.parse_rules(text), out, get_llm().name)
        applied = dict(meta.get("applied") or {})
        changed = apply_resume_fields(p, fields, applied) if meta.get("apply") else []
        p.resume_parse_meta = meta | m2 | {"llm_status": "done", "applied": applied, "updated": changed,
                                           "parsed": {k: fields.get(k) for k in PARSED_KEYS}}
        db.commit()


@router.post("/survey", summary="Пройти опрос: направление, специализация, заявленный грейд")
def survey(data: SurveyIn, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    sp = SPEC_BY_SLUG.get(data.specialization)
    if not sp:
        raise ServiceError(422, "bad_spec", "Неизвестная специализация")
    if p.grade and p.specialization and p.specialization != data.specialization:
        raise ServiceError(409, "spec_locked", "Смена специализации после присвоения категории — через повторное "
                                               "тестирование; обратитесь в поддержку")
    p.direction, p.specialization, p.primary_stack = sp.direction, sp.slug, data.primary_stack
    p.industries = [i for i in data.industries if i in {x["slug"] for x in INDUSTRIES}]
    p.claimed_grade = data.claimed_grade
    if data.years_experience is not None:
        p.years_experience = data.years_experience
    if data.work_formats:
        p.work_formats = data.work_formats
    if data.salary_from is not None:
        p.salary_from = data.salary_from
    if data.salary_to is not None:
        p.salary_to = data.salary_to
    db.add(SurveyResponse(candidate_id=p.id, answers=data.model_dump()))
    db.commit()
    recommended = data.claimed_grade if data.claimed_grade in TESTABLE_GRADES else "junior"
    return {"profile": profile_out(db, p), "recommended_test_grade": recommended}


@router.get("/status", summary="Категория, грейд, доступность тестов, история опросов и тестов")
def status(p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    attempts = db.scalars(select(TestAttempt).where(TestAttempt.candidate_id == p.id).order_by(TestAttempt.id.desc())).all()
    history = db.scalars(select(GradeHistory).where(GradeHistory.candidate_id == p.id).order_by(GradeHistory.id.desc())).all()
    surveys = db.scalars(select(SurveyResponse).where(SurveyResponse.candidate_id == p.id).order_by(SurveyResponse.id.desc())).all()
    consent = {}
    for c in db.scalars(select(Consent).where(Consent.user_id == p.user_id).order_by(Consent.id)):
        consent[c.kind] = c.granted
    steps = [
        {"key": "survey", "title": "Опрос по специализации", "done": bool(p.specialization)},
        {"key": "test", "title": "Тест на грейд", "done": bool(p.grade)},
        {"key": "profile", "title": "Анкета и условия", "done": bool(p.full_name and (p.salary_from or p.salary_to))},
        {"key": "fsp", "title": "Привязка ФСП ID (необязательно)", "done": bool(p.fsp_id), "optional": True},
        {"key": "publication", "title": "Согласие на показ профиля работодателям", "done": bool(consent.get("publication"))},
    ]
    active = next((a for a in attempts if a.status == "in_progress"), None)
    return {
        "category": category(p), "claimed_grade": p.claimed_grade, "theta": p.theta, "theta_se": p.theta_se,
        "grade_assigned_at": p.grade_assigned_at, "steps": steps,
        "visible_to_employers": bool(p.grade and p.open_to_offers and consent.get("publication")),
        "availability": testing.availability(db, p) if p.specialization else {},
        "active_attempt_id": active.id if active else None,
        "attempts": [testing.attempt_public(a) for a in attempts[:20]],
        "grade_history": [{"from": h.from_grade, "to": h.to_grade, "reason": h.reason, "at": h.created_at,
                           "specialization": h.specialization} for h in history],
        "surveys": [{"at": s.created_at, "specialization": s.answers.get("specialization"),
                     "claimed_grade": s.answers.get("claimed_grade")} for s in surveys[:10]],
    }


@router.get("/insights", summary="Что требуют работодатели в моей категории и чего не хватает в профиле")
def insights(p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    return candidate_insights(db, p)


@router.put("/privacy", summary="Настройки приватности: что видно работодателю")
def privacy(data: PrivacyIn, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    pv = dict(p.privacy or {})
    pv.update(data.model_dump(exclude_none=True))
    p.privacy = pv
    db.commit()
    return pv


@router.get("/profile.pdf", summary="Стандартизированный PDF-профиль", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
def profile_pdf(p: CandidateProfile = Depends(candidate_profile)):
    pdf = resume_svc.render_profile_pdf(p, (p.fsp_data or {}).get("summary"))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="profile_{p.id}.pdf"'})


@router.get("/grades", summary="Справка по грейдам и порогам теста")
def grades_info():
    return [{"slug": g, "name": GRADE_BY_SLUG[g]["name"], "cut": GRADE_BY_SLUG[g]["cut"],
             "experience": GRADE_BY_SLUG[g]["experience"]} for g in TESTABLE_GRADES]
