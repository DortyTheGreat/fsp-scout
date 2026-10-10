"""Мок-сервис ФСП: ФСП ID (OIDC-провайдер с URL-схемой Keycloak) + API реестра достижений.

Замена на боевую систему = смена базового URL и realm в настройках платформы:
  /realms/{realm}/.well-known/openid-configuration
  /realms/{realm}/protocol/openid-connect/{auth,token,userinfo,certs}
Каждое достижение отдаётся с подписью (JWS RS256) — платформа проверяет её по JWKS и показывает
работодателю отметку «подтверждено ФСП».
"""
import base64
import hashlib
import html
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from data import DISCIPLINES, EVENT_BY_ID, EVENTS, LEVELS, PARTICIPANT_BY_ID, PARTICIPANTS

REALM = os.getenv("FSP_REALM", "fsp")
PUBLIC_URL = os.getenv("FSP_PUBLIC_URL", "http://localhost:8001").rstrip("/")
ISSUER = f"{PUBLIC_URL}/realms/{REALM}"
CLIENTS = {os.getenv("FSP_CLIENT_ID", "scout"): os.getenv("FSP_CLIENT_SECRET", "scout-secret")}
ALLOWED_REDIRECT_PREFIXES = os.getenv("FSP_ALLOWED_REDIRECTS", "http://localhost").split(",")
DEMO_PASSWORD = "demo"

_key_path = Path(__file__).with_name("dev_signing_key.pem")  # ключ ТОЛЬКО для разработки
PRIVATE_KEY = serialization.load_pem_private_key(_key_path.read_bytes(), password=None)
PUBLIC_KEY = PRIVATE_KEY.public_key()
KID = "fsp-dev-key-1"


def _b64u(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


_nums = PUBLIC_KEY.public_numbers()
JWKS = {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": KID, "n": _b64u(_nums.n), "e": _b64u(_nums.e)}]}

app = FastAPI(title="ФСП (мок): ФСП ID и реестр достижений", version="0.1.0",
              description="Эмуляция будущего API ФСП для хакатона. URL-схема OIDC совпадает с Keycloak.")

_codes: dict[str, dict] = {}   # код авторизации → данные (живёт 120 с)


def _sign(payload: dict, ttl: int | None = 300) -> str:
    now = int(time.time())
    body = {"iss": ISSUER, "iat": now, **payload}
    if ttl:
        body["exp"] = now + ttl
    return jwt.encode(body, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})


def _check_bearer(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Нужен Bearer-токен")
    try:
        return jwt.decode(authorization[7:], PUBLIC_KEY, algorithms=["RS256"], options={"verify_aud": False},
                          issuer=ISSUER)
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Неверный токен: {e}")


# ------------------------------------------------------------------ OIDC (как в Keycloak)
@app.get(f"/realms/{REALM}/.well-known/openid-configuration")
def discovery():
    base = f"{ISSUER}/protocol/openid-connect"
    return {"issuer": ISSUER, "authorization_endpoint": f"{base}/auth", "token_endpoint": f"{base}/token",
            "userinfo_endpoint": f"{base}/userinfo", "jwks_uri": f"{base}/certs",
            "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "client_credentials"],
            "code_challenge_methods_supported": ["S256"], "id_token_signing_alg_values_supported": ["RS256"],
            "scopes_supported": ["openid", "profile", "email", "fsp_achievements"]}


@app.get(f"/realms/{REALM}/protocol/openid-connect/certs")
def certs():
    return JWKS


@app.get(f"/realms/{REALM}/protocol/openid-connect/auth", response_class=HTMLResponse)
def auth_page(client_id: str, redirect_uri: str, state: str = "", response_type: str = "code", scope: str = "openid",
              code_challenge: str = "", code_challenge_method: str = "S256", error: str = ""):
    if client_id not in CLIENTS:
        raise HTTPException(400, "unknown client_id")
    if not any(redirect_uri.startswith(p) for p in ALLOWED_REDIRECT_PREFIXES):
        raise HTTPException(400, "redirect_uri не разрешён")
    hidden = "".join(f'<input type="hidden" name="{k}" value="{html.escape(v)}">' for k, v in
                     {"client_id": client_id, "redirect_uri": redirect_uri, "state": state,
                      "code_challenge": code_challenge, "scope": scope}.items())
    demo = "".join(f"<li><code>{p['fsp_id']}</code> — {html.escape(p['full_name'])}"
                   f" ({len(p['results'])} результатов)</li>" for p in [PARTICIPANT_BY_ID['FSP-000777'],
                                                                        PARTICIPANT_BY_ID['FSP-000778']] + PARTICIPANTS[:3])
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Вход — ФСП ID</title><style>
body{{font-family:Montserrat,system-ui,sans-serif;background:#2D1451;color:#fff;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#fff;color:#1C1D22;border-radius:16px;padding:32px;max-width:420px;width:calc(100% - 32px);box-shadow:0 10px 40px #0005}}
h1{{margin:0 0 4px;font-size:22px}} .sub{{color:#5b6b8c;margin:0 0 20px;font-size:14px}}
label{{display:block;font-size:13px;margin:12px 0 4px;color:#33415c}}
input[type=text],input[type=password]{{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #c9d2e3;border-radius:8px;font-size:15px}}
button{{margin-top:18px;width:100%;padding:12px;border:0;border-radius:8px;background:#FF0053;color:#fff;font-size:15px;cursor:pointer}}
.hint{{font-size:12px;color:#5b6b8c;margin-top:18px}} .err{{color:#FF0053}} code{{background:#eef2f9;padding:1px 4px;border-radius:4px}}
</style></head><body><form class="card" method="post" action="/realms/{REALM}/login-actions/authenticate">
<h1>ФСП ID</h1><p class="sub">Вход в единый аккаунт участника Федерации спортивного программирования (демо)</p>{err}
{hidden}<label>ФСП ID или email</label><input type="text" name="username" required autofocus value="FSP-000777">
<label>Пароль</label><input type="password" name="password" required value="demo">
<button type="submit">Войти и разрешить доступ к достижениям</button>
<div class="hint">Демо-режим: пароль для всех — <code>demo</code>. Примеры:<ul>{demo}</ul></div></form></body></html>"""


@app.post(f"/realms/{REALM}/login-actions/authenticate")
def authenticate(username: str = Form(...), password: str = Form(...), client_id: str = Form(...),
                 redirect_uri: str = Form(...), state: str = Form(""), code_challenge: str = Form(""),
                 scope: str = Form("openid")):
    person = PARTICIPANT_BY_ID.get(username.strip().upper()) or next(
        (p for p in PARTICIPANTS if p["email"] == username.strip().lower()), None)
    if not person or password != DEMO_PASSWORD:
        q = urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "state": state,
                       "code_challenge": code_challenge, "error": "Неверный ФСП ID или пароль"})
        return RedirectResponse(f"/realms/{REALM}/protocol/openid-connect/auth?{q}", status_code=303)
    code = secrets.token_urlsafe(24)
    _codes[code] = {"fsp_id": person["fsp_id"], "client_id": client_id, "redirect_uri": redirect_uri,
                    "code_challenge": code_challenge, "exp": time.time() + 120, "scope": scope}
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode({'code': code, 'state': state})}", status_code=303)


@app.post(f"/realms/{REALM}/protocol/openid-connect/token")
async def token(request: Request):
    form = await request.form()
    client_id, client_secret = form.get("client_id"), form.get("client_secret")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        client_id, client_secret = base64.b64decode(auth[6:]).decode().split(":", 1)
    if CLIENTS.get(client_id) != client_secret:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    gt = form.get("grant_type")
    if gt == "client_credentials":
        at = _sign({"sub": f"service-account-{client_id}", "azp": client_id, "scope": "fsp_registry:read",
                    "typ": "Bearer"})
        return {"access_token": at, "token_type": "Bearer", "expires_in": 300}
    if gt != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    data = _codes.pop(form.get("code", ""), None)
    if not data or data["exp"] < time.time() or data["client_id"] != client_id \
            or data["redirect_uri"] != form.get("redirect_uri"):
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    if data["code_challenge"]:  # PKCE S256
        verifier = form.get("code_verifier", "")
        digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if digest != data["code_challenge"]:
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE"}, status_code=400)
    p = PARTICIPANT_BY_ID[data["fsp_id"]]
    claims = {"sub": p["fsp_id"], "fsp_id": p["fsp_id"], "name": p["full_name"], "email": p["email"],
              "preferred_username": p["fsp_id"].lower(), "azp": client_id}
    return {"access_token": _sign({**claims, "typ": "Bearer", "scope": data["scope"]}),
            "id_token": _sign({**claims, "aud": client_id, "typ": "ID"}), "token_type": "Bearer", "expires_in": 300}


@app.get(f"/realms/{REALM}/protocol/openid-connect/userinfo")
def userinfo(authorization: str | None = Header(None)):
    c = _check_bearer(authorization)
    return {k: c[k] for k in ("sub", "fsp_id", "name", "email", "preferred_username") if k in c}


# ------------------------------------------------------------------ API реестра
def _achievement(person: dict, r: dict) -> dict:
    ev = EVENT_BY_ID[r["event_id"]]
    a = {"id": f"{person['fsp_id']}-{ev['id']}", "fsp_id": person["fsp_id"], "event_id": ev["id"],
         "event_name": ev["name"], "discipline": ev["discipline"], "discipline_name": ev["discipline_name"],
         "level": ev["level"], "level_name": ev["level_name"], "format": ev["format"], "date": r["date"],
         "place": r["place"], "participants_total": r["participants_total"], "score": r.get("score"),
         "is_prize": r["place"] <= 3, "team_name": r.get("team_name"), "role": r.get("role"),
         "stack": r.get("stack", []), "tasks_solved": r.get("tasks_solved"), "tasks_total": r.get("tasks_total"),
         "protocol_url": f"{PUBLIC_URL}/protocols/{ev['id']}"}
    # подпись без срока действия: достижение — факт; отзыв — через список отозванных (в боевой версии)
    a["proof"] = _sign({"sub": person["fsp_id"], "ach": hashlib.sha256(
        json.dumps({k: a[k] for k in ("id", "event_id", "place", "participants_total", "date")},
                   sort_keys=True).encode()).hexdigest()}, ttl=None)
    return a


@app.get("/api/v1/participants/{fsp_id}", tags=["registry"])
def participant(fsp_id: str, authorization: str | None = Header(None)):
    _check_bearer(authorization)
    p = PARTICIPANT_BY_ID.get(fsp_id.upper())
    if not p:
        raise HTTPException(404, "Участник не найден")
    return {k: p[k] for k in ("fsp_id", "full_name", "birth_year", "region", "sport_rank")} | {
        "results_count": len(p["results"])}


@app.get("/api/v1/participants/{fsp_id}/achievements", tags=["registry"])
def achievements(fsp_id: str, authorization: str | None = Header(None)):
    _check_bearer(authorization)
    p = PARTICIPANT_BY_ID.get(fsp_id.upper())
    if not p:
        raise HTTPException(404, "Участник не найден")
    return {"fsp_id": p["fsp_id"], "sport_rank": p["sport_rank"],
            "items": [_achievement(p, r) for r in p["results"]]}


@app.get("/api/v1/events", tags=["registry"])
def events(discipline: str | None = Query(None), level: str | None = Query(None)):
    return [e for e in EVENTS if (not discipline or e["discipline"] == discipline) and (not level or e["level"] == level)]


@app.get("/api/v1/dictionaries", tags=["registry"])
def dictionaries():
    return {"disciplines": DISCIPLINES, "levels": LEVELS}


@app.get("/protocols/{event_id}", response_class=HTMLResponse, tags=["public"])
def protocol(event_id: int):
    ev = EVENT_BY_ID.get(event_id)
    if not ev:
        raise HTTPException(404)
    rows = sorted(((r["place"], p) for p in PARTICIPANTS for r in p["results"] if r["event_id"] == event_id),
                  key=lambda x: x[0])
    tr = "".join(f"<tr><td>{pl}</td><td>{html.escape(p['full_name'])}</td><td><code>{p['fsp_id']}</code></td></tr>"
                 for pl, p in rows)
    return (f"<!doctype html><meta charset=utf-8><title>Протокол</title><body style='font-family:system-ui;max-width:800px;margin:40px auto;padding:0 16px'>"
            f"<h2>{html.escape(ev['name'])}</h2><p>{ev['date']} · {ev['level_name']} · участников: {ev['participants_total']}</p>"
            f"<table border=1 cellpadding=6 style='border-collapse:collapse'><tr><th>Место</th><th>Участник</th><th>ФСП ID</th></tr>{tr}</table>")


@app.get("/health")
def health():
    return {"status": "ok", "participants": len(PARTICIPANTS), "events": len(EVENTS)}
