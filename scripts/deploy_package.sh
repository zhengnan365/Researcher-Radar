#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PROJECT_DIR="/www/wwwroot/researcher-radar"
DEFAULT_DOMAIN=""
DEFAULT_SCHEME="https"
DEFAULT_BACKEND_PORT="8000"
DEFAULT_SERVICE_NAME="researcher-radar"
DEFAULT_CRON_EXPR="0 8 * * *"

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
if [ -d "$SCRIPT_DIR/backend" ] && [ -d "$SCRIPT_DIR/frontend" ]; then
  SOURCE_DIR="$SCRIPT_DIR"
else
  SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
TEMP_DIR=""

prompt() {
  local label="$1"
  local default_value="${2:-}"
  local value
  if [ -n "$default_value" ]; then
    read -r -p "$label [$default_value]: " value
    printf '%s' "${value:-$default_value}"
  else
    read -r -p "$label: " value
    printf '%s' "$value"
  fi
}

yes_no() {
  local label="$1"
  local default_value="${2:-Y}"
  local value
  read -r -p "$label [$default_value]: " value
  value="${value:-$default_value}"
  case "${value,,}" in
    y|yes|true|1|是) return 0 ;;
    *) return 1 ;;
  esac
}

cleanup() {
  if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
  fi
}
trap cleanup EXIT

if [ "${1:-}" != "" ]; then
  ARCHIVE_PATH="$(readlink -f "$1")"
  if [ ! -f "$ARCHIVE_PATH" ]; then
    echo "找不到压缩包：$ARCHIVE_PATH" >&2
    exit 1
  fi
  TEMP_DIR="$(mktemp -d)"
  unzip -q "$ARCHIVE_PATH" -d "$TEMP_DIR"
  if [ -d "$TEMP_DIR/backend" ] && [ -d "$TEMP_DIR/frontend" ]; then
    SOURCE_DIR="$TEMP_DIR"
  else
    SOURCE_DIR="$(find "$TEMP_DIR" -mindepth 1 -maxdepth 2 -type d -name backend -print -quit | xargs -r dirname)"
  fi
fi

if [ ! -d "$SOURCE_DIR/backend" ] || [ ! -d "$SOURCE_DIR/frontend" ]; then
  echo "部署包结构不正确，应包含 backend/ 和 frontend/：$SOURCE_DIR" >&2
  exit 1
fi

load_existing_env() {
  local env_file="$1"
  if [ -f "$env_file" ]; then
    # shellcheck disable=SC1090
    set -a && source "$env_file" && set +a
  fi
}

install_system_deps() {
  if ! command -v apt >/dev/null 2>&1; then
    echo "未检测到 apt，跳过系统依赖安装。"
    return
  fi
  if [ "$(id -u)" -ne 0 ]; then
    echo "当前不是 root，跳过系统依赖安装。"
    return
  fi
  apt update
  apt install -y python3 python3-venv python3-pip nodejs npm unzip rsync cron psmisc
}

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

show_port_owner() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$BACKEND_PORT" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null || true
  fi
}

release_backend_port() {
  if ! port_is_listening; then
    echo "后端端口 $BACKEND_PORT 当前空闲。"
    return
  fi

  echo "检测到后端端口 $BACKEND_PORT 已被占用，准备强制释放："
  show_port_owner

  if command -v fuser >/dev/null 2>&1; then
    fuser -k -TERM "$BACKEND_PORT/tcp" 2>/dev/null || true
  else
    local pids
    pids="$(ss -ltnp "sport = :$BACKEND_PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u | xargs || true)"
    if [ -n "$pids" ]; then
      kill -TERM $pids 2>/dev/null || true
    fi
  fi

  local waited
  for waited in $(seq 1 10); do
    if ! port_is_listening; then
      echo "后端端口 $BACKEND_PORT 已释放。"
      return
    fi
    sleep 1
  done

  echo "端口 $BACKEND_PORT 上的进程未正常退出，执行强制终止。"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k -KILL "$BACKEND_PORT/tcp" 2>/dev/null || true
  else
    local remaining_pids
    remaining_pids="$(ss -ltnp "sport = :$BACKEND_PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u | xargs || true)"
    if [ -n "$remaining_pids" ]; then
      kill -KILL $remaining_pids 2>/dev/null || true
    fi
  fi
  sleep 1

  if port_is_listening; then
    echo "无法释放后端端口 $BACKEND_PORT，当前占用信息：" >&2
    show_port_owner >&2
    return 1
  fi
  echo "后端端口 $BACKEND_PORT 已强制释放。"
}

sync_code() {
  mkdir -p "$PROJECT_DIR"
  if [ "$(readlink -f "$SOURCE_DIR")" = "$(readlink -f "$PROJECT_DIR")" ]; then
    echo "代码已位于项目目录，跳过自我同步。"
    return
  fi
  rsync -av --delete \
    --exclude=".git/" \
    --exclude=".env" \
    --exclude=".env.*" \
    --exclude="data/" \
    --exclude="logs/" \
    --exclude="deploy/" \
    --exclude="backend/db.sqlite3" \
    --exclude="backend/.venv/" \
    --exclude="backend/logs/" \
    --exclude="backend/staticfiles/" \
    --exclude="frontend/node_modules/" \
    --exclude="frontend/.env.production" \
    --exclude="__pycache__/" \
    --exclude="*.pyc" \
    --exclude="*.log" \
    "$SOURCE_DIR/" "$PROJECT_DIR/"
}

prepare_runtime_dirs() {
  mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/logs" "$PROJECT_DIR/deploy" "$BACKEND_DIR/logs"
  if [ ! -f "$PROJECT_DIR/data/db.sqlite3" ] && [ -f "$BACKEND_DIR/db.sqlite3" ]; then
    cp "$BACKEND_DIR/db.sqlite3" "$PROJECT_DIR/data/db.sqlite3"
    echo "已将旧数据库复制到：$PROJECT_DIR/data/db.sqlite3"
  fi
}

write_env() {
  local env_file="$PROJECT_DIR/.env"
  local preserved_env
  preserved_env="$(mktemp)"
  local secret
  secret="${DJANGO_SECRET_KEY:-}"
  if [ -z "$secret" ]; then
    secret="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(50))
PY
)"
  fi
  if [ -f "$env_file" ]; then
grep -Ev '^(DJANGO_SECRET_KEY|DJANGO_DEBUG|DJANGO_ALLOWED_HOSTS|DJANGO_CORS_ALLOWED_ORIGINS|DJANGO_CSRF_TRUSTED_ORIGINS|DJANGO_SECURE_SSL_REDIRECT|DJANGO_SESSION_COOKIE_SECURE|DJANGO_CSRF_COOKIE_SECURE|DJANGO_SECURE_HSTS_SECONDS|DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS|DJANGO_SECURE_HSTS_PRELOAD|DJANGO_SQLITE_PATH|DJANGO_STATIC_ROOT|LITERATURE_HTTP_TIMEOUT|REPORT_MIN_RECOMMEND_SCORE|REPORT_SHOW_WEAK_RELATED|REPORT_MAX_PAPERS|SCORE_WEAK_THRESHOLD|SCORE_(TITLE_KEYWORD|ABSTRACT_KEYWORD|RAW_KEYWORD|JOURNAL_KEYWORD|SOURCE_CATEGORY_KEYWORD|DIRECTION_NAME|DIRECTION_DESCRIPTION|SOURCE_DIRECTION|MULTI_FIELD_BONUS|MAX_SCORE|KEY_THRESHOLD|NORMAL_THRESHOLD)|BACKEND_PORT|DOMAIN|SERVER_IP|PUBLIC_SCHEME)=' "$env_file" > "$preserved_env" || true
  fi
  cat "$preserved_env" > "$env_file"
  rm -f "$preserved_env"
  cat >> "$env_file" <<EOF
DJANGO_SECRET_KEY=$secret
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=$DJANGO_ALLOWED_HOSTS_VALUE
DJANGO_CORS_ALLOWED_ORIGINS=$PUBLIC_SCHEME://$DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=$PUBLIC_SCHEME://$DOMAIN
DJANGO_SECURE_SSL_REDIRECT=$([ "$PUBLIC_SCHEME" = "https" ] && echo true || echo false)
DJANGO_SESSION_COOKIE_SECURE=$([ "$PUBLIC_SCHEME" = "https" ] && echo true || echo false)
DJANGO_CSRF_COOKIE_SECURE=$([ "$PUBLIC_SCHEME" = "https" ] && echo true || echo false)
DJANGO_SECURE_HSTS_SECONDS=$([ "$PUBLIC_SCHEME" = "https" ] && echo 3600 || echo 0)
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false
DJANGO_SQLITE_PATH=$PROJECT_DIR/data/db.sqlite3
DJANGO_STATIC_ROOT=$PROJECT_DIR/staticfiles
LITERATURE_HTTP_TIMEOUT=15
REPORT_MIN_RECOMMEND_SCORE=18
REPORT_SHOW_WEAK_RELATED=false
REPORT_MAX_PAPERS=80
SCORE_WEAK_THRESHOLD=8
BACKEND_PORT=$BACKEND_PORT
DOMAIN=$DOMAIN
SERVER_IP=$SERVER_IP
PUBLIC_SCHEME=$PUBLIC_SCHEME
EOF
  chmod 600 "$env_file"
}

load_runtime_env() {
  # shellcheck disable=SC1090
  set -a && source "$PROJECT_DIR/.env" && set +a
}

setup_backend() {
  cd "$BACKEND_DIR"
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  if [ -n "$PIP_MIRROR" ]; then
    pip install -r requirements.txt -i "$PIP_MIRROR"
  else
    pip install -r requirements.txt
  fi
  load_runtime_env
  python manage.py migrate
  python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute('BEGIN IMMEDIATE'); cursor.execute('ROLLBACK'); print('SQLite write check: OK')"
  python manage.py collectstatic --noinput
  python manage.py check
}

build_frontend() {
  cd "$FRONTEND_DIR"
  if [ -f "dist/index.html" ] && [ "$(readlink -f "$SOURCE_DIR")" != "$(readlink -f "$PROJECT_DIR")" ]; then
    echo "Using the prebuilt frontend bundled with this release."
    return
  fi
  cat > .env.production <<EOF
VITE_API_BASE_URL=$PUBLIC_SCHEME://$DOMAIN/api
VITE_ADMIN_URL=$PUBLIC_SCHEME://$DOMAIN/admin/
EOF
  if [ -n "$NPM_REGISTRY" ]; then
    npm config set registry "$NPM_REGISTRY"
  fi
  npm install
  npm run build
}

create_or_update_admin() {
  local username="$1"
  local email="$2"
  local password="$3"
  cd "$BACKEND_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  load_runtime_env
  ADMIN_USERNAME="$username" ADMIN_EMAIL="$email" ADMIN_PASSWORD="$password" python manage.py shell <<'PY'
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
}

normalize_cron_expr() {
  local raw="$1"
  raw="$(echo "$raw" | xargs)"
  if [[ "$raw" =~ ^[0-9]{1,2}$ ]]; then
    local hour="$raw"
    if [ "$hour" -ge 0 ] && [ "$hour" -le 23 ]; then
      echo "0 $hour * * *"
      return
    fi
  fi
  if [[ "$raw" =~ ^([0-9]{1,2}):([0-9]{1,2})$ ]]; then
    local hour="${BASH_REMATCH[1]}"
    local minute="${BASH_REMATCH[2]}"
    if [ "$hour" -ge 0 ] && [ "$hour" -le 23 ] && [ "$minute" -ge 0 ] && [ "$minute" -le 59 ]; then
      echo "$minute $hour * * *"
      return
    fi
  fi
  if [ "$(echo "$raw" | awk '{print NF}')" -eq 5 ]; then
    echo "$raw"
    return
  fi
  echo ""
}

install_cron_job() {
  local expr
  expr="$(normalize_cron_expr "$1")"
  if [ -z "$expr" ]; then
    echo "cron 表达式无效。示例：0 8 * * *，或直接输入 8 表示每天 08:00。"
    exit 1
  fi
  local log_file="$PROJECT_DIR/logs/researcher-radar.log"
  if [ "$PROJECT_DIR" = "/www/wwwroot/researcher-radar" ]; then
    log_file="$PROJECT_DIR/logs/literature_daily.log"
  fi
  local cron_cmd="cd $BACKEND_DIR && set -a && . $PROJECT_DIR/.env && set +a && $BACKEND_DIR/.venv/bin/python manage.py fetch_daily_papers >> $log_file 2>&1"
  local cron_line="$expr $cron_cmd"
  local tmp
  tmp="$(mktemp)"
  crontab -l > "$tmp" 2>/dev/null || true
  if grep -Fq "$cron_cmd" "$tmp"; then
    grep -Fv "$cron_cmd" "$tmp" > "$tmp.next" || true
    mv "$tmp.next" "$tmp"
    printf "\n%s\n" "$cron_line" >> "$tmp"
  else
    printf "\n%s\n" "$cron_line" >> "$tmp"
  fi
  crontab "$tmp"
  rm -f "$tmp"
}

write_nginx_snippet() {
  cat > "$PROJECT_DIR/deploy/nginx_${DOMAIN}.conf" <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    root $FRONTEND_DIR/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:$BACKEND_PORT/api/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }

    location /admin/ {
        proxy_pass http://127.0.0.1:$BACKEND_PORT/admin/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }

    location /static/ {
        alias $PROJECT_DIR/staticfiles/;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
}

setup_systemd() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "当前不是 root，跳过 systemd 服务配置。"
    return
  fi
  cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=ResearcherRadar Django backend
After=network.target

[Service]
Type=simple
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=/bin/bash $PROJECT_DIR/scripts/run_backend.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true

  release_backend_port

  systemctl start "$SERVICE_NAME"
  sleep 2
  if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "$SERVICE_NAME 启动失败，最近日志如下：" >&2
    journalctl -u "$SERVICE_NAME" -n 30 --no-pager >&2 || true
    return 1
  fi
  echo "$SERVICE_NAME 已启动，后端监听端口：$BACKEND_PORT"
}

backup_database() {
  if [ -f "$PROJECT_DIR/data/db.sqlite3" ]; then
    mkdir -p "$PROJECT_DIR/data/backups"
    cp "$PROJECT_DIR/data/db.sqlite3" "$PROJECT_DIR/data/backups/db.sqlite3.$(date +%F_%H%M%S)"
  fi
}

print_summary() {
  cat <<EOF

部署完成。

项目目录：
$PROJECT_DIR

持久化数据：
$PROJECT_DIR/data/db.sqlite3
$PROJECT_DIR/.env
$PROJECT_DIR/logs/

前端目录：
$FRONTEND_DIR/dist

后端地址：
http://127.0.0.1:$BACKEND_PORT

访问地址：
$PUBLIC_SCHEME://$DOMAIN

Nginx 配置参考：
$PROJECT_DIR/deploy/nginx_${DOMAIN}.conf

如果使用宝塔 Python 项目，启动命令：
bash $PROJECT_DIR/scripts/run_backend.sh

EOF
}

main() {
  echo "科研雷达（ResearcherRadar）部署脚本"
  echo "代码来源：$SOURCE_DIR"
  echo
  echo "请选择部署模式："
  echo "1) 首次部署"
  echo "2) 增量部署"
  while true; do
    read -r -p "输入 1 或 2: " mode
    case "$mode" in
      1|2) break ;;
      *) echo "请选择首次部署或增量部署。" >&2 ;;
    esac
  done

  local project_default="${PROJECT_DIR:-$DEFAULT_PROJECT_DIR}"
  if [ "$mode" = "2" ] && [ -z "${PROJECT_DIR:-}" ] && [ ! -f "$DEFAULT_PROJECT_DIR/.env" ] && [ -f "/www/wwwroot/researcher-radar/.env" ]; then
    project_default="/www/wwwroot/researcher-radar"
  fi
  PROJECT_DIR="$(prompt '服务器项目目录' "$project_default")"
  if [ "$mode" = "2" ] && [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "未发现现有部署配置 $PROJECT_DIR/.env；请先选择首次部署。" >&2
    exit 1
  fi
  BACKEND_DIR="$PROJECT_DIR/backend"
  FRONTEND_DIR="$PROJECT_DIR/frontend"
  load_existing_env "$PROJECT_DIR/.env"

  DOMAIN="$(prompt '域名' "${DOMAIN:-$DEFAULT_DOMAIN}")"
  if [ -z "$DOMAIN" ]; then
    echo "域名不能为空。" >&2
    exit 1
  fi
  SERVER_IP="$(prompt '服务器公网 IP，可留空' "${SERVER_IP:-}")"
  PUBLIC_SCHEME="$(prompt '访问协议 http/https' "${PUBLIC_SCHEME:-$DEFAULT_SCHEME}")"
  BACKEND_PORT="$(prompt '后端本机端口' "${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}")"
  if ! [[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] || [ "$BACKEND_PORT" -lt 1 ] || [ "$BACKEND_PORT" -gt 65535 ]; then
    echo "后端本机端口无效：$BACKEND_PORT（必须为 1-65535 的整数）" >&2
    exit 1
  fi
  local service_default="$DEFAULT_SERVICE_NAME"
  if [ "$mode" = "2" ] && [ "$PROJECT_DIR" = "/www/wwwroot/researcher-radar" ]; then
    service_default="literature_daily"
  fi
  SERVICE_NAME="$(prompt 'systemd 服务名' "${SERVICE_NAME:-$service_default}")"

  DJANGO_ALLOWED_HOSTS_VALUE="$DOMAIN,127.0.0.1,localhost"
  if [ -n "$SERVER_IP" ]; then
    DJANGO_ALLOWED_HOSTS_VALUE="$DJANGO_ALLOWED_HOSTS_VALUE,$SERVER_IP"
  fi

  PIP_MIRROR=""
  NPM_REGISTRY=""
  if yes_no '是否使用国内镜像安装依赖' 'Y'; then
    PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
    NPM_REGISTRY="https://registry.npmmirror.com"
  fi

  if [ "$mode" = "1" ] && yes_no '是否自动安装系统依赖' 'Y'; then
    install_system_deps
  fi

  sync_code
  prepare_runtime_dirs
  write_env
  backup_database
  setup_backend
  build_frontend
  write_nginx_snippet

  if [ "$mode" = "1" ] && yes_no '是否创建或重置管理员账号' 'Y'; then
    admin_username="$(prompt '管理员用户名' 'admin')"
    admin_email="$(prompt '管理员邮箱，可留空' '')"
    while true; do
      read -r -s -p "管理员密码: " admin_password
      echo
      read -r -s -p "再次输入管理员密码: " admin_password_confirm
      echo
      if [ -n "$admin_password" ] && [ "$admin_password" = "$admin_password_confirm" ]; then
        break
      fi
      echo "两次密码不一致或为空，请重新输入。"
    done
    create_or_update_admin "$admin_username" "$admin_email" "$admin_password"
  fi

  if yes_no '是否安装或更新每日抓取 cron' "$([ "$mode" = "1" ] && echo Y || echo N)"; then
    cron_input="$(prompt 'cron 时间；可填 8、08:30 或完整表达式' "$DEFAULT_CRON_EXPR")"
    install_cron_job "$cron_input"
  fi

  if yes_no '是否创建/重启 systemd 后端服务（选择 Y 将强制释放所选后端端口）' 'Y'; then
    setup_systemd
  else
    echo "已跳过 systemd 服务配置；未停止进程，也未释放端口 $BACKEND_PORT。"
  fi

  print_summary
}

main "$@"
