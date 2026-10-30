"""版本扫描 / 合并 / 路径推导的单元测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from mcl.versions import (VersionError, detect_loader, library_key, maven_path,
                                   remove, resolve, scan)


def write_version(root: Path, version_id: str, payload: dict, jar: bool = False):
    directory = root / "versions" / version_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{version_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    if jar:
        (directory / f"{version_id}.jar").write_bytes(b"jar")


BASE = {
    "id": "1.20.1",
    "type": "release",
    "mainClass": "net.minecraft.client.main.Main",
    "javaVersion": {"majorVersion": 17},
    "assets": "5",
    "assetIndex": {"id": "5"},
    "downloads": {"client": {"url": "https://example/client.jar", "sha1": "a", "size": 1}},
    "libraries": [{"name": "com.example:base:1.0", "downloads": {"artifact": {
        "path": "com/example/base/1.0/base-1.0.jar", "url": "https://example/base.jar"}}}],
    "arguments": {"jvm": ["-cp", "${classpath}"], "game": ["--version", "${version_name}"]},
}

FABRIC = {
    "id": "fabric-loader-0.16.0-1.20.1",
    "inheritsFrom": "1.20.1",
    "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
    "libraries": [{"name": "net.fabricmc:fabric-loader:0.16.0", "url": "https://maven.fabricmc.net/"}],
    "arguments": {"jvm": ["-DFabricMcEmu=net.minecraft.client.main.Main"], "game": []},
}


class VersionTests(unittest.TestCase):
    def test_maven_path(self):
        self.assertEqual(
            maven_path("net.fabricmc:fabric-loader:0.16.0"),
            "net/fabricmc/fabric-loader/0.16.0/fabric-loader-0.16.0.jar",
        )
        self.assertEqual(
            maven_path("org.lwjgl:lwjgl:3.3.1:natives-linux"),
            "org/lwjgl/lwjgl/3.3.1/lwjgl-3.3.1-natives-linux.jar",
        )

    def test_library_key_keeps_classifier(self):
        self.assertEqual(library_key({"name": "org.lwjgl:lwjgl:3.3.1"}), "org.lwjgl:lwjgl:")
        self.assertEqual(library_key({"name": "org.lwjgl:lwjgl:3.3.1:natives-linux"}),
                         "org.lwjgl:lwjgl:natives-linux")

    def test_detect_loader(self):
        self.assertEqual(detect_loader("1.20.1", BASE), "vanilla")
        self.assertEqual(detect_loader("fabric-loader-0.16.0-1.20.1", FABRIC), "fabric")
        self.assertEqual(detect_loader("quilt-loader-0.2-1.20.1", {}), "quilt")
        self.assertEqual(detect_loader("1.20.1-forge-47.2.0", {}), "forge")
        self.assertEqual(detect_loader("1.20.1-neoforge-20.4.1", {}), "neoforge")

    def test_detect_loader_neoforge_legacy(self):
        data = {
            "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
            "libraries": [{"name": "net.neoforged.fancymodloader:loader:47.2.2"}],
        }
        self.assertEqual(detect_loader("1.20.1-forge-47.1.106", data), "neoforge")

    def test_resolve_inherits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_version(root, "1.20.1", BASE, jar=True)
            write_version(root, FABRIC["id"], FABRIC)
            resolved = resolve(root, FABRIC["id"])
            self.assertEqual(resolved.chain, ["1.20.1", FABRIC["id"]])
            self.assertEqual(resolved.main_class, FABRIC["mainClass"])
            self.assertEqual(resolved.java_major, 17)
            self.assertEqual(resolved.assets_index, "5")
            self.assertEqual(resolved.client_jar, root / "versions" / "1.20.1" / "1.20.1.jar")
            names = [library["name"] for library in resolved.libraries]
            self.assertIn("com.example:base:1.0", names)
            self.assertIn("net.fabricmc:fabric-loader:0.16.0", names)
            # 子版本的参数追加在父版本后面
            self.assertIn("-DFabricMcEmu=net.minecraft.client.main.Main", resolved.data["arguments"]["jvm"])
            self.assertIn("-cp", resolved.data["arguments"]["jvm"])

    def test_remove_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_version(root, "1.20.1", BASE, jar=True)
            write_version(root, "1.20.2", BASE, jar=True)
            remove(root, "1.20.1")
            self.assertFalse((root / "versions" / "1.20.1").exists())
            self.assertTrue((root / "versions" / "1.20.2").exists())
            with self.assertRaises(VersionError):
                remove(root, "1.20.1")
            with self.assertRaises(VersionError):
                remove(root, "../outside")

    def test_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_version(root, "1.20.1", BASE, jar=True)
            write_version(root, FABRIC["id"], FABRIC)
            (root / "versions" / "broken").mkdir()
            versions = {version.id: version for version in scan(root)}
            self.assertEqual(set(versions), {"1.20.1", FABRIC["id"]})
            self.assertEqual(versions[FABRIC["id"]].loader, "fabric")
            self.assertEqual(versions[FABRIC["id"]].java_major, 17)  # 从父版本继承
            self.assertTrue(versions["1.20.1"].has_jar)


if __name__ == "__main__":
    unittest.main()
