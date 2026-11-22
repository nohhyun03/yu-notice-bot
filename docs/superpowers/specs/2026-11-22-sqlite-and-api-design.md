# SQLite + mini app API (steps 2 and 3) — design

Date: 2026-11-22
Status: approved by the user on 2026-11-22

## Intent

Today the mini app (`index.html` on GitHub Pages) talks to Supabase straight from the browser with a publishable key that anyone can read from the page. That key can read and change every subscriber's settings and every bookmark (verified: anonymous requests return all rows). The page also falls back to the admin's chat id `8730998890` when opened outside Telegram, and renders bookmark titles with `innerHTML` (XSS). The bot itself uses the same publishable key.

The user wants to keep the mini app UI (settings toggles + bookmark list), drop the external database, and close these holes. Data moves to a SQLite file on ncp-micro; the browser only talks to the bot's own API, which verifies Telegram's signature on every request.

Steps 2 (SQLite) and 3 (API) ship together. They cannot ship apart: if the bot read SQLite while the mini app still wrote Supabase, settings changes and new bookmarks would be lost. The user picked "ship together" over "API on Supabase first, then swap storage", because the second path writes Supabase API code only to throw it away.

## Goals

- All subscriber and bookmark data lives in `/srv/yu-notice-bot/data.db`. The 3 subscribers and 11 bookmarks move over once, unchanged.
- The mini app is served from `https://bot.nohhyun.me/` and calls `https://bot.nohhyun.me/api/...` only.
- Every API request carries Telegram `initData`; the server verifies its HMAC and acts only for the user inside it. No fallback user.
- The "📌 스크랩" button on notice messages saves the bookmark in the chat: tapping it shows a "📌 스크랩 완료" popup, no screen change (user's choice). The button carries only a notice reference, never the title or link.
- Bookmark titles are rendered as text, never as HTML.
- The bot no longer depends on Supabase (`supabase` package removed).

## Non-goals

- No change to the crawl schedule, categories, message text, or how new notices are detected (`last_notices.json` stays as is).
- No new mini app features or redesign; same two tabs, same look.
- No change to `/start` and `/menu` other than the button URL.
- Supabase project is not deleted or locked in this work; the user decides that after cutover.

## Anti-goals

- Any subscriber losing their subscriptions or bookmarks in the move.
- Duplicate notices or missed notices around cutover.
- One user able to read or change another user's data through the API.

## Constraints

- Server: ncp-micro, Ubuntu 24.04, Python 3.12, 1GB RAM, no IPv6. Bot runs as `yubot` from `/srv/yu-notice-bot` as systemd service `yu-notice-bot` (always-on asyncio process from step 1).
- nginx already serves `bot.nohhyun.me` with a Let's Encrypt certificate (site file `/etc/nginx/sites-available/bot.nohhyun.me`, current root `/var/www/bot.nohhyun.me`).
- Only one new package allowed: `aiohttp` (planned in step 1's design). SQLite via stdlib `sqlite3`.
- Never run the bot locally against the production token. Tests must not need `.env`, network or Supabase.
- Commits and pushes need the user's OK in chat.

## Approaches

| | Summary | Trade-off |
|---|---|---|
| **A. Ship SQLite + API + new mini app together (chosen)** | One cutover: migrate data, switch bot to SQLite, start API, serve new `index.html`. | Bigger single deploy. No throwaway code. 3 users, so the cutover moment is low-impact; Supabase data stays untouched as fallback. |
| B. API on Supabase first, SQLite later | Mini app → server API → Supabase; then swap storage behind the API. | Each step deploys alone, but the Supabase-backed API code is thrown away in the next step. |

Scrap button behavior — user picked **save in chat** (callback button) over **open mini app** (current). Trade-off accepted: the bookmark list no longer appears after each save; users open it from the menu.

## Design

### Storage — `db.py`

SQLite file `data.db` next to the code (git-ignored). WAL mode. One short-lived connection per operation (`sqlite3.connect`, `row_factory = sqlite3.Row`), so the crawl thread, the polling thread and the API handlers never share a connection.

```sql
CREATE TABLE IF NOT EXISTS subscribers (
  chat_id     TEXT PRIMARY KEY,
  name        TEXT NOT NULL DEFAULT '',
  subscriptions TEXT NOT NULL DEFAULT '[]',   -- JSON array of category keys
  updated_at  TEXT NOT NULL                    -- ISO 8601 UTC
);
CREATE TABLE IF NOT EXISTS bookmarks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id    TEXT NOT NULL,
  title      TEXT NOT NULL,
  link       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (chat_id, link)
);
CREATE TABLE IF NOT EXISTS notices (          -- notices the bot has sent, for scrap buttons
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  category   TEXT NOT NULL,
  article_id TEXT NOT NULL,
  title      TEXT NOT NULL,
  link       TEXT NOT NULL,
  UNIQUE (category, article_id)
);
```

Functions (all take/return plain Python values): `init_db(path)`, `list_subscribers()`, `get_subscriptions(chat_id)`, `set_subscriptions(chat_id, name, categories)`, `list_bookmarks(chat_id)`, `add_bookmark(chat_id, title, link) -> bool` (False when it already exists), `delete_bookmark(chat_id, bookmark_id) -> bool` (deletes only when the row belongs to `chat_id`), `remember_notice(category, article_id, title, link) -> int` (insert or return existing id), `get_notice(notice_id)`.

### Bot changes — `telegram_bot.py`

- `load_subscribers_from_db()` reads SQLite instead of Supabase; same return shape (`chat_id`, `name`, `subscriptions` list).
- When sending a new notice: `notice_id = remember_notice(...)`, and the button becomes `{"text": "📌 이 공지 스크랩하기", "callback_data": f"bm:{notice_id}"}`.
- `handle_update` also handles `callback_query`: for `bm:<id>`, look up the notice, `add_bookmark(from.id, title, link)`, then `answerCallbackQuery` with `📌 스크랩 완료` or `이미 보관함에 있는 공지입니다`. Unknown id → `스크랩할 수 없는 공지입니다`. The user id comes from Telegram's update, so it cannot be forged.
- `getUpdates` asks for `allowed_updates=["message","callback_query"]`.
- `send_menu` points its `web_app` button at `WEBAPP_URL`, which becomes `https://bot.nohhyun.me/` in `.env`.
- Supabase imports, client and env vars are removed. The env check requires only `TELEGRAM_TOKEN`.

### API — `api.py` (aiohttp, same process)

aiohttp `web.Application` started from `run()` with `AppRunner` on `127.0.0.1:8080`, next to `poll_loop` and `schedule_loop`. Blocking DB calls go through `asyncio.to_thread`.

Auth: every request sends header `X-Telegram-Init-Data: <Telegram.WebApp.initData>`. Server validation (`verify_init_data(init_data, bot_token, max_age_seconds=86400) -> dict | None`):
1. Parse as URL query; remove `hash`.
2. `data_check_string` = remaining `key=value` pairs sorted by key, joined with `\n`.
3. `secret = HMAC_SHA256(key="WebAppData", msg=bot_token)`; expected = `HMAC_SHA256(key=secret, msg=data_check_string).hexdigest()`; compare with `hmac.compare_digest`.
4. Reject if `auth_date` is older than `max_age_seconds`.
5. Return the parsed `user` JSON (needs `id`, uses `first_name`).
Missing or invalid → `401 {"error": "unauthorized"}`.

Endpoints (JSON):
| Method | Path | Body / result |
|---|---|---|
| GET | `/api/categories` | `[{"key","name"}]` from `CATEGORIES` (no auth needed) |
| GET | `/api/subscriptions` | `{"subscriptions": [...]}` for the caller |
| PUT | `/api/subscriptions` | body `{"subscriptions": [...]}`; unknown keys → 400; saves name = `first_name` |
| GET | `/api/bookmarks` | `[{"id","title","link","created_at"}]` newest first |
| DELETE | `/api/bookmarks/{id}` | 204 if deleted, 404 if not the caller's or missing |

Request body limit: aiohttp default (1MB) is fine.

### Mini app — `web/index.html`

Moves into the repo at `web/index.html`; nginx serves `/srv/yu-notice-bot/web` as the site root. Same look and two tabs. Changes:
- Remove Supabase JS, the hard-coded keys and the admin fallback. If `Telegram.WebApp.initData` is empty, show "텔레그램 앱에서 열어 주세요" and nothing else.
- Category toggles are built from `GET /api/categories` (removes the duplicate list).
- Every fetch sends `X-Telegram-Init-Data`.
- Bookmark cards are built with `textContent` and `addEventListener`; links open with `Telegram.WebApp.openLink(link)`, only for `http(s)` URLs.
- The `?action=add` path is removed.

### nginx

`/var/www/bot.nohhyun.me` holds only a placeholder page made on 2026-11-22. certbot renews with the nginx authenticator (`authenticator = nginx` in `/etc/letsencrypt/renewal/bot.nohhyun.me.conf`), so changing the root does not affect renewal; confirm with `certbot renew --dry-run` after the change. In the `bot.nohhyun.me` HTTPS server block: `root /srv/yu-notice-bot/web;` and

```
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
}
```

### Old messages, the bot menu button and GitHub Pages

Checked facts (2026-11-22):
- GitHub Pages serves the repo root `index.html` from `main` (live page hash equals `git show HEAD:index.html`). Since the `nohhyun.me` domain was set up, `nohhyun03.github.io/yu-notice-bot/` redirects to `http://nohhyun.me/yu-notice-bot/`; HTTPS on `nohhyun.me` is not issued by GitHub yet.
- The bot has a chat menu button (BotFather "설정", `getChatMenuButton`) of type `web_app` pointing at `https://nohhyun03.github.io/yu-notice-bot/`. No bot commands are registered.

Plan:
- The new mini app lives at `web/index.html`. The root `index.html` stays the old app in the first push, so pushing code does not change the live Pages site.
- At cutover the menu button is repointed with `setChatMenuButton` (`{"type":"web_app","text":"설정","web_app":{"url":"https://bot.nohhyun.me/"}}`).
- Right after migration, a second push replaces the root `index.html` with a stub: "이 버튼은 더 이상 지원되지 않습니다. 채팅에서 /menu 를 보내 주세요." Old scrap buttons and old menu links land there instead of writing to Supabase.
- Between migration and the stub going live (a few minutes), the old page can still write to Supabase. After the stub is live, re-read Supabase counts and `updated_at`; if anything changed since migration, copy those rows over by hand.

### Migration — `scripts/migrate_from_supabase.py`

One-off script run on the server as `yubot` with the venv **before** `supabase` is removed from it: reads both Supabase tables with the existing `.env` key, inserts into `data.db` keeping `chat_id`, `name`, `subscriptions`, `updated_at` and bookmark `id`, `title`, `link`, `created_at`. Refuses to run if `data.db` already has rows. Prints counts read vs written (expect 3 and 11).

### Backup

Daily `sqlite3 data.db ".backup backups/data-YYYYMMDD.db"` via `/etc/cron.d/yu-notice-bot-backup` as `yubot` at 03:00, keeping the last 14 files. Backups stay on the same server.

### Cutover order

1. Push code (root `index.html` unchanged); on server `git pull`, `pip install -r requirements.txt` (adds aiohttp; supabase still installed).
2. Stop service. Run migration; check counts 3/11.
3. Set `WEBAPP_URL=https://bot.nohhyun.me/` in `.env`; update nginx; reload nginx; `certbot renew --dry-run`.
4. Start service; `setChatMenuButton` to the new URL; check `/api/categories` over HTTPS.
5. Push the root `index.html` stub; re-check Supabase for changes since migration.
6. User opens the mini app from `/menu`, toggles a setting, sees their bookmarks; taps a scrap button on a new notice when one arrives.
7. Uninstall `supabase` from the venv.
Rollback window: the cutover day. Until step 7, rollback = revert the commit, restore the old `.env` value and menu button URL, restart; changes made in SQLite after cutover are lost. After the cutover day, problems are fixed forward.

### Tests (stdlib `unittest`, no network)

- `tests/test_db.py`: on a temp file — set/get subscriptions; `add_bookmark` twice returns True then False; `delete_bookmark` with another user's chat_id returns False and keeps the row; `remember_notice` twice returns the same id.
- `tests/test_auth.py`: a valid `initData` built in the test with a fake token passes and returns the user; tampered field fails; wrong token fails; `auth_date` older than max age fails; missing hash fails.
- `tests/test_api.py`: aiohttp test client (`aiohttp.test_utils`) with a temp DB and fake token — 401 without header; user A cannot delete user B's bookmark (404, row kept); PUT with unknown category → 400; GET returns only the caller's bookmarks.

## Calls made by the builder (Claude), not the user

- `last_notices.json` stays; the new `notices` table only backs scrap buttons.
- API on `127.0.0.1:8080` behind nginx `/api/`; mini app served by nginx from `web/`.
- `initData` max age 24 hours.
- Old GitHub Pages scrap buttons stop working and show a notice, instead of being supported.
- Supabase is left untouched after cutover; deleting or locking it is the user's decision.
- Backups daily, 14 kept, on the same server only.
- Category list served by the API to remove the duplicate in `index.html`.
- Two pushes at cutover (code first, Pages stub after migration) so the live Pages app is never deleted early.
- Rollback window is the cutover day; after that, fix forward.
