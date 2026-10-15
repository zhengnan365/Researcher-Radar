# 科研雷达（ResearcherRadar）技术手册

项目概览见 [README.md](README.md)。本文保留完整的功能、配置、部署和运维说明。

科研雷达（ResearcherRadar）用于自动追踪指定期刊 RSS 和研究关键词下的最新文献信息，完成 DOI / 元数据 / 摘要补全、去重入库、关键词匹配、研究方向归类、每日文献日报生成，并提供 Vue 网页端浏览、筛选、收藏、摘要更新、Zotero 文献库同步与导入功能。

新部署默认使用 `/www/wwwroot/researcher-radar` 和 `researcher-radar.service`。已有部署可以继续使用原目录和服务名，无需搬迁数据库；Django 包名 `literature_backend` 属于程序内部标识，保持不变。

当前主系统位于 `backend/` 和 `frontend/`。早期脚本版原型已清理，部署和日常使用均以 Django + Vue 系统为准。

> 安全提示：仓库只保存程序、迁移、示例配置和部署脚本。不要提交 `.env`、SQLite 数据库、日志、Zotero Access Key、配置导出 JSON 或包含真实密码的文件。公开发布前应确认历史中也不存在已使用过的密钥。

## 快速导航

- 本地开发：见[安装步骤](#安装步骤)和[启动方式](#启动方式)。
- 页面操作：见[功能使用指南](#功能使用指南)。
- GitHub / 宝塔部署：见[通过-git-clone-部署到宝塔](#通过-git-clone-部署到宝塔)。
- 首次部署与增量更新：见 [docs/DEPLOY_FIRST_INCREMENTAL.md](docs/DEPLOY_FIRST_INCREMENTAL.md)。
- 完整宝塔配置：见 [docs/DEPLOY_BAOTA.md](docs/DEPLOY_BAOTA.md)。

## 主要功能

- RSS 源管理：新增、编辑、删除、启用/停用、测试 RSS 地址。
- OpenAlex 期刊补抓：源可选 RSS、OpenAlex 或两者组合；按 ISSN 查最近文献，复用现有去重与评分流程。主源失败时先尝试 Crossref，必要时再尝试已授权的 Elsevier ScienceDirect 期刊接口。
- 文献抓取：抓取启用的 RSS 源，解析标题、作者、期刊、发布日期、链接、DOI、RSS 摘要。
- 元数据补全：优先通过 DOI 查询 Crossref，缺 DOI 时可按题名搜索 Crossref。
- 摘要补全：抓取时先使用 RSS 和 Crossref 元数据，再对缺失摘要做一次短时 OpenAlex 查询；Crossref / OpenAlex 连接失败时短暂跳过重复查询，避免阻塞整轮抓取。文献列表的“更新摘要”任务依次尝试 Crossref、已授权的 Elsevier、OpenAlex、Semantic Scholar、PubMed，并在 DOI 查不到时按题名搜索。
- 后台摘要更新：文献列表中可按所选文献或当前日期后台更新缺失摘要，支持页面切换后恢复任务状态。
- 文献去重：优先 DOI，其次 URL / 标题归一化，避免 RSS 重复条目反复入库。
- 关键词追踪：维护关键词表，抓取后自动匹配文献。
- 相关性校准：英文关键词按完整词匹配，支持同义词、排除词和已有文献重新评分。
- 研究方向归类：关键词可绑定研究方向，文献可自动关联多个方向。
- 推荐评分：仅标题、摘要和 RSS Keywords 中的关键词命中提供相关性证据；匹配方向和多字段命中提供受限奖励。
- 科研兴趣模型：方向保留中文名并可填写英文科研标签、研究相关度和关注优先级；前者参与方向加分，后者用于展示排序。关键词沿用现有 1–5 权重。抓取筛选和推荐评分共用标题、摘要、RSS Keywords 的完整词匹配。
- 日报生成：生成 `DailyReport` 数据记录，按推荐分数和展示阈值生成 Markdown 与 HTML 内容。
- 文献列表：按日期、研究方向、关键词、期刊、收藏状态、Zotero 导入状态、推荐等级、搜索词筛选。
- AI 速读：在文献详情页按需生成，仅依据标题和原始摘要，保留原文摘要与生成模型信息。
- 日历视图：按日期显示当天文献数量。
- 收藏：文献可在列表中标记收藏并筛选查看。
- AI 与 Zotero 设置：在同一页面分别配置 AI 服务和 Zotero User ID / Group ID / Access Key。
- Zotero 文献库：读取并缓存 Zotero Web API 中的 Collections 和 Items，支持增量同步、全量校准。
- Zotero 导入：从文献列表导入单篇或批量文献到 Zotero，按 DOI / 标题去重，支持推荐或手动选择 Collection。
- Zotero Collection 新建：在文献库页创建文件夹，并同步到 Zotero 服务器。
- 配置迁移：在系统管理中一键导出/导入研究方向、关键词、RSS 源、评分规则、Zotero Key 和 AI API 配置。
- 评分解释与后台重评：文献详情可展开逐项贡献；评分设置页支持后台重新计算全部推荐分，显示进度并刷新已有日报。
- 重点推荐降级词：在评分规则中按行维护明显跨领域的英文标题词组。命中后该文献保留原始关键词贡献，但不进入重点推荐；更改后需重新评分。
- 抓取日志：记录每个 RSS 源的抓取结果、新增数量、重复数量和错误详情。
- 登录保护：Django 用户 + DRF Token 认证；未登录不能访问页面或业务 API。
- 用户管理：超级管理员可在网页端新增、编辑、禁用用户，也可进入 Django Admin。
- Django Admin：管理核心数据表、任务状态和 Zotero 缓存。

未实现或不推荐的功能：

- 不直接爬取 Google / ResearchGate 摘要，原因是反爬、登录、版权和稳定性风险较高。
- 未接入 Celery，当前后台任务使用 Django 进程内线程，适合轻量部署；生产高并发可扩展为 Celery / Redis。
- 后台任务使用数据库锁防止多 worker 重复启动，并识别执行进程退出后的中断任务。服务重启仍会中断正在执行的任务，需要手动重新启动。
- 收藏 RSS 导出入口已从前端移除，当前推荐使用 Pyzotero 直接导入 Zotero。

## 系统架构

```text
project-root/
├── backend/                         # Django + DRF 后端
│   ├── manage.py
│   ├── requirements.txt
│   ├── literature_backend/           # Django 项目配置
│   └── papers/
│       ├── models.py                 # 数据模型
│       ├── serializers.py            # DRF 序列化
│       ├── views.py                  # API 入口
│       ├── filters.py                # 查询过滤逻辑
│       ├── admin.py                  # Django Admin 配置
│       ├── services/                 # 核心业务服务
│       │   ├── rss_fetcher.py        # RSS 抓取与入库
│       │   ├── metadata_enricher.py  # Crossref 元数据补全
│       │   ├── abstract_enricher.py  # 摘要补全
│       │   ├── keyword_matcher.py    # 关键词和方向匹配
│       │   ├── relevance_scorer.py   # 推荐评分、等级和命中明细
│       │   ├── report_generator.py   # 日报生成
│       │   ├── fetch_task_runner.py  # 后台抓取任务
│       │   ├── abstract_task_runner.py # 后台摘要更新任务
│       │   └── zotero_api.py         # Pyzotero 同步、缓存、导入
│       └── management/commands/      # 命令行任务
├── frontend/                         # Vite + Vue 3 + Element Plus 前端
│   ├── package.json
│   └── src/
│       ├── api/                      # Axios API 封装
│       ├── router/                   # 前端路由
│       ├── views/                    # 页面
│       ├── components/               # 公共组件
│       └── styles/                   # 主题和动画样式
├── .env.example                      # 环境变量示例
├── README.md                         # GitHub 项目首页
└── TECHNICAL_GUIDE.md                # 完整技术手册
```

## 环境要求

- Python：3.11+。
- Node.js：建议 18+ 或 20+。
- 包管理：`pip` 与 `npm`。
- 数据库：SQLite；本地开发默认文件为 `backend/db.sqlite3`，生产部署建议使用 `/www/wwwroot/researcher-radar/data/db.sqlite3`。
- 浏览器：Chrome / Edge / Firefox 现代版本。
- Zotero：如需本地客户端打开功能，请安装 Zotero Desktop；如需同步和导入，请配置 Zotero Web API Key。

## 安装步骤

### 1. 获取项目

```bash
cd /path/to/workspace
git clone https://github.com/zhengnan365/Researcher-Radar.git researcher-radar
cd researcher-radar
```

私有仓库推荐为服务器配置 GitHub Deploy Key，然后使用 SSH 地址：

```bash
git clone git@github.com:zhengnan365/Researcher-Radar.git researcher-radar
```

如果使用 GitHub Desktop，本地选择 `File -> Add local repository` 打开本项目；首次上传使用 `Publish repository`，并建议勾选 `Keep this code private`。

如果是直接上传文件到服务器，确保保留 `backend/`、`frontend/`、`scripts/`、`README.md`、`TECHNICAL_GUIDE.md` 和 `.env.example`。推荐使用部署包脚本，避免覆盖服务器数据库和运行配置。

生成部署包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_deploy_package.ps1
```

服务器端首次部署或增量部署：

服务器可直接使用 `git clone` 在线获取代码；首次部署、已有 ZIP 部署在线更新的完整命令见[在线 Git 部署](docs/DEPLOY_FIRST_INCREMENTAL.md#在线-git-部署推荐)。以下是 ZIP 部署命令：

```bash
rm -rf /tmp/researcher_radar_release
mkdir -p /tmp/researcher_radar_release
unzip /www/wwwroot/researcher_radar_deploy_YYYYMMDD.zip -d /tmp/researcher_radar_release
bash /tmp/researcher_radar_release/deploy.sh
```

部署脚本会让用户选择：

```text
1) 首次部署
2) 增量部署
```

首次部署和增量部署都会询问：

```text
是否创建/重启 systemd 后端服务（选择 Y 将强制释放所选后端端口） [Y]:
```

- 选择 `Y`：停止所选 systemd 服务，显示后端端口的占用进程，先尝试正常终止，必要时强制终止，然后重新创建并启动服务。
- 选择 `N`：不停止现有进程、不释放端口，也不修改或重启 systemd 服务。
- 同一台服务器不要同时使用宝塔 Python 项目和 systemd 管理同一个后端端口；生产环境推荐只保留 `researcher-radar.service`。

详细说明见：[docs/DEPLOY_FIRST_INCREMENTAL.md](docs/DEPLOY_FIRST_INCREMENTAL.md)。

旧版脚本仍保留作兼容。如果你已经把完整代码解压到了正式目录，也可以执行：

```bash
cd /www/wwwroot/researcher-radar
bash scripts/one_click_deploy.sh
```

但日常推荐使用 `deploy.sh`，因为它会先解压到临时目录，再安全同步代码，不会覆盖数据库和 `.env`。

宝塔 Python 项目推荐使用部署脚本最后输出的启动命令，例如：

```bash
DOMAIN=your-domain.com SERVER_IP=203.0.113.10 PUBLIC_SCHEME=https BACKEND_PORT=8000 bash /www/wwwroot/researcher-radar/scripts/run_backend.sh
```

### 2. 安装后端依赖

Windows PowerShell：

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Linux / 宝塔服务器：

```bash
cd /www/wwwroot/researcher-radar/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

Windows PowerShell 可使用：

```powershell
npm.cmd install
```

## 配置说明

可参考项目根目录 `.env.example`。Django 当前通过系统环境变量读取配置；生产环境建议在宝塔 Python 项目的环境变量、systemd、Supervisor 或启动脚本中设置。

后端常用环境变量：

```text
DJANGO_SECRET_KEY=请替换为随机密钥
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com,127.0.0.1
DJANGO_CORS_ALLOWED_ORIGINS=https://your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com
DJANGO_SQLITE_PATH=/www/wwwroot/researcher-radar/data/db.sqlite3
DJANGO_STATIC_ROOT=/www/wwwroot/researcher-radar/staticfiles
LITERATURE_HTTP_TIMEOUT=10
ZOTERO_USER_ID=
ZOTERO_API_KEY=
```

前端构建环境变量：

```text
VITE_API_BASE_URL=https://your-domain.com/api
VITE_ADMIN_URL=https://your-domain.com/admin/
```

Zotero 配置也可以不写环境变量，直接在前端 `系统管理 > AI 与 Zotero 设置` 中保存。数据库中的网页配置优先用于 Zotero 功能；配置导出文件包含明文 Key，必须按敏感文件管理。

## 启动方式

### 开发环境

启动后端：

```bash
cd backend
python manage.py runserver 127.0.0.1:8000
```

启动前端：

```bash
cd frontend
npm run dev
```

访问：

```text
前端：http://127.0.0.1:5173
后端 API：http://127.0.0.1:8000/api/
Django Admin：http://127.0.0.1:8000/admin/
```

### 生产构建

```bash
cd frontend
npm run build
```

构建产物在：

```text
frontend/dist/
```

### 后端生产启动示例

```bash
cd /www/wwwroot/researcher-radar/backend
source .venv/bin/activate
gunicorn literature_backend.wsgi:application --bind 127.0.0.1:8000 --workers 2
```

### 创建登录账号

系统页面和业务 API 默认都需要登录。首次运行迁移后创建超级管理员：

```bash
cd backend
python manage.py createsuperuser
```

登录页使用该用户名和密码。超级管理员可以打开 `系统管理 -> 用户管理` 创建普通用户，也可以访问 `/admin/`。认证采用 DRF Token：登录成功后前端将 Token 保存在浏览器本地存储，请不要在公共电脑上保持登录；退出登录会删除服务端 Token 并清除前端状态。

同一来源地址和用户名连续登录失败 8 次后，登录会限制 15 分钟；计数保存在数据库中，对多个 Gunicorn worker 生效。公网部署必须使用 HTTPS，并设置独立的 `DJANGO_SECRET_KEY`、明确的 `DJANGO_ALLOWED_HOSTS` 和可信反向代理。后台抓取、重评、摘要更新目前仍运行在 Web 进程内；进程退出后任务会标为失败，需要手动重试。

## 通过 Git Clone 部署到宝塔

### 首次部署

服务器准备好 Git、Python、Node.js、Nginx 后执行：

```bash
cd /www/wwwroot
git clone git@github.com:zhengnan365/Researcher-Radar.git researcher-radar
cd researcher-radar
bash scripts/deploy_package.sh
```

根据提示选择 `1) 首次部署`，依次填写域名、服务器 IP、后端端口、管理员账号和 cron 时间。脚本会创建独立数据目录、后端虚拟环境、前端构建、数据库迁移、静态文件、Nginx 示例配置，以及可选的 systemd 和 cron。

### 后续增量更新

本地完成修改并推送 GitHub 后，在服务器执行：

```bash
cd /www/wwwroot/researcher-radar
git remote set-url origin git@github.com:zhengnan365/Researcher-Radar.git
git pull --ff-only
bash scripts/deploy_package.sh
```

仓库历史曾清理重写。旧服务器检出第一次更新前，请先进入**现有项目目录**，按[首次与增量部署指南](docs/DEPLOY_FIRST_INCREMENTAL.md#6-增量部署)执行一次 `git fetch` 和 `git reset --hard origin/main`；此后可继续使用上面的 `git pull --ff-only`。如果服务器原本使用 HTTPS 拉取，则将 origin 设为 `https://github.com/zhengnan365/Researcher-Radar.git`。选择 `2) 增量部署`；若旧目录名仍为 `literature_daily`，填写原目录和原服务名。脚本会保留：

- `/www/wwwroot/researcher-radar/.env`；
- `/www/wwwroot/researcher-radar/data/db.sqlite3`；
- `/www/wwwroot/researcher-radar/logs/`；
- 已生成的生产运行配置。

更新前建议备份：

```bash
cp /www/wwwroot/researcher-radar/data/db.sqlite3 \
  /www/wwwroot/researcher-radar/data/db.sqlite3.$(date +%Y%m%d_%H%M%S).bak
```

私有仓库需先把服务器公钥添加到 GitHub 仓库的 `Settings -> Deploy keys`。服务器生成只读 Deploy Key：

```bash
ssh-keygen -t ed25519 -C "researcher-radar-server"
cat ~/.ssh/id_ed25519.pub
ssh -T git@github.com
```

## 带域名服务器部署说明（宝塔）

完整可执行部署教程见：

```text
docs/DEPLOY_BAOTA.md
```

部署辅助脚本：

```text
scripts/make_deploy_package.ps1  # 本地生成干净部署 zip
scripts/deploy_package.sh        # 服务器端首次/增量部署入口
scripts/one_click_deploy.sh      # 早期服务器交互式一键部署
scripts/run_backend.sh           # 宝塔 Python 项目后端启动脚本
scripts/server_setup.sh          # 服务器初始化后端
scripts/build_frontend.sh        # 服务器构建前端
scripts/create_admin.sh          # 交互式创建或重置管理员
scripts/install_cron.sh          # 安装每日抓取 cron
```

推荐使用“前端静态站点 + Django 后端反向代理”的方式。

1. 上传项目到：

```text
/www/wwwroot/researcher-radar/
```

2. 后端安装依赖并初始化数据库：

```bash
cd /www/wwwroot/researcher-radar/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

3. 宝塔中新建 Python 项目：

```text
项目目录：/www/wwwroot/researcher-radar/backend
启动命令：/www/wwwroot/researcher-radar/backend/.venv/bin/gunicorn literature_backend.wsgi:application --bind 127.0.0.1:8000 --workers 2
```

4. 前端配置生产 API：

在 `frontend/.env.production` 中写入：

```text
VITE_API_BASE_URL=https://你的域名/api
VITE_ADMIN_URL=https://你的域名/admin/
```

然后构建：

```bash
cd /www/wwwroot/researcher-radar/frontend
npm install
npm run build
```

5. 宝塔中新建静态站点，网站根目录指向：

```text
/www/wwwroot/researcher-radar/frontend/dist
```

6. Nginx 反向代理示例：

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
```

7. 生产环境变量至少设置：

```text
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=安全随机字符串
DJANGO_ALLOWED_HOSTS=你的域名,www.你的域名,127.0.0.1
DJANGO_CORS_ALLOWED_ORIGINS=https://你的域名
DJANGO_CSRF_TRUSTED_ORIGINS=https://你的域名
```

## 定时任务

每日 08:00 抓取 RSS 并生成日报：

```cron
0 8 * * * cd /www/wwwroot/researcher-radar/backend && /www/wwwroot/researcher-radar/backend/.venv/bin/python manage.py fetch_daily_papers >> /www/wwwroot/researcher-radar/logs/researcher-radar.log 2>&1
```

手动抓取：

```bash
cd backend
python manage.py fetch_daily_papers
```

重新生成指定日期日报：

```bash
cd backend
python manage.py regenerate_daily_report report_date=2026-07-05
```

重新评分已有文献：

```bash
cd backend
python manage.py rescore_papers
python manage.py rescore_papers --days 7
python manage.py rescore_papers --journal "Applied Energy"
python manage.py rescore_papers --paper-id 123
```

回填已有文献元数据和摘要：

```bash
cd backend
python manage.py backfill_paper_metadata --only-empty-abstract --limit 100
```

## 功能使用指南

### 1. 登录与账号

1. 打开前端地址，未登录时会自动进入 `/login`。
2. 使用 `createsuperuser` 创建的账号登录。
3. 超级管理员可在 `系统管理 -> 用户管理` 新增、编辑、启用或停用账号。
4. 使用顶部或系统入口的退出功能结束登录；Token 失效后，前端收到 `401/403` 会自动返回登录页。

### 2. 配置追踪范围

建议按以下顺序配置：

1. 在 `系统管理 -> 研究方向管理` 新增方向，设置中英文名称、研究相关度和关注优先级。
2. 在 `系统管理 -> 关键词管理` 选择研究方向并添加关键词，可单条或批量粘贴。批量输入可写 `关键词 | 权重`，例如 `energy hub | 4`；只写关键词时使用上方统一权重（1–5）。普通关键词仍支持换行、逗号和分号分隔。研究方向批量添加页也提供可复制的粘贴模板。
3. 在 `系统管理 -> RSS 源管理` 添加文献源名称、期刊和 RSS URL；使用 OpenAlex 时填写 ISSN。
4. 点击 RSS 源的“测试”，确认地址可访问并能解析条目。
5. 在 `系统管理 -> 推荐评分规则` 调整字段倍率、日报阈值和展示数量；保存时可启动最近 7 天、30 天或全部文献的后台重评。

批量导入示例位于 [docs/import_examples](docs/import_examples)。系统管理中的“配置导入导出”可迁移方向、关键词、RSS 源、评分规则、Zotero Key 和 AI API 配置，但导出 JSON 含敏感 Key，不能提交 Git。

### 3. 抓取与日报首页

1. 首页显示当日新增、文献总量、收藏数量、待补摘要，以及来源、方向、关键词和近 7 日趋势。
2. 点击“自动抓取”后，后端创建后台任务；前端轮询任务状态，切换页面后返回仍会恢复“正在抓取”状态。
3. RSS 条目经过 DOI / URL / 标题去重后入库，再补元数据、匹配关键词和方向、计算推荐分数并生成当日日报。
4. “入库与订阅状态”用于查看 DOI/摘要覆盖率、Zotero 导入量和最近 RSS 源抓取结果；抓取失败时可从首页进入抓取日志查看原因。
5. “今日重点文献”只显示达到当前重点推荐阈值的文献；没有符合条件的文章时显示空状态。
6. 定时抓取由服务器 cron 负责，页面按钮主要用于首次测试或临时补抓。

### 4. 文献列表

1. 默认显示当天未隐藏、未软删除的文献；可通过右侧日历切换日期。
2. 支持标题/作者/DOI搜索，以及方向、关键词、期刊、收藏、Zotero 状态、推荐等级和最低分筛选。
3. 文献卡片展示推荐分数、推荐等级、命中关键词、命中字段、匹配方向和简要评分原因；长摘要默认收起，可在卡片内展开。
4. 点击标题查看完整摘要和最近评分时间。
5. 收藏用于建立人工关注清单；它不等同于 Zotero 已导入状态。
6. 卡片区分入库日期与期刊日期。ScienceDirect RSS 可能提供未来卷期的期刊日期，此时显示“期刊预标日期”，原始日期不会自动改写。
7. “更新摘要”的范围：
   - 已勾选文献时，只更新所选文献中摘要为空的条目；
   - 未勾选时，更新当前所选日期中摘要为空的条目。

### 5. Zotero 文献库与导入

1. 在 `系统管理 -> AI 与 Zotero 设置` 保存 Library 类型、User/Group ID 和 Access Key；Key 需要对应文献库的读写权限。
2. 打开 `Zotero 文献库`，页面会先显示本地缓存。
3. 左侧“同步”按钮按 Zotero 版本增量更新 Items 和 Collections；“全量校准”位于旁边的更多菜单中，以 Zotero 服务器为准重建本地缓存。同步状态和上次成功时间显示在文件夹栏底部。
   页面左侧持续显示同步中、成功或失败状态及上次成功时间；失败时可查看原因并重试。
   中间列表逐批读取本地缓存，可按标题、作者、DOI 搜索，并按年份、条目类型筛选；筛选作用于当前选中的文件夹（含子文件夹）。列表读取失败时会保留已显示的条目并提供重试入口。
4. 点击 My Library 旁的加号可新建文件夹，选择父级后会直接创建到 Zotero 服务器并更新本地树。同步完成后会保留仍存在的文件夹选择和展开状态。
5. 文献列表中的“导入 Zotero”会先按 DOI、无 DOI 时按规范化标题去重：
   - 已存在且已在目标 Collection：直接标记已存在；
   - 已存在但不在目标 Collection：只补充 Collection，不重复创建；
   - 不存在：在 Zotero 服务器创建并写入目标 Collection，然后更新本地缓存。
6. 批量导入支持“每篇自动推荐分组”或“统一导入指定分组”；推荐依据研究方向和关键词。
7. 本地 Zotero 缓存只用于快速展示，删除校准以 Zotero 服务器为准。

### 6. 低分条目与不相关

- `系统管理 -> 低分条目管理` 默认展示低于低分阈值的文献。
- 文献列表卡片点击“不相关”后，该篇文献记为 0 分，并从文献列表、低分条目、日报及常规统计中隐藏；数据库记录和去重键仍保留，后续 RSS 抓取不会重复入库。
- 自动评为低分的文献仍在低分条目管理中，可以重新评分。
- 低分条目管理保留批量软删除、恢复和重新评分。
- 系统默认不提供物理删除，降低误删风险。

### 7. 日志、用户与配置备份

- `抓取日志`：查看每个 RSS 源抓取、新入库、已存在和异常详情。
- `用户管理`：仅超级管理员可用；普通用户可以登录和使用文献功能，但不能管理用户或导入导出敏感配置。
- `配置导入导出`：适合服务器迁移，不包含文献数据库、用户账号、日志或 Zotero Item 缓存。
- Django Admin 位于 `/admin/`，用于必要的底层数据和任务状态维护，日常操作优先使用 Vue 页面。

### 8. 调整推荐与扩充期刊覆盖

1. 在 `系统管理 -> 关键词管理` 为同一概念填写逐行同义词；把明确不需要的主题设为排除词。英文关键词按完整词匹配。撤稿、勘误类标题会被降为低相关；期刊名本身不会形成推荐分数。修改后可在 `系统管理 -> 推荐评分规则` 重评最近 30 天或全部文献。
2. 在 `系统管理 -> RSS 源管理` 可将单个期刊设为 `RSS`、`OpenAlex` 或两者组合。OpenAlex 模式需填写该期刊 ISSN；两者组合也需保留有效 RSS URL。可先用“测试”确认来源，再启用抓取。已有来源不会自动切换模式。OpenAlex 默认回看 14 天，最多请求 3 页，可用 `OPENALEX_LOOKBACK_DAYS` 和 `OPENALEX_MAX_PAGES` 调整。建议在后端环境变量配置免费的 `OPENALEX_API_KEY` 和联系邮箱 `OPENALEX_MAILTO`；`OPENALEX_MIN_INTERVAL_SECONDS` 默认让同一后端进程的 OpenAlex 请求至少间隔 0.25 秒。遇到 429 时该进程会按 `Retry-After` 或额度重置提示暂停请求，稍后再运行；额度用尽无法靠立即重试解决。缺摘要文献仍可从文献列表按需更新，且部分出版商本身不向这些服务提供摘要。
   - RSS 或 OpenAlex 本轮失败时，系统自动尝试 Crossref 期刊备用抓取；正常抓取时不额外请求。ScienceDirect RSS URL 可自动识别 ISSN，其他 RSS 源需在编辑页填写期刊 ISSN。Crossref 只读取最近索引且近期发表的期刊论文，每期刊最多 3 页；可通过 `CROSSREF_JOURNAL_FALLBACK_ENABLED`、`CROSSREF_FALLBACK_LOOKBACK_DAYS`、`CROSSREF_FALLBACK_PUBLICATION_DAYS`、`CROSSREF_FALLBACK_MAX_PAGES` 调整。建议配置 `CROSSREF_MAILTO`。主来源失败而备用成功会标记“部分完成”，抓取日志分别保留结果。
   - 若主来源失败，而且 Crossref 未返回文献、失败或只完成部分查询，配置了 `ELSEVIER_API_KEY` 时还会尝试 ScienceDirect Search V2 按期刊名补抓。该接口使用最近加载日期，结果会再次核对期刊名，并沿用现有去重与评分；每期刊默认最多 2 页，可通过 `ELSEVIER_FALLBACK_LOOKBACK_DAYS`、`ELSEVIER_FALLBACK_MAX_PAGES` 调整。401/403 权限错误和 429 限流会暂停后续请求。普通 Elsevier Key 不保证有 ScienceDirect API 权限；未配置 Key 时不会调用。
   - 摘要更新已使用 Semantic Scholar 兜底，配置 `SEMANTIC_SCHOLAR_API_KEY` 可使用个人额度。已授权的 Elsevier Key 也可对 Elsevier DOI 请求 `META_ABS` 摘要；未配置、无权限或返回限流时会跳过，不会阻断其他来源。以上 Key 均为服务器环境变量，不包含在页面配置导出中。
3. 文献卡片的“不相关”会将该篇文献记为 0 分，并从常规页面与低分条目中隐藏；记录仍保留用于 RSS 去重。重新评分不会取消该标记。这是单篇反馈，不会自动修改全局关键词。
4. 在 `系统管理 -> AI 与 Zotero 设置` 的“AI 速读”区可填写 DeepSeek API Key（默认基础地址 `https://api.deepseek.com`、模型 `deepseek-flash`），也可使用其他兼容 Chat Completions 的服务。API Key 加密保存在数据库中，设置接口只返回“是否已配置”；现有 `LITERATURE_AI_API_KEY`、`LITERATURE_AI_MODEL`、`LITERATURE_AI_BASE_URL` 环境变量仍可作为尚未保存页面配置时的回退方案。AI 速读只有手动点击时才发送单篇文献的标题和原始摘要；没有原始摘要的文献不能生成。原文摘要与 AI 结果分别保存，重新生成会覆盖旧的 AI 结果。更换 `DJANGO_SECRET_KEY` 后，需重新保存 API Key。

建议先逐篇标记一小组“不相关”文献，再比较调整关键词前后的命中率与误报率。

## 入库规则与处理流程说明

系统采用“RSS / OpenAlex 抓取 + DOI/URL/标题去重 + 入库后相关性评分 + 日报按分数排序展示”的处理模式。

### 入库规则

- RSS 抓取阶段默认不因为未命中关键词而丢弃文章。
- 只要文章通过 DOI、URL 或标题归一化去重判断，就允许进入正式文献库。
- `RSS_INGEST_ONLY_MATCHED=false` 是推荐配置；如改为 `true`，系统会恢复为只入库命中关键词或研究方向的条目。
- 重复文章不会再次创建记录，但会补全缺失字段并重新评分。

### 相关性评分

每篇文章入库后会调用统一的 `matching_engine.py` 匹配标题、摘要和 RSS Keywords，再由 `relevance_scorer.py` 计算分数。关键词权重乘标题 3、摘要 2、RSS Keywords 1；所属方向按权重获得 1/3/5/8/10 分名义奖励，命中两个或三个字段获得 5/10 分名义奖励。两项奖励合计最多为关键词分的 25%，总分最多 100。英文词按完整词匹配，重叠词优先计较长术语；排除词命中则归零。期刊名和中英文方向名均不单独提供相关性证据。

评分结果会保存到 `Paper`：

- `recommend_score`：推荐总分；
- `recommend_level`：推荐等级，包含 `key`、`normal`、`weak`、`low`；
- `matched_fields`：关键词命中的字段；
- `score_detail`：分数来源明细；
- `scored_at`：最近评分时间。

默认展示阈值：

- `SCORE_WEAK_THRESHOLD=8`：低分条目阈值，低于 8 分的文献默认进入低分条目管理；
- `REPORT_MIN_RECOMMEND_SCORE=18`：日报最低展示分，`18-29` 分可进入日报候选；
- 重点推荐阈值默认 30 分，可在“推荐评分规则”页面调整；
- `8-17` 分达不到日报最低分，默认不进入日报。

上述值是默认配置，不是硬编码。`.env` 提供默认值，若在“系统管理 > 推荐评分规则”页面保存过配置，则数据库中的 `SystemSetting` 优先级更高。

若旧版批量粘贴曾把 `关键词 | 权重` 整串保存为关键词名称，可先备份数据库，再运行 `python manage.py repair_keyword_weights` 预览修复清单，确认后运行 `python manage.py repair_keyword_weights --apply`。该命令只处理这种异常格式，保留关键词所属方向及其它信息；修复后需重新计算全部推荐分。

### 日报生成规则

日报基于正式文献库生成，不直接基于原始 RSS 数据生成。

生成流程：

```text
指定日期新入库文章
-> 排除已归档和已软删除文章
-> 按 REPORT_MIN_RECOMMEND_SCORE 过滤
-> 默认排除 weak / low 条目
-> 按推荐分数、发布时间、期刊、标题排序
-> 生成 Markdown 与 HTML 日报
```

可通过环境变量控制：

- `REPORT_MIN_RECOMMEND_SCORE`：日报最低展示分数；
- `REPORT_SHOW_WEAK_RELATED`：是否展示弱相关和低相关条目；
- `REPORT_MAX_PAPERS`：日报最多展示文献数量。

### 评分分布统计

系统提供评分分布统计，用于辅助判断阈值是否合理。默认区间为：

- `0-9`：统计区间；其中低于 8 分的文献默认进入低分条目管理；
- `10-14`：统计区间，默认不进入日报；
- `15-29`：统计区间；其中 18 分及以上可进入日报候选；
- `30+`：今日重点推荐文献。

统计默认排除已归档和已软删除文献。

展示位置：

- “系统管理 > 推荐评分规则”页面可查看全部文献或最近 30 天文献的评分分布，并可选择是否包含软删除文献；
- “文献列表”页面的“当日提要”下方会显示当前所选日期的评分分布，切换日期后同步更新；
- 当日没有文献时显示空状态。

评分分布接口：

```text
GET /api/settings/scoring/distribution/
GET /api/settings/scoring/distribution/?range=30d
GET /api/settings/scoring/distribution/?date=2026-07-06
GET /api/settings/scoring/distribution/?include_archived=true&include_deleted=true
```

返回内容包括总量、各分数段数量、占比和区间含义。

### 重新评分

当关键词、研究方向或评分环境变量改变后，不需要重新抓取 RSS，可以直接重新评分已有文献：

```bash
cd backend
python manage.py rescore_papers
python manage.py rescore_papers --days 30
python manage.py rescore_papers --source "Applied Energy"
```

重新评分会更新推荐分数、推荐等级、命中关键词、命中字段、研究方向和评分明细。网页端还可在评分规则页点击“重新计算全部推荐分”，任务后台运行并显示进度；完成后刷新已有日报。人工标记“不相关”的文章保持 0 分。

### 低分条目管理

系统管理中提供“低分条目管理”页面，用于集中处理推荐分数较低、推荐等级较低或未进入日报候选的文献。

默认筛选条件：

- `recommend_score < low_score_threshold`；
- 已标记“不相关”的文献不会显示；
- `is_soft_deleted=false`。
- 默认只查询入库时间最近 90 天；切换“全部历史”可查看尚未清理的旧条目。

页面支持：

- 按推荐分数、推荐等级、期刊、RSS 来源、发布时间范围、软删除状态、日报候选状态筛选；
- 查看标题、期刊、发布时间、推荐分数、推荐等级、命中字段、分数明细、入库时间；
- 当前页多选和当前页全选；
- 批量软删除；
- 批量恢复；
- 批量重新评分；
- 单篇详情、软删除、恢复和重新评分。

软删除和恢复区别：

- 软删除：文章仍保留在数据库中，但不进入默认列表、日报和常规统计，适合临时移除。
- 恢复：清除软删除状态，文章重新回到默认文献列表，并可重新参与日报筛选。
- 物理删除：当前页面默认不提供，避免误删文献数据。

日报生成会排除标记“不相关”及 `is_soft_deleted=true` 的文章。

每次完成定时或手动抓取后，系统按“低相关内容保留天数”（默认 90 天）清理到期的低分或人工标记“不相关”文献。收藏或已导入 Zotero 的文献受到保护。清理后保留原始标题、DOI、URL 和索引去重键，清空摘要、作者、AI 摘要、评分详情等内容；精简记录不在列表中显示，也不会被后续抓取或重评分还原。DOI 和规范化标题检索键均有数据库索引，去重涵盖低分、软删除和精简记录。

### 推荐评分规则配置

系统管理中提供“推荐评分规则”页面。`.env` 仍作为默认配置来源，但一旦在页面保存配置，数据库中的 `SystemSetting` 会优先生效。

可配置的评分项包括：

- 标题、摘要和 RSS Keywords 的关键词倍率；
- 每增加一个命中字段的名义奖励；
- 附加奖励相对关键词分的比例上限，最高 25%；
- 单篇文章最高分；
- 日报最低展示分数；
- 今日重点文献最低分数；
- 一般推荐最低分数；
- 低分条目阈值。
- 低相关内容保留天数（30-3650 天，默认 90 天）；随配置导入导出保存。

可配置的展示项包括：

- 日报默认排序方式；
- 是否按推荐分数降序；
- 是否按研究方向分组；
- 每日最多展示文献数量；
- 今日重点文献最多展示数量；
- 是否展示分数明细；
- 是否展示弱相关文献。

保存评分规则后，前端会提示是否立即重新评分，可选：

- 只保存，不重新评分；
- 重新评分最近 7 天；
- 重新评分最近 30 天；
- 重新评分全部文献。

配置合法性约束：

- 分数不能为负数；
- 今日重点文献阈值应高于日报最低展示分数；
- 低分条目阈值不应高于日报最低展示分数；
- 多字段奖励每增加一个字段最多 5 分，附加奖励比例最多 25%；
- 每日展示数量不能小于 1。

日报排序和筛选规则在下一次生成日报时生效；评分项变更需要重新评分后才能影响已有文献的推荐分数。

### 前端评分展示

每日推荐、文献日报和普通文献列表中的文献卡片会显示：

- 推荐分数，例如 `32 分`；
- 推荐等级，例如“重点推荐”“一般推荐”“弱相关”“低相关”；
- 命中关键词，列表中默认只展示前 3 到 5 个；
- 命中字段，例如“标题”“摘要”“RSS 关键词”“研究方向”“期刊”；
- 匹配研究方向；
- 简要推荐原因。

文献详情弹窗会展示推荐分数、等级、命中字段、关键词、方向及最近评分时间；完整分数明细可在低分条目管理页查看。标记“不相关”的文献不再出现在这些页面中。

### 配置导入导出

配置包包含：

- 研究方向及启用状态；
- 关键词、权重和研究方向关联；
- 文献源名称、抓取方式、RSS URL、OpenAlex ISSN、期刊和启用状态；
- 数据库运行时推荐评分与日报展示规则；
- Zotero 文献库类型、User ID、Group ID 和完整 Access Key。
- AI 服务类型、接口基础地址、模型和完整 API Key（已配置时）。

配置包不包含文献、日报、抓取日志、后台任务、用户账号、Zotero Collections/Items 缓存，也不备份服务器环境变量中的部署参数（如 Django 密钥、数据库路径、OpenAlex、Semantic Scholar 和 Elsevier API Key）。导入采用安全的合并模式：研究方向按名称、关键词按内容、RSS 源按 URL 更新或新增，不删除当前系统中未出现在配置包里的项目；RSS 最近抓取状态和累计抓取数量会保留。导入在数据库事务中执行，任一项校验失败时会整体回滚。

注意：导出的 JSON 包含明文 Zotero Access Key 和已配置的 AI API Key。请将其作为敏感备份保存，不要上传到公开仓库、网盘公开链接或发送给无关人员。登录后可使用导入导出；网页登录账号和密码不在配置包中。旧版 v1、v2 配置包仍可导入。

## 主要 API

除登录接口外，业务 API 默认要求请求头携带 `Authorization: Token <token>`。超级管理员专用接口还会检查 Django `is_staff` / `is_superuser` 权限。

### 认证与用户

- `POST /api/auth/login/`：用户名密码登录，返回 Token 和用户信息。
- `POST /api/auth/logout/`：注销当前 Token。
- `GET /api/auth/me/`：检查 Token 和当前用户状态。
- `GET/POST /api/users/`：用户列表和创建用户，仅管理员。
- `GET/PUT/DELETE /api/users/{id}/`：用户维护，仅管理员。

### 文献

- `GET /api/papers/`：文献列表。
- `GET /api/papers/{id}/`：文献详情。
- `POST /api/papers/{id}/favorite/`：收藏文献。
- `DELETE /api/papers/{id}/favorite/`：取消收藏。
- `GET /api/papers/date_counts/`：按日期统计文献数量。
- `POST /api/papers/update-abstracts/`：创建后台摘要更新任务。
- `GET /api/papers/low-score/`：低分条目列表。
- `POST /api/papers/bulk-soft-delete/`：批量软删除文献。
- `POST /api/papers/bulk-restore/`：批量恢复文献。
- `POST /api/papers/bulk-rescore/`：批量重新评分文献。
- `POST /api/papers/{id}/mark-irrelevant/`：将文献记为不相关并隐藏，数据库记录保留用于去重。
- `POST /api/papers/{id}/soft-delete/`：单篇软删除。
- `POST /api/papers/{id}/restore/`：单篇恢复。
- `POST /api/papers/{id}/rescore/`：单篇重新评分。

常用查询参数：

```text
date=2026-07-06
keyword=hydrogen 或 keyword=<id>
direction=新能源 或 direction=<id>
journal=Applied Energy
source=<source_id>
favorite=true
zotero_imported=true
abstract_missing=true
search=HVDC
page=1
page_size=20
```

### RSS 源、关键词、研究方向

- `GET/POST /api/sources/`
- `GET/PUT/DELETE /api/sources/{id}/`
- `POST /api/sources/{id}/test/`
- `GET/POST /api/keywords/`
- `GET/PUT/DELETE /api/keywords/{id}/`
- `GET/POST /api/directions/`
- `GET/PUT/DELETE /api/directions/{id}/`

### 日报与日志

- `GET /api/reports/`
- `GET /api/reports/{id}/`
- `POST /api/reports/regenerate/`
- `GET /api/fetch_logs/`

### 后台任务

- `POST /api/tasks/fetch-daily/`：启动后台抓取任务。
- `GET /api/tasks/fetch-daily/active/`：查询当前抓取任务。
- `GET /api/tasks/fetch-daily/{task_id}/`：查询抓取任务详情。
- `GET /api/tasks/abstract-update/active/`：查询当前摘要更新任务。
- `GET /api/tasks/abstract-update/{task_id}/`：查询摘要更新任务详情。

### Zotero

- `GET/POST /api/zotero/config/`：读取或保存 Zotero 配置。
- `POST /api/zotero/library/`：读取本地缓存或触发 Zotero 文献库同步。
- `GET /api/zotero/items/{item_key}/`：按需读取缓存条目的完整详情。
- `GET /api/zotero/sync-status/`：读取快速同步或全量校准的后台任务状态。
- `POST /api/zotero/create-collection/`：创建 Zotero Collection。
- `POST /api/zotero/suggest-collection/`：推荐文献导入 Collection。
- `POST /api/zotero/import-paper/`：导入文献到 Zotero。
- `POST /api/zotero/sync/`：旧版同步接口，保留兼容，前端主流程不依赖。

### 系统配置

- `GET /api/settings/scoring/`：读取当前评分和日报展示规则。
- `POST /api/settings/scoring/`：保存评分和日报展示规则，可通过 `rescore_scope` 启动后台重新评分。
- `POST /api/settings/scoring/rescore/`：独立启动后台重新评分；`GET /api/settings/scoring/rescore/active/` 和 `GET /api/settings/scoring/rescore/{task_id}/` 查询进度。
- `POST /api/settings/scoring/reset/`：恢复默认评分和日报展示规则。
- `GET /api/settings/scoring/distribution/`：获取评分分布统计，支持 `range=all|30d`、`date=YYYY-MM-DD`、`include_archived=true|false`、`include_deleted=true|false`。
- `GET /api/settings/config/export/`：登录后下载完整系统配置 JSON，响应包含完整 Zotero Access Key 和已配置的 AI API Key。
- `POST /api/settings/config/import/`：登录后合并导入系统配置；校验失败时整体回滚。

## 数据库说明

默认使用 SQLite。本地开发不设置 `DJANGO_SQLITE_PATH` 时使用 `backend/db.sqlite3`；生产环境建议设置为 `/www/wwwroot/researcher-radar/data/db.sqlite3`，避免增量部署覆盖数据库。

主要数据表：

- `ResearchDirection`：研究方向，包含中英文名称、研究相关度、关注优先级和启用状态。
- `Keyword`：关键词，包含关键词、权重、绑定方向、同义词和排除词标记。
- `RssSource`：文献源，包含 RSS URL、OpenAlex ISSN、期刊和最近抓取状态。
- `Paper`：文献记录，包含标题、作者、期刊、发布日期、DOI、URL、摘要、收藏状态、Zotero 导入状态、推荐分数、推荐等级、命中字段、评分明细、归档状态、软删除状态、去重键。
- `DailyReport`：日报记录，包含日期、标题、HTML、Markdown、文献数量。
- `FetchLog`：每个 RSS 源的抓取日志。
- `FetchTask`：后台自动抓取任务状态。
- `AbstractUpdateTask`：后台摘要更新任务状态。
- `ZoteroConfig`：Zotero 连接配置。
- `ZoteroCollection`：Zotero Collection 本地缓存。
- `ZoteroItem`：Zotero 条目本地缓存。
- `ZoteroSyncState`：Zotero 同步版本和时间。
- `SystemSetting`：运行时系统配置，当前用于保存推荐评分规则和日报展示规则。

数据库迁移：

```bash
cd backend
python manage.py makemigrations
python manage.py migrate
```

## 常见问题

### 1. 前端无法访问后端

检查：

- 后端是否运行在 `http://127.0.0.1:8000`。
- 前端 `VITE_API_BASE_URL` 是否正确。
- 生产环境 `DJANGO_CORS_ALLOWED_ORIGINS` 是否包含前端域名。

### 2. 登录后返回 500 或无法保持登录

依次检查：

```bash
cd /www/wwwroot/researcher-radar/backend
source .venv/bin/activate
python manage.py migrate
python manage.py check
systemctl restart researcher-radar
```

确认生产数据库文件和 `data/` 目录对后端运行用户可读写。前端请求应携带 `Authorization: Token ...`；如果浏览器保存了失效 Token，退出登录或清理站点本地存储后重新登录。

### 3. Django Admin 登录后 CSRF 报错

生产环境需要设置：

```text
DJANGO_CSRF_TRUSTED_ORIGINS=https://你的域名
```

### 4. Zotero 文献库读取失败

检查：

- 是否安装后端依赖：`pip install -r backend/requirements.txt`。
- `pyzotero` 是否安装。
- `系统管理 > AI 与 Zotero 设置` 中是否保存了 User ID 和 Access Key。
- Access Key 是否具备 library 读取和写入权限。

### 5. 点击自动抓取或更新摘要一直转圈

系统会在服务重启后自动将旧进程遗留的任务标记失败。可进入 Django Admin 查看：

- `FetchTask`
- `AbstractUpdateTask`

如仍异常，可重启后端服务并重新点击按钮。

### 6. 摘要仍然为空

不是所有数据库都会公开摘要。入库时优先保留 RSS 和 Crossref 提供的摘要；手动更新会依次尝试 Crossref、已授权的 Elsevier、OpenAlex、Semantic Scholar、PubMed，并在 DOI 查不到时用题名搜索。Google / ResearchGate 不作为自动抓取源。

### 7. RSS 抓取没有新增

如果某 RSS 源返回的前几十条都已存在，系统会提前停止检查该源，避免重复跑外部 API。这是正常的去重加速策略。

### 8. 宝塔部署后静态资源 404

执行：

```bash
cd backend
python manage.py collectstatic --noinput
```

并确认 Nginx `/static/` 指向项目根目录的 `staticfiles/`，与 `DJANGO_STATIC_ROOT` 保持一致。

## 交付状态

当前系统已经完成核心链路：

```text
RSS 源管理 -> RSS 抓取 -> DOI / 摘要补全 -> 去重入库 -> 关键词匹配 -> 研究方向归类
-> 日报生成 -> 网页浏览筛选 -> 收藏 / 摘要更新 -> Zotero 同步和导入
```

建议后续增强：

- 使用 Celery + Redis 替换进程内后台线程。
- 增加 RIS / BibTeX 导出。
- 增加更稳定的 DOI landing page 元数据兜底解析。
- 增加 LLM 智能综述模块。
