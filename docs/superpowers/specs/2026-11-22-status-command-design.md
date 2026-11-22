# Admin /status and replies to unknown messages — short design

Date: 2026-11-22
Status: approved by the user on 2026-11-22

## Intent

The admin (the user, `ADMIN_CHAT_ID`) wants to check from Telegram, without logging into the server, that the bot works. The rule they want: **if the bot does not answer, something is wrong.** That only holds if every message gets an answer while the bot is alive, so unknown messages must get a reply too.

## Goals

- `/status` from the admin always gets a status reply (see format below).
- Any other unsupported message, from anyone, gets: `지원하지 않는 명령어입니다. /help 를 보내 보세요.` This includes `/status` from non-admins (the admin command stays hidden) and non-text messages (stickers, photos).
- The status flags a bot that answers but has stopped crawling.

## Non-goals

- No alert when the server dies (that needs a watcher outside the server; not requested).
- `/status` is not added to the public command list or to `/help`.

## Approaches

| | Summary | Trade-off |
|---|---|---|
| A. `/status` only | Admin command; other messages stay silent. | Simplest, but silence stays ambiguous (typo vs. bot down). |
| **B. `/status` + reply to unknown messages (chosen)** | As A, plus a generic reply to anything unsupported. | A little more code; silence now always means trouble, and users get guidance on typos. |

The user picked B.

## Design

Status message (HTML), header ✅ when healthy, ⚠️ when not:

```
✅ 봇 정상 동작 중 (17:40:12)
⏱ 가동 시간: 2시간 3분
📥 마지막 수집: 11/22 17:30 — 성공 (새 공지 0건)
⏰ 다음 수집: 11/22 17:40
⚠️ 장애 중인 게시판: 없음
👥 구독자 3명 · 스크랩 3건
💾 디스크 여유 1.4G · 메모리 여유 540MB
```

- **Unhealthy (⚠️)** when any board is in `failing_categories`, when the last crawl raised an exception, or when the bot is inside the crawl window (Mon–Fri 09:00–17:59 KST) and the last crawl (or start, if none yet) is more than 20 minutes old.
- "마지막 수집" shows `아직 없음` before the first crawl after a restart; on failure `실패: <error>` (HTML-escaped).
- `crawl_and_send()` returns the number of new notices; `schedule_loop` records time, result and error in a module-level state dict next to `failing_categories`.
- Disk free from `shutil.disk_usage("/")`; memory from `MemAvailable` in `/proc/meminfo` (shows `?` where unavailable, e.g. Windows).
- Admin check: `str(chat_id) == ADMIN_CHAT_ID`. The sender id comes from Telegram's update, so it cannot be forged.

## Builder's calls (Claude)

- Formatting lives in `messages.py` as `format_status(...)`, a pure function with tests for: healthy → ✅; failing board → ⚠️ with its name; stale crawl inside the window → ⚠️; old crawl outside the window (night, weekend) → still ✅.
- 20-minute staleness threshold (two missed slots).
- Unknown-message reply text above; `/help` text unchanged.
- Deploy: commit, push, server pull, restart (about 40 s, outside crawl hours today).
