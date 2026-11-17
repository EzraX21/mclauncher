"""已装版本：扫描、inheritsFrom 合并、加载器识别。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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


def remove(root: Path, version_id: str) -> None:
    """删除已安装版本目录；只允许删除 versions/ 下的一级目录。"""
    if not version_id or version_id in (".", "..") or "/" in version_id or "\\" in version_id:
        raise VersionError(f"非法版本名：{version_id}")
    base = (Path(root) / "versions").resolve()
    target = (base / version_id).resolve()
    if target.parent != base:
        raise VersionError(f"非法版本路径：{version_id}")
    if not target.is_dir():
        raise VersionError(f"找不到版本 {version_id}")
    try:
        shutil.rmtree(target)
    except OSError as exc:
        raise VersionError(f"删除失败：{exc}") from exc


_BAD_NAME_CHARS = '/\\:*?"<>|'


def _clean_name(version_id: str) -> str:
    """版本名要能当目录名用，Windows 和 Linux 都得过。"""
    cleaned = (version_id or "").strip()
    if not cleaned:
        raise VersionError("版本名不能为空")
    if cleaned in (".", ".."):
        raise VersionError(f"版本名不合法：{version_id}")
    bad = [char for char in cleaned if char in _BAD_NAME_CHARS or ord(char) < 32]
    if bad:
        raise VersionError(f"版本名里有不能用的字符：{''.join(sorted(set(bad)))}")
    if len(cleaned) > 64:
        raise VersionError("版本名太长（上限 64 字）")
    return cleaned


def _version_dir(root: Path, version_id: str) -> Path:
    base = (Path(root) / "versions").resolve()
    target = (base / version_id).resolve()
    if target.parent != base:
        raise VersionError(f"非法版本路径：{version_id}")
    return target


def _rewrite_id(directory: Path, old_id: str, new_id: str) -> None:
    """把版本目录里的 JSON 和 jar 换成新 id。

    两样都得改：JSON 里的 id 字段决定加载器去找哪个 jar，jar 文件名不对就会「缺客户端」。
    """
    old_json = directory / f"{old_id}.json"
    data = _read_json(old_json)
    data["id"] = new_id
    new_json = directory / f"{new_id}.json"
    new_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if old_json != new_json and old_json.exists():
        old_json.unlink()
    old_jar = directory / f"{old_id}.jar"
    if old_jar.exists() and old_id != new_id:
        old_jar.rename(directory / f"{new_id}.jar")


def rename(root: Path, version_id: str, new_id: str) -> str:
    """重命名版本目录 + JSON 里的 id。有别的版本继承它就不让改。"""
    old_dir = _version_dir(root, version_id)
    if not old_dir.is_dir():
        raise VersionError(f"找不到版本 {version_id}")
    new = _clean_name(new_id)
    if new == version_id:
        return version_id
    new_dir = _version_dir(root, new)
    if new_dir.exists():
        raise VersionError(f"已经有叫 {new} 的版本了")
    dependents = [item.id for item in scan(root) if item.inherits == version_id]
    if dependents:
        raise VersionError(
            f"{version_id} 是这些版本的父版本，改名会让它们失效：{', '.join(dependents)}")
    try:
        old_dir.rename(new_dir)
    except OSError as exc:
        raise VersionError(f"重命名失败：{exc}") from exc
    try:
        _rewrite_id(new_dir, version_id, new)
    except (OSError, VersionError) as exc:
        try:  # 改不回去的话，版本会处于半残状态，尽量回滚
            new_dir.rename(old_dir)
        except OSError:
            pass
        raise VersionError(f"改名后写 JSON 失败，已尝试回滚：{exc}") from exc
    return new


def copy(root: Path, version_id: str, new_id: str) -> str:
    """整份复制一个版本目录（隔离开的话，模组和存档也会一起复制）。"""
    source = _version_dir(root, version_id)
    if not source.is_dir():
        raise VersionError(f"找不到版本 {version_id}")
    new = _clean_name(new_id)
    if new == version_id:
        raise VersionError("新版本名和原来的名字一样")
    target = _version_dir(root, new)
    if target.exists():
        raise VersionError(f"已经有叫 {new} 的版本了")
    try:
        shutil.copytree(source, target)
    except OSError as exc:
        raise VersionError(f"复制失败：{exc}") from exc
    try:
        _rewrite_id(target, version_id, new)
    except (OSError, VersionError) as exc:
        try:
            shutil.rmtree(target)
        except OSError:
            pass
        raise VersionError(f"复制后写 JSON 失败，已清理：{exc}") from exc
    return new


def open_folder(path: Path) -> None:
    """用系统文件管理器打开目录（GUI 的「打开文件夹」）。"""
    target = Path(path)
    if not target.exists():
        raise VersionError(f"目录不存在：{target}")
    if os.name == "nt":
        command = ["explorer", str(target)]
    elif sys.platform == "darwin":
        command = ["open", str(target)]
    else:
        command = ["xdg-open", str(target)]
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise VersionError(f"打不开文件管理器：{exc}") from exc


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
            raw = _read_json(json_path)
        except VersionError:
            continue
        try:
            resolved = resolve(root, directory.name)
            data = resolved.data
        except VersionError:
            data = raw
            resolved = None
        versions.append(InstalledVersion(
            id=directory.name,
            directory=directory,
            data=data,
            # 必须取原始 JSON：resolve() 出来的 data 已经合并过，inheritsFrom 被吃掉了
            inherits=raw.get("inheritsFrom"),
            loader=detect_loader(directory.name, data),
            java_major=resolved.java_major if resolved is not None else _java_major_of(root, data),
            has_jar=(resolved.client_jar.exists() if resolved is not None
                     else (directory / f"{directory.name}.jar").exists()),
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
