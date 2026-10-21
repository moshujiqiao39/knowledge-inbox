from __future__ import annotations

import os
import unittest
from datetime import datetime
from pathlib import Path
from inbox.logic import (
    CaptureError,
    build_entry,
    classify_clipboard,
    clipboard_prompt_text,
    compute_dedup,
    hotkey_label,
    normalize_url,
    parse_tags,
)
from inbox.settings import load_settings


class LogicTests(unittest.TestCase):
    def test_parse_tags(self) -> None:
        self.assertEqual(parse_tags("#工作, 灵感，#工作  阅读"), ["工作", "灵感", "阅读"])
        self.assertEqual(parse_tags("   "), [])

    def test_hotkey_label(self) -> None:
        self.assertEqual(hotkey_label("<ctrl>+<alt>+k"), "Ctrl+Alt+K")

    def test_normalize_url_strips_tracking(self) -> None:
        left = normalize_url("https://Example.com/path/?utm_source=wechat&id=7#top")
        right = normalize_url("https://example.com/path?id=7")
        self.assertEqual(left, right)

    def test_same_link_with_different_tracking_is_one_dedup_key(self) -> None:
        first = build_entry("https://example.com/a?utm_source=1", [], now=datetime(2026, 10, 20, 12, 0, 0))
        second = build_entry("https://example.com/a?utm_source=2", [], now=datetime(2026, 10, 20, 12, 1, 0))
        assert first and second
        self.assertEqual(first.dedup, second.dedup)
        self.assertEqual(first.text, "")
        self.assertTrue(first.url.startswith("https://example.com/a"))

    def test_text_dedup_ignores_whitespace(self) -> None:
        self.assertEqual(compute_dedup("", "你好   世界"), compute_dedup("", "你好 世界"))

    def test_note_and_bare_link_are_different(self) -> None:
        note = build_entry("看到 https://example.com/a 先记下来", ["工作"])
        link = build_entry("https://example.com/a", ["工作"])
        assert note and link
        self.assertNotEqual(note.dedup, link.dedup)
        self.assertEqual(note.url, "https://example.com/a")
        self.assertIn("先记下来", note.text)

    def test_too_long(self) -> None:
        with self.assertRaises(CaptureError):
            build_entry("字" * 100_001, [])

    def test_clipboard_prompt_skips_same_and_non_text(self) -> None:
        self.assertIsNone(clipboard_prompt_text("image", "", None))
        self.assertIsNone(clipboard_prompt_text("empty", "   ", None))
        self.assertIsNone(clipboard_prompt_text("text", "同一句", "同一句"))
        self.assertIsNone(clipboard_prompt_text("text", "同一句\n", "同一句"))
        self.assertEqual(clipboard_prompt_text("text", "新的一句", "同一句"), "新的一句")

    def test_classify_clipboard(self) -> None:
        self.assertEqual(classify_clipboard("  链接  ", False), ("text", "  链接  "))
        self.assertEqual(classify_clipboard("   ", True), ("image", ""))
        self.assertEqual(classify_clipboard("", False), ("empty", ""))

    def test_settings_defaults_and_override(self) -> None:
        import tempfile

        os.environ.pop("INBOX_HOTKEY", None)
        os.environ.pop("INBOX_PORT", None)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            created = load_settings(path)
            self.assertEqual(created["hotkey"], "<ctrl>+<alt>+k")
            self.assertTrue(path.is_file())
            path.write_text("{", encoding="utf-8")
            broken = load_settings(path)
            self.assertEqual(broken["port"], 8765)
            os.environ["INBOX_HOTKEY"] = "<ctrl>+<shift>+k"
            os.environ["INBOX_PORT"] = "8877"
            try:
                overridden = load_settings(path)
            finally:
                os.environ.pop("INBOX_HOTKEY", None)
                os.environ.pop("INBOX_PORT", None)
            self.assertEqual(overridden["hotkey"], "<ctrl>+<shift>+k")
            self.assertEqual(overridden["port"], 8877)


if __name__ == "__main__":
    unittest.main()
