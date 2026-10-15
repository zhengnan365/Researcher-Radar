#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKEND_DIR="${BACKEND_DIR:-$PROJECT_DIR/backend}"
DOMAIN="${DOMAIN:-}"
SERVER_IP="${SERVER_IP:-}"
PUBLIC_SCHEME="${PUBLIC_SCHEME:-https}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
WORKERS="${GUNICORN_WORKERS:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-300}"
STATIC_ROOT="${DJANGO_STATIC_ROOT:-$BACKEND_DIR/staticfiles}"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$PROJECT_DIR/.env"
  set +a
fi

if [ -z "$DOMAIN" ]; then
  echo "请在环境变量或 $PROJECT_DIR/.env 中设置 DOMAIN。" >&2
  exit 1
fi

allowed_hosts="$DOMAIN,127.0.0.1,localhost"
if [ -n "$SERVER_IP" ]; then
  allowed_hosts="$allowed_hosts,$SERVER_IP"
fi

cd "$BACKEND_DIR"

export DJANGO_DEBUG="${DJANGO_DEBUG:-false}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-$allowed_hosts}"
export DJANGO_CORS_ALLOWED_ORIGINS="${DJANGO_CORS_ALLOWED_ORIGINS:-$PUBLIC_SCHEME://$DOMAIN}"
export DJANGO_CSRF_TRUSTED_ORIGINS="${DJANGO_CSRF_TRUSTED_ORIGINS:-$PUBLIC_SCHEME://$DOMAIN}"
export DJANGO_STATIC_ROOT="$STATIC_ROOT"
if [ "$PUBLIC_SCHEME" = "https" ]; then
  export DJANGO_SECURE_SSL_REDIRECT="${DJANGO_SECURE_SSL_REDIRECT:-true}"
  export DJANGO_SESSION_COOKIE_SECURE="${DJANGO_SESSION_COOKIE_SECURE:-true}"
  export DJANGO_CSRF_COOKIE_SECURE="${DJANGO_CSRF_COOKIE_SECURE:-true}"
  export DJANGO_SECURE_HSTS_SECONDS="${DJANGO_SECURE_HSTS_SECONDS:-3600}"
  export DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS="${DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS:-false}"
fi

exec "$BACKEND_DIR/.venv/bin/gunicorn" literature_backend.wsgi:application \
  --bind "127.0.0.1:$BACKEND_PORT" \
  --workers "$WORKERS" \
  --timeout "$TIMEOUT"
