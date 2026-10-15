#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-${DOMAIN:-}}"
PROJECT_DIR="${PROJECT_DIR:-/www/wwwroot/researcher-radar}"
BACKEND_DIR="$PROJECT_DIR/backend"

if [ -z "$DOMAIN" ]; then
  echo "请提供域名：bash scripts/server_setup.sh your-domain.com" >&2
  exit 1
fi

if [ ! -d "$BACKEND_DIR" ]; then
  echo "Backend directory not found: $BACKEND_DIR" >&2
  exit 1
fi

cd "$BACKEND_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install with: apt install -y python3 python3-venv python3-pip" >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

export DJANGO_DEBUG="${DJANGO_DEBUG:-false}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-$DOMAIN,127.0.0.1,localhost}"
export DJANGO_CORS_ALLOWED_ORIGINS="${DJANGO_CORS_ALLOWED_ORIGINS:-https://$DOMAIN}"
export DJANGO_CSRF_TRUSTED_ORIGINS="${DJANGO_CSRF_TRUSTED_ORIGINS:-https://$DOMAIN}"
export DJANGO_STATIC_ROOT="${DJANGO_STATIC_ROOT:-$BACKEND_DIR/staticfiles}"
export DJANGO_SECURE_SSL_REDIRECT="${DJANGO_SECURE_SSL_REDIRECT:-true}"
export DJANGO_SESSION_COOKIE_SECURE="${DJANGO_SESSION_COOKIE_SECURE:-true}"
export DJANGO_CSRF_COOKIE_SECURE="${DJANGO_CSRF_COOKIE_SECURE:-true}"
export DJANGO_SECURE_HSTS_SECONDS="${DJANGO_SECURE_HSTS_SECONDS:-3600}"
export DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS="${DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS:-false}"

mkdir -p "$BACKEND_DIR/logs"
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check

cat <<EOF
Backend initialized.

Gunicorn command:
cd $BACKEND_DIR && DJANGO_DEBUG=false DJANGO_ALLOWED_HOSTS=$DOMAIN,127.0.0.1,localhost DJANGO_CORS_ALLOWED_ORIGINS=https://$DOMAIN DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN DJANGO_STATIC_ROOT=$BACKEND_DIR/staticfiles $BACKEND_DIR/.venv/bin/gunicorn literature_backend.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 300
EOF
