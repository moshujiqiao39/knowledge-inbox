from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from inbox.logic import build_entry
from inbox.store import Store, save_text


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.store = Store(Path(self._temporary.name) / "knowledge.md")

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_roundtrip_and_newest_first(self) -> None:
        first = build_entry("第一则笔记", ["工作"], now=datetime(2026, 10, 20, 9, 0, 0), entry_id="a" * 16)
        second = build_entry("第二则\n还有一行", ["灵感"], now=datetime(2026, 10, 20, 10, 0, 0), entry_id="b" * 16)
        assert first and second
        self.assertEqual(self.store.add(first), "saved")
        self.assertEqual(self.store.add(second), "saved")
        entries = self.store.list_entries()
        self.assertEqual([item.text for item in entries], ["第二则\n还有一行", "第一则笔记"])
        self.assertEqual(entries[0].tags, ["灵感"])
        raw = self.store.path.read_text(encoding="utf-8")
        self.assertIn("第二则", raw)
        self.assertIn("<!-- kb id=", raw)

    def test_duplicate_link_and_tag_merge(self) -> None:
        status, message = save_text(self.store, "https://example.com/post?utm_source=a", "工作")
        self.assertEqual(status, "saved")
        self.assertEqual(message, "已保存")
        status, message = save_text(self.store, "https://example.com/post?utm_source=b", "工作")
        self.assertEqual(status, "duplicate")
        status, message = save_text(self.store, "https://example.com/post", "灵感")
        self.assertEqual(status, "updated")
        self.assertEqual(message, "这条已经收过，已补上新标签")
        entry = self.store.list_entries()[0]
        self.assertEqual(entry.tags, ["工作", "灵感"])
        self.assertEqual(len(self.store.list_entries()), 1)

    def test_edited_tag_line_is_what_search_reads(self) -> None:
        entry = build_entry("手改之前", ["旧"], entry_id="c" * 16)
        assert entry
        self.store.add(entry)
        raw = self.store.path.read_text(encoding="utf-8")
        raw = raw.replace("标签：#旧", "标签：#新标签 #另一个")
        self.store.path.write_text(raw, encoding="utf-8")
        found = self.store.list_entries()[0]
        self.assertEqual(found.tags, ["新标签", "另一个"])
        self.assertEqual(found.text, "手改之前")

    def test_end_marker_inside_body_does_not_cut_the_note(self) -> None:
        entry = build_entry("上文\n<!-- /kb id=" + "d" * 16 + " -->\n下文", [], entry_id="d" * 16)
        assert entry
        self.assertEqual(self.store.add(entry), "saved")
        found = self.store.list_entries()[0]
        self.assertIn("上文", found.text)
        self.assertIn("下文", found.text)
        self.assertNotIn("<!-- /kb", found.text)

    def test_empty_clipboard_text(self) -> None:
        status, _message = save_text(self.store, "   \n  ", "")
        self.assertEqual(status, "empty")
        self.assertEqual(self.store.list_public(), [])


if __name__ == "__main__":
    unittest.main()
