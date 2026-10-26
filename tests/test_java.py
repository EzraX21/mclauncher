"""Java 版本解析与选择的单元测试。"""

import unittest

from mclauncher.java import JavaRuntime, parse_version, pick


def runtime(major: int, version: str = "") -> JavaRuntime:
    return JavaRuntime(path=__import__("pathlib").Path(f"/java{major}"), major=major, version=version or f"{major}.0.1")


class JavaTests(unittest.TestCase):
    def test_parse_legacy(self):
        self.assertEqual(parse_version('java version "1.8.0_202"'), ("1.8.0_202", 8))
        self.assertEqual(parse_version('java version "1.7.0_80"'), ("1.7.0_80", 7))

    def test_parse_modern(self):
        self.assertEqual(parse_version('openjdk version "21.0.7" 2025-04-15'), ("21.0.7", 21))
        self.assertEqual(parse_version('openjdk version "25" 2025-09-16'), ("25", 25))
        self.assertIsNone(parse_version("nothing here"))

    def test_pick_exact(self):
        runtimes = [runtime(8), runtime(17), runtime(21)]
        self.assertEqual(pick(runtimes, 17).major, 17)

    def test_pick_lower_bound(self):
        runtimes = [runtime(8), runtime(21), runtime(25)]
        self.assertEqual(pick(runtimes, 17).major, 21)   # 最小的够用版本
        self.assertEqual(pick(runtimes, 99).major, 25)   # 都不够就给最高的

    def test_pick_empty(self):
        self.assertIsNone(pick([], 17))


if __name__ == "__main__":
    unittest.main()
