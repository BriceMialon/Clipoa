import time
import unittest

from core.antigravity_bridge import is_quota_error, parse_reset_seconds, scan_quota_errors


class AntigravityQuotaTests(unittest.TestCase):
    def test_parse_reset(self):
        self.assertEqual(parse_reset_seconds("Individual quota reached. Resets in 2h44m31s."), 2 * 3600 + 44 * 60 + 31)
        self.assertEqual(parse_reset_seconds("Resets in 3d4h"), 3 * 86400 + 4 * 3600)
        self.assertIsNone(parse_reset_seconds("tout va bien"))

    def test_is_quota_error(self):
        self.assertTrue(is_quota_error("RESOURCE_EXHAUSTED (code 429): Individual quota reached."))
        self.assertFalse(is_quota_error("weekly plan generator"))

    def test_scan_logs_recent_error_gives_future_reset(self):
        now = time.time()
        lt = time.localtime(now - 600)
        stamp = time.strftime("E%m%d %H:%M:%S", lt)
        line = stamp + ".2 1 errorreport.go:273] RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 1h0m0s."
        reset_at = scan_quota_errors(["I0101 00:00:00 bruit", line], now=now)
        self.assertIsNotNone(reset_at)
        self.assertGreater(reset_at, now + 2900)
        self.assertLess(reset_at, now + 3100)


if __name__ == "__main__":
    unittest.main()
