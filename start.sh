#!/usr/bin/env bash
# Start Gmail Cleaner (backend + frontend)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_PID_FILE="$SCRIPT_DIR/.backend.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"

# Check .venv is activated or exists
if [ ! -f ".venv/bin/uvicorn" ]; then
  echo "ERROR: .venv not found or dependencies not installed."
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "ERROR: frontend/node_modules not found."
  echo "Run: cd frontend && npm install"
  exit 1
fi

echo "Starting backend (FastAPI) on http://localhost:8000 ..."
.venv/bin/uvicorn backend.main:app --port 8000 > .backend.log 2>&1 &
echo $! > "$BACKEND_PID_FILE"

echo "Starting frontend (Next.js) on http://localhost:3000 ..."
rm -f "$SCRIPT_DIR/frontend/.next/dev/lock"
cd frontend && npm run dev > ../.frontend.log 2>&1 &
echo $! > "$FRONTEND_PID_FILE"
cd "$SCRIPT_DIR"

echo ""
echo "Both services started."
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000"
echo ""
echo "Logs: .backend.log  .frontend.log"
echo "Stop: ./stop.sh"
