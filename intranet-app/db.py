"""SQLite 数据层：reports（日/周/月报 JSON）+ items（新闻全文 JSON）。"""

import json
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    kind        TEXT NOT NULL,           -- daily / weekly / monthly
    period      TEXT NOT NULL,           -- 2026-07-30 / 2026-W30 / 2026-06
    title       TEXT NOT NULL DEFAULT '',
    story_count INTEGER NOT NULL DEFAULT 0,
    json        TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (kind, period)
);
CREATE TABLE IF NOT EXISTS items (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    json         TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_items_title ON items(title);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


# ---------- 写入（sync 用） ----------

def upsert_report(kind, period, data):
    title = ""
    if kind == "daily":
        first = (data.get("sections") or [{}])
        arts = first[0].get("articles") if first else []
        title = arts[0]["title"] if arts else ""
    else:
        title = (data.get("lead") or {}).get("headline", "")
    with connect() as conn:
        conn.execute(
            """INSERT INTO reports (kind, period, title, story_count, json, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
               ON CONFLICT(kind, period) DO UPDATE SET
                 title=excluded.title, story_count=excluded.story_count,
                 json=excluded.json, updated_at=excluded.updated_at""",
            (kind, period, title, data.get("story_count", 0),
             json.dumps(data, ensure_ascii=False)),
        )


def upsert_item(item_id, data):
    with connect() as conn:
        conn.execute(
            """INSERT INTO items (id, title, source, published_at, json, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, source=excluded.source,
                 published_at=excluded.published_at, json=excluded.json,
                 updated_at=excluded.updated_at""",
            (item_id, data.get("title", ""), data.get("source", ""),
             data.get("published_at", ""), json.dumps(data, ensure_ascii=False)),
        )


def has_report(kind, period):
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM reports WHERE kind=? AND period=?", (kind, period)
        ).fetchone()
        return row is not None


def has_item(item_id):
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone()
        return row is not None


def get_meta(key, default=""):
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_meta(key, value):
    with connect() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ---------- 读取（app 用） ----------

def get_report(kind, period):
    with connect() as conn:
        row = conn.execute(
            "SELECT json FROM reports WHERE kind=? AND period=?", (kind, period)
        ).fetchone()
        return json.loads(row["json"]) if row else None


def latest_report(kind):
    with connect() as conn:
        row = conn.execute(
            "SELECT period FROM reports WHERE kind=? ORDER BY period DESC LIMIT 1",
            (kind,),
        ).fetchone()
        return get_report(kind, row["period"]) if row else None


def list_reports(kind):
    """返回 [{period, title, story_count}]，按期号倒序。"""
    with connect() as conn:
        rows = conn.execute(
            "SELECT period, title, story_count FROM reports WHERE kind=? "
            "ORDER BY period DESC",
            (kind,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_item(item_id):
    with connect() as conn:
        row = conn.execute("SELECT json FROM items WHERE id=?", (item_id,)).fetchone()
        return json.loads(row["json"]) if row else None


def search_items(keyword, limit=50):
    like = f"%{keyword}%"
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, source, published_at FROM items "
            "WHERE title LIKE ? OR json LIKE ? ORDER BY published_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]
