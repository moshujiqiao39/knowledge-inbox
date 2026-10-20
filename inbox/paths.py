from __future__ import annotations

import os
import sys
from pathlib import Path


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    """程序所在目录。打包后是 exe 旁边，开发时是项目根目录。"""
    if _frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """只读资源目录。打包后网页文件在 PyInstaller 的临时目录里。"""
    if _frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return install_root()


def data_root() -> Path:
    """笔记、设置和日志的目录。INBOX_HOME 可改到别的文件夹，便于测试。"""
    override = os.environ.get("INBOX_HOME", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return install_root()


def index_html() -> Path:
    candidates = [
        resource_root() / "web" / "index.html",
        install_root() / "web" / "index.html",
        install_root() / "_internal" / "web" / "index.html",
    ]
    for path in candidates:
        if path.is_file():
            return path
    searched = "\n".join(str(path) for path in candidates)
    raise FileNotFoundError("找不到搜索页 web/index.html\n" + searched)
