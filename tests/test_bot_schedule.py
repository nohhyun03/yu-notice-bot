import unittest
from datetime import datetime, timezone

from bot_schedule import KST, next_run_time


def kst(y, m, d, h, mi, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=KST)


class NextRunTimeTest(unittest.TestCase):
    # 2026-11-23 is a Monday.

    def test_inside_window_rounds_up(self):
        self.assertEqual(next_run_time(kst(2026, 11, 23, 10, 3)), kst(2026, 11, 23, 10, 10))

    def test_exact_boundary_moves_to_next_slot(self):
        self.assertEqual(next_run_time(kst(2026, 11, 23, 10, 10)), kst(2026, 11, 23, 10, 20))

    def test_before_window_goes_to_nine(self):
        self.assertEqual(next_run_time(kst(2026, 11, 23, 8, 59)), kst(2026, 11, 23, 9, 0))

    def test_last_slot_then_next_morning(self):
        self.assertEqual(next_run_time(kst(2026, 11, 23, 17, 50)), kst(2026, 11, 24, 9, 0))
        self.assertEqual(next_run_time(kst(2026, 11, 23, 17, 45)), kst(2026, 11, 23, 17, 50))

    def test_friday_evening_goes_to_monday(self):
        self.assertEqual(next_run_time(kst(2026, 11, 27, 18, 0)), kst(2026, 11, 30, 9, 0))

    def test_saturday_goes_to_monday(self):
        self.assertEqual(next_run_time(kst(2026, 11, 28, 12, 0)), kst(2026, 11, 30, 9, 0))

    def test_utc_input_is_converted(self):
        utc = datetime(2026, 11, 23, 1, 3, tzinfo=timezone.utc)  # 10:03 KST
        self.assertEqual(next_run_time(utc), kst(2026, 11, 23, 10, 10))


if __name__ == "__main__":
    unittest.main()
