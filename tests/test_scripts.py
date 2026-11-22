import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

import db
from scripts.backup_db import backup
from scripts.migrate_from_supabase import migrate


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.init_db(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_migrate_copies_rows(self):
        subs = [
            {"chat_id": "1", "name": "A", "subscriptions": ["general"], "updated_at": "2026-01-01T00:00:00+00:00"},
            {"chat_id": "2", "name": "B", "subscriptions": [], "updated_at": "2026-01-02T00:00:00+00:00"},
        ]
        bms = [
            {"id": 5, "chat_id": "1", "title": "T5", "link": "https://x/5", "created_at": "2026-01-03T00:00:00+00:00"},
            {"id": 9, "chat_id": "1", "title": "T9", "link": "https://x/9", "created_at": "2026-01-04T00:00:00+00:00"},
            {"id": 12, "chat_id": "2", "title": "T12", "link": "https://x/12", "created_at": "2026-01-05T00:00:00+00:00"},
        ]
        self.assertEqual(migrate(subs, bms), {"subscribers": 2, "bookmarks": 3})
        self.assertEqual(sorted(b["id"] for b in db.list_bookmarks("1")), [5, 9])

    def test_migrate_handles_nulls(self):
        migrate([{"chat_id": 3, "subscriptions": None, "updated_at": None}], [])
        self.assertEqual(db.get_subscriptions("3"), [])
        self.assertEqual(db.list_subscribers()[0]["name"], "")

    def test_migrate_refuses_non_empty_db(self):
        migrate([{"chat_id": "1", "name": "A", "subscriptions": [], "updated_at": None}], [])
        with self.assertRaises(RuntimeError):
            migrate([], [])


class BackupTest(unittest.TestCase):
    def test_backup_keeps_14(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "data.db")
            db.init_db(db_path)
            backup_dir = os.path.join(tmp, "backups")
            start = date(2026, 11, 1)
            for i in range(16):
                newest = backup(db_path, backup_dir, keep=14, today=start + timedelta(days=i))
            files = sorted(os.listdir(backup_dir))
            self.assertEqual(len(files), 14)
            self.assertEqual(files[0], "data-20261103.db")
            self.assertEqual(os.path.basename(newest), "data-20261116.db")
            conn = sqlite3.connect(newest)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            conn.close()
            self.assertTrue({"subscribers", "bookmarks", "notices"} <= tables)


if __name__ == "__main__":
    unittest.main()
