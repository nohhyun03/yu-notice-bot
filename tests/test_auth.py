import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode

from auth import verify_init_data

TOKEN = "123:fake"


def make_init_data(token, user, auth_date):
    fields = {"auth_date": str(int(auth_date)), "query_id": "AAE", "user": json.dumps(user)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class VerifyInitDataTest(unittest.TestCase):
    def test_valid_returns_user(self):
        user = verify_init_data(make_init_data(TOKEN, {"id": 42, "first_name": "Kim"}, time.time()), TOKEN)
        self.assertEqual(user["id"], 42)

    def test_tampered_field_fails(self):
        now = int(time.time())
        data = make_init_data(TOKEN, {"id": 42}, now).replace(f"auth_date={now}", f"auth_date={now - 1}")
        self.assertIsNone(verify_init_data(data, TOKEN))

    def test_wrong_token_fails(self):
        self.assertIsNone(verify_init_data(make_init_data(TOKEN, {"id": 42}, time.time()), "999:other"))

    def test_expired_fails(self):
        self.assertIsNone(verify_init_data(make_init_data(TOKEN, {"id": 42}, time.time() - 86401), TOKEN))

    def test_missing_hash_fails(self):
        data = make_init_data(TOKEN, {"id": 42}, time.time())
        without_hash = "&".join(p for p in data.split("&") if not p.startswith("hash="))
        self.assertIsNone(verify_init_data(without_hash, TOKEN))
        self.assertIsNone(verify_init_data("", TOKEN))

    def test_user_without_first_name(self):
        user = verify_init_data(make_init_data(TOKEN, {"id": 7}, time.time()), TOKEN)
        self.assertEqual(user["id"], 7)


if __name__ == "__main__":
    unittest.main()
