"""下载 / 安装原版：沿用原来的交互流程。"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from .config import Config
from .installer import PlanError, build_plan, execute
from .manifest import ApiError, Manifest, fetch_json
from .progress import ProgressReporter, human_size, human_time
from . import prompts
from .ui import UI


def print_summary(ui: UI, plan, jobs: int, source: str = "auto") -> None:
    version_json = plan.version_json
    rows = [
        ("版本", f"{plan.version_id}   ({version_json.get('type', 'release')}, {version_json.get('releaseTime', '')[:10]})"),
        ("目录", str(plan.root)),
        ("文件", f"{len(plan.version_tasks)} 个版本文件 + {len(plan.asset_tasks)} 个资源文件"),
        ("体积", human_size(plan.total_bytes)),
        ("Java", f"需要 Java {plan.java_major}+（会尝试复用或下载）" if plan.java_major else "未知"),
        ("并发", f"{jobs} 线程"),
        ("下载源", "BMCLAPI 镜像优先" if source != "official" else "仅官方"),
    ]
    ui.box("安装计划", rows)


def print_next_steps(ui: UI, plan) -> None:
    ui.title("下一步")
    ui.info("1. 在 PCL 里「导入已有游戏」指向这个目录，或者")
    ui.info(f"2. 直接用本工具启动：mcl launch {plan.version_id}")
    if plan.java_major:
        ui.note(f"启动需要 Java {plan.java_major}+，没有的话可以让我从 Mojang 下（java install {plan.java_major}）。")


def run(args, ui: UI, cfg: Config) -> int:
    manifest = prompts.spinner(ui, "读取 Mojang 版本清单",
                               lambda: Manifest.load(cfg.download_source))

    if args.list:
        ui.title("官方版本清单")
        ui.kv("最新正式版", manifest.latest_release)
        ui.kv("最新快照", manifest.latest_snapshot)
        ui.blank()
        for version in manifest.versions[:30]:
            ui.info(f"{version.id:<24}{version.type:<10}{version.release_time[:10]}")
        return 0

    interactive = not args.yes and sys.stdin.isatty()
    if args.target:
        entry = manifest.resolve(args.target)
    elif args.yes:
        entry = manifest.resolve("latest")
    elif interactive:
        entry = prompts.choose_version(manifest, ui)
    else:
        raise prompts.PromptsUnavailable("非交互终端：请给版本号，或加 -y 用最新正式版")

    version_json = prompts.spinner(ui, f"读取 {entry.id} 的元数据",
                                   lambda: manifest.version_json(entry))

    if args.directory:
        root = Path(args.directory).expanduser().resolve()
    elif args.yes:
        root = cfg.root()
    elif interactive:
        root = prompts.choose_directory(ui, cfg.root())
    else:
        root = cfg.root()

    cache: dict[str, dict] = {}

    def index_loader(url: str) -> dict:
        if url not in cache:
            cache[url] = fetch_json(url)
        return cache[url]

    full_plan = prompts.spinner(
        ui, "生成下载计划",
        lambda: build_plan(version_json, root, with_assets=True, index_loader=index_loader,
                           source=cfg.download_source),
    )

    if args.assets is None:
        with_assets = prompts.ask_assets(ui, full_plan.asset_bytes) if interactive else True
    else:
        with_assets = args.assets

    plan = full_plan if with_assets else build_plan(
        version_json, root, with_assets=False, source=cfg.download_source)

    jobs = args.jobs
    if jobs is None:
        jobs = prompts.ask_jobs(ui) if interactive else 8
    jobs = min(32, max(1, jobs))

    print_summary(ui, plan, jobs, cfg.download_source)
    if not with_assets:
        ui.warn("已跳过资源文件：游戏里会没有音效和语言文件。之后去掉 --no-assets 重跑即可补上。")

    if args.dry_run:
        ui.blank()
        ui.note("dry-run：计划已生成，没有下载任何文件。")
        return 0

    if interactive and not prompts.confirm(ui, "开始下载？"):
        return 130

    ui.title("开始下载")
    started = time.monotonic()
    phase = {"count": 0}

    def on_phase(label: str, files: int, total_bytes: int):
        if phase["count"]:
            ui.blank()
        phase["count"] += 1
        return ProgressReporter(label, files, total_bytes)

    result = execute(
        plan,
        jobs=jobs,
        retries=args.retries,
        force=args.force,
        on_phase=on_phase,
        on_note=ui.note,
    )
    elapsed = time.monotonic() - started

    ui.blank()
    if not result.ok:
        ui.error(f"{len(result.errors)} 个文件失败（共 {plan.total_files} 个）")
        for message in result.errors[:3]:
            ui.note(message)
        ui.warn("直接重跑同一条命令即可续传，校验通过的文件不会重下。")
        return 1

    ui.ok(f"完成：{plan.version_id}，{plan.total_files} 个文件，{human_size(result.downloaded_bytes)} 新下载")
    ui.kv("耗时", human_time(elapsed))
    ui.kv("位置", str(plan.root))
    if result.skipped_files:
        ui.note(f"其中 {result.skipped_files} 个文件已存在且校验通过，直接跳过。")

    cfg.game_dir = str(plan.root)
    cfg.last_version = plan.version_id
    cfg.save()

    print_next_steps(ui, plan)
    return 0
