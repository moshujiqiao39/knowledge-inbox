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
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.c_bool
    user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_void_p]
    user32.keybd_event.restype = None
    user32.SwitchToThisWindow.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    user32.SwitchToThisWindow.restype = None
    user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    user32.SystemParametersInfoW.restype = ctypes.c_bool
    return user32


def widget_hwnd(widget) -> int:
    widget.update_idletasks()
    hwnd = int(widget.winfo_id())
    if sys.platform != "win32":
        return hwnd
    # GA_ROOT 走到真正的外层窗口。GetParent 在隶属窗口上会返回主人，置顶就会打到主窗口上。
    root = _user32().GetAncestor(hwnd, 2)
    return int(root or hwnd)


def _same_window(user32, left, right) -> bool:
    if not left or not right:
        return False
    root_left = user32.GetAncestor(left, 2) or left
    root_right = user32.GetAncestor(right, 2) or right
    return int(root_left) == int(root_right)


def _raise_then_release(user32, hwnd: int) -> None:
    """先借一次置顶跳到最前，马上取消置顶，之后别的窗口可以盖住它。"""
    no_move = 0x0002
    no_size = 0x0001
    show = 0x0040
    flags = no_move | no_size | show
    user32.ShowWindow(hwnd, 9)
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)


def _unlock_foreground_once(user32, hwnd: int) -> None:
    """前台锁还挡着时，短暂清掉超时再抢一次，马上把原来的值写回去。"""
    import ctypes

    get_timeout = 0x2000
    set_timeout = 0x2001
    previous = ctypes.c_uint()
    if not user32.SystemParametersInfoW(get_timeout, 0, ctypes.byref(previous), 0):
        return
    if not user32.SystemParametersInfoW(set_timeout, 0, None, 0):
        return
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.SwitchToThisWindow(hwnd, True)
    finally:
        user32.SystemParametersInfoW(set_timeout, previous.value, None, 0)


def force_foreground(hwnd: int) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    import ctypes

    user32 = _user32()
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
    root = user32.GetAncestor(hwnd, 2)
    target = int(root or hwnd)
    if not target:
        return
    _raise_then_release(user32, target)
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = False
    if foreground_thread and foreground_thread != current_thread:
        attached = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))
    alt_down = False
    try:
        # 模拟一次 Alt，系统才允许后台程序在复制发生时把窗口拉到前台。
        user32.keybd_event(0x12, 0, 0, None)
        alt_down = True
        user32.SetForegroundWindow(target)
        user32.BringWindowToTop(target)
        user32.SwitchToThisWindow(target, True)
        if not _same_window(user32, user32.GetForegroundWindow(), target):
            _unlock_foreground_once(user32, target)
    finally:
        if alt_down:
            user32.keybd_event(0x12, 0, 0x0002, None)
        if attached:
            user32.AttachThreadInput(foreground_thread, current_thread, False)
    _raise_then_release(user32, target)
