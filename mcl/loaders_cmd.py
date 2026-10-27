"""加载器安装命令。"""

from __future__ import annotations

from . import loaders, prompts
from .config import Config
from .java import ensure_java
from .progress import ProgressReporter
from .ui import UI
from .versions import VersionError, load_version


def run(args, ui: UI, cfg: Config) -> int:
    if args.name not in loaders.SUPPORTED:
        raise VersionError(f"支持：{', '.join(loaders.SUPPORTED)}")
    if not (cfg.version_dir(args.game) / f"{args.game}.json").exists():
        raise VersionError(f"先装原版 {args.game}，再装加载器")

    java = None
    if args.name in ("forge", "neoforge"):
        base = load_version(cfg.root(), args.game)
        required = (base.get("javaVersion") or {}).get("majorVersion")

        def on_phase(label: str, files: int, total_bytes: int):
            return ProgressReporter(label, files, total_bytes)

        runtime = ensure_java(cfg, required, on_phase=on_phase, note=ui.note)
        java = runtime.path
        ui.note(f"使用 {runtime.display}")

    version_id = prompts.spinner(
        ui, f"安装 {args.name} 到 {args.game}",
        lambda: loaders.install(
            args.name, args.game, cfg.root(), args.loader_version,
            source=cfg.download_source, java=java,
        ),
    )
    ui.ok(f"已创建版本 {version_id}")
    ui.note(f"启动：mcl launch {version_id}")
    return 0
