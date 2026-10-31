"""离线自定义皮肤：校验 PNG，生成本地资源包并写入 options.txt。"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from .config import Config
from .platforms import config_dir

MAX_BYTES = 24 * 1024
PACK_NAME = "MCL-Custom-Skin.zip"
PACK_ENTRY = f"file/{PACK_NAME}"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class SkinError(RuntimeError):
    pass


def skin_path() -> Path:
    return config_dir() / "skin.png"


def load_skin() -> Optional[bytes]:
    path = skin_path()
    if not path.exists():
        return None
    return path.read_bytes()


def preview(cfg: Config) -> str:
    if not cfg.custom_skin:
        return ""
    data = load_skin()
    if data is None:
        return ""
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def validate(data: bytes) -> tuple[int, int]:
    if len(data) > MAX_BYTES:
        raise SkinError(f"皮肤文件不能超过 {MAX_BYTES // 1024} KB")
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise SkinError("不是有效的 PNG 文件")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if (width, height) not in ((64, 32), (64, 64)):
        raise SkinError(f"皮肤尺寸必须是 64×32 或 64×64，当前是 {width}×{height}")
    return width, height


def save(data: bytes, model: str = "classic") -> None:
    validate(data)
    model = model if model in ("classic", "slim") else "classic"
    path = skin_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=".skin-", suffix=".png", dir=str(path.parent))
    try:
        with os.fdopen(handle, "wb") as handle_file:
            handle_file.write(data)
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def clear() -> None:
    try:
        skin_path().unlink()
    except FileNotFoundError:
        pass


def pack_format(version_id: str) -> int:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version_id)
    if not match:
        return 15
    version = tuple(int(part or 0) for part in match.groups())
    thresholds = [
        ((1, 21, 4), 46), ((1, 21, 2), 42), ((1, 21, 0), 34),
        ((1, 20, 5), 32), ((1, 20, 3), 22), ((1, 20, 2), 18),
        ((1, 20, 0), 15), ((1, 19, 4), 13), ((1, 19, 3), 12),
        ((1, 19, 0), 9), ((1, 18, 0), 8), ((1, 17, 0), 7),
        ((1, 16, 2), 6), ((1, 16, 0), 5), ((1, 15, 0), 5),
        ((1, 13, 0), 4), ((1, 11, 0), 3), ((1, 9, 0), 2),
    ]
    for minimum, value in thresholds:
        if version >= minimum:
            return value
    return 1


def _resource_pack(version_id: str, data: bytes) -> bytes:
    meta = {
        "pack": {
            "pack_format": pack_format(version_id),
            "supported_formats": {"min_inclusive": 1, "max_inclusive": 999},
            "description": "MCL 自定义皮肤",
        }
    }
    textures = (
        "assets/minecraft/textures/entity/steve.png",
        "assets/minecraft/textures/entity/alex.png",
        "assets/minecraft/textures/entity/player/wide/steve.png",
        "assets/minecraft/textures/entity/player/wide/alex.png",
        "assets/minecraft/textures/entity/player/slim/steve.png",
        "assets/minecraft/textures/entity/player/slim/alex.png",
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pack.mcmeta", json.dumps(meta, ensure_ascii=False, indent=2))
        for name in textures:
            archive.writestr(name, data)
    return buffer.getvalue()


def _enable_options(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found = False
    output = []
    for line in lines:
        if line.startswith("resourcePacks:"):
            found = True
            raw = line.split(":", 1)[1].strip()
            try:
                packs = json.loads(raw)
                if not isinstance(packs, list):
                    packs = []
            except json.JSONDecodeError:
                packs = []
            if PACK_ENTRY not in packs:
                packs.append(PACK_ENTRY)
            line = "resourcePacks:" + json.dumps(packs, ensure_ascii=False, separators=(",", ":"))
        elif line.startswith("incompatibleResourcePacks:"):
            raw = line.split(":", 1)[1].strip()
            try:
                packs = json.loads(raw)
                if isinstance(packs, list):
                    packs = [item for item in packs if item != PACK_ENTRY]
                    line = ("incompatibleResourcePacks:"
                            + json.dumps(packs, ensure_ascii=False, separators=(",", ":")))
            except json.JSONDecodeError:
                pass
        output.append(line)
    if not found:
        output.append("resourcePacks:" + json.dumps(
            ["vanilla", PACK_ENTRY], ensure_ascii=False, separators=(",", ":")))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.replace(temp, path)


def apply(cfg: Config, version_id: str, format_id: Optional[str] = None) -> Optional[Path]:
    if not cfg.custom_skin:
        return None
    data = load_skin()
    if data is None:
        raise SkinError("没有找到自定义皮肤文件")
    validate(data)
    # 游戏实际工作目录是启动的那个版本（可能是 fabric-loader-...），
    # pack_format 要用它继承的原版版本号，不能拿 loader 版本号。
    game_dir = cfg.game_dir_for(version_id)
    pack_dir = game_dir / "resourcepacks"
    pack_dir.mkdir(parents=True, exist_ok=True)
    target = pack_dir / PACK_NAME
    target.write_bytes(_resource_pack(format_id or version_id, data))
    _enable_options(game_dir / "options.txt")
    return target
