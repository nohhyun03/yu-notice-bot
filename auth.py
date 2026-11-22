import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def verify_init_data(init_data, bot_token, max_age_seconds=86400, now=None):
    """Check Telegram WebApp initData and return its user dict, or None if it is not genuine."""
    try:
        fields = dict(parse_qsl(init_data or "", keep_blank_values=True, strict_parsing=True))
        received_hash = fields.pop("hash", None)
        if not received_hash:
            return None

        check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            return None

        current = time.time() if now is None else now
        if current - int(fields["auth_date"]) > max_age_seconds:
            return None

        user = json.loads(fields["user"])
        return user if isinstance(user, dict) and "id" in user else None
    except (ValueError, KeyError, TypeError):
        return None
