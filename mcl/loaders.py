"""加载器：Fabric / Quilt 用 profile JSON，Forge / NeoForge 走官方安装器。"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import sources
from .manifest import fetch_json, fetch_json_any, fetch_text
from .net import DownloadTask, download
from .versions import VersionError

FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
FORGE_PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
NEOFORGE_API = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
NEOFORGE_LEGACY_API = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/forge"
BMCLAPI = "https://bmclapi2.bangbang93.com"

SUPPORTED = ("fabric", "quilt", "forge", "neoforge")
LABELS = {
    "fabric": "Fabric",
    "quilt": "Quilt",
    "forge": "Forge",
    "neoforge": "NeoForge",
}

_CACHE: dict[tuple[str, str], list["LoaderVersion"]] = {}


@dataclass(frozen=True)
class LoaderVersion:
    version: str
    stable: bool = True
    recommended: bool = False

    @property
    def label(self) -> str:
        text = self.version if self.stable else f"{self.version} (beta)"
        return text + ("  ★推荐" if self.recommended else "")


def neoforge_prefix(game_version: str) -> Optional[str]:
    """把游戏版本映射成 NeoForge 的版本前缀。

    1.21.1 -> 21.1.；1.21 -> 21.0.；2026 起的 26.3 -> 26.3.
    """
    parts = game_version.split(".")
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    if parts[0] == "1":
        minor = parts[1]
        patch = parts[2] if len(parts) > 2 else "0"
        return f"{minor}.{patch}."
    if parts[1].isdigit():
        return f"{parts[0]}.{parts[1]}."
    return None


def _vkey(text: str) -> tuple:
    return tuple(int(part) if part.isdigit() else -1 for part in re.split(r"[.\-+]", text))


def _fetch(url: str, loader: str, source: str) -> dict:
    if loader == "fabric":
        return fetch_json_any(sources.fabric_meta_candidates(url, source))
    return fetch_json(url)


def list_versions(loader: str, game_version: str, source: str = "official",
                  refresh: bool = False) -> list[LoaderVersion]:
    """列出某个加载器对某游戏版本可用的版本，新的在前。"""
    if loader not in SUPPORTED:
        raise VersionError(f"不支持的加载器：{loader}")
    key = (loader, game_version)
    if not refresh and key in _CACHE:
        return _CACHE[key]

    if loader in ("fabric", "quilt"):
        versions = _fabric_like(loader, game_version, source)
    elif loader == "forge":
        versions = _forge(game_version, source)
    else:
        versions = _neoforge(game_version)

    versions = sorted(versions, key=lambda item: _vkey(item.version), reverse=True)
    _CACHE[key] = versions
    return versions


def _fabric_like(loader: str, game_version: str, source: str) -> list[LoaderVersion]:
    base = FABRIC_META if loader == "fabric" else QUILT_META
    data = _fetch(f"{base}/versions/loader/{game_version}", loader, source)
    return [
        LoaderVersion(item["loader"]["version"], bool(item["loader"].get("stable")))
        for item in data
    ]


def _forge(game_version: str, source: str) -> list[LoaderVersion]:
    versions: list[str] = []

    if sources.normalize_mode(source) == "auto":
        try:
            builds = fetch_json(f"{BMCLAPI}/forge/minecraft/{game_version}")
            versions = [str(build["version"]) for build in builds if build.get("version")]
        except Exception:  # noqa: BLE001 - 镜像挂了就退回官方
            versions = []

    if not versions:
        xml = fetch_text(f"{FORGE_MAVEN}/maven-metadata.xml")
        prefix = f"{game_version}-"
        versions = [
            entry[len(prefix):]
            for entry in re.findall(r"<version>([^<]+)</version>", xml)
            if entry.startswith(prefix)
        ]

    recommended = latest = None
    try:
        promos = json.loads(fetch_text(FORGE_PROMOS)).get("promos", {})
        recommended = promos.get(f"{game_version}-recommended")
        latest = promos.get(f"{game_version}-latest")
    except Exception:  # noqa: BLE001
        pass

    return [
        LoaderVersion(version, stable=True, recommended=(version == (recommended or latest)))
        for version in versions
    ]


def _version_tuple(text: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", text))[:3]


def neoforge_is_legacy(game_version: str) -> bool:
    """1.20.1 的 NeoForge 还叫 net.neoforged:forge，版本号是 47.1.x。"""
    parts = _version_tuple(game_version)
    return (1, 20, 1) <= parts < (1, 20, 2)


def _neoforge(game_version: str) -> list[LoaderVersion]:
    if neoforge_is_legacy(game_version):
        entries = fetch_json(NEOFORGE_LEGACY_API).get("versions", [])
        prefix = f"{game_version}-"
        return [LoaderVersion(str(entry)[len(prefix):])
                for entry in entries if str(entry).startswith(prefix)]

    prefix = neoforge_prefix(game_version)
    if not prefix:
        return []
    data = fetch_json(NEOFORGE_API)
    versions = [str(item) for item in data.get("versions", []) if str(item).startswith(prefix)]
    return [LoaderVersion(version, "beta" not in version) for version in versions]


# ---------------------------------------------------------------- 安装

def install(loader: str, game_version: str, root: Path,
            loader_version: Optional[str] = None,
            source: str = "official",
            java: Optional[Path] = None,
            on_log: Optional[Callable[[str], None]] = None) -> str:
    root = Path(root)
    if loader in ("fabric", "quilt"):
        return _install_fabric_like(loader, game_version, root, loader_version, source)
    if loader in ("forge", "neoforge"):
        return _install_with_installer(loader, game_version, root, loader_version,
                                       source, java, on_log)
    raise VersionError(f"不支持的加载器：{loader}")


def _base_installed(root: Path, game_version: str) -> bool:
    return (root / "versions" / game_version / f"{game_version}.json").exists()


def _install_fabric_like(loader: str, game_version: str, root: Path,
                         loader_version: Optional[str], source: str) -> str:
    base_json = root / "versions" / game_version / f"{game_version}.json"
    if not base_json.exists():
        raise VersionError(f"先装原版 {game_version}，再装 {loader} 加载器")

    if not loader_version:
        versions = list_versions(loader, game_version, source)
        if not versions:
            raise VersionError(f"{loader} 没有支持 {game_version} 的加载器版本")
        stable = [item for item in versions if item.stable]
        loader_version = (stable or versions)[0].version

    base = FABRIC_META if loader == "fabric" else QUILT_META
    profile = _fetch(
        f"{base}/versions/loader/{game_version}/{loader_version}/profile/json",
        loader, source,
    )
    version_id = profile.get("id") or f"{loader}-loader-{loader_version}-{game_version}"
    profile["id"] = version_id
    profile.setdefault("inheritsFrom", game_version)
    profile.setdefault("type", "release")

    directory = root / "versions" / version_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{version_id}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return version_id


def installer_urls(loader: str, game_version: str, loader_version: str, source: str) -> list[str]:
    if loader == "forge":
        path = (f"net/minecraftforge/forge/{game_version}-{loader_version}/"
                f"forge-{game_version}-{loader_version}-installer.jar")
        official = f"https://maven.minecraftforge.net/{path}"
    elif neoforge_is_legacy(game_version):
        path = (f"net/neoforged/forge/{game_version}-{loader_version}/"
                f"forge-{game_version}-{loader_version}-installer.jar")
        official = f"https://maven.neoforged.net/releases/{path}"
    else:
        path = f"net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar"
        official = f"https://maven.neoforged.net/releases/{path}"
    mirror = f"{BMCLAPI}/maven/{path}"
    return sources._rank(official, [mirror], source)


def _ensure_profiles(root: Path) -> None:
    path = root / "launcher_profiles.json"
    if path.exists():
        return
    if not (root / "versions").exists():
        raise VersionError(f"{root} 看起来不是游戏目录")
    path.write_text('{"profiles":{},"settings":{},"version":3}\n', encoding="utf-8")


def _profile(root: Path, version_id: str) -> Optional[dict]:
    path = root / "versions" / version_id / f"{version_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _find_installed(root: Path, game_version: str, loader_version: str,
                    pool: Optional[set[str]] = None) -> Optional[str]:
    names = pool if pool is not None else _version_ids(root)
    matches = []
    for name in names:
        data = _profile(root, name)
        if not data or data.get("inheritsFrom") != game_version:
            continue
        dumped = json.dumps(data).lower()
        if loader_version in dumped or loader_version in name:
            matches.append(name)
    if not matches:
        return None
    matches.sort(key=lambda name: ("neoforge" not in name.lower(), "forge" not in name.lower(), name))
    return matches[0]


def _version_ids(root: Path) -> set[str]:
    base = root / "versions"
    if not base.exists():
        return set()
    return {item.name for item in base.iterdir() if item.is_dir()}


def _install_with_installer(loader: str, game_version: str, root: Path,
                            loader_version: Optional[str], source: str,
                            java: Optional[Path],
                            on_log: Optional[Callable[[str], None]]) -> str:
    if not _base_installed(root, game_version):
        raise VersionError(f"先装原版 {game_version}，再装 {loader}")
    if java is None:
        raise VersionError("安装 Forge / NeoForge 需要 Java，先装一个")

    versions = list_versions(loader, game_version, source, refresh=True)
    if not versions:
        raise VersionError(f"{loader} 没有支持 {game_version} 的版本")
    chosen = loader_version or next(
        (item.version for item in versions if item.recommended),
        next((item.version for item in versions if item.stable), versions[0].version),
    )

    urls = installer_urls(loader, game_version, chosen, source)
    installers = root / "mcl" / "installers"
    installers.mkdir(parents=True, exist_ok=True)
    installer = installers / f"{loader}-{game_version}-{chosen}-installer.jar"
    if not installer.exists():
        download(DownloadTask(urls[0], installer, alternates=tuple(urls[1:])))

    existing = _find_installed(root, game_version, chosen)
    if existing:
        if on_log:
            on_log(f"已经装过，复用 {existing}")
        return existing

    _ensure_profiles(root)
    before = _version_ids(root)

    command = [str(java), "-jar", str(installer), "--installClient", str(root)]
    if on_log:
        on_log(f"运行 {loader} 安装器：{' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        text = line.rstrip()
        if text and on_log:
            on_log(text)
    code = process.wait()
    if code != 0:
        raise VersionError(f"{loader} 安装器退出码 {code}")

    created = _version_ids(root) - before
    detected = _find_installed(root, game_version, chosen, created) or \
        _find_installed(root, game_version, chosen)
    if detected:
        return detected

    expected_ids = [f"{game_version}-{loader}-{chosen}", f"{loader}-{chosen}",
                    f"{game_version}-forge-{chosen}"]
    for expected in expected_ids:
        if (root / "versions" / expected / f"{expected}.json").exists():
            return expected
    raise VersionError(f"安装器跑完了，但没找到新版本（试过 {', '.join(expected_ids)}）")
