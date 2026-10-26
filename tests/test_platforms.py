"""跨平台路径的单元测试（不依赖真实系统）。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mclauncher import platforms


class PlatformTests(unittest.TestCase):
    def test_windows_config_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.dict(os.environ, {"APPDATA": tmp, "LOCALAPPDATA": tmp}):
                self.assertEqual(platforms.config_dir(), Path(tmp) / "mclauncher")
                self.assertEqual(platforms.cache_dir(), Path(tmp) / "mclauncher" / "cache")

    def test_linux_xdg(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sys, "platform", "linux"), \
                    mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp, "XDG_CACHE_HOME": tmp}):
                self.assertEqual(platforms.config_dir(), Path(tmp) / "mclauncher")
                self.assertEqual(platforms.cache_dir(), Path(tmp) / "mclauncher")

    def test_macos(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sys, "platform", "darwin"), \
                    mock.patch("pathlib.Path.home", return_value=Path(tmp)):
                self.assertEqual(platforms.config_dir(),
                                 Path(tmp) / "Library" / "Application Support" / "mclauncher")

    def test_system_name(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(platforms.system(), "linux")
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(platforms.system(), "macos")
        with mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(platforms.system(), "windows")


if __name__ == "__main__":
    unittest.main()
