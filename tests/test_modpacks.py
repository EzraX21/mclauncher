"""整合包解析/安装测试（本地 zip，不联网）。"""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mcl import modpacks
from mcl.config import Config


def make_version(root: Path, version_id: str = "1.20.1") -> None:
    directory = root / "versions" / version_id
    directory.mkdir(parents=True)
    (directory / f"{version_id}.json").write_text(json.dumps({
        "id": version_id, "type": "release", "mainClass": "net.minecraft.client.main.Main",
        "javaVersion": {"majorVersion": 17},
        "downloads": {"client": {"url": "u", "sha1": "a", "size": 1}},
    }))


def make_mrpack(path: Path, files=None, overrides=None) -> None:
    index = {
        "formatVersion": 1, "game": "minecraft", "versionId": "1.0.0",
        "name": "Test Pack", "dependencies": {"minecraft": "1.20.1"},
        "files": files or [],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(index))
        for name, content in (overrides or {}).items():
            archive.writestr(f"overrides/{name}", content)


class ModpackTests(unittest.TestCase):
    def test_inspect_modrinth(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pack.mrpack"
            make_mrpack(path, files=[{
                "path": "mods/example.jar",
                "downloads": ["https://cdn.modrinth.com/data/x/example.jar"],
                "hashes": {"sha1": "abc"},
                "fileSize": 10,
            }, {
                "path": "mods/server-only.jar",
                "downloads": ["https://cdn.modrinth.com/data/y/server.jar"],
                "env": {"client": "unsupported"},
            }], overrides={"config/test.txt": "hello"})
            info = modpacks.inspect(path)
        self.assertEqual(info.format, "modrinth")
        self.assertEqual(info.name, "Test Pack")
        self.assertEqual(info.minecraft, "1.20.1")
        self.assertEqual(len(info.files), 1)
        self.assertEqual(info.files[0].sha1, "abc")
        self.assertEqual(info.overrides, ["config/test.txt"])

    def test_install_creates_instance_and_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            make_version(root)
            path = Path(tmp) / "pack.mrpack"
            make_mrpack(path, overrides={"config/test.txt": "hello"})
            cfg = Config(game_dir=str(root))
            version_id = modpacks.install(path, cfg)
            profile = json.loads((root / "versions" / version_id / f"{version_id}.json").read_text())
            self.assertEqual(profile["inheritsFrom"], "1.20.1")
            self.assertTrue((root / "versions" / version_id / "config" / "test.txt").exists())

    def test_curseforge_without_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            make_version(root)
            path = Path(tmp) / "pack.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", json.dumps({
                    "name": "CF Pack", "version": "1.0",
                    "minecraft": {"version": "1.20.1",
                                  "modLoaders": [{"id": "forge-47.2.0"}]},
                    "files": [{"projectID": 1, "fileID": 2, "required": True}],
                }))
            cfg = Config(game_dir=str(root))
            with self.assertRaises(modpacks.PackError) as ctx:
                modpacks.install(path, cfg)
        self.assertIn("CurseForge", str(ctx.exception))

    def test_bad_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.mrpack"
            path.write_bytes(b"not a zip")
            with self.assertRaises(modpacks.PackError):
                modpacks.inspect(path)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        self.cfg = Config(game_dir=str(self.root), isolate_versions=True)

    def tearDown(self):
        self.tmp.cleanup()

    def make_instance(self, version_id="1.20.1", payload=None) -> Path:
        directory = self.root / "versions" / version_id
        (directory / "mods").mkdir(parents=True)
        (directory / "config").mkdir()
        (directory / "saves" / "world").mkdir(parents=True)
        (directory / "logs").mkdir()
        (directory / f"{version_id}.json").write_text(json.dumps(payload or {
            "id": version_id, "type": "release",
            "mainClass": "net.minecraft.client.main.Main",
            "javaVersion": {"majorVersion": 17},
            "downloads": {"client": {"url": "u", "sha1": "a", "size": 1}},
        }), encoding="utf-8")
        (directory / f"{version_id}.jar").write_bytes(b"jar")
        (directory / "mods" / "sodium.jar").write_bytes(b"sodium")
        (directory / "mods" / "disabled.jar.disabled").write_bytes(b"off")
        (directory / "config" / "sodium.json").write_text("{}", encoding="utf-8")
        (directory / "options.txt").write_text("fov:0.5", encoding="utf-8")
        (directory / "saves" / "world" / "level.dat").write_bytes(b"level")
        (directory / "logs" / "latest.log").write_text("noise", encoding="utf-8")
        return directory

    def test_loader_version_of(self):
        self.assertEqual(modpacks.loader_version_of("fabric", ["fabric-loader-0.15.11-1.20.1"]), "0.15.11")
        self.assertEqual(modpacks.loader_version_of("quilt", ["quilt-loader-0.23.1-1.20.1"]), "0.23.1")
        self.assertEqual(modpacks.loader_version_of("forge", ["1.20.1-forge-47.2.0"]), "47.2.0")
        self.assertEqual(modpacks.loader_version_of("neoforge", ["neoforge-21.1.0"]), "21.1.0")
        self.assertEqual(modpacks.loader_version_of("vanilla", ["1.20.1"]), "")

    def test_export_writes_index_and_overrides(self):
        self.make_instance()
        result = modpacks.export(self.cfg, "1.20.1")
        self.assertTrue(Path(result["path"]).exists())
        with zipfile.ZipFile(result["path"]) as archive:
            names = set(archive.namelist())
            index = json.loads(archive.read("modrinth.index.json").decode("utf-8"))
        self.assertEqual(index["formatVersion"], 1)
        self.assertEqual(index["game"], "minecraft")
        self.assertEqual(index["dependencies"]["minecraft"], "1.20.1")
        self.assertEqual(index["files"], [])
        self.assertIn("overrides/mods/sodium.jar", names)
        self.assertIn("overrides/config/sodium.json", names)
        self.assertIn("overrides/options.txt", names)
        # 日志和存档默认不导出；版本 JSON / jar 也不该混进 overrides
        self.assertNotIn("overrides/logs/latest.log", names)
        self.assertFalse(any(name.startswith("overrides/saves/") for name in names))
        self.assertNotIn("overrides/1.20.1.json", names)
        self.assertNotIn("overrides/1.20.1.jar", names)

    def test_export_with_saves(self):
        self.make_instance()
        result = modpacks.export(self.cfg, "1.20.1", include_saves=True)
        with zipfile.ZipFile(result["path"]) as archive:
            names = set(archive.namelist())
        self.assertIn("overrides/saves/world/level.dat", names)

    def test_export_fabric_dependency(self):
        self.make_instance("fabric-loader-0.15.11-1.20.1", payload={
            "id": "fabric-loader-0.15.11-1.20.1",
            "inheritsFrom": "1.20.1",
            "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
        })
        make_version(self.root)
        result = modpacks.export(self.cfg, "fabric-loader-0.15.11-1.20.1")
        self.assertEqual(result["loader"], "fabric")
        self.assertEqual(result["loader_version"], "0.15.11")
        with zipfile.ZipFile(result["path"]) as archive:
            index = json.loads(archive.read("modrinth.index.json").decode("utf-8"))
        self.assertEqual(index["dependencies"]["fabric-loader"], "0.15.11")
        self.assertEqual(index["dependencies"]["minecraft"], "1.20.1")

    def test_export_unknown_version(self):
        with self.assertRaises(modpacks.PackError):
            modpacks.export(self.cfg, "没有这个版本")

    def test_export_roundtrip_through_install(self):
        """导出再用我们自己的导入装回去：模组和配置要还在（纯本地，不联网）。"""
        self.make_instance()
        result = modpacks.export(self.cfg, "1.20.1")

        other_root = Path(self.tmp.name) / "other"
        make_version(other_root)  # 原版已存在，安装时不用下载
        other = Config(game_dir=str(other_root), isolate_versions=True)
        instance = modpacks.install(Path(result["path"]), other, name="回环测试")
        target = other_root / "versions" / instance
        self.assertTrue((target / "mods" / "sodium.jar").exists())
        self.assertTrue((target / "config" / "sodium.json").exists())
        self.assertTrue((target / "options.txt").exists())
