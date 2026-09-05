#!/usr/bin/env bash
# macOS / Linux: backend ve frontend'i birlikte başlatır (Ctrl+C ikisini de durdurur).
# Kurulum: backend/.venv içinde Python 3.12 (conda create -p backend/.venv python=3.12 ya da python3.12 -m venv backend/.venv),
#          backend/.venv/bin/python -m pip install -r backend/requirements.txt ; cd frontend && npm install
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || { echo "backend/.venv bulunamadı; README'deki kurulum adımlarını uygulayın."; exit 1; }
(cd "$ROOT/backend" && "$PY" -m uvicorn app.main:app --reload --port 8000) &
BACK=$!
(cd "$ROOT/frontend" && npm run dev) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' EXIT INT TERM
sleep 3
command -v open >/dev/null && open "http://127.0.0.1:5173" || true
wait
