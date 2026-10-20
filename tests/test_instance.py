from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from inbox.instance import AlreadyRunning, SingleInstance


class InstanceTests(unittest.TestCase):
    def test_second_process_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "inbox.lock"
            holder = Path(__file__).resolve().parent / "hold_lock.py"
            process = subprocess.Popen(
                [sys.executable, str(holder), str(lock)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            timer = threading.Timer(8, process.kill)
            timer.start()
            try:
                assert process.stdout is not None
                line = process.stdout.readline()
                if line.strip() != "LOCKED":
                    error = ""
                    if process.poll() is not None and process.stderr is not None:
                        error = process.stderr.read()
                    self.fail(f"锁进程没有启动：{line!r} {error}")
                with self.assertRaises(AlreadyRunning):
                    SingleInstance(lock)
            finally:
                timer.cancel()
                process.kill()
                process.wait(timeout=5)
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()


if __name__ == "__main__":
    unittest.main()
