#!/bin/sh
set -e
# 1) схема БД через миграции
alembic upgrade head
# 2) демо-данные при первом запуске (SEED_ON_START=true): генератор сам проверяет, пуста ли база
if [ "${SEED_ON_START:-true}" = "true" ]; then
  python -m app.seed --candidates "${SEED_CANDIDATES:-300}" || echo "seed: пропущено"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_WORKERS:-2}" --proxy-headers
