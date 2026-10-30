"""启动参数构建的单元测试（不启动游戏）。"""

import os
import unittest
from pathlib import Path

from mcl.config import Config
from mcl.launch import LaunchCommand, build_arguments, build_command, offline_uuid
from mcl.versions import Resolved


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
    def build(self, tmp_path: Path, java=None, account=None) -> LaunchCommand:
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
                    "game": ["--username", "${auth_player_name}", "--uuid", "${auth_uuid}",
                             "--accessToken", "${auth_access_token}", "--userType", "${user_type}",
                             "--version", "${version_name}"],
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
        return build_command(resolved, cfg, java=java, account=account)

    def test_warns_when_java_major_mismatch(self):
        import tempfile
        from pathlib import Path as P

        from mcl.java import JavaRuntime

        with tempfile.TemporaryDirectory() as directory:
            wrong = JavaRuntime(path=P("/java21"), major=21, version="21.0.1")
            command = self.build(Path(directory), java=wrong)
            self.assertTrue(any("要求 Java 17" in warning for warning in command.warnings))

    def test_online_account_arguments(self):
        import tempfile
        import time

        from mcl.auth import Account

        account = Account(name="Notch", uuid="069a79f4-44e9-4726-a5be-fca90e38aaf5",
                          access_token="mc-token", refresh_token="refresh",
                          expires_at=time.time() + 3600)
        with tempfile.TemporaryDirectory() as directory:
            command = self.build(Path(directory), account=account)
        self.assertIn("Notch", command.argv)
        self.assertIn("mc-token", command.argv)
        self.assertIn("msa", command.argv)
        self.assertIn("069a79f4-44e9-4726-a5be-fca90e38aaf5", command.argv)

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
            cfg = Config(memory_mb=3072, username="Tester",
                         download_source="custom", mirror_url="https://m.example.com")
            cfg.save(path)
            loaded = Config.load(path)
            self.assertEqual(loaded.memory_mb, 3072)
            self.assertEqual(loaded.username, "Tester")
            self.assertIn("memory_mb", json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(loaded.mirror_url, "https://m.example.com")

    def test_custom_source(self):
        cfg = Config(download_source="custom", mirror_url="https://mirror.example.com/")
        self.assertEqual(cfg.source, "custom:https://mirror.example.com")
        self.assertEqual(Config(download_source="custom").source, "official")


if __name__ == "__main__":
    unittest.main()
