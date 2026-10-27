"""崩溃日志分析测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from mcl import crash
from mcl.config import Config


class CrashTests(unittest.TestCase):
    def test_java_version(self):
        findings = crash.analyze("java.lang.UnsupportedClassVersionError: class file version 61.0")
        self.assertTrue(any("Java" in finding.title for finding in findings))

    def test_out_of_memory(self):
        findings = crash.analyze("java.lang.OutOfMemoryError: Java heap space")
        self.assertTrue(any("内存" in finding.title for finding in findings))

    def test_missing_dependency(self):
        text = ("Missing or unsupported mandatory dependencies:\\n"
                "\\tMod ID: 'fabric-api', Requested by: 'sodium'")
        findings = crash.analyze(text)
        self.assertTrue(any("前置" in finding.title for finding in findings))

    def test_analyze_version_reads_latest_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            version_dir = root / "versions" / "1.20.1"
            reports = version_dir / "crash-reports"
            reports.mkdir(parents=True)
            (reports / "crash-2026-01-01.txt").write_text(
                "java.lang.OutOfMemoryError: Java heap space", encoding="utf-8")
            cfg = Config(game_dir=str(root), last_version="1.20.1")
            result = crash.analyze_version(cfg, "1.20.1")
        self.assertTrue(result["path"].endswith("crash-2026-01-01.txt"))
        self.assertTrue(any("内存" in finding["title"] for finding in result["findings"]))

    def test_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(game_dir=str(Path(tmp) / "game"))
            result = crash.analyze_version(cfg)
        self.assertEqual(result["findings"], [])
        self.assertTrue(result["message"])
