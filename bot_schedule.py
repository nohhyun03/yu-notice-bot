from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# Notices are only posted on weekdays during office hours, so crawl Mon-Fri 09:00-17:50.
FIRST_HOUR = 9
LAST_HOUR = 17
STEP_MINUTES = 10


def next_run_time(now: datetime) -> datetime:
    """Return the first crawl slot strictly after `now`, in KST."""
    now = now.astimezone(KST)
    candidate = now.replace(minute=now.minute - now.minute % STEP_MINUTES, second=0, microsecond=0)
    candidate += timedelta(minutes=STEP_MINUTES)

    while True:
        is_weekday = candidate.weekday() < 5
        if is_weekday and FIRST_HOUR <= candidate.hour <= LAST_HOUR:
            return candidate
        if is_weekday and candidate.hour < FIRST_HOUR:
            candidate = candidate.replace(hour=FIRST_HOUR, minute=0)
        else:
            candidate = (candidate + timedelta(days=1)).replace(hour=FIRST_HOUR, minute=0)
