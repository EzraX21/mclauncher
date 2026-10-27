"""已装版本：扫描、inheritsFrom 合并、加载器识别。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

LOADER_NAMES = ("fabric", "quilt", "neoforge", "forge")


class VersionError(RuntimeError):
    pass


def maven_path(name: str) -> str:
    """'net.fabricmc:fabric-loader:0.16.9' -> 'net/fabricmc/fabric-loader/0.16.9/fabric-loader-0.16.9.jar'"""
    extension = "jar"
    if "@" in name:
        name, extension = name.rsplit("@", 1)
    parts = name.split(":")
    if len(parts) < 3:
        raise ValueError(f"不是合法的 Maven 坐标：{name}")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = f"-{parts[3]}" if len(parts) > 3 else ""
    return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}{classifier}.{extension}"


def maven_url(base: str, name: str) -> str:
    return base.rstrip("/") + "/" + maven_path(name)


def library_key(library: dict) -> str:
    parts = library.get("name", "").split(":")
    group = parts[0] if parts else ""
    artifact = parts[1] if len(parts) > 1 else library.get("name", "")
    classifier = parts[3] if len(parts) > 3 else ""
    return f"{group}:{artifact}:{classifier}"


def detect_loader(version_id: str, data: dict) -> str:
    main = (data.get("mainClass") or "").lower()
    lowered = version_id.lower()
    libraries = " ".join(str(lib.get("name", "")) for lib in data.get("libraries") or []).lower()
    if "fabric" in main or "fabric" in lowered:
        return "fabric"
    if "quilt" in main or "quilt" in lowered:
        return "quilt"
    # NeoForge 1.20.1 的版本 id 叫 1.20.1-forge-47.1.x，只能靠库名识别
    if "neoforge" in main or "neoforge" in lowered or "neoforged" in libraries:
        return "neoforge"
    if "forge" in main or "forge" in lowered:
        return "forge"
    return "vanilla"


@dataclass
class InstalledVersion:
    id: str
    directory: Path
    data: dict
    inherits: Optional[str] = None
    loader: str = "vanilla"
    java_major: Optional[int] = None
    has_jar: bool = False
    modified: float = 0.0

    @property
    def json_path(self) -> Path:
        return self.directory / f"{self.id}.json"

    @property
    def type(self) -> str:
        return self.data.get("type", "release")


@dataclass
class Resolved:
    id: str
    directory: Path
    data: dict
    client_jar: Path
    jar_id: str
    libraries: list[dict] = field(default_factory=list)
    main_class: str = ""
    java_major: Optional[int] = None
    assets_index: Optional[str] = None
    assets_dir: Path = Path("assets")
    version_type: str = "release"
    chain: list[str] = field(default_factory=list)

    @property
    def client_jar_exists(self) -> bool:
        return self.client_jar.exists()

    @property
    def log_config(self) -> Optional[dict]:
        return ((self.data.get("logging") or {}).get("client") or {}).get("file")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionError(f"读不了 {path}：{exc}") from exc


def load_version(root: Path, version_id: str) -> dict:
    path = root / "versions" / version_id / f"{version_id}.json"
    if not path.exists():
        raise VersionError(f"找不到版本 {version_id}（{path}）")
    data = _read_json(path)
    data.setdefault("id", version_id)
    return data


def _java_major_of(root: Path, data: dict, depth: int = 0) -> Optional[int]:
    java = (data.get("javaVersion") or {}).get("majorVersion")
    if java or depth > 5:
        return java
    parent = data.get("inheritsFrom")
    if not parent:
        return None
    try:
        return _java_major_of(root, load_version(root, parent), depth + 1)
    except VersionError:
        return None


def scan(root: Path) -> list[InstalledVersion]:
    base = root / "versions"
    versions: list[InstalledVersion] = []
    if not base.exists():
        return versions
    for directory in base.iterdir():
        if not directory.is_dir():
            continue
        json_path = directory / f"{directory.name}.json"
        if not json_path.exists():
            continue
        try:
            data = _read_json(json_path)
        except VersionError:
            continue
        java = _java_major_of(root, data)
        versions.append(InstalledVersion(
            id=directory.name,
            directory=directory,
            data=data,
            inherits=data.get("inheritsFrom"),
            loader=detect_loader(directory.name, data),
            java_major=java,
            has_jar=(directory / f"{directory.name}.jar").exists(),
            modified=json_path.stat().st_mtime,
        ))
    versions.sort(key=lambda version: version.modified, reverse=True)
    return versions


def _chain(root: Path, version_id: str, seen: Optional[set[str]] = None) -> list[tuple[str, dict]]:
    seen = seen or set()
    if version_id in seen:
        raise VersionError(f"inheritsFrom 出现循环：{version_id}")
    seen.add(version_id)
    data = load_version(root, version_id)
    parent = data.get("inheritsFrom")
    if parent:
        return _chain(root, parent, seen) + [(version_id, data)]
    return [(version_id, data)]


def resolve(root: Path, version_id: str) -> Resolved:
    chain = _chain(root, version_id)
    merged: dict = {}
    libraries: dict[str, dict] = {}
    order: list[str] = []
    jvm_args: list = []
    game_args: list = []

    for element_id, data in chain:
        for key in ("mainClass", "assets", "assetIndex", "downloads", "javaVersion",
                    "type", "logging", "minimumLauncherVersion", "minecraftArguments"):
            if key in data:
                merged[key] = data[key]
        for library in data.get("libraries") or []:
            key = library_key(library)
            if key not in libraries:
                order.append(key)
            libraries[key] = library
        arguments = data.get("arguments") or {}
        jvm_args.extend(arguments.get("jvm") or [])
        game_args.extend(arguments.get("game") or [])

    if jvm_args or game_args:
        merged["arguments"] = {"jvm": jvm_args, "game": game_args}
    merged["libraries"] = [libraries[key] for key in order]

    jar_id, client_jar = version_id, None
    for element_id, data in reversed(chain):
        client = (data.get("downloads") or {}).get("client")
        if client:
            jar_id = element_id
            client_jar = root / "versions" / element_id / f"{element_id}.jar"
            break
    if client_jar is None:
        client_jar = root / "versions" / version_id / f"{version_id}.jar"

    assets_index = (merged.get("assetIndex") or {}).get("id") or merged.get("assets")
    return Resolved(
        id=version_id,
        directory=root / "versions" / version_id,
        data=merged,
        client_jar=client_jar,
        jar_id=jar_id,
        libraries=merged["libraries"],
        main_class=merged.get("mainClass", ""),
        java_major=(merged.get("javaVersion") or {}).get("majorVersion"),
        assets_index=assets_index,
        assets_dir=root / "assets",
        version_type=merged.get("type", "release"),
        chain=[element_id for element_id, _ in chain],
    )


def version_size(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total
