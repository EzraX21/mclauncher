"""版本级启动覆盖项的单元测试。"""

import os
import tempfile
import unittest
from pathlib import Path

from mcl import vsettings


class VersionSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.temp.name

    def tearDown(self):
        self.temp.cleanup()
        if self.previous is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.previous

    def test_roundtrip(self):
        vsettings.update("1.20.1", {
            "memory_mb": 8192, "width": 1280, "height": 720,
            "jvm_args": "-XX:+UseG1GC", "game_args": "--fullscreen",
        })
        options = vsettings.get("1.20.1")
        self.assertEqual(options["memory_mb"], 8192)
        self.assertEqual(options["width"], 1280)
        self.assertEqual(options["height"], 720)
        self.assertEqual(options["jvm_args"], "-XX:+UseG1GC")
        self.assertEqual(options["game_args"], "--fullscreen")
        self.assertEqual(vsettings.get("other")["memory_mb"], None)

    def test_validation(self):
        with self.assertRaises(ValueError):
            vsettings.update("1.20.1", {"memory_mb": 128})
        with self.assertRaises(ValueError):
            vsettings.update("1.20.1", {"width": "abc"})
        with self.assertRaises(ValueError):
            vsettings.update("../x", {"memory_mb": 2048})

    def test_clear_values(self):
        vsettings.update("1.20.1", {"memory_mb": 4096})
        vsettings.update("1.20.1", {"memory_mb": None, "width": None})
        options = vsettings.get("1.20.1")
        self.assertIsNone(options["memory_mb"])
        self.assertIsNone(options["width"])


if __name__ == "__main__":
    unittest.main()
