"""CurseForge 客户端的单元测试（全部 mock，不联网）。"""

import os
import unittest
from unittest import mock

from mclauncher import curseforge


class KeyTests(unittest.TestCase):
    def test_env_wins(self):
        with mock.patch.dict(os.environ, {"CURSEFORGE_API_KEY": " env-key "}, clear=False):
            self.assertEqual(curseforge.api_key(), "env-key")

    def test_config_fallback(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = mock.Mock(curseforge_api_key="cfg-key")
            self.assertEqual(curseforge.api_key(cfg), "cfg-key")
            self.assertIsNone(curseforge.api_key())

    def test_require_key_message(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(curseforge.CurseForgeError) as ctx:
                curseforge.require_key(None)
            self.assertIn("CURSEFORGE_API_KEY", str(ctx.exception))


class SearchTests(unittest.TestCase):
    def test_loader_ids(self):
        self.assertEqual(curseforge.loader_id("fabric"), 4)
        self.assertEqual(curseforge.loader_id("forge"), 1)
        self.assertEqual(curseforge.loader_id("neoforge"), 6)
        self.assertIsNone(curseforge.loader_id("vanilla"))

    def test_search_maps_hits(self):
        payload = {"data": [{
            "id": 238222, "name": "Just Enough Items", "summary": "View items",
            "downloadCount": 12345, "authors": [{"name": "mezz"}],
        }]}
        with mock.patch.object(curseforge, "_get", return_value=payload) as get:
            hits = curseforge.search("jei", loader="forge", game_version="1.20.1", key="k")
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual((hit.mod_id, hit.slug, hit.title), (238222, "238222", "Just Enough Items"))
        self.assertEqual(hit.author, "mezz")
        args, _kwargs = get.call_args
        self.assertEqual(args[0], "/mods/search")
        params = args[2]
        self.assertEqual(params["gameId"], 432)
        self.assertEqual(params["classId"], 6)
        self.assertEqual(params["modLoaderType"], 1)

    def test_latest_file(self):
        payload = {"data": [{"id": 9, "modId": 1, "fileName": "a.jar"}]}
        with mock.patch.object(curseforge, "_get", return_value=payload):
            file = curseforge.latest_file(1, "fabric", "1.20.1", key="k")
        self.assertEqual(file["fileName"], "a.jar")

    def test_dependencies_only_required(self):
        file = {"dependencies": [
            {"modId": 10, "relationType": 3},
            {"modId": 11, "relationType": 2},
            {"modId": 12, "relationType": 3},
            {},
        ]}
        self.assertEqual(curseforge.required_dependency_ids(file), [10, 12])

    def test_download_url_fallback(self):
        with mock.patch.object(curseforge, "_get", return_value={"data": "https://cdn/x.jar"}):
            url = curseforge.file_download_url({"modId": 1, "id": 2, "downloadUrl": None}, "k")
        self.assertEqual(url, "https://cdn/x.jar")

    def test_download_url_missing(self):
        with mock.patch.object(curseforge, "_get", side_effect=curseforge.CurseForgeError("no")):
            self.assertIsNone(curseforge.file_download_url({"modId": 1, "id": 2}, "k"))


if __name__ == "__main__":
    unittest.main()
