#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

HOME_DIR="$ROOT/.home_nginx"
RUN_DIR="$HOME_DIR/run"
NGINX_PID="$RUN_DIR/nginx.pid"
GUNICORN_PID="$RUN_DIR/gunicorn.pid"
GUNICORN_PORT_FILE="$RUN_DIR/gunicorn.port"

echo "Stopping HeritageTree home server..."

if [[ -f "$NGINX_PID" ]]; then
  if nginx -p "$HOME_DIR" -c "$HOME_DIR/nginx.conf" -s stop 2>/dev/null; then
    echo "Nginx stopped."
  else
    pid="$(cat "$NGINX_PID" 2>/dev/null || echo "")"
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$NGINX_PID"
fi

if [[ -f "$GUNICORN_PID" ]]; then
  pid="$(cat "$GUNICORN_PID" 2>/dev/null || echo "")"
  if [[ -n "$pid" ]]; then
    kill -TERM "$pid" 2>/dev/null || true
    for _ in {1..10}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.5
    done
    kill -9 "$pid" 2>/dev/null || true
    echo "Gunicorn stopped."
  fi
  rm -f "$GUNICORN_PID"
fi

gunicorn_port="${HOME_APP_PORT:-8028}"
if [[ -f "$GUNICORN_PORT_FILE" ]]; then
  stored_port="$(tr -dc '0-9' < "$GUNICORN_PORT_FILE")"
  if [[ -n "$stored_port" ]]; then
    gunicorn_port="$stored_port"
  fi
fi

NGINX_PORT="${HOME_PORT:-8008}"
NGINX_HTTPS_PORT="${HOME_HTTPS_PORT:-8443}"
GUNICORN_PORT="$gunicorn_port"

pids="$(ss -ltnp "( sport = :${NGINX_PORT} or sport = :${NGINX_HTTPS_PORT} or sport = :${GUNICORN_PORT} )" 2>/dev/null | grep -o 'pid=[0-9]\+' | cut -d= -f2 | sort -u || true)"
if [[ -n "$pids" ]]; then
  kill $pids 2>/dev/null || true
  sleep 0.5
  kill -9 $pids 2>/dev/null || true
fi

rm -f "$GUNICORN_PORT_FILE"

echo "Done."
