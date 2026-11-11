"""Browser session + login-state management.

Two connection modes:
    ephemeral : each call launches its own browser context from storage_state.
    serve     : a long-lived browser (started by `serve`) that `ask` connects to
                over CDP, so conversation context survives across calls.
"""
from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
from pathlib import Path

from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    Error as PWError,
)

from .config import Config
from .selectors import Selectors
from .errors import AskGoError, EXIT_NOT_LOGGED_IN, EXIT_CLIENT


class Session:
    def __init__(self, config: Config, selectors: Selectors | None = None):
        self.cfg = config
        self.sel = selectors or Selectors()
        self._pw = sync_playwright().start()
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._owns_browser = False

    # -- lifecycle ----------------------------------------------------------
    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        try:
            if self.context and self._owns_browser:
                self.context.close()
        except PWError:
            pass
        try:
            if self.browser and self._owns_browser:
                self.browser.close()
        except PWError:
            pass
        try:
            self._pw.stop()
        except PWError:
            pass

    # -- connection ---------------------------------------------------------
    def connect_serve(self, new_session: bool = False) -> None:
        """Connect to a running `serve` browser over CDP (multi-turn)."""
        self.browser = self._pw.chromium.connect_over_cdp(self.cfg.serve_url)
        self._owns_browser = False
        self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        if new_session:
            # A brand-new page starts on about:blank, so navigate it into the
            # app first (open_site also re-injects the saved sessionStorage
            # token into this fresh page) before the caller touches the model
            # picker or chat input.
            self.page = self.context.new_page()
            self.open_site()
        else:
            self.page = self._chat_page(self.context)

    def connect_ephemeral(self) -> None:
        self.browser = self._pw.chromium.launch(headless=self.cfg.headless)
        self._owns_browser = True
        kwargs = {}
        if self.cfg.state_file.exists():
            kwargs["storage_state"] = str(self.cfg.state_file)
        if self.cfg.user_agent:
            kwargs["user_agent"] = self.cfg.user_agent
        self.context = self.browser.new_context(**kwargs)
        self.page = self.context.new_page()

    @staticmethod
    def _chat_page(context: BrowserContext) -> Page:
        for p in context.pages:
            if "askgo" in p.url or p.url.startswith("http"):
                return p
        return context.new_page()

    # -- login --------------------------------------------------------------
    def open_site(self) -> None:
        self.page.set_default_timeout(self.cfg.timeout_ms)
        self.page.goto(self.cfg.base_url, wait_until="domcontentloaded")
        # askgo.ai is a landing page that opens the real app (askgo.co) in a new
        # tab via "进入网页版". If we landed there, follow it into the app so the
        # rest of the flow (login detection, chat) runs against the real page.
        try:
            if "askgo.ai" in self.page.url:
                enter = self.page.get_by_text("进入网页版")
                if enter.count():
                    with self.context.expect_page() as np:
                        enter.first.click(timeout=self.cfg.timeout_ms)
                    self.page = np.value
                    self.page.set_default_timeout(self.cfg.timeout_ms)
                    self.page.wait_for_load_state("domcontentloaded")
        except PWError:
            pass
        # The app is an SPA: content renders *after* domcontentloaded. Wait for
        # the chat input (or the "新建聊天" nav) so later steps don't race the
        # render. Without this, login-detection and the probe see an empty page.
        try:
            self.page.get_by_placeholder(self.sel.input_placeholder).first.wait_for(
                state="attached", timeout=self.cfg.timeout_ms)
        except PWError:
            try:
                self.page.get_by_text("新建聊天").first.wait_for(
                    state="attached", timeout=self.cfg.timeout_ms)
            except PWError:
                pass
        # If we have a saved auth token, inject it into sessionStorage.
        self._inject_auth()


    def _inject_auth(self) -> None:
        """Inject saved sessionStorage token into the page after load."""
        auth_file = self.cfg.auth_state_file
        if not auth_file.exists():
            return
        try:
            data = json.loads(auth_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        token = data.get("token", "")
        if not token:
            return
        # Inject token into sessionStorage
        self.page.evaluate(
            "([k, v]) => { sessionStorage.setItem(k, v); }",
            ["token", token]
        )
        # Also inject tokenList if present
        ss = data.get("sessionStorage", {})
        for key, val in ss.items():
            if key != "token":
                self.page.evaluate(
                    "([k, v]) => { sessionStorage.setItem(k, v); }",
                    [key, val if isinstance(val, str) else json.dumps(val)]
                )
        # Reload to apply
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(2000)

    def _scan_frames(self):
        frames = [self.page]
        try:
            frames.extend(self.page.frames)
        except PWError:
            pass
        return frames

    def _dump_probe(self, tag="loop"):
        import json as _json
        probe = {"tag": tag, "url": self.page.url, "frames": 0,
                 "inputs": 0, "contenteditable": 0, "logout": False,
                 "text_snippet": ""}
        try:
            probe["frames"] = len(self.page.frames)
            for fr in self._scan_frames():
                try:
                    probe["inputs"] += fr.locator(
                        "input, textarea, [contenteditable='true']"
                    ).count()
                except PWError:
                    pass
            logout = self.page.get_by_role("button").filter(
                has_text=re.compile(r"退出|log ?out|sign ?out|我的|个人中心", re.I)
            )
            probe["logout"] = bool(logout.count())
            probe["text_snippet"] = (self.page.locator("body").inner_text(timeout=1500)
                                    or "")[:300]
        except PWError:
            pass
        try:
            (self.cfg.debug_dir / "login_probe.json").write_text(
                _json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def is_logged_in(self) -> bool:
        """Detect a *real* logged-in state on askgo.co.

        The chat input ("问我任何问题") is always present even in guest mode,
        so it is NOT a reliable signal. Instead: the app is loaded AND the
        "登录" button is gone AND a user-specific marker is visible
        (e.g. "剩余积分", "我的内容", "升级", "退出", "个人中心").
        """
        try:
            app_loaded = (
                self.page.get_by_text("新建聊天").count()
                or self.page.get_by_placeholder("问我任何问题").count()
            )
        except PWError:
            app_loaded = 0
        if not app_loaded:
            return False
        # A visible "登录 / login" button means we are still in guest mode.
        try:
            lb = self.page.get_by_role("button", name=re.compile(r"登录|log ?in", re.I))
            if lb.count() and lb.first.is_visible(timeout=1000):
                return False
        except PWError:
            pass
        # Check for user-specific markers that only appear when logged in.
        try:
            user_marker = self.page.get_by_text(
                re.compile(r"剩余积分|我的内容|升级|退出|log ?out|sign ?out|个人中心|专业版", re.I)
            )
            if user_marker.count() > 0:
                return True
        except PWError:
            pass
        # Also check sessionStorage for token
        try:
            token = self.page.evaluate("() => sessionStorage.getItem('token')")
            if token and len(token) > 50:
                return True
        except PWError:
            pass
        return False

    def open_login_modal(self):
        """Dismiss notice popups and open the login dialog for the human."""
        try:
            for label in ("知道了", "我知道了", "确定", "关闭"):
                b = self.page.get_by_role("button", name=label)
                if b.count():
                    b.first.click(timeout=1500)
                    break
        except PWError:
            pass
        try:
            lb = self.page.get_by_role("button", name=re.compile(r"登录|log ?in", re.I))
            if lb.count():
                lb.first.click(timeout=3000)
                sys.stderr.write("[askgo] Login dialog opened; please sign in...\n")
        except PWError:
            pass

    def ensure_login(self, interactive: bool = False) -> None:
        """Navigate and confirm a logged-in state.

        Decision is state-file first, so a fresh session with no saved login is
        treated as "not logged in" without trusting the DOM heuristic:

        - state exists & page logged in -> return
        - state exists & page not in    -> expired -> exit 2
        - no state & interactive        -> wait for the human, then save
        - no state & not interactive    -> not logged in -> exit 2
        """
        self.open_site()
        has_state = self.cfg.state_file.exists() or self.cfg.auth_state_file.exists()
        if has_state and self.is_logged_in():
            return
        # No valid session at this point.
        if not has_state and not interactive:
            raise AskGoError(
                "Not logged in. Run `python -m askgo.cli login` first.",
                exit_code=EXIT_NOT_LOGGED_IN,
                step="ensure_login",
                screenshot=self._screenshot("not_logged_in"),
            )
        if has_state and not interactive:
            raise AskGoError(
                "Login state expired or invalid; re-run `login`.",
                exit_code=EXIT_NOT_LOGGED_IN,
                step="ensure_login",
                screenshot=self._screenshot("login_expired"),
            )
        # interactive with no saved state: wait for the human to finish logging in
        sys.stderr.write("[askgo] Please complete login in the opened browser...\n")
        self.open_login_modal()
        deadline = time.time() + self.cfg.login_timeout_s
        last_dump = 0.0
        while time.time() < deadline:
            if self.is_logged_in():
                break
            if time.time() - last_dump > 3:
                self._dump_probe()
                last_dump = time.time()
            self.page.wait_for_timeout(1000)
        else:
            raise AskGoError(
                "Timed out waiting for interactive login.",
                exit_code=EXIT_NOT_LOGGED_IN,
                step="ensure_login",
                screenshot=self._screenshot("login_timeout"),
            )
        self.save_state()
        sys.stderr.write("[askgo] Login saved.\n")

    def save_state(self) -> None:
        self.context.storage_state(path=str(self.cfg.state_file))
        # Also save the sessionStorage token for future sessions.
        try:
            token = self.page.evaluate("() => sessionStorage.getItem('token')")
            if token:
                import json as _json
                auth_data = {
                    "token": token,
                    "sessionStorage": _json.loads(self.page.evaluate("() => JSON.stringify(sessionStorage)")),
                    "url": self.page.url,
                }
                self.cfg.auth_state_file.write_text(
                    _json.dumps(auth_data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except PWError:
            pass

    # -- helpers ------------------------------------------------------------
    def _screenshot(self, tag: str) -> str:
        path = self.cfg.debug_dir / f"{tag}_{int(time.time())}.png"
        try:
            self.page.screenshot(path=str(path), full_page=False)
        except PWError:
            return ""
        return str(path)

    def screenshot(self, tag: str) -> str:
        return self._screenshot(tag)
