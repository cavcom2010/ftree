#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

detect_home_ip() {
  local detected_ip=""

  if [[ -n "${HOME_INTERFACE:-}" ]]; then
    detected_ip="$(ip -o -4 addr show dev "${HOME_INTERFACE}" scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1 || true)"
  fi

  if [[ -z "$detected_ip" ]]; then
    detected_ip="$(ip -o -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' || true)"
  fi

  if [[ -z "$detected_ip" ]]; then
    detected_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi

  printf '%s' "$detected_ip"
}

csv_add_unique() {
  local csv="$1"
  local value="$2"
  printf '%s\n' "${csv},${value}" | tr ',' '\n' | awk 'NF && !seen[$0]++' | paste -sd, -
}

if [[ ! -x "$ROOT/venv/bin/python" ]]; then
  echo "Missing venv at $ROOT/venv. Activate/create your venv first." >&2
  exit 1
fi

if [[ ! -x "$ROOT/venv/bin/gunicorn" ]]; then
  echo "Missing gunicorn at $ROOT/venv/bin/gunicorn. Install requirements in this venv first." >&2
  exit 1
fi

mkdir -p "$ROOT/.home_nginx/logs" "$ROOT/.home_nginx/run"
mkdir -p "$ROOT/.home_nginx/tmp/client_body" "$ROOT/.home_nginx/tmp/proxy" "$ROOT/.home_nginx/tmp/fastcgi" "$ROOT/.home_nginx/tmp/uwsgi" "$ROOT/.home_nginx/tmp/scgi"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.deploy}"
export DJANGO_ENFORCE_STRONG_SECRET_KEY="${DJANGO_ENFORCE_STRONG_SECRET_KEY:-0}"

echo "Collecting static files..."
"$ROOT/venv/bin/python" manage.py collectstatic --noinput >/dev/null

set -a
if [[ -f "$ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.env"
fi
set +a

HOME_PORT="${HOME_PORT:-8009}"
HOME_UPSTREAM_PORT="${HOME_UPSTREAM_PORT:-8028}"
HOME_IP="${HOME_IP:-$(detect_home_ip)}"
EMAIL_BACKEND="${EMAIL_BACKEND:-django.core.mail.backends.console.EmailBackend}"
HOME_STREAM_LOGS="${HOME_STREAM_LOGS:-1}"
export EMAIL_BACKEND

if [[ -z "$HOME_IP" ]]; then
  echo "Could not auto-detect HOME_IP. Set HOME_IP in your environment or .env." >&2
  exit 1
fi

DJANGO_ALLOWED_HOSTS_BASE="${DJANGO_ALLOWED_HOSTS_BASE:-localhost,127.0.0.1}"
DJANGO_CSRF_TRUSTED_ORIGINS_BASE="${DJANGO_CSRF_TRUSTED_ORIGINS_BASE:-http://localhost:${HOME_PORT}}"

export DJANGO_ALLOWED_HOSTS
DJANGO_ALLOWED_HOSTS="$(csv_add_unique "$DJANGO_ALLOWED_HOSTS_BASE" "$HOME_IP")"

export DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_CSRF_TRUSTED_ORIGINS="$(csv_add_unique "$DJANGO_CSRF_TRUSTED_ORIGINS_BASE" "http://${HOME_IP}:${HOME_PORT}")"

export ALLOWED_HOSTS
ALLOWED_HOSTS="$(csv_add_unique "${ALLOWED_HOSTS:-127.0.0.1,localhost}" "$HOME_IP")"

export CSRF_TRUSTED_ORIGINS
CSRF_TRUSTED_ORIGINS="$(csv_add_unique "${CSRF_TRUSTED_ORIGINS:-http://localhost:${HOME_PORT},http://127.0.0.1:${HOME_PORT}}" "http://${HOME_IP}:${HOME_PORT}")"

export SITE_BASE_URL="http://${HOME_IP}:${HOME_PORT}"

GUNICORN_PID="$ROOT/.home_nginx/run/gunicorn.pid"
HOME_IP_STATE_FILE="$ROOT/.home_nginx/run/home_ip.txt"
PREV_HOME_IP="$(cat "$HOME_IP_STATE_FILE" 2>/dev/null || true)"

if [[ -f "$GUNICORN_PID" ]] && kill -0 "$(cat "$GUNICORN_PID")" 2>/dev/null; then
  if [[ -n "$PREV_HOME_IP" && "$PREV_HOME_IP" != "$HOME_IP" ]]; then
    echo "Home IP changed (${PREV_HOME_IP} -> ${HOME_IP}). Restarting Gunicorn..."
    kill "$(cat "$GUNICORN_PID")" 2>/dev/null || true
    rm -f "$GUNICORN_PID"
  else
    echo "Gunicorn already running (pid $(cat "$GUNICORN_PID"))."
  fi
fi

if [[ ! -f "$GUNICORN_PID" ]] || ! kill -0 "$(cat "$GUNICORN_PID")" 2>/dev/null; then
  echo "Starting Gunicorn on 127.0.0.1:${HOME_UPSTREAM_PORT}..."
  "$ROOT/venv/bin/gunicorn" \
    config.wsgi:application \
    --bind "127.0.0.1:${HOME_UPSTREAM_PORT}" \
    --workers 3 \
    --timeout 120 \
    --access-logfile "$ROOT/.home_nginx/logs/gunicorn-access.log" \
    --error-logfile "$ROOT/.home_nginx/logs/gunicorn-error.log" \
    --capture-output \
    --log-level info \
    --daemon \
    --pid "$GUNICORN_PID"
fi

printf '%s\n' "$HOME_IP" >"$HOME_IP_STATE_FILE"

NGINX_PREFIX="$ROOT/.home_nginx"
NGINX_CONF="$ROOT/deploy/home/nginx.conf"
NGINX_PID="$ROOT/.home_nginx/run/nginx.pid"

if [[ -f "$NGINX_PID" ]] && kill -0 "$(cat "$NGINX_PID")" 2>/dev/null; then
  echo "Nginx already running (pid $(cat "$NGINX_PID")). Reloading config..."
  nginx -p "$NGINX_PREFIX" -c "$NGINX_CONF" -s reload
else
  echo "Starting Nginx on 0.0.0.0:${HOME_PORT}..."
  nginx -p "$NGINX_PREFIX" -c "$NGINX_CONF"
fi

echo "Done."
echo "Detected HOME_IP: ${HOME_IP}"
echo "Open: ${SITE_BASE_URL}/"
echo "Email backend: ${EMAIL_BACKEND}"

if [[ "$HOME_STREAM_LOGS" == "1" ]]; then
  echo "Streaming authentication emails from $ROOT/.home_nginx/logs/gunicorn-error.log"
  echo "Verification emails will appear below. Press Ctrl+C to stop watching logs; services keep running."
  tail -n 0 -F "$ROOT/.home_nginx/logs/gunicorn-error.log"
fi
