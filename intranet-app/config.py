"""内网应用配置。可用环境变量覆盖。"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("AIHUB_DB", str(BASE_DIR / "aihub.db"))

# GitHub 仓库（爬虫数据所在仓库），格式 "用户名/仓库名"
SYNC_REPO = os.environ.get("AIHUB_REPO", "YOUR_NAME/ai-daily-hub")
SYNC_BRANCH = os.environ.get("AIHUB_BRANCH", "main")


def sync_base_urls():
    """数据文件下载地址，按优先级排序，失败自动降级。

    1. raw.githubusercontent.com（最适合程序拉取）
    2. GitHub Pages 镜像（需在仓库开启 Pages，分支根目录部署）
    """
    owner, repo = SYNC_REPO.split("/", 1)
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/{SYNC_BRANCH}",
        f"https://{owner}.github.io/{repo}",
    ]
