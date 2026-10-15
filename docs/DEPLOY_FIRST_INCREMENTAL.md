# 部署与运行

只需选择一种获取代码的方式：**服务器直接 clone**，或**从 GitHub 下载 ZIP 后上传**。两种方式最后都运行同一个部署脚本。以下以 Ubuntu 服务器为例；命令中的路径按实际情况填写。

## 方式一：服务器直接 clone

### 首次部署

```bash
git clone https://github.com/zhengnan365/Researcher-Radar.git /www/wwwroot/researcher-radar &&
cd /www/wwwroot/researcher-radar &&
bash scripts/deploy_package.sh
```

向导选择 `1) 首次部署`，按提示填写项目目录、域名，并设置管理员账号和密码。选择启动 systemd 服务后，脚本会安装依赖、迁移数据库、构建前端并启动后端。系统没有默认账号密码。

### 后续更新

在**现有 Git 项目目录**运行：

```bash
cd /www/wwwroot/researcher-radar &&
git pull --ff-only &&
bash scripts/deploy_package.sh
```

向导选择 `2) 增量部署`。若项目原本位于 `/www/wwwroot/researcher-radar`，继续使用原目录和原服务名；增量部署保留 `.env`、数据库和管理员密码。

如果现有项目是上传 ZIP 安装的，没有 `.git`，不要在原目录执行 `git pull` 或直接 `clone` 覆盖。可以将新代码克隆到临时目录，再选择增量部署并填写**原项目目录**：

```bash
release_dir=$(mktemp -d /tmp/researcher-radar.XXXXXX) &&
git clone --depth 1 https://github.com/zhengnan365/Researcher-Radar.git "$release_dir" &&
cd "$release_dir" &&
bash scripts/deploy_package.sh
```

## 方式二：下载 ZIP 并上传

在 GitHub 仓库页面选择 **Code → Download ZIP**，将下载的 ZIP 上传到服务器 `/tmp/`。假设上传后的文件名是 `Researcher-Radar-main.zip`，运行：

```bash
release_dir=$(mktemp -d /tmp/researcher-radar.XXXXXX) &&
unzip /tmp/Researcher-Radar-main.zip -d "$release_dir" &&
cd "$release_dir"/*/ &&
bash scripts/deploy_package.sh
```

文件名不同则替换命令中的 ZIP 名称。首次安装选 `1`；更新现有系统选 `2` 并填写现有项目目录。不要将 ZIP 直接解压覆盖数据库目录。

## 确认运行

部署向导中选择创建或重启 systemd 服务后，检查状态：

```bash
systemctl status researcher-radar --no-pager
journalctl -u researcher-radar -n 50 --no-pager
```

若沿用旧服务名，将 `researcher-radar` 换成实际服务名，例如 `literature_daily`。前端构建文件位于项目目录的 `frontend/dist`；后端启动命令和服务名会在部署结束时显示。
