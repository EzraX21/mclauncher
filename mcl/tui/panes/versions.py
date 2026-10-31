"""版本管理面板：列表、启动、装加载器、删除。"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, ProgressBar, RichLog, Static

from ...java import ensure_java
from ... import auth, skin
from ...launch import build_command, ensure_libraries, prepare_natives, spawn, wait
from ...loaders import install as install_loader
from ...mods import list_mods
from ...versions import VersionError, load_version, remove as remove_version, resolve, scan
from ..common import Confirm, PaneTitle, UiProgress, ui_call
from .loader import LoaderScreen


class VersionsPane(Vertical):
    def compose(self) -> ComposeResult:
        yield PaneTitle("已装版本")
        yield DataTable(id="versions-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(classes="row"):
            yield Button("刷新", id="v-refresh", variant="primary")
            yield Button("启动", id="v-launch")
            yield Button("装加载器", id="v-loader")
            yield Button("日志", id="v-log-toggle")
            yield Button("打开目录", id="v-open")
            yield Button("删除", id="v-delete", variant="error")
        yield Static("", id="v-progress-label", classes="progress-label")
        yield ProgressBar(total=100, show_eta=False, id="v-progress")
        yield RichLog(id="v-log", wrap=True, markup=True, classes="hidden")

    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        self.bar = self.query_one("#v-progress", ProgressBar)
        self.label = self.query_one("#v-progress-label", Static)
        self.log_view = self.query_one("#v-log", RichLog)
        table = self.query_one("#versions-table", DataTable)
        table.add_columns("版本", "加载器", "Java", "模组", "客户端")
        self.version_ids: list[str] = []
        self.refresh_versions()

    @property
    def cfg(self):
        return self.app.cfg

    def refresh_content(self) -> None:
        self.refresh_versions()

    def refresh_versions(self) -> None:
        table = self.query_one("#versions-table", DataTable)
        table.clear()
        versions = scan(self.cfg.root())
        self.version_ids = [version.id for version in versions]
        for version in versions:
            mods_dir = self.cfg.mods_path(version.id)
            mods = len(list_mods(mods_dir)) if mods_dir.exists() else 0
            table.add_row(
                version.id,
                version.loader,
                str(version.java_major or "?"),
                str(mods),
                "✓" if version.has_jar else "—",
            )
        self.log_view.write(f"[dim]刷新：{len(versions)} 个版本[/]")

    # ------------------------------------------------------------------
    def selected(self) -> str | None:
        table = self.query_one("#versions-table", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self.version_ids):
            return self.version_ids[row]
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "v-refresh": self.refresh_versions,
            "v-launch": self._launch_selected,
            "v-loader": self._open_loader,
            "v-log-toggle": self._toggle_log,
            "v-open": self._open_selected,
            "v-delete": self._delete_selected,
        }
        handler = handlers.get(event.button.id or "")
        if handler:
            handler()

    # ------------------------------------------------------------------
    def _toggle_log(self) -> None:
        self.log_view.display = not self.log_view.display

    def _launch_selected(self) -> None:
        version_id = self.selected()
        if not version_id:
            self.app.notify("先选一个版本", severity="warning")
            return
        self.log_view.display = True
        self._log(f"启动 {version_id} …")
        self._launch(version_id)

    def _open_selected(self) -> None:
        from ...platforms import open_in_file_manager

        version_id = self.selected()
        if not version_id:
            self.app.notify("先选一个版本", severity="warning")
            return
        path = self.cfg.version_dir(version_id)
        if not open_in_file_manager(path):
            self._log(f"[yellow]没有文件管理器，目录：{path}[/]")

    def _delete_selected(self) -> None:
        version_id = self.selected()
        if not version_id:
            self.app.notify("先选一个版本", severity="warning")
            return

        def done(confirmed: bool | None) -> None:
            if not confirmed:
                return
            try:
                remove_version(self.cfg.root(), version_id)
            except VersionError as exc:
                self.app.notify(str(exc), severity="error")
                return
            if self.cfg.last_version == version_id:
                self.cfg.last_version = None
                self.cfg.save()
            self._log(f"[red]已删除 {version_id}[/]")
            self.refresh_versions()

        detail = ("该版本目录里的存档、模组和配置会一起删除"
                  if self.cfg.isolate_versions else "公共存档和模组不会动")
        self.app.push_screen(Confirm(f"删除版本 {version_id}？{detail}。"), done)

    def _open_loader(self) -> None:
        version_id = self.selected()
        if not version_id:
            self.app.notify("先选一个版本", severity="warning")
            return
        try:
            game = resolve(self.cfg.root(), version_id).chain[0]
        except Exception as exc:  # noqa: BLE001
            self.app.notify(str(exc), severity="error")
            return
        self.app.push_screen(LoaderScreen(game), self._on_loader_chosen)

    def _on_loader_chosen(self, result) -> None:
        if not result:
            return
        loader, loader_version = result
        version_id = self.selected()
        if not version_id:
            return
        try:
            game = resolve(self.cfg.root(), version_id).chain[0]
        except Exception as exc:  # noqa: BLE001
            self.app.notify(str(exc), severity="error")
            return
        self._install_loader_worker(loader, game, loader_version)

    # ------------------------------------------------------------------
    def _progress(self, label: str, files: int, total_bytes: int) -> UiProgress:
        ui_call(self, lambda: setattr(self.bar, "display", "block"))
        progress = UiProgress(self, self.bar, self.label, files, total_bytes)
        progress.start(label)
        return progress

    def _finish_progress(self) -> None:
        ui_call(self, lambda: setattr(self.bar, "display", "none"))
        ui_call(self, self.label.update, "")

    def _log(self, message: str) -> None:
        self.log_view.write(message)

    def _log_threadsafe(self, message: str) -> None:
        ui_call(self, self._log, message)

    # ------------------------------------------------------------------
    @work(thread=True, group="launch", exclusive=True)
    def _launch(self, version_id: str) -> None:
        try:
            resolved = resolve(self.cfg.root(), version_id)
            java = ensure_java(self.cfg, resolved.java_major,
                               on_phase=self._progress, note=self._log_threadsafe)
            self._finish_progress()
            self._log_threadsafe(f"Java：{java.display}")

            ensure_libraries(resolved, self.cfg.root(), jobs=self.cfg.jobs,
                             on_phase=self._progress, source=self.cfg.source)
            self._finish_progress()
            prepare_natives(resolved, self.cfg.root())

            account = auth.ensure_account(self.cfg)
            self._log_threadsafe(f"账号：{account.name}（微软正版）" if account else "账号：离线模式")
            command = build_command(resolved, self.cfg, java, account=account)
            if command.missing:
                self._log_threadsafe(f"[red]缺少 {len(command.missing)} 个文件，先补全[/]")
                return
            try:
                skin.apply(self.cfg, resolved.chain[0])
            except skin.SkinError as exc:
                self._log_threadsafe(f"[yellow]自定义皮肤不可用：{exc}[/]")
            self._log_threadsafe("启动中…（关闭游戏后这里会显示退出码）")
            process = spawn(command)
            code = wait(process)
            self._log_threadsafe(f"[dim]游戏退出，代码 {code}[/]")
        except Exception as exc:  # noqa: BLE001
            self._log_threadsafe(f"[red]启动失败：{exc}[/]")
        finally:
            self._finish_progress()

    @work(thread=True, group="loader", exclusive=True)
    def _install_loader_worker(self, loader: str, game: str, loader_version: str) -> None:
        self._log_threadsafe(f"安装 {loader} {loader_version} 到 {game} …")
        try:
            base = load_version(self.cfg.root(), game)
            required = (base.get("javaVersion") or {}).get("majorVersion")
            java = ensure_java(self.cfg, required, on_phase=self._progress,
                               note=self._log_threadsafe)
            self._finish_progress()
            self._log_threadsafe(f"使用 {java.display}")
            version_id = install_loader(
                loader, game, self.cfg.root(), loader_version,
                source=self.cfg.source, java=java.path,
                on_log=self._log_threadsafe,
            )
            self._log_threadsafe(f"[green]已创建 {version_id}[/]")
            ui_call(self, self.refresh_versions)
        except Exception as exc:  # noqa: BLE001
            self._log_threadsafe(f"[red]安装失败：{exc}[/]")
