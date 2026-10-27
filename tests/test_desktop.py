"""桌面启动项测试（写入临时 XDG_DATA_HOME）。"""

import os
import tempfile
import unittest
from pathlib import Path

from mcl import desktop


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self.tmp.name

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.previous
        self.tmp.cleanup()

    def test_install_and_remove(self):
        entry, icon = desktop.install()
        self.assertTrue(entry.exists())
        self.assertTrue(icon.exists())
        text = entry.read_text(encoding="utf-8")
        self.assertIn(" gui", text)
        self.assertIn("Exec=", text)
        self.assertIn("Icon=mcl", text)
        self.assertIn("StartupWMClass=mcl", text)
        self.assertTrue(desktop.ensure() is False)  # 已存在不重复
        self.assertTrue(desktop.remove())
        self.assertFalse(entry.exists())

    def test_ensure_creates_once(self):
        self.assertTrue(desktop.ensure())
        self.assertTrue(desktop.desktop_path().exists())
        self.assertFalse(desktop.ensure())
