"""Result serialization and the exit-code contract."""
import unittest

from askgo.errors import (
    EXIT_CLIENT,
    EXIT_NOT_LOGGED_IN,
    EXIT_OK,
    AskGoError,
    Result,
)


class TestExitCodes(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(EXIT_OK, 0)
        self.assertEqual(EXIT_CLIENT, 1)
        self.assertEqual(EXIT_NOT_LOGGED_IN, 2)

    def test_error_defaults_to_client_code(self):
        err = AskGoError("selector missing")
        self.assertEqual(err.exit_code, EXIT_CLIENT)
        self.assertEqual(err.message, "selector missing")
        self.assertIsNone(err.step)

    def test_error_carries_debug_context(self):
        err = AskGoError("boom", exit_code=EXIT_NOT_LOGGED_IN,
                         step="login", selector="input#email",
                         screenshot="debug/x.png")
        self.assertEqual(err.exit_code, EXIT_NOT_LOGGED_IN)
        self.assertEqual(err.step, "login")
        self.assertEqual(err.selector, "input#email")
        self.assertEqual(err.screenshot, "debug/x.png")


class TestResult(unittest.TestCase):
    def test_to_dict_drops_none_fields(self):
        r = Result(ok=True, reply="hello")
        d = r.to_dict()
        self.assertTrue(d["ok"])
        self.assertEqual(d["reply"], "hello")
        self.assertNotIn("model", d)
        self.assertNotIn("session_id", d)
        self.assertEqual(d["media"], [])
        self.assertEqual(d["debug"], {})

    def test_to_dict_sanitizes_bytes(self):
        r = Result(ok=False, error="bad", debug={"raw": b"\xff\x00data"})
        d = r.to_dict()
        self.assertIsInstance(d["debug"]["raw"], str)

    def test_media_item_shape(self):
        r = Result(ok=True, media=[{
            "type": "image", "url": "https://x/y.png",
            "path": "media/image_1.png", "ok": True,
        }])
        d = r.to_dict()
        self.assertEqual(len(d["media"]), 1)
        self.assertTrue(d["media"][0]["ok"])


if __name__ == "__main__":
    unittest.main()
