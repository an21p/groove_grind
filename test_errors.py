import unittest
from beatport.errors import (
    BeatportError, BeatportUnavailable, BeatportRateLimited, BeatportAuthError,
)


class ErrorTaxonomyTest(unittest.TestCase):
    def test_attributes(self):
        cases = [
            (BeatportUnavailable, "unavailable", 503),
            (BeatportRateLimited, "rate_limited", 429),
            (BeatportAuthError, "auth", 502),
        ]
        for cls, code, status in cases:
            with self.subTest(cls=cls.__name__):
                e = cls()
                self.assertIsInstance(e, BeatportError)
                self.assertEqual(e.code, code)
                self.assertEqual(e.http_status, status)
                self.assertTrue(e.user_message)
        base = BeatportError()
        self.assertEqual(base.code, "error")
        self.assertEqual(base.http_status, 502)
        self.assertTrue(base.user_message)

    def test_custom_message_does_not_change_user_message(self):
        e = BeatportUnavailable("internal detail HTTP 500")
        self.assertEqual(str(e), "internal detail HTTP 500")
        self.assertIn("unavailable", e.user_message.lower())


if __name__ == "__main__":
    unittest.main()
