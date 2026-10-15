# 宝塔服务器部署教程

本文档记录“科研雷达（ResearcherRadar）”部署到宝塔面板服务器的标准流程。以下使用文档专用示例域名；部署时请替换为自己的域名和服务器地址：

```text
https://radar.example.com
```

服务器路径约定：

```text
/www/wwwroot/researcher-radar
```

`researcher-radar` 是新部署的默认目录名，不要求提前创建。已有服务器若使用 `/www/wwwroot/researcher-radar`，更新时继续填写该目录，不要仅为改名而搬动运行数据。其他目录也可在部署向导中指定；单独执行脚本时可用 `PROJECT_DIR` 覆盖：

```bash
PROJECT_DIR=/www/wwwroot/你的实际目录 bash scripts/server_setup.sh radar.example.com
PROJECT_DIR=/www/wwwroot/你的实际目录 bash scripts/build_frontend.sh radar.example.com
PROJECT_DIR=/www/wwwroot/你的实际目录 bash scripts/install_cron.sh
```

## 1. DNS 解析

在域名 DNS 控制台添加 A 记录：

```text
主机记录：radar
记录类型：A
记录值：203.0.113.10
```

注意：记录值只写 IP，不要写 `https://`。

验证：

```bash
ping radar.example.com
```

## 2. 上传部署包

如果服务器可以访问 GitHub，可直接 `git clone` 后部署；已有 ZIP 部署也可克隆到临时目录做增量更新。完整命令见[在线 Git 部署](DEPLOY_FIRST_INCREMENTAL.md#在线-git-部署推荐)。以下为 ZIP 部署方式。

本地推荐用脚本生成干净部署包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_deploy_package.ps1
```

生成：

```text
researcher_radar_deploy_YYYYMMDD.zip
```

上传到服务器后建议先解压到临时目录，不要直接覆盖正式项目目录：

```text
/tmp/researcher_radar_release
```

部署包不应包含：

```text
.git
backend/.venv
frontend/node_modules
frontend/dist
backend/db.sqlite3
data/
logs/
backend/logs
__pycache__
*.pyc
*.log
```

## 3. 一键首次部署 / 增量部署

推荐使用新的部署包脚本：

```bash
rm -rf /tmp/researcher_radar_release
mkdir -p /tmp/researcher_radar_release
unzip /www/wwwroot/researcher_radar_deploy_YYYYMMDD.zip -d /tmp/researcher_radar_release
bash /tmp/researcher_radar_release/deploy.sh
```

脚本会提示选择：

```text
1) 首次部署
2) 增量部署
```

正式运行数据会保存在：

```text
/www/wwwroot/researcher-radar/.env
/www/wwwroot/researcher-radar/data/db.sqlite3
/www/wwwroot/researcher-radar/logs/
```

增量部署会自动排除这些文件和目录，避免覆盖数据库。

无论首次还是增量部署，脚本最后都会询问：

```text
是否创建/重启 systemd 后端服务（选择 Y 将强制释放所选后端端口） [Y]:
```

选择 `Y` 后会停止同名服务并强制释放所选后端端口，再启动新的 systemd 服务；选择 `N` 则不触碰当前后端。若以前在宝塔“Python 项目”中启动过同一个 Django 后端，建议停用该项目，只保留 `researcher-radar.service`，防止宝塔守护进程再次抢占端口。

## 4. 旧版一键部署

如果已经将完整代码解压到正式目录，也可以执行旧版交互式一键部署脚本：

```bash
cd /www/wwwroot/researcher-radar
bash scripts/one_click_deploy.sh
```

脚本会提示输入：

```text
域名
服务器公网 IP
访问协议 http / https
后端本机端口
是否使用国内 pip / npm 镜像
是否安装系统依赖
是否创建或重置管理员账号
是否安装每日 RSS 抓取 cron
```

脚本完成后会生成：

```text
deploy/runtime.env
deploy/nginx_域名.conf
```

宝塔 Python 项目启动命令使用脚本最后输出的命令，格式类似：

```bash
DOMAIN=radar.example.com SERVER_IP=203.0.113.10 PUBLIC_SCHEME=https BACKEND_PORT=8000 bash /www/wwwroot/researcher-radar/scripts/run_backend.sh
```

## 4. 手动安装系统依赖

如果不使用一键脚本，Ubuntu 服务器执行：

```bash
apt update
apt install -y python3 python3-venv python3-pip nodejs npm
```

检查：

```bash
python3 --version
pip3 --version
node -v
npm -v
```

## 5. 手动初始化后端

可以用脚本：

```bash
cd /www/wwwroot/researcher-radar
bash scripts/server_setup.sh radar.example.com
```

等价手动命令：

```bash
cd /www/wwwroot/researcher-radar/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
mkdir -p logs
```

如果 pip 慢：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 6. 创建管理员账号

避免 `createsuperuser` 在中文终端中出现编码问题，推荐用脚本：

```bash
cd /www/wwwroot/researcher-radar
bash scripts/create_admin.sh admin 'you@example.com'
```

脚本会无回显提示输入并确认自定义密码。首次部署创建账号；增量部署不需要再次运行。

## 7. 构建前端

脚本方式：

```bash
cd /www/wwwroot/researcher-radar
bash scripts/build_frontend.sh radar.example.com
```

等价手动命令：

```bash
cd /www/wwwroot/researcher-radar/frontend
cat > .env.production <<'EOF'
VITE_API_BASE_URL=https://radar.example.com/api
VITE_ADMIN_URL=https://radar.example.com/admin/
EOF
npm install
npm run build
```

如果 npm 慢：

```bash
npm config set registry https://registry.npmmirror.com
npm install
```

## 8. 宝塔 Python 项目

宝塔面板中新建 Python 项目：

```text
项目目录：/www/wwwroot/researcher-radar/backend
启动文件：不使用固定启动文件，使用自定义启动命令
```

启动命令：

```bash
cd /www/wwwroot/researcher-radar/backend && DJANGO_DEBUG=false DJANGO_ALLOWED_HOSTS=radar.example.com,203.0.113.10,127.0.0.1 DJANGO_CORS_ALLOWED_ORIGINS=https://radar.example.com DJANGO_CSRF_TRUSTED_ORIGINS=https://radar.example.com DJANGO_STATIC_ROOT=/www/wwwroot/researcher-radar/staticfiles /www/wwwroot/researcher-radar/backend/.venv/bin/gunicorn literature_backend.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 300
```

如果宝塔支持环境变量，建议拆成：

```text
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=radar.example.com,203.0.113.10,127.0.0.1
DJANGO_CORS_ALLOWED_ORIGINS=https://radar.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://radar.example.com
DJANGO_STATIC_ROOT=/www/wwwroot/researcher-radar/staticfiles
```

然后启动命令简化为：

```bash
cd /www/wwwroot/researcher-radar/backend && /www/wwwroot/researcher-radar/backend/.venv/bin/gunicorn literature_backend.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 300
```

## 9. 宝塔网站与 Nginx

宝塔添加站点：

```text
域名：radar.example.com
网站目录：/www/wwwroot/researcher-radar/frontend/dist
类型：纯静态
```

进入站点设置：

```text
网站 -> radar.example.com -> 设置 -> 配置文件
```

在 HTTPS `server { ... }` 内加入：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /admin/ {
    proxy_pass http://127.0.0.1:8000/admin/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /static/ {
    alias /www/wwwroot/researcher-radar/staticfiles/;
}

location / {
    try_files $uri $uri/ /index.html;
}
```

检查并重载：

```bash
nginx -t
systemctl reload nginx
```

## 10. SSL

宝塔：

```text
网站 -> radar.example.com -> SSL -> Let's Encrypt
```

申请成功后开启强制 HTTPS。

## 11. 计划任务

安装 cron：

```bash
cd /www/wwwroot/researcher-radar
bash scripts/install_cron.sh
```

默认每天 08:00 执行：

```bash
cd /www/wwwroot/researcher-radar/backend && /www/wwwroot/researcher-radar/backend/.venv/bin/python manage.py fetch_daily_papers >> /www/wwwroot/researcher-radar/logs/researcher-radar.log 2>&1
```

宝塔计划任务也可以手动添加同一条命令。

## 12. 验收

前端：

```text
https://radar.example.com
```

API：

```bash
curl -I https://radar.example.com/api/auth/me/
```

后端本机：

```bash
curl http://127.0.0.1:8000/api/auth/me/
```

Django Admin：

```text
https://radar.example.com/admin/
```

## 13. 常见问题

### 前端能打开，但登录失败

检查 `/api/` 反向代理：

```bash
curl -I https://radar.example.com/api/auth/me/
```

如果不是后端响应，检查 Nginx `location /api/`。

### 502 Bad Gateway

检查后端 Gunicorn 是否运行：

```bash
curl http://127.0.0.1:8000/api/auth/me/
```

不通则看宝塔 Python 项目日志。

### createsuperuser 报 UnicodeDecodeError

使用：

```bash
bash scripts/create_admin.sh admin 'you@example.com'
```

### 前端请求 localhost

重新设置 `frontend/.env.production` 后构建：

```bash
bash scripts/build_frontend.sh radar.example.com
```

### Zotero 快速同步返回 500

先确认线上系统中“系统管理 -> Zotero Key 设置”已保存：

```text
文献库类型：个人文献库
User ID：Zotero API 页面显示的 Your user ID for use in API calls
Access Key：需要具备 library read 权限
```

然后在服务器执行：

```bash
cd /www/wwwroot/researcher-radar/backend
source .venv/bin/activate
python manage.py shell -c "from papers.models import ZoteroConfig; c=ZoteroConfig.get_active(); print(c.library_type if c else None, c.user_id if c else None, c.group_id if c else None, bool(c.api_key) if c else None)"
curl -I https://api.zotero.org/
python manage.py shell -c "from papers.services.zotero_api import read_zotero_library; print(read_zotero_library(max_items=3, refresh=True, full_sync=False).keys())"
```

判断方式：

```text
没有 api_key：线上 Zotero Key 没保存成功。
curl 不通：服务器无法访问 Zotero API，需要检查服务器网络或代理。
403/权限错误：Access Key 没有 Library Read 权限，或 User ID / Group ID 填错。
能在 shell 成功：重启宝塔 Python 项目，再刷新前端重试。
```
