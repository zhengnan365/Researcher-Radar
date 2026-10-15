#!/usr/bin/env bash
set -euo pipefail

USERNAME="${1:-admin}"
EMAIL="${2:-}"
PASSWORD="${ADMIN_PASSWORD:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKEND_DIR="$PROJECT_DIR/backend"

if [ "$#" -gt 2 ]; then
  echo "不要将密码作为命令行参数传入；请运行脚本后按提示输入。" >&2
  exit 1
fi

if [ -z "$PASSWORD" ]; then
  if [ ! -t 0 ]; then
    echo "非交互运行时请通过 ADMIN_PASSWORD 环境变量提供密码。" >&2
    exit 1
  fi
  while true; do
    read -r -s -p "管理员密码: " PASSWORD
    echo
    read -r -s -p "再次输入管理员密码: " PASSWORD_CONFIRM
    echo
    if [ -n "$PASSWORD" ] && [ "$PASSWORD" = "$PASSWORD_CONFIRM" ]; then
      break
    fi
    echo "两次密码不一致或为空，请重新输入。" >&2
  done
fi

cd "$BACKEND_DIR"
source .venv/bin/activate

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$PROJECT_DIR/.env"
  set +a
fi

ADMIN_USERNAME="$USERNAME" ADMIN_EMAIL="$EMAIL" ADMIN_PASSWORD="$PASSWORD" python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ["ADMIN_USERNAME"]
email = os.environ.get("ADMIN_EMAIL", "")
password = os.environ["ADMIN_PASSWORD"]

user, created = User.objects.get_or_create(username=username)
user.email = email
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.set_password(password)
user.save()

print(("created" if created else "updated") + f" admin user: {username}")
PY
