import unittest

from messages import HELP_TEXT, format_notice_message


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
