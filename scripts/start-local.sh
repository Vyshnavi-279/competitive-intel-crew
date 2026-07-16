#!/usr/bin/env bash
set -euo pipefail

# start-local.sh — start backend and frontend together
# Usage:  ./scripts/start-local.sh
#         BACKEND_PORT=8001 ./scripts/start-local.sh   # custom port

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# ── Activate the project venv (.venv takes priority, venv311 as fallback) ──
if [ -f "$ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
  echo "✓ Using .venv ($(python3 --version))"
elif [ -f "$ROOT/venv311/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/venv311/bin/activate"
  echo "✓ Using venv311 ($(python3 --version))"
else
  echo "⚠ No venv found — make sure dependencies are installed."
fi

# ── Sanity-check that crewai is importable before starting ──
if ! python3 -c "import crewai" 2>/dev/null; then
  echo "✗ crewai not found. Run: pip install -r requirements.txt"
  exit 1
fi

# ── Start backend ──
BACKEND_PORT=${BACKEND_PORT:-8000}
uvicorn backend.main:app --reload --port "$BACKEND_PORT" &
BACKEND_PID=$!
echo "✓ Backend started (pid=$BACKEND_PID) → http://localhost:$BACKEND_PORT"
echo "  API docs → http://localhost:$BACKEND_PORT/docs"

# ── Start frontend ──
(cd frontend && NEXT_PUBLIC_API_URL=http://localhost:$BACKEND_PORT npm run dev) &
FRONTEND_PID=$!
echo "✓ Frontend started (pid=$FRONTEND_PID) → http://localhost:3000"

echo ""
echo "To stop both:  kill $BACKEND_PID $FRONTEND_PID"
echo "               (or Ctrl+C)"

wait
