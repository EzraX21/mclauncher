"""终端进度条：TTY 下是单行刷新，重定向时按 10% 打点。"""

from __future__ import annotations

import sys
import threading
import time
from typing import TextIO


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} B" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def human_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


class ProgressReporter:
    """一个下载阶段的进度。文件数、字节数、速度、ETA 都算给你看。"""

    def __init__(self, label: str, total_files: int, total_bytes: int,
                 width: int = 22, stream: TextIO | None = None):
        self.label = label
        self.total_files = max(total_files, 0)
        self.total_bytes = max(total_bytes, 0)
        self.width = width
        self.stream = stream or sys.stdout
        self.done_files = 0
        self.done_bytes = 0
        self.started = time.monotonic()
        self._last_render = 0.0
        self._last_bucket = -1
        self._lock = threading.Lock()
        self._finished = False

    # ------------------------------------------------------------------ 对外
    def tick(self) -> None:
        with self._lock:
            self.done_files += 1
            self._render(force=False)

    def add(self, nbytes: int) -> None:
        with self._lock:
            self.done_bytes += max(0, nbytes)

    def finish(self) -> None:
        with self._lock:
            if not self._finished:
                self._render(force=True, final=True)
                self._finished = True

    # ------------------------------------------------------------------ 内部
    @property
    def _ratio(self) -> float:
        if self.total_files:
            return min(1.0, self.done_files / self.total_files)
        if self.total_bytes:
            return min(1.0, self.done_bytes / self.total_bytes)
        return 1.0

    def _line(self, final: bool = False) -> str:
        ratio = self._ratio
        filled = int(round(ratio * self.width))
        bar = "█" * filled + "░" * (self.width - filled)
        elapsed = max(time.monotonic() - self.started, 0.001)
        speed = self.done_bytes / elapsed
        amount = human_size(self.done_bytes)
        if self.total_bytes:
            amount += f"/{human_size(self.total_bytes)}"
        text = (f"  {self.label}  {bar} {ratio * 100:3.0f}%  "
                f"{self.done_files}/{self.total_files}  "
                f"{amount}  {human_size(speed)}/s")
        if not final and speed > 0 and self.total_bytes > self.done_bytes and ratio >= 0.03:
            text += f"  剩余 {human_time((self.total_bytes - self.done_bytes) / speed)}"
        return text

    def _render(self, force: bool = False, final: bool = False) -> None:
        if not sys.stdout.isatty():
            bucket = int(self._ratio * 10)
            if not final and bucket <= self._last_bucket:
                return
            self._last_bucket = bucket
            print(self._line(final=False).rstrip())
            return
        now = time.monotonic()
        if not force and now - self._last_render < 0.1:
            return
        self._last_render = now
        self.stream.write("\r" + self._line(final=final).ljust(6) + ("\n" if final else "   "))
        self.stream.flush()
