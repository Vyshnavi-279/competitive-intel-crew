#!/usr/bin/env bash
# start-local.sh — reliably start backend + frontend using the project venv.
# Usage: ./scripts/start-local.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
UVICORN="$VENV/bin/uvicorn"
PYTHON="$VENV/bin/python3"

# ── Sanity checks ────────────────────────────────────────────────────────────
if [ ! -x "$UVICORN" ]; then
  echo "✗ $UVICORN not found. Run: pip install -r requirements.txt inside the venv."
  exit 1
fi
if ! "$PYTHON" -c "import crewai" 2>/dev/null; then
  echo "✗ crewai not importable. Run: $VENV/bin/pip install -r $ROOT/requirements.txt"
  exit 1
fi

# ── Kill anything already on port 8000 ───────────────────────────────────────
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 1

echo "✓ Using Python: $($PYTHON --version)"

# ── Backend ───────────────────────────────────────────────────────────────────
BACKEND_PORT="${BACKEND_PORT:-8000}"
cd "$ROOT"
PYTHONPATH="$ROOT" "$UVICORN" backend.main:app --reload --port "$BACKEND_PORT" &
BACKEND_PID=$!
echo "✓ Backend → http://localhost:$BACKEND_PORT  (pid=$BACKEND_PID)"

sleep 3
if ! curl -sf "http://localhost:$BACKEND_PORT/api/health" >/dev/null; then
  echo "✗ Backend failed to start. Check /tmp/backend.log"
  kill $BACKEND_PID 2>/dev/null
  exit 1
fi
echo "  Health OK"

# ── Frontend ──────────────────────────────────────────────────────────────────
(
  cd "$ROOT/frontend"
  NEXT_PUBLIC_API_URL="http://localhost:$BACKEND_PORT" npm run dev
) &
FRONTEND_PID=$!
echo "✓ Frontend → http://localhost:3000  (pid=$FRONTEND_PID)"

echo ""
echo "Stop both:  kill $BACKEND_PID $FRONTEND_PID   (or Ctrl+C)"
wait
