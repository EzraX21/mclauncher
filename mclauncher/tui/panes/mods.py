"""模组面板：本地模组开关 / 删除，Modrinth 搜索安装。"""

from __future__ import annotations

import threading

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, RichLog, Select, Static

from ... import modrinth
from ...mods import find, list_mods, remove, set_enabled
from ...platforms import open_in_file_manager
from ...progress import human_size
from ...versions import detect_loader, resolve, scan
from ..common import Confirm, PaneTitle, ui_call


class ModsPane(Vertical):
    def compose(self) -> ComposeResult:
        yield PaneTitle("模组")
        with Horizontal(classes="row"):
            yield Select([], prompt="选择版本", id="m-version")
            yield Button("刷新", id="m-refresh", variant="primary")
            yield Button("启用 / 禁用", id="m-toggle")
            yield Button("删除", id="m-delete", variant="error")
            yield Button("打开 mods 目录", id="m-open")
        yield DataTable(id="mods-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(classes="row"):
            yield Input(placeholder="在 Modrinth 搜模组，例如 sodium", id="m-query")
            yield Button("搜索", id="m-search")
            yield Button("日志", id="m-log-toggle")
            yield Button("安装选中", id="m-install", variant="success")
            yield Button("取消安装", id="m-cancel", variant="warning", disabled=True)
        yield DataTable(id="results-table", cursor_type="row", zebra_stripes=True, classes="hidden")
        yield RichLog(id="m-log", wrap=True, markup=True, classes="hidden")

    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        self.log_view = self.query_one("#m-log", RichLog)
        mods_table = self.query_one("#mods-table", DataTable)
        mods_table.add_columns("状态", "名称", "版本", "大小")
        results = self.query_one("#results-table", DataTable)
        results.add_columns("名称", "标识", "下载量")
        self.cancel_event: threading.Event | None = None
        self.local_mods: list = []
        self.results: list = []
        self.load_versions()

    @property
    def cfg(self):
        return self.app.cfg

    def refresh_content(self) -> None:
        self.load_versions()

    # ------------------------------------------------------------------
    def load_versions(self) -> None:
        versions = scan(self.cfg.root())
        options = [(version.id, version.id) for version in versions]
        select = self.query_one("#m-version", Select)
        if options:
            select.set_options(options)
            target = self.cfg.last_version if self.cfg.last_version in {v.id for v in versions} else None
            select.value = target or options[0][1]
        else:
            select.set_options([("（没有已装版本）", None)])
            select.disabled = True
        self.refresh_mods()

    def selected_version(self) -> str | None:
        value = self.query_one("#m-version", Select).value
        return value if isinstance(value, str) else None

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "m-version":
            self.refresh_mods()

    def refresh_mods(self) -> None:
        table = self.query_one("#mods-table", DataTable)
        table.clear()
        version_id = self.selected_version()
        if not version_id:
            self.local_mods = []
            return
        self.local_mods = list_mods(self.cfg.mods_path(version_id))
        for mod in self.local_mods:
            table.add_row(
                "启用" if mod.enabled else "禁用",
                mod.title or mod.name,
                mod.version or "—",
                human_size(mod.size),
            )

    # ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "m-refresh": self.load_versions,
            "m-toggle": self._toggle,
            "m-delete": self._delete,
            "m-open": self._open,
            "m-search": self._search,
            "m-install": self._install_selected,
            "m-log-toggle": lambda: setattr(self.log_view, "display", not self.log_view.display),
            "m-cancel": self._cancel_install,
        }
        handler = handlers.get(event.button.id or "")
        if handler:
            handler()

    def _selected_mod(self):
        table = self.query_one("#mods-table", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self.local_mods):
            return self.local_mods[row]
        return None

    def _toggle(self) -> None:
        mod = self._selected_mod()
        if mod is None:
            self.app.notify("先在列表里选一个模组", severity="warning")
            return
        try:
            set_enabled(mod, not mod.enabled)
            self._log(f"{'启用' if not mod.enabled else '禁用'} {mod.name}")
        except OSError as exc:
            self._log(f"[red]{exc}[/]")
        self.refresh_mods()

    def _delete(self) -> None:
        mod = self._selected_mod()
        if mod is None:
            self.app.notify("先在列表里选一个模组", severity="warning")
            return

        def done(confirmed: bool | None) -> None:
            if confirmed:
                remove(mod)
                self._log(f"已删除 {mod.name}")
                self.refresh_mods()

        self.app.push_screen(Confirm(f"删除 {mod.name}？"), done)

    def _open(self) -> None:
        version_id = self.selected_version()
        if not version_id:
            return
        path = self.cfg.mods_dir(version_id)
        if not open_in_file_manager(path):
            self._log(f"目录：{path}")

    # ------------------------------------------------------------------
    def _search(self) -> None:
        query = self.query_one("#m-query", Input).value.strip()
        version_id = self.selected_version()
        if not query:
            self.app.notify("先输入关键词", severity="warning")
            return
        if not version_id:
            self.app.notify("先选一个版本", severity="warning")
            return
        loader, game = self._loader_and_game(version_id)
        self._log(f"搜索 {query}（{game} / {loader}）…")
        self._search_worker(query, loader, game)

    def _loader_and_game(self, version_id: str) -> tuple[str, str]:
        resolved = resolve(self.cfg.root(), version_id)
        loader = detect_loader(version_id, resolved.data)
        game = resolved.chain[0] if resolved.chain else version_id
        return loader, game

    def _install_selected(self) -> None:
        table = self.query_one("#results-table", DataTable)
        row = table.cursor_row
        if not (0 <= row < len(self.results)):
            self.app.notify("先搜一个模组并选中", severity="warning")
            return
        version_id = self.selected_version()
        if not version_id:
            return
        loader, game = self._loader_and_game(version_id)
        hit = self.results[row]
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.cancel_event = threading.Event()
        self.query_one("#m-cancel", Button).disabled = False
        self.query_one("#m-install", Button).disabled = True
        self._install_worker(version_id, hit.slug, loader, game)

    # ------------------------------------------------------------------
    def _log(self, message: str) -> None:
        self.log_view.write(message)

    def _log_threadsafe(self, message: str) -> None:
        ui_call(self, self._log, message)

    @work(thread=True, group="mod-search", exclusive=True)
    def _search_worker(self, query: str, loader: str, game: str) -> None:
        try:
            hits = modrinth.search(query, loader=loader, game_version=game, limit=12,
                                   source=self.cfg.download_source)
        except Exception as exc:  # noqa: BLE001
            self._log_threadsafe(f"[red]搜索失败：{exc}[/]")
            return
        self.results = hits
        ui_call(self, self._fill_results)
        self._log_threadsafe(f"找到 {len(hits)} 个结果")

    def _fill_results(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.display = True
        table.styles.height = 8
        table.clear()
        for hit in self.results:
            table.add_row(hit.title, hit.slug, f"{hit.downloads:,}")

    def _cancel_install(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
            self._log("正在取消 …")
            self.query_one("#m-cancel", Button).disabled = True

    def _finish_install_ui(self) -> None:
        self.query_one("#m-cancel", Button).disabled = True
        self.query_one("#m-install", Button).disabled = False
        self.cancel_event = None

    @work(thread=True, group="mod-install", exclusive=True)
    def _install_worker(self, version_id: str, slug: str, loader: str, game: str) -> None:
        source = self.cfg.download_source
        cancel = self.cancel_event
        try:
            project = modrinth.get_project(slug, source)
            version = modrinth.latest_version(project.get("id", slug), loader, game, source)
            if version is None:
                self._log_threadsafe(f"[red]{slug} 没有适配 {game} / {loader} 的版本[/]")
                return
            if cancel is not None and cancel.is_set():
                raise RuntimeError("已取消")
            path = modrinth.download_version(version, self.cfg.mods_dir(version_id), source,
                                             cancel=cancel)
            self._log_threadsafe(f"[green]已安装 {path.name}[/]")
            for dependency in modrinth.required_dependencies(version):
                if cancel is not None and cancel.is_set():
                    raise RuntimeError("已取消")
                if dependency.get("version_id"):
                    dep = modrinth.get_version(dependency["version_id"], source)
                else:
                    dep = modrinth.latest_version(dependency.get("project_id", ""), loader, game, source)
                if not dep:
                    continue
                dep_path = modrinth.download_version(dep, self.cfg.mods_dir(version_id), source,
                                                     cancel=cancel)
                self._log_threadsafe(f"前置：{dep_path.name}")
            ui_call(self, self.refresh_mods)
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if "已取消" in text or "取消" in text:
                self._log_threadsafe("[yellow]安装已取消[/]")
            else:
                self._log_threadsafe(f"[red]安装失败：{exc}[/]")
        finally:
            ui_call(self, self._finish_install_ui)
