#!/usr/bin/env python3
"""AIHOT 数据下载脚本 —— 纯标准库实现，无需安装任何依赖。

只把 GitHub 仓库 data/ 下的 JSON 文件增量下载到本地目录，不写数据库，
适合内网已有自己的网页/数据库的系统：下载后自行把 JSON 导入即可。

用法：
    python3 fetch_data.py                          # 增量下载到 ./data
    python3 fetch_data.py --out /opt/aihot/data    # 指定输出目录
    python3 fetch_data.py --repo lekoon/ai-daily-hub
    python3 fetch_data.py --full                   # 忽略已有文件，全量重新下载
    python3 fetch_data.py --test                   # 只下载 index.json，验证连通性

数据源自动降级（内网两个入口任一个可用即可）：
    1. https://raw.githubusercontent.com/<repo>/main
    2. https://<owner>.github.io/<repo>

建议 cron 配置（每天 09:30 运行）：
    30 9 * * * cd /path/to/fetch && python3 fetch_data.py >> fetch.log 2>&1
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_REPO = "lekoon/ai-daily-hub"
TIMEOUT = 20
RETRIES = 2

HEADERS = {"User-Agent": "aihot-fetch/1.0"}
CST = timezone(timedelta(hours=8))  # 北京时间


def base_urls(repo):
    owner, name = repo.split("/", 1)
    return [
        f"https://raw.githubusercontent.com/{owner}/{name}/main",
        f"https://{owner}.github.io/{name}",
    ]


def http_get(url, retries=RETRIES):
    """GET 文本内容，失败重试；404 返回 None；其他错误抛异常。"""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                if resp.status == 404:
                    return None
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except Exception as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"下载失败: {url}: {last}")


def fetch_json(path, bases):
    """按优先级尝试所有数据源，返回 (data, base) 或 (None, None)。"""
    for base in bases:
        raw = http_get(f"{base}/{path}")
        if raw is None:
            print(f"  [info] {base}/{path} -> 404", file=sys.stderr)
            continue
        try:
            return json.loads(raw.decode("utf-8")), base
        except json.JSONDecodeError:
            print(f"  [warn] {base}/{path} 不是合法 JSON", file=sys.stderr)
    return None, None


def main():
    ap = argparse.ArgumentParser(description="从 GitHub 下载 AIHOT 数据 JSON")
    ap.add_argument("--out", default="./data", help="输出目录（默认 ./data）")
    ap.add_argument("--repo", default=BASE_REPO, help=f"GitHub 仓库（默认 {BASE_REPO}）")
    ap.add_argument("--full", action="store_true", help="忽略已有文件，全量重新下载")
    ap.add_argument("--test", action="store_true", help="只下载 index.json，验证连通性")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bases = base_urls(args.repo)

    print(f"[{datetime.now().isoformat(timespec='seconds')}] 数据源: {bases[0]} / {bases[1]}")

    index, base = fetch_json("data/index.json", bases)
    if index is None:
        print("无法获取 data/index.json：内网两个 GitHub 入口都不可达，请检查网络", file=sys.stderr)
        sys.exit(1)
    print(f"使用数据源: {base}，清单共 {len(index.get('daily', []))} 期日报、"
          f"{len(index.get('weekly', []))} 期周报、{len(index.get('monthly', []))} 期月报、"
          f"{len(index.get('items', []))} 条新闻")
    if args.test:
        print("连通性验证通过 ✔")
        return

    def need(rel):
        return args.full or not (out / rel).exists()

    def download(rel):
        data, _ = fetch_json(rel, bases)
        if data is None:
            return False
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True

    n = 0
    for kind in ("daily", "weekly", "monthly"):
        for period in index.get(kind, []):
            rel = f"data/{kind}/{period}.json"
            if not need(rel):
                continue
            if download(rel):
                n += 1
            time.sleep(0.05)

    for item_id in index.get("items", []):
        rel = f"data/items/{item_id}.json"
        if not need(rel):
            continue
        if download(rel):
            n += 1
        time.sleep(0.05)

    # 兜底：index.json 可能因 CDN 缓存延迟缺少当天日报，直接按今天日期再拉一次
    today = datetime.now(CST).date().isoformat()
    rel = f"data/daily/{today}.json"
    if today not in index.get("daily", []) and not (out / rel).exists():
        if download(rel):
            n += 1
            print(f"兜底补充：今日日报 {today}")

    print(f"完成：本次下载 {n} 个文件，目录 {out}，共 {sum(1 for _ in out.rglob('*.json'))} 个 JSON")


if __name__ == "__main__":
    main()
