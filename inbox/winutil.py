from __future__ import annotations

import sys


def disable_console_quick_edit() -> None:
    """点一下黑色窗口时，Windows 会暂停整个程序。这里关掉这个行为。"""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    handle = kernel32.GetStdHandle(-10)
    if not handle or handle == ctypes.c_void_p(-1).value:
        return
    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)):
        return
    enable_extended = 0x0080
    quick_edit = 0x0040
    kernel32.SetConsoleMode(ctypes.c_void_p(handle), (mode.value | enable_extended) & ~quick_edit)


def modifiers_held() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    # Ctrl, Alt, Shift, 左右 Windows 键。快捷键还按着时不要弹出输入框。
    for virtual_key in (0x11, 0x12, 0x10, 0x5B, 0x5C):
        if user32.GetAsyncKeyState(virtual_key) & 0x8000:
            return True
    return False


def _user32():
    import ctypes

    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_bool
    user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    user32.BringWindowToTop.restype = ctypes.c_bool
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool]
    user32.AttachThreadInput.restype = ctypes.c_bool
    return user32


def widget_hwnd(widget) -> int:
    widget.update_idletasks()
    hwnd = int(widget.winfo_id())
    if sys.platform != "win32":
        return hwnd
    parent = _user32().GetParent(hwnd)
    return int(parent or hwnd)


def force_foreground(hwnd: int) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    import ctypes

    user32 = _user32()
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = False
    if foreground_thread and foreground_thread != current_thread:
        attached = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
    try:
        user32.ShowWindow(hwnd, 5)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        if target_thread and target_thread != current_thread:
            user32.AttachThreadInput(current_thread, target_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(current_thread, target_thread, False)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)
