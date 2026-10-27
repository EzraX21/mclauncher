"""Modrinth 官方 API：搜索模组、取兼容版本、下载文件。"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from . import __version__, sources
from .manifest import fetch_json_any
from .net import DownloadTask, download

API = "https://api.modrinth.com/v2"
USER_AGENT = f"mcl/{__version__} (local launcher)"

LOADERS = ("fabric", "quilt", "forge", "neoforge")


class ModrinthError(RuntimeError):
    pass


@dataclass
class ModHit:
    project_id: str
    slug: str
    title: str
    description: str
    downloads: int
    author: str
    client_side: str
    versions: list[str]

    @property
    def client_ok(self) -> bool:
        return self.client_side != "unsupported"


def _get(path: str, params: Optional[dict] = None, source: str = "official") -> object:
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    try:
        return fetch_json_any(sources.modrinth_candidates(url, source))
    except Exception as exc:  # noqa: BLE001
        raise ModrinthError(f"Modrinth 请求失败：{exc}") from exc


def search(query: str, loader: Optional[str] = None, game_version: Optional[str] = None,
           limit: int = 10, source: str = "official") -> list[ModHit]:
    facets: list[list[str]] = [["project_type:mod"]]
    if loader:
        facets.append([f"categories:{loader}"])
    if game_version:
        facets.append([f"versions:{game_version}"])
    data = _get("/search", {
        "query": query,
        "limit": limit,
        "facets": json.dumps(facets, separators=(",", ":")),
        "index": "relevance",
    }, source)
    hits = []
    for item in data.get("hits", []):  # type: ignore[union-attr]
        hits.append(ModHit(
            project_id=item["project_id"],
            slug=item.get("slug", ""),
            title=item.get("title", ""),
            description=item.get("description", ""),
            downloads=item.get("downloads", 0),
            author=item.get("author", ""),
            client_side=item.get("client_side", "required"),
            versions=item.get("versions", []),
        ))
    return hits


def get_project(project_id: str, source: str = "official") -> dict:
    data = _get(f"/project/{project_id}", None, source)
    if not isinstance(data, dict):
        raise ModrinthError(f"找不到项目 {project_id}")
    return data


def get_version(version_id: str, source: str = "official") -> dict:
    data = _get(f"/version/{version_id}", None, source)
    if not isinstance(data, dict):
        raise ModrinthError(f"找不到版本 {version_id}")
    return data


def project_versions(project_id: str, loader: Optional[str] = None,
                     game_version: Optional[str] = None,
                     source: str = "official") -> list[dict]:
    params = {}
    if loader:
        params["loaders"] = json.dumps([loader])
    if game_version:
        params["game_versions"] = json.dumps([game_version])
    versions = _get(f"/project/{project_id}/version", params or None, source)
    if not isinstance(versions, list):
        raise ModrinthError(f"{project_id} 的版本列表格式异常")
    return versions


def latest_version(project_id: str, loader: Optional[str] = None,
                   game_version: Optional[str] = None,
                   source: str = "official") -> Optional[dict]:
    versions = project_versions(project_id, loader, game_version, source)
    return versions[0] if versions else None


def primary_file(version: dict) -> Optional[dict]:
    files = version.get("files") or []
    if not files:
        return None
    for item in files:
        if item.get("primary"):
            return item
    return files[0]


def required_dependencies(version: dict) -> list[dict]:
    return [dep for dep in version.get("dependencies", [])
            if dep.get("dependency_type") == "required" and dep.get("project_id")]


def download_version(version: dict, directory: Path, source: str = "official",
                     cancel=None) -> Path:
    file_info = primary_file(version)
    if not file_info:
        raise ModrinthError(f"{version.get('id', '?')} 没有可下载文件")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / file_info["filename"]
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    candidates = sources.modrinth_candidates(file_info["url"], source)
    task = DownloadTask(
        url=candidates[0],
        dest=destination,
        sha1=(file_info.get("hashes") or {}).get("sha1"),
        alternates=tuple(candidates[1:]),
    )
    download(task, cancel=cancel)
    return destination
