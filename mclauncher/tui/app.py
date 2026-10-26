"""mclauncher 的 Textual 应用。"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from .. import __version__
from ..config import Config
from .panes.install import InstallPane
from .panes.mods import ModsPane
from .panes.settings import SettingsPane
from .panes.versions import VersionsPane


class MclauncherApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "mclauncher"
    SUB_TITLE = f"v{__version__}  ·  Minecraft 启动器"
    BINDINGS = [
        ("q", "quit", "退出"),
        ("ctrl+r", "refresh", "刷新"),
        ("ctrl+s", "save", "保存设置"),
    ]

    def __init__(self, config: Config | None = None):
        super().__init__()
        self.cfg = config or Config.load()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-versions"):
            with TabPane("版本", id="tab-versions"):
                yield VersionsPane()
            with TabPane("安装", id="tab-install"):
                yield InstallPane()
            with TabPane("模组", id="tab-mods"):
                yield ModsPane()
            with TabPane("设置", id="tab-settings"):
                yield SettingsPane()
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "textual-dark"

    @property
    def active_pane(self):
        active = self.query_one(TabbedContent).active
        mapping = {
            "tab-versions": VersionsPane,
            "tab-install": InstallPane,
            "tab-mods": ModsPane,
            "tab-settings": SettingsPane,
        }
        return self.query_one(mapping[active]) if active in mapping else None

    def action_refresh(self) -> None:
        pane = self.active_pane
        if pane is not None and hasattr(pane, "refresh_content"):
            pane.refresh_content()

    def action_save(self) -> None:
        pane = self.active_pane
        if isinstance(pane, SettingsPane):
            pane.save()

    def notify_error(self, message: str) -> None:
        self.notify(message, severity="error", timeout=8)


def run(config: Config | None = None) -> int:
    import sys

    if not sys.stdout.isatty():
        print("TUI 需要交互式终端；脚本里请用子命令（mclauncher --help）")
        return 2
    MclauncherApp(config).run()
    return 0
