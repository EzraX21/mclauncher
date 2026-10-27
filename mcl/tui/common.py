"""TUI 通用组件：确认弹窗、进度适配、跨线程调用。"""

from __future__ import annotations

import threading
import time
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, ProgressBar, Static

from ..progress import human_size


def ui_call(widget, fn: Callable, *args, **kwargs) -> None:
    app = widget.app
    if threading.current_thread() is threading.main_thread():
        fn(*args, **kwargs)
    else:
        app.call_from_thread(fn, *args, **kwargs)


class Confirm(ModalScreen[bool]):
    """简单的确认弹窗，返回 True / False。"""

    BINDINGS = [("escape", "dismiss(False)", "取消")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="confirm-box"):
            yield Static(self.message, classes="confirm-text")
            with Horizontal(classes="confirm-buttons"):
                yield Button("取消", id="confirm-no")
                yield Button("确定", id="confirm-yes", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class UiProgress:
    """把下载进度映射到 TUI 进度条 + 文字（线程安全）。"""

    def __init__(self, widget, bar: ProgressBar, label: Static,
                 total_files: int, total_bytes: int):
        self.widget = widget
        self.bar = bar
        self.label = label
        self.total_files = max(total_files, 0)
        self.total_bytes = max(total_bytes, 0)
        self.done_files = 0
        self.done_bytes = 0
        self.started = time.monotonic()
        self._last = 0.0
        self._title = ""

    # ------------------------------------------------------------------
    def start(self, title: str) -> None:
        self._title = title
        ui_call(self.widget, self._render, True)

    def add(self, nbytes: int) -> None:
        self.done_bytes += max(0, nbytes)
        self._render_throttled()

    def tick(self) -> None:
        self.done_files += 1
        self._render_throttled()

    # ------------------------------------------------------------------
    def _render_throttled(self) -> None:
        now = time.monotonic()
        if now - self._last < 0.1 and self.done_files < self.total_files:
            return
        ui_call(self.widget, self._render, False)

    def _render(self, force: bool) -> None:
        if self.total_files:
            ratio = min(1.0, self.done_files / self.total_files)
        elif self.total_bytes:
            ratio = min(1.0, self.done_bytes / self.total_bytes)
        else:
            ratio = 0.0
        self.bar.update(total=100, progress=ratio * 100)
        elapsed = max(time.monotonic() - self.started, 0.001)
        speed = human_size(self.done_bytes / elapsed) + "/s" if self.done_bytes else "—"
        amount = human_size(self.done_bytes)
        if self.total_bytes:
            amount += f" / {human_size(self.total_bytes)}"
        self.label.update(
            f"{self._title}  {self.done_files}/{self.total_files} 个文件  {amount}  {speed}"
        )


class PaneTitle(Static):
    pass
