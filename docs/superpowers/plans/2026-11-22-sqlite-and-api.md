# SQLite + Mini App API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move subscribers and bookmarks from Supabase to SQLite, serve the mini app and a signed-request API from `https://bot.nohhyun.me`, and save scraps from a chat button.

**Architecture:** `db.py` owns SQLite. `auth.py` verifies Telegram `initData`. `api.py` builds an aiohttp app that `telegram_bot.run()` starts on `127.0.0.1:8080` next to the polling and schedule loops; nginx serves `web/` and proxies `/api/`. A one-off script migrates Supabase rows.

**Tech Stack:** Python 3.12, stdlib `sqlite3`/`hmac`/`unittest`, `aiohttp==3.11.11` (new), existing `requests`, `beautifulsoup4`, `python-dotenv`. Vanilla JS mini app with `telegram-web-app.js`.

**Spec:** `docs/superpowers/specs/2026-11-22-sqlite-and-api-design.md`

## Global Constraints

- Only new package: `aiohttp`. Pin `aiohttp==3.11.11`. Remove `supabase` from `requirements.txt` (stays installed on the server until cutover step 7).
- Tests: stdlib `unittest` (+ `aiohttp.test_utils`), no network, no `.env`, temp DB files. Run with `python -m unittest discover -s tests -v`.
- Local test env: a repo-local `.venv` (already git-ignored) with `pip install -r requirements.txt`.
- Never run `telegram_bot.py` locally (production token in local `.env`).
- `initData` max age: 86400 seconds. Header name: `X-Telegram-Init-Data`.
- API listens on `127.0.0.1:8080`; paths under `/api/`.
- Callback data format: `bm:<notice_id>`. Answers: `📌 스크랩 완료`, `이미 보관함에 있는 공지입니다`, `스크랩할 수 없는 공지입니다`.
- Mini app outside Telegram shows only: `텔레그램 앱에서 열어 주세요`.
- Pages stub text: `이 버튼은 더 이상 지원되지 않습니다. 채팅에서 /menu 를 보내 주세요.`
- Backups: daily 03:00, `backups/data-YYYYMMDD.db`, keep 14.
- Commits/pushes need the user's OK in chat.

## Review Focus

1. Malformed or unknown callback data (`bm:abc`, `bm:999999`, `xx`) must answer `스크랩할 수 없는 공지입니다` or be ignored, never crash polling. → Task 1 tests `test_parse_bookmark_data_rejects_garbage`, `test_bookmark_notice_missing`.
2. Malformed request bodies (non-JSON, `subscriptions` not a list, non-string items) must get 400, not 500. → Task 3 test `test_put_subscriptions_bad_body`.
3. `DELETE /api/bookmarks/abc` must be 404, not 500. → Task 3 test `test_delete_non_numeric_id`.
4. `initData` whose user has no `first_name` must still work (name stored as `""`). → Task 2 test `test_user_without_first_name`.
5. Supabase rows with `subscriptions = null` or missing `name` must migrate as `[]` / `""`. → Task 6 test `test_migrate_handles_nulls`.

---

### Task 1: SQLite storage

**Files:**
- Create: `db.py`, `tests/test_db.py`
- Modify: `.gitignore` (add `data.db*`, `backups/`)

**Interfaces:**
- Produces (all in `db.py`; `init_db` sets a module-level path used by the rest; each call opens its own connection):
  - `init_db(path: str) -> None` — creates the three tables from the spec, sets `PRAGMA journal_mode=WAL`.
  - `list_subscribers() -> list[dict]` — `{"chat_id": str, "name": str, "subscriptions": list[str]}`
  - `get_subscriptions(chat_id: str) -> list[str]` (empty list if no row)
  - `set_subscriptions(chat_id: str, name: str, categories: list[str]) -> None` (upsert, `updated_at` = UTC ISO now)
  - `list_bookmarks(chat_id: str) -> list[dict]` — `{"id","title","link","created_at"}` newest first
  - `add_bookmark(chat_id: str, title: str, link: str) -> bool`
  - `delete_bookmark(chat_id: str, bookmark_id: int) -> bool`
  - `remember_notice(category: str, article_id: str, title: str, link: str) -> int`
  - `parse_bookmark_data(data: str) -> int | None` — `"bm:12"` → 12, anything else → None
  - `bookmark_notice(chat_id: str, notice_id: int) -> str` — `"added"`, `"exists"` or `"missing"`
  - `count_rows() -> dict` — `{"subscribers": n, "bookmarks": n}`

- [ ] **Step 1: Write failing tests** in `tests/test_db.py` (`setUp`: temp dir, `init_db(tmp/"t.db")`):
  - `test_subscriptions_roundtrip`: `set_subscriptions("1","A",["general"])` → `get_subscriptions("1") == ["general"]`; `list_subscribers() == [{"chat_id":"1","name":"A","subscriptions":["general"]}]`; unknown user → `[]`.
  - `test_add_bookmark_twice`: first `True`, second `False`, `len(list_bookmarks("1")) == 1`.
  - `test_delete_other_users_bookmark`: add for `"1"`, `delete_bookmark("2", id) is False`, row still listed for `"1"`; `delete_bookmark("1", id) is True`.
  - `test_remember_notice_is_idempotent`: same `(category, article_id)` twice → same id.
  - `test_parse_bookmark_data_rejects_garbage`: `"bm:5"` → 5; `"bm:abc"`, `"xx"`, `""`, `"bm:"` → None.
  - `test_bookmark_notice_missing`: `bookmark_notice("1", 999) == "missing"`; after `remember_notice`, first call `"added"`, second `"exists"`.
- [ ] **Step 2: Run** `python -m unittest tests.test_db -v` → ERROR `No module named 'db'`.
- [ ] **Step 3: Implement `db.py`** per Interfaces and the spec's SQL.
- [ ] **Step 4: Run** `python -m unittest tests.test_db -v` → 6 OK.

---

### Task 2: initData verification

**Files:**
- Create: `auth.py`, `tests/test_auth.py`

**Interfaces:**
- Produces: `verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400, now: float | None = None) -> dict | None` — returns the parsed `user` dict or None. `now` defaults to `time.time()` (parameter exists for tests).
- Test helper (in the test file): `make_init_data(token, user, auth_date)` builds a valid string with the spec's HMAC steps.

- [ ] **Step 1: Write failing tests** (`TOKEN = "123:fake"`):
  - `test_valid_returns_user`: user `{"id": 42, "first_name": "Kim"}`, `auth_date=now` → returns dict with `id == 42`.
  - `test_tampered_field_fails`: replace `auth_date` value after signing → None.
  - `test_wrong_token_fails`: verify with `"999:other"` → None.
  - `test_expired_fails`: `auth_date = now - 86401` → None.
  - `test_missing_hash_fails`: string without `hash=` → None; `""` → None.
  - `test_user_without_first_name`: user `{"id": 7}` → returns dict with `id == 7`.
- [ ] **Step 2: Run** `python -m unittest tests.test_auth -v` → ERROR `No module named 'auth'`.
- [ ] **Step 3: Implement `verify_init_data`** with `urllib.parse.parse_qsl(keep_blank_values=True)`, the spec's 5 steps, `hmac.compare_digest`; any parsing error → None.
- [ ] **Step 4: Run** → 6 OK.

---

### Task 3: API

**Files:**
- Create: `api.py`, `tests/test_api.py`
- Modify: `requirements.txt` → `aiohttp==3.11.11`, `requests==2.31.0`, `beautifulsoup4==4.12.3`, `python-dotenv==1.2.2` (no `supabase`)

**Interfaces:**
- Consumes: Task 1 `db` functions, Task 2 `verify_init_data`.
- Produces: `make_app(bot_token: str, categories: dict) -> aiohttp.web.Application` with the spec's five endpoints. `categories` is the bot's `CATEGORIES` dict (`key -> {"name": ...}`). Blocking DB calls via `asyncio.to_thread`. Auth failure → 401 `{"error":"unauthorized"}`.

- [ ] **Step 1: Set up local venv**: `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt` → installs without error.
- [ ] **Step 2: Write failing tests** (`unittest.IsolatedAsyncioTestCase`, `TestServer`/`TestClient`, temp DB, `TOKEN="123:fake"`, `CATS={"general":{"name":"일반"},"sw_edu":{"name":"SW"}}`, header helper using Task 2's `make_init_data` — import it from `tests.test_auth`):
  - `test_categories_public`: GET `/api/categories` without header → 200, `[{"key":"general","name":"일반"},{"key":"sw_edu","name":"SW"}]`.
  - `test_requires_auth`: GET `/api/subscriptions` without header → 401; with tampered header → 401.
  - `test_put_and_get_subscriptions`: PUT `{"subscriptions":["general"]}` as user 1 → 200; GET → `{"subscriptions":["general"]}`; `db.list_subscribers()[0]["name"] == "Kim"`.
  - `test_put_unknown_category`: `["nope"]` → 400.
  - `test_put_subscriptions_bad_body`: body `"x"` (non-JSON), `{"subscriptions":"general"}`, `{"subscriptions":[1]}` → each 400.
  - `test_bookmarks_only_own`: add bookmark for "1" and "2" via `db`; GET as user 1 → one item with user 1's title.
  - `test_delete_other_users_bookmark`: user 1 deletes user 2's id → 404, row still there; deletes own → 204.
  - `test_delete_non_numeric_id`: DELETE `/api/bookmarks/abc` → 404.
- [ ] **Step 3: Run** `.venv/Scripts/python -m unittest tests.test_api -v` → ERROR `No module named 'api'`.
- [ ] **Step 4: Implement `make_app`** per Interfaces.
- [ ] **Step 5: Run full suite** `.venv/Scripts/python -m unittest discover -s tests -v` → all OK (7 schedule + 6 db + 6 auth + 8 api).

---

### Task 4: Bot on SQLite + scrap callback + API startup

**Files:**
- Modify: `telegram_bot.py` (imports 11-17, Supabase block 52-60, `load_subscribers_from_db` 103-109, `handle_update` 158-169, `poll_loop` 171-202, send block in `crawl_and_send`, `run` 399-408, `main` 410-)

**Interfaces:**
- Consumes: `db.init_db`, `db.list_subscribers`, `db.remember_notice`, `db.parse_bookmark_data`, `db.bookmark_notice`; `api.make_app`.
- Produces: `DB_PATH = os.getenv("DB_PATH", "data.db")`; `WEBAPP_URL` default `"https://bot.nohhyun.me/"`.

- [ ] **Step 1: Remove Supabase** (import, client, `SUPABASE_*`); env check needs only `TELEGRAM_TOKEN`; `main()` calls `db.init_db(DB_PATH)` before `asyncio.run`.
- [ ] **Step 2: `load_subscribers_from_db()`** returns `db.list_subscribers()` (keep try/except + log, return `[]` on error).
- [ ] **Step 3: Scrap button** — in the send loop, `notice_id = db.remember_notice(category, post["id"], post["title"], post["link"])` once per post (before the subscriber loop), button `{"text": "📌 이 공지 스크랩하기", "callback_data": f"bm:{notice_id}"}`. Delete the `bookmark_url` code.
- [ ] **Step 4: Callback handling** — `handle_update` handles `callback_query`: `notice_id = db.parse_bookmark_data(cq.get("data",""))`; result `"missing"` when None, else `db.bookmark_notice(str(cq["from"]["id"]), notice_id)`; POST `answerCallbackQuery` with `callback_query_id` and the matching text from Global Constraints; log it. `poll_loop` params add `"allowed_updates": json.dumps(["message","callback_query"])`.
- [ ] **Step 5: Start API in `run()`** — `runner = web.AppRunner(api.make_app(TELEGRAM_TOKEN, CATEGORIES))`, `await runner.setup()`, `await web.TCPSite(runner, "127.0.0.1", 8080).start()`, then the existing gather; `await runner.cleanup()` in `finally`.
- [ ] **Step 6: Check** `.venv/Scripts/python -m py_compile telegram_bot.py` → no output; full suite → all OK; `grep -n supabase telegram_bot.py` → no matches.

---

### Task 5: Mini app

**Files:**
- Create: `web/index.html` (from current `index.html`), `deploy/pages-stub.html`
- Keep: root `index.html` unchanged in this task

**Interfaces:**
- Consumes: Task 3 endpoints and header name.

- [ ] **Step 1: Write `web/index.html`** — same CSS/markup; remove Supabase script, keys, `userId` fallback and `checkAutoBookmark`/`?action=add`; if `Telegram.WebApp.initData` is empty, replace body content with `텔레그램 앱에서 열어 주세요`. Build toggle cards from `GET /api/categories` (keep current per-category description text in a small JS map, fallback to the name). `api(path, options)` helper adds `X-Telegram-Init-Data`. Save → PUT then `tg.close()`. Bookmarks rendered with `createElement`/`textContent`/`addEventListener`; "보기" calls `tg.openLink(link)` only when `link` starts with `http://` or `https://`; "삭제" → DELETE then reload list.
- [ ] **Step 2: Write `deploy/pages-stub.html`** — minimal page, same dark colors, the stub text from Global Constraints.
- [ ] **Step 3: Check** `grep -nE "supabase|8730998890|innerHTML" web/index.html` → no matches; open `web/index.html` in a browser locally → shows `텔레그램 앱에서 열어 주세요`.

---

### Task 6: Migration and backup scripts

**Files:**
- Create: `scripts/migrate_from_supabase.py`, `scripts/backup_db.py`, `tests/test_scripts.py`

**Interfaces:**
- Consumes: `db.init_db`, `db.count_rows`.
- Produces:
  - `migrate(subscribers: list[dict], bookmarks: list[dict]) -> dict` in `scripts/migrate_from_supabase.py` — raises `RuntimeError` if `count_rows()` is not all zero; inserts keeping ids and timestamps; returns `count_rows()`. `main()` loads `.env`, imports `supabase` inside `main`, fetches both tables, calls `init_db(os.getenv("DB_PATH","data.db"))` and `migrate`, prints `read: 3/11, written: {...}`.
  - `backup(db_path: str, backup_dir: str, keep: int = 14, today: date | None = None) -> str` in `scripts/backup_db.py` — uses `sqlite3.Connection.backup`, file `data-YYYYMMDD.db`, deletes oldest beyond `keep`; returns the new path. `main()` uses `DB_PATH` and `backups/`.

- [ ] **Step 1: Write failing tests** (temp DB; add `scripts/__init__.py`):
  - `test_migrate_copies_rows`: 2 subscribers, 3 bookmarks → counts `{"subscribers":2,"bookmarks":3}`, bookmark ids preserved.
  - `test_migrate_handles_nulls`: subscriber with `subscriptions=None`, no `name` → `get_subscriptions == []`, name `""`.
  - `test_migrate_refuses_non_empty_db`: second run → `RuntimeError`.
  - `test_backup_keeps_14`: run `backup` for 16 consecutive `today` dates → 14 files remain, oldest two gone, newest file opens and has the tables.
- [ ] **Step 2: Run** `.venv/Scripts/python -m unittest tests.test_scripts -v` → ERROR (modules missing).
- [ ] **Step 3: Implement both scripts.**
- [ ] **Step 4: Run full suite** → all OK.

---

### Task 7: Deploy files, commit, cutover

**Files:**
- Create: `deploy/nginx-bot.nohhyun.me.conf` (the two directives to put in the HTTPS server block), `deploy/yu-notice-bot-backup.cron` (`0 3 * * * yubot cd /srv/yu-notice-bot && .venv/bin/python -m scripts.backup_db`)
- Modify: `README.md` (storage = SQLite, mini app URL, migration/backup), `deploy/yu-notice-bot.service` unchanged

- [ ] **Step 1: Final review** of the whole change (fresh reviewer).
- [ ] **Step 2: Push 1 (ask user first)** — commit everything; root `index.html` still the old app. Merge to `main`, push.
- [ ] **Step 3: Server prep** — `runuser -u yubot -- git pull`; `.venv/bin/pip install -r requirements.txt` (supabase stays installed).
- [ ] **Step 4: Migrate** — `systemctl stop yu-notice-bot`; `runuser -u yubot -- .venv/bin/python -m scripts.migrate_from_supabase` → `read: 3/11`, written counts equal. Note the time.
- [ ] **Step 5: Config** — `.env` `WEBAPP_URL=https://bot.nohhyun.me/`; edit nginx site per `deploy/nginx-bot.nohhyun.me.conf`; `nginx -t && systemctl reload nginx`; `certbot renew --dry-run` → success; `cp deploy/yu-notice-bot-backup.cron /etc/cron.d/yu-notice-bot-backup`.
- [ ] **Step 6: Start** — `systemctl start yu-notice-bot` → active; `curl -s https://bot.nohhyun.me/api/categories` → 7 categories; `curl -s -o /dev/null -w "%{http_code}" https://bot.nohhyun.me/api/subscriptions` → 401; `setChatMenuButton` to `https://bot.nohhyun.me/` → `ok:true`.
- [ ] **Step 7: Push 2 (ask user first)** — replace root `index.html` with `deploy/pages-stub.html` content; push. Re-read Supabase row counts and max `updated_at`/`created_at`; if newer than the migration time, copy those rows by hand.
- [ ] **Step 8: User checks** — `/menu` → mini app shows their toggles; save works; bookmarks tab shows their items; on the next new notice, the scrap button shows `📌 스크랩 완료`.
- [ ] **Step 9: Cleanup (end of cutover day)** — `.venv/bin/pip uninstall -y supabase` and its now-unused deps only if listed by `pip uninstall` as supabase-*; run backup once by hand → file in `backups/`.
