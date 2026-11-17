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
}


class ResourceError(RuntimeError):
    pass


def _kind(kind: str) -> tuple[str, str, str]:
    if kind not in KINDS:
        raise ResourceError("类型只能是 shader（光影）或 resourcepack（材质包）")
    return KINDS[kind]


def directory(kind: str, cfg: Config, version_id: str) -> Path:
    _, folder, _ = _kind(kind)
    return cfg.game_dir_for(version_id) / folder


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


def install(kind: str, cfg: Config, version_id: str, project: str) -> Path:
    game = game_version(cfg, version_id)
    version = latest(kind, project, game, cfg.source)
    if version is None:
        raise ResourceError(f"{project} 没有适配 {game} 的文件")
    target = directory(kind, cfg, version_id)
    return modrinth.download_version(version, target, cfg.source)


def local(kind: str, cfg: Config, version_id: str) -> list[dict]:
    target = directory(kind, cfg, version_id)
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


def remove(kind: str, cfg: Config, version_id: str, name: str) -> bool:
    target = directory(kind, cfg, version_id)
    path = target / name
    if path.parent != target or not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True
