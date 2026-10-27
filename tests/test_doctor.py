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


if __name__ == "__main__":
    unittest.main()
