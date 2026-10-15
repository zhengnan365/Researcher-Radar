# 首次部署与增量部署

本文档说明“科研雷达（ResearcherRadar）”在宝塔服务器上的安全部署流程。核心原则：

```text
代码可以覆盖，运行数据不能覆盖。
```

新部署默认将运行数据保存在：

```text
/www/wwwroot/researcher-radar/.env
/www/wwwroot/researcher-radar/data/db.sqlite3
/www/wwwroot/researcher-radar/logs/
```

上传新版本时，部署脚本会自动排除这些目录和文件。

已有服务器若部署在 `/www/wwwroot/researcher-radar`，增量更新时继续使用原目录和原服务名；无需为了项目改名而移动 `.env` 或数据库。本文后续的路径和服务名示例均针对新部署，旧部署应替换为实际值。

## 1. 本地生成部署包

在本地项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_deploy_package.ps1
```

默认生成：

```text
C:\path\to\researcher_radar_deploy_YYYYMMDD.zip
```

部署包不会包含：

```text
.git/
backend/.venv/
frontend/node_modules/
frontend/dist/
backend/db.sqlite3
backend/logs/
data/
logs/
.env
*.log
```

## 2. 上传到服务器

将压缩包上传到服务器，例如：

```text
/www/wwwroot/researcher_radar_deploy_YYYYMMDD.zip
```

## 3. 解压到临时目录

不要直接解压覆盖正式目录。

```bash
rm -rf /tmp/researcher_radar_release
mkdir -p /tmp/researcher_radar_release
unzip /www/wwwroot/researcher_radar_deploy_YYYYMMDD.zip -d /tmp/researcher_radar_release
```

## 4. 运行部署脚本

```bash
bash /tmp/researcher_radar_release/deploy.sh
```

脚本会让你选择：

```text
1) 首次部署
2) 增量部署
```

## 5. 首次部署

首次部署建议选择 `1`。

脚本会要求选择部署模式，首次部署选择 `1` 并按提示设置管理员用户名与密码；系统不会预置可登录账号。下方的 `radar.example.com` 和 `203.0.113.10` 是文档占位值，请替换为自己的域名和服务器 IP。

脚本会自动完成：

- 创建项目目录；
- 同步代码；
- 创建持久化数据目录；
- 创建 `.env`；
- 安装 Python 依赖；
- 执行数据库迁移；
- 收集 Django 静态文件；
- 构建前端；
- 创建或重置管理员账号；
- 安装 cron 定时抓取任务；
- 创建或重启 systemd 后端服务；
- 生成 Nginx 配置参考文件。

首次部署和增量部署都会询问是否创建/重启 systemd 后端服务。选择 `Y` 表示授权脚本释放刚才填写的后端本机端口：脚本先停止同名服务，对占用进程发送 `TERM` 并等待最多 10 秒，仍未退出时发送 `KILL`，确认端口空闲后再启动服务。选择 `N` 时不会停止进程、释放端口或改动 systemd。

常用输入：

```text
服务器项目目录：/www/wwwroot/researcher-radar
域名：radar.example.com
服务器公网 IP：203.0.113.10
访问协议：https
后端本机端口：8000
systemd 服务名：researcher-radar
```

cron 时间支持三种输入：

```text
8         # 每天 08:00
08:30     # 每天 08:30
0 8 * * * # 标准 cron 表达式
```

## 6. 增量部署

GitHub 仓库地址为 `zhengnan365/Researcher-Radar`。使用 Git 检出的服务器需将 `origin` 更新为 `git@github.com:zhengnan365/Researcher-Radar.git`（若原本使用 HTTPS，则使用相应 HTTPS 地址）。

**2026 年 10 月历史清理后的一次性更新：**旧检出与新的 `main` 没有共同提交，`git pull --ff-only` 会失败。`/www/wwwroot` 是项目的上级目录，不能直接在其中运行下面的命令。先找出服务器实际使用的项目目录：

```bash
find /www/wwwroot -maxdepth 3 -name .git -print
```

如果找到例如 `/www/wwwroot/researcher-radar/.git`，先进入该目录并确认 Git 根目录和本地改动。其他目录请替换为实际路径：

```bash
cd /www/wwwroot/researcher-radar || exit 1
git rev-parse --show-toplevel
git status --short
```

确认输出的目录正确，并备份需要保留的代码改动后，再在**同一目录**执行：

```bash
git remote set-url origin git@github.com:zhengnan365/Researcher-Radar.git
git fetch origin main
git reset --hard origin/main
bash scripts/deploy_package.sh
```

若没有找到 `.git`，说明服务器可能使用 ZIP 部署包；不要执行 `git reset`，按本指南第 2–4 节上传新版部署包，并在向导中选择 `2) 增量部署`，填写现有项目目录。若 `git status --short` 显示需要保留的代码改动，请先单独备份这些文件，再执行 `reset`。旧目录无需改名。`.env`、`data/db.sqlite3`、日志和虚拟环境都在 Git 跟踪范围之外，部署脚本继续按增量模式 `2` 运行，不会重置账号密码。完成这次更新后，后续可恢复使用 `git pull --ff-only`。

后续更新建议选择 `2`。

增量部署沿用现有管理员账号和密码，不会提示重新设置；也不会覆盖已有 `.env` 和数据库。

增量部署会：

- 备份当前数据库到 `data/backups/`；
- 只同步代码；
- 保留 `.env`、数据库、日志、虚拟环境、node_modules；
- 安装或更新后端依赖；
- 执行数据库迁移；
- 重新构建前端；
- 可选更新 cron；
- 可选重启 systemd 服务。

选择重启 systemd 时会自动释放所选后端端口，避免旧 Gunicorn、手工启动进程或宝塔旧 Python 项目占用端口导致新服务启动失败。不要让宝塔 Python 项目和 systemd 长期同时管理同一个后端。

增量部署不会覆盖项目目录中的：

```text
/www/wwwroot/researcher-radar/data/db.sqlite3
/www/wwwroot/researcher-radar/.env
/www/wwwroot/researcher-radar/logs/
```

## 7. 宝塔 Nginx 配置

脚本会生成：

```text
/www/wwwroot/researcher-radar/deploy/nginx_radar.example.com.conf
```

如果宝塔站点已能访问前端，只需要确认：

- 网站目录指向：`/www/wwwroot/researcher-radar/frontend/dist`
- `/api/` 反向代理到：`http://127.0.0.1:8000/api/`
- `/admin/` 反向代理到：`http://127.0.0.1:8000/admin/`
- `/static/` 指向：`/www/wwwroot/researcher-radar/staticfiles/`

## 8. 常用维护命令

查看服务状态：

```bash
systemctl status researcher-radar
```

重启后端：

```bash
systemctl restart researcher-radar
```

查看后端日志：

```bash
journalctl -u researcher-radar -f
```

手动抓取：

```bash
cd /www/wwwroot/researcher-radar/backend
set -a && . /www/wwwroot/researcher-radar/.env && set +a
.venv/bin/python manage.py fetch_daily_papers
```

手动迁移：

```bash
cd /www/wwwroot/researcher-radar/backend
set -a && . /www/wwwroot/researcher-radar/.env && set +a
.venv/bin/python manage.py migrate
```
