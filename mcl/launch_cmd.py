"""启动命令：选版本 -> 选 Java -> 补库 -> 构建参数 -> 跑。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from . import auth, prompts
from .config import Config
from .java import JavaRuntime, component_for, ensure_java, find_all, pick, pick_exact, probe
from .launch import build_command, ensure_libraries, prepare_natives, run
from .progress import ProgressReporter, human_size
from .ui import UI
from .versions import VersionError, resolve, scan


def _select_version(ui: UI, cfg: Config, requested: Optional[str], interactive: bool) -> str:
    if requested:
        return requested
    installed = scan(cfg.root())
    if not installed:
        raise VersionError(f"{cfg.root()} 里没有已装版本，先运行 install")
    if interactive:
        return prompts.choose_installed(ui, installed, "启动哪个版本？")
    if cfg.last_version:
        return cfg.last_version
    raise VersionError("请指定版本号，例如：mcl launch 1.20.1")


def _select_java(ui: UI, cfg: Config, required: Optional[int], requested: Optional[str],
                 interactive: bool, dry_run: bool) -> Optional[JavaRuntime]:
    if requested:
        runtime = probe(Path(requested).expanduser())
        if runtime is None:
            raise RuntimeError(f"{requested} 不是可用的 Java")
        return runtime

    runtimes = find_all(cfg)
    exact = pick_exact(runtimes, required) if required is not None else pick(runtimes, None)
    if exact is not None:
        return exact

    if dry_run:
        return pick(runtimes, required)

    component = component_for(required)
    hint = f"需要 Java {required}，当前没有主版本匹配的运行时" if required else "没找到 Java"
    if not interactive:
        raise RuntimeError(f"{hint}。先运行：mcl java install {component}")

    if not prompts.confirm(ui, f"{hint}，要从 Mojang 下载 {component} 吗？", default=True):
        raise RuntimeError("没有可用的 Java，已取消")

    def on_phase(label, files, total):
        return ProgressReporter(label, files, total)

    return ensure_java(cfg, required, on_phase=on_phase, note=ui.note)


def run_launch(args, ui: UI, cfg: Config) -> int:
    interactive = not args.yes and sys.stdin.isatty()
    version_id = _select_version(ui, cfg, args.version, interactive)
    resolved = resolve(cfg.root(), version_id)

    if not resolved.client_jar.exists():
        ui.error(f"缺少客户端 jar：{resolved.client_jar}")
        ui.note(f"先运行：mcl install {resolved.jar_id}")
        return 2

    java = _select_java(ui, cfg, resolved.java_major, args.java, interactive, args.dry_run)

    phase = {"count": 0}

    def on_phase(label: str, files: int, total_bytes: int):
        if phase["count"]:
            ui.blank()
        phase["count"] += 1
        return ProgressReporter(label, files, total_bytes)

    prompts.spinner(ui, "检查依赖库",
                    lambda: ensure_libraries(resolved, cfg.root(), jobs=cfg.jobs,
                                             on_phase=on_phase, source=cfg.source))
    prompts.spinner(ui, "解压 natives", lambda: prepare_natives(resolved, cfg.root()))

    account = None
    if not getattr(args, "offline", False):
        account = auth.ensure_account(cfg)
    ui.note(f"账号：{account.name}（微软正版）" if account else "账号：离线模式")

    command = build_command(
        resolved,
        cfg,
        java,
        username=args.username,
        memory_mb=args.memory,
        account=account,
    )

    rows = [
        ("版本", f"{resolved.id}   ({', '.join(resolved.chain)})"),
        ("Java", java.display if java else "未找到"),
        ("内存", f"{args.memory or cfg.memory_mb} MB"),
        ("游戏目录", str(command.cwd)),
        ("类路径", f"{len(command.argv)} 个参数"),
    ]
    ui.box("启动配置", rows)

    for warning in command.warnings:
        ui.warn(warning)
    if command.missing:
        ui.error(f"缺少 {len(command.missing)} 个文件，先补全：")
        for path in command.missing[:5]:
            ui.note(path)
        if len(command.missing) > 5:
            ui.note(f"…… 还有 {len(command.missing) - 5} 个")
        return 2

    if args.dry_run:
        ui.blank()
        ui.note("dry-run：命令如下（不会启动）")
        print("  " + command.pretty())
        return 0

    if interactive and not prompts.confirm(ui, "启动游戏？"):
        return 130

    cfg.last_version = resolved.id
    cfg.save()
    ui.blank()
    ui.info(f"启动 {resolved.id} …（关闭游戏窗口即退出）")
    code = run(command)
    ui.blank()
    if code == 0:
        ui.ok("游戏正常退出")
    else:
        ui.warn(f"游戏退出码 {code}，日志在 {command.cwd / 'logs'}")
    return code
