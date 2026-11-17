"""GUI 后端 API 的测试（本地 HTTP，不联网）。"""

import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from mcl.config import Config
from mcl.webui import serve
from tests.test_skin import make_png


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post_bytes(url: str, payload: bytes, headers: dict) -> dict:
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


class WebuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = os.environ.get("MCL_CONFIG")
        os.environ["MCL_CONFIG"] = str(Path(self.tmp.name) / "config.json")
        self.cfg = Config(game_dir=str(Path(self.tmp.name) / "game"), memory_mb=2048)
        self.httpd, self.url = serve(self.cfg, 0)

    def tearDown(self):
        self.httpd.shutdown()
        self.tmp.cleanup()
        if self.previous is None:
            os.environ.pop("MCL_CONFIG", None)
        else:
            os.environ["MCL_CONFIG"] = self.previous

    def test_login_disabled(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/login/start", {"client_id": "x"})
        self.assertEqual(ctx.exception.code, 403)

    def test_state(self):
        data = get_json(self.url + "api/state")
        self.assertIn("version", data)
        self.assertEqual(data["config"]["game_dir"], str(Path(self.tmp.name) / "game"))
        self.assertEqual(data["config"]["memory_mb"], 2048)
        self.assertEqual(data["versions"], [])

    def test_config_update(self):
        data = post_json(self.url + "api/config", {"memory_mb": 8192, "username": "Steve"})
        self.assertEqual(data["config"]["memory_mb"], 8192)
        self.assertEqual(data["config"]["username"], "Steve")
        self.assertEqual(Config.load().memory_mb, 8192)  # 写进的是临时配置

    def test_microsoft_client_id(self):
        data = post_json(self.url + "api/config", {"ms_client_id": " 7808d7d9-test "})
        self.assertEqual(data["config"]["ms_client_id"], "7808d7d9-test")

    def test_custom_download_source(self):
        data = post_json(self.url + "api/config", {
            "download_source": "custom",
            "mirror_url": "https://mirror.example.com/",
        })
        self.assertEqual(data["config"]["download_source"], "custom")
        self.assertEqual(data["config"]["mirror_url"], "https://mirror.example.com")

    def test_theme(self):
        data = post_json(self.url + "api/config", {"theme": "dark"})
        self.assertEqual(data["config"]["theme"], "dark")
        self.assertEqual(Config.load().theme, "dark")
        post_json(self.url + "api/config", {"theme": "system"})
        self.assertEqual(Config.load().theme, "system")

    def test_skin_upload_and_remove(self):
        data = post_bytes(self.url + "api/skin", make_png(64, 64), {
            "Content-Type": "image/png", "X-Skin-Model": "slim",
        })
        self.assertTrue(data["config"]["custom_skin"])
        self.assertEqual(data["config"]["skin_model"], "slim")
        self.assertTrue(data["config"]["skin_preview"].startswith("data:image/png;base64,"))
        data = post_json(self.url + "api/skin/remove", {})
        self.assertFalse(data["config"]["custom_skin"])
        self.assertEqual(data["config"]["skin_preview"], "")

    def test_version_options(self):
        data = post_json(self.url + "api/version/options", {
            "id": "1.20.1", "memory_mb": 8192, "width": 1280, "height": 720,
            "jvm_args": "-XX:+UseG1GC", "game_args": "--fullscreen",
        })
        self.assertEqual(data["options"]["memory_mb"], 8192)
        self.assertEqual(data["options"]["jvm_args"], "-XX:+UseG1GC")
        got = get_json(self.url + "api/version/options?id=1.20.1")
        self.assertEqual(got["options"]["width"], 1280)

    def test_remove_version(self):
        root = Path(self.tmp.name) / "game"
        version_dir = root / "versions" / "1.20.1"
        version_dir.mkdir(parents=True)
        (version_dir / "1.20.1.json").write_text(json.dumps({"id": "1.20.1"}), encoding="utf-8")
        data = post_json(self.url + "api/versions/remove", {"id": "1.20.1"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["versions"], [])
        self.assertFalse(version_dir.exists())

    def test_modpack_upload(self):
        root = Path(self.tmp.name) / "game"
        version_dir = root / "versions" / "1.20.1"
        version_dir.mkdir(parents=True)
        (version_dir / "1.20.1.json").write_text(json.dumps({
            "id": "1.20.1", "type": "release", "mainClass": "x",
            "javaVersion": {"majorVersion": 17},
            "downloads": {"client": {"url": "u", "sha1": "a", "size": 1}},
        }))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("modrinth.index.json", json.dumps({
                "formatVersion": 1, "game": "minecraft", "versionId": "1.0",
                "name": "Upload Test", "dependencies": {"minecraft": "1.20.1"},
                "files": [],
            }))
            archive.writestr("overrides/config/upload.txt", "hello")
        task = post_bytes(self.url + "api/modpack/install", buffer.getvalue(), {
            "Content-Type": "application/octet-stream",
            "X-Filename": "pack.mrpack",
            "X-Pack-Name": "UploadTest",
        })
        for _ in range(50):
            with urllib.request.urlopen(self.url + f"api/task/{task['id']}", timeout=10) as response:
                task = json.loads(response.read().decode("utf-8"))
            if task["state"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(task["state"], "done", task.get("error"))
        self.assertEqual(task["result"]["version"], "UploadTest")
        self.assertTrue((root / "versions" / "UploadTest" / "config" / "upload.txt").exists())

    def test_unknown_api(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            get_json(self.url + "api/nope")
        self.assertEqual(ctx.exception.code, 404)

    # ------------------------------------------------------------ 联机
    def make_version(self, version_id="1.20.1") -> Path:
        version_dir = Path(self.tmp.name) / "game" / "versions" / version_id
        version_dir.mkdir(parents=True)
        (version_dir / f"{version_id}.json").write_text(
            json.dumps({"id": version_id, "type": "release"}), encoding="utf-8")
        return version_dir

    def test_servers_empty_list(self):
        self.make_version()
        data = get_json(self.url + "api/servers")
        self.assertEqual(data["servers"], [])
        self.assertEqual(data["version"], "1.20.1")
        # 版本隔离开着：游戏读的就是 versions/<id>/servers.dat
        self.assertTrue(data["path"].endswith("/versions/1.20.1/servers.dat"))

    def test_servers_add_and_remove(self):
        self.make_version()
        data = post_json(self.url + "api/servers/add", {
            "version": "1.20.1", "name": "Hypixel", "ip": "mc.hypixel.net",
        })
        self.assertEqual(len(data["servers"]), 1)
        self.assertEqual(data["servers"][0]["host"], "mc.hypixel.net")
        self.assertEqual(data["servers"][0]["port"], 25565)
        data = post_json(self.url + "api/servers/remove", {"version": "1.20.1", "index": 0})
        self.assertEqual(data["servers"], [])

    def test_servers_add_rejects_bad_port(self):
        self.make_version()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/servers/add", {
                "version": "1.20.1", "name": "X", "ip": "example.com:99999",
            })
        self.assertEqual(ctx.exception.code, 400)

    def test_servers_join_unknown_index(self):
        self.make_version()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/servers/join", {"version": "1.20.1", "index": 3})
        self.assertEqual(ctx.exception.code, 404)

    def test_servers_needs_installed_version(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            get_json(self.url + "api/servers")
        self.assertEqual(ctx.exception.code, 404)

    # ------------------------------------------------------------ 版本管理
    def test_version_info(self):
        version_dir = self.make_version()
        (version_dir / "1.20.1.jar").write_bytes(b"jar")
        mods = version_dir / "mods"
        mods.mkdir()
        (mods / "sodium.jar").write_bytes(b"mod")
        data = get_json(self.url + "api/version/info?id=1.20.1")
        self.assertEqual(data["id"], "1.20.1")
        self.assertEqual(data["loader"], "vanilla")
        self.assertTrue(data["has_jar"])
        self.assertEqual(data["mods"], 1)
        self.assertGreater(data["size"], 0)
        self.assertEqual(data["path"], str(version_dir))

    def test_version_rename(self):
        self.make_version()
        data = post_json(self.url + "api/versions/rename", {"id": "1.20.1", "new_id": "原版 1.20.1"})
        self.assertTrue(data["ok"])
        self.assertEqual([item["id"] for item in data["versions"]], ["原版 1.20.1"])
        root = Path(self.tmp.name) / "game" / "versions"
        self.assertTrue((root / "原版 1.20.1" / "原版 1.20.1.json").exists())

    def test_version_rename_rejects_existing(self):
        self.make_version("1.20.1")
        self.make_version("1.19.4")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/versions/rename", {"id": "1.20.1", "new_id": "1.19.4"})
        self.assertEqual(ctx.exception.code, 400)

    def test_version_copy(self):
        self.make_version()
        data = post_json(self.url + "api/versions/copy", {"id": "1.20.1", "new_id": "副本"})
        self.assertTrue(data["ok"])
        self.assertEqual(sorted(item["id"] for item in data["versions"]), ["1.20.1", "副本"])

    def test_version_open(self):
        from unittest import mock

        self.make_version()
        with mock.patch("mcl.versions.subprocess.Popen") as popen:
            data = post_json(self.url + "api/versions/open", {"id": "1.20.1"})
        self.assertTrue(data["ok"])
        self.assertTrue(data["path"].endswith("versions/1.20.1"))
        self.assertTrue(popen.called)

    def test_version_open_missing(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/versions/open", {"id": "nope"})
        self.assertEqual(ctx.exception.code, 400)


    def test_modpack_export(self):
        version_dir = self.make_version()
        (version_dir / "mods").mkdir()
        (version_dir / "mods" / "sodium.jar").write_bytes(b"m")
        (version_dir / "options.txt").write_text("fov:0.5", encoding="utf-8")
        data = post_json(self.url + "api/modpack/export", {"version": "1.20.1"})
        self.assertTrue(Path(data["path"]).exists())
        self.assertTrue(data["path"].endswith(".mrpack"))
        self.assertEqual(data["game"], "1.20.1")
        self.assertGreaterEqual(data["files"], 2)
        with zipfile.ZipFile(data["path"]) as archive:
            names = set(archive.namelist())
        self.assertIn("modrinth.index.json", names)
        self.assertIn("overrides/mods/sodium.jar", names)

    def test_modpack_export_unknown_version(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/modpack/export", {"version": "nope"})
        self.assertEqual(ctx.exception.code, 500)

    def test_exports_open_rejects_outside_path(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/exports/open", {"path": "/etc/passwd"})
        self.assertEqual(ctx.exception.code, 400)

    # ------------------------------------------------------------ 百宝箱
    def test_about(self):
        data = get_json(self.url + "api/about")
        self.assertEqual(data["license"], "GPL-3.0-or-later")
        self.assertEqual(data["game_dir"], str(Path(self.tmp.name) / "game"))
        self.assertTrue(data["repo"].startswith("https://github.com/"))
        self.assertIn("version", data)

    def test_doctor_report(self):
        data = get_json(self.url + "api/doctor")
        labels = [check["label"] for check in data["checks"]]
        self.assertIn("游戏目录", labels)
        self.assertIn("Java", labels)
        for check in data["checks"]:
            self.assertIn(check["status"], ("ok", "warn", "bad", "info"))

    def test_open_dir_rejects_unknown(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/open-dir", {"which": "passwd"})
        self.assertEqual(ctx.exception.code, 400)

    def test_open_dir_config(self):
        from unittest import mock

        with mock.patch("mcl.versions.subprocess.Popen") as popen:
            data = post_json(self.url + "api/open-dir", {"which": "config"})
        self.assertTrue(data["ok"])
        self.assertTrue(popen.called)
        self.assertTrue(data["path"].endswith("/config.json") or Path(data["path"]).name != "")


    # ------------------------------------------------------------ Java
    def fake_java(self, major: int = 17) -> Path:
        path = Path(self.tmp.name) / f"java{major}"
        path.write_text(f'#!/bin/sh\necho \'openjdk version "{major}.0.9" 2023-10-17\' >&2\n',
                        encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_java_listing(self):
        data = get_json(self.url + "api/java")
        self.assertIn("runtimes", data)
        self.assertIn("components", data)
        self.assertIn(17, [item["major"] for item in data["components"]])
        self.assertEqual(data["configured"], "")

    def test_java_set_and_clear(self):
        path = self.fake_java(17)
        data = post_json(self.url + "api/java/set", {"path": str(path)})
        self.assertTrue(data["ok"])
        self.assertEqual(Config.load().java_path, str(path))
        self.assertEqual(data["config"]["java_path"], str(path))
        listed = [item for item in data["java"]["runtimes"] if item["configured"]]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["major"], 17)
        data = post_json(self.url + "api/java/clear", {})
        self.assertEqual(Config.load().java_path, "")

    def test_java_set_rejects_garbage(self):
        bogus = Path(self.tmp.name) / "not-java"
        bogus.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        bogus.chmod(0o755)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/java/set", {"path": str(bogus)})
        self.assertEqual(ctx.exception.code, 400)

    def test_java_install_rejects_unknown_major(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post_json(self.url + "api/java/install", {"major": 7})
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
