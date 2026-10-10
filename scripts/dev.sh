#!/usr/bin/env bash
# Локальный запуск без Docker (Linux/macOS): SQLite + мок ФСП + бэкенд + фронтенд.
# Требуется: Python 3.10+, Node.js 20+.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r backend/requirements.txt -r fsp-mock/requirements.txt
export DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT/backend/scout.db}"
(cd fsp-mock && uvicorn main:app --port 8001 > "$ROOT/.fsp.log" 2>&1 &)
sleep 2
cd backend
if [ ! -f scout.db ] && [[ "$DATABASE_URL" == sqlite* ]]; then
  echo "Генерирую демо-данные (1–2 минуты)…"
  python -m app.seed --candidates "${SEED_CANDIDATES:-300}"
fi
(uvicorn app.main:app --port 8000 > "$ROOT/.api.log" 2>&1 &)
cd ../frontend
[ -d node_modules ] || npm ci --no-audit --no-fund
BACKEND_URL=http://127.0.0.1:8000 npm run build
echo "Готово: http://localhost:3000  (API: http://localhost:8000/api/docs)"
BACKEND_URL=http://127.0.0.1:8000 npm start
