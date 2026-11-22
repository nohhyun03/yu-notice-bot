# Always-on bot (step 1 of 3) — design

Date: 2026-11-22
Status: approved by the user on 2026-11-22

## Intent

The bot runs from cron every 10 minutes on weekdays 09:00–17:50. A user who sends `/start` or `/menu` waits up to 10 minutes for a reply, and gets none outside that window. The server (ncp-micro) is always on, so an always-on process costs nothing extra. Goal: reply to commands immediately, 24 hours a day, and keep the crawl schedule unchanged.

This is step 1 of 3. Step 2 replaces Supabase with SQLite. Step 3 adds an HTTP API for the mini app behind nginx on `https://bot.nohhyun.me`. Step 1 must leave a structure that step 3 can attach a web server to.

## Goals

- `/start` and `/menu` get a reply within a few seconds, at any time.
- Crawling and sending keep the current schedule: Monday–Friday, every 10 minutes from 09:00 to 17:50 Asia/Seoul. Notices are only posted in that window (the user checked this).
- The process restarts by itself if it crashes.
- One admin alert when a board starts failing and one when it recovers, instead of one every 10 minutes.

## Non-goals

- No change to Supabase, `index.html`, the message format or the categories.
- No webhook. Polling stays (fewer failure points; see Approaches).
- No crawler parser tests in this step.

## Anti-goals

- Duplicate notices sent to subscribers.
- Commands lost because two processes read `getUpdates` at once.
- Subscribers noticing any change other than faster replies.

## Approaches

| | Summary | Trade-off |
|---|---|---|
| **A. asyncio + aiohttp (chosen)** | One asyncio loop: a polling task and a schedule task. aiohttp joins in step 3 for the API server. | Retry and error handling written by hand (tens of lines). Fewest dependencies, readable a year later, step 3 attaches to the same loop. |
| B. python-telegram-bot | PTB handlers + JobQueue (APScheduler). | Large dependency, Telegram code rewritten in the library's style, still needs aiohttp for the API. |
| C. Threads + requests | Polling thread + schedule thread. | Smallest change now, but step 3 needs a hand-written `http.server` or Flask, and shared state across threads. |
| D. FastAPI + uvicorn | Web app with background tasks, optional webhook. | Best API ergonomics, but heaviest RAM and dependencies; overkill for 3 subscribers on a 1GB server. |

The user picked A.

## Design

**Process layout** — `telegram_bot.py` stays the single entry point.

- `crawl_and_send()`: today's `main()` body minus command handling. Same logic for loading subscribers, crawling, finding new notices, sending and saving `last_notices.json`.
- `poll_loop()`: calls `getUpdates` with `timeout=50` and the next `offset`, answers `/start` and `/menu` with the existing `send_menu()`, repeats. Calls `deleteWebhook` once at start. On a network error it waits a few seconds and retries.
- `schedule_loop()`: computes the next run time (next 10-minute mark that falls on Mon–Fri between 09:00 and 17:50 Asia/Seoul, using `zoneinfo`), sleeps until then, runs `crawl_and_send()`, repeats. Runs are sequential, so two crawls never overlap.
- `main()`: checks required env vars (as today), then runs both loops with `asyncio.gather`.

**Blocking code** — The existing `requests`-based functions (crawl, send, Supabase) run through `asyncio.to_thread`, so they do not block polling. Step 1 needs no new package: long polling also goes through `requests` in a thread. aiohttp is added in step 3 when the web server arrives.

**Alert dedupe** — A per-category in-memory flag. The first failed crawl sends the admin alert as today. Later failures only log. The first success after a failure sends a short "recovered" message.

**Dependencies** — Add `requirements.txt` pinning the versions running on the server: supabase 2.31.0, requests 2.31.0, beautifulsoup4 4.12.3, python-dotenv 1.2.2. Add `.venv/` to `.gitignore`.

**Service** — `/etc/systemd/system/yu-notice-bot.service`: `User=yubot`, `WorkingDirectory=/srv/yu-notice-bot`, `ExecStart=/srv/yu-notice-bot/.venv/bin/python telegram_bot.py`, `Restart=always`, `RestartSec=5`, `TimeoutStopSec=120` (SIGTERM cancels the loops and the running crawl thread finishes first). Logs keep going to `bot_run.log` (RotatingFileHandler, unchanged) and to journald.

**Cutover** — In one step: `systemctl enable --now yu-notice-bot` and `rm /etc/cron.d/yu-notice-bot`. Then send `/start` from Telegram and confirm the reply arrives in seconds.

**Test** — One test file for the next-run-time function: weekday inside the window, 17:50 → next day 09:00, Friday evening → Monday 09:00, exact 10-minute boundary.

## Calls made by the builder (Claude), not the user

- Long polling via `requests` in a thread for step 1; aiohttp deferred to step 3.
- Recovery message added to the alert dedupe.
- If the service is stopped in the middle of sending, `last_notices.json` may not be saved, and those notices can be sent again on the next run. Mitigated: a SIGTERM handler lets the running crawl finish within `TimeoutStopSec=120`.
- Only the scheduler gets a test in this step.
