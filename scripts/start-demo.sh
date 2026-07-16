#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# start-demo.sh  —  one command to start MarketPulse locally
#
# Usage (from project root):
#   ./scripts/start-demo.sh
#
# Opens:
#   Frontend  →  http://localhost:3000
#   Backend   →  http://localhost:8000
#   API docs  →  http://localhost:8000/docs
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
UVICORN="$VENV/bin/uvicorn"
PYTHON="$VENV/bin/python3"
LOG_BACKEND="/tmp/marketpulse-backend.log"
LOG_FRONTEND="/tmp/marketpulse-frontend.log"

echo ""
echo "  ███╗   ███╗ █████╗ ██████╗ ██╗  ██╗███████╗████████╗"
echo "  ████╗ ████║██╔══██╗██╔══██╗██║ ██╔╝██╔════╝╚══██╔══╝"
echo "  ██╔████╔██║███████║██████╔╝█████╔╝ █████╗     ██║   "
echo "  ██║╚██╔╝██║██╔══██║██╔══██╗██╔═██╗ ██╔══╝     ██║   "
echo "  ██║ ╚═╝ ██║██║  ██║██║  ██║██║  ██╗███████╗   ██║   "
echo "  ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝   "
echo "  ██████╗ ██╗   ██╗██╗     ███████╗███████╗"
echo "  ██╔══██╗██║   ██║██║     ██╔════╝██╔════╝"
echo "  ██████╔╝██║   ██║██║     ███████╗█████╗  "
echo "  ██╔═══╝ ██║   ██║██║     ╚════██║██╔══╝  "
echo "  ██║     ╚██████╔╝███████╗███████║███████╗"
echo "  ╚═╝      ╚═════╝ ╚══════╝╚══════╝╚══════╝"
echo ""

# ── Sanity checks ────────────────────────────────────────────
if [ ! -x "$UVICORN" ]; then
  echo "✗  venv not found at $VENV"
  echo "   Run:  python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [ ! -f "$ROOT/.env" ]; then
  echo "✗  .env file missing — copy .env.example and fill in your keys"
  exit 1
fi

# ── Kill anything already on ports 8000 / 3000 ───────────────
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
sleep 1

echo "▶  Starting backend  (logs → $LOG_BACKEND)"
cd "$ROOT"
PYTHONPATH="$ROOT" "$UVICORN" backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  > "$LOG_BACKEND" 2>&1 &
BACKEND_PID=$!

# Wait for backend to be healthy
echo -n "   Waiting for backend"
for i in $(seq 1 15); do
  if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "  ✓"
    break
  fi
  echo -n "."
  sleep 1
done

if ! curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
  echo ""
  echo "✗  Backend failed to start. Check $LOG_BACKEND"
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi

echo "▶  Starting frontend  (logs → $LOG_FRONTEND)"
(
  cd "$ROOT/frontend"
  NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev \
    > "$LOG_FRONTEND" 2>&1
) &
FRONTEND_PID=$!

# Wait for frontend
echo -n "   Waiting for frontend"
for i in $(seq 1 20); do
  if curl -sf http://localhost:3000 >/dev/null 2>&1; then
    echo "  ✓"
    break
  fi
  echo -n "."
  sleep 2
done

echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  ✓  MarketPulse is running                  │"
echo "  │                                             │"
echo "  │  Dashboard  →  http://localhost:3000        │"
echo "  │  API docs   →  http://localhost:8000/docs   │"
echo "  │                                             │"
echo "  │  Press Ctrl+C to stop both services         │"
echo "  └─────────────────────────────────────────────┘"
echo ""

# Open browser automatically (macOS)
open http://localhost:3000 2>/dev/null || true

# Keep running — Ctrl+C kills both
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
