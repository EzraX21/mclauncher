"""离线皮肤：PNG 校验、资源包生成、options.txt。"""

import os
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from mcl import skin
from mcl.config import Config


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def make_png(width: int, height: int) -> bytes:
    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height))
    return (skin.PNG_SIGNATURE
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


class SkinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(Path(self.temp.name) / "config")
        self.game = Path(self.temp.name) / "game"
        self.cfg = Config(game_dir=str(self.game), custom_skin=True, skin_model="classic")

    def tearDown(self):
        self.temp.cleanup()
        if self.previous is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.previous

    def test_validate(self):
        self.assertEqual(skin.validate(make_png(64, 64)), (64, 64))
        self.assertEqual(skin.validate(make_png(64, 32)), (64, 32))
        with self.assertRaises(skin.SkinError):
            skin.validate(make_png(32, 32))
        with self.assertRaises(skin.SkinError):
            skin.validate(b"not a png")
        with self.assertRaises(skin.SkinError):
            skin.validate(make_png(64, 64) + b"x" * (24 * 1024))

    def test_pack_format(self):
        self.assertEqual(skin.pack_format("1.20.1"), 15)
        self.assertEqual(skin.pack_format("1.19.2"), 9)
        self.assertEqual(skin.pack_format("1.8.9"), 1)
        self.assertEqual(skin.pack_format("1.21.1"), 34)

    def test_apply_resource_pack(self):
        skin.save(make_png(64, 64), "classic")
        target = skin.apply(self.cfg, "1.20.1")
        self.assertIsNotNone(target)
        self.assertTrue(target.exists())
        with zipfile.ZipFile(target) as archive:
            names = set(archive.namelist())
        self.assertIn("assets/minecraft/textures/entity/steve.png", names)
        self.assertIn("assets/minecraft/textures/entity/player/wide/steve.png", names)
        game_dir = self.game / "versions" / "1.20.1"
        options = (game_dir / "options.txt").read_text(encoding="utf-8")
        self.assertIn("MCL-Custom-Skin.zip", options)
        self.assertIn("resourcePacks:", options)

    def test_loader_instance_gets_own_pack(self):
        skin.save(make_png(64, 64), "classic")
        target = skin.apply(self.cfg, "fabric-loader-0.20.1-26.3", "26.3")
        self.assertIsNotNone(target)
        self.assertIn("fabric-loader-0.20.1-26.3", str(target))
        self.assertNotIn("versions/26.3/resourcepacks", str(target))
        with zipfile.ZipFile(target) as archive:
            meta = archive.read("pack.mcmeta").decode("utf-8")
        self.assertIn('"pack_format": 46', meta)
        options = target.parent.parent / "options.txt"
        self.assertIn("MCL-Custom-Skin.zip", options.read_text(encoding="utf-8"))

    def test_disabled_does_not_apply(self):
        self.cfg.custom_skin = False
        self.assertIsNone(skin.apply(self.cfg, "1.20.1"))
        self.assertFalse((self.game / "versions" / "1.20.1" / "resourcepacks" / skin.PACK_NAME).exists())


if __name__ == "__main__":
    unittest.main()
