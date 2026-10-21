"""创建本机运行环境并打开知识收件箱。双击 启动.bat / 启动.sh 会走到这里。"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def raise_inbox_window() -> bool:
    """找到已经打开的「知识收件箱」并把它拉到最前面。"""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value == "知识收件箱":
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(visit, 0)
    if not found:
        return False
    sys.path.insert(0, str(ROOT))
    from inbox.winutil import force_foreground, release_topmost

    force_foreground(found[0])
    release_topmost(found[0])
    return True


def pause() -> None:
    if sys.platform == "win32":
        try:
            input("按回车关闭…")
        except EOFError:
            pass


def venv_python() -> tuple[Path, Path]:
    if sys.platform == "win32":
        folder = ROOT / ".venv" / "Scripts"
        return folder / "python.exe", folder / "pythonw.exe"
    folder = ROOT / ".venv" / "bin"
    python = folder / "python"
    return python, python


def main() -> int:
    configure_stdio()
    if sys.version_info < (3, 10):
        print(f"需要 Python 3.10 或更高版本。当前是 {sys.version.split()[0]}。")
        print("安装时请勾选 Add python.exe to PATH。")
        print("https://www.python.org/downloads/")
        pause()
        return 1

    python, pythonw = venv_python()
    try:
        if not python.exists():
            print("第一次运行，正在创建独立的 Python 环境…")
            subprocess.check_call([sys.executable, "-m", "venv", str(ROOT / ".venv")])
        print("正在检查依赖，第一次可能需要一两分钟…")
        subprocess.check_call(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"准备运行环境失败：{exc}")
        print("请检查网络后重新双击启动脚本。")
        pause()
        return 1

    launcher = pythonw if pythonw.exists() else python
    print("正在打开知识收件箱…")
    popen_kwargs = {"cwd": str(ROOT)}
    if sys.platform == "win32":
        # 和黑色窗口拆开。关掉黑色窗口时，小窗口继续留着。
        popen_kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen([str(launcher), str(ROOT / "main.py")], **popen_kwargs)
    for _ in range(20):
        if raise_inbox_window():
            return 0
        if process.poll() not in (None, 0):
            break
        time.sleep(0.25)
    if raise_inbox_window():
        return 0
    print("窗口没有留住，改用可见方式再打开一次，方便看到错误。")
    code = subprocess.call([str(python), str(ROOT / "main.py")], cwd=str(ROOT))
    if raise_inbox_window():
        return 0
    pause()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
