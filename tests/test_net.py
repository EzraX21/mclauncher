"""代理检测的单元测试（不联网）。"""

import os
import threading
import unittest
from unittest import mock

from mclauncher.net import _proxied


class ProxyTests(unittest.TestCase):
    def test_no_proxy_env(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_proxied("https://piston-data.mojang.com/x"))

    def test_https_proxy(self):
        with mock.patch.dict(os.environ, {"https_proxy": "http://127.0.0.1:7890"}, clear=True):
            self.assertTrue(_proxied("https://piston-data.mojang.com/x"))

    def test_no_proxy_bypass(self):
        env = {"https_proxy": "http://127.0.0.1:7890", "no_proxy": "mojang.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(_proxied("https://piston-data.mojang.com/x"))
            self.assertTrue(_proxied("https://cdn.modrinth.com/x"))


if __name__ == "__main__":
    unittest.main()


class CancelTests(unittest.TestCase):
    def test_download_cancelled_before_start(self):
        import tempfile
        from pathlib import Path

        from mclauncher.net import Cancelled, DownloadTask, download

        event = threading.Event()
        event.set()
        with tempfile.TemporaryDirectory() as directory:
            task = DownloadTask("https://example.invalid/x.jar", Path(directory) / "x.jar")
            with self.assertRaises(Cancelled):
                download(task, cancel=event)

    def test_run_tasks_reports_cancelled_without_errors(self):
        import tempfile
        from pathlib import Path

        from mclauncher.net import DownloadTask, run_tasks

        event = threading.Event()
        event.set()
        with tempfile.TemporaryDirectory() as directory:
            tasks = [DownloadTask(f"https://example.invalid/{i}.jar", Path(directory) / f"{i}.jar")
                     for i in range(3)]
            result = run_tasks(tasks, jobs=2, cancel=event)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.downloaded_files, 0)
