"""造一个演示用的游戏目录，给截图工具用。

不是测试夹具，是给 `tools/screenshots.mjs` 生成「看起来像真在用」的界面：
几个版本、几个模组、服务器列表、光影材质、存档。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 仓库根，才能 import mcl

from mcl import nbt, servers  # noqa: E402
from mcl.config import Config  # noqa: E402


def _version(root: Path, version_id: str, payload: dict, jar: bool = True) -> Path:
    directory = root / "versions" / version_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{version_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if jar:
        (directory / f"{version_id}.jar").write_bytes(b"jar" * 2048)
    return directory


def _vanilla(version_id: str, java: int = 21) -> dict:
    return {
        "id": version_id,
        "type": "release",
        "mainClass": "net.minecraft.client.main.Main",
        "javaVersion": {"majorVersion": java},
        "assets": "19",
        "assetIndex": {"id": "19"},
        "downloads": {"client": {"url": "https://example/client.jar", "sha1": "a", "size": 1}},
        "libraries": [],
        "arguments": {"jvm": ["-cp", "${classpath}"], "game": ["--username", "${auth_player_name}"]},
    }


def build(target: Path) -> Path:
    game = target / "game"
    game.mkdir(parents=True, exist_ok=True)

    # 两个原版 + 一个 Fabric 实例
    _version(game, "1.21.4", _vanilla("1.21.4"))
    _version(game, "1.20.1", _vanilla("1.20.1", java=17))
    fabric_dir = _version(game, "fabric-loader-0.16.9-1.21.4", {
        "id": "fabric-loader-0.16.9-1.21.4",
        "inheritsFrom": "1.21.4",
        "type": "release",
        "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
    }, jar=False)

    mods = fabric_dir / "mods"
    mods.mkdir(exist_ok=True)
    for name, size in (("sodium-fabric-0.6.9.jar", 1_800_000),
                       ("iris-1.8.8.jar", 2_400_000),
                       ("lithium-0.14.3.jar", 640_000),
                       ("modmenu-13.0.0.jar", 220_000),
                       ("xaeros_minimap-24.2.0.jar.disabled", 3_100_000)):
        (mods / name).write_bytes(b"mod" * (size // 3))
    (fabric_dir / "config").mkdir(exist_ok=True)
    (fabric_dir / "config" / "sodium-options.json").write_text("{\"quality\":\"high\"}", encoding="utf-8")
    (fabric_dir / "options.txt").write_text("fov:0.5\nrenderDistance:12\n", encoding="utf-8")
    (fabric_dir / "shaderpacks").mkdir(exist_ok=True)
    (fabric_dir / "shaderpacks" / "ComplementaryReimagined_r5.5.1.zip").write_bytes(b"zip" * 900_000)
    (fabric_dir / "resourcepacks").mkdir(exist_ok=True)
    (fabric_dir / "resourcepacks" / "Faithful_64x.zip").write_bytes(b"zip" * 1_200_000)
    world = fabric_dir / "saves" / "新世界"
    world.mkdir(parents=True, exist_ok=True)
    (world / "level.dat").write_bytes(b"level")

    # 服务器列表（走真实格式，截图时 ping 会显示延迟/人数）
    servers.add(Config(game_dir=str(game), isolate_versions=True), "fabric-loader-0.16.9-1.21.4",
                "Hypixel", "mc.hypixel.net")
    servers.add(Config(game_dir=str(game), isolate_versions=True), "fabric-loader-0.16.9-1.21.4",
                "Hypixel 大厅", "mc.hypixel.net:25566")
    servers.add(Config(game_dir=str(game), isolate_versions=True), "fabric-loader-0.16.9-1.21.4",
                "朋友的内网服", "127.0.0.1:25566")

    cfg = Config(game_dir=str(game), username="Steve", memory_mb=8192,
                 isolate_versions=True, theme="light",
                 last_version="fabric-loader-0.16.9-1.21.4")
    cfg.save(target / "config.json")
    return game


if __name__ == "__main__":
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else ".screenshots/fixture").resolve()
    build(destination)
    print(destination)
