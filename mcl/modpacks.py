"""整合包导入：Modrinth .mrpack / CurseForge zip。

目前完整支持 Modrinth 格式（含 overrides、加载器安装）；
CurseForge 的 manifest 能识别，但下载文件需要 CurseForge API key。
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import curseforge, loaders, sources
from .config import Config
from .installer import build_plan, execute
from .java import ensure_java
from .manifest import Manifest
from .net import DownloadTask, run_tasks
from .versions import scan


class PackError(RuntimeError):
    """整合包解析/安装失败。"""


@dataclass
class PackFile:
    path: str
    urls: list[str] = field(default_factory=list)
    sha1: Optional[str] = None
    size: Optional[int] = None


@dataclass
class PackInfo:
    path: Path
    format: str
    name: str
    version: str = ""
    minecraft: str = ""
    loader: str = "vanilla"
    loader_version: str = ""
    files: list[PackFile] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)
    client_overrides: list[str] = field(default_factory=list)
    needs_curseforge_key: bool = False


def _loader_from_dependencies(deps: dict) -> tuple[str, str]:
    for key, loader in (("fabric-loader", "fabric"), ("quilt-loader", "quilt"),
                        ("forge", "forge"), ("neoforge", "neoforge")):
        if deps.get(key):
            return loader, str(deps[key])
    return "vanilla", ""


def inspect(path: Path) -> PackInfo:
    path = Path(path).expanduser()
    if not path.is_file():
        raise PackError(f"找不到整合包：{path}")
    if path.suffix.lower() not in (".mrpack", ".zip"):
        raise PackError("只支持 .mrpack / .zip 整合包")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "modrinth.index.json" in names:
                return _inspect_modrinth(path, archive)
            if "manifest.json" in names:
                return _inspect_curseforge(path, archive)
    except zipfile.BadZipFile as exc:
        raise PackError("这不是有效的 zip / mrpack 文件") from exc
    raise PackError("压缩包里没有 modrinth.index.json 或 manifest.json")


def _inspect_modrinth(path: Path, archive: zipfile.ZipFile) -> PackInfo:
    try:
        index = json.loads(archive.read("modrinth.index.json").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PackError("modrinth.index.json 解析失败") from exc
    deps = index.get("dependencies") or {}
    loader, loader_version = _loader_from_dependencies(deps)
    minecraft = str(deps.get("minecraft") or "")
    files: list[PackFile] = []
    for entry in index.get("files") or []:
        env = entry.get("env") or {}
        if env.get("client") == "unsupported":
            continue
        path_text = str(entry.get("path") or "").lstrip("/")
        if not path_text or ".." in Path(path_text).parts:
            continue
        downloads = [str(url) for url in entry.get("downloads") or [] if url]
        if not downloads:
            continue
        hashes = entry.get("hashes") or {}
        files.append(PackFile(path=path_text, urls=downloads,
                              sha1=hashes.get("sha1"), size=entry.get("fileSize")))
    overrides = sorted(name[len("overrides/"):] for name in archive.namelist()
                       if name.startswith("overrides/") and not name.endswith("/"))
    client = sorted(name[len("client-overrides/"):] for name in archive.namelist()
                    if name.startswith("client-overrides/") and not name.endswith("/"))
    return PackInfo(
        path=path, format="modrinth", name=str(index.get("name") or path.stem),
        version=str(index.get("versionId") or ""), minecraft=minecraft,
        loader=loader, loader_version=loader_version, files=files,
        overrides=overrides, client_overrides=client,
    )


def _inspect_curseforge(path: Path, archive: zipfile.ZipFile) -> PackInfo:
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PackError("manifest.json 解析失败") from exc
    minecraft = (manifest.get("minecraft") or {})
    loaders_list = minecraft.get("modLoaders") or []
    loader, loader_version = "vanilla", ""
    if loaders_list:
        raw = str(loaders_list[0].get("id") or "")
        for name in ("forge", "neoforge", "fabric", "quilt"):
            if raw.lower().startswith(name + "-"):
                loader = "neoforge" if raw.lower().startswith("neoforge-") else name
                loader_version = raw[len(name) + 1:]
                break
    overrides = sorted(name[len("overrides/"):] for name in archive.namelist()
                       if name.startswith("overrides/") and not name.endswith("/"))
    return PackInfo(
        path=path, format="curseforge", name=str(manifest.get("name") or path.stem),
        version=str(manifest.get("version") or ""),
        minecraft=str(minecraft.get("version") or ""), loader=loader,
        loader_version=loader_version, overrides=overrides,
        needs_curseforge_key=bool(manifest.get("files")),
    )


def _safe_relative(name: str) -> Optional[Path]:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return candidate


def _instance_name(base: str, root: Path) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-._") or "modpack"
    existing = {version.id for version in scan(root)}
    candidate = cleaned
    index = 2
    while candidate in existing or (root / "versions" / candidate).exists():
        candidate = f"{cleaned}-{index}"
        index += 1
    return candidate


def _ensure_base(cfg: Config, minecraft: str, on_log: Callable[[str], None],
                 on_phase=None) -> None:
    target = cfg.root() / "versions" / minecraft / f"{minecraft}.json"
    if target.exists():
        return
    on_log(f"先安装原版 {minecraft} …")
    manifest = Manifest.load(cfg.download_source)
    entry = manifest.resolve(minecraft)
    version_json = manifest.version_json(entry)
    plan = build_plan(version_json, cfg.root(), with_assets=False,
                      source=cfg.download_source)
    result = execute(plan, jobs=cfg.jobs, on_phase=on_phase, on_note=on_log)
    if result.errors:
        raise PackError(result.errors[0])


def install(path: Path, cfg: Config, name: Optional[str] = None,
            on_log: Optional[Callable[[str], None]] = None,
            on_phase=None, cancel=None) -> str:
    note = on_log or (lambda _message: None)
    info = inspect(path)
    if info.needs_curseforge_key:
        if not curseforge.api_key(cfg):
            raise PackError("CurseForge 整合包需要先配置 CurseForge API key"
                            "（设置 → CurseForge，或 mcl config set curseforge_api_key）")
        raise PackError("CurseForge 整合包下载暂未接入，先用 Modrinth 的 .mrpack")
    if not info.minecraft:
        raise PackError("整合包没有写 Minecraft 版本")
    if info.loader != "vanilla" and not info.loader_version:
        raise PackError(f"整合包没有写 {info.loader} 版本")

    root = cfg.root()
    _ensure_base(cfg, info.minecraft, note, on_phase)

    java = None
    if info.loader in ("forge", "neoforge"):
        from .versions import resolve
        resolved = resolve(root, info.minecraft)
        java = ensure_java(cfg, resolved.java_major, on_phase=on_phase, note=note)

    loader_id = info.minecraft
    if info.loader != "vanilla":
        note(f"安装 {info.loader} {info.loader_version} …")
        loader_id = loaders.install(
            info.loader, info.minecraft, root, loader_version=info.loader_version,
            source=cfg.download_source, java=java.path if java else None,
            on_log=note,
        )

    instance = _instance_name(name or info.name or info.path.stem, root)
    instance_dir = root / "versions" / instance
    instance_dir.mkdir(parents=True, exist_ok=True)
    profile = {
        "id": instance,
        "inheritsFrom": loader_id,
        "type": "release",
        "name": info.name or instance,
    }
    (instance_dir / f"{instance}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    tasks: list[DownloadTask] = []
    for pack_file in info.files:
        relative = _safe_relative(pack_file.path)
        if relative is None:
            continue
        destination = instance_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        urls = sources.modrinth_candidates(pack_file.urls[0], cfg.download_source) \
            if "modrinth" in pack_file.urls[0] else [pack_file.urls[0]]
        alternates = tuple(urls[1:] + pack_file.urls[1:])
        tasks.append(DownloadTask(url=urls[0], dest=destination,
                                  sha1=pack_file.sha1, size=pack_file.size,
                                  alternates=alternates))
    note(f"下载 {len(tasks)} 个模组文件 …")
    result = run_tasks(tasks, jobs=cfg.jobs, cancel=cancel,
                       progress=None)
    if result.errors:
        raise PackError(result.errors[0])

    with zipfile.ZipFile(info.path) as archive:
        for prefix, names in (("overrides/", info.overrides),
                              ("client-overrides/", info.client_overrides)):
            for relative_text in names:
                relative = _safe_relative(relative_text)
                if relative is None:
                    continue
                target = instance_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(prefix + relative_text) as source, open(target, "wb") as sink:
                    shutil.copyfileobj(source, sink)

    note(f"整合包已安装：{instance}")
    return instance
