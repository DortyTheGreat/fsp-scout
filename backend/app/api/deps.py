"""Аутентификация и разграничение прав по ролям."""
from fastapi import Cookie, Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ServiceError
from app.core.security import decode_access_token
from app.models import CandidateProfile, Company, User

COOKIE = "scout_session"

AUTH_ERRORS = {401: {"description": "Не аутентифицирован"}, 403: {"description": "Недостаточно прав для роли"}}


def current_user(db: Session = Depends(get_db), scout_session: str | None = Cookie(None),
                 authorization: str | None = Header(None)) -> User:
    """Токен берётся из httpOnly-cookie (веб) или заголовка Authorization: Bearer (API-клиенты, Swagger)."""
    token = scout_session
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    data = decode_access_token(token) if token else None
    if not data:
        raise ServiceError(401, "unauthorized", "Требуется вход")
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise ServiceError(401, "unauthorized", "Пользователь не найден или заблокирован")
    return user


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise ServiceError(403, "forbidden", "Действие недоступно для вашей роли")
        return user
    return dep


def candidate_profile(user: User = Depends(require("candidate")), db: Session = Depends(get_db)) -> CandidateProfile:
    prof = user.candidate
    if prof is None:
        prof = CandidateProfile(user_id=user.id, contact_email=user.email)
        db.add(prof)
        db.commit()
        db.refresh(prof)
    return prof


def employer_company(user: User = Depends(require("employer")), db: Session = Depends(get_db)) -> Company:
    comp = user.company
    if comp is None:
        comp = Company(owner_user_id=user.id, contact_email=user.email)
        db.add(comp)
        db.commit()
        db.refresh(comp)
    return comp
