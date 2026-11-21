"""Tests for the local file-queue IPC layer (askgo/ipc.py).

This module had no coverage. The tests exercise the pure, deterministic
logic -- the path helpers, the request/response file contract, the timeout
and cleanup path, and process_request's success / empty-reply / new-session /
model-fallback / unexpected-error branches -- with a tiny fake client, so no
browser (and no Playwright) is needed.
"""
import tempfile
import unittest
from pathlib import Path

from askgo import ipc
from askgo.config import Config
from askgo.errors import EXIT_CLIENT, EXIT_OK, AskGoError


class FakeClient:
    """Stand-in for AskGoClient: records the calls it gets and returns
    canned values, so process_request can be tested without a real browser."""

    def __init__(self, text="hello", media=None, model="gpt-x"):
        self._text = text
        self._media = [] if media is None else media
        self._model = model
        self.calls = []
        self.new_session_called = False

    def start_new_conversation(self):
        self.new_session_called = True
        self.calls.append("new_conversation")

    def select_model(self, model):
        self.calls.append(f"select_model:{model}")
        return self._model

    def send(self, prompt):
        self.calls.append(f"send:{prompt}")

    def wait_for_reply(self):
        return self._text

    def extract_media(self, save=True):
        self.calls.append(f"extract_media:{save}")
        return self._media

    def _shot(self, tag):
        return f"debug/{tag}.png"


class RaisingClient(FakeClient):
    """A client whose reply step blows up, to exercise the catch-all branch."""

    def wait_for_reply(self):
        raise RuntimeError("boom")


class TestPathHelpers(unittest.TestCase):
    def test_paths_live_under_askgo_dir(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(state_file=Path(d) / ".askgo" / "storage_state.json")
            req = ipc._req_path(cfg)
            self.assertEqual(req.name, "ipc_req.json")
            self.assertEqual(req.parent, Path(d) / ".askgo")
            resp = ipc._resp_path(cfg, "abc123")
            self.assertEqual(resp.name, "ipc_resp_abc123.json")
            self.assertEqual(resp.parent, req.parent)
            # _ipc_dir creates the folder and hands it back
            self.assertTrue(ipc._ipc_dir(cfg).exists())
            self.assertEqual(ipc._ipc_dir(cfg), req.parent)


class TestSendRequest(unittest.TestCase):
    def test_times_out_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(state_file=Path(d) / ".askgo" / "storage_state.json")
            with self.assertRaises(AskGoError) as ctx:
                ipc.send_request(cfg, "hi", "gpt-x",
                                 new_session=False, save_media=True,
                                 timeout_s=0.1)
            self.assertEqual(ctx.exception.step, "ipc_wait")
            self.assertEqual(ctx.exception.exit_code, EXIT_CLIENT)
            # the pending request file is removed on timeout
            self.assertFalse(ipc._req_path(cfg).exists())


class TestProcessRequest(unittest.TestCase):
    def _cfg(self, default_model="default-model"):
        return Config(default_model=default_model)

    def test_success_sets_result_and_exit_code(self):
        cfg = self._cfg()
        client = FakeClient(text="the answer",
                            media=[{"type": "image", "ok": True}],
                            model="gpt-x")
        result, code = ipc.process_request(
            cfg, client, {"prompt": "hi", "model": "gpt-x"})
        self.assertTrue(result.ok)
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result.model, "gpt-x")
        self.assertEqual(result.reply, "the answer")
        self.assertEqual(len(result.media), 1)
        self.assertIn("select_model:gpt-x", client.calls)

    def test_empty_reply_is_a_client_error(self):
        cfg = self._cfg()
        client = FakeClient(text="", media=[])
        result, code = ipc.process_request(cfg, client, {"prompt": "hi"})
        self.assertFalse(result.ok)
        self.assertEqual(code, EXIT_CLIENT)
        self.assertIn("empty", result.error.lower())
        self.assertEqual(result.debug.get("step"), "extract_text")

    def test_new_session_starts_conversation_first(self):
        cfg = self._cfg()
        client = FakeClient(text="hi")
        ipc.process_request(cfg, client, {"prompt": "hi", "new_session": True})
        self.assertTrue(client.new_session_called)
        self.assertLess(
            client.calls.index("new_conversation"),
            client.calls.index("select_model:default-model"),
        )

    def test_model_falls_back_to_default(self):
        cfg = self._cfg(default_model="default-model")
        client = FakeClient(text="hi")
        ipc.process_request(cfg, client, {"prompt": "hi"})
        self.assertIn("select_model:default-model", client.calls)

    def test_unexpected_error_is_captured(self):
        cfg = self._cfg()
        result, code = ipc.process_request(cfg, RaisingClient(), {"prompt": "hi"})
        self.assertFalse(result.ok)
        self.assertEqual(code, EXIT_CLIENT)
        self.assertTrue(result.error.startswith("unexpected error"))
        self.assertEqual(result.debug.get("step"), "process_request")


if __name__ == "__main__":
    unittest.main()
