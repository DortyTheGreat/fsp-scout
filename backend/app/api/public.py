"""Публичные справочники и демо-почта."""
from fastapi import APIRouter, Depends
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import taxonomy
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ServiceError
from app.models import OutboxEmail

router = APIRouter(tags=["Справочники"])


@router.get("/dictionaries", summary="Справочник: специализации, грейды, навыки, отрасли, причины отказа")
def dictionaries():
    return taxonomy.as_dict()


@router.get("/health", tags=["Служебное"])
def health():
    return {"status": "ok", "demo_mode": settings.demo_mode, "llm": settings.llm_provider}


demo = APIRouter(prefix="/demo", tags=["Демо-режим"])


@demo.get("/mailbox", summary="Демо-почтовый ящик (только DEMO_MODE): письма на указанный адрес",
          description="Позволяет жюри пройти регистрацию с подтверждением email без реальной почты. "
                      "В боевом режиме выключен, письма уходят через SMTP.")
def mailbox(email: EmailStr, db: Session = Depends(get_db)):
    if not settings.demo_mode:
        raise ServiceError(404, "not_found", "Недоступно")
    rows = db.scalars(select(OutboxEmail).where(OutboxEmail.to == email.lower()).order_by(OutboxEmail.id.desc()).limit(20))
    return [{"subject": m.subject, "body": m.body, "link": m.link, "at": m.created_at} for m in rows]


@demo.get("/accounts", summary="Демо-аккаунты для проверки")
def accounts():
    if not settings.demo_mode:
        raise ServiceError(404, "not_found", "Недоступно")
    return [
        {"role": "candidate", "email": "candidate@demo.ru", "password": "demo12345", "note": "Кандидат без категории — пройдите опрос и тест"},
        {"role": "candidate", "email": "senior@demo.ru", "password": "demo12345", "note": "Senior-бэкендер с достижениями ФСП и приглашениями"},
        {"role": "employer", "email": "employer@demo.ru", "password": "demo12345", "note": "Работодатель с потребностями, вакансиями и заданиями"},
        {"role": "admin", "email": "admin@demo.ru", "password": "demo12345", "note": "Админ: банк заданий, калибровка, модель ранжирования"},
    ]
