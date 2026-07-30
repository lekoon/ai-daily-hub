# AIHOT 内网日报镜像

每天自动抓取 [aihot.virxact.com](https://aihot.virxact.com/daily) 的日报 / 周报 / 月报
（含每条新闻全文），数据以 JSON 形式存在本仓库，供公司内网网站同步展示。

## 数据流

```
aihot.virxact.com
    │  每天 09:00（北京时间）GitHub Actions 抓取
    ▼
本仓库 data/ 目录（JSON）
    │  每天 09:30 内网服务器从 raw.githubusercontent.com 拉取
    ▼
内网 Flask 网站（intranet-app/）
```

## 目录结构

```
crawler/            爬虫（GitHub Actions 每天运行）
  crawl.py          主脚本：python crawl.py [--date YYYY-MM-DD] [--backfill-daily N]
  parse.py          页面解析（日报/周报/月报/详情页 Markdown 导出）
data/               抓取产出的 JSON（index.json 为清单）
intranet-app/       内网 Flask 网站
  sync.py           数据同步（cron 每天 09:30 执行）
  app.py            Web 应用
.github/workflows/  定时抓取工作流
```

## 部署步骤

### 1. GitHub 侧（家中 / 外网）

1. 把本仓库 push 到 GitHub（仓库需为 public，否则 raw 下载需要 token）
2. 仓库 Actions 页面手动触发一次「每日抓取 AIHOT 日报」验证；之后每天
   北京时间 09:00 自动运行（GitHub 定时任务可能延迟几分钟，属正常现象）
3. 可选：仓库 Settings → Pages → 选择 main 分支根目录部署，
   这样 `https://<用户名>.github.io/<仓库>/data/...` 可作为内网同步的备用源

### 2. 内网侧（公司服务器）

```bash
# 1. 拷贝 intranet-app/ 到内网服务器，安装依赖
pip install -r requirements.txt

# 2. 配置仓库地址
export AIHUB_REPO="你的GitHub用户名/仓库名"

# 3. 首次同步
python sync.py

# 4. 启动网站（生产）
waitress-serve --host 0.0.0.0 --port 8000 app:app

# 5. 配置每天 09:30 自动同步（crontab -e）
30 9 * * * cd /path/to/intranet-app && AIHUB_REPO="你的GitHub用户名/仓库名" /usr/bin/python3 sync.py >> sync.log 2>&1
```

同步源优先级：`raw.githubusercontent.com` → `<用户名>.github.io`（需开启 Pages）。
也可用 `POST /sync?token=xxx`（设置环境变量 `SYNC_TOKEN` 后）手动触发同步。

## 注意事项

- 解析依赖目标站当前 HTML 结构，若对方改版需更新 `crawler/parse.py`
  （GitHub Actions 失败会有邮件通知）
- 爬虫已限速（详情页 1 秒/条），请勿调小
- `data/` 会随时间增长，每个 JSON 仅几 KB，一年约几十 MB，无需特别处理
