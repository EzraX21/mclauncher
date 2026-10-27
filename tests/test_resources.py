"""光影 / 材质包管理测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcl import resources
from mcl.config import Config


class ResourceTests(unittest.TestCase):
    def test_local_and_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            folder = root / "versions" / "1.20.1" / "shaderpacks"
            folder.mkdir(parents=True)
            (folder / "demo.zip").write_bytes(b"zip")
            (folder / "packdir").mkdir()
            cfg = Config(game_dir=str(root))
            items = resources.local("shader", cfg, "1.20.1")
            self.assertEqual([item["name"] for item in items], ["demo.zip", "packdir"])
            self.assertTrue(resources.remove("shader", cfg, "1.20.1", "demo.zip"))
            self.assertFalse((folder / "demo.zip").exists())
            self.assertFalse(resources.remove("shader", cfg, "1.20.1", "../x"))

    def test_search_facets(self):
        hits = {"hits": [{"slug": "demo", "title": "Demo", "description": "d",
                          "downloads": 1, "author": "a"}]}
        with mock.patch("mcl.resources._get", return_value=hits) as get:
            result = resources.search("shader", "demo", "1.20.1")
        self.assertEqual(result[0]["slug"], "demo")
        params = get.call_args.args[1]
        facets = json.loads(params["facets"])
        self.assertIn(["project_type:shader"], facets)
        self.assertIn(["versions:1.20.1"], facets)

    def test_bad_kind(self):
        with self.assertRaises(resources.ResourceError):
            resources.local("mod", Config(game_dir="/tmp"), "1.20.1")
