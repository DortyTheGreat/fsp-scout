"""Регистрация по email с подтверждением адреса, вход/выход, согласия на обработку данных (152-ФЗ)."""
import time
from collections import defaultdict
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, COOKIE, current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ServiceError
from app.core.security import create_access_token, hash_password, new_opaque_token, sha256, utcnow, verify_password
from app.models import AuditLog, CandidateProfile, Company, Consent, EmailToken, User
from app.services import mailer

router = APIRouter(prefix="/auth", tags=["Аутентификация"])

CONSENT_TEXTS = {
    "processing": "Согласие на обработку персональных данных (ФИО, контакты, резюме, результаты тестирования) "
                  "в целях подбора работы в соответствии с 152-ФЗ.",
    "publication": "Согласие на публикацию обезличенного профиля (категория, оценки навыков, достижения ФСП) "
                   "для работодателей платформы. Контакты раскрываются только после вашего согласия на приглашение.",
    "fsp_data": "Согласие на получение сведений о моих результатах из реестра ФСП.",
}


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="Не короче 8 символов")
    role: Literal["candidate", "employer"]
    consent_processing: bool = Field(description="Обязательное согласие на обработку ПДн")
    consent_publication: bool = Field(False, description="Для кандидата: согласие на показ профиля работодателям")
    full_name: str | None = Field(None, max_length=200)
    company_name: str | None = Field(None, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_email_verified: bool
    name: str | None = None


class TokenIn(BaseModel):
    token: str


class ConsentIn(BaseModel):
    kind: Literal["processing", "publication", "fsp_data"]
    granted: bool


def _user_out(u: User) -> UserOut:
    name = (u.candidate.full_name if u.candidate else None) or (u.company.name if u.company else None)
    return UserOut(id=u.id, email=u.email, role=u.role, is_email_verified=u.is_email_verified, name=name)


def _issue_verification(db: Session, user: User) -> str:
    raw, h = new_opaque_token()
    db.add(EmailToken(user_id=user.id, token_hash=h, purpose="verify",
                      expires_at=utcnow() + timedelta(hours=settings.email_token_ttl_hours)))
    link = f"{settings.public_web_url}/verify-email?token={raw}"
    mailer.send(db, user.email, "Подтвердите адрес электронной почты — ФСП Скаут",
                "Здравствуйте! Чтобы завершить регистрацию, перейдите по ссылке. Если вы не регистрировались — "
                "просто проигнорируйте письмо.", link)
    return link


@router.post("/register", status_code=201, response_model=UserOut,
             responses={409: {"description": "Email уже зарегистрирован"}, 422: {"description": "Нет согласия на обработку ПДн / невалидные данные"}})
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    """Создаёт аккаунт и отправляет письмо со ссылкой подтверждения. Войти можно только после подтверждения."""
    if not data.consent_processing:
        raise ServiceError(422, "consent_required", "Без согласия на обработку персональных данных регистрация невозможна")
    email = data.email.lower()
    if db.scalars(select(User).where(User.email == email)).first():
        raise ServiceError(409, "email_taken", "Пользователь с таким email уже зарегистрирован")
    user = User(email=email, password_hash=hash_password(data.password), role=data.role)
    db.add(user)
    db.flush()
    ip = request.client.host if request.client else None
    db.add(Consent(user_id=user.id, kind="processing", granted=True, ip=ip))
    if data.role == "candidate":
        db.add(Consent(user_id=user.id, kind="publication", granted=data.consent_publication, ip=ip))
        db.add(CandidateProfile(user_id=user.id, full_name=data.full_name or "", contact_email=email))
    else:
        db.add(Company(owner_user_id=user.id, name=data.company_name or "", contact_email=email))
    _issue_verification(db, user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/verify-email", response_model=UserOut, responses={400: {"description": "Ссылка недействительна или устарела"}})
def verify_email(data: TokenIn, response: Response, db: Session = Depends(get_db)):
    """Подтверждает адрес по токену из письма и сразу выполняет вход."""
    tok = db.scalars(select(EmailToken).where(EmailToken.token_hash == sha256(data.token),
                                              EmailToken.purpose == "verify")).first()
    if not tok or tok.used_at or tok.expires_at < utcnow():
        raise ServiceError(400, "bad_token", "Ссылка недействительна или устарела")
    tok.used_at = utcnow()
    user = db.get(User, tok.user_id)
    user.is_email_verified = True
    db.commit()
    _set_cookie(response, user)
    return _user_out(user)


@router.post("/resend-verification", status_code=202)
def resend(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.email == data.email.lower())).first()
    if user and not user.is_email_verified and verify_password(data.password, user.password_hash):
        _issue_verification(db, user)
        db.commit()
    return {"status": "accepted"}


_attempts: dict[str, list[float]] = defaultdict(list)


def _rate_limit(key: str, limit: int = 10, window: float = 300) -> None:
    now = time.time()
    _attempts[key] = [t for t in _attempts[key] if now - t < window]
    if len(_attempts[key]) >= limit:
        raise ServiceError(429, "too_many_attempts", "Слишком много попыток входа, попробуйте через несколько минут")
    _attempts[key].append(now)


def _set_cookie(response: Response, user: User) -> str:
    token = create_access_token(user.id, user.role)
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="lax",
                        max_age=settings.access_token_ttl_minutes * 60, path="/")
    return token


@router.post("/login", response_model=UserOut,
             responses={401: {"description": "Неверный email или пароль"}, 403: {"description": "Email не подтверждён"},
                        429: {"description": "Слишком много попыток"}})
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Вход. Токен выдаётся в httpOnly-cookie (недоступен JS) и дублируется в заголовке X-Access-Token для API-клиентов."""
    _rate_limit(f"{request.client.host if request.client else ''}:{data.email.lower()}")
    user = db.scalars(select(User).where(User.email == data.email.lower())).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise ServiceError(401, "bad_credentials", "Неверный email или пароль")
    if not user.is_email_verified:
        raise ServiceError(403, "email_not_verified", "Подтвердите email: ссылка отправлена в письме")
    token = _set_cookie(response, user)
    response.headers["X-Access-Token"] = token
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")


@router.get("/me", response_model=UserOut, responses=AUTH_ERRORS)
def me(user: User = Depends(current_user)):
    return _user_out(user)


@router.get("/consents", responses=AUTH_ERRORS)
def consents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Текущее состояние согласий и история их изменений."""
    rows = db.scalars(select(Consent).where(Consent.user_id == user.id).order_by(Consent.id)).all()
    current = {}
    for r in rows:
        current[r.kind] = r.granted
    return {"current": current, "texts": CONSENT_TEXTS,
            "history": [{"kind": r.kind, "granted": r.granted, "version": r.version, "at": r.created_at} for r in rows]}


@router.post("/consents", responses=AUTH_ERRORS)
def set_consent(data: ConsentIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Изменение согласия. Отзыв согласия на публикацию сразу скрывает профиль из выдачи работодателей."""
    db.add(Consent(user_id=user.id, kind=data.kind, granted=data.granted, ip=request.client.host if request.client else None))
    db.add(AuditLog(actor_user_id=user.id, action="consent", meta={"kind": data.kind, "granted": data.granted}))
    db.commit()
    return consents(user, db)


@router.delete("/me", status_code=204, responses=AUTH_ERRORS)
def delete_account(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Удаление аккаунта и всех связанных персональных данных (право субъекта ПДн, ст. 21 152-ФЗ)."""
    db.add(AuditLog(actor_user_id=None, action="account_deleted", target_type="user", target_id=user.id))
    db.delete(user)
    db.commit()
    response.delete_cookie(COOKIE, path="/")
