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


class EnsureJavaTests(unittest.TestCase):
    def test_pick_exact(self):
        from mclauncher.java import pick_exact

        runtimes = [runtime(8), runtime(21), runtime(25)]
        self.assertEqual(pick_exact(runtimes, 8).major, 8)
        self.assertIsNone(pick_exact(runtimes, 17))

    def test_uses_exact_without_download(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from mclauncher.config import Config
        from mclauncher.java import ensure_java

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(game_dir=tmp)
            with mock.patch("mclauncher.java.find_all", return_value=[runtime(8), runtime(25)]), \
                    mock.patch("mclauncher.java.install_runtime") as install:
                result = ensure_java(cfg, 8)
        self.assertEqual(result.major, 8)
        install.assert_not_called()

    def test_downloads_matching_runtime_when_only_newer(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from mclauncher.config import Config
        from mclauncher.java import ensure_java

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(game_dir=tmp)
            new_java = runtime(8)
            with mock.patch("mclauncher.java.find_all", return_value=[runtime(25)]), \
                    mock.patch("mclauncher.java.install_runtime",
                               return_value=Path(tmp) / "jre-legacy" / "bin" / "java") as install, \
                    mock.patch("mclauncher.java.probe", return_value=new_java):
                result = ensure_java(cfg, 8)
        self.assertEqual(result.major, 8)
        self.assertEqual(install.call_args.args[0], "jre-legacy")

    def test_falls_back_with_warning_if_download_fails(self):
        import tempfile
        from unittest import mock

        from mclauncher.config import Config
        from mclauncher.java import ensure_java

        notes = []
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(game_dir=tmp)
            with mock.patch("mclauncher.java.find_all", return_value=[runtime(25)]), \
                    mock.patch("mclauncher.java.install_runtime", side_effect=RuntimeError("no net")):
                result = ensure_java(cfg, 8, note=notes.append)
        self.assertEqual(result.major, 25)
        self.assertTrue(any("不兼容" in note for note in notes))
