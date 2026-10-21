"""Приглашения — основная механика контакта: работодатель сам выходит на кандидата с предложением и вилкой."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, current_user
from app.api.serializers import invitation_view
from app.core.db import get_db
from app.core.errors import ServiceError, forbidden, not_found
from app.core.security import utcnow
from app.models import (AuditLog, CandidateProfile, Company, Invitation, InvitationMessage, Need, StatusEvent, User,
                        Vacancy)
from app.services import mailer
from app.services.matching import ranker
from app.services.matching import service as matching
from app.taxonomy import DECLINE_REASON_SLUGS

router = APIRouter(prefix="/invitations", tags=["Приглашения"], responses=AUTH_ERRORS)


class InvitationIn(BaseModel):
    candidate_id: int
    title: str = Field(min_length=3, max_length=200, description="Позиция / суть предложения")
    description: str = Field(min_length=10, max_length=5000, description="Описание предложения: задачи, команда, условия")
    salary_from: int = Field(gt=0, description="Обязательно: нижняя граница, ₽/мес")
    salary_to: int = Field(gt=0, description="Обязательно: верхняя граница, ₽/мес")
    contact_method: str = Field(min_length=3, max_length=300, description="Как связаться: email/телефон/Telegram рекрутера")
    work_format: Literal["office", "hybrid", "remote"] | None = None
    need_id: int | None = None
    vacancy_id: int | None = None

    @model_validator(mode="after")
    def check(self):
        if self.salary_from > self.salary_to:
            raise ValueError("Нижняя граница вилки больше верхней")
        return self


class MessageIn(BaseModel):
    text: str = Field(min_length=2, max_length=2000, description="Вопрос или ответ по приглашению")


class DeclineIn(BaseModel):
    reason: str = Field(description="Код причины из справочника decline_reasons")
    comment: str | None = Field(None, max_length=2000)


def _event(db: Session, inv: Invitation, status: str, role: str) -> None:
    db.add(StatusEvent(entity="invitation", entity_id=inv.id, status=status, actor_role=role))


@router.post("", status_code=201, summary="Отправить приглашение кандидату (работодатель)",
             responses={409: {"description": "Активное приглашение этому кандидату уже есть"},
                        422: {"description": "Не заполнена вилка/контакт или профиль компании"}})
def create(data: InvitationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "employer":
        raise forbidden()
    comp: Company = user.company
    if not comp or not comp.name:
        raise ServiceError(422, "company_required", "Заполните название компании в профиле — оно указывается в приглашении")
    cand = db.get(CandidateProfile, data.candidate_id)
    if not cand or not matching.is_visible(db, cand):
        raise not_found("Кандидат")
    dup = db.scalars(select(Invitation).where(Invitation.company_id == comp.id, Invitation.candidate_id == cand.id,
                                              Invitation.status.in_(("sent", "viewed")))).first()
    if dup:
        raise ServiceError(409, "duplicate", "Этому кандидату уже отправлено приглашение, ожидается ответ")
    req_src = None
    if data.need_id:
        req_src = db.get(Need, data.need_id)
        if not req_src or req_src.company_id != comp.id:
            raise not_found("Потребность")
    if data.vacancy_id:
        v = db.get(Vacancy, data.vacancy_id)
        if not v or v.company_id != comp.id:
            raise not_found("Вакансия")
        req_src = req_src or v
    if req_src is not None:
        req = ranker.Requirement.from_obj(req_src)
    else:
        req = ranker.Requirement(specialization=cand.specialization, grades=[cand.grade],
                                 salary_from=data.salary_from, salary_to=data.salary_to)
    req.salary_from, req.salary_to = data.salary_from, data.salary_to
    w = matching.active_weights(db)
    f, d = ranker.features(req, cand)
    snap = {"score": ranker.score(f, w), "features": f, "explanation": ranker.explain(req, cand, f, d, w)}
    inv = Invitation(company_id=comp.id, candidate_id=cand.id, need_id=data.need_id, vacancy_id=data.vacancy_id,
                     title=data.title, description=data.description, salary_from=data.salary_from,
                     salary_to=data.salary_to, contact_method=data.contact_method, work_format=data.work_format,
                     match_snapshot=snap)
    db.add(inv)
    db.flush()
    _event(db, inv, "sent", "employer")
    mailer.send(db, cand.contact_email or cand.user.email, f"Приглашение от {comp.name}: {data.title}",
                f"{comp.name} приглашает вас: {data.title}. Вилка {data.salary_from:,}–{data.salary_to:,} ₽. "
                f"Ответьте в личном кабинете.".replace(",", " "))
    db.commit()
    return invitation_view(inv, "employer", db)


@router.get("", summary="Мои приглашения: входящие (кандидат) или отправленные (работодатель)")
def list_invitations(status: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Invitation)
    if user.role == "candidate":
        if not user.candidate:
            return []
        q = q.where(Invitation.candidate_id == user.candidate.id)
    elif user.role == "employer":
        if not user.company:
            return []
        q = q.where(Invitation.company_id == user.company.id)
    else:
        raise forbidden()
    if status:
        q = q.where(Invitation.status == status)
    rows = db.scalars(q.order_by(Invitation.id.desc())).all()
    return [invitation_view(i, user.role, db) for i in rows]


def _get(db: Session, user: User, inv_id: int) -> Invitation:
    inv = db.get(Invitation, inv_id)
    if not inv:
        raise not_found("Приглашение")
    if user.role == "candidate" and (not user.candidate or inv.candidate_id != user.candidate.id):
        raise not_found("Приглашение")  # чужие приглашения недоступны и не раскрывают факт существования
    if user.role == "employer" and (not user.company or inv.company_id != user.company.id):
        raise not_found("Приглашение")
    if user.role not in ("candidate", "employer"):
        raise forbidden()
    return inv


@router.get("/{inv_id}", summary="Приглашение. Первое открытие кандидатом переводит статус в «просмотрено»")
def get_invitation(inv_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _get(db, user, inv_id)
    if user.role == "candidate" and inv.status == "sent":
        inv.status, inv.viewed_at = "viewed", utcnow()
        _event(db, inv, "viewed", "candidate")
        db.commit()
    d = invitation_view(inv, user.role, db)
    d["messages"] = _messages(db, inv)
    if user.role == "candidate" and inv.candidate.specialization and inv.candidate.grade:
        d["salary_context"]["category_median"] = matching._salary_median(db, inv.candidate.specialization,
                                                                         inv.candidate.grade)
    d["history"] = [{"status": e.status, "at": e.created_at, "by": e.actor_role} for e in db.scalars(
        select(StatusEvent).where(StatusEvent.entity == "invitation", StatusEvent.entity_id == inv.id).order_by(StatusEvent.id))]
    return d


def _messages(db: Session, inv: Invitation) -> list[dict]:
    return [{"id": m.id, "author_role": m.author_role, "text": m.text, "created_at": m.created_at}
            for m in db.scalars(select(InvitationMessage).where(InvitationMessage.invitation_id == inv.id)
                                .order_by(InvitationMessage.id))]


@router.get("/{inv_id}/messages", summary="Вопросы и ответы по приглашению (обе стороны)")
def list_messages(inv_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _messages(db, _get(db, user, inv_id))


@router.post("/{inv_id}/messages", status_code=201, summary="Задать вопрос или ответить до раскрытия контактов",
             description="Кандидат уточняет условия (формат, стек, вилку), не открывая контактов: работодатель видит "
                         "вопрос от «Иван И.», а контакты — только после принятия приглашения. Работает, пока "
                         "приглашение не отклонено и не отозвано.",
             responses={409: {"description": "Приглашение отклонено или отозвано"}})
def post_message(inv_id: int, data: MessageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _get(db, user, inv_id)
    if inv.status in ("declined", "withdrawn"):
        raise ServiceError(409, "bad_status", "Приглашение закрыто — переписка недоступна")
    if user.role == "candidate" and inv.status == "sent":
        inv.status, inv.viewed_at = "viewed", utcnow()
        _event(db, inv, "viewed", "candidate")
    db.add(InvitationMessage(invitation_id=inv.id, author_role=user.role, text=data.text.strip()))
    if user.role == "candidate":
        mailer.send(db, inv.company.contact_email or inv.company.owner.email, f"Вопрос по приглашению: {inv.title}",
                    "Кандидат задал вопрос по приглашению. Ответьте в личном кабинете — контакты кандидата откроются, "
                    "когда он примет приглашение.")
    else:
        mailer.send(db, inv.candidate.contact_email or inv.candidate.user.email, f"Ответ компании {inv.company.name}",
                    f"Компания ответила на ваш вопрос по приглашению «{inv.title}». Ответ — в личном кабинете.")
    db.commit()
    return _messages(db, inv)


@router.post("/{inv_id}/accept", summary="Принять приглашение (кандидат) — контакты раскрываются работодателю")
def accept(inv_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _get(db, user, inv_id)
    if user.role != "candidate":
        raise forbidden()
    if inv.status not in ("sent", "viewed"):
        raise ServiceError(409, "bad_status", "Приглашение уже обработано")
    inv.status, inv.responded_at = "accepted", utcnow()
    inv.viewed_at = inv.viewed_at or utcnow()
    _event(db, inv, "accepted", "candidate")
    db.add(AuditLog(actor_user_id=user.id, action="contacts_revealed", target_type="company", target_id=inv.company_id,
                    meta={"invitation_id": inv.id}))
    cand = inv.candidate
    cand.last_activity_at = utcnow()
    mailer.send(db, inv.company.contact_email or inv.company.owner.email, f"Кандидат принял приглашение: {inv.title}",
                "Контакты кандидата открыты в карточке приглашения.")
    db.commit()
    return invitation_view(inv, "candidate", db)


@router.post("/{inv_id}/decline", summary="Отклонить приглашение с причиной (кандидат)",
             description="Причина обязательна: из причин строится обратная связь работодателю и дообучение ранжирования.")
def decline(inv_id: int, data: DeclineIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _get(db, user, inv_id)
    if user.role != "candidate":
        raise forbidden()
    if inv.status not in ("sent", "viewed"):
        raise ServiceError(409, "bad_status", "Приглашение уже обработано")
    if data.reason not in DECLINE_REASON_SLUGS:
        raise ServiceError(422, "bad_reason", "Неизвестная причина отказа")
    inv.status, inv.responded_at, inv.decline_reason, inv.decline_comment = "declined", utcnow(), data.reason, data.comment
    inv.viewed_at = inv.viewed_at or utcnow()
    _event(db, inv, "declined", "candidate")
    db.commit()
    return invitation_view(inv, "candidate", db)


@router.post("/{inv_id}/withdraw", summary="Отозвать приглашение (работодатель)")
def withdraw(inv_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _get(db, user, inv_id)
    if user.role != "employer":
        raise forbidden()
    if inv.status not in ("sent", "viewed"):
        raise ServiceError(409, "bad_status", "Отозвать можно только приглашение без ответа")
    inv.status = "withdrawn"
    _event(db, inv, "withdrawn", "employer")
    db.commit()
    return invitation_view(inv, "employer", db)
