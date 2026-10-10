"""Клиент ФСП: вход через ФСП ID (OIDC Authorization Code + PKCE) и чтение реестра достижений
(client credentials). Совместим с Keycloak: используются только стандартные эндпоинты realm."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings


class FspError(Exception):
    pass


class FspClient:
    def __init__(self, http: httpx.Client | None = None):
        self.realm_path = f"/realms/{settings.fsp_realm}"
        self.issuer = f"{settings.fsp_public_url.rstrip('/')}{self.realm_path}"
        self.http = http or httpx.Client(base_url=settings.fsp_internal_url, timeout=10.0)
        self._jwks: jwt.PyJWKSet | None = None
        self._svc_token: tuple[str, float] | None = None

    # ---------------------------------------------------------------- OIDC
    @staticmethod
    def new_pkce() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return verifier, challenge

    def authorize_url(self, redirect_uri: str, state: str, challenge: str) -> str:
        q = urlencode({"client_id": settings.fsp_client_id, "response_type": "code", "scope": "openid profile fsp_achievements",
                       "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge,
                       "code_challenge_method": "S256"})
        return f"{self.issuer}/protocol/openid-connect/auth?{q}"

    def _jwk_set(self, refresh: bool = False) -> jwt.PyJWKSet:
        if self._jwks is None or refresh:
            r = self.http.get(f"{self.realm_path}/protocol/openid-connect/certs")
            r.raise_for_status()
            self._jwks = jwt.PyJWKSet.from_dict(r.json())
        return self._jwks

    def _verify_jwt(self, token: str, audience: str | None = None) -> dict:
        kid = jwt.get_unverified_header(token).get("kid")
        for attempt in (False, True):  # при ротации ключей — один повторный запрос JWKS
            keys = [k for k in self._jwk_set(refresh=attempt).keys if k.key_id == kid]
            if keys:
                opts = {"verify_aud": audience is not None}
                return jwt.decode(token, keys[0].key, algorithms=["RS256"], issuer=self.issuer, audience=audience,
                                  options=opts)
        raise FspError("Неизвестный ключ подписи ФСП")

    def exchange_code(self, code: str, redirect_uri: str, verifier: str) -> dict:
        r = self.http.post(f"{self.realm_path}/protocol/openid-connect/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "client_id": settings.fsp_client_id, "client_secret": settings.fsp_client_secret, "code_verifier": verifier})
        if r.status_code != 200:
            raise FspError(f"Обмен кода не удался: {r.text[:200]}")
        claims = self._verify_jwt(r.json()["id_token"], audience=settings.fsp_client_id)
        if not claims.get("fsp_id"):
            raise FspError("В токене нет fsp_id")
        return claims

    # ---------------------------------------------------------------- реестр
    def _service_token(self) -> str:
        if self._svc_token and self._svc_token[1] > time.time() + 10:
            return self._svc_token[0]
        r = self.http.post(f"{self.realm_path}/protocol/openid-connect/token", data={
            "grant_type": "client_credentials", "client_id": settings.fsp_client_id,
            "client_secret": settings.fsp_client_secret})
        r.raise_for_status()
        d = r.json()
        self._svc_token = (d["access_token"], time.time() + d.get("expires_in", 60))
        return d["access_token"]

    def get_achievements(self, fsp_id: str) -> dict:
        h = {"Authorization": f"Bearer {self._service_token()}"}
        p = self.http.get(f"/api/v1/participants/{fsp_id}", headers=h)
        if p.status_code == 404:
            raise FspError("Участник ФСП не найден")
        p.raise_for_status()
        a = self.http.get(f"/api/v1/participants/{fsp_id}/achievements", headers=h)
        a.raise_for_status()
        items = a.json().get("items", [])
        for it in items:
            it["verified"] = self.verify_proof(it)
        return {"participant": p.json(), "items": items}

    def verify_proof(self, item: dict) -> bool:
        """Подпись ФСП над ключевыми полями достижения: защита от подмены данных в кэше или при передаче."""
        try:
            claims = self._verify_jwt(item["proof"])
        except Exception:
            return False
        digest = hashlib.sha256(json.dumps({k: item[k] for k in ("id", "event_id", "place", "participants_total", "date")},
                                           sort_keys=True).encode()).hexdigest()
        return claims.get("sub") == item.get("fsp_id") and claims.get("ach") == digest


_client: FspClient | None = None


def get_fsp_client() -> FspClient:
    global _client
    if _client is None:
        _client = FspClient()
    return _client


def set_fsp_client(client: FspClient | None) -> None:
    """Для тестов: подмена HTTP-транспорта на in-process мок."""
    global _client
    _client = client
