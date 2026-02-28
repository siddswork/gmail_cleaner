#!/usr/bin/env bash
# Status of Gmail Cleaner services (backend + frontend)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID_FILE="$SCRIPT_DIR/.backend.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"

port_listening() {
  ss -tlnp "sport = :$1" 2>/dev/null | grep -q LISTEN
}

check_service() {
  local name="$1"
  local pid_file="$2"
  local url="$3"
  local port="$4"

  if [ ! -f "$pid_file" ]; then
    printf "  %-12s  DOWN    %s\n" "$name" "$url"
    return
  fi

  local pid
  pid=$(cat "$pid_file")

  if kill -0 "$pid" 2>/dev/null; then
    if port_listening "$port"; then
      printf "  %-12s  UP      PID %-8s  %s\n" "$name" "$pid" "$url"
    else
      printf "  %-12s  UP      PID %-8s  WARNING: not listening on port %s\n" "$name" "$pid" "$port"
    fi
  else
    if port_listening "$port"; then
      printf "  %-12s  DOWN    (orphan on port %s — run ./stop.sh)\n" "$name" "$port"
    else
      printf "  %-12s  DOWN    %s\n" "$name" "$url"
    fi
  fi
}

echo ""
echo "Gmail Cleaner — service status"
echo "─────────────────────────────────────────────────────"
check_service "backend"  "$BACKEND_PID_FILE"  "http://localhost:8000" 8000
check_service "frontend" "$FRONTEND_PID_FILE" "http://localhost:3000" 3000
echo "─────────────────────────────────────────────────────"
echo ""
