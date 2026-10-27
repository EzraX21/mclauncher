"""mcl crash [版本]：分析最新崩溃报告。"""

from __future__ import annotations

from . import crash
from .config import Config
from .ui import UI


def run(args, ui: UI, cfg: Config) -> int:
    version_id = getattr(args, "version", None) or cfg.last_version
    result = crash.analyze_version(cfg, version_id)
    if result["message"] and not result["findings"]:
        ui.warn(result["message"])
        if result["path"]:
            ui.note(result["path"])
            for line in result["tail"].splitlines()[-10:]:
                ui.note(f"  {line}")
            return 0
        return 1
    ui.title(f"崩溃分析 · {version_id or '最近一次'}")
    if result["path"]:
        ui.kv("日志", result["path"])
    for finding in result["findings"]:
        ui.blank()
        ui.kv("原因", finding["title"])
        ui.kv("详情", finding["detail"])
        ui.kv("建议", finding["fix"])
    if result["tail"]:
        ui.blank()
        ui.note("日志末尾：")
        for line in result["tail"].splitlines()[-15:]:
            ui.note(f"  {line}")
    return 0
