"""命令行入口：子命令分发，无参数时进交互主菜单。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, doctor, home, install_cmd, java_cmd, launch_cmd, loaders_cmd, mods_cmd, settings_cmd
from .config import Config
from .installer import PlanError
from .manifest import ApiError
from .prompts import Cancelled, PromptsUnavailable
from .ui import UI
from .versions import VersionError

COMMANDS = {"install", "versions", "launch", "loaders", "mods", "java", "config", "tui", "doctor"}
_GLOBAL_FLAGS = {"--plain", "--cli", "-h", "--help", "--version"}


def _normalize(argv: list[str]) -> list[str]:
    """`mclauncher 1.20.1` / `mclauncher --list` 都按 install 处理。"""
    if not argv:
        return argv
    if argv[0] in COMMANDS or argv[0] in _GLOBAL_FLAGS:
        return argv
    return ["install"] + argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mclauncher",
        description="原版 Minecraft 下载 + 版本管理 + 模组管理 + 启动，一条龙。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  mclauncher                        交互主菜单\n"
            "  mclauncher install 1.20.1         装原版\n"
            "  mclauncher loaders fabric 1.20.1  装 Fabric / Quilt / Forge / NeoForge\n"
            "  mclauncher mods search sodium     搜模组\n"
            "  mclauncher launch 1.20.1          启动\n"
        ),
    )
    parser.add_argument("--plain", action="store_true", help="关闭颜色")
    parser.add_argument("--cli", action="store_true", help="不用 TUI，用原来的文本界面")
    parser.add_argument("--version", action="version", version=f"mclauncher {__version__}")
    sub = parser.add_subparsers(dest="command")

    def add_dir(p):
        p.add_argument("-d", "--dir", dest="directory", help="游戏目录（默认读配置）")

    def add_source(p):
        p.add_argument("--source", choices=["auto", "official"],
                       help="下载源：official=只走官方（默认），auto=BMCLAPI 优先（PCL 同款）")

    p = sub.add_parser("install", help="下载 / 安装原版")
    p.add_argument("target", nargs="?", help="版本号，或 latest / latest-snapshot")
    add_dir(p)
    add_source(p)
    p.add_argument("--jobs", type=int, help="并发数")
    p.add_argument("--retries", type=int, default=3, help="单文件重试次数")
    p.add_argument("--assets", dest="assets", action="store_true", default=None, help="下载资源")
    p.add_argument("--no-assets", dest="assets", action="store_false", help="跳过资源")
    p.add_argument("--force", action="store_true", help="忽略已有文件全部重下")
    p.add_argument("--dry-run", action="store_true", help="只生成计划")
    p.add_argument("--list", action="store_true", help="列出官方版本")
    p.add_argument("-y", "--yes", action="store_true", help="全部用默认值")

    p = sub.add_parser("versions", help="列出已装版本")
    add_dir(p)

    p = sub.add_parser("launch", help="启动游戏")
    p.add_argument("version", nargs="?", help="版本号")
    add_dir(p)
    add_source(p)
    p.add_argument("--java", help="指定 java 可执行文件")
    p.add_argument("--memory", type=int, help="内存 MB")
    p.add_argument("--username", help="离线用户名")
    p.add_argument("--dry-run", action="store_true", help="只打印启动命令")
    p.add_argument("-y", "--yes", action="store_true", help="不确认直接启动")

    p = sub.add_parser("loaders", help="安装 Fabric / Quilt")
    p.add_argument("name", choices=["fabric", "quilt", "forge", "neoforge"])
    p.add_argument("game", help="原版版本号，例如 1.20.1")
    add_dir(p)
    add_source(p)
    p.add_argument("--loader-version", help="指定加载器版本")

    p = sub.add_parser("mods", help="模组管理")
    p.add_argument("action", choices=["list", "search", "install", "toggle", "remove"])
    p.add_argument("project", nargs="?", help="项目 slug / 本地模组名")
    add_dir(p)
    add_source(p)
    p.add_argument("--query", help="搜索关键词（search 用）")
    p.add_argument("--version", help="游戏版本（默认 last_version）")
    p.add_argument("--loader", help="加载器（fabric/quilt/forge/neoforge）")
    p.add_argument("--provider", choices=["modrinth", "curseforge"], default=None,
                   help="模组来源（默认 modrinth）")
    p.add_argument("-y", "--yes", action="store_true", help="不确认")

    p = sub.add_parser("java", help="Java 运行时")
    p.add_argument("action", choices=["list", "install"])
    p.add_argument("component", nargs="?", help="组件名或主版本号，例如 21")
    add_dir(p)
    add_source(p)

    sub.add_parser("tui", help="打开全屏 TUI")

    p = sub.add_parser("doctor", help="检查运行环境")
    p.add_argument("--network", action="store_true", help="顺便测一下下载源连通性")

    p = sub.add_parser("config", help="查看 / 修改配置")
    p.add_argument("action", nargs="?", default="show", choices=["show", "set"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    return parser


def _apply_directory(args, cfg: Config) -> None:
    directory = getattr(args, "directory", None)
    if directory:
        cfg.game_dir = str(Path(directory).expanduser().resolve())


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(_normalize(raw))
    ui = UI(color=False if getattr(args, "plain", False) else None)
    cfg = Config.load()

    if not args.command:
        if not sys.stdout.isatty():
            build_parser().print_help()
            return 0
        if not args.cli:
            try:
                from .tui.app import run as run_tui

                return run_tui(cfg)
            except ImportError:
                ui.warn("没装 textual，退回文本界面（pip install textual）")
        try:
            return home.run(ui, cfg)
        except PromptsUnavailable as exc:
            ui.error(str(exc))
            return 1

    _apply_directory(args, cfg)
    if getattr(args, "source", None):
        cfg.download_source = args.source

    try:
        if args.command == "install":
            return install_cmd.run(args, ui, cfg)
        if args.command == "versions":
            from .versions_cmd import run as versions_run

            return versions_run(args, ui, cfg)
        if args.command == "launch":
            return launch_cmd.run_launch(args, ui, cfg)
        if args.command == "loaders":
            return loaders_cmd.run(args, ui, cfg)
        if args.command == "mods":
            return mods_cmd.run(args, ui, cfg)
        if args.command == "java":
            return java_cmd.run(args, ui, cfg)
        if args.command == "config":
            return settings_cmd.run(args, ui, cfg)
        if args.command == "tui":
            if not sys.stdout.isatty():
                ui.error("TUI 需要交互式终端")
                return 2
            try:
                from .tui.app import run as run_tui
            except ImportError:
                ui.error("没装 textual：pip install textual（或 pipx install mclauncher）")
                return 1
            return run_tui(cfg)
        if args.command == "doctor":
            return doctor.run(args, ui, cfg)
    except Cancelled:
        ui.blank()
        ui.warn("已取消。")
        return 130
    except PromptsUnavailable as exc:
        ui.error(str(exc))
        return 1
    except (ApiError, VersionError, PlanError, RuntimeError) as exc:
        ui.blank()
        ui.error(str(exc))
        return 1
    except KeyboardInterrupt:
        ui.blank()
        ui.warn("已中断。")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
