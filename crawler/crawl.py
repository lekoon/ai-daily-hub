"""AIHOT 日报/周报/月报抓取脚本。

每天由 GitHub Actions 运行（北京时间 09:00），抓取结果写入 data/ 目录：
    data/daily/2026-07-30.json
    data/weekly/2026-W30.json
    data/monthly/2026-06.json
    data/items/<id>.json     （每条新闻全文，Markdown 导出解析而来）
    data/index.json          （清单，供内网同步用）

用法：
    python crawl.py                  # 抓当天日报 + 新周报/月报
    python crawl.py --date 2026-07-30
    python crawl.py --backfill-daily 7   # 补抓最近 7 天日报
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from parse import BASE_URL, parse_daily, parse_item_markdown, parse_period, parse_report_links

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CST = timezone(timedelta(hours=8))  # 北京时间

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}
ITEM_DELAY = 1.0   # 详情页抓取间隔，避免给对方服务器造成压力
PAGE_DELAY = 0.5

session = requests.Session()
session.headers.update(HEADERS)


def fetch(path, retries=2):
    """GET 目标站页面，失败重试，最终失败抛异常。"""
    url = path if path.startswith("http") else BASE_URL + path
    last = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            last = e
            print(f"  [warn] {url} 第 {attempt + 1} 次请求失败: {e}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"抓取失败: {url}: {last}")


def save_json(rel_path, obj):
    p = DATA_DIR / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  saved {p.relative_to(ROOT)}")


def load_index():
    p = DATA_DIR / "index.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"daily": [], "weekly": [], "monthly": [], "updated_at": ""}


def crawl_item(item_id, index):
    """抓取单条新闻全文（若本地已有则跳过）。"""
    p = DATA_DIR / "items" / f"{item_id}.json"
    if p.exists():
        return False
    md = fetch(f"/items/{item_id}/markdown")
    time.sleep(ITEM_DELAY)
    if md is None:
        print(f"  [warn] 详情页不存在: {item_id}", file=sys.stderr)
        return False
    item = parse_item_markdown(md)
    item["id"] = item_id
    item["url"] = f"{BASE_URL}/items/{item_id}"
    item["fetched_at"] = datetime.now(CST).isoformat(timespec="seconds")
    save_json(Path("items") / f"{item_id}.json", item)
    index.setdefault("items", [])
    if item_id not in index["items"]:
        index["items"].append(item_id)
    return True


def collect_item_ids(*reports):
    ids = []
    for rep in reports:
        for sec in rep.get("sections", []):
            ids.extend(a["id"] for a in sec["articles"] if a.get("id"))
        for theme in rep.get("themes", []):
            ids.extend(s["id"] for s in theme["stories"] if s.get("id"))
    # 去重保序
    return list(dict.fromkeys(ids))


def crawl_daily(date_str, index, force=False):
    rel = Path("daily") / f"{date_str}.json"
    if (DATA_DIR / rel).exists() and not force:
        print(f"日报 {date_str} 已存在，跳过")
        return None
    html = fetch(f"/daily/{date_str}")
    time.sleep(PAGE_DELAY)
    if html is None:
        print(f"日报 {date_str} 不存在（404），跳过")
        return None
    report = parse_daily(html)
    report["date"] = date_str
    report["url"] = f"{BASE_URL}/daily/{date_str}"
    report["fetched_at"] = datetime.now(CST).isoformat(timespec="seconds")
    if report["story_count"] == 0:
        # 当天 8 点前页面已存在但无内容（视为未发布）；若白天仍是 0 条则可能是页面改版
        print(f"  [warn] 日报 {date_str} 解析为 0 条（未发布或页面结构变化），跳过", file=sys.stderr)
        return None
    save_json(rel, report)
    if date_str not in index["daily"]:
        index["daily"].append(date_str)
        index["daily"].sort()
    return report


def crawl_new_periods(kind, index, with_items=True):
    """抓取 index 页发现的所有新周报/月报，返回新抓取的报告列表。"""
    html = fetch(f"/{kind}")
    time.sleep(PAGE_DELAY)
    if html is None:
        print(f"[warn] /{kind} 索引页抓取失败", file=sys.stderr)
        return []
    known = set(index[kind])
    new_reports = []
    for pid in parse_report_links(html, kind):
        if pid in known:
            continue
        page = fetch(f"/{kind}/{pid}")
        time.sleep(PAGE_DELAY)
        if page is None:
            continue
        report = parse_period(page, kind)
        report["period"] = pid
        report["url"] = f"{BASE_URL}/{kind}/{pid}"
        report["fetched_at"] = datetime.now(CST).isoformat(timespec="seconds")
        save_json(Path(kind) / f"{pid}.json", report)
        index[kind].append(pid)
        index[kind].sort()
        new_reports.append(report)
        print(f"新{'周报' if kind == 'weekly' else '月报'}: {pid}（{report['story_count']} 条）")
    return new_reports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="指定日报日期 YYYY-MM-DD，默认今天（北京时间）")
    ap.add_argument("--backfill-daily", type=int, metavar="N", help="补抓最近 N 天日报")
    ap.add_argument("--no-items", action="store_true", help="只抓报告页，不抓新闻全文")
    ap.add_argument("--force", action="store_true", help="已存在也重新抓取")
    args = ap.parse_args()

    index = load_index()
    reports = []

    if args.backfill_daily:
        today = datetime.now(CST).date()
        for i in range(args.backfill_daily):
            d = (today - timedelta(days=i)).isoformat()
            rep = crawl_daily(d, index, force=args.force)
            if rep:
                reports.append(rep)
    else:
        date_str = args.date or datetime.now(CST).date().isoformat()
        rep = crawl_daily(date_str, index, force=args.force)
        if rep:
            reports.append(rep)

    weekly_new = crawl_new_periods("weekly", index)
    monthly_new = crawl_new_periods("monthly", index)
    reports.extend(weekly_new)
    reports.extend(monthly_new)

    if not args.no_items:
        ids = collect_item_ids(*reports) if reports else []
        print(f"需要抓取 {len(ids)} 条新闻全文")
        for n, item_id in enumerate(ids, 1):
            if crawl_item(item_id, index):
                print(f"  [{n}/{len(ids)}] item {item_id}")

    index["updated_at"] = datetime.now(CST).isoformat(timespec="seconds")
    save_json("index.json", index)
    print("完成。")


if __name__ == "__main__":
    main()
