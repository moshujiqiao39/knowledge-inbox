from __future__ import annotations

import json
import threading
import unittest
import urllib.request
from pathlib import Path
import tempfile

from inbox.server import ServerState, start_server
from inbox.store import save_text, Store


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.store = Store(Path(self._temporary.name) / "knowledge.md")
        save_text(self.store, "搜索得到 <script>alert(1)</script> 与标签", "工作")
        self.state = ServerState(self.store, "Ctrl+Alt+K")
        self.httpd, self.port = start_server(self.state, 0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self._temporary.cleanup()

    def test_page_and_api(self) -> None:
        base = f"http://127.0.0.1:{self.port}"
        with urllib.request.urlopen(base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("搜索正文、链接或标签", html)
        self.assertNotIn("innerHTML", html)
        with urllib.request.urlopen(base + "/api/entries", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload[0]["tags"], ["工作"])
        self.assertIn("<script>", payload[0]["text"])
        with urllib.request.urlopen(base + "/api/meta", timeout=5) as response:
            meta = json.loads(response.read().decode("utf-8"))
        self.assertEqual(meta["hotkey"], "Ctrl+Alt+K")
        self.assertTrue(meta["file"].endswith("knowledge.md"))


if __name__ == "__main__":
    unittest.main()
