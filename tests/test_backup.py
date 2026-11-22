import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

import db
from scripts.backup_db import backup


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
