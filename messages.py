from html import escape

HELP_TEXT = (
    "<b>📖 사용 가능한 명령어</b>\n\n"
    "/start - 알림 설정·스크랩 보관함 열기 버튼 받기\n"
    "/help - 이 도움말 보기\n\n"
    "<b>그 밖의 기능</b>\n"
    "• 채팅창 왼쪽 아래 \"설정\" 버튼: 알림 설정·스크랩 보관함 바로 열기\n"
    "• 새 공지 메시지의 \"📌 이 공지 스크랩하기\" 버튼: 보관함에 바로 저장"
)


def format_notice_message(category_name, post):
    # Telegram parse_mode=HTML rejects the whole message on a stray "<" or "&", so escape crawled text.
    return (
        f"<b>🚨 [{escape(category_name)} 새 공지!]</b>\n\n"
        f"{escape(post['title'])}\n\n"
        f"👉 <a href='{escape(post['link'], quote=True)}'>공지 본문 바로가기</a>"
    )
