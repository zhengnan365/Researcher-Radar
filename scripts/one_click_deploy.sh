#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
DEPLOY_DIR="$PROJECT_DIR/deploy"

DEFAULT_DOMAIN=""
DEFAULT_BACKEND_PORT="8000"
DEFAULT_CRON_EXPR="0 8 * * *"

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

prompt_yes_no() {
  local label="$1"
  local default_value="${2:-Y}"
  local value
  read -r -p "$label [$default_value]: " value
  value="${value:-$default_value}"
  case "${value,,}" in
    y|yes|是|true|1) return 0 ;;
    *) return 1 ;;
  esac
}

require_dir() {
  local dir="$1"
  local name="$2"
  if [ ! -d "$dir" ]; then
    echo "缺少 $name 目录：$dir" >&2
    exit 1
  fi
}

install_system_deps() {
  if ! command -v apt >/dev/null 2>&1; then
    echo "未检测到 apt，跳过系统依赖安装。请手动安装 python3 python3-venv python3-pip nodejs npm。"
    return
  fi
  if [ "$(id -u)" -ne 0 ]; then
    echo "当前不是 root，跳过 apt 安装。请用 root 执行或手动安装系统依赖。"
    return
  fi
  apt update
  apt install -y python3 python3-venv python3-pip nodejs npm curl cron
}

init_backend() {
  local pip_mirror="$1"
  cd "$BACKEND_DIR"
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  if [ -n "$pip_mirror" ]; then
    pip install -r requirements.txt -i "$pip_mirror"
  else
    pip install -r requirements.txt
  fi

  export DJANGO_DEBUG=false
  export DJANGO_ALLOWED_HOSTS="$DJANGO_ALLOWED_HOSTS_VALUE"
  export DJANGO_CORS_ALLOWED_ORIGINS="$DJANGO_CORS_ALLOWED_ORIGINS_VALUE"
  export DJANGO_CSRF_TRUSTED_ORIGINS="$DJANGO_CSRF_TRUSTED_ORIGINS_VALUE"
  export DJANGO_STATIC_ROOT="$BACKEND_DIR/staticfiles"

  mkdir -p "$BACKEND_DIR/logs"
  python manage.py migrate
  python manage.py collectstatic --noinput
  python manage.py check
}

build_frontend() {
  local npm_registry="$1"
  cd "$FRONTEND_DIR"
  cat > .env.production <<EOF
VITE_API_BASE_URL=$PUBLIC_SCHEME://$DOMAIN/api
VITE_ADMIN_URL=$PUBLIC_SCHEME://$DOMAIN/admin/
EOF
  if [ -n "$npm_registry" ]; then
    npm config set registry "$npm_registry"
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

install_cron_job() {
  local cron_expr="$1"
  local log_file="$BACKEND_DIR/logs/literature_daily.log"
  local cron_cmd="cd $BACKEND_DIR && $BACKEND_DIR/.venv/bin/python manage.py fetch_daily_papers >> $log_file 2>&1"
  local cron_line="$cron_expr $cron_cmd"
  local current_cron
  current_cron="$(mktemp)"
  crontab -l > "$current_cron" 2>/dev/null || true
  if grep -Fq "$cron_cmd" "$current_cron"; then
    echo "cron 已存在，跳过重复添加。"
  else
    printf "\n%s\n" "$cron_line" >> "$current_cron"
    crontab "$current_cron"
    echo "已添加 cron：$cron_line"
  fi
  rm -f "$current_cron"
}

write_nginx_snippet() {
  mkdir -p "$DEPLOY_DIR"
  cat > "$DEPLOY_DIR/nginx_${DOMAIN}.conf" <<EOF
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
        alias $BACKEND_DIR/staticfiles/;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
}

write_env_summary() {
  mkdir -p "$DEPLOY_DIR"
  cat > "$DEPLOY_DIR/runtime.env" <<EOF
DOMAIN=$DOMAIN
SERVER_IP=$SERVER_IP
PROJECT_DIR=$PROJECT_DIR
BACKEND_DIR=$BACKEND_DIR
FRONTEND_DIR=$FRONTEND_DIR
PUBLIC_SCHEME=$PUBLIC_SCHEME
BACKEND_PORT=$BACKEND_PORT
DJANGO_ALLOWED_HOSTS=$DJANGO_ALLOWED_HOSTS_VALUE
DJANGO_CORS_ALLOWED_ORIGINS=$DJANGO_CORS_ALLOWED_ORIGINS_VALUE
DJANGO_CSRF_TRUSTED_ORIGINS=$DJANGO_CSRF_TRUSTED_ORIGINS_VALUE
EOF
}

print_final_commands() {
  cat <<EOF

部署初始化完成。

1. 宝塔站点目录：
$FRONTEND_DIR/dist

2. 宝塔 Python 项目启动命令：
DOMAIN=$DOMAIN SERVER_IP=$SERVER_IP PUBLIC_SCHEME=$PUBLIC_SCHEME BACKEND_PORT=$BACKEND_PORT bash $PROJECT_DIR/scripts/run_backend.sh

3. Nginx 配置片段已生成：
$DEPLOY_DIR/nginx_${DOMAIN}.conf

如果宝塔已能访问站点，只需要确认 /api/ 和 /admin/ 已反向代理到：
http://127.0.0.1:$BACKEND_PORT

4. 验收地址：
$PUBLIC_SCHEME://$DOMAIN
$PUBLIC_SCHEME://$DOMAIN/api/auth/me/
$PUBLIC_SCHEME://$DOMAIN/admin/

EOF
}

main() {
  require_dir "$BACKEND_DIR" "backend"
  require_dir "$FRONTEND_DIR" "frontend"

  echo "科研雷达（ResearcherRadar）一键部署"
  echo "当前项目目录：$PROJECT_DIR"
  echo

  DOMAIN="$(prompt '请输入域名' "$DEFAULT_DOMAIN")"
  if [ -z "$DOMAIN" ]; then
    echo "域名不能为空。" >&2
    exit 1
  fi
  SERVER_IP="$(prompt '请输入服务器公网 IP，可留空' '')"
  while true; do
    PUBLIC_SCHEME="$(prompt '请输入访问协议 http 或 https' 'https')"
    if [ "$PUBLIC_SCHEME" = "http" ] || [ "$PUBLIC_SCHEME" = "https" ]; then
      break
    fi
    echo "访问协议只能输入 http 或 https。"
  done
  BACKEND_PORT="$(prompt '请输入后端本机端口' "$DEFAULT_BACKEND_PORT")"

  DJANGO_ALLOWED_HOSTS_VALUE="$DOMAIN,127.0.0.1,localhost"
  if [ -n "$SERVER_IP" ]; then
    DJANGO_ALLOWED_HOSTS_VALUE="$DJANGO_ALLOWED_HOSTS_VALUE,$SERVER_IP"
  fi
  DJANGO_CORS_ALLOWED_ORIGINS_VALUE="$PUBLIC_SCHEME://$DOMAIN"
  DJANGO_CSRF_TRUSTED_ORIGINS_VALUE="$PUBLIC_SCHEME://$DOMAIN"

  pip_mirror=""
  npm_registry=""
  if prompt_yes_no '是否使用国内镜像安装依赖' 'Y'; then
    pip_mirror="https://pypi.tuna.tsinghua.edu.cn/simple"
    npm_registry="https://registry.npmmirror.com"
  fi

  if prompt_yes_no '是否自动安装系统依赖 python3/node/npm/cron' 'Y'; then
    install_system_deps
  fi

  echo
  echo "开始初始化后端..."
  init_backend "$pip_mirror"

  echo
  echo "开始构建前端..."
  build_frontend "$npm_registry"

  if prompt_yes_no '是否创建或重置管理员账号' 'Y'; then
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

  if prompt_yes_no '是否安装每日 RSS 抓取 cron 任务' 'Y'; then
    cron_expr="$(prompt '请输入 cron 时间表达式' "$DEFAULT_CRON_EXPR")"
    install_cron_job "$cron_expr"
  fi

  write_nginx_snippet
  write_env_summary
  chmod +x "$PROJECT_DIR/scripts/run_backend.sh" "$PROJECT_DIR/scripts/install_cron.sh" "$PROJECT_DIR/scripts/check_zotero.sh" 2>/dev/null || true
  print_final_commands
}

main "$@"
