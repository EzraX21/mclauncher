"""配置、路径（游戏目录 / 版本隔离 / 模组目录）。"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from .platforms import config_dir

APP_NAME = "mcl"
LEGACY_PATHS = [Path.home() / ".config" / "mclauncher" / "config.json"]


def config_path() -> Path:
    override = os.environ.get("MCL_CONFIG") or os.environ.get("MCLAUNCHER_CONFIG")
    if override:
        return Path(override).expanduser()
    return config_dir() / "config.json"


def _migrate(target: Path) -> None:
    if target.exists():
        return
    if os.name == "nt":
        return
    for legacy in LEGACY_PATHS:
        if legacy.exists() and legacy != target:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, target)
            return


def default_game_dir() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / ".minecraft"
    return Path.home() / ".minecraft"


@dataclass
class Config:
    game_dir: Optional[str] = None
    java_path: Optional[str] = None
    memory_mb: int = 4096
    username: str = "Player"
    isolate_versions: bool = True
    jobs: int = 8
    download_source: str = "official"
    mirror_url: str = ""
    theme: str = "light"
    ms_client_id: str = ""
    curseforge_api_key: str = ""
    last_version: Optional[str] = None
    width: int = 854
    height: int = 480

    # ------------------------------------------------------------ 读写
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        target = path or config_path()
        if path is None:
            _migrate(target)
        if not target.exists():
            return cls()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: Optional[Path] = None) -> Path:
        target = path or config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @property
    def source(self) -> str:
        """下载源标识：official / auto / custom:<URL>。"""
        mode = (self.download_source or "official").lower()
        if mode == "custom":
            base = (self.mirror_url or "").strip().rstrip("/")
            return f"custom:{base}" if base else "official"
        return mode if mode in ("official", "auto") else "official"

    # ------------------------------------------------------------ 路径
    def root(self) -> Path:
        return Path(self.game_dir).expanduser().resolve() if self.game_dir else default_game_dir()

    def version_dir(self, version_id: str) -> Path:
        return self.root() / "versions" / version_id

    def game_dir_for(self, version_id: str) -> Path:
        """版本隔离开：每个版本独立存档/配置；关：共用根目录。"""
        if self.isolate_versions:
            target = self.version_dir(version_id)
            target.mkdir(parents=True, exist_ok=True)
            return target
        target = self.root()
        target.mkdir(parents=True, exist_ok=True)
        return target

    def mods_path(self, version_id: str) -> Path:
        """只算路径，不创建目录（列表时用）。"""
        base = self.version_dir(version_id) if self.isolate_versions else self.root()
        return base / "mods"

    def mods_dir(self, version_id: str) -> Path:
        target = self.mods_path(version_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def java(self) -> Optional[Path]:
        return Path(self.java_path).expanduser() if self.java_path else None
