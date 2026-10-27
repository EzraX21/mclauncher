"""本地模组管理：列出、启用/禁用（改后缀）、删除。"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DISABLED_SUFFIX = ".disabled"


@dataclass
class LocalMod:
    path: Path
    enabled: bool
    size: int
    mod_id: Optional[str] = None
    title: Optional[str] = None
    version: Optional[str] = None

    @property
    def name(self) -> str:
        name = self.path.name
        if name.endswith(DISABLED_SUFFIX):
            name = name[: -len(DISABLED_SUFFIX)]
        return name


def read_metadata(path: Path) -> dict:
    """从 jar 里读 Fabric / Quilt / Forge 的元数据，拿 mod id、名字、版本。"""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "fabric.mod.json" in names:
                data = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                return {"id": data.get("id"), "title": data.get("name"), "version": data.get("version")}
            if "quilt.mod.json" in names:
                data = json.loads(archive.read("quilt.mod.json").decode("utf-8"))
                loader = data.get("quilt_loader") or {}
                meta = (loader.get("metadata") or {})
                return {"id": loader.get("id"), "title": meta.get("name"), "version": loader.get("version")}
            if "META-INF/mods.toml" in names:
                text = archive.read("META-INF/mods.toml").decode("utf-8", "replace")
                def grab(key):
                    match = re.search(rf'^\s*{key}\s*=\s*"([^"]*)"', text, re.MULTILINE)
                    return match.group(1) if match else None
                return {"id": grab("modId"), "title": grab("displayName"), "version": grab("version")}
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError):
        return {}
    return {}


def list_mods(mods_dir: Path) -> list[LocalMod]:
    if not mods_dir.exists():
        return []
    mods: list[LocalMod] = []
    for path in sorted(mods_dir.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        if not (path.name.endswith(".jar") or path.name.endswith(".jar" + DISABLED_SUFFIX)):
            continue
        meta = read_metadata(path)
        enabled = path.name.endswith(".jar")
        mods.append(LocalMod(
            path=path,
            enabled=enabled,
            size=path.stat().st_size,
            mod_id=meta.get("id"),
            title=meta.get("title"),
            version=meta.get("version"),
        ))
    return mods


def set_enabled(mod: LocalMod, enabled: bool) -> Path:
    name = mod.name
    if enabled and not mod.enabled:
        destination = mod.path.with_name(name)
    elif not enabled and mod.enabled:
        destination = mod.path.with_name(name + DISABLED_SUFFIX)
    else:
        return mod.path
    if destination.exists():
        raise FileExistsError(f"目标已存在：{destination}")
    mod.path.rename(destination)
    return destination


def remove(mod: LocalMod) -> None:
    mod.path.unlink(missing_ok=True)


def find(mods_dir: Path, query: str) -> list[LocalMod]:
    query = query.lower()
    return [mod for mod in list_mods(mods_dir) if query in mod.name.lower()]
