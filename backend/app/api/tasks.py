"""Регулярные короткие задания от работодателей: «реши или предложи подход».

Система периодически (не чаще раза в 7 дней) предлагает кандидату 1–2 задания его специализации и грейда.
Ответ оценивается автоматически по рубрике работодателя (LLM или ключевые слова), работодатель может
поставить свою оценку. Сдача задания обновляет «свежесть» профиля — фактор ранжирования.
"""
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, candidate_profile, employer_company
from app.core.db import SessionLocal, get_db
from app.core.errors import ServiceError, not_found
from app.core.security import utcnow
from app.models import CandidateProfile, Company, RegularTask, TaskAssignment
from app.services import rubric as rubric_svc
from app.services.llm import get_llm
from app.taxonomy import GRADE_ORDER, SKILL_BY_SLUG, SPEC_BY_SLUG

router = APIRouter(tags=["Регулярные задания"], responses=AUTH_ERRORS)
OFFER_EVERY_DAYS = 7


class RubricItem(BaseModel):
    criterion: str
    keywords: list[str] = Field(default_factory=list)
    weight: float = 1.0


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=5000)
    specialization: str
    skills: list[str] = Field(default_factory=list)
    min_grade: str = "junior"
    rubric: list[RubricItem] = Field(default_factory=list)
    active: bool = True


class SubmitIn(BaseModel):
    answer: str = Field(min_length=20, max_length=10000)


class ReviewIn(BaseModel):
    score: float = Field(ge=0, le=10)
    comment: str | None = None


def quick_score(task: RegularTask, answer: str) -> tuple[float, dict]:
    """Мгновенная оценка 0–10: по ключевым словам критериев (без рубрики — по объёму). Уточнение моделью — фоном."""
    rubric = task.rubric or []
    if not rubric:
        return rubric_svc.auto_score(task.body, [], answer)
    return rubric_svc.keyword_score(rubric, answer)


def refine_score_with_llm(asg_id: int) -> None:
    """Фоновая оценка ответа моделью по рубрике (на GTX 1650 — около 30 с). Балл — по отметкам и весам в коде."""
    with SessionLocal() as db:
        a = db.get(TaskAssignment, asg_id)
        if not a or not a.answer:
            return
        body, rubric, answer = a.task.body, list(a.task.rubric or []), a.answer
    try:
        res = rubric_svc.from_llm(rubric, rubric_svc.llm_extract(body, rubric, answer))
    except Exception:
        res = None
    with SessionLocal() as db:
        a = db.get(TaskAssignment, asg_id)
        if not a or a.answer != answer:
            return
        if res:
            a.auto_score, a.auto_feedback = res[0], res[1] | {"llm_status": "done"}
        else:
            a.auto_feedback = dict(a.auto_feedback or {}) | {"llm_status": "failed"}
        db.commit()


def _task_view(t: RegularTask, stats: bool = False, db: Session | None = None) -> dict:
    d = {"id": t.id, "title": t.title, "body": t.body, "specialization": t.specialization, "skills": t.skills,
         "skill_names": [SKILL_BY_SLUG[s].name for s in t.skills if s in SKILL_BY_SLUG], "min_grade": t.min_grade,
         "active": t.active, "company": t.company.name if t.company else None, "created_at": t.created_at}
    if stats and db is not None:
        d["rubric"] = t.rubric
        asg = db.scalars(select(TaskAssignment).where(TaskAssignment.task_id == t.id)).all()
        d["stats"] = {"offered": len(asg), "submitted": sum(1 for a in asg if a.status in ("submitted", "reviewed"))}
    return d


# ------------------------------------------------------------------ работодатель
@router.get("/employer/tasks", summary="Задания компании", tags=["Работодатель"])
def emp_tasks(comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    return [_task_view(t, True, db) for t in db.scalars(select(RegularTask).where(RegularTask.company_id == comp.id)
                                                         .order_by(RegularTask.id.desc()))]


@router.post("/employer/tasks", status_code=201, summary="Создать короткое задание для кандидатов", tags=["Работодатель"])
def create_task(data: TaskIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    if data.specialization not in SPEC_BY_SLUG or data.min_grade not in GRADE_ORDER:
        raise ServiceError(422, "bad_input", "Неизвестная специализация или грейд")
    t = RegularTask(company_id=comp.id, title=data.title, body=data.body, specialization=data.specialization,
                    skills=[s for s in data.skills if s in SKILL_BY_SLUG], min_grade=data.min_grade,
                    rubric=[r.model_dump() for r in data.rubric], active=data.active)
    db.add(t)
    db.commit()
    db.refresh(t)
    return _task_view(t, True, db)


@router.get("/employer/tasks/{task_id}/answers", summary="Ответы кандидатов на задание", tags=["Работодатель"])
def task_answers(task_id: int, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    t = db.get(RegularTask, task_id)
    if not t or t.company_id != comp.id:
        raise not_found("Задание")
    from app.api.serializers import candidate_for_employer
    out = []
    for a in db.scalars(select(TaskAssignment).where(TaskAssignment.task_id == t.id,
                                                     TaskAssignment.status.in_(("submitted", "reviewed")))):
        c = db.get(CandidateProfile, a.candidate_id)
        out.append({"id": a.id, "answer": a.answer, "auto_score": a.auto_score, "auto_feedback": a.auto_feedback,
                    "employer_score": a.employer_score, "employer_comment": a.employer_comment,
                    "submitted_at": a.submitted_at, "candidate": candidate_for_employer(db, c, comp, brief=True)})
    out.sort(key=lambda x: -(x["employer_score"] or x["auto_score"] or 0))
    return out


@router.post("/employer/task-answers/{asg_id}/review", summary="Оценить ответ кандидата", tags=["Работодатель"])
def review(asg_id: int, data: ReviewIn, comp: Company = Depends(employer_company), db: Session = Depends(get_db)):
    a = db.get(TaskAssignment, asg_id)
    if not a or a.task.company_id != comp.id:
        raise not_found("Ответ")
    a.employer_score, a.employer_comment, a.status = data.score, data.comment, "reviewed"
    db.commit()
    return {"status": "reviewed"}


# ------------------------------------------------------------------ кандидат
def offer_tasks(db: Session, p: CandidateProfile) -> None:
    if not p.specialization or not p.grade:
        return
    recent = db.scalars(select(TaskAssignment).where(TaskAssignment.candidate_id == p.id,
                                                     TaskAssignment.created_at >= utcnow() - timedelta(days=OFFER_EVERY_DAYS))).first()
    if recent:
        return
    seen = {a.task_id for a in db.scalars(select(TaskAssignment).where(TaskAssignment.candidate_id == p.id))}
    gi = GRADE_ORDER.index(p.grade)
    tasks = [t for t in db.scalars(select(RegularTask).where(RegularTask.active.is_(True),
                                                             RegularTask.specialization == p.specialization))
             if t.id not in seen and GRADE_ORDER.index(t.min_grade) <= gi]
    tasks.sort(key=lambda t: -len(set(t.skills) & set((p.skill_scores or {}).keys())))
    for t in tasks[:2]:
        db.add(TaskAssignment(task_id=t.id, candidate_id=p.id))
    db.commit()


@router.get("/tasks", summary="Предложенные мне задания (выдаются раз в неделю)")
def my_tasks(p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    offer_tasks(db, p)
    rows = db.scalars(select(TaskAssignment).where(TaskAssignment.candidate_id == p.id).order_by(TaskAssignment.id.desc())).all()
    return [{"id": a.id, "status": a.status, "answer": a.answer, "auto_score": a.auto_score,
             "auto_feedback": a.auto_feedback, "employer_score": a.employer_score, "employer_comment": a.employer_comment,
             "created_at": a.created_at, "submitted_at": a.submitted_at, "task": _task_view(a.task)} for a in rows]


@router.post("/tasks/{asg_id}/submit", summary="Отправить решение или подход")
def submit(asg_id: int, data: SubmitIn, background: BackgroundTasks, p: CandidateProfile = Depends(candidate_profile),
           db: Session = Depends(get_db)):
    a = db.get(TaskAssignment, asg_id)
    if not a or a.candidate_id != p.id:
        raise not_found("Задание")
    if a.status != "offered":
        raise ServiceError(409, "bad_status", "Ответ уже отправлен")
    score, fb = quick_score(a.task, data.answer)
    llm_on = get_llm().name != "none" and bool(a.task.rubric)
    if llm_on:
        fb = fb | {"llm_status": "pending"}
    a.answer, a.auto_score, a.auto_feedback, a.status, a.submitted_at = data.answer, score, fb, "submitted", utcnow()
    p.last_activity_at = utcnow()
    db.commit()
    if llm_on:
        background.add_task(refine_score_with_llm, a.id)
    return {"id": a.id, "status": a.status, "auto_score": score, "auto_feedback": fb}


@router.post("/tasks/{asg_id}/skip", summary="Пропустить задание")
def skip(asg_id: int, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    a = db.get(TaskAssignment, asg_id)
    if not a or a.candidate_id != p.id:
        raise not_found("Задание")
    a.status = "skipped"
    db.commit()
    return {"status": "skipped"}
