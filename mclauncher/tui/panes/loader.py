"""装加载器的弹窗：选加载器、选版本，然后交给版本面板去装。"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Select, Static

from ... import loaders
from ..common import PaneTitle, ui_call


class LoaderScreen(ModalScreen[tuple[str, str] | None]):
    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, game_version: str):
        super().__init__()
        self.game_version = game_version
        self.versions: list[loaders.LoaderVersion] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="loader-box"):
            yield PaneTitle(f"给 {self.game_version} 装加载器")
            with Horizontal(classes="row"):
                yield Select(
                    [(loaders.LABELS[name], name) for name in loaders.SUPPORTED],
                    value="fabric",
                    id="l-loader",
                )
                yield Static("", id="l-status", classes="progress-label")
            yield Select([], prompt="加载版本列表…", id="l-version", disabled=True)
            with Horizontal(classes="confirm-buttons"):
                yield Button("取消", id="l-cancel")
                yield Button("安装", id="l-install", variant="success", disabled=True)

    def on_mount(self) -> None:
        self.load_versions("fabric")

    # ------------------------------------------------------------------
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "l-loader" and isinstance(event.value, str):
            self.load_versions(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "l-cancel":
            self.dismiss(None)
        elif event.button.id == "l-install":
            loader = self.query_one("#l-loader", Select).value
            version = self.query_one("#l-version", Select).value
            if isinstance(loader, str) and isinstance(version, str):
                self.dismiss((loader, version))
            else:
                self.notify("没有可安装的版本", severity="warning")

    def action_cancel(self) -> None:
        self.dismiss(None)

    # ------------------------------------------------------------------
    def load_versions(self, loader: str) -> None:
        """主线程入口：先标忙，再起后台请求，并递增代号防止旧结果覆盖。"""
        self._request_id = getattr(self, "_request_id", 0) + 1
        self._set_busy()
        self._fetch_versions(loader, self._request_id)

    @work(thread=True, group="loader-versions", exclusive=True)
    def _fetch_versions(self, loader: str, request_id: int) -> None:
        try:
            versions = loaders.list_versions(loader, self.game_version, self.app.cfg.download_source)
        except Exception as exc:  # noqa: BLE001
            ui_call(self, self._apply_error, request_id, str(exc))
            return
        ui_call(self, self._apply_versions, request_id, versions)

    def _apply_versions(self, request_id: int, versions: list) -> None:
        if request_id != getattr(self, "_request_id", 0):
            return  # 已经有更新的请求了，丢弃旧结果
        self.versions = versions
        self._populate()

    def _apply_error(self, request_id: int, message: str) -> None:
        if request_id != getattr(self, "_request_id", 0):
            return
        self.versions = []
        self._set_status(f"读取失败：{message}")
        self.query_one("#l-version", Select).set_options([("（读取失败）", None)])
        self.query_one("#l-version", Select).disabled = True
        self.query_one("#l-install", Button).disabled = True

    def _set_status(self, text: str) -> None:
        self.query_one("#l-status", Static).update(text)

    def _set_busy(self) -> None:
        select = self.query_one("#l-version", Select)
        select.set_options([("读取中 …", None)])
        select.value = None
        select.disabled = True
        self.query_one("#l-install", Button).disabled = True
        self._set_status("读取版本列表 …")

    def _populate(self) -> None:
        select = self.query_one("#l-version", Select)
        install = self.query_one("#l-install", Button)
        if not self.versions:
            game = self.game_version
            loader = self.query_one("#l-loader", Select).value
            hint = ""
            if loader == "neoforge":
                hint = "（NeoForge 按游戏版本发布，可能还没跟上）"
            self._set_status(f"没有支持 {game} 的版本 {hint}")
            select.set_options([("（无可用版本）", None)])
            select.value = None
            select.disabled = True
            install.disabled = True
            install.variant = "default"
            return
        select.set_options([(item.label, item.version) for item in self.versions])
        select.disabled = False
        preferred = next((item for item in self.versions if item.recommended),
                         next((item for item in self.versions if item.stable), self.versions[0]))
        select.value = preferred.version
        install.disabled = False
        install.variant = "success"
        self._set_status(f"共 {len(self.versions)} 个版本")
