"""One-off copy of subscribers and bookmarks from Supabase into data.db.

Run from the repo root on the server, before supabase is uninstalled:
    .venv/bin/python -m scripts.migrate_from_supabase
"""
import json
import os
from datetime import datetime, timezone

import db


def migrate(subscribers, bookmarks):
    if any(db.count_rows().values()):
        raise RuntimeError("data.db already has rows; refusing to migrate twice")

    now = datetime.now(timezone.utc).isoformat()
    conn = db._connect()
    with conn:
        for s in subscribers:
            conn.execute(
                "INSERT INTO subscribers (chat_id, name, subscriptions, updated_at) VALUES (?, ?, ?, ?)",
                (str(s["chat_id"]), s.get("name") or "", json.dumps(s.get("subscriptions") or []),
                 s.get("updated_at") or now),
            )
        for b in bookmarks:
            conn.execute(
                "INSERT INTO bookmarks (id, chat_id, title, link, created_at) VALUES (?, ?, ?, ?, ?)",
                (b["id"], str(b["chat_id"]), b["title"], b["link"], b.get("created_at") or now),
            )
    conn.close()
    return db.count_rows()


def main():
    from dotenv import load_dotenv
    from supabase import create_client  # only installed on the server until cutover cleanup

    load_dotenv()
    client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    subscribers = client.table("subscribers").select("*").execute().data or []
    bookmarks = client.table("bookmarks").select("*").execute().data or []

    db.init_db(os.getenv("DB_PATH", "data.db"))
    written = migrate(subscribers, bookmarks)
    print(f"read: {len(subscribers)}/{len(bookmarks)}, written: {written}")


if __name__ == "__main__":
    main()
