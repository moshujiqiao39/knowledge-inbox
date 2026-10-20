from __future__ import annotations

import os
import sys
from pathlib import Path


class AlreadyRunning(Exception):
    pass


class SingleInstance:
    """占住一个锁文件，避免两个窗口同时写同一份笔记。"""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handle = open(path, "a+b")
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() == 0:
            self._handle.write(b"\0")
            self._handle.flush()
        self._handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            raise AlreadyRunning() from exc

    def close(self) -> None:
        try:
            if sys.platform == "win32":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._handle.close()
