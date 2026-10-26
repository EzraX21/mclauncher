"""加载器列表 / 版本映射 / 安装器 URL 的单元测试（不联网）。"""

import json
import unittest
from unittest import mock

from mclauncher import loaders


class LoaderVersionTests(unittest.TestCase):
    def test_neoforge_prefix(self):
        self.assertEqual(loaders.neoforge_prefix("1.21.1"), "21.1.")
        self.assertEqual(loaders.neoforge_prefix("1.21"), "21.0.")
        self.assertEqual(loaders.neoforge_prefix("1.20.4"), "20.4.")
        self.assertEqual(loaders.neoforge_prefix("26.3"), "26.3.")
        self.assertEqual(loaders.neoforge_prefix("26.3.1"), "26.3.")

    def test_installer_urls_official_only(self):
        urls = loaders.installer_urls("forge", "1.20.1", "47.2.0", "official")
        self.assertEqual(urls, [
            "https://maven.minecraftforge.net/net/minecraftforge/forge/"
            "1.20.1-47.2.0/forge-1.20.1-47.2.0-installer.jar"
        ])

    def test_installer_urls_mirror_first(self):
        urls = loaders.installer_urls("forge", "1.20.1", "47.2.0", "auto")
        self.assertIn("bmclapi2.bangbang93.com/maven/", urls[0])
        self.assertTrue(urls[-1].startswith("https://maven.minecraftforge.net"))

        neo = loaders.installer_urls("neoforge", "1.21.1", "21.1.77", "auto")
        self.assertTrue(neo[0].startswith("https://bmclapi2.bangbang93.com/maven/"))
        self.assertIn("neoforge-21.1.77-installer.jar", neo[0])

    def test_forge_list_from_mirror(self):
        builds = [{"version": "47.2.0"}, {"version": "47.1.0"}]
        promos = {"promos": {"1.20.1-recommended": "47.2.0"}}
        with mock.patch.object(loaders, "fetch_json", return_value=builds), \
                mock.patch.object(loaders, "fetch_text", return_value=json.dumps(promos)):
            versions = loaders.list_versions("forge", "1.20.1", "auto", refresh=True)
        self.assertEqual([item.version for item in versions], ["47.2.0", "47.1.0"])
        self.assertTrue(versions[0].recommended)
        self.assertFalse(versions[1].recommended)
        self.assertTrue(all(item.stable for item in versions))

    def test_forge_official_xml_fallback(self):
        xml = ("<metadata><versioning><versions>"
               "<version>1.20.1-47.2.0</version>"
               "<version>1.20.1-47.1.0</version>"
               "<version>1.19.2-43.2.0</version>"
               "</versions></versioning></metadata>")
        promos = {"promos": {"1.20.1-latest": "47.2.0"}}
        with mock.patch.object(loaders, "fetch_json", side_effect=RuntimeError("no mirror")), \
                mock.patch.object(loaders, "fetch_text", side_effect=[xml, json.dumps(promos)]):
            versions = loaders.list_versions("forge", "1.20.1", "auto", refresh=True)
        self.assertEqual([item.version for item in versions], ["47.2.0", "47.1.0"])
        self.assertTrue(versions[0].recommended)

    def test_neoforge_filtering(self):
        payload = {"versions": ["21.1.10", "21.1.9-beta", "21.0.1", "20.4.237"]}
        with mock.patch.object(loaders, "fetch_json", return_value=payload):
            versions = loaders.list_versions("neoforge", "1.21.1", "official", refresh=True)
        self.assertEqual([item.version for item in versions], ["21.1.10", "21.1.9-beta"])
        self.assertFalse(versions[1].stable)
        self.assertEqual(versions[0].label, "21.1.10")

    def test_neoforge_new_scheme(self):
        payload = {"versions": ["26.3.0.99", "26.3.0.98", "26.2.1.1"]}
        with mock.patch.object(loaders, "fetch_json", return_value=payload):
            versions = loaders.list_versions("neoforge", "26.3", "official", refresh=True)
        self.assertEqual([item.version for item in versions], ["26.3.0.99", "26.3.0.98"])

    def test_neoforge_legacy_1201(self):
        payload = {"versions": ["1.20.1-47.1.106", "1.20.1-47.1.105", "1.20.2-20.2.1"]}
        with mock.patch.object(loaders, "fetch_json", return_value=payload):
            versions = loaders.list_versions("neoforge", "1.20.1", "official", refresh=True)
        self.assertEqual([item.version for item in versions], ["47.1.106", "47.1.105"])
        self.assertTrue(loaders.neoforge_is_legacy("1.20.1"))
        self.assertFalse(loaders.neoforge_is_legacy("1.20.2"))
        self.assertFalse(loaders.neoforge_is_legacy("26.3"))

    def test_neoforge_legacy_installer_url(self):
        url = loaders.installer_urls("neoforge", "1.20.1", "47.1.106", "official")[0]
        self.assertEqual(
            url,
            "https://maven.neoforged.net/releases/net/neoforged/forge/"
            "1.20.1-47.1.106/forge-1.20.1-47.1.106-installer.jar",
        )

    def test_labels(self):
        self.assertEqual(loaders.LoaderVersion("47.2.0", True, True).label, "47.2.0  ★推荐")
        self.assertEqual(loaders.LoaderVersion("47.2.0", False).label, "47.2.0 (beta)")


if __name__ == "__main__":
    unittest.main()
