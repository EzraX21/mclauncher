"""CurseForge API 客户端（需要申请 API key）。

key 从环境变量 CURSEFORGE_API_KEY 读，其次读配置里的 curseforge_api_key。
接口文档：https://docs.curseforge.com/rest-api/
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import __version__
from .net import DownloadTask, download

API = "https://api.curseforge.com/v1"
GAME_ID = 432          # Minecraft
CLASS_MOD = 6          # Mods
LOADER_IDS = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
USER_AGENT = f"mclauncher/{__version__}"


class CurseForgeError(RuntimeError):
    pass


@dataclass
class ModHit:
    mod_id: int
    slug: str
    title: str
    description: str
    downloads: int
    author: str


def api_key(config=None) -> Optional[str]:
    key = os.environ.get("CURSEFORGE_API_KEY")
    if key:
        return key.strip()
    if config is not None:
        stored = getattr(config, "curseforge_api_key", "") or ""
        return stored.strip() or None
    return None


def require_key(config=None) -> str:
    key = api_key(config)
    if not key:
        raise CurseForgeError(
            "没有 CurseForge API key：先申请，然后设置 CURSEFORGE_API_KEY，"
            "或 mclauncher config set curseforge_api_key <key>"
        )
    return key


def _get(path: str, key: str, params: Optional[dict] = None) -> object:
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    request = urllib.request.Request(url, headers={
        "x-api-key": key,
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise CurseForgeError("CurseForge 拒绝了请求：API key 无效或没有权限") from exc
        if exc.code == 429:
            raise CurseForgeError("CurseForge 限流了，等一会儿再试") from exc
        raise CurseForgeError(f"CurseForge 请求失败：HTTP {exc.code}") from exc
    except Exception as exc:  # noqa: BLE001
        raise CurseForgeError(f"CurseForge 请求失败：{exc}") from exc


def loader_id(loader: Optional[str]) -> Optional[int]:
    return LOADER_IDS.get((loader or "").lower())


def search(query: str, loader: Optional[str] = None, game_version: Optional[str] = None,
           limit: int = 10, key: Optional[str] = None, config=None) -> list[ModHit]:
    key = key or require_key(config)
    data = _get("/mods/search", key, {
        "gameId": GAME_ID,
        "classId": CLASS_MOD,
        "searchFilter": query,
        "gameVersion": game_version,
        "modLoaderType": loader_id(loader),
        "pageSize": limit,
    })
    hits = []
    for item in (data or {}).get("data", []):
        authors = ", ".join(author.get("name", "") for author in item.get("authors", []))
        hits.append(ModHit(
            mod_id=int(item["id"]),
            slug=str(item["id"]),
            title=item.get("name", ""),
            description=(item.get("summary") or "").strip(),
            downloads=int(item.get("downloadCount") or 0),
            author=authors,
        ))
    return hits


def files(mod_id: int, loader: Optional[str] = None, game_version: Optional[str] = None,
          key: Optional[str] = None, config=None) -> list[dict]:
    key = key or require_key(config)
    data = _get(f"/mods/{mod_id}/files", key, {
        "gameVersion": game_version,
        "modLoaderType": loader_id(loader),
    })
    return list((data or {}).get("data", []))


def latest_file(mod_id: int, loader: Optional[str] = None, game_version: Optional[str] = None,
                key: Optional[str] = None, config=None) -> Optional[dict]:
    items = files(mod_id, loader, game_version, key, config)
    return items[0] if items else None


def file_download_url(file: dict, key: str, config=None) -> Optional[str]:
    if file.get("downloadUrl"):
        return file["downloadUrl"]
    mod_id = file.get("modId")
    file_id = file.get("id")
    if not mod_id or not file_id:
        return None
    try:
        data = _get(f"/mods/{mod_id}/files/{file_id}/download-url", key)
    except CurseForgeError:
        return None
    url = (data or {}).get("data")
    return url if isinstance(url, str) and url else None


def required_dependency_ids(file: dict) -> list[int]:
    ids = []
    for dependency in file.get("dependencies") or []:
        if dependency.get("relationType") == 3 and dependency.get("modId"):
            ids.append(int(dependency["modId"]))
    return ids


def primary_file_name(file: dict) -> str:
    return file.get("fileName") or f"mod-{file.get('id', 'unknown')}.jar"


def download_file(file: dict, directory: Path, key: Optional[str] = None,
                  config=None, cancel=None) -> Path:
    key = key or require_key(config)
    url = file_download_url(file, key, config)
    if not url:
        raise CurseForgeError(
            f"{primary_file_name(file)} 没有第三方下载链接（作者可能在 CurseForge 设置里禁用了）"
        )
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / primary_file_name(file)
    download(DownloadTask(url, destination), cancel=cancel)
    return destination


def describe(file: dict) -> str:
    return f"{file.get('displayName') or primary_file_name(file)}  ({file.get('fileName', '')})"
