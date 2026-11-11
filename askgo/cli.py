"""Command-line entry point.

    python -m askgo.cli ask "prompt" [--model M] [--no-save-media] [--new-session]
    python -m askgo.cli login
    python -m askgo.cli serve
    python -m askgo.cli stop
    python -m askgo.cli probe

stdout  : a single JSON object (the Result) on every path.
stderr  : human-readable logs / warnings only.
exit    : 0 ok | 1 client/generation error | 2 not logged in.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from .config import Config
from .selectors import Selectors
from .session import Session
from .client import AskGoClient
from . import ipc
from .errors import AskGoError, Result, EXIT_OK, EXIT_CLIENT, EXIT_NOT_LOGGED_IN

PID_FILE = Path(".askgo/serve.pid")


def _log(msg: str) -> None:
    sys.stderr.write(f"[askgo] {msg}\n")


# --------------------------------------------------------------------------
# serve helpers
# --------------------------------------------------------------------------
def _port_from_url(url: str) -> int:
    p = urlparse(url)
    return p.port or 9222


def _serve_reachable(cfg: Config) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(cfg.serve_url + "/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------
def cmd_login(cfg: Config, args) -> Result:
    """Interactive first-time login; saves storage_state. Always headed."""
    result = Result()
    with Session(cfg) as s:
        # force headed for interactive login
        s.browser = s._pw.chromium.launch(headless=False)
        s._owns_browser = True
        s.context = s.browser.new_context()
        s.page = s.context.new_page()
        s.ensure_login(interactive=True)
    # Verify the saved state captured a real session.
    # AskGo stores auth in sessionStorage (JWT token), not cookies.
    auth_path = cfg.auth_state_file
    if auth_path.exists():
        try:
            saved = json.loads(auth_path.read_text(encoding="utf-8"))
            token = saved.get("token", "")
            if token and len(token) > 50:
                _log(f"login token saved to {auth_path} ({len(token)} chars)")
                result.ok = True
                result.session_id = "login-saved"
                return result
        except (json.JSONDecodeError, OSError):
            pass
    # Fall back to checking storage_state cookies
    state_path = cfg.state_file
    try:
        size = state_path.stat().st_size if state_path.exists() else 0
    except OSError:
        size = 0
    if size < 100:
        result.ok = False
        result.error = ("Login did not capture a session. "
                        "Please run login again and finish sign-in.")
        result.debug = {"step": "login_verify", "state_file": str(state_path),
                        "bytes": size}
        return result
    _log(f"login state saved to {state_path} ({size} bytes)")
    result.ok = True
    result.session_id = "login-saved"
    return result


def cmd_serve(cfg: Config, args) -> Result:
    """Start a long-lived browser for multi-turn `ask` over CDP."""
    result = Result()
    port = _port_from_url(cfg.serve_url)
    with Session(cfg) as s:
        s.browser = s._pw.chromium.launch(
            headless=False,
            args=[f"--remote-debugging-port={port}"],
        )
        s._owns_browser = True
        kwargs = {}
        if cfg.state_file.exists():
            kwargs["storage_state"] = str(cfg.state_file)
        s.context = s.browser.new_context(**kwargs)
        s.page = s.context.new_page()
        s.open_site()
        if s.is_logged_in():
            s.save_state()
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
        _log(f"serve running on {cfg.serve_url} (pid {os.getpid()}); Ctrl-C to stop.")
        client = AskGoClient(s.page, s.context, cfg)
        try:
            ipc.serve_loop(cfg, client, args.serve_timeout)
        except KeyboardInterrupt:
            pass
        finally:
            if PID_FILE.exists():
                PID_FILE.unlink()
    result.ok = True
    result.session_id = "serve"
    return result


def cmd_stop(cfg: Config, args) -> Result:
    result = Result()
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            _log(f"stopped serve pid {pid}")
        except (ValueError, ProcessLookupError, PermissionError) as exc:
            result.ok = False
            result.error = f"could not stop serve: {exc}"
            return result
        PID_FILE.unlink()
    else:
        _log("no serve pidfile; nothing to stop.")
    result.ok = True
    return result


def cmd_probe(cfg: Config, args) -> Result:
    """Dump candidate selectors to help fill in selectors.py."""
    result = Result()
    with Session(cfg) as s:
        s.connect_ephemeral()
        s.open_site()
        data = s.page.evaluate(
            """() => {
              const out = {buttons: [], inputs: [], roles: {}, dataAttrs: []};
              document.querySelectorAll('button,[role="button"]').forEach(b => {
                const name = (b.getAttribute('aria-label')||b.textContent||'').trim().slice(0,40);
                out.buttons.push({name, role: b.getAttribute('role')});
              });
              document.querySelectorAll('input,textarea,[contenteditable]').forEach(i => {
                out.inputs.push({tag: i.tagName, placeholder: i.getAttribute('placeholder'),
                  aria: i.getAttribute('aria-label'), role: i.getAttribute('role')});
              });
              document.querySelectorAll('[data-role],[data-message-role],[data-testid]').forEach(e => {
                out.dataAttrs.push({tag: e.tagName,
                  data_role: e.getAttribute('data-role'),
                  data_message_role: e.getAttribute('data-message-role'),
                  data_testid: e.getAttribute('data-testid')});
              });
              return out;
            }"""
        )
        out_path = cfg.debug_dir / f"probe_{int(time.time())}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        _log(f"probe written to {out_path}")
        result.ok = True
        result.debug = {"probe_file": str(out_path)}
        result.reply = json.dumps(data, ensure_ascii=False)
    return result


def cmd_ask(cfg: Config, args) -> tuple[Result, int]:
    cfg.use_serve = args.serve or _serve_reachable(cfg)
    cfg.new_session = args.new_session
    cfg.save_media = not args.no_save_media
    if args.headed:
        cfg.headless = False  # --headed forces a visible browser
    model = args.model or cfg.default_model
    if cfg.use_serve:
        _log(f"dispatching to serve at {cfg.serve_url}")
        data = ipc.send_request(
            cfg, args.prompt, model, cfg.new_session, cfg.save_media, timeout_s=360.0
        )
        result = Result(
            ok=data.get("ok", False),
            model=data.get("model"),
            reply=data.get("reply"),
            media=data.get("media", []),
            error=data.get("error"),
            debug=data.get("debug", {}),
        )
        exit_code = data.get("exit_code", EXIT_OK if result.ok else EXIT_CLIENT)
        return result, exit_code
    # Ephemeral: fresh browser + fresh conversation for this single run.
    result = Result()
    with Session(cfg) as s:
        s.connect_ephemeral()
        s.ensure_login(interactive=False)
        client = AskGoClient(s.page, s.context, cfg)
        if cfg.new_session:
            client.start_new_conversation()
        chosen = client.select_model(model)
        client.send(args.prompt)
        text = client.wait_for_reply()
        media = client.extract_media(save=cfg.save_media)
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
    return result, EXIT_OK


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="askgo", description="Drive askgo.ai via Playwright.")
    p.add_argument("--base-url", dest="base_url")
    p.add_argument("--state-file", dest="state_file")
    p.add_argument("--timeout", dest="timeout", type=int)
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("ask", help="send a prompt and get a reply (JSON on stdout)")
    pa.add_argument("prompt", help="the prompt text")
    pa.add_argument("--model", default="")
    pa.add_argument("--no-save-media", action="store_true", help="return media links only")
    pa.add_argument("--new-session", action="store_true", help="start a fresh conversation")
    pa.add_argument("--serve", action="store_true", help="force connecting to a running serve")
    pa.add_argument("--headed", action="store_true", help="run the browser visibly")

    sub.add_parser("login", help="interactive first-time login; saves state")

    ps = sub.add_parser("serve", help="start a long-lived browser for multi-turn")
    ps.add_argument("--serve-timeout", type=int, default=0, help="auto-stop after N seconds (0=until Ctrl-C)")

    sub.add_parser("stop", help="stop a running serve")

    pp = sub.add_parser("probe", help="dump candidate selectors to debug/")
    pp.add_argument("--headed", action="store_true")

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = Config.from_env()
    if args.base_url:
        cfg.base_url = args.base_url.rstrip("/")
    if args.state_file:
        cfg.state_file = Path(args.state_file)
    if args.timeout:
        cfg.timeout_ms = args.timeout
    cfg.ensure_dirs()

    result = Result()
    exit_code = EXIT_OK
    try:
        if args.cmd == "ask":
            result, exit_code = cmd_ask(cfg, args)
        elif args.cmd == "login":
            result = cmd_login(cfg, args)
            exit_code = EXIT_OK if result.ok else EXIT_CLIENT
        elif args.cmd == "serve":
            result = cmd_serve(cfg, args)
            exit_code = EXIT_OK if result.ok else EXIT_CLIENT
        elif args.cmd == "stop":
            result = cmd_stop(cfg, args)
            exit_code = EXIT_OK if result.ok else EXIT_CLIENT
        elif args.cmd == "probe":
            result = cmd_probe(cfg, args)
            exit_code = EXIT_OK if result.ok else EXIT_CLIENT
    except AskGoError as exc:
        result.ok = False
        result.error = exc.message
        result.debug = {
            "step": exc.step,
            "selector": exc.selector,
            "screenshot": exc.screenshot,
        }
        exit_code = exc.exit_code
    except Exception as exc:  # noqa: BLE001 - never crash without JSON
        result.ok = False
        result.error = f"unexpected error: {exc}"
        exit_code = EXIT_CLIENT

    sys.stdout.write(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
