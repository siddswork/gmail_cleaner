#!/usr/bin/env bash
# Stop Gmail Cleaner (backend + frontend)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stop_pid() {
  local file="$1"
  local name="$2"
  local port="$3"

  # Kill by PID file first
  if [ -f "$file" ]; then
    PID=$(cat "$file")
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID"
      echo "Stopped $name (PID $PID)"
    else
      echo "$name PID file was stale"
    fi
    rm -f "$file"
  else
    echo "No PID file for $name"
  fi

  # Kill any orphan still holding the port (use fuser, fallback to ss+kill)
  if [ -n "$port" ]; then
    ORPHAN=$(fuser "${port}/tcp" 2>/dev/null)
    if [ -n "$ORPHAN" ]; then
      kill $ORPHAN 2>/dev/null
      echo "Killed orphan on port $port (PID $ORPHAN)"
    fi
  fi
}

stop_pid "$SCRIPT_DIR/.backend.pid"  "backend"  8000
stop_pid "$SCRIPT_DIR/.frontend.pid" "frontend" 3000
