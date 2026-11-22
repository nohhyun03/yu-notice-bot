from html import escape


def format_notice_message(category_name, post):
    # Telegram parse_mode=HTML rejects the whole message on a stray "<" or "&", so escape crawled text.
    return (
        f"<b>🚨 [{escape(category_name)} 새 공지!]</b>\n\n"
        f"{escape(post['title'])}\n\n"
        f"👉 <a href='{escape(post['link'], quote=True)}'>공지 본문 바로가기</a>"
    )
