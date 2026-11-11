"""High-level operations on the AskGo chat page.

No fixed sleeps: generation completion is detected by (stop button gone) AND
(reply text stable across two consecutive polls).
"""
from __future__ import annotations

import re
import time

from playwright.sync_api import Page, BrowserContext, Error as PWError

from .config import Config
from .selectors import Selectors
from .errors import AskGoError, EXIT_CLIENT
from . import media as media_mod

POLL_INTERVAL_MS = 400
STABLE_POLLS = 2
TOTAL_WAIT_MS = 300_000  # hard ceiling so a stuck page can't hang forever


def _norm(s: str) -> str:
    """Normalize a model name for matching (lowercase, alphanumerics only)."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


class AskGoClient:
    def __init__(self, page: Page, context: BrowserContext, config: Config, selectors: Selectors | None = None):
        self.page = page
        self.context = context
        self.cfg = config
        self.sel = selectors or Selectors()

    # -- helpers ------------------------------------------------------------
    def _shot(self, tag: str) -> str:
        """Write a debug screenshot and return its path (never the raw bytes)."""
        path = self.cfg.debug_dir / f"{tag}_{int(time.time())}.png"
        try:
            self.page.screenshot(path=str(path))
        except PWError:
            return ""
        return str(path)

    # -- model --------------------------------------------------------------
    # In-page finder: returns the DOM-order index of the first *visible*
    # .select_mode_item whose .model-name-text matches `name` (case-insensitive,
    # exact or substring). -1 if none. The index lines up with
    # page.locator(".select_mode_item").nth(idx) because both iterate the same
    # document-order node list.
    _FIND_MODEL_JS = r"""
    (name) => {
      const items = Array.from(document.querySelectorAll('.select_mode_item'));
      const norm = (s) => String(s).trim().toLowerCase().replace(/[^a-z0-9]/g, '');
      const n = norm(name);
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        if (!it.offsetParent) continue;          // skip hidden items
        const t = it.querySelector('.model-name-text') || it;
        const txt = norm(t.textContent || '');
        if (txt === n || txt.includes(n)) return i;
      }
      return -1;
    }
    """

    def _dismiss_modals(self) -> None:
        """Close any notice/dialog popups that would block the model picker."""
        for label in ("知道了", "我知道了", "取消", "Close"):
            try:
                btn = self.page.get_by_role("button", name=label)
                if btn.count() and btn.first.is_visible(timeout=300):
                    btn.first.click(timeout=1500)
            except PWError:
                pass

    def _current_model_text(self) -> str:
        try:
            trig = self.sel.model_trigger(self.page)
            if trig.count():
                return (trig.first.inner_text(timeout=1500) or "").strip()
        except PWError:
            pass
        return ""

    def select_model(self, name: str) -> str:
        if not name:
            return ""
        name = name.strip()
        self._dismiss_modals()
        # Fast path: the pill already shows this model -> nothing to do.
        current = self._current_model_text()
        if current and _norm(name) in _norm(current):
            return current
        items = self.sel.model_items(self.page)
        trigger = self.sel.model_trigger(self.page)
        # Open the picker (up to 3 attempts); the popover may need a nudge.
        for _attempt in range(3):
            try:
                if items.first.is_visible(timeout=300):
                    break
                trigger.first.scroll_into_view_if_needed(timeout=2000)
                trigger.first.click(timeout=3000, force=True)
                items.first.wait_for(state="visible", timeout=3000)
                break
            except PWError:
                try:
                    self.page.keyboard.press("Escape")
                except PWError:
                    pass
                self.page.wait_for_timeout(400)
        else:
            shot = self._shot("select_model_open")
            raise AskGoError(
                "Could not open the model picker.",
                exit_code=EXIT_CLIENT,
                step="select_model",
                selector="model_trigger",
                screenshot=shot,
            )
        idx = self.page.evaluate(self._FIND_MODEL_JS, name)
        if idx < 0:
            shot = self._shot("select_model_nofind")
            raise AskGoError(
                f"Model '{name}' not found in the picker.",
                exit_code=EXIT_CLIENT,
                step="select_model",
                selector="model_item / model_name_text",
                screenshot=shot,
            )
        try:
            items.nth(idx).scroll_into_view_if_needed(timeout=2000)
            items.nth(idx).click(timeout=3000)
        except PWError:
            shot = self._shot("select_model_click")
            raise AskGoError(
                f"Could not click model '{name}'.",
                exit_code=EXIT_CLIENT,
                step="select_model",
                selector="model_item",
                screenshot=shot,
            )
        # Confirm the pill updated; wait for the popover to close.
        deadline = time.time() + 5
        chosen = ""
        while time.time() < deadline:
            chosen = self._current_model_text()
            if _norm(name) in _norm(chosen):
                return chosen
            self.page.wait_for_timeout(200)
        shot = self._shot("select_model_unconfirmed")
        raise AskGoError(
            f"Model '{name}' was not confirmed after selection.",
            exit_code=EXIT_CLIENT,
            step="select_model",
            selector="model_trigger",
            screenshot=shot,
        )

    # -- conversation reset -------------------------------------------------
    def start_new_conversation(self) -> None:
        """Reset to a fresh conversation by clicking the 'new chat' control.

        AskGo keeps the last conversation in localStorage, so merely navigating
        the app resumes it. Clicking 'new chat' is the reliable reset. No-op if
        the control is absent (the view is already a fresh conversation).
        """
        self._dismiss_modals()
        try:
            btn = self.sel.new_chat(self.page)
            if btn.count() and btn.first.is_visible(timeout=2000):
                btn.first.click(timeout=self.cfg.timeout_ms)
                # Give the SPA a beat to swap to the blank conversation view.
                self.page.wait_for_timeout(800)
        except PWError:
            pass

    # -- send ---------------------------------------------------------------
    def send(self, prompt: str) -> None:
        try:
            # Pick the composer that is actually visible (text vs. image vs.
            # video mode), not the DOM-first one which may be hidden.
            box = self.sel.input_visible(self.page)
            box.fill(prompt, timeout=self.cfg.timeout_ms)
            # Prefer a send button; fall back to Enter.
            send = self.sel.send(self.page)
            if send.count() and send.first.is_visible(timeout=1500):
                send.first.click()
            else:
                box.press("Enter")
        except PWError as exc:
            shot = self._shot("send")
            raise AskGoError(
                f"Failed to send prompt: {exc}",
                exit_code=EXIT_CLIENT,
                step="send",
                selector="input_placeholder / send_button",
                screenshot=shot,
            ) from exc

    # -- wait ---------------------------------------------------------------
    def _stop_visible(self) -> bool:
        try:
            return self.sel.stop(self.page).first.is_visible(timeout=500)
        except PWError:
            return False

    def _generating(self) -> bool:
        """True while the assistant is still producing a reply.

        Detection (any one signal is enough):
          1. the streaming container (.latest_reply_streaming) is present,
          2. a stage label (.reply_stage_text) reads 思考中/生成中/thinking/...,
          3. a stop button is visible (fallback for other UIs).
        Completion is the *absence* of every signal -- no fixed sleep.
        """
        try:
            loc = self.page.locator(self.sel.streaming_indicator_css)
            if loc.count() and loc.first.is_visible(timeout=500):
                return True
        except PWError:
            pass
        try:
            stage = self.page.locator(self.sel.reply_stage_text_css)
            if stage.count():
                txt = (stage.first.inner_text(timeout=500) or "")
                if any(k in txt for k in self.sel.generating_keywords):
                    return True
        except PWError:
            pass
        return self._stop_visible()

    def _media_present(self) -> bool:
        """True when a real (non-icon) image/video/audio element is on screen.

        Image/video/audio replies carry no assistant text, so completion cannot
        be detected by text stability alone. We look for a rendered media
        element large enough to be a real result rather than a UI glyph.
        """
        try:
            return bool(self.page.evaluate(
                """() => {
                  const out = [];
                  document.querySelectorAll('img,video,audio').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) return;
                    if (r.width < 120 || r.height < 120) return;   // skip UI icons
                    const src = el.currentSrc || el.src || el.getAttribute('src') || el.getAttribute('href') || '';
                    if (!src || src.startsWith('data:')) return;
                    out.push(true);
                  });
                  return out.length > 0;
                }"""))
        except PWError:
            return False

    def _reply_text(self) -> str:
        try:
            last = self._last_non_empty(self.sel.reply_text(self.page))
            if last:
                return last
            # Fallback to the broader assistant selector (still last non-empty,
            # so the empty export-icon node is skipped).
            return self._last_non_empty(self.sel.assistant(self.page))
        except PWError:
            return ""

    def _last_non_empty(self, loc) -> str:
        """Return the inner text of the last non-empty match, else ''."""
        last = ""
        try:
            n = loc.count()
        except PWError:
            return ""
        for i in range(n):
            try:
                txt = (loc.nth(i).inner_text(timeout=1000) or "").strip()
            except PWError:
                continue
            if txt:
                last = txt
        return last

    def wait_for_reply(self) -> str:
        deadline = time.time() + TOTAL_WAIT_MS / 1000
        prev = ""
        stable = 0
        while time.time() < deadline:
            generating = self._generating()
            text = self._reply_text()
            if not generating:
                # Text reply: require two consecutive stable polls.
                if text and text == prev:
                    stable += 1
                    if stable >= STABLE_POLLS:
                        return text
                # Media-only reply (image/video/audio): no text, so complete as
                # soon as the generator stops and a real media element is shown.
                elif self._media_present():
                    return text
                else:
                    stable = 0
            else:
                stable = 0
            prev = text
            self.page.wait_for_timeout(POLL_INTERVAL_MS)
        shot = self._shot("reply_timeout")
        raise AskGoError(
            "Timed out waiting for a stable reply.",
            exit_code=EXIT_CLIENT,
            step="wait_for_reply",
            screenshot=shot,
        )

    # -- extract ------------------------------------------------------------
    def extract_text(self, text: str) -> str:
        if not text:
            shot = self._shot("empty_reply")
            raise AskGoError(
                "Reply text was empty.",
                exit_code=EXIT_CLIENT,
                step="extract_text",
                selector="assistant_message",
                screenshot=shot,
            )
        return text

    def extract_media(self, save: bool = True) -> list[dict]:
        return media_mod.extract_media(self.page, self.context, self.cfg, self.sel, save=save)
