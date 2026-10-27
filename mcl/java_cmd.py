"""Java 管理：列出现有运行时，或从 Mojang 下载一份。"""

from __future__ import annotations

from . import prompts
from .config import Config
from .java import component_for, find_all, install_runtime, probe
from .progress import ProgressReporter
from .ui import UI


def run(args, ui: UI, cfg: Config) -> int:
    if args.action == "list":
        runtimes = find_all(cfg)
        ui.title("可用的 Java")
        if not runtimes:
            ui.note("一个都没找到。运行 mcl java install 21 下载一个。")
            return 0
        for runtime in runtimes:
            ui.info(f"{runtime.display:<26} {runtime.path}")
        return 0

    component = args.component or "java-runtime-delta"
    if component.isdigit():
        component = component_for(int(component))

    def on_phase(label, files, total):
        return ProgressReporter(label, files, total)

    ui.note(f"从 Mojang 下载 {component} …")
    path = install_runtime(component, cfg.root(), jobs=cfg.jobs, on_phase=on_phase,
                           source=cfg.download_source)
    runtime = probe(path)
    if runtime is None:
        ui.error(f"装好了但跑不起来：{path}")
        return 1
    ui.ok(f"已安装 {runtime.display}")
    ui.kv("路径", str(path))
    cfg.java_path = str(path)
    cfg.save()
    ui.note("已设置为默认 Java。")
    return 0
