#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKEND_DIR="$PROJECT_DIR/backend"
if [ "$PROJECT_DIR" = "/www/wwwroot/researcher-radar" ]; then
  SERVICE_NAME="${SERVICE_NAME:-literature_daily}"
else
  SERVICE_NAME="${SERVICE_NAME:-researcher-radar}"
fi

if [ ! -d "$BACKEND_DIR" ] || [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "项目目录或 .env 不存在：$PROJECT_DIR" >&2
  exit 1
fi

cd "$BACKEND_DIR"
source .venv/bin/activate
set -a
# shellcheck disable=SC1090
source "$PROJECT_DIR/.env"
set +a
BACKEND_PORT="${BACKEND_PORT:-8000}"

port_is_listening() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$BACKEND_PORT" 2>/dev/null | grep -q LISTEN
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi
  return 1
}

release_backend_port() {
  if ! port_is_listening; then
    return
  fi
  echo "检测到端口 $BACKEND_PORT 被旧进程占用，准备释放："
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$BACKEND_PORT" 2>/dev/null || true
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -k -TERM "$BACKEND_PORT/tcp" 2>/dev/null || true
  else
    local pids
    pids="$(ss -ltnp "sport = :$BACKEND_PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u | xargs || true)"
    [ -z "$pids" ] || kill -TERM $pids 2>/dev/null || true
  fi
  for _ in $(seq 1 10); do
    port_is_listening || return
    sleep 1
  done
  if command -v fuser >/dev/null 2>&1; then
    fuser -k -KILL "$BACKEND_PORT/tcp" 2>/dev/null || true
  else
    local remaining_pids
    remaining_pids="$(ss -ltnp "sport = :$BACKEND_PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u | xargs || true)"
    [ -z "$remaining_pids" ] || kill -KILL $remaining_pids 2>/dev/null || true
  fi
  sleep 1
  if port_is_listening; then
    echo "无法释放端口 $BACKEND_PORT。" >&2
    return 1
  fi
}

echo "数据库：${DJANGO_SQLITE_PATH:-$BACKEND_DIR/db.sqlite3}"
python manage.py migrate
python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute('BEGIN IMMEDIATE'); cursor.execute('ROLLBACK'); print('SQLite write check: OK')"
python manage.py showmigrations authtoken

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$SERVICE_NAME.service" >/dev/null 2>&1; then
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  release_backend_port
  systemctl start "$SERVICE_NAME"
  sleep 1
  systemctl --no-pager --full status "$SERVICE_NAME" | head -n 20
else
  echo "未找到 systemd 服务 $SERVICE_NAME，请在宝塔中重启后端 Python 项目。"
fi

echo "登录数据库检查与修复完成。"
