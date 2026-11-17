"""整合包导入：Modrinth .mrpack / CurseForge zip。

目前完整支持 Modrinth 格式（含 overrides、加载器安装）；
CurseForge 的 manifest 能识别，但下载文件需要 CurseForge API key。
"""

from __future__ import annotations

import json
import re
import shutil
import time
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
    project_id: Optional[int] = None
    file_id: Optional[int] = None
    required: bool = True


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
    files = [PackFile(path="", project_id=int(entry.get("projectID", 0)),
                      file_id=int(entry.get("fileID", 0)),
                      required=bool(entry.get("required", True)))
             for entry in manifest.get("files") or []
             if entry.get("projectID") and entry.get("fileID")]
    return PackInfo(
        path=path, format="curseforge", name=str(manifest.get("name") or path.stem),
        version=str(manifest.get("version") or ""),
        minecraft=str(minecraft.get("version") or ""), loader=loader,
        loader_version=loader_version, files=files, overrides=overrides,
        needs_curseforge_key=bool(files),
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
    manifest = Manifest.load(cfg.source)
    entry = manifest.resolve(minecraft)
    version_json = manifest.version_json(entry)
    plan = build_plan(version_json, cfg.root(), with_assets=False,
                      source=cfg.source)
    result = execute(plan, jobs=cfg.jobs, on_phase=on_phase, on_note=on_log)
    if result.errors:
        raise PackError(result.errors[0])


def install(path: Path, cfg: Config, name: Optional[str] = None,
            on_log: Optional[Callable[[str], None]] = None,
            on_phase=None, cancel=None) -> str:
    note = on_log or (lambda _message: None)
    info = inspect(path)
    if info.needs_curseforge_key and not curseforge.api_key(cfg):
        raise PackError("CurseForge 整合包需要先配置 CurseForge API key"
                        "（设置 → CurseForge，或 mcl config set curseforge_api_key）")
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
            source=cfg.source, java=java.path if java else None,
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
    if info.format == "modrinth":
        for pack_file in info.files:
            relative = _safe_relative(pack_file.path)
            if relative is None:
                continue
            destination = instance_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            urls = sources.modrinth_candidates(pack_file.urls[0], cfg.source) \
                if "modrinth" in pack_file.urls[0] else [pack_file.urls[0]]
            alternates = tuple(urls[1:] + pack_file.urls[1:])
            tasks.append(DownloadTask(url=urls[0], dest=destination,
                                      sha1=pack_file.sha1, size=pack_file.size,
                                      alternates=alternates))
    else:
        key = curseforge.require_key(cfg)
        for pack_file in info.files:
            if not pack_file.required:
                continue
            try:
                cf_file = curseforge.file(pack_file.project_id, pack_file.file_id,
                                          key=key, config=cfg)
                url = curseforge.file_download_url(cf_file, key, cfg)
            except curseforge.CurseForgeError as exc:
                note(f"跳过 {pack_file.project_id}/{pack_file.file_id}：{exc}")
                continue
            if not url:
                note(f"跳过 {pack_file.project_id}/{pack_file.file_id}：没有下载链接")
                continue
            destination = instance_dir / "mods" / curseforge.primary_file_name(cf_file)
            destination.parent.mkdir(parents=True, exist_ok=True)
            tasks.append(DownloadTask(url=url, dest=destination,
                                      size=cf_file.get("fileLength")))

    note(f"下载 {len(tasks)} 个模组文件 …")
    total_bytes = sum(task.size or 0 for task in tasks)
    sink = on_phase("模组文件", len(tasks), total_bytes) if on_phase else None
    result = run_tasks(tasks, jobs=cfg.jobs, cancel=cancel, progress=sink)
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


# ---------------------------------------------------------------- 导出

# 只导出这些目录/文件：版本 JSON、jar、natives 这些是加载器装的，导出会重复且没必要
EXPORT_DIRS = ("mods", "config", "defaultconfigs", "kubejs", "resourcepacks", "shaderpacks")
EXPORT_FILES = ("options.txt", "optionsof.txt")
SKIP_SUFFIXES = (".log", ".part", ".tmp")

_LOADER_ID_PATTERNS = {
    "fabric": re.compile(r"^fabric-loader-(.+?)-(\d+\.\d+(?:\.\d+)?)$"),
    "quilt": re.compile(r"^quilt-loader-(.+?)-(\d+\.\d+(?:\.\d+)?)$"),
    "forge": re.compile(r"^(.+?)-forge-(.+)$"),
    "neoforge": re.compile(r"^(?:.+?-)?neoforge-(.+)$"),
}


def loader_version_of(loader: str, version_ids: list[str]) -> str:
    """从版本 id 里反推加载器版本（mcl 装加载器时就是用这些名字命名的）。"""
    pattern = _LOADER_ID_PATTERNS.get(loader)
    if pattern is None:
        return ""
    for version_id in version_ids:
        match = pattern.match(version_id)
        if match:
            groups = match.groups()
            # fabric-loader-<加载器版本>-<游戏版本>：加载器版本在前；forge 反过来
            return groups[0] if loader in ("fabric", "quilt") else groups[-1]
    return ""


def _export_slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return cleaned or "modpack"


def export(cfg: Config, version_id: str, dest: Optional[Path] = None,
           name: Optional[str] = None, include_saves: bool = False) -> dict:
    """把一个已装版本导出成 Modrinth 格式的 .mrpack。

    模组文件直接放进 overrides/（不联网去匹配 Modrinth 上的版本），所以导出包是自包含的：
    谁拿到都能装，代价是体积大一些。加载器和游戏版本写进 dependencies。
    """
    from .versions import VersionError, detect_loader, resolve

    root = cfg.root()
    try:
        resolved = resolve(root, version_id)
    except VersionError as exc:
        raise PackError(str(exc)) from exc

    chain = list(resolved.chain)
    game = chain[0] if chain else version_id
    loader = detect_loader(version_id, resolved.data)
    loader_version = loader_version_of(loader, [version_id] + list(reversed(chain)))
    warnings: list[str] = []
    if loader != "vanilla" and not loader_version:
        warnings.append(f"认不出 {loader} 的加载器版本，导入这个包时可能要手动选加载器")

    base = cfg.version_dir(version_id) if cfg.isolate_versions else root
    if not base.is_dir():
        raise PackError(f"找不到版本目录：{base}")
    if not cfg.isolate_versions:
        warnings.append("当前没开版本隔离：导出的是公共目录，可能混进别的版本的文件")

    dependencies: dict[str, str] = {"minecraft": str(game)}
    if loader != "vanilla" and loader_version:
        key = {"fabric": "fabric-loader", "quilt": "quilt-loader",
               "forge": "forge", "neoforge": "neoforge"}[loader]
        dependencies[key] = loader_version

    pack_name = (name or version_id).strip() or version_id
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "1.0.0",
        "name": pack_name,
        "summary": f"从 MCL 导出的实例：{version_id}",
        "files": [],
        "dependencies": dependencies,
    }

    directories = list(EXPORT_DIRS) + (["saves"] if include_saves else [])
    collected: list[tuple[Path, str]] = []
    for directory_name in directories:
        directory = base / directory_name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
                continue
            collected.append((path, f"{directory_name}/{path.relative_to(directory).as_posix()}"))
    for file_name in EXPORT_FILES:
        path = base / file_name
        if path.is_file():
            collected.append((path, file_name))

    if dest is None:
        exports_dir = root / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = exports_dir / f"{_export_slug(version_id)}-{stamp}.mrpack"
    dest = Path(dest).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("modrinth.index.json",
                             json.dumps(index, ensure_ascii=False, indent=2))
            for path, relative in collected:
                archive.write(path, f"overrides/{relative}")
    except OSError as exc:
        raise PackError(f"写整合包失败：{exc}") from exc

    return {
        "path": str(dest),
        "version": version_id,
        "name": pack_name,
        "game": str(game),
        "loader": loader,
        "loader_version": loader_version,
        "files": len(collected),
        "size": dest.stat().st_size,
        "warnings": warnings,
    }
