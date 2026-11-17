"""光影 / 材质包（资源包）的搜索、下载与本地管理。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from . import modrinth
from .config import Config
from .modrinth import ModrinthError, _get, primary_file

KINDS = {
    "shader": ("shader", "shaderpacks", "光影"),
    "resourcepack": ("resourcepack", "resourcepacks", "材质包"),
    # 数据包不在实例根目录，而在某个存档里，所以要多一个 world 参数
    "datapack": ("datapack", "datapacks", "数据包"),
}


class ResourceError(RuntimeError):
    pass


def _kind(kind: str) -> tuple[str, str, str]:
    if kind not in KINDS:
        raise ResourceError("类型只能是 shader（光影）、resourcepack（材质包）或 datapack（数据包）")
    return KINDS[kind]


def _world_name(world: Optional[str]) -> str:
    name = (world or "").strip()
    if not name:
        raise ResourceError("数据包装在存档里，先选一个存档")
    if name in (".", "..") or "/" in name or "\\" in name:
        raise ResourceError(f"存档名不合法：{world}")
    return name


def directory(kind: str, cfg: Config, version_id: str, world: Optional[str] = None) -> Path:
    _, folder, _ = _kind(kind)
    base = cfg.game_dir_for(version_id)
    if kind == "datapack":
        return base / "saves" / _world_name(world) / folder
    return base / folder


def worlds(cfg: Config, version_id: str) -> list[dict]:
    """实例里已有的存档（数据包要装进其中一个）。"""
    base = cfg.game_dir_for(version_id) / "saves"
    if not base.is_dir():
        return []
    items = []
    for path in sorted(base.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        packs = path / "datapacks"
        count = len([p for p in packs.iterdir() if not p.name.startswith(".")]) if packs.is_dir() else 0
        items.append({
            "name": path.name,
            "path": str(path),
            "has_level": (path / "level.dat").is_file(),
            "datapacks": count,
            "modified": path.stat().st_mtime,
        })
    items.sort(key=lambda item: item["modified"], reverse=True)
    return items


def game_version(cfg: Config, version_id: str) -> str:
    """实例版本号（可能是 fabric-loader-x-y）→ 真正的游戏版本。

    搜索/下载要对 Modrinth 报游戏版本，装文件要落到实例目录，两者不是一回事：
    以前都拿实例版本号当游戏版本，装在加载器实例上的光影会搜不到也装不上。
    """
    from .versions import VersionError, resolve

    try:
        resolved = resolve(cfg.root(), version_id)
    except VersionError:
        return version_id
    return resolved.chain[0] if resolved.chain else version_id


def search(kind: str, query: str, cfg: Config, version_id: str, limit: int = 20) -> list[dict]:
    project_type, _, _ = _kind(kind)
    game = game_version(cfg, version_id)
    facets = [[f"project_type:{project_type}"]]
    if game:
        facets.append([f"versions:{game}"])
    data = _get("/search", {
        "query": query,
        "facets": json.dumps(facets),
        "limit": limit,
        "index": "relevance",
    }, cfg.source)
    hits = []
    for hit in data.get("hits", []):
        hits.append({
            "slug": hit.get("slug", ""),
            "title": hit.get("title", ""),
            "description": hit.get("description", ""),
            "downloads": hit.get("downloads", 0),
            "author": hit.get("author", ""),
        })
    return hits


def latest(kind: str, project_id: str, game_version: str,
           source: str = "official") -> Optional[dict]:
    return modrinth.latest_version(project_id, None, game_version, source)


def install(kind: str, cfg: Config, version_id: str, project: str,
            world: Optional[str] = None) -> Path:
    game = game_version(cfg, version_id)
    target = directory(kind, cfg, version_id, world)  # 先校验 world，别下完了才发现没选存档
    version = latest(kind, project, game, cfg.source)
    if version is None:
        raise ResourceError(f"{project} 没有适配 {game} 的文件")
    return modrinth.download_version(version, target, cfg.source)


def local(kind: str, cfg: Config, version_id: str, world: Optional[str] = None) -> list[dict]:
    target = directory(kind, cfg, version_id, world)
    if not target.exists():
        return []
    items = []
    for path in sorted(target.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_file():
            items.append({"name": path.name, "size": path.stat().st_size, "dir": False})
        elif path.is_dir():
            items.append({"name": path.name, "size": 0, "dir": True})
    return items


def remove(kind: str, cfg: Config, version_id: str, name: str,
           world: Optional[str] = None) -> bool:
    target = directory(kind, cfg, version_id, world)
    path = target / name
    if path.parent != target or not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True
