"""GUI 后端 API 的测试（本地 HTTP，不联网）。"""

import io
import json
import os
import tempfile
import time
import unittest
import urllib.request
import zipfile
from pathlib import Path

from mcl.config import Config
from mcl.webui import serve


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


if __name__ == "__main__":
    unittest.main()
