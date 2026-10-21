from __future__ import annotations

import subprocess
import sys
import time

from inbox.logic import classify_clipboard


class ClipboardError(Exception):
    pass


def clipboard_sequence() -> int | None:
    """Windows 上剪贴板每次变化，这个数字都会变。其他系统没有这个接口。"""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetClipboardSequenceNumber.argtypes = []
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    return int(user32.GetClipboardSequenceNumber())


def read_clipboard() -> tuple[str, str]:
    """返回 (kind, text)。kind 是 text、image 或 empty。"""
    if sys.platform == "win32":
        text, has_image = _read_windows()
        return classify_clipboard(text, has_image)
    if sys.platform == "darwin":
        result = _run_command(["pbpaste"])
        if result is None:
            raise ClipboardError("读不到 macOS 剪贴板。")
        text = result.stdout.decode("utf-8", errors="replace")
        return classify_clipboard(text, False)
    return _read_linux()


def _read_linux() -> tuple[str, str]:
    commands = [
        ["wl-paste", "--no-newline"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ]
    found_tool = False
    for command in commands:
        result = _run_command(command)
        if result is None:
            continue
        found_tool = True
        if result.returncode == 0 or result.stdout:
            text = result.stdout.decode("utf-8", errors="replace")
            return classify_clipboard(text, False)
    if not found_tool:
        raise ClipboardError("读不到剪贴板。请先安装 wl-clipboard、xclip 或 xsel。")
    return "empty", ""


def _run_command(command: list[str]):
    try:
        return subprocess.run(command, capture_output=True, timeout=2, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _read_windows() -> tuple[str, bool]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    cf_unicodetext = 13
    cf_bitmap = 2
    cf_dib = 8

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    opened = False
    for _ in range(8):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.02)
    if not opened:
        raise ClipboardError("剪贴板正被其他程序占用，请再试一次。")
    try:
        has_image = bool(
            user32.IsClipboardFormatAvailable(cf_dib)
            or user32.IsClipboardFormatAvailable(cf_bitmap)
        )
        png_format = user32.RegisterClipboardFormatW("PNG")
        if png_format and user32.IsClipboardFormatAvailable(png_format):
            has_image = True
        if not user32.IsClipboardFormatAvailable(cf_unicodetext):
            return "", has_image
        handle = user32.GetClipboardData(cf_unicodetext)
        if not handle:
            return "", has_image
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return "", has_image
        try:
            return ctypes.wstring_at(pointer), has_image
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
