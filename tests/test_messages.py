import unittest
from datetime import datetime

from bot_schedule import KST
from messages import HELP_TEXT, format_notice_message, format_status

COUNTS = {"subscribers": 3, "bookmarks": 3}


def kst(h, mi, day=23):  # 2026-11-23 is a Monday
    return datetime(2026, 11, day, h, mi, tzinfo=KST)


def status(now, last_crawl, failing=(), started=None):
    return format_status(now, started or kst(9, 0), last_crawl, kst(23, 59), list(failing), COUNTS, "1.4G", "540MB")


def crawl(h, mi, ok=True, new=0, error=None):
    return {"time": kst(h, mi), "ok": ok, "new": new, "error": error}


class StatusTest(unittest.TestCase):
    def test_healthy(self):
        text = status(kst(10, 5), crawl(10, 0, new=2))
        self.assertTrue(text.startswith("✅"), text)
        self.assertIn("성공 (새 공지 2건)", text)
        self.assertIn("구독자 3명 · 스크랩 3건", text)
        self.assertIn("장애 중인 게시판: 없음", text)

    def test_failing_board_is_warning(self):
        text = status(kst(10, 5), crawl(10, 0), failing=["컴퓨터학부 공지사항"])
        self.assertTrue(text.startswith("⚠️"), text)
        self.assertIn("컴퓨터학부 공지사항", text)

    def test_stale_crawl_in_window_is_warning(self):
        self.assertTrue(status(kst(10, 40), crawl(10, 0)).startswith("⚠️"))

    def test_old_crawl_outside_window_is_ok(self):
        self.assertTrue(status(kst(22, 0), crawl(17, 50)).startswith("✅"))

    def test_no_crawl_yet_uses_start_time(self):
        text = status(kst(10, 5), None, started=kst(10, 0))
        self.assertTrue(text.startswith("✅"), text)
        self.assertIn("아직 없음", text)
        self.assertTrue(status(kst(10, 30), None, started=kst(10, 0)).startswith("⚠️"))

    def test_failed_crawl_error_is_escaped(self):
        text = status(kst(10, 5), crawl(10, 0, ok=False, error="<html> 503"))
        self.assertTrue(text.startswith("⚠️"), text)
        self.assertIn("&lt;html&gt; 503", text)


class HelpTextTest(unittest.TestCase):
    def test_lists_supported_commands_only(self):
        self.assertIn("/start", HELP_TEXT)
        self.assertIn("/help", HELP_TEXT)
        self.assertNotIn("/menu", HELP_TEXT)


class FormatNoticeMessageTest(unittest.TestCase):
    def test_title_with_html_characters_is_escaped(self):
        post = {"title": "<2026> 장학금 & 근로 안내", "link": "https://www.yu.ac.kr/a?x=1&y=2"}
        text = format_notice_message("영대소식", post)
        self.assertIn("&lt;2026&gt; 장학금 &amp; 근로 안내", text)
        self.assertIn("href='https://www.yu.ac.kr/a?x=1&amp;y=2'", text)
        self.assertNotIn("<2026>", text)

    def test_quote_in_link_cannot_break_attribute(self):
        text = format_notice_message("영대소식", {"title": "t", "link": "https://x/'><b>x"})
        self.assertNotIn("'><b>", text)

    def test_plain_title_unchanged(self):
        text = format_notice_message("영대소식", {"title": "일반 공지", "link": "https://x/1"})
        self.assertEqual(
            text,
            "<b>🚨 [영대소식 새 공지!]</b>\n\n일반 공지\n\n👉 <a href='https://x/1'>공지 본문 바로가기</a>",
        )


if __name__ == "__main__":
    unittest.main()
