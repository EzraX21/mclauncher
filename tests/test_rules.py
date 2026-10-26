"""规则匹配与平台选择的单元测试（不需要网络）。"""

import unittest

from mclauncher.rules import dedupe, is_allowed, rule_matches
from mclauncher.net import DownloadTask
from pathlib import Path


LINUX = {"name": "linux", "version": "6.1.0"}
WINDOWS = {"name": "windows", "version": "10"}
MACOS = {"name": "osx", "version": "14.0"}


class RuleTests(unittest.TestCase):
    def test_no_rules_means_allowed(self):
        self.assertTrue(is_allowed({"name": "x"}, {}, LINUX))

    def test_os_rule(self):
        lib = {"name": "x", "rules": [{"action": "allow", "os": {"name": "windows"}}]}
        self.assertTrue(is_allowed(lib, {}, WINDOWS))
        self.assertFalse(is_allowed(lib, {}, LINUX))

    def test_disallow_wins_when_matched_later(self):
        lib = {"rules": [
            {"action": "allow"},
            {"action": "disallow", "os": {"name": "osx"}},
        ]}
        self.assertTrue(is_allowed(lib, {}, LINUX))
        self.assertFalse(is_allowed(lib, {}, MACOS))

    def test_features_default_false(self):
        lib = {"rules": [{"action": "allow", "features": {"is_demo_user": True}}]}
        self.assertFalse(is_allowed(lib, {}, LINUX))
        self.assertTrue(is_allowed(lib, {"is_demo_user": True}, LINUX))

    def test_version_regex(self):
        rule = {"action": "allow", "os": {"name": "linux", "version": "^6\\."}}
        self.assertTrue(rule_matches(rule, {}, LINUX))
        self.assertFalse(rule_matches(rule, {}, {"name": "linux", "version": "5.15"}))

    def test_dedupe_keeps_first(self):
        root = Path("/tmp/x")
        tasks = [
            DownloadTask("https://a/1.jar", root / "libraries/a.jar"),
            DownloadTask("https://b/1.jar", root / "libraries/a.jar"),
            DownloadTask("https://c/2.jar", root / "libraries/b.jar"),
        ]
        unique = dedupe(tasks)
        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0].url, "https://a/1.jar")


if __name__ == "__main__":
    unittest.main()
