import os
import tempfile
import unittest

import db


class DbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.init_db(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_subscriptions_roundtrip(self):
        db.set_subscriptions("1", "A", ["general"])
        self.assertEqual(db.get_subscriptions("1"), ["general"])
        self.assertEqual(db.list_subscribers(), [{"chat_id": "1", "name": "A", "subscriptions": ["general"]}])
        self.assertEqual(db.get_subscriptions("unknown"), [])

    def test_add_bookmark_twice(self):
        self.assertTrue(db.add_bookmark("1", "T", "https://x/1"))
        self.assertFalse(db.add_bookmark("1", "T", "https://x/1"))
        self.assertEqual(len(db.list_bookmarks("1")), 1)

    def test_delete_other_users_bookmark(self):
        db.add_bookmark("1", "T", "https://x/1")
        bookmark_id = db.list_bookmarks("1")[0]["id"]
        self.assertFalse(db.delete_bookmark("2", bookmark_id))
        self.assertEqual(len(db.list_bookmarks("1")), 1)
        self.assertTrue(db.delete_bookmark("1", bookmark_id))
        self.assertEqual(db.list_bookmarks("1"), [])

    def test_remember_notice_is_idempotent(self):
        first = db.remember_notice("general", "100", "T", "https://x/100")
        second = db.remember_notice("general", "100", "T", "https://x/100")
        self.assertEqual(first, second)

    def test_parse_bookmark_data_rejects_garbage(self):
        self.assertEqual(db.parse_bookmark_data("bm:5"), 5)
        for bad in ["bm:abc", "xx", "", "bm:", "bm:²", "bm:" + "9" * 30]:
            self.assertIsNone(db.parse_bookmark_data(bad), bad)

    def test_bookmark_notice_missing(self):
        self.assertEqual(db.bookmark_notice("1", 999), "missing")
        notice_id = db.remember_notice("general", "100", "T", "https://x/100")
        self.assertEqual(db.bookmark_notice("1", notice_id), "added")
        self.assertEqual(db.bookmark_notice("1", notice_id), "exists")


if __name__ == "__main__":
    unittest.main()
