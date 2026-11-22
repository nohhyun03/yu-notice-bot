from datetime import timedelta
from html import escape

HELP_TEXT = (
    "<b>📖 사용 가능한 명령어</b>\n\n"
    "/start - 알림 설정·스크랩 보관함 열기 버튼 받기\n"
    "/help - 이 도움말 보기\n\n"
    "<b>그 밖의 기능</b>\n"
    "• 채팅창 왼쪽 아래 \"설정\" 버튼: 알림 설정·스크랩 보관함 바로 열기\n"
    "• 새 공지 메시지의 \"📌 이 공지 스크랩하기\" 버튼: 보관함에 바로 저장"
)


# Appended to /help only for the admin; others never see admin commands.
ADMIN_HELP_TEXT = "\n\n<b>🔧 관리자 기능</b>\n/status - 봇·서버 상태 확인"

UNKNOWN_REPLY ="지원하지 않는 명령어입니다. /help 를 보내 보세요."

STALE_AFTER =timedelta(minutes=20)  # two missed 10-minute crawl slots


def _in_crawl_window(now):
    return now.weekday() < 5 and 9 <= now.hour < 18


def _duration(delta):
    minutes = int(delta.total_seconds() // 60)
    days, rest = divmod(minutes, 24 * 60)
    text = f"{rest // 60}시간 {rest % 60}분"
    return f"{days}일 {text}" if days else text


def format_status(now, started_at, last_crawl, next_run, failing_names, counts, disk_free, mem_free):
    last_ref = last_crawl["time"] if last_crawl else started_at
    stale = _in_crawl_window(now) and now - last_ref > STALE_AFTER
    crawl_failed = bool(last_crawl) and not last_crawl["ok"]
    healthy = not (failing_names or crawl_failed or stale)

    if last_crawl is None:
        crawl_line = "아직 없음"
    elif last_crawl["ok"]:
        crawl_line = f"{last_crawl['time']:%m/%d %H:%M} — 성공 (새 공지 {last_crawl['new']}건)"
    else:
        crawl_line = f"{last_crawl['time']:%m/%d %H:%M} — 실패: {escape(last_crawl['error'] or '')}"

    header = "✅ 봇 정상 동작 중" if healthy else "⚠️ 점검 필요"
    return "\n".join([
        f"{header} ({now:%H:%M:%S})",
        f"⏱ 가동 시간: {_duration(now - started_at)}",
        f"📥 마지막 수집: {crawl_line}" + (" (지연)" if stale else ""),
        f"⏰ 다음 수집: {next_run:%m/%d %H:%M}",
        f"⚠️ 장애 중인 게시판: {', '.join(escape(n) for n in failing_names) or '없음'}",
        f"👥 구독자 {counts['subscribers']}명 · 스크랩 {counts['bookmarks']}건",
        f"💾 디스크 여유 {disk_free} · 메모리 여유 {mem_free}",
    ])


def format_notice_message(category_name, post):
    # Telegram parse_mode=HTML rejects the whole message on a stray "<" or "&", so escape crawled text.
    return (
        f"<b>🚨 [{escape(category_name)} 새 공지!]</b>\n\n"
        f"{escape(post['title'])}\n\n"
        f"👉 <a href='{escape(post['link'], quote=True)}'>공지 본문 바로가기</a>"
    )
