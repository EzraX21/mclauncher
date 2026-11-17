"""doctor 的输出/退出码测试。"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mcl import doctor
from mcl.config import Config
from mcl.ui import UI


class DoctorTests(unittest.TestCase):
    def test_runs_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("MCL_CONFIG")
            os.environ["MCL_CONFIG"] = str(Path(tmp) / "config.json")
            try:
                cfg = Config(game_dir=str(Path(tmp) / "game"))
                output = io.StringIO()
                with contextlib.redirect_stdout(output), \
                        mock.patch("mcl.doctor.find_all", return_value=[]):
                    code = doctor.run(SimpleNamespace(network=False), UI(color=False), cfg)
                self.assertEqual(code, 0)
                text = output.getvalue()
                self.assertIn("mcl doctor", text)
                self.assertIn("Textual", text)
                self.assertIn(str(cfg.root()), text)
            finally:
                if previous is None:
                    os.environ.pop("MCL_CONFIG", None)
                else:
                    os.environ["MCL_CONFIG"] = previous

    def test_report_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("MCL_CONFIG")
            os.environ["MCL_CONFIG"] = str(Path(tmp) / "config.json")
            try:
                cfg = Config(game_dir=str(Path(tmp) / "game"))
                with mock.patch("mcl.doctor.find_all", return_value=[]):
                    data = doctor.report(cfg)
                labels = [check["label"] for check in data["checks"]]
                for expected in ("Python", "系统", "Textual", "配置文件", "游戏目录", "已装版本", "Java", "下载源"):
                    self.assertIn(expected, labels)
                for check in data["checks"]:
                    self.assertIn(check["status"], ("ok", "warn", "bad", "info"))
                    self.assertTrue(check["value"])
                self.assertEqual(data["java"], [])
                self.assertEqual(data["problems"], 0)  # 没 Java 只是警告
            finally:
                if previous is None:
                    os.environ.pop("MCL_CONFIG", None)
                else:
                    os.environ["MCL_CONFIG"] = previous

    def test_report_counts_missing_textual(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(game_dir=str(Path(tmp) / "game"))
            with mock.patch("mcl.doctor.find_all", return_value=[]), \
                    mock.patch.dict("sys.modules", {"textual": None}):
                data = doctor.report(cfg)
            textual = next(check for check in data["checks"] if check["label"] == "Textual")
            self.assertEqual(textual["status"], "bad")
            self.assertEqual(data["problems"], 1)

    def test_about(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(game_dir=str(Path(tmp) / "game"))
            data = doctor.about(cfg)
            self.assertEqual(data["version"], doctor.__version__)
            self.assertEqual(data["game_dir"], str(cfg.root()))
            self.assertEqual(data["license"], "GPL-3.0-or-later")
            self.assertTrue(data["repo"].startswith("https://github.com/"))



if __name__ == "__main__":
    unittest.main()
