"""安装面板：加载官方版本清单、筛选、下载安装。"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, ProgressBar, RichLog, Static

from ...installer import build_plan, execute
from ...manifest import Manifest
from ...progress import human_size
import threading

from ..common import PaneTitle, UiProgress, ui_call


class InstallPane(Vertical):
    def compose(self) -> ComposeResult:
        yield PaneTitle("安装原版")
        with Horizontal(classes="row"):
            yield Input(placeholder="搜索版本，例如 1.20.1", id="i-filter")
            yield Button("刷新清单", id="i-load", variant="primary")
            yield Button("日志", id="i-log-toggle")
        yield DataTable(id="remote-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(classes="row"):
            yield Checkbox("下载资源文件（音效、语言）", value=True, id="i-assets")
            yield Button("安装选中版本", id="i-install", variant="success")
            yield Button("取消安装", id="i-cancel", variant="warning", disabled=True)
        yield Static("", id="i-progress-label", classes="progress-label")
        yield ProgressBar(total=100, show_eta=False, id="i-progress")
        yield RichLog(id="i-log", wrap=True, markup=True, classes="hidden")

    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        self.bar = self.query_one("#i-progress", ProgressBar)
        self.label = self.query_one("#i-progress-label", Static)
        self.log_view = self.query_one("#i-log", RichLog)
        table = self.query_one("#remote-table", DataTable)
        table.add_columns("版本", "类型", "发布日期")
        self.cancel_event: threading.Event | None = None
        self.manifest: Manifest | None = None
        self.all_versions: list = []
        self.filtered_ids: list[str] = []
        self._log("正在读取版本清单 …")
        self.load_manifest()

    @property
    def cfg(self):
        return self.app.cfg

    def refresh_content(self) -> None:
        self.load_manifest()

    # ------------------------------------------------------------------
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "i-filter":
            self._populate()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "i-filter":
            self._populate()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "i-load":
            self.load_manifest()
        elif event.button.id == "i-install":
            self._install_selected()
        elif event.button.id == "i-log-toggle":
            self.toggle_log()
        elif event.button.id == "i-cancel":
            self._cancel_install()

    # ------------------------------------------------------------------
    def toggle_log(self) -> None:
        self.log_view.display = not self.log_view.display

    def show_log(self) -> None:
        self.log_view.display = True

    def _log(self, message: str) -> None:
        self.log_view.write(message)

    def _log_threadsafe(self, message: str) -> None:
        ui_call(self, self._log, message)

    def _populate(self) -> None:
        table = self.query_one("#remote-table", DataTable)
        table.clear()
        query = self.query_one("#i-filter", Input).value.strip().lower()
        versions = [v for v in self.all_versions if not query or query in v.id.lower()]
        self.filtered_ids = [v.id for v in versions]
        for version in versions:
            table.add_row(version.id, version.type, version.release_time[:10])

    def _selected(self) -> str | None:
        table = self.query_one("#remote-table", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self.filtered_ids):
            return self.filtered_ids[row]
        return None

    # ------------------------------------------------------------------
    @work(thread=True, group="manifest", exclusive=True)
    def load_manifest(self) -> None:
        try:
            manifest = Manifest.load(self.cfg.download_source)
        except Exception as exc:  # noqa: BLE001
            self._log_threadsafe(f"[red]读取清单失败：{exc}[/]")
            return
        self.manifest = manifest
        self.all_versions = manifest.versions
        ui_call(self, self._populate)
        ui_call(self, self._log, f"[green]清单已加载：{len(manifest.versions)} 个版本[/]")

    def _progress(self, label: str, files: int, total_bytes: int) -> UiProgress:
        ui_call(self, lambda: setattr(self.bar, "display", "block"))
        progress = UiProgress(self, self.bar, self.label, files, total_bytes)
        progress.start(label)
        return progress

    def _finish_progress(self) -> None:
        ui_call(self, lambda: setattr(self.bar, "display", "none"))
        ui_call(self, self.label.update, "")

    def _cancel_install(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
            self._log("正在取消 …")
            self.query_one("#i-cancel", Button).disabled = True

    def _set_installing(self, running: bool) -> None:
        self.query_one("#i-cancel", Button).disabled = not running
        self.query_one("#i-install", Button).disabled = running

    def _install_selected(self) -> None:
        version_id = self._selected()
        if not version_id:
            self.app.notify("先在列表里选一个版本", severity="warning")
            return
        if self.manifest is None:
            self.app.notify("版本清单还没加载好", severity="warning")
            return
        with_assets = self.query_one("#i-assets", Checkbox).value
        if self.cancel_event is not None:
            self.cancel_event.set()  # 取消上一次
        self.cancel_event = threading.Event()
        self._set_installing(True)
        self._log(f"开始安装 {version_id}（资源文件：{'是' if with_assets else '否'}）")
        self._install(version_id, with_assets)

    @work(thread=True, group="install", exclusive=True)
    def _install(self, version_id: str, with_assets: bool) -> None:
        try:
            assert self.manifest is not None
            entry = self.manifest.resolve(version_id)
            version_json = self.manifest.version_json(entry)
            plan = build_plan(
                version_json,
                self.cfg.root(),
                with_assets=with_assets,
                source=self.cfg.download_source,
            )
            ui_call(self, self.show_log)
            self._log_threadsafe(
                f"计划：{plan.total_files} 个文件，约 {human_size(plan.total_bytes)}"
            )
            result = execute(
                plan,
                jobs=self.cfg.jobs,
                on_phase=self._progress,
                on_note=self._log_threadsafe,
                cancel=self.cancel_event,
            )
            self._finish_progress()
            if result.cancelled:
                self._log_threadsafe("[yellow]安装已取消，已下载的文件保留，重跑会续传[/]")
            elif result.ok:
                self._log_threadsafe(
                    f"[green]完成：{version_id}，新下载 {human_size(result.downloaded_bytes)}[/]"
                )
                ui_call(self, self._after_install, version_id)
            else:
                self._log_threadsafe(f"[red]{len(result.errors)} 个文件失败，重试即可续传[/]")
                for error in result.errors[:3]:
                    self._log_threadsafe(f"[red]{error}[/]")
        except Exception as exc:  # noqa: BLE001
            self._log_threadsafe(f"[red]安装失败：{exc}[/]")
        finally:
            self._finish_progress()
            self.cancel_event = None
            ui_call(self, self._set_installing, False)

    def _after_install(self, version_id: str) -> None:
        self.cfg.last_version = version_id
        self.cfg.save()
        from .versions import VersionsPane

        pane = self.app.query_one(VersionsPane)
        pane.refresh_versions()
        self.app.notify(f"{version_id} 安装完成", severity="information")
