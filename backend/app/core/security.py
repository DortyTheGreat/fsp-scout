"""Пароли (Argon2id), JWT-токены доступа и одноразовые токены подтверждения почты."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()  # Argon2id с параметрами по умолчанию (OWASP-совместимые)
ALGO = "HS256"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGO)


def decode_access_token(token: str) -> dict | None:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
        return data if data.get("typ") == "access" else None
    except jwt.PyJWTError:
        return None


def new_opaque_token() -> tuple[str, str]:
    """Возвращает (токен для письма, его SHA-256 для хранения в БД). В БД сам токен не хранится."""
    raw = secrets.token_urlsafe(32)
    return raw, sha256(raw)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
