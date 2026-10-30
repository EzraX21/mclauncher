"""版本列表 / 删除。"""

from __future__ import annotations

from . import prompts
from .config import Config
from .mods import list_mods
from .ui import UI
from .versions import VersionError, remove as remove_version, scan


def remove(args, ui: UI, cfg: Config) -> int:
    version_id = (getattr(args, "version", None) or "").strip()
    if not version_id:
        ui.error("要删除哪个版本？例如：mcl versions remove 1.20.1")
        return 2
    directory = cfg.version_dir(version_id)
    if not directory.is_dir():
        ui.error(f"找不到版本 {version_id}")
        return 1

    if cfg.isolate_versions:
        detail = "该版本目录里的存档、模组和配置会一起删除"
    else:
        detail = "只删除版本文件，公共存档和模组不会动"
    if not getattr(args, "yes", False):
        if not prompts.confirm(ui, f"删除版本 {version_id}？{detail}。", default=False):
            ui.note("已取消")
            return 0

    try:
        remove_version(cfg.root(), version_id)
    except VersionError as exc:
        ui.error(str(exc))
        return 1
    if cfg.last_version == version_id:
        cfg.last_version = None
        cfg.save()
    ui.ok(f"已删除 {version_id}")
    return 0


def run(args, ui: UI, cfg: Config) -> int:
    if getattr(args, "action", "list") == "remove":
        return remove(args, ui, cfg)

    versions = scan(cfg.root())
    ui.title(f"已装版本  ·  {cfg.root()}")
    if not versions:
        ui.note("还没有装任何版本。运行 mcl install 下载一个。")
        return 0

    for version in versions:
        jar = "✓" if version.has_jar else "—"
        mods = len(list_mods(cfg.mods_path(version.id))) if cfg.mods_path(version.id).exists() else 0
        ui.info(
            f"{version.id:<36}"
            f"{version.loader:<10}"
            f"Java {str(version.java_major or '?'):<5}"
            f"jar {jar}  模组 {mods}"
        )
    return 0
