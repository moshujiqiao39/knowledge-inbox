from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from inbox.paths import index_html
from inbox.store import Store


class ServerState:
    def __init__(self, store: Store, hotkey_label: str) -> None:
        self.store = store
        self.hotkey_label = hotkey_label


def build_handler(state: ServerState):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            try:
                if path in ("/", "/index.html"):
                    body = index_html().read_bytes()
                    self._send(200, body, "text/html; charset=utf-8")
                elif path == "/api/entries":
                    payload = json.dumps(state.store.list_public(), ensure_ascii=False).encode("utf-8")
                    self._send(200, payload, "application/json; charset=utf-8")
                elif path == "/api/meta":
                    payload = json.dumps(
                        {
                            "hotkey": state.hotkey_label,
                            "file": str(state.store.path),
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")
                    self._send(200, payload, "application/json; charset=utf-8")
                else:
                    self._send(404, "没有这个页面".encode("utf-8"), "text/plain; charset=utf-8")
            except Exception:
                logging.exception("处理网页请求失败")
                try:
                    self._send(500, "读取笔记失败".encode("utf-8"), "text/plain; charset=utf-8")
                except OSError:
                    return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            return

    return Handler


class ReuseHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def start_server(state: ServerState, port: int) -> tuple[ThreadingHTTPServer, int]:
    handler = build_handler(state)
    last_error: OSError | None = None
    for candidate in range(port, port + 20):
        try:
            httpd = ReuseHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as exc:
            last_error = exc
            continue
        httpd.daemon_threads = True
        return httpd, int(httpd.server_address[1])
    detail = f"{last_error}" if last_error else "未知原因"
    raise OSError(f"8765 附近的端口都被占用，搜索页没有打开。{detail}")
