"""内网数据同步：从 GitHub 仓库拉取爬虫产出的 JSON，写入本地 SQLite。

每天 09:30 由 cron 执行：
    30 9 * * * cd /opt/aihub && /usr/bin/python3 sync.py >> sync.log 2>&1

也可手动执行：python sync.py [--full]
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

import db
from config import sync_base_urls

TIMEOUT = 20


def fetch_json(path):
    """按优先级尝试多个下载源，返回 (data, base_url)，全部失败返回 (None, None)。"""
    for base in sync_base_urls():
        url = f"{base}/{path}"
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.json(), base
            print(f"  [warn] {url} -> HTTP {resp.status_code}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  [warn] {url} 请求失败: {e}", file=sys.stderr)
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="忽略本地缓存，全量重新下载")
    ap.add_argument("--local-dir", metavar="DIR",
                    help="不走网络，直接从本地 data/ 目录导入（调试用）")
    args = ap.parse_args()

    db.init_db()
    started = datetime.now().isoformat(timespec="seconds")
    print(f"[{started}] 开始同步")

    local_dir = Path(args.local_dir).resolve() if args.local_dir else None

    def load_json(path):
        """返回 (data, source_desc)。"""
        if local_dir:
            p = local_dir / path
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8")), str(local_dir)
            return None, None
        return fetch_json(path)

    index, base = load_json("data/index.json")
    if index is None:
        print("无法获取 data/index.json，请检查网络与 AIHUB_REPO 配置", file=sys.stderr)
        sys.exit(1)
    print(f"数据源: {base}")

    n_reports = n_items = 0

    # 报告文件：本地已有的跳过（报告内容发布后不变），
    # 但最新一期日报每次重新下载，防止白天有修订。
    latest_daily = max(index.get("daily") or [""])
    for kind in ("daily", "weekly", "monthly"):
        for period in index.get(kind, []):
            need = args.full or not db.has_report(kind, period)
            if kind == "daily" and period == latest_daily:
                need = True
            if not need:
                continue
            data, _ = load_json(f"data/{kind}/{period}.json")
            if data is None:
                print(f"  [warn] 下载失败 data/{kind}/{period}.json", file=sys.stderr)
                continue
            db.upsert_report(kind, period, data)
            n_reports += 1
            if not local_dir: time.sleep(0.1)

    # 新闻全文
    for item_id in index.get("items", []):
        if not args.full and db.has_item(item_id):
            continue
        data, _ = load_json(f"data/items/{item_id}.json")
        if data is None:
            print(f"  [warn] 下载失败 data/items/{item_id}.json", file=sys.stderr)
            continue
        db.upsert_item(item_id, data)
        n_items += 1
        time.sleep(0.05)

    db.set_meta("last_sync", started)
    db.set_meta("remote_updated_at", index.get("updated_at", ""))
    print(f"同步完成：新增/更新 {n_reports} 份报告、{n_items} 条新闻")


if __name__ == "__main__":
    main()
