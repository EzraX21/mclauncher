"""doctor：检查环境是否适合跑 mcl。"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

from . import __version__, platforms, sources
from .config import Config, config_path
from .java import find_all
from .ui import UI
from .versions import scan


def _writable(path: Path) -> bool:
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return os.access(probe, os.W_OK)


def run(args, ui: UI, cfg: Config) -> int:
    ui.title(f"mcl doctor  ·  {__version__}")
    problems = 0

    ui.kv("Python", f"{sys.version.split()[0]}  ({sys.executable})")
    ui.kv("系统", f"{platform.system()} {platform.release()}  {platform.machine()}")
    size = shutil.get_terminal_size()
    ui.kv("终端", f"{'TTY' if sys.stdout.isatty() else '非交互'}  {size.columns}x{size.lines}")

    try:
        import textual

        ui.kv("Textual", textual.__version__)
    except ImportError:
        ui.kv("Textual", "未安装（TUI 不可用）")
        problems += 1

    try:
        import questionary

        ui.kv("questionary", questionary.__version__)
    except ImportError:
        ui.kv("questionary", "未安装（--cli 交互菜单不可用，装 mcl[cli]）")

    ui.blank()
    conf = config_path()
    ui.kv("配置", str(conf))
    if conf.exists():
        ui.info("已存在")
    else:
        ui.note("还没有，第一次保存配置时创建")

    root = cfg.root()
    ui.kv("游戏目录", str(root))
    if root.exists():
        if _writable(root):
            ui.info("可写")
        else:
            ui.error("不可写")
            problems += 1
    else:
        ui.note("不存在，安装时会创建")

    versions = scan(root)
    ui.kv("已装版本", f"{len(versions)} 个")

    ui.blank()
    runtimes = find_all(cfg)
    if runtimes:
        for runtime in runtimes[:5]:
            ui.ok(f"{runtime.display:<22} {runtime.path}")
    else:
        ui.warn("没找到 Java，可以在 TUI 里让它从 Mojang 下载")

    ui.blank()
    ui.kv("下载源", sources.describe(cfg.download_source))
    if getattr(args, "network", False):
        from .manifest import Manifest

        for mode in ("auto", "official"):
            try:
                manifest = Manifest.load(mode)
                ui.ok(f"{sources.describe(mode)}：最新正式版 {manifest.latest_release}")
            except Exception as exc:  # noqa: BLE001
                ui.error(f"{sources.describe(mode)}：{str(exc)[:90]}")
                problems += 1

    ui.blank()
    if problems:
        ui.warn(f"发现 {problems} 个问题，上面标 ✗ 的地方需要处理")
        return 1
    ui.ok("环境看起来没问题，直接运行 mcl 进 TUI")
    return 0
