"""版本列表。"""

from __future__ import annotations

from .config import Config
from .mods import list_mods
from .ui import UI
from .versions import scan


def run(args, ui: UI, cfg: Config) -> int:
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
