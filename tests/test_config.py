"""Config: defaults, .env loading, and CLI-style overrides.

These run with plain ``python -m unittest`` (no third-party deps) and also
under pytest.
"""
import os
import tempfile
import unittest
from pathlib import Path

from askgo.config import Config, _load_dotenv


class TestDefaults(unittest.TestCase):
    def test_defaults_when_no_env(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config.from_env(env_file=Path(d) / "does-not-exist.env")
            self.assertEqual(cfg.base_url, "https://askgo.co")
            self.assertTrue(cfg.headless)
            self.assertEqual(cfg.timeout_ms, 60000)
            self.assertEqual(cfg.serve_url, "http://127.0.0.1:9222")
            self.assertEqual(cfg.login_timeout_s, 600)

    def test_base_url_trailing_slash_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("ASKGO_BASE_URL=https://askgo.co/\n", encoding="utf-8")
            cfg = Config.from_env(env_file=env)
            self.assertEqual(cfg.base_url, "https://askgo.co")


class TestEnvOverrides(unittest.TestCase):
    def test_headless_false(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text('ASKGO_HEADLESS=0\nASKGO_TIMEOUT_MS=12000\n',
                           encoding="utf-8")
            cfg = Config.from_env(env_file=env)
            self.assertFalse(cfg.headless)
            self.assertEqual(cfg.timeout_ms, 12000)

    def test_quoted_value_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text('ASKGO_DEFAULT_MODEL="gpt-x"\n', encoding="utf-8")
            cfg = Config.from_env(env_file=env)
            self.assertEqual(cfg.default_model, "gpt-x")

    def test_ensure_dirs_creates_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config.from_env(env_file=Path(d) / "none.env")
            self.assertTrue(cfg.state_file.parent.exists())
            self.assertTrue(cfg.media_dir.exists())
            self.assertTrue(cfg.debug_dir.exists())


class TestDotenvLoader(unittest.TestCase):
    def test_does_not_override_real_env(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("ASKGO_BASE_URL=https://from-file.example\n",
                           encoding="utf-8")
            os.environ["ASKGO_BASE_URL"] = "https://from-real.example"
            try:
                _load_dotenv(env)
                # real env wins; the loader only sets defaults
                self.assertEqual(os.environ["ASKGO_BASE_URL"],
                                 "https://from-real.example")
            finally:
                del os.environ["ASKGO_BASE_URL"]


if __name__ == "__main__":
    unittest.main()
