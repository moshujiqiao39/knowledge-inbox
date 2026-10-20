from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_HOTKEY = "<ctrl>+<alt>+k"
DEFAULT_PORT = 8765


def load_settings(path: Path) -> dict:
    """读取 settings.json。文件坏了就用默认值，不阻止程序启动。"""
    settings = {"hotkey": DEFAULT_HOTKEY, "port": DEFAULT_PORT}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            raw = {}
        if isinstance(raw, dict):
            hotkey = raw.get("hotkey")
            if isinstance(hotkey, str) and hotkey.strip():
                settings["hotkey"] = hotkey.strip()
            try:
                port = int(raw.get("port", DEFAULT_PORT))
            except (TypeError, ValueError):
                port = DEFAULT_PORT
            if 1 <= port <= 65535:
                settings["port"] = port
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    env_hotkey = os.environ.get("INBOX_HOTKEY", "").strip()
    if env_hotkey:
        settings["hotkey"] = env_hotkey
    env_port = os.environ.get("INBOX_PORT", "").strip()
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            port = settings["port"]
        if 1 <= port <= 65535:
            settings["port"] = port
    return settings
