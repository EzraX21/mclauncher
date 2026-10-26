"""模组：本地列表 / 启用禁用 / 删除，以及 Modrinth 搜索安装。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from . import curseforge, modrinth, prompts
from .config import Config
from .mods import find, list_mods, remove, set_enabled
from .progress import human_size
from .ui import UI
from .versions import VersionError, detect_loader, resolve, scan


def _version_context(cfg: Config, version_id: str) -> tuple[str, str]:
    resolved = resolve(cfg.root(), version_id)
    loader = detect_loader(version_id, resolved.data)
    game_version = resolved.chain[0] if resolved.chain else version_id
    return loader, game_version


def _pick_version(ui: UI, cfg: Config, requested: Optional[str], interactive: bool) -> str:
    if requested:
        return requested
    installed = scan(cfg.root())
    if not installed:
        raise VersionError("还没有装任何版本")
    if interactive:
        return prompts.choose_installed(ui, installed, "给哪个版本管理模组？")
    if cfg.last_version:
        return cfg.last_version
    raise VersionError("请指定版本，例如：mclauncher mods list 1.20.1")


def _print_mods(ui: UI, cfg: Config, version_id: str) -> None:
    mods = list_mods(cfg.mods_path(version_id))
    ui.title(f"{version_id} 的模组（{len(mods)} 个）")
    if not mods:
        ui.note("一个都没有。用 mclauncher mods search <关键词> 搜一个。")
        return
    seen: dict[str, list[str]] = {}
    for mod in mods:
        state = "启用" if mod.enabled else "禁用"
        title = mod.title or mod.name
        version = f"  {mod.version}" if mod.version else ""
        ui.info(f"{state}  {human_size(mod.size):>9}  {title}{version}")
        if mod.mod_id:
            seen.setdefault(mod.mod_id, []).append(mod.name)
    duplicates = {key: value for key, value in seen.items() if len(value) > 1}
    for mod_id, files in duplicates.items():
        ui.warn(f"重复的模组 {mod_id}：{', '.join(files)}（游戏里可能冲突）")


def _install_project(ui: UI, cfg: Config, version_id: str, reference: str,
                     loader: str, game_version: str, interactive: bool,
                     install_deps: bool = True) -> int:
    source = cfg.download_source
    project = modrinth.get_project(reference, source)
    title = project.get("title", reference)
    version = modrinth.latest_version(project.get("id", reference), loader, game_version, source)
    if version is None:
        ui.error(f"{title} 没有适配 {game_version} / {loader} 的版本")
        return 1

    if interactive:
        ui.note(f"{title}：{modrinth.describe(version)}")
        if not prompts.confirm(ui, "下载并装进 mods 目录？"):
            return 130

    file_info = modrinth.primary_file(version) or {}
    filename = file_info.get("filename", "")
    mods_path = cfg.mods_path(version_id)
    if filename and (mods_path / filename).exists():
        path = mods_path / filename
        ui.ok(f"{filename} 已经在 mods 里，跳过下载")
    else:
        installed_ids = {mod.mod_id for mod in list_mods(mods_path) if mod.mod_id}
        project_slug = project.get("slug")
        if project_slug and project_slug in installed_ids:
            ui.warn(f"已经装过 {title} 的其它版本，注意别重复")
        path = modrinth.download_version(version, cfg.mods_dir(version_id), source)
        ui.ok(f"已安装 {path.name}")

    if not install_deps:
        return 0

    for dependency in modrinth.required_dependencies(version):
        dep_version = None
        if dependency.get("version_id"):
            dep_version = modrinth.get_version(dependency["version_id"], source)
        elif dependency.get("project_id"):
            dep_version = modrinth.latest_version(dependency["project_id"], loader, game_version, source)
        if dep_version is None:
            continue
        file_info = modrinth.primary_file(dep_version) or {}
        filename = file_info.get("filename")
        if filename and ((cfg.mods_path(version_id) / filename).exists()
                         or (cfg.mods_path(version_id) / (filename + ".disabled")).exists()):
            continue
        try:
            dep_project = modrinth.get_project(dependency["project_id"], source)
            dep_title = dep_project.get("title", dependency["project_id"])
        except modrinth.ModrinthError:
            dep_project, dep_title = {}, dependency.get("project_id", "前置")

        dep_slug = dep_project.get("slug")
        present = {mod.mod_id for mod in list_mods(cfg.mods_path(version_id)) if mod.mod_id}
        if dep_slug and dep_slug in present:
            continue
        if interactive and not prompts.confirm(ui, f"还需要前置 {dep_title}，一起装？"):
            continue
        dep_path = modrinth.download_version(dep_version, cfg.mods_dir(version_id), source)
        ui.ok(f"已安装前置 {dep_path.name}")
    return 0


def _install_curseforge(ui: UI, cfg: Config, version_id: str, reference: str,
                        loader: str, game_version: str, interactive: bool) -> int:
    key = curseforge.require_key(cfg)
    try:
        mod_id = int(reference)
    except ValueError:
        raise VersionError(f"CurseForge 需要数字 mod id，收到的是 {reference}")

    file = curseforge.latest_file(mod_id, loader, game_version, key=key)
    if file is None:
        ui.error(f"CurseForge 上没有适配 {game_version} / {loader} 的文件")
        return 1
    name = curseforge.primary_file_name(file)
    if interactive:
        ui.note(f"{curseforge.describe(file)}")
        if not prompts.confirm(ui, "下载并装进 mods 目录？"):
            return 130

    path = curseforge.download_file(file, cfg.mods_dir(version_id), key=key)
    ui.ok(f"已安装 {path.name}")

    for dependency_id in curseforge.required_dependency_ids(file):
        dep_file = curseforge.latest_file(dependency_id, loader, game_version, key=key)
        if dep_file is None:
            continue
        dep_path = curseforge.download_file(dep_file, cfg.mods_dir(version_id), key=key)
        ui.ok(f"前置：{dep_path.name}")
    return 0


def run(args, ui: UI, cfg: Config) -> int:
    interactive = not args.yes and sys.stdin.isatty()
    requested = args.version
    if args.action == "list" and not requested:
        requested = args.project
    version_id = _pick_version(ui, cfg, requested, interactive)

    if args.action == "list":
        _print_mods(ui, cfg, version_id)
        return 0

    loader, game_version = _version_context(cfg, version_id)
    if loader == "vanilla":
        runner = args.loader or ""
        if runner not in ("fabric", "quilt", "forge", "neoforge"):
            if not args.loader:
                raise VersionError(
                    f"{version_id} 是原版，装模组得先套加载器："
                    f"mclauncher loaders fabric {game_version}"
                )
        loader = args.loader

    provider = getattr(args, "provider", None) or "modrinth"

    if args.action == "search":
        query = args.query or args.project or ""
        if not query:
            raise VersionError("搜索要给关键词：mods search <关键词>")
        if provider == "curseforge":
            hits = curseforge.search(query, loader=loader, game_version=game_version,
                                     limit=10, config=cfg)
        else:
            hits = modrinth.search(query, loader=loader, game_version=game_version, limit=10,
                                   source=cfg.download_source)
        if not hits:
            ui.warn("没搜到结果，换个关键词？")
            return 0
        ui.title(f"搜索：{query}  （{game_version} / {loader} / {provider}）")
        for index, hit in enumerate(hits, 1):
            ui.info(f"{index:>2}. {hit.title}  ({hit.slug})  {hit.downloads:,} 次下载")
            ui.note(hit.description[:80])
        if not interactive:
            return 0
        choices = [prompts.Choice(title=f"{hit.title}  ({hit.slug})", value=hit.slug) for hit in hits]
        choices.append(prompts.Separator("────────"))
        choices.append(prompts.Choice(title="返回", value=None))
        picked = prompts.select(ui, "装哪个？", choices)
        if not picked:
            return 0
        if provider == "curseforge":
            return _install_curseforge(ui, cfg, version_id, picked, loader, game_version, interactive)
        return _install_project(ui, cfg, version_id, picked, loader, game_version, interactive)

    if args.action == "install":
        if not args.project:
            raise VersionError("要给 mod id 或 slug，例如 mods install sodium")
        if provider == "curseforge":
            return _install_curseforge(ui, cfg, version_id, args.project, loader,
                                       game_version, interactive)
        return _install_project(ui, cfg, version_id, args.project, loader, game_version, interactive)

    if args.action == "toggle":
        matches = find(cfg.mods_path(version_id), args.project)
        if not matches:
            ui.error(f"mods 里没有匹配 “{args.project}” 的模组")
            return 1
        target = matches[0] if len(matches) == 1 else None
        if target is None:
            choices = [prompts.Choice(title=f"{'启用' if mod.enabled else '禁用'}  {mod.name}", value=mod.name)
                       for mod in matches]
            name = prompts.select(ui, "切换哪个？", choices)
            target = next(mod for mod in matches if mod.name == name)
        destination = set_enabled(target, not target.enabled)
        ui.ok(f"{target.name} -> {'启用' if not target.enabled else '禁用'}（{destination.name}）")
        return 0

    if args.action == "remove":
        matches = find(cfg.mods_path(version_id), args.project)
        if not matches:
            ui.error(f"mods 里没有匹配 “{args.project}” 的模组")
            return 1
        target = matches[0]
        if interactive and not prompts.confirm(ui, f"删掉 {target.name}？", default=False):
            return 130
        remove(target)
        ui.ok(f"已删除 {target.name}")
        return 0

    raise VersionError(f"未知的 mods 动作：{args.action}")
