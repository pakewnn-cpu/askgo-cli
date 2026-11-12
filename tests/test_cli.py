"""CLI argument parsing and the port helper."""
import unittest

from askgo.cli import _port_from_url, build_parser


class TestParser(unittest.TestCase):
    def test_ask_with_flags(self):
        args = build_parser().parse_args(
            ["ask", "hello", "--model", "gpt-x", "--no-save-media",
             "--new-session", "--headed"])
        self.assertEqual(args.cmd, "ask")
        self.assertEqual(args.prompt, "hello")
        self.assertEqual(args.model, "gpt-x")
        self.assertTrue(args.no_save_media)
        self.assertTrue(args.new_session)
        self.assertTrue(args.headed)

    def test_serve_timeout_default(self):
        args = build_parser().parse_args(["serve"])
        self.assertEqual(args.cmd, "serve")
        self.assertEqual(args.serve_timeout, 0)

    def test_missing_command_fails(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])

    def test_global_flags(self):
        args = build_parser().parse_args(
            ["--base-url", "https://example.com/", "--timeout", "5000",
             "ask", "hi"])
        self.assertEqual(args.base_url, "https://example.com/")
        self.assertEqual(args.timeout, 5000)


class TestPortFromUrl(unittest.TestCase):
    def test_default_port(self):
        self.assertEqual(_port_from_url("http://127.0.0.1:9222"), 9222)

    def test_missing_port_falls_back(self):
        self.assertEqual(_port_from_url("http://127.0.0.1"), 9222)


if __name__ == "__main__":
    unittest.main()
