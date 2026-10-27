"""TUI 的无头启动测试（Textual run_test，不联网）。"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from textual.widgets import TabbedContent

from mcl.config import Config
from mcl.manifest import Manifest
from mcl.tui.app import MclauncherApp

FAKE_MANIFEST = {
    "latest": {"release": "1.20.1", "snapshot": "26.4-snapshot-5"},
    "versions": [
        {"id": "1.20.1", "type": "release", "releaseTime": "2023-06-12T00:00:00+00:00", "url": "u"},
        {"id": "1.19.4", "type": "release", "releaseTime": "2023-03-14T00:00:00+00:00", "url": "u"},
    ],
}


def make_version(root: Path):
    directory = root / "versions" / "1.20.1"
    directory.mkdir(parents=True)
    (directory / "1.20.1.json").write_text(json.dumps({
        "id": "1.20.1",
        "type": "release",
        "mainClass": "net.minecraft.client.main.Main",
        "javaVersion": {"majorVersion": 17},
        "assets": "5",
        "downloads": {"client": {"url": "https://example/client.jar", "sha1": "a", "size": 1}},
    }), encoding="utf-8")
    (directory / "1.20.1.jar").write_bytes(b"jar")


class TuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_boots_and_switches_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("MCL_CONFIG")
            os.environ["MCL_CONFIG"] = str(Path(tmp) / "config.json")
            try:
                root = Path(tmp) / "game"
                make_version(root)
                cfg = Config(game_dir=str(root), memory_mb=2048)
                app = MclauncherApp(cfg)
                with mock.patch.object(Manifest, "load",
                                       classmethod(lambda cls, source="official": Manifest(FAKE_MANIFEST))):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        self.assertEqual(app.query_one("#versions-table").row_count, 1)

                        tabs = app.query_one(TabbedContent)
                        tabs.active = "tab-install"
                        await pilot.pause()
                        self.assertEqual(app.query_one("#remote-table").row_count, 2)

                        tabs.active = "tab-mods"
                        await pilot.pause()
                        self.assertEqual(app.query_one("#m-version").value, "1.20.1")

                        tabs.active = "tab-settings"
                        await pilot.pause()
                        self.assertEqual(app.query_one("#s-memory").value, "2048")
                        await pilot.press("q")
            finally:
                if previous is None:
                    os.environ.pop("MCL_CONFIG", None)
                else:
                    os.environ["MCL_CONFIG"] = previous

    async def test_settings_save_is_written_to_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("MCL_CONFIG")
            config_file = Path(tmp) / "config.json"
            os.environ["MCL_CONFIG"] = str(config_file)
            try:
                cfg = Config(game_dir=str(Path(tmp) / "game"), memory_mb=1024)
                cfg.memory_mb = 8192
                cfg.save()
                self.assertTrue(config_file.exists())
                self.assertEqual(Config.load().memory_mb, 8192)
            finally:
                if previous is None:
                    os.environ.pop("MCL_CONFIG", None)
                else:
                    os.environ["MCL_CONFIG"] = previous


if __name__ == "__main__":
    unittest.main()


class LoaderDialogTests(unittest.IsolatedAsyncioTestCase):
    async def test_dialog_lists_versions_and_dismisses(self):
        from mcl import loaders
        from mcl.tui.panes.loader import LoaderScreen

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("MCL_CONFIG")
            os.environ["MCL_CONFIG"] = str(Path(tmp) / "config.json")
            try:
                cfg = Config(game_dir=str(Path(tmp) / "game"))
                app = MclauncherApp(cfg)
                versions = [loaders.LoaderVersion("47.2.0", True, True),
                            loaders.LoaderVersion("47.1.0", True, False)]
                with mock.patch.object(loaders, "list_versions", return_value=versions):
                    async with app.run_test(size=(120, 40)) as pilot:
                        screen = LoaderScreen("1.20.1")
                        app.push_screen(screen)
                        await pilot.pause()
                        select = screen.query_one("#l-version")
                        self.assertEqual(select.value, "47.2.0")
                        self.assertFalse(select.disabled)
                        await pilot.click("#l-install")
                        await pilot.pause()
                        self.assertNotIsInstance(app.screen, LoaderScreen)
            finally:
                if previous is None:
                    os.environ.pop("MCL_CONFIG", None)
                else:
                    os.environ["MCL_CONFIG"] = previous


class CancelButtonTests(unittest.IsolatedAsyncioTestCase):
    async def test_install_cancel_stops_worker(self):
        import time
        from types import SimpleNamespace

        from mcl.installer import InstallResult
        from mcl.tui.panes import install as install_pane

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("MCL_CONFIG")
            os.environ["MCL_CONFIG"] = str(Path(tmp) / "config.json")
            try:
                cfg = Config(game_dir=str(Path(tmp) / "game"))
                app = MclauncherApp(cfg)

                def fake_plan(*_args, **_kwargs):
                    return SimpleNamespace(
                        total_files=3, total_bytes=100, root=Path(tmp) / "game",
                        version_id="1.20.1", version_json={"type": "release", "releaseTime": ""},
                        version_tasks=[], asset_tasks=[], java_major=17,
                    )

                def fake_execute(_plan, **kwargs):
                    cancel = kwargs.get("cancel")
                    for _ in range(500):
                        if cancel is not None and cancel.is_set():
                            return InstallResult(cancelled=True)
                        time.sleep(0.01)
                    return InstallResult()

                with mock.patch.object(Manifest, "load",
                                       classmethod(lambda cls, source="official": Manifest(FAKE_MANIFEST))), \
                        mock.patch.object(install_pane, "build_plan", fake_plan), \
                        mock.patch.object(install_pane, "execute", fake_execute):
                    async with app.run_test(size=(120, 30)) as pilot:
                        app.query_one(TabbedContent).active = "tab-install"
                        await pilot.pause()
                        self.assertTrue(app.query_one("#i-cancel").disabled)
                        await pilot.click("#i-install")
                        await pilot.pause(0.2)
                        self.assertFalse(app.query_one("#i-cancel").disabled)
                        await pilot.click("#i-cancel")
                        await pilot.pause(0.4)
                        self.assertTrue(app.query_one("#i-cancel").disabled)
            finally:
                if previous is None:
                    os.environ.pop("MCL_CONFIG", None)
                else:
                    os.environ["MCL_CONFIG"] = previous


class CurseForgeKeyTests(unittest.IsolatedAsyncioTestCase):
    async def test_key_saved_from_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("MCL_CONFIG")
            os.environ["MCL_CONFIG"] = str(Path(tmp) / "config.json")
            try:
                cfg = Config(game_dir=str(Path(tmp) / "game"))
                app = MclauncherApp(cfg)
                with mock.patch.object(Manifest, "load",
                                       classmethod(lambda cls, source="official": Manifest(FAKE_MANIFEST))):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        app.query_one(TabbedContent).active = "tab-settings"
                        await pilot.pause()
                        app.query_one("#s-cf-key").value = "cf-test-key"
                        await pilot.click("#s-save")
                        await pilot.pause()
                        self.assertEqual(cfg.curseforge_api_key, "cf-test-key")
                        self.assertEqual(Config.load().curseforge_api_key, "cf-test-key")
                        await pilot.press("q")
            finally:
                if previous is None:
                    os.environ.pop("MCL_CONFIG", None)
                else:
                    os.environ["MCL_CONFIG"] = previous


class ModsPaneTests(unittest.IsolatedAsyncioTestCase):
    async def test_vanilla_version_warns_instead_of_silent_empty(self):
        from mcl.tui.panes.mods import ModsPane

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("MCL_CONFIG")
            os.environ["MCL_CONFIG"] = str(Path(tmp) / "config.json")
            try:
                root = Path(tmp) / "game"
                make_version(root)
                app = MclauncherApp(Config(game_dir=str(root), download_source="official"))
                with mock.patch.object(Manifest, "load",
                                       classmethod(lambda cls, source="official": Manifest(FAKE_MANIFEST))):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        app.query_one(TabbedContent).active = "tab-mods"
                        await pilot.pause()
                        pane = app.query_one(ModsPane)
                        app.query_one("#m-query").value = "sodium"
                        pane._search()
                        await pilot.pause(0.5)
                        self.assertTrue(pane.log_view.display)
                        self.assertEqual(pane.results, [])
                        await pilot.press("q")
            finally:
                if previous is None:
                    os.environ.pop("MCL_CONFIG", None)
                else:
                    os.environ["MCL_CONFIG"] = previous
