"""下载计划生成的单元测试（用假元数据，不联网）。"""

import unittest
from pathlib import Path

from mcl.installer import build_plan

LINUX = {"name": "linux", "version": "6.1.0"}
SHA = "a" * 40
SHA2 = "b" * 40
SHA3 = "c" * 40

VERSION = {
    "id": "test-1",
    "type": "release",
    "releaseTime": "2026-01-01T00:00:00+00:00",
    "javaVersion": {"majorVersion": 21},
    "downloads": {"client": {"url": "https://example/client.jar", "sha1": SHA, "size": 100}},
    "libraries": [
        {"name": "common", "downloads": {"artifact": {
            "url": "https://example/common.jar", "path": "g/common/1/common-1.jar", "sha1": SHA2, "size": 10}}},
        {"name": "windows-only", "rules": [{"action": "allow", "os": {"name": "windows"}}],
         "downloads": {"artifact": {
             "url": "https://example/win.jar", "path": "g/win/1/win-1.jar", "sha1": SHA3, "size": 20}}},
    ],
    "logging": {"client": {"file": {"id": "client.xml", "url": "https://example/log.xml",
                                    "sha1": SHA, "size": 5}}},
    "assetIndex": {"id": "legacy", "url": "https://example/index.json", "sha1": SHA, "size": 1},
}

INDEX = {"virtual": True, "objects": {"sound/a.ogg": {"hash": SHA2, "size": 7}}}


def fake_loader(_url):
    return INDEX


class PlanTests(unittest.TestCase):
    def test_client_and_libraries(self):
        plan = build_plan(VERSION, Path("/tmp/mc"), with_assets=False, system=LINUX)
        urls = [task.url for task in plan.version_tasks]
        self.assertIn("https://example/client.jar", urls)
        self.assertIn("https://example/common.jar", urls)
        self.assertNotIn("https://example/win.jar", urls)  # windows 规则在 linux 上被过滤
        self.assertTrue(any(task.dest.name == "test-1.jar" for task in plan.version_tasks))

    def test_logging_config(self):
        plan = build_plan(VERSION, Path("/tmp/mc"), with_assets=False, system=LINUX)
        destinations = [task.dest for task in plan.version_tasks]
        self.assertIn(Path("/tmp/mc/assets/log_configs/client.xml"), destinations)

    def test_assets_and_legacy_mapping(self):
        plan = build_plan(VERSION, Path("/tmp/mc"), with_assets=True, system=LINUX, index_loader=fake_loader)
        self.assertEqual(len(plan.asset_tasks), 1)
        task = plan.asset_tasks[0]
        self.assertEqual(task.url, f"https://resources.download.minecraft.net/{SHA2[:2]}/{SHA2}")
        self.assertEqual(task.dest, Path("/tmp/mc/assets/objects") / SHA2[:2] / SHA2)
        self.assertEqual(plan.asset_index_id, "legacy")
        self.assertEqual(plan.legacy_mapping, [("sound/a.ogg", task.dest)])

    def test_totals(self):
        plan = build_plan(VERSION, Path("/tmp/mc"), with_assets=True, system=LINUX, index_loader=fake_loader)
        self.assertEqual(plan.version_bytes, 100 + 10 + 5)
        self.assertEqual(plan.asset_bytes, 7)
        self.assertEqual(plan.total_bytes, 122)
        self.assertEqual(plan.java_major, 21)


if __name__ == "__main__":
    unittest.main()
