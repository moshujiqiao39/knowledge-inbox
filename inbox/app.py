from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from inbox.clipboard import ClipboardError, read_clipboard
from inbox.instance import AlreadyRunning, SingleInstance
from inbox.logic import MAX_CHARS, hotkey_label
from inbox.paths import data_root
from inbox.server import ServerState, start_server
from inbox.settings import load_settings
from inbox.store import Store, save_text
from inbox.winutil import (
    disable_console_quick_edit,
    force_foreground,
    modifiers_held,
    widget_hwnd,
)


def fatal(message: str) -> None:
    logging.error(message)
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("知识收件箱", message)
        root.destroy()
    except Exception:
        if sys.stderr is not None:
            print(message, file=sys.stderr)
    raise SystemExit(1)


class App:
    def __init__(self) -> None:
        disable_console_quick_edit()
        self.data_dir = data_root()
        self._setup_logging()
        try:
            self._instance = SingleInstance(self.data_dir / "inbox.lock")
        except AlreadyRunning:
            fatal("知识收件箱已经在运行。请到任务栏里找到它的窗口。")

        self.settings = load_settings(self.data_dir / "settings.json")
        self.hotkey_spec = self.settings["hotkey"]
        self.hotkey_text = hotkey_label(self.hotkey_spec)
        self.store = Store(self.data_dir / "knowledge.md")
        self.state = ServerState(self.store, self.hotkey_text)
        try:
            self.httpd, self.port = start_server(self.state, int(self.settings["port"]))
        except OSError as exc:
            fatal(str(exc))
        self.url = f"http://127.0.0.1:{self.port}"
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, name="inbox-http", daemon=True)
        self.server_thread.start()
        logging.info("搜索页 %s", self.url)

        self.queue: queue.Queue[str] = queue.Queue()
        self.busy = False
        self.hotkeys = None
        self.root = tk.Tk()
        self.root.report_callback_exception = self._report_callback_exception
        self._build_window()
        self._start_hotkey()
        self.refresh_count()
        self.root.after(80, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if os.environ.get("INBOX_NO_BROWSER") != "1":
            self.root.after(700, self.open_search)

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        logging.info("退出")
        if self.hotkeys is not None:
            try:
                self.hotkeys.stop()
            except Exception:
                logging.exception("停止快捷键失败")
        threading.Thread(target=self._stop_server, name="inbox-http-stop", daemon=True).start()
        try:
            self._instance.close()
        except Exception:
            logging.exception("释放单实例锁失败")
        self.root.destroy()

    def open_search(self) -> None:
        webbrowser.open(self.url)

    def open_folder(self) -> None:
        folder = str(self.store.path.parent)
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        except OSError as exc:
            self.set_status(f"打不开文件夹：{exc}", error=True)

    def capture(self) -> None:
        try:
            kind, text = read_clipboard()
        except ClipboardError as exc:
            self.show_notice(str(exc))
            return
        if kind == "image":
            self.show_notice("剪贴板里是图片。第一版只收录文字和链接。")
            return
        if kind != "text" or not text.strip():
            self.show_notice("剪贴板是空的。请先复制一段文字或链接，再按快捷键。")
            return
        if len(text.strip()) > MAX_CHARS:
            self.show_notice("这段内容超过 10 万字，没有收录。请只复制需要的部分。")
            return
        self.show_capture_dialog(text)

    def show_notice(self, message: str) -> None:
        dialog = self._dialog("知识收件箱", 440, 180)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=message, wraplength=390, justify="left").pack(anchor="w", fill="x")
        button = ttk.Button(frame, text="知道了", command=dialog.destroy)
        button.pack(anchor="e", pady=(16, 0))
        dialog.bind("<Return>", lambda _event: dialog.destroy())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._present(dialog)
        button.focus_set()
        dialog.grab_set()
        dialog.wait_window()

    def show_capture_dialog(self, text: str) -> None:
        dialog = self._dialog("收录到知识库", 560, 420)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="剪贴板内容").pack(anchor="w")
        preview = tk.Text(frame, height=8, wrap="word", relief="solid", borderwidth=1)
        preview.pack(fill="both", expand=True, pady=(6, 10))
        shown = text.strip()
        if len(shown) > 4000:
            shown = shown[:4000] + "\n…（后面还有，保存时会完整写入）"
        preview.insert("1.0", shown)
        preview.configure(state="disabled")

        ttk.Label(frame, text="标签，用空格或逗号分隔，可以不填。例如：工作 灵感").pack(anchor="w")
        tags_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=tags_var)
        entry.pack(fill="x", pady=(6, 8))
        hint = ttk.Label(frame, text="", wraplength=510, justify="left")
        hint.pack(anchor="w", fill="x")

        saving = {"on": False}

        def save(_event=None):
            if saving["on"]:
                return "break"
            saving["on"] = True
            status, message = save_text(self.store, text, tags_var.get())
            if status in ("saved", "updated"):
                logging.info("收录结果 %s id 已写入", status)
                self.set_status(message, error=False)
                self.refresh_count()
                dialog.destroy()
                return "break"
            hint.configure(text=message)
            saving["on"] = False
            return "break"

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(12, 0))
        ttk.Button(buttons, text="保存", command=save).pack(side="left")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left", padx=(8, 0))
        dialog.bind("<Return>", save)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._present(dialog)
        entry.focus_set()
        entry.icursor("end")

        def refocus() -> None:
            try:
                if dialog.winfo_exists():
                    entry.focus_force()
            except tk.TclError:
                return

        dialog.after(200, refocus)
        dialog.grab_set()
        dialog.wait_window()

    def refresh_count(self) -> None:
        count = len(self.store.list_entries())
        self.count_var.set(f"已收录    {count} 条")

    def set_status(self, message: str, *, error: bool = False) -> None:
        self.status_var.set(message)
        self.status_label.configure(foreground="#9a3412" if error else "#0b6b2a")

    def _build_window(self) -> None:
        self.root.title("知识收件箱")
        self._use_cjk_font()
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="知识收件箱", font=self.title_font).pack(anchor="w")
        ttk.Label(
            frame,
            text="复制一段文字或链接，按下快捷键，输入标签后回车。",
            wraplength=460,
        ).pack(anchor="w", pady=(8, 14))

        self.hotkey_var = tk.StringVar(value=f"快捷键    {self.hotkey_text}")
        self.url_var = tk.StringVar(value=f"搜索页    {self.url}")
        self.count_var = tk.StringVar(value="已收录    0 条")
        self.status_var = tk.StringVar(value="正在运行")
        for variable in (self.hotkey_var, self.url_var, self.count_var):
            ttk.Label(frame, textvariable=variable).pack(anchor="w", pady=1)

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w", pady=(16, 8))
        ttk.Button(buttons, text="收录剪贴板", command=self._capture_from_button).pack(side="left")
        ttk.Button(buttons, text="打开搜索页", command=self.open_search).pack(side="left", padx=8)
        ttk.Button(buttons, text="打开数据文件夹", command=self.open_folder).pack(side="left")

        self.status_label = ttk.Label(frame, textvariable=self.status_var, wraplength=460, justify="left")
        self.status_label.pack(anchor="w", pady=(10, 0))
        self.status_label.configure(foreground="#0b6b2a")
        self.root.update_idletasks()
        width = max(frame.winfo_reqwidth() + 24, 520)
        height = max(frame.winfo_reqheight() + 24, 280)
        self.root.minsize(width, height)
        self._center(self.root, width, height)

    def _capture_from_button(self) -> None:
        if self.busy:
            return
        self.busy = True
        try:
            self.capture()
        finally:
            self._drain_queue()
            self.busy = False

    def _start_hotkey(self) -> None:
        try:
            from pynput import keyboard

            self.hotkeys = keyboard.GlobalHotKeys({self.hotkey_spec: self._enqueue_capture})
            self.hotkeys.start()
        except ImportError:
            logging.exception("没有 pynput")
            self.hotkey_var.set("快捷键    未安装 pynput")
            self.set_status("快捷键不可用。请重新双击启动脚本。现在可以用「收录剪贴板」按钮。", error=True)
        except Exception as exc:
            logging.exception("注册快捷键失败")
            self.hotkey_var.set("快捷键    注册失败")
            self.set_status(f"快捷键 {self.hotkey_text} 注册失败：{exc}。请改 settings.json，或先用按钮收录。", error=True)

    def _enqueue_capture(self) -> None:
        self.queue.put("capture")

    def _poll(self) -> None:
        job = None
        try:
            job = self.queue.get_nowait()
        except queue.Empty:
            pass
        if job == "capture" and not self.busy:
            self.busy = True
            self._capture_when_keys_released(0)
        self.root.after(80, self._poll)

    def _capture_when_keys_released(self, attempt: int) -> None:
        if attempt < 4 or (modifiers_held() and attempt < 40):
            self.root.after(50, lambda: self._capture_when_keys_released(attempt + 1))
            return
        try:
            self.capture()
        finally:
            self._drain_queue()
            self.busy = False

    def _drain_queue(self) -> None:
        try:
            while True:
                self.queue.get_nowait()
        except queue.Empty:
            return

    def _dialog(self, title: str, width: int, height: int) -> tk.Toplevel:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.attributes("-topmost", True)
        dialog._inbox_min = (width, height)  # noqa: SLF001 - 只在这个窗口上记下最小尺寸
        return dialog

    def _present(self, window) -> None:
        window.update_idletasks()
        minimum = getattr(window, "_inbox_min", (420, 150))
        width = max(window.winfo_reqwidth() + 8, minimum[0])
        height = max(window.winfo_reqheight() + 8, minimum[1])
        self._center(window, width, height)
        window.deiconify()
        window.lift()
        window.attributes("-topmost", True)
        window.update_idletasks()
        try:
            force_foreground(widget_hwnd(window))
        except Exception:
            logging.exception("把窗口带到前台失败")
        window.focus_force()

    def _center(self, window, width: int, height: int) -> None:
        window.update_idletasks()
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _use_cjk_font(self) -> None:
        family = "Microsoft YaHei UI" if sys.platform == "win32" else "PingFang SC"
        available = set(tkfont.families(self.root))
        if family not in available:
            self.title_font = tkfont.nametofont("TkDefaultFont").copy()
            self.title_font.configure(size=16)
            return
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except tk.TclError:
                continue
        self.title_font = tkfont.Font(family=family, size=16)

    def _setup_logging(self) -> None:
        try:
            logging.basicConfig(
                filename=self.data_dir / "inbox.log",
                encoding="utf-8",
                level=logging.INFO,
                format="%(asctime)s %(levelname)s %(message)s",
            )
        except OSError:
            logging.basicConfig(level=logging.INFO)

    def _report_callback_exception(self, exc, val, tb) -> None:
        logging.error("界面出错", exc_info=(exc, val, tb))
        self.set_status(f"出错了：{val}", error=True)

    def _stop_server(self) -> None:
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            logging.exception("关闭搜索页失败")


def main() -> None:
    if sys.version_info < (3, 10):
        fatal(f"需要 Python 3.10 或更高版本。当前是 {sys.version.split()[0]}。")
    app = App()
    app.run()
