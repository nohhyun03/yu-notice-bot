# Admin /status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin-only `/status` that always answers with bot health, and a generic reply to every unsupported message, so silence means trouble.

**Architecture:** `messages.format_status(...)` builds the text from plain values (tested). `telegram_bot` keeps a small `bot_state` dict updated by `schedule_loop`, gathers disk/memory/counts, and routes messages in `handle_update`.

**Tech Stack:** Python 3.12 stdlib (`shutil`, `datetime`, `html`), existing modules. No new packages.

**Spec:** `docs/superpowers/specs/2026-11-22-status-command-design.md`

## Global Constraints

- Unknown-message reply, exact: `지원하지 않는 명령어입니다. /help 를 보내 보세요.`
- Healthy header `✅ 봇 정상 동작 중 (HH:MM:SS)`; unhealthy header `⚠️ 점검 필요 (HH:MM:SS)`.
- Unhealthy if: any failing board; last crawl raised; inside window (Mon–Fri, 09:00–17:59 KST) and last crawl (or start) older than 20 minutes.
- `/status` is not in `setMyCommands` or `/help`. Admin = `str(chat_id) == ADMIN_CHAT_ID`.
- Error text in status is HTML-escaped.

## Review Focus

1. A non-admin sending `/status` gets the generic unknown reply, never status data. → Task 2 step 1 (routing rule), checked by reading; `handle_update` imports prod env so no unit test (same ruling as before).
2. Messages without text (sticker, photo) get the unknown reply, not a crash. → Task 2 `msg.get("text") or ""`.
3. Status before the first crawl after restart shows `아직 없음` and judges staleness from start time. → Task 1 test `test_no_crawl_yet_uses_start_time`.
4. `/proc/meminfo` missing (Windows) shows `?`, no crash. → Task 2 helper returns `"?"` on OSError.
5. Error text containing `<` does not break the HTML message. → Task 1 test `test_failed_crawl_error_is_escaped`.

---

### Task 1: `format_status`

**Files:** Modify `messages.py`; Test `tests/test_messages.py`

**Interfaces:**
- Produces: `format_status(now, started_at, last_crawl, next_run, failing_names, counts, disk_free, mem_free) -> str`
  - `now`, `started_at`, `next_run`: aware datetimes in KST
  - `last_crawl`: `None` or `{"time": datetime, "ok": bool, "new": int, "error": str | None}`
  - `failing_names`: list of board names; `counts`: `{"subscribers": int, "bookmarks": int}`; `disk_free`, `mem_free`: display strings
  - Lines in the spec's order; `⚠️ 장애 중인 게시판: 없음` or comma-joined names.

- [ ] **Step 1: Failing tests** in `tests/test_messages.py`, class `StatusTest`, Monday 2026-11-23 KST:
  - `test_healthy`: now 10:05, last crawl 10:00 ok new 2 → starts with `✅`, contains `성공 (새 공지 2건)`, `구독자 3명 · 스크랩 3건`, `장애 중인 게시판: 없음`.
  - `test_failing_board_is_warning`: failing `["컴퓨터학부 공지사항"]` → starts `⚠️`, contains that name.
  - `test_stale_crawl_in_window_is_warning`: now 10:40, last crawl 10:00 ok → `⚠️`.
  - `test_old_crawl_outside_window_is_ok`: now 22:00, last crawl 17:50 ok → `✅`.
  - `test_no_crawl_yet_uses_start_time`: last_crawl None, started 10:00, now 10:05 → `✅`, contains `아직 없음`; started 10:00, now 10:30 → `⚠️`.
  - `test_failed_crawl_error_is_escaped`: last crawl ok False error `"<html> 503"` → `⚠️`, contains `&lt;html&gt; 503`.
- [ ] **Step 2:** `.venv/Scripts/python -m unittest tests.test_messages -v` → ImportError `format_status`.
- [ ] **Step 3:** Implement in `messages.py`. Uptime as `N일 N시간 N분` (omit zero day part).
- [ ] **Step 4:** Same command → all OK.

### Task 2: Routing and state in the bot

**Files:** Modify `telegram_bot.py`

**Interfaces:** Consumes `format_status`; `crawl_and_send() -> int` (new notice count: sum of `len(posts)` in `new_notices_by_category`, 0 on early returns).

- [ ] **Step 1:** `bot_state = {"started_at": None, "last_crawl": None}`; `main()` sets `started_at = datetime.now(KST)`. `schedule_loop` records `{"time", "ok", "new", "error"}` after each run (ok False with `str(e)` on exception).
- [ ] **Step 2:** `handle_update` routing for messages: `text = (msg.get("text") or "").strip()`; `/start` → menu; `/help` → help; `/status` and admin → `send_telegram_message(token, chat_id, build_status())`; everything else → unknown reply.
- [ ] **Step 3:** `build_status() -> str` gathers `next_run_time(now)`, failing board names from `failing_categories`, `db.count_rows()`, disk via `shutil.disk_usage("/").free`, memory from `/proc/meminfo` `MemAvailable` (`"?"` on OSError), sizes as `1.4G`/`540MB`.
- [ ] **Step 4:** `py_compile`, full suite OK, `pyflakes` shows only the pre-existing unused `e`.
- [ ] **Step 5:** Commit, push, server pull + tests, restart; admin sends `/status` → status; sends `/foo` → unknown reply.
