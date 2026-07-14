#!/usr/bin/env bash
set -euo pipefail

# start-local.sh — start backend and frontend in separate terminals
# Usage: ./scripts/start-local.sh

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# Activate venv311 if present
if [ -f "$ROOT/venv311/bin/activate" ]; then
  source "$ROOT/venv311/bin/activate"
fi

# Start backend on 8002 (change PORT if needed)
BACKEND_PORT=${BACKEND_PORT:-8002}
uvicorn backend.main:app --reload --port "$BACKEND_PORT" &
BACKEND_PID=$!

echo "Started backend (pid=$BACKEND_PID) on http://localhost:$BACKEND_PORT"

# Start frontend
(cd frontend && NEXT_PUBLIC_API_URL=http://localhost:$BACKEND_PORT npm run dev) &
FRONTEND_PID=$!

echo "Started frontend (pid=$FRONTEND_PID)"

echo "To stop: kill $BACKEND_PID $FRONTEND_PID"
wait
