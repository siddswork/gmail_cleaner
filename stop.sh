#!/usr/bin/env bash
# Stop Gmail Cleaner (backend + frontend)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stop_pid() {
  local file="$1"
  local name="$2"
  if [ -f "$file" ]; then
    PID=$(cat "$file")
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID"
      echo "Stopped $name (PID $PID)"
    else
      echo "$name was not running"
    fi
    rm -f "$file"
  else
    echo "No PID file for $name — may not be running"
  fi
}

stop_pid "$SCRIPT_DIR/.backend.pid" "backend"
stop_pid "$SCRIPT_DIR/.frontend.pid" "frontend"
