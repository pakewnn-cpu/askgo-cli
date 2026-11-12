"""Local file-queue IPC between a long-lived `serve` and short-lived `ask`.

Each `ask` is a separate process that reconnects over CDP, so it cannot see the
conversation page the previous `ask` used -- multi-turn context and the in-memory
model selection do not survive. The fix: `serve` owns the single conversation
page, and each `ask` hands its request to `serve` through a file queue. `serve`
processes the request on its own page (where context lives) and writes the
response back. Sequential by design: single user, low frequency, no concurrency.

Files (under the .askgo dir, next to storage_state.json):
    ipc_req.json          one pending request (atomic tmp+rename)
    ipc_resp_<id>.json    the matching response (atomic tmp+rename)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from .config import Config
from .errors import EXIT_CLIENT, EXIT_OK, AskGoError, Result

POLL_INTERVAL_S = 0.2


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------
def _ipc_dir(cfg: Config) -> Path:
    d = cfg.state_file.parent  # .askgo
    d.mkdir(parents=True, exist_ok=True)
    return d


def _req_path(cfg: Config) -> Path:
    return _ipc_dir(cfg) / "ipc_req.json"


def _resp_path(cfg: Config, req_id: str) -> Path:
    return _ipc_dir(cfg) / f"ipc_resp_{req_id}.json"


# --------------------------------------------------------------------------
# client side
# --------------------------------------------------------------------------
def send_request(
    cfg: Config,
    prompt: str,
    model: str,
    new_session: bool,
    save_media: bool,
    timeout_s: float = 360.0,
) -> dict:
    """Write a request file and block until `serve` writes the response.

    Returns the response dict (a Result payload plus `exit_code`). On timeout the
    request's own response file (if any) is cleaned up and an AskGoError is raised.
    """
    req_id = uuid.uuid4().hex
    req = {
        "id": req_id,
        "prompt": prompt,
        "model": model,
        "new_session": new_session,
        "save_media": save_media,
        "ts": time.time(),
    }
    req_path = _req_path(cfg)
    tmp = req_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, req_path)  # atomic: serve always sees a complete file

    resp_path = _resp_path(cfg, req_id)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if resp_path.exists():
            try:
                data = json.loads(resp_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                time.sleep(POLL_INTERVAL_S)
                continue
            try:
                resp_path.unlink()
            except OSError:
                pass
            return data
        time.sleep(POLL_INTERVAL_S)

    # Timed out: best-effort cleanup of our own request/response, then fail.
    for p in (req_path, resp_path):
        try:
            p.unlink()
        except OSError:
            pass
    raise AskGoError(
        f"serve did not respond within {timeout_s:g}s",
        exit_code=EXIT_CLIENT,
        step="ipc_wait",
    )


# --------------------------------------------------------------------------
# server side
# --------------------------------------------------------------------------
def process_request(cfg: Config, client, data: dict) -> tuple[Result, int]:
    """Run one request on `client`'s page and return (Result, exit_code)."""
    result = Result()
    try:
        if data.get("new_session"):
            client.start_new_conversation()
        model = data.get("model") or cfg.default_model
        chosen = client.select_model(model)
        client.send(data.get("prompt", ""))
        text = client.wait_for_reply()
        media = client.extract_media(save=data.get("save_media", True))
        if not text and not media:
            shot = client._shot("empty_reply")
            raise AskGoError(
                "Reply was empty (no text and no media).",
                exit_code=EXIT_CLIENT,
                step="extract_text",
                selector="assistant_message",
                screenshot=shot,
            )
        result.ok = True
        result.model = chosen or None
        result.reply = text or None
        result.media = media
        exit_code = EXIT_OK
    except AskGoError as exc:
        result.ok = False
        result.error = exc.message
        result.debug = {
            "step": exc.step,
            "selector": exc.selector,
            "screenshot": exc.screenshot,
        }
        exit_code = exc.exit_code
    except Exception as exc:  # noqa: BLE001 - never crash the serve loop
        result.ok = False
        result.error = f"unexpected error: {exc}"
        result.debug = {"step": "process_request"}
        exit_code = EXIT_CLIENT
    return result, exit_code


def serve_loop(cfg: Config, client, timeout_s: float = 0.0) -> None:
    """Poll for request files and service them on `client`'s page.

    Runs until Ctrl-C, or until `timeout_s` elapses when it is > 0.
    """
    req_path = _req_path(cfg)
    deadline = (time.time() + timeout_s) if timeout_s and timeout_s > 0 else None
    while True:
        if deadline is not None and time.time() > deadline:
            return
        if req_path.exists():
            data = None
            try:
                data = json.loads(req_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = None
            # Consume the request regardless of parse success so a malformed file
            # does not wedge the loop.
            try:
                req_path.unlink()
            except OSError:
                pass
            if data and data.get("id"):
                result, exit_code = process_request(cfg, client, data)
                payload = result.to_dict()
                payload["exit_code"] = exit_code
                resp_path = _resp_path(cfg, data["id"])
                tmp = resp_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                               encoding="utf-8")
                os.replace(tmp, resp_path)  # atomic: client sees a complete file
        else:
            time.sleep(POLL_INTERVAL_S)
