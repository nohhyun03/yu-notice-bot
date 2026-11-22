import json
import re
import sqlite3
from datetime import datetime, timezone

_path = "data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
  chat_id       TEXT PRIMARY KEY,
  name          TEXT NOT NULL DEFAULT '',
  subscriptions TEXT NOT NULL DEFAULT '[]',
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookmarks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id    TEXT NOT NULL,
  title      TEXT NOT NULL,
  link       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (chat_id, link)
);
CREATE TABLE IF NOT EXISTS notices (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  category   TEXT NOT NULL,
  article_id TEXT NOT NULL,
  title      TEXT NOT NULL,
  link       TEXT NOT NULL,
  UNIQUE (category, article_id)
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _connect():
    # One short-lived connection per call: the crawl thread, polling thread and API never share one.
    conn = sqlite3.connect(_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path):
    global _path
    _path = path
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
    conn.close()


def list_subscribers():
    with _connect() as conn:
        rows = conn.execute("SELECT chat_id, name, subscriptions FROM subscribers").fetchall()
    conn.close()
    return [{"chat_id": r["chat_id"], "name": r["name"], "subscriptions": json.loads(r["subscriptions"])} for r in rows]


def get_subscriptions(chat_id):
    with _connect() as conn:
        row = conn.execute("SELECT subscriptions FROM subscribers WHERE chat_id = ?", (chat_id,)).fetchone()
    conn.close()
    return json.loads(row["subscriptions"]) if row else []


def set_subscriptions(chat_id, name, categories):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO subscribers (chat_id, name, subscriptions, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET name = excluded.name, "
            "subscriptions = excluded.subscriptions, updated_at = excluded.updated_at",
            (chat_id, name, json.dumps(categories), _now()),
        )
    conn.close()


def list_bookmarks(chat_id):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, link, created_at FROM bookmarks WHERE chat_id = ? ORDER BY created_at DESC, id DESC",
            (chat_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_bookmark(chat_id, title, link):
    with _connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO bookmarks (chat_id, title, link, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, title, link, _now()),
        )
    conn.close()
    return cur.rowcount == 1


def delete_bookmark(chat_id, bookmark_id):
    with _connect() as conn:
        cur = conn.execute("DELETE FROM bookmarks WHERE id = ? AND chat_id = ?", (bookmark_id, chat_id))
    conn.close()
    return cur.rowcount == 1


def remember_notice(category, article_id, title, link):
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO notices (category, article_id, title, link) VALUES (?, ?, ?, ?)",
            (category, str(article_id), title, link),
        )
        row = conn.execute(
            "SELECT id FROM notices WHERE category = ? AND article_id = ?", (category, str(article_id))
        ).fetchone()
    conn.close()
    return row["id"]


def parse_id(text):
    # ASCII digits only and short enough for SQLite INTEGER; str.isdigit() also accepts "²".
    return int(text) if re.fullmatch(r"[0-9]{1,18}", text or "") else None


def parse_bookmark_data(data):
    prefix, _, value = (data or "").partition(":")
    return parse_id(value) if prefix == "bm" else None


def bookmark_notice(chat_id, notice_id):
    with _connect() as conn:
        notice = conn.execute("SELECT title, link FROM notices WHERE id = ?", (notice_id,)).fetchone()
    conn.close()
    if notice is None:
        return "missing"
    return "added" if add_bookmark(chat_id, notice["title"], notice["link"]) else "exists"


def count_rows():
    with _connect() as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("subscribers", "bookmarks")}
    conn.close()
    return counts
