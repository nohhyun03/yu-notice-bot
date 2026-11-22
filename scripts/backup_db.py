"""Daily copy of data.db into backups/, keeping the newest 14.

Run from the repo root (cron): .venv/bin/python -m scripts.backup_db
"""
import os
import sqlite3
from datetime import date


def backup(db_path, backup_dir, keep=14, today=None):
    os.makedirs(backup_dir, exist_ok=True)
    target = os.path.join(backup_dir, f"data-{(today or date.today()):%Y%m%d}.db")

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)  # consistent copy even while the bot is writing
    dst.close()
    src.close()

    old = sorted(f for f in os.listdir(backup_dir) if f.startswith("data-") and f.endswith(".db"))
    for name in old[:-keep]:
        os.remove(os.path.join(backup_dir, name))
    return target


def main():
    print(backup(os.getenv("DB_PATH", "data.db"), "backups"))


if __name__ == "__main__":
    main()
