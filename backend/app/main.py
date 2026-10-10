"""Точка входа API «ФСП Скаут»."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, candidate, employer, fsp, invitations, public, tasks, tests, vacancies
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.services.testing.service import sync_templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DESCRIPTION = """
Платформа подбора ИТ-специалистов с **обратной механикой**: кандидаты распределяются по категориям
(специализация × грейд) по результатам адаптивного тестирования, а работодатель сам находит категорию
и выходит на конкретного человека с предложением и зарплатной вилкой.

**Аутентификация:** `POST /api/v1/auth/login` ставит httpOnly-cookie `scout_session`; для внешних клиентов
тот же токен возвращается в заголовке `X-Access-Token` и принимается как `Authorization: Bearer <token>`.

**Ошибки** возвращаются в формате `{"detail": {"code": "...", "message": "..."}}`; ошибки валидации — 422.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Схема создаётся миграциями Alembic (см. backend/alembic); create_all — страховка для локального запуска/тестов
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_templates(db)
    yield


app = FastAPI(title="ФСП Скаут API", version="0.9.0", description=DESCRIPTION, lifespan=lifespan,
              docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Access-Token"])

API = "/api/v1"
for r in (public.router, public.demo, auth.router, candidate.router, tests.router, fsp.router, employer.router,
          invitations.router, vacancies.router, tasks.router, admin.router):
    app.include_router(r, prefix=API)
