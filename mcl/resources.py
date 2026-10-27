"""光影 / 材质包（资源包）的搜索、下载与本地管理。"""

from __future__ import annotations

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


def search(kind: str, query: str, game_version: str, source: str = "official",
           limit: int = 20) -> list[dict]:
    project_type, _, _ = _kind(kind)
    facets = [[f"project_type:{project_type}"]]
    if game_version:
        facets.append([f"versions:{game_version}"])
    data = _get("/search", {
        "query": query,
        "facets": __import__("json").dumps(facets),
        "limit": limit,
        "index": "relevance",
    }, source)
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


def install(kind: str, game_version: str, project: str, cfg: Config,
            source: Optional[str] = None) -> Path:
    version = latest(kind, project, game_version, source or cfg.download_source)
    if version is None:
        raise ResourceError(f"{project} 没有适配 {game_version} 的文件")
    target = directory(kind, cfg, game_version)
    path = modrinth.download_version(version, target, source or cfg.download_source)
    return path


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
