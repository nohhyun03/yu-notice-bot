import os
import tempfile
import time
import unittest

from aiohttp.test_utils import TestClient, TestServer

import db
from api import make_app
from tests.test_auth import TOKEN, make_init_data

CATS = {"general": {"name": "일반"}, "sw_edu": {"name": "SW"}}


def headers(user_id, first_name="Kim"):
    user = {"id": user_id, "first_name": first_name}
    return {"X-Telegram-Init-Data": make_init_data(TOKEN, user, time.time())}


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.init_db(os.path.join(self.tmp.name, "t.db"))
        self.client = TestClient(TestServer(make_app(TOKEN, CATS)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.tmp.cleanup()

    async def test_categories_public(self):
        resp = await self.client.get("/api/categories")
        self.assertEqual(resp.status, 200)
        self.assertEqual(await resp.json(), [{"key": "general", "name": "일반"}, {"key": "sw_edu", "name": "SW"}])

    async def test_requires_auth(self):
        self.assertEqual((await self.client.get("/api/subscriptions")).status, 401)
        bad = {"X-Telegram-Init-Data": headers(1)["X-Telegram-Init-Data"].replace("Kim", "Lee")}
        self.assertEqual((await self.client.get("/api/subscriptions", headers=bad)).status, 401)

    async def test_put_and_get_subscriptions(self):
        resp = await self.client.put("/api/subscriptions", json={"subscriptions": ["general"]}, headers=headers(1))
        self.assertEqual(resp.status, 200)
        resp = await self.client.get("/api/subscriptions", headers=headers(1))
        self.assertEqual(await resp.json(), {"subscriptions": ["general"]})
        self.assertEqual(db.list_subscribers()[0]["name"], "Kim")

    async def test_put_unknown_category(self):
        resp = await self.client.put("/api/subscriptions", json={"subscriptions": ["nope"]}, headers=headers(1))
        self.assertEqual(resp.status, 400)

    async def test_put_subscriptions_bad_body(self):
        h = {**headers(1), "Content-Type": "application/json"}
        for body in ["x", '{"subscriptions": "general"}', '{"subscriptions": [1]}']:
            resp = await self.client.put("/api/subscriptions", data=body, headers=h)
            self.assertEqual(resp.status, 400, body)

    async def test_bookmarks_only_own(self):
        db.add_bookmark("1", "mine", "https://x/1")
        db.add_bookmark("2", "theirs", "https://x/2")
        items = await (await self.client.get("/api/bookmarks", headers=headers(1))).json()
        self.assertEqual([i["title"] for i in items], ["mine"])

    async def test_delete_other_users_bookmark(self):
        db.add_bookmark("1", "mine", "https://x/1")
        db.add_bookmark("2", "theirs", "https://x/2")
        theirs = db.list_bookmarks("2")[0]["id"]
        mine = db.list_bookmarks("1")[0]["id"]
        self.assertEqual((await self.client.delete(f"/api/bookmarks/{theirs}", headers=headers(1))).status, 404)
        self.assertEqual(len(db.list_bookmarks("2")), 1)
        self.assertEqual((await self.client.delete(f"/api/bookmarks/{mine}", headers=headers(1))).status, 204)

    async def test_delete_non_numeric_id(self):
        for bad in ["abc", "%C2%B2", "9" * 30]:
            resp = await self.client.delete(f"/api/bookmarks/{bad}", headers=headers(1))
            self.assertEqual(resp.status, 404, bad)


if __name__ == "__main__":
    unittest.main()
