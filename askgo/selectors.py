"""ALL page selectors live here, in one place.

These are best-effort locators using role / aria-label / placeholder / data-*
instead of random hash class names. They MUST be verified against the real page
with `python -m askgo.cli probe` (dumps candidate elements) and tuned here.

Conventions:
    - Prefer get_by_role / get_by_placeholder / get_by_label / get_by_test_id.
    - Regexes are case-insensitive and cover both Chinese and English labels.
    - `logged_in_marker` is a heuristic: a logout control OR absence of the
      login control means "logged in".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from playwright.sync_api import Locator, Page


def _re(*patterns: str) -> re.Pattern:
    joined = "|".join(patterns)
    return re.compile(joined, re.IGNORECASE)


@dataclass
class Selectors:
    # --- login / auth -------------------------------------------------------
    login_button: re.Pattern = _re("登录", "log ?in", "sign ?in")
    logged_in_marker: re.Pattern = _re("退出", "log ?out", "sign ?out", "我的", "个人中心", "剩余积分", "我的内容", "升级", "专业版")

    # --- model selection ----------------------------------------------------
    # AskGo uses an Element Plus popover picker (verified via `probe`):
    #   - trigger  : SPAN.mode_name  (visible pill showing the current model)
    #   - items    : DIV.select_mode_item (136 in DOM, hidden until the popover
    #                opens; each holds the clean name in SPAN.model-name-text)
    #   - selected : DIV.select_mode_item_success
    # The picker has NO <button role="menu">, so we target by CSS class.
    model_trigger_css: str = ".mode_name"
    model_item_css: str = ".select_mode_item"
    model_name_text_css: str = ".model-name-text"
    model_selected_css: str = ".select_mode_item_success"

    # --- chat input ---------------------------------------------------------
    # AskGo swaps the composer when a media model is active: the text box
    # placeholder becomes "描述你想生成的图片，可上传参考图" (image mode) while the
    # plain text box ("请输入您的提示词") stays in the DOM but hidden. We match
    # both so the union covers every composer variant; send() then picks the
    # *visible* one.
    input_placeholder: re.Pattern = _re("输入", "消息", "message", "ask", "问题", "prompt", "问我任何", "描述", "图片", "参考图")
    send_button: re.Pattern = _re("发送", "send")
    stop_button: re.Pattern = _re("停止", "stop", "终止")

    # --- reply / media ------------------------------------------------------
    # Assistant message container. Adjust after `probe`.
    assistant_message: str = "[data-role='assistant'], [data-message-role='assistant'], .assistant, .message-assistant, [class*='markdown']"
    user_message: str = "[data-role='user'], [data-message-role='user'], .user"
    # The real answer text lives in .default_title_markdown (confirmed by
    # diag2.json). The generic [class*='markdown'] ALSO matches an empty
    # .export_answer_icon node, so target the concrete class and take the last
    # *non-empty* match to avoid grabbing that empty node.
    reply_text_css: str = ".default_title_markdown"
    # While the assistant is generating, a streaming container is present and a
    # stage label reads 思考中/生成中. Its disappearance marks completion.
    streaming_indicator_css: str = ".latest_reply_streaming"
    reply_stage_text_css: str = ".reply_stage_text"
    generating_keywords: tuple = ("思考中", "生成中", "thinking", "generating")
    media_selector: str = "img, video, audio, a[href$='.png'], a[href$='.jpg'], a[href$='.jpeg'], a[href$='.webp'], a[href$='.mp4'], a[href$='.mp3'], a[href$='.wav'], a[href$='.m4a']"

    # --- session / new conversation ----------------------------------------
    new_chat_button: re.Pattern = _re("新对话", "新建", "new chat", "new conversation")

    # --- locator helpers ----------------------------------------------------
    def login(self, page: Page) -> Locator:
        return page.get_by_role("button", name=self.login_button)

    def logged_in(self, page: Page) -> Locator:
        return page.get_by_text(self.logged_in_marker)

    def input(self, page: Page) -> Locator:
        # Chat boxes are often contenteditable divs, not <input>/<textarea>.
        by_placeholder = page.get_by_placeholder(self.input_placeholder)
        editable = page.locator('[contenteditable="true"]')
        return by_placeholder.or_(editable)

    def input_visible(self, page: Page) -> Locator:
        """Return the composer that is actually on screen.

        AskGo keeps multiple composers in the DOM (text vs. image vs. video)
        and only one is visible at a time, so a plain `.first` can resolve to a
        hidden box. This filters the union down to the first visible element.
        """
        box = self.input(page)
        for i in range(box.count()):
            item = box.nth(i)
            try:
                if item.is_visible(timeout=500):
                    return item
            except Exception:
                continue
        # Fall back to the union's first element so callers still get a locator.
        return box.first

    def send(self, page: Page) -> Locator:
        return page.get_by_role("button", name=self.send_button)

    def stop(self, page: Page) -> Locator:
        return page.get_by_role("button", name=self.stop_button)

    def model_trigger(self, page: Page) -> Locator:
        return page.locator(self.model_trigger_css)

    def model_items(self, page: Page) -> Locator:
        return page.locator(self.model_item_css)

    def assistant(self, page: Page) -> Locator:
        return page.locator(self.assistant_message)

    def reply_text(self, page: Page) -> Locator:
        return page.locator(self.reply_text_css)

    def streaming(self, page: Page) -> Locator:
        return page.locator(self.streaming_indicator_css)

    def reply_stage_text(self, page: Page) -> Locator:
        return page.locator(self.reply_stage_text_css)

    def media(self, page: Page) -> Locator:
        return page.locator(self.media_selector)

    def new_chat(self, page: Page) -> Locator:
        return page.get_by_role("button", name=self.new_chat_button)
