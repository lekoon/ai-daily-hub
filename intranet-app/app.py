"""AIHOT 内网镜像站 —— Flask 动态 Web 应用。

页面：
    /                      最新日报
    /daily/<date>          指定日期日报
    /weekly, /weekly/<p>   周报
    /monthly, /monthly/<p> 月报
    /items/<id>            新闻全文
    /search?q=             关键词搜索
    /sync                  手动触发同步（可选，需 SYNC_TOKEN）

运行：
    开发: python app.py
    生产: waitress-serve --host 0.0.0.0 --port 8000 app:app
"""

import os
import re
import threading

import markdown as md_lib
from flask import Flask, abort, redirect, render_template, request, url_for

import db

app = Flask(__name__)

KIND_NAMES = {"daily": "日报", "weekly": "周报", "monthly": "月报"}


def render_md(text):
    return md_lib.markdown(
        text or "",
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )


app.jinja_env.filters["md"] = render_md


@app.context_processor
def inject_globals():
    return {
        "kind_names": KIND_NAMES,
        "last_sync": db.get_meta("last_sync"),
    }


def get_report_or_404(kind, period=None):
    data = db.get_report(kind, period) if period else db.latest_report(kind)
    if data is None:
        abort(404)
    return data


def archives(kind):
    """归档列表。日报按月分组，周/月报按列表。"""
    reports = db.list_reports(kind)
    if kind != "daily":
        return reports
    groups = {}
    for r in reports:
        ym = r["period"][:7]  # 2026-07
        groups.setdefault(ym, []).append(r)
    return [{"month": ym, "entries": entries} for ym, entries in groups.items()]


@app.route("/")
def home():
    latest = db.list_reports("daily")
    if not latest:
        return render_template("empty.html"), 200
    return redirect(url_for("daily", date=latest[0]["period"]))


@app.route("/daily")
@app.route("/daily/<date>")
def daily(date=None):
    data = get_report_or_404("daily", date)
    return render_template(
        "daily.html", report=data, kind="daily",
        archive=archives("daily"), current=data["date"],
    )


@app.route("/weekly")
@app.route("/weekly/<period>")
def weekly(period=None):
    data = get_report_or_404("weekly", period)
    return render_template(
        "period.html", report=data, kind="weekly",
        archive=archives("weekly"), current=data["period"],
    )


@app.route("/monthly")
@app.route("/monthly/<period>")
def monthly(period=None):
    data = get_report_or_404("monthly", period)
    return render_template(
        "period.html", report=data, kind="monthly",
        archive=archives("monthly"), current=data["period"],
    )


@app.route("/items/<item_id>")
def item(item_id):
    if not re.fullmatch(r"[A-Za-z0-9]+", item_id):
        abort(404)
    data = db.get_item(item_id)
    if data is None:
        abort(404)
    return render_template("item.html", item=data)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = db.search_items(q) if q else []
    return render_template("search.html", q=q, results=results)


@app.route("/sync", methods=["POST"])
def sync_now():
    """手动触发同步：POST /sync?token=xxx（环境变量 SYNC_TOKEN，未设置则禁用）。"""
    token = os.environ.get("SYNC_TOKEN")
    if not token or request.args.get("token") != token:
        abort(403)

    def run():
        import sync
        sync.main()

    threading.Thread(target=run, daemon=True).start()
    return {"status": "sync started"}


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=8000, debug=True)
