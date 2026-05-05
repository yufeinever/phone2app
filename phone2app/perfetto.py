from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .adb import Adb


@dataclass
class PerfettoCapture:
    process: subprocess.Popen
    remote_path: str
    local_path: Path


class PerfettoCollector:
    def __init__(self, adb: Adb):
        self.adb = adb

    def start(self, local_path: Path, seconds: int = 15) -> Optional[PerfettoCapture]:
        remote_path = f"/data/misc/perfetto-traces/phone2app-{int(time.time() * 1000)}.perfetto-trace"
        command = (
            f"perfetto -o {remote_path} -t {int(seconds)}s "
            "sched freq idle am wm gfx view binder_driver hal dalvik input res memory"
        )
        args = self.adb.base_args() + ["shell", command]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return PerfettoCapture(process=process, remote_path=remote_path, local_path=local_path)

    def finish(self, capture: Optional[PerfettoCapture], timeout: int = 60) -> Optional[str]:
        if capture is None:
            return None
        try:
            capture.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            capture.process.terminate()
            capture.process.wait(timeout=5)
        if capture.process.returncode not in (0, None):
            return None
        try:
            self.adb.pull(capture.remote_path, capture.local_path)
            return str(capture.local_path)
        finally:
            self.adb.remove_remote(capture.remote_path)
