"""Прохождение адаптивного теста кандидатом."""
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, candidate_profile
from app.core.db import get_db
from app.core.errors import ServiceError, not_found
from app.models import CandidateProfile, TestAttempt, Vacancy
from app.services.testing import service as testing

router = APIRouter(prefix="/tests", tags=["Тестирование"], responses=AUTH_ERRORS)


class StartIn(BaseModel):
    target_grade: Literal["junior", "middle", "senior"]
    vacancy_id: int | None = None


class AnswerIn(BaseModel):
    item_id: int
    value: Any = None  # single: индекс варианта; multi: список индексов; input: строка


def _own(db: Session, p: CandidateProfile, attempt_id: int) -> TestAttempt:
    a = db.get(TestAttempt, attempt_id)
    if not a or a.candidate_id != p.id:
        raise not_found("Тест")
    return a


def _view(a: TestAttempt) -> dict:
    d = testing.attempt_public(a, with_items=a.status == "finished")
    cur = testing.current_item(a) if a.status == "in_progress" else None
    if cur:
        d["current"] = {"id": cur.id, "order": cur.order, **cur.rendered, "presented_at": cur.presented_at}
    return d


@router.post("/start", summary="Начать тест на грейд (или продолжить незавершённый)",
             responses={409: {"description": "Не пройден опрос / действует ограничение по частоте смены грейда"}})
def start(data: StartIn, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    vacancy = None
    kind = "grade"
    if data.vacancy_id:
        vacancy = db.get(Vacancy, data.vacancy_id)
        if not vacancy or vacancy.status != "published":
            raise not_found("Вакансия")
        kind = "vacancy"
    a = testing.start(db, p, data.target_grade, kind, vacancy)
    return _view(a)


@router.get("/{attempt_id}", summary="Состояние теста и текущее задание (без ключа ответа)")
def get_attempt(attempt_id: int, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    return _view(_own(db, p, attempt_id))


@router.post("/{attempt_id}/answer", summary="Ответить на текущее задание",
             responses={409: {"description": "Тест завершён или ответ не на текущее задание"}})
def answer(attempt_id: int, data: AnswerIn, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    a = _own(db, p, attempt_id)
    testing.answer(db, a, data.item_id, data.value)
    db.refresh(a)
    return _view(a)


@router.post("/{attempt_id}/abandon", summary="Завершить тест досрочно (оставшееся засчитывается как неверное)")
def abandon(attempt_id: int, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    a = _own(db, p, attempt_id)
    testing.abandon(db, a)
    return _view(a)


@router.post("/{attempt_id}/accept-lower", summary="Принять грейд ниже по результату теста",
             responses={409: {"description": "Результат не позволяет принять грейд ниже без отдельного теста"}})
def accept_lower(attempt_id: int, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    a = _own(db, p, attempt_id)
    g = testing.accept_lower(db, p, a)
    return {"grade": g, "attempt": _view(a)}


@router.get("", summary="История тестов кандидата")
def history(p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    rows = db.scalars(select(TestAttempt).where(TestAttempt.candidate_id == p.id).order_by(TestAttempt.id.desc())).all()
    return [testing.attempt_public(a) for a in rows]


_ = ServiceError
