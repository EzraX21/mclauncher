"""设置面板：路径、内存、用户名、隔离、下载源。"""

from __future__ import annotations

import platform
import sys

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, RichLog, Select, Static, Switch

from ... import __version__, platforms
from ...config import config_path
from ...java import find_all
from ..common import PaneTitle, ui_call


class SettingsPane(Vertical):
    def compose(self) -> ComposeResult:
        yield PaneTitle("设置")
        with Horizontal(classes="row"):
            yield Static("游戏目录", classes="label")
            yield Input(id="s-dir")
        with Horizontal(classes="row"):
            yield Static("Java 路径", classes="label")
            yield Input(placeholder="留空 = 自动查找", id="s-java")
        with Horizontal(classes="row"):
            yield Static("内存 (MB)", classes="label")
            yield Input(id="s-memory", type="integer")
            yield Static("用户名", classes="label")
            yield Input(id="s-username")
        with Horizontal(classes="row"):
            yield Static("CurseForge key", classes="label")
            yield Input(placeholder="可选，模组来源选 CurseForge 时需要", password=True, id="s-cf-key")
        with Horizontal(classes="row"):
            yield Static("版本隔离", classes="label")
            yield Switch(value=True, id="s-isolate")
            yield Static("下载源", classes="label")
            yield Select([("仅官方（默认）", "official"), ("BMCLAPI 镜像优先", "auto")], id="s-source")
        with Horizontal(classes="row"):
            yield Button("保存", id="s-save", variant="success")
            yield Button("检测 Java", id="s-java-check")
            yield Button("打开配置目录", id="s-open-config")
        yield RichLog(id="s-log", wrap=True, markup=True)

    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        self.log_view = self.query_one("#s-log", RichLog)
        cfg = self.app.cfg
        self.query_one("#s-dir", Input).value = str(cfg.root())
        self.query_one("#s-java", Input).value = cfg.java_path or ""
        self.query_one("#s-memory", Input).value = str(cfg.memory_mb)
        self.query_one("#s-username", Input).value = cfg.username
        self.query_one("#s-cf-key", Input).value = cfg.curseforge_api_key
        self.query_one("#s-isolate", Switch).value = cfg.isolate_versions
        self.query_one("#s-source", Select).value = cfg.download_source
        self._log(
            f"[bold]mcl {__version__}[/]  ·  Python {sys.version.split()[0]}  ·  "
            f"{platform.system()} {platform.machine()}"
        )
        self._log(f"配置：{config_path()}")
        self._log(f"游戏目录：{cfg.root()}")

    @property
    def cfg(self):
        return self.app.cfg

    def refresh_content(self) -> None:
        self.on_mount()

    def _log(self, message: str) -> None:
        self.log_view.write(message)

    # ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "s-save":
            self.save()
        elif event.button.id == "s-java-check":
            self.check_java()
        elif event.button.id == "s-open-config":
            path = config_path().parent
            if not platforms.open_in_file_manager(path):
                self._log(f"配置目录：{path}")

    def save(self) -> None:
        cfg = self.app.cfg
        directory = self.query_one("#s-dir", Input).value.strip()
        java = self.query_one("#s-java", Input).value.strip()
        memory = self.query_one("#s-memory", Input).value.strip()
        username = self.query_one("#s-username", Input).value.strip() or "Player"

        if memory and (not memory.isdigit() or not 512 <= int(memory) <= 65536):
            self.app.notify("内存要填 512-65536 之间的整数", severity="error")
            return

        cfg.game_dir = directory or None
        cfg.java_path = java or None
        cfg.memory_mb = int(memory) if memory else cfg.memory_mb
        cfg.username = username
        cfg.curseforge_api_key = self.query_one("#s-cf-key", Input).value.strip()
        cfg.isolate_versions = self.query_one("#s-isolate", Switch).value
        value = self.query_one("#s-source", Select).value
        if isinstance(value, str):
            cfg.download_source = value
        path = cfg.save()
        self._log(f"[green]已保存到 {path}[/]")
        self.app.notify("设置已保存", severity="information")

    @work(thread=True, group="java-check", exclusive=True)
    def check_java(self) -> None:
        runtimes = find_all(self.cfg)
        if not runtimes:
            ui_call(self, self._log, "[yellow]没找到 Java，可以在安装面板里让工具下载[/]")
            return
        for runtime in runtimes:
            ui_call(self, self._log, f"{runtime.display:<22} {runtime.path}")
