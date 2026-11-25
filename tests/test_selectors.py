"""Regression tests for the hand-tuned page selectors (askgo/selectors.py).

The selector patterns are tuned by hand against the real AskGo page (via the
`probe` command), so a careless edit to one pattern can silently stop matching a
real control. These tests lock the behaviour in: each key pattern must still
match the labels it was tuned for, in both Chinese and English, and the model
picker's CSS classes must stay in sync with what `probe` found.

They run with plain `python -m unittest` and need no browser and no Playwright:
the module's Playwright import is now type-only, so the pure pattern definitions
import cleanly on a machine that has not installed the browser.
"""
import unittest

from askgo.selectors import Selectors


class TestLoginMarkers(unittest.TestCase):
    def setUp(self):
        self.s = Selectors()

    def test_login_button_matches_zh_and_en(self):
        for label in ("登录", "Log in", "Sign In", "SIGN IN"):
            self.assertIsNotNone(self.s.login_button.search(label), label)

    def test_logged_in_marker_matches_logout_and_profile(self):
        for label in ("退出", "Log out", "Sign out", "我的",
                      "个人中心", "剩余积分", "专业版"):
            self.assertIsNotNone(self.s.logged_in_marker.search(label), label)

    def test_login_button_does_not_match_logout(self):
        # A logout control must never be mistaken for the login button.
        self.assertIsNone(self.s.login_button.search("退出"))
        self.assertIsNone(self.s.login_button.search("Log out"))


class TestComposerAndActions(unittest.TestCase):
    def setUp(self):
        self.s = Selectors()

    def test_input_placeholder_covers_text_and_image_modes(self):
        for label in ("请输入您的提示词", "描述你想生成的图片，可上传参考图",
                      "Ask me anything", "Message"):
            self.assertIsNotNone(self.s.input_placeholder.search(label), label)

    def test_send_stop_new_chat_buttons(self):
        self.assertIsNotNone(self.s.send_button.search("发送"))
        self.assertIsNotNone(self.s.send_button.search("Send"))
        self.assertIsNotNone(self.s.stop_button.search("停止"))
        self.assertIsNotNone(self.s.stop_button.search("Stop"))
        self.assertIsNotNone(self.s.new_chat_button.search("新对话"))
        self.assertIsNotNone(self.s.new_chat_button.search("New Chat"))
        self.assertIsNotNone(self.s.new_chat_button.search("new conversation"))


class TestModelPickerCss(unittest.TestCase):
    def setUp(self):
        self.s = Selectors()

    def test_model_picker_classes(self):
        self.assertEqual(self.s.model_trigger_css, ".mode_name")
        self.assertEqual(self.s.model_item_css, ".select_mode_item")
        self.assertEqual(self.s.model_name_text_css, ".model-name-text")
        self.assertEqual(self.s.model_selected_css, ".select_mode_item_success")

    def test_reply_and_media_selectors(self):
        self.assertEqual(self.s.reply_text_css, ".default_title_markdown")
        for tag in ("img", "video", "audio"):
            self.assertIn(tag, self.s.media_selector)


if __name__ == "__main__":
    unittest.main()
