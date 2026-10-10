"""Привязка ФСП ID к профилю кандидата и обновление достижений."""
from datetime import timedelta

import jwt
from fastapi import APIRouter, Cookie, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, candidate_profile
from app.api.serializers import fsp_view
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ServiceError
from app.core.security import utcnow
from app.models import AuditLog, CandidateProfile, Consent
from app.services.fsp.client import FspError, get_fsp_client
from app.services.fsp.service import load_into_profile

router = APIRouter(prefix="/fsp", tags=["Интеграция с ФСП"], responses=AUTH_ERRORS)
STATE_COOKIE = "fsp_link_state"


def _callback_url() -> str:
    return f"{settings.public_api_url.rstrip('/')}/api/v1/fsp/link/callback"


@router.get("/link/start", summary="Начать привязку: редирект на страницу входа ФСП ID (OIDC + PKCE)",
            response_class=RedirectResponse, status_code=302)
def link_start(p: CandidateProfile = Depends(candidate_profile)):
    client = get_fsp_client()
    verifier, challenge = client.new_pkce()
    state = jwt.encode({"cid": p.id, "v": verifier, "exp": utcnow() + timedelta(minutes=10)}, settings.secret_key,
                       algorithm="HS256")
    url = client.authorize_url(_callback_url(), state[-32:], challenge)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(STATE_COOKIE, state, httponly=True, samesite="lax", max_age=600, secure=settings.cookie_secure, path="/")
    return resp


@router.get("/link/callback", summary="Возврат от ФСП ID: обмен кода, загрузка и проверка достижений",
            response_class=RedirectResponse, status_code=302)
def link_callback(code: str, state: str, p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db),
                  fsp_link_state: str | None = Cookie(None)):
    back = f"{settings.public_web_url}/candidate/settings"
    try:
        st = jwt.decode(fsp_link_state or "", settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return RedirectResponse(f"{back}?fsp=error&reason=state", status_code=302)
    if st.get("cid") != p.id or not (fsp_link_state or "").endswith(state):
        return RedirectResponse(f"{back}?fsp=error&reason=state", status_code=302)
    client = get_fsp_client()
    try:
        claims = client.exchange_code(code, _callback_url(), st["v"])
        _load(db, p, claims["fsp_id"])
    except FspError as e:
        return RedirectResponse(f"{back}?fsp=error&reason={str(e)[:60]}", status_code=302)
    resp = RedirectResponse(f"{back}?fsp=linked", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


def _load(db: Session, p: CandidateProfile, fsp_id: str) -> None:
    load_into_profile(db, p, fsp_id)
    db.commit()


@router.post("/refresh", summary="Перечитать достижения из реестра ФСП")
def refresh(p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    if not p.fsp_id:
        raise ServiceError(409, "not_linked", "ФСП ID не привязан")
    try:
        _load(db, p, p.fsp_id)
    except FspError as e:
        raise ServiceError(502, "fsp_unavailable", str(e))
    return fsp_view(p)


@router.delete("/link", summary="Отвязать ФСП ID и удалить полученные данные")
def unlink(p: CandidateProfile = Depends(candidate_profile), db: Session = Depends(get_db)):
    p.fsp_id, p.fsp_linked_at, p.fsp_data, p.fsp_score = None, None, {}, 0.0
    db.add(Consent(user_id=p.user_id, kind="fsp_data", granted=False))
    db.commit()
    return fsp_view(p)


@router.get("/me", summary="Достижения ФСП в профиле")
def me(p: CandidateProfile = Depends(candidate_profile)):
    return fsp_view(p)
