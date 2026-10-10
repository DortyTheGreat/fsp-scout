"""Вакансии и самостоятельные отклики (дополнительный сценарий к основной механике приглашений)."""
import random
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, candidate_profile, current_user, employer_company
from app.api.serializers import application_view, vacancy_view
from app.core.db import get_db
from app.core.errors import ServiceError, forbidden, not_found
from app.models import (Application, AuditLog, CandidateProfile, Company, StatusEvent, TestAttempt, User, Vacancy)
from app.services import mailer
from app.services.matching import ranker
from app.services.matching import service as matching
from app.services.testing import cat
from app.services.testing import service as testing
from app.taxonomy import GRADE_BY_SLUG, SKILL_BY_SLUG, SPEC_BY_SLUG

router = APIRouter(tags=["Вакансии и отклики"], responses=AUTH_ERRORS)


class VacancyIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=8000)
    specialization: str
    grade: Literal["intern", "junior", "middle", "senior"]
    must_skills: list[str] = Field(default_factory=list)
    nice_skills: list[str] = Field(default_factory=list)
    work_format: Literal["office", "hybrid", "remote"] = "hybrid"
    city: str | None = None
    salary_from: int = Field(gt=0, description="Обязательно, ₽/мес")
    salary_to: int = Field(gt=0, description="Обязательно, ₽/мес")
    status: Literal["draft", "published", "closed"] = "published"

    @model_validator(mode="after")
    def check(self):
        if self.specialization not in SPEC_BY_SLUG:
            raise ValueError("Неизвестная специализация")
        if self.salary_from > self.salary_to:
            raise ValueError("Нижняя граница вилки больше верхней")
        self.must_skills = [s for s in self.must_skills if s in SKILL_BY_SLUG]
        self.nice_skills = [s for s in self.nice_skills if s in SKILL_BY_SLUG and s not in self.must_skills]
        return self


class ApplyIn(BaseModel):
    cover_letter: str = Field("", max_length=3000)


class AppStatusIn(BaseModel):
    status: Literal["viewed", "accepted", "rejected"]
    reason: str | None = None
    comment: str | None = Field(None, max_length=2000)


# ------------------------------------------------------------------ работодатель
@router.get("/employer/vacancies", summary="Вакансии компании", tags=["Работодатель"])
def my_vacancies(comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    rows = db.scalars(select(Vacancy).where(Vacancy.company_id == comp.id).order_by(Vacancy.id.desc())).all()
    out = []
    for v in rows:
        d = vacancy_view(v)
        apps = db.scalars(select(Application).where(Application.vacancy_id == v.id)).all()
        d["applications"] = {"total": len(apps), "new": sum(1 for a in apps if a.status == "sent")}
        out.append(d)
    return out


@router.post("/employer/vacancies", status_code=201, summary="Опубликовать вакансию (вилка обязательна)", tags=["Работодатель"])
def create_vacancy(data: VacancyIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    if not comp.name:
        raise ServiceError(422, "company_required", "Заполните название компании")
    v = Vacancy(company_id=comp.id, **data.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return vacancy_view(v)


def _my_vac(db: Session, comp: Company, vid: int) -> Vacancy:
    v = db.get(Vacancy, vid)
    if not v or v.company_id != comp.id:
        raise not_found("Вакансия")
    return v


@router.put("/employer/vacancies/{vid}", summary="Редактировать вакансию", tags=["Работодатель"])
def update_vacancy(vid: int, data: VacancyIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    v = _my_vac(db, comp, vid)
    for k, val in data.model_dump().items():
        setattr(v, k, val)
    db.commit()
    return vacancy_view(v)


@router.get("/employer/vacancies/{vid}/applications", summary="Отклики на вакансию с оценкой соответствия",
            tags=["Работодатель"])
def vacancy_applications(vid: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    v = _my_vac(db, comp, vid)
    apps = db.scalars(select(Application).where(Application.vacancy_id == v.id)).all()
    for a in apps:  # открытие списка работодателем = «просмотрено»
        if a.status == "sent":
            a.status = "viewed"
            db.add(StatusEvent(entity="application", entity_id=a.id, status="viewed", actor_role="employer"))
    db.commit()
    rows = [application_view(a, v, "employer", db, db.get(CandidateProfile, a.candidate_id)) for a in apps]
    rows.sort(key=lambda r: -(r.get("match") or {}).get("score", 0))
    return rows


@router.post("/employer/applications/{app_id}/status", summary="Сменить статус отклика", tags=["Работодатель"])
def set_app_status(app_id: int, data: AppStatusIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise not_found("Отклик")
    v = _my_vac(db, comp, a.vacancy_id)
    if a.status == "withdrawn":
        raise ServiceError(409, "bad_status", "Кандидат отозвал отклик")
    a.status = data.status
    if data.status == "rejected":
        a.reject_reason, a.employer_comment = data.reason, data.comment
    elif data.comment:
        a.employer_comment = data.comment
    db.add(StatusEvent(entity="application", entity_id=a.id, status=data.status, actor_role="employer"))
    cand = db.get(CandidateProfile, a.candidate_id)
    if data.status in ("accepted", "rejected"):
        mailer.send(db, cand.contact_email or cand.user.email, f"Ответ по отклику: {v.title}",
                    f"Статус вашего отклика: {'приглашение к общению' if data.status == 'accepted' else 'отказ'}.")
    db.commit()
    return application_view(a, v, "employer", db, cand)


@router.get("/employer/vacancies/{vid}/test-blueprint", summary="Как система сформирует тест под эту вакансию",
            tags=["Работодатель"],
            description="Чертёж теста (доли навыков), откалиброванный пул шаблонов и 3 примера уникальных экземпляров "
                        "одного шаблона — демонстрация устойчивости к утечке заданий.")
def test_blueprint(vid: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    v = _my_vac(db, comp, vid)
    return build_blueprint(db, v)


def build_blueprint(db: Session, v: Vacancy) -> dict:
    pool = testing.pool_for(db, v.specialization)
    core = list(SPEC_BY_SLUG[v.specialization].core_skills)
    bp = cat.blueprint_from_requirements(v.must_skills, v.nice_skills, pool, core)
    uncovered = [s for s in v.must_skills + v.nice_skills if s not in bp]
    by_skill = {}
    for s in bp:
        items = [p for p in pool if p.skills.get(s, 0) >= 0.5]
        by_skill[s] = {"name": SKILL_BY_SLUG[s].name, "share": round(bp[s], 3), "templates": len(items),
                       "difficulty_range": [round(min(p.b for p in items), 2), round(max(p.b for p in items), 2)] if items else None}
    # пример: один шаблон, три разных кандидата — три разных экземпляра
    rng = random.Random(secrets.randbits(32))
    top_skill = max(bp, key=bp.get) if bp else None
    sample = None
    if top_skill:
        cands = [p for p in pool if p.skills.get(top_skill, 0) >= 0.5]
        cands.sort(key=lambda p: abs(p.b - GRADE_BY_SLUG[v.grade]["cut"]) if v.grade != "intern" else p.b)
        t = cands[0]
        sample = {"template_id": t.id, "a": t.a, "b": t.b,
                  "instances": [testing.render(db, t.id, rng.randrange(2 ** 31)).public() for _ in range(3)]}
    return {"vacancy_id": v.id, "grade": v.grade, "cut_theta": GRADE_BY_SLUG[v.grade]["cut"], "blueprint": by_skill,
            "uncovered_skills": [{"slug": s, "name": SKILL_BY_SLUG[s].name} for s in uncovered],
            "pool_size": len(pool), "min_items": testing.settings.test_min_items,
            "max_items": testing.settings.test_max_items, "sample": sample}


# ------------------------------------------------------------------ кандидат
@router.get("/vacancies", summary="Опубликованные вакансии (для кандидатов)")
def public_vacancies(user: User = Depends(current_user), db: Session = Depends(get_db), specialization: str | None = None,
                     grade: str | None = None, q: str | None = None, salary_min: int | None = None,
                     work_format: str | None = None, limit: int = Query(50, le=200), offset: int = 0):
    query = select(Vacancy).where(Vacancy.status == "published")
    if specialization:
        query = query.where(Vacancy.specialization == specialization)
    if grade:
        query = query.where(Vacancy.grade == grade)
    if work_format:
        query = query.where(Vacancy.work_format == work_format)
    if salary_min:
        query = query.where(Vacancy.salary_to >= salary_min)
    rows = db.scalars(query.order_by(Vacancy.id.desc())).all()
    if q:
        rows = [v for v in rows if q.lower() in (v.title + " " + v.description).lower()]
    cand = user.candidate if user.role == "candidate" else None
    applied = {}
    if cand:
        applied = {a.vacancy_id: a.status for a in db.scalars(select(Application).where(Application.candidate_id == cand.id))}
    out = []
    for v in rows:
        d = vacancy_view(v)
        if cand and cand.grade:
            req = ranker.Requirement.from_obj(v)
            f, det = ranker.features(req, cand)
            d["match"] = {"score": ranker.score(f), "summary": ranker.explain(req, cand, f, det)["summary"],
                          "same_category": cand.specialization == v.specialization and cand.grade == v.grade}
        d["my_application"] = applied.get(v.id)
        out.append(d)
    if cand and cand.grade:
        out.sort(key=lambda d: -d["match"]["score"])
    return {"total": len(out), "items": out[offset: offset + limit]}


@router.get("/vacancies/{vid}", summary="Вакансия")
def get_vacancy(vid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.get(Vacancy, vid)
    if not v or (v.status != "published" and not (user.company and user.company.id == v.company_id)):
        raise not_found("Вакансия")
    d = vacancy_view(v)
    if user.role == "candidate" and user.candidate:
        a = db.scalars(select(Application).where(Application.vacancy_id == v.id,
                                                 Application.candidate_id == user.candidate.id)).first()
        d["my_application"] = a.status if a else None
        t = db.scalars(select(TestAttempt).where(TestAttempt.vacancy_id == v.id,
                                                 TestAttempt.candidate_id == user.candidate.id)).first()
        d["my_vacancy_test"] = testing.attempt_public(t) if t else None
    return d


@router.post("/vacancies/{vid}/apply", status_code=201, summary="Откликнуться на вакансию (контакты станут видны работодателю)",
             responses={409: {"description": "Отклик уже есть"}})
def apply(vid: int, data: ApplyIn, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    v = db.get(Vacancy, vid)
    if not v or v.status != "published":
        raise not_found("Вакансия")
    if db.scalars(select(Application).where(Application.vacancy_id == v.id, Application.candidate_id == p.id)).first():
        raise ServiceError(409, "duplicate", "Вы уже откликались на эту вакансию")
    snap = {}
    if p.grade:
        req = ranker.Requirement.from_obj(v)
        f, det = ranker.features(req, p)
        snap = {"score": ranker.score(f, matching.active_weights(db)), "features": f, "explanation": ranker.explain(req, p, f, det)}
    a = Application(vacancy_id=v.id, candidate_id=p.id, cover_letter=data.cover_letter, match_snapshot=snap)
    db.add(a)
    db.flush()
    db.add(StatusEvent(entity="application", entity_id=a.id, status="sent", actor_role="candidate"))
    db.add(AuditLog(actor_user_id=p.user_id, action="contacts_revealed", target_type="company", target_id=v.company_id,
                    meta={"application_id": a.id}))
    db.commit()
    return application_view(a, v, "candidate")


@router.get("/applications", summary="Мои отклики и их статусы (кандидат)")
def my_applications(p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    rows = db.scalars(select(Application).where(Application.candidate_id == p.id).order_by(Application.id.desc())).all()
    return [application_view(a, db.get(Vacancy, a.vacancy_id), "candidate") for a in rows]


@router.post("/applications/{app_id}/withdraw", summary="Отозвать отклик")
def withdraw(app_id: int, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a or a.candidate_id != p.id:
        raise not_found("Отклик")
    a.status = "withdrawn"
    db.add(StatusEvent(entity="application", entity_id=a.id, status="withdrawn", actor_role="candidate"))
    db.commit()
    return application_view(a, db.get(Vacancy, a.vacancy_id), "candidate")


_ = forbidden
