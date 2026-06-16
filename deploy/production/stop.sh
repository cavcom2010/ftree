#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PRODUCTION_SERVICE_NAME="${PRODUCTION_SERVICE_NAME:-ftree-gunicorn.service}"
PID_FILE="$ROOT/.production/run/gunicorn.pid"

MODE="${1:---auto}"

print_usage() {
  cat <<'EOF'
Usage: ./deploy/production/stop.sh [mode]

Modes:
  --auto      Stop the debug gunicorn if running, otherwise stop systemd service (default).
  --debug     Force stop the debug gunicorn daemon.
  --systemd   Force stop the systemd gunicorn service and socket.

Environment:
  PRODUCTION_SERVICE_NAME=ftree-gunicorn.service
EOF
}

case "$MODE" in
  --auto)
    ;;
  --debug|--systemd)
    ;;
  -h|--help)
    print_usage
    exit 0
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    print_usage >&2
    exit 1
    ;;
esac

stop_debug() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No debug PID file found at $PID_FILE"
    return 0
  fi
  local pid=""
  pid="$(tr -dc '0-9' < "$PID_FILE")"
  if [[ -z "$pid" ]]; then
    echo "Debug PID file is empty."
    rm -f "$PID_FILE"
    return 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Debug Gunicorn pid ${pid} is not running."
    rm -f "$PID_FILE"
    return 0
  fi
  echo "Stopping debug Gunicorn pid ${pid}..."
  kill -TERM "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "Force killing debug Gunicorn pid ${pid}..."
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "Debug Gunicorn stopped."
}

stop_systemd() {
  echo "Stopping ${PRODUCTION_SERVICE_NAME}..."
  sudo systemctl stop "$PRODUCTION_SERVICE_NAME" 2>/dev/null || true
  sudo systemctl stop "${PRODUCTION_SERVICE_NAME%.service}.socket" 2>/dev/null || true
  echo "Systemd Gunicorn service stopped."
}

if [[ "$MODE" == "--debug" ]]; then
  stop_debug
elif [[ "$MODE" == "--systemd" ]]; then
  stop_systemd
else
  if [[ -f "$PID_FILE" ]]; then
    DBG_PID="$(tr -dc '0-9' < "$PID_FILE")"
    if [[ -n "$DBG_PID" ]] && kill -0 "$DBG_PID" 2>/dev/null; then
      stop_debug
      exit 0
    fi
  fi
  stop_systemd
fi
