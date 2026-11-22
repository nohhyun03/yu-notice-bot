# Always-on Bot (Step 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the cron batch `telegram_bot.py` into one always-on process that answers `/start` and `/menu` immediately and still crawls Mon–Fri 09:00–17:50 every 10 minutes.

**Architecture:** One asyncio loop runs two tasks: `poll_loop` (Telegram long polling) and `schedule_loop` (sleep until the next 10-minute slot, then crawl and send). Existing blocking `requests`/Supabase code runs through `asyncio.to_thread`. The slot calculation lives in its own module so it can be tested without env vars or network.

**Tech Stack:** Python 3.12 stdlib (`asyncio`, `zoneinfo`, `unittest`), existing `requests`, `beautifulsoup4`, `supabase`, `python-dotenv`. No new packages.

**Spec:** `docs/superpowers/specs/2026-11-22-always-on-bot-design.md`

## Global Constraints

- Schedule: Monday–Friday, every 10 minutes from 09:00 to 17:50, timezone `Asia/Seoul`.
- No new dependencies in this step. aiohttp waits for step 3.
- Pinned versions: supabase 2.31.0, requests 2.31.0, beautifulsoup4 4.12.3, python-dotenv 1.2.2.
- No change to Supabase tables, `index.html`, message text or categories.
- Polling only; no webhook.
- Tests use stdlib `unittest` (pytest is not installed on the server).
- Never run the bot locally against the production token: a local run would consume production `getUpdates` and could send real notices. Local checks are tests and `py_compile` only; the real run happens on the server at cutover.
- Commits and pushes need the user's OK in chat before they happen.

## Review Focus

1. An exception inside one crawl run (network, Supabase, parsing) must not stop `schedule_loop`; the next slot still runs. → Task 3, `crawl_and_send` wrapped in try/except inside the loop; checked in Task 4 step 3 by log review.
2. Telegram or network outage during long polling must not crash the process; `poll_loop` logs and retries after 5 seconds. → Task 3.
3. Telegram `409 Conflict` (another `getUpdates` consumer, e.g. the cron job still present) must be logged clearly, not crash. → Task 3 logs the HTTP status; Task 4 removes the cron file in the same step as the service start.
4. The slot exactly on a boundary (e.g. 10:10:00) must not run twice. → Task 1 test `test_exact_boundary_moves_to_next_slot`.
5. Startup outside the window (night, weekend) must sleep until the next valid slot, not crawl immediately. → Task 1 tests `test_friday_evening_goes_to_monday`, `test_saturday_goes_to_monday`.

---

### Task 1: Slot calculation

**Files:**
- Create: `bot_schedule.py`
- Test: `tests/test_bot_schedule.py` (plus empty `tests/__init__.py`)

**Interfaces:**
- Produces: `next_run_time(now: datetime) -> datetime` in `bot_schedule.py`. `now` is timezone-aware. Returns the first slot **strictly after** `now`, in `Asia/Seoul`, where a slot is a minute divisible by 10 with seconds 0, on Mon–Fri, between 09:00 and 17:50 inclusive. Also export `KST = ZoneInfo("Asia/Seoul")`.

- [ ] **Step 1: Write the failing tests** in `tests/test_bot_schedule.py` (`unittest.TestCase`), with helper `kst(y, m, d, h, mi, s=0)` building aware datetimes. 2026-11-23 is a Monday.

```python
def test_inside_window_rounds_up(self):
    self.assertEqual(next_run_time(kst(2026,11,23,10,3)), kst(2026,11,23,10,10))
def test_exact_boundary_moves_to_next_slot(self):
    self.assertEqual(next_run_time(kst(2026,11,23,10,10)), kst(2026,11,23,10,20))
def test_before_window_goes_to_nine(self):
    self.assertEqual(next_run_time(kst(2026,11,23,8,59)), kst(2026,11,23,9,0))
def test_last_slot_then_next_morning(self):
    self.assertEqual(next_run_time(kst(2026,11,23,17,50)), kst(2026,11,24,9,0))
    self.assertEqual(next_run_time(kst(2026,11,23,17,45)), kst(2026,11,23,17,50))
def test_friday_evening_goes_to_monday(self):
    self.assertEqual(next_run_time(kst(2026,11,27,18,0)), kst(2026,11,30,9,0))
def test_saturday_goes_to_monday(self):
    self.assertEqual(next_run_time(kst(2026,11,28,12,0)), kst(2026,11,30,9,0))
def test_utc_input_is_converted(self):
    utc = datetime(2026,11,23,1,3, tzinfo=timezone.utc)  # 10:03 KST
    self.assertEqual(next_run_time(utc), kst(2026,11,23,10,10))
```

- [ ] **Step 2: Run tests, expect failure**

Run: `python -m unittest tests.test_bot_schedule -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'bot_schedule'`

- [ ] **Step 3: Implement `next_run_time` in `bot_schedule.py`**

Convert `now` to KST, drop seconds/microseconds, round down to the 10-minute mark, add 10 minutes, then step forward until the candidate falls inside the window (jump to 09:00 of the same day when before 09:00 on a weekday, otherwise to 09:00 of the next day).

- [ ] **Step 4: Run tests, expect pass**

Run: `python -m unittest tests.test_bot_schedule -v`
Expected: 7 tests OK

---

### Task 2: Alert dedupe

**Files:**
- Modify: `telegram_bot.py` — `fetch_notices` (lines 196-240)

**Interfaces:**
- Produces: module-level `failing_categories: set[str]`. `fetch_notices(category_key)` keeps its signature and return value.

- [ ] **Step 1: Change the failure branch** — send the existing admin alert only if `category_key` is not in `failing_categories`, then add it. Log the error every time, as today.
- [ ] **Step 2: Change the success path** — before `return notices`, if `category_key` is in `failing_categories`, remove it and send the admin a message: `<b>✅ [영남대 공지봇 복구]</b>\n\n📌 <b>복구 대상:</b> {info['name']}`.
- [ ] **Step 3: Check it compiles**

Run: `python -m py_compile telegram_bot.py`
Expected: no output

---

### Task 3: Always-on loops

**Files:**
- Modify: `telegram_bot.py` — `process_pending_commands` (153-191) and `main` (268-380)

**Interfaces:**
- Consumes: `next_run_time`, `KST` from `bot_schedule`.
- Produces:
  - `crawl_and_send() -> None`: today's `main()` body from "2. Supabase DB에서…" to the end, without the env check and without `process_pending_commands`.
  - `handle_update(token: str, update: dict) -> None`: the per-update body of today's loop (`/start`, `/menu` → `send_menu`).
  - `async poll_loop(token: str) -> None`
  - `async schedule_loop() -> None`
  - `async run() -> None`: `asyncio.gather(poll_loop(TELEGRAM_TOKEN), schedule_loop())`.
  - `main()`: env check as today, then `asyncio.run(run())`.

- [ ] **Step 1: Split out `crawl_and_send` and `handle_update`**; delete `process_pending_commands`.
- [ ] **Step 2: Write `poll_loop`** — call `deleteWebhook` once. Then forever: `requests.get(getUpdates, params={"offset": offset, "timeout": 50}, timeout=60)` via `asyncio.to_thread`; on HTTP 200 call `handle_update` for each update (in a thread) and set `offset = update_id + 1`; on any other status log `⚠️ getUpdates HTTP {status}: {body[:200]}` and sleep 5; on exception log it and sleep 5. Start with `offset = None`.
- [ ] **Step 3: Write `schedule_loop`** — forever: `target = next_run_time(datetime.now(KST))`, log `⏰ 다음 수집 예정: {target:%Y-%m-%d %H:%M}`, sleep `(target - now).total_seconds()`, then `await asyncio.to_thread(crawl_and_send)` inside `try/except Exception` that logs `🚨 수집 실행 중 예외: {e}` and continues.
- [ ] **Step 4: Update `main`** as in Interfaces; replace the start log text with `🤖 영남대 공지봇 상시 실행 시작 (Supabase 연동)...`.
- [ ] **Step 5: Check compile and tests**

Run: `python -m py_compile telegram_bot.py bot_schedule.py && python -m unittest discover -s tests -v`
Expected: no compile output, 7 tests OK

---

### Task 4: Packaging, service and cutover

**Files:**
- Create: `requirements.txt`, `deploy/yu-notice-bot.service`
- Modify: `.gitignore` (add `.venv/`), `README.md` section "3. 크론탭(Crontab) 주기 배치 등록" → replace with systemd instructions

**Interfaces:**
- Consumes: `main()` from Task 3 as the entry point.

- [ ] **Step 1: Write `requirements.txt`** with the four pinned versions from Global Constraints.
- [ ] **Step 2: Write `deploy/yu-notice-bot.service`** — `[Unit] After=network-online.target`, `Wants=network-online.target`; `[Service] User=yubot`, `WorkingDirectory=/srv/yu-notice-bot`, `ExecStart=/srv/yu-notice-bot/.venv/bin/python telegram_bot.py`, `Restart=always`, `RestartSec=5`, `TimeoutStopSec=60`; `[Install] WantedBy=multi-user.target`.
- [ ] **Step 3: Commit and push** (ask the user first)

```bash
git add bot_schedule.py tests/ telegram_bot.py requirements.txt deploy/ .gitignore README.md docs/superpowers/
git commit -m "feat: run bot as always-on service with instant command replies"
git push origin main
```

- [ ] **Step 4: Deploy on ncp-micro**

```bash
cd /srv/yu-notice-bot && runuser -u yubot -- git pull
cp deploy/yu-notice-bot.service /etc/systemd/system/ && systemctl daemon-reload
rm /etc/cron.d/yu-notice-bot && systemctl enable --now yu-notice-bot
```

Expected: `systemctl is-active yu-notice-bot` → `active`; `ls /etc/cron.d/yu-notice-bot` → not found.

- [ ] **Step 5: Verify**
  - `tail bot_run.log` shows `상시 실행 시작` and `⏰ 다음 수집 예정: <next weekday slot>`.
  - User sends `/start` in Telegram → menu reply within a few seconds; log shows the message.
  - `systemctl restart yu-notice-bot` → comes back `active`.
  - Next weekday slot (2026-11-23 09:00): log shows a crawl run.
