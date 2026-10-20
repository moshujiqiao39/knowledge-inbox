from __future__ import annotations

import sys

import tkinter  # PyInstaller 需要在入口模块里看见 tkinter。


def _fail_version() -> None:
    message = f"需要 Python 3.10 或更高版本。当前是 {sys.version.split()[0]}。"
    try:
        from inbox.app import fatal

        fatal(message)
    except SystemExit:
        raise
    except Exception:
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        raise SystemExit(1)


if sys.version_info < (3, 10):
    _fail_version()

from inbox.app import main


if __name__ == "__main__":
    main()
