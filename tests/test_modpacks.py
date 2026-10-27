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
