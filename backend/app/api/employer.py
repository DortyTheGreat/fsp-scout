"""Личный кабинет работодателя: компания, потребности и подборки, каталог категорий, поиск по банку, карточки."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, employer_company
from app.api.serializers import candidate_for_employer, need_view
from app.core.db import get_db
from app.core.errors import ServiceError, not_found
from app.models import AuditLog, CandidateProfile, Company, ItemResponse, Need, ShortlistEntry, TestAttempt
from app.services.matching import ranker
from app.services.matching import service as matching
from app.services.matching.service import visible_candidates
from app.taxonomy import GRADE_BY_SLUG, SKILL_BY_SLUG, SPEC_BY_SLUG

router = APIRouter(prefix="/employer", tags=["Работодатель"], responses=AUTH_ERRORS)


class CompanyIn(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    industry: str | None = None
    website: str | None = None
    city: str | None = None
    size: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    contact_telegram: str | None = None


class NeedIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field("", max_length=8000, description="Чем занимается команда, задачи")
    specialization: str
    grades: list[Literal["intern", "junior", "middle", "senior"]] = Field(min_length=1)
    must_skills: list[str] = Field(default_factory=list)
    nice_skills: list[str] = Field(default_factory=list)
    work_formats: list[Literal["office", "hybrid", "remote"]] = Field(default_factory=list)
    city: str | None = None
    salary_from: int | None = Field(None, ge=0)
    salary_to: int | None = Field(None, ge=0)
    allow_adjacent: bool = False
    parsed_by: str = "manual"

    @model_validator(mode="after")
    def check(self):
        if self.specialization not in SPEC_BY_SLUG:
            raise ValueError("Неизвестная специализация")
        self.must_skills = [s for s in self.must_skills if s in SKILL_BY_SLUG]
        self.nice_skills = [s for s in self.nice_skills if s in SKILL_BY_SLUG and s not in self.must_skills]
        if self.salary_from and self.salary_to and self.salary_from > self.salary_to:
            raise ValueError("Нижняя граница вилки больше верхней")
        return self


class ParseIn(BaseModel):
    text: str = Field(min_length=10, max_length=8000)


class ShortlistIn(BaseModel):
    candidate_id: int
    note: str = ""


def _need(db: Session, comp: Company, need_id: int) -> Need:
    n = db.get(Need, need_id)
    if not n or n.company_id != comp.id:
        raise not_found("Потребность")
    return n


@router.get("/company", summary="Профиль компании")
def get_company(comp: Company = Depends(employer_company)):
    return {k: getattr(comp, k) for k in ("id", "name", "description", "industry", "website", "city", "size",
                                          "contact_name", "contact_email", "contact_phone", "contact_telegram")}


@router.put("/company", summary="Обновить профиль компании")
def put_company(data: CompanyIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(comp, k, v)
    db.commit()
    return get_company(comp)


# ------------------------------------------------------------------ потребности
@router.post("/needs/parse", summary="Разобрать текстовое описание потребности в структуру (LLM или правила)")
def parse_need(data: ParseIn, comp: Company = Depends(employer_company)):
    return matching.parse_need_text(data.text)


@router.get("/needs", summary="Список потребностей компании")
def list_needs(comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    rows = db.scalars(select(Need).where(Need.company_id == comp.id).order_by(Need.id.desc())).all()
    return [need_view(n) for n in rows]


@router.post("/needs", status_code=201, summary="Создать потребность — на её основе строится подборка")
def create_need(data: NeedIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    n = Need(company_id=comp.id, **data.model_dump())
    db.add(n)
    db.commit()
    return need_view(n)


@router.get("/needs/{need_id}", summary="Потребность")
def get_need(need_id: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    return need_view(_need(db, comp, need_id))


@router.put("/needs/{need_id}", summary="Изменить потребность (подборка пересчитается, закреплённые кандидаты сохранятся)")
def update_need(need_id: int, data: NeedIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    n = _need(db, comp, need_id)
    for k, v in data.model_dump().items():
        setattr(n, k, v)
    db.commit()
    return need_view(n)


@router.delete("/needs/{need_id}", status_code=204, summary="Закрыть потребность")
def close_need(need_id: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    n = _need(db, comp, need_id)
    n.status = "closed"
    db.commit()


@router.get("/needs/{need_id}/categories", summary="Рекомендованные категории под потребность")
def need_categories(need_id: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    return matching.catalog(db, _need(db, comp, need_id))


@router.get("/needs/{need_id}/candidates", summary="Подборка: ранжированные кандидаты с объяснением",
            description="Фильтры уточняют выдачу, не теряя подборку: закреплённые кандидаты, скрытые фильтром, "
                        "возвращаются отдельно в pinned_hidden.")
def need_candidates(need_id: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db),
                    grades: list[str] = Query(default=[]), skills: list[str] = Query(default=[]),
                    has_fsp: bool = False, salary_max: int | None = None, formats: list[str] = Query(default=[]),
                    must_full: bool = False, min_score: float | None = None, include_adjacent: bool | None = None,
                    include_borderline: bool = Query(True, description="Показывать кандидатов на границе с грейдом "
                                                                        "запроса (вероятность ≥ 30%) — после точной категории"),
                    limit: int = Query(30, le=200), offset: int = 0):
    n = _need(db, comp, need_id)
    res = matching.need_results(db, n, {"grades": grades, "skills": skills, "has_fsp": has_fsp, "salary_max": salary_max,
                                        "formats": formats, "must_full": must_full, "min_score": min_score},
                                include_adjacent, include_borderline)

    def row(r, pinned=False, hidden=False):
        c = r["candidate"]
        return candidate_for_employer(db, c, comp, brief=True, extra={
            "score": r["score"], "features": r["features"], "explanation": r["explanation"],
            "pinned": c.id in res["pinned_ids"], "filtered_out": hidden, "invitation_status": res["invited"].get(c.id)})

    items = res["items"][offset: offset + limit]
    return {"need": need_view(n), "total_in_category": res["total_in_category"], "total": res["total"],
            "items": [row(r) for r in items], "pinned_hidden": [row(r, hidden=True) for r in res["pinned_hidden"]],
            "weights": res["weights"], "factor_names": ranker.FACTOR_NAMES}


@router.get("/needs/{need_id}/shortlist", summary="Подборка (закреплённые кандидаты)")
def get_shortlist(need_id: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    n = _need(db, comp, need_id)
    rows = db.scalars(select(ShortlistEntry).where(ShortlistEntry.need_id == n.id).order_by(ShortlistEntry.id)).all()
    out = []
    for e in rows:
        c = db.get(CandidateProfile, e.candidate_id)
        if c:
            out.append(candidate_for_employer(db, c, comp, brief=True, extra={"note": e.note, "snapshot": e.snapshot,
                                                                              "pinned_at": e.created_at}))
    return out


@router.post("/needs/{need_id}/shortlist", status_code=201, summary="Закрепить кандидата в подборке")
def add_shortlist(need_id: int, data: ShortlistIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    n = _need(db, comp, need_id)
    c = db.get(CandidateProfile, data.candidate_id)
    if not c or not matching.is_visible(db, c):
        raise not_found("Кандидат")
    if db.scalars(select(ShortlistEntry).where(ShortlistEntry.need_id == n.id, ShortlistEntry.candidate_id == c.id)).first():
        return {"status": "exists"}
    f, d = ranker.features(ranker.Requirement.from_obj(n), c)
    db.add(ShortlistEntry(need_id=n.id, candidate_id=c.id, note=data.note,
                          snapshot={"score": ranker.score(f, matching.active_weights(db)), "features": f}))
    db.commit()
    return {"status": "added"}


@router.delete("/needs/{need_id}/shortlist/{candidate_id}", status_code=204, summary="Убрать из подборки")
def del_shortlist(need_id: int, candidate_id: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    n = _need(db, comp, need_id)
    e = db.scalars(select(ShortlistEntry).where(ShortlistEntry.need_id == n.id, ShortlistEntry.candidate_id == candidate_id)).first()
    if e:
        db.delete(e)
        db.commit()


# ------------------------------------------------------------------ каталог и поиск
@router.get("/categories", summary="Каталог категорий (специализация × грейд) с размерами и рыночными ожиданиями")
def categories(comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    return matching.catalog(db)


@router.get("/search", summary="Поиск по банку кандидатов",
            description="Фильтры: специализация, грейд (категория), навыки с минимальной оценкой по тесту, наличие "
                        "подтверждённых достижений ФСП, зарплата, формат. Сортировка — по силе подтверждённого профиля.")
def search(comp: Company = Depends(employer_company), db: Session = Depends(get_db), specialization: str | None = None,
           grade: str | None = None, skills: list[str] = Query(default=[]), min_skill_score: int = 50,
           has_fsp: bool = False, fsp_prize: bool = Query(False, description="Только призёры соревнований ФСП"),
           sort: Literal["strength", "fsp"] = Query("strength", description="strength — сила профиля (тест + ФСП), "
                                                                             "fsp — сила результатов ФСП"),
           salary_max: int | None = None, formats: list[str] = Query(default=[]),
           q: str | None = None, limit: int = Query(30, le=200), offset: int = 0):
    rows = matching.search(db, {"specialization": specialization, "grade": grade, "skills": skills,
                                "min_skill_score": min_skill_score, "has_fsp": has_fsp, "fsp_prize": fsp_prize,
                                "sort": sort, "salary_max": salary_max, "formats": formats, "q": q})
    return {"total": len(rows), "items": [candidate_for_employer(db, r["candidate"], comp, brief=True,
                                                                  extra={"score": r["score"], "explanation": r["explanation"]})
                                          for r in rows[offset: offset + limit]]}


@router.get("/candidates/{candidate_id}", summary="Карточка кандидата с доказательствами навыков",
            description="Контакты (contacts) присутствуют, только если кандидат принял приглашение компании или откликнулся.")
def candidate_card(candidate_id: int, need_id: int | None = None, comp: Company = Depends(employer_company),
                   db: Session = Depends(get_db)):
    c = db.get(CandidateProfile, candidate_id)
    if not c or not matching.is_visible(db, c) and not _has_relation(db, comp, c):
        raise not_found("Кандидат")
    extra = {}
    if need_id:
        n = _need(db, comp, need_id)
        req = ranker.Requirement.from_obj(n)
        f, d = ranker.features(req, c)
        w = matching.active_weights(db)
        extra = {"score": ranker.score(f, w), "features": f, "explanation": ranker.explain(req, c, f, d, w)}
    tests = db.scalars(select(TestAttempt).where(TestAttempt.candidate_id == c.id, TestAttempt.status == "finished",
                                                 TestAttempt.kind == "grade").order_by(TestAttempt.id.desc())).all()
    extra["tests"] = [{"id": t.id, "target_grade": t.target_grade, "target_grade_name": GRADE_BY_SLUG[t.target_grade]["name"],
                       "outcome": t.outcome, "theta": t.theta, "se": t.se, "n_items": len(t.responses),
                       "finished_at": t.finished_at} for t in tests[:5]]
    db.add(AuditLog(actor_user_id=comp.owner_user_id, action="view_candidate", target_type="candidate", target_id=c.id))
    db.commit()
    return candidate_for_employer(db, c, comp, extra=extra)


def _has_relation(db: Session, comp: Company, c: CandidateProfile) -> bool:
    from app.api.serializers import contacts_unlocked
    return contacts_unlocked(db, comp.id, c.id)


@router.get("/candidates/{candidate_id}/evidence/{response_id}", summary="Доказательство: конкретное задание и ответ кандидата",
            description="Экземпляр задания уникален для кандидата, поэтому его показ работодателю не раскрывает банк.")
def evidence(candidate_id: int, response_id: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    c = db.get(CandidateProfile, candidate_id)
    r = db.get(ItemResponse, response_id)
    if not c or not r or r.attempt.candidate_id != c.id or not r.scored or not matching.is_visible(db, c):
        raise not_found("Задание")
    rd = r.rendered or {}
    key = r.key or {}
    ans = key.get("answer")
    return {"title": rd.get("title"), "prompt": rd.get("prompt"), "code": rd.get("code"), "lang": rd.get("lang"),
            "fmt": rd.get("fmt"), "options": rd.get("options"), "correct_answer": ans, "candidate_answer": (r.response or {}).get("value"),
            "is_correct": r.is_correct, "time_ms": r.time_ms, "difficulty_b": r.b, "discrimination_a": r.a,
            "answered_at": r.answered_at}


@router.get("/insights", summary="Аналитика по приглашениям и причинам отказов с рекомендациями")
def insights(comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    return matching.employer_insights(db, comp.id)


_ = ServiceError
