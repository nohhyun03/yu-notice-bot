# /help command, remove /menu — short design

Date: 2026-11-22
Status: approved by the user in chat on 2026-11-22

- **Why:** `/menu` duplicates the chat menu button ("설정") and `/start`. Users have no way to discover what the bot can do; the bot registers no command list.
- **Goal:** `/help` replies with the available commands and the two button features. `/menu` is no longer handled. `/start` unchanged.
- **Non-goals:** no new features behind the commands; no change to the mini app.
- **Approach:** help text is a constant `HELP_TEXT` in `messages.py` (HTML parse mode), sent by `handle_update` for `/help`. Only one sensible way, so no alternatives.
- **Builder's calls (Claude):** register `/start` and `/help` once with `setMyCommands` at deploy so they appear in Telegram's `/` autocomplete; one test checks the help text lists `/start` and `/help` and not `/menu`.
