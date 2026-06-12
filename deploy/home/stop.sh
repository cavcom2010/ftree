#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

NGINX_PREFIX="$ROOT/.home_nginx"
NGINX_CONF="$ROOT/deploy/home/nginx.conf"

echo "Stopping Nginx..."
nginx -p "$NGINX_PREFIX" -c "$NGINX_CONF" -s stop 2>/dev/null || true

GUNICORN_PID="$ROOT/.home_nginx/run/gunicorn.pid"
if [[ -f "$GUNICORN_PID" ]]; then
  PID="$(cat "$GUNICORN_PID")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping Gunicorn (pid $PID)..."
    kill "$PID" 2>/dev/null || true
  fi
  rm -f "$GUNICORN_PID"
fi

echo "Stopped."
