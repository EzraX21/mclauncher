"""GUI 后端 API 的测试（本地 HTTP，不联网）。"""

import json
import os
import tempfile
import unittest
import urllib.request
from pathlib import Path

from mcl.config import Config
from mcl.webui import serve


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
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

    def test_theme(self):
        data = post_json(self.url + "api/config", {"theme": "dark"})
        self.assertEqual(data["config"]["theme"], "dark")
        self.assertEqual(Config.load().theme, "dark")
        post_json(self.url + "api/config", {"theme": "system"})
        self.assertEqual(Config.load().theme, "system")

    def test_unknown_api(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            get_json(self.url + "api/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
