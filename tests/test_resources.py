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
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(game_dir=str(Path(tmp) / "game"))
            with mock.patch("mcl.resources._get", return_value=hits) as get:
                result = resources.search("shader", "demo", cfg, "1.20.1")
        self.assertEqual(result[0]["slug"], "demo")
        params = get.call_args.args[1]
        facets = json.loads(params["facets"])
        self.assertIn(["project_type:shader"], facets)
        self.assertIn(["versions:1.20.1"], facets)

    def test_search_uses_game_version_for_loader_instance(self):
        """装在 Fabric 实例上的光影，要按 1.21.4 搜，不能拿 fabric-loader-… 去搜。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            for version_id, payload in (
                ("1.21.4", {"id": "1.21.4", "type": "release"}),
                ("fabric-loader-0.16.9-1.21.4", {"id": "fabric-loader-0.16.9-1.21.4",
                                                 "inheritsFrom": "1.21.4"}),
            ):
                directory = root / "versions" / version_id
                directory.mkdir(parents=True)
                (directory / f"{version_id}.json").write_text(json.dumps(payload), encoding="utf-8")
            cfg = Config(game_dir=str(root), isolate_versions=True)
            with mock.patch("mcl.resources._get", return_value={"hits": []}) as get:
                resources.search("shader", "complementary", cfg, "fabric-loader-0.16.9-1.21.4")
            facets = json.loads(get.call_args.args[1]["facets"])
            self.assertIn(["versions:1.21.4"], facets)
            self.assertNotIn(["versions:fabric-loader-0.16.9-1.21.4"], facets)

    def test_install_resolves_game_version_but_writes_to_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            for version_id, payload in (
                ("1.21.4", {"id": "1.21.4", "type": "release"}),
                ("fabric-loader-0.16.9-1.21.4", {"id": "fabric-loader-0.16.9-1.21.4",
                                                 "inheritsFrom": "1.21.4"}),
            ):
                directory = root / "versions" / version_id
                directory.mkdir(parents=True)
                (directory / f"{version_id}.json").write_text(json.dumps(payload), encoding="utf-8")
            cfg = Config(game_dir=str(root), isolate_versions=True)
            with mock.patch("mcl.resources.latest", return_value={"id": "v1"}) as latest_mock, \
                    mock.patch("mcl.resources.modrinth.download_version",
                               return_value=Path("/tmp/pack.zip")) as download_mock:
                resources.install("shader", cfg, "fabric-loader-0.16.9-1.21.4", "complementary")
            self.assertEqual(latest_mock.call_args.args[2], "1.21.4")
            target = download_mock.call_args.args[1]
            self.assertEqual(target, root / "versions" / "fabric-loader-0.16.9-1.21.4" / "shaderpacks")

    def test_bad_kind(self):
        with self.assertRaises(resources.ResourceError):
            resources.local("mod", Config(game_dir="/tmp"), "1.20.1")
