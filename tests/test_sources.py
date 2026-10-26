"""下载源候选列表的单元测试。"""

import unittest

from mclauncher import sources


class SourceTests(unittest.TestCase):
    def test_official_mode_has_no_mirror(self):
        self.assertEqual(sources.manifest_candidates("official"),
                         ["https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"])
        url = "https://piston-data.mojang.com/v1/objects/abc/client.jar"
        self.assertEqual(sources.meta_candidates(url, "official"), [url])

    def test_auto_prefers_mirror_then_official(self):
        candidates = sources.manifest_candidates("auto")
        self.assertIn("bmclapi2.bangbang93.com", candidates[0])
        self.assertTrue(candidates[-1].startswith("https://piston-meta.mojang.com"))

    def test_meta_rewrite_keeps_path(self):
        url = "https://piston-meta.mojang.com/v1/packages/abc/1.20.1.json"
        candidates = sources.meta_candidates(url, "auto")
        self.assertEqual(candidates[0], "https://bmclapi2.bangbang93.com/v1/packages/abc/1.20.1.json")
        self.assertEqual(candidates[1], url)

    def test_library_prefixes(self):
        url = "https://libraries.minecraft.net/com/google/guava/guava/31.1-jre/guava-31.1-jre.jar"
        candidates = sources.library_candidates(url, "auto")
        self.assertEqual(candidates[0],
                         "https://bmclapi2.bangbang93.com/maven/com/google/guava/guava/31.1-jre/guava-31.1-jre.jar")
        self.assertIn("https://bmclapi2.bangbang93.com/libraries/com/google/guava/guava/31.1-jre/guava-31.1-jre.jar",
                      candidates)
        self.assertIn(url, candidates)

    def test_asset_prefix(self):
        url = "https://resources.download.minecraft.net/0d/0d000710b71ca9aafabd8f587768431d0b560b32"
        self.assertEqual(sources.asset_candidates(url, "auto")[0],
                         "https://bmclapi2.bangbang93.com/assets/0d/0d000710b71ca9aafabd8f587768431d0b560b32")

    def test_modrinth_rewrite(self):
        api = sources.modrinth_candidates("https://api.modrinth.com/v2/search?query=a", "auto")
        self.assertEqual(api[0], "https://mod.mcimirror.top/modrinth/v2/search?query=a")
        cdn = sources.modrinth_candidates("https://cdn.modrinth.com/data/x/versions/y/a.jar", "auto")
        self.assertEqual(cdn[0], "https://mod.mcimirror.top/data/x/versions/y/a.jar")

    def test_fabric_meta_rewrite(self):
        url = "https://meta.fabricmc.net/v2/versions/loader/1.20.1"
        self.assertEqual(sources.fabric_meta_candidates(url, "auto")[0],
                         "https://bmclapi2.bangbang93.com/fabric-meta/v2/versions/loader/1.20.1")

    def test_unknown_hosts_untouched(self):
        url = "https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.16.9/fabric-loader-0.16.9.jar"
        self.assertEqual(sources.library_candidates(url, "auto"), [url])


if __name__ == "__main__":
    unittest.main()
