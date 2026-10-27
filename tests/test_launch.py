"""启动参数构建的单元测试（不启动游戏）。"""

import os
import unittest
from pathlib import Path

from mclauncher.config import Config
from mclauncher.launch import LaunchCommand, build_arguments, build_command, offline_uuid
from mclauncher.versions import Resolved


class ArgumentTests(unittest.TestCase):
    def test_plain_strings_and_substitution(self):
        args = build_arguments(
            ["--username", "${auth_player_name}", "-Dfoo=${missing_but_known}"],
            {"auth_player_name": "Steve", "missing_but_known": "x"},
            {}, [],
        )
        self.assertEqual(args, ["--username", "Steve", "-Dfoo=x"])

    def test_rules_filter(self):
        entries = [
            "--always",
            {"rules": [{"action": "allow", "os": {"name": "windows"}}], "value": "--windows-only"},
            {"rules": [{"action": "allow", "os": {"name": "linux"}}], "value": ["--linux", "--linux2"]},
        ]
        args = build_arguments(entries, {}, {}, [])
        self.assertIn("--always", args)
        self.assertNotIn("--windows-only", args)
        if os.name != "nt":
            self.assertIn("--linux", args)
            self.assertIn("--linux2", args)

    def test_unknown_placeholder_warns(self):
        warnings = []
        build_arguments(["--x=${who_knows}"], {}, {}, warnings)
        self.assertTrue(any("who_knows" in message for message in warnings))


class CommandTests(unittest.TestCase):
    def build(self, tmp_path: Path, java=None) -> LaunchCommand:
        root = tmp_path / "mc"
        (root / "versions" / "demo").mkdir(parents=True)
        (root / "versions" / "demo" / "demo.jar").write_bytes(b"jar")
        resolved = Resolved(
            id="demo",
            directory=root / "versions" / "demo",
            data={
                "mainClass": "net.minecraft.client.main.Main",
                "type": "release",
                "arguments": {
                    "jvm": ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"],
                    "game": ["--username", "${auth_player_name}", "--version", "${version_name}"],
                },
            },
            client_jar=root / "versions" / "demo" / "demo.jar",
            jar_id="demo",
            libraries=[{"name": "com.example:lib:1.0", "downloads": {"artifact": {
                "path": "com/example/lib/1.0/lib-1.0.jar", "url": "https://example/lib.jar"}}}],
            main_class="net.minecraft.client.main.Main",
            java_major=17,
            assets_index="5",
            assets_dir=root / "assets",
        )
        cfg = Config(game_dir=str(root), username="Alex", memory_mb=1024, isolate_versions=False)
        return build_command(resolved, cfg, java=java)

    def test_warns_when_java_major_mismatch(self):
        import tempfile
        from pathlib import Path as P

        from mclauncher.java import JavaRuntime

        with tempfile.TemporaryDirectory() as directory:
            wrong = JavaRuntime(path=P("/java21"), major=21, version="21.0.1")
            command = self.build(Path(directory), java=wrong)
            self.assertTrue(any("要求 Java 17" in warning for warning in command.warnings))

    def test_offline_uuid_stable(self):
        first = offline_uuid("Alex")
        self.assertEqual(first, offline_uuid("Alex"))
        self.assertNotEqual(first, offline_uuid("Steve"))
        self.assertEqual(len(first), 36)

    def test_command_structure(self, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            command = self.build(Path(directory))
            self.assertEqual(command.argv[0], "java")
            self.assertIn("-Xmx1024M", command.argv)
            self.assertIn("-cp", command.argv)
            self.assertIn("net.minecraft.client.main.Main", command.argv)
            index = command.argv.index("--username")
            self.assertEqual(command.argv[index + 1], "Alex")
            classpath = command.argv[command.argv.index("-cp") + 1]
            self.assertIn(os.pathsep, classpath)
            self.assertIn("demo.jar", classpath)


class ConfigTests(unittest.TestCase):
    def test_roundtrip(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            cfg = Config(memory_mb=3072, username="Tester")
            cfg.save(path)
            loaded = Config.load(path)
            self.assertEqual(loaded.memory_mb, 3072)
            self.assertEqual(loaded.username, "Tester")
            self.assertIn("memory_mb", json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
