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


def report(cfg: Config) -> dict:
    """结构化体检结果，给 GUI 的「百宝箱 → 环境诊断」用。

    返回的 checks 每项是 {label, value, status}，status 取 ok / warn / bad / info。
    """
    checks: list[dict] = []
    problems = 0

    checks.append({"label": "Python", "status": "info",
                   "value": f"{sys.version.split()[0]}  ({sys.executable})"})
    checks.append({"label": "系统", "status": "info",
                   "value": f"{platform.system()} {platform.release()}  {platform.machine()}"})

    try:
        import textual

        checks.append({"label": "Textual", "status": "ok", "value": textual.__version__})
    except ImportError:
        checks.append({"label": "Textual", "status": "bad", "value": "未安装（TUI 不可用）"})
        problems += 1

    try:
        import questionary

        checks.append({"label": "questionary", "status": "ok", "value": questionary.__version__})
    except ImportError:
        checks.append({"label": "questionary", "status": "warn",
                       "value": "未安装（--cli 交互菜单不可用，装 mcl[cli]）"})

    conf = config_path()
    if conf.exists():
        checks.append({"label": "配置文件", "status": "ok", "value": str(conf)})
    else:
        checks.append({"label": "配置文件", "status": "info",
                       "value": f"{conf}（还没有，保存设置时创建）"})

    root = cfg.root()
    if root.exists():
        writable = _writable(root)
        checks.append({"label": "游戏目录", "status": "ok" if writable else "bad",
                       "value": f"{root}{'' if writable else '（不可写）'}"})
        if not writable:
            problems += 1
    else:
        checks.append({"label": "游戏目录", "status": "info",
                       "value": f"{root}（不存在，安装版本时创建）"})

    versions = scan(root)
    checks.append({"label": "已装版本", "status": "ok" if versions else "warn",
                   "value": f"{len(versions)} 个"})

    # 探测给短超时：report() 在 HTTP 请求线程里跑，逐个探测每个都给 15 秒会堵住界面
    runtimes = find_all(cfg, timeout=5)
    # 没 Java 只是警告：mcl java install 能补，别把退出码弄成失败
    checks.append({"label": "Java", "status": "ok" if runtimes else "warn",
                   "value": "、".join(runtime.display for runtime in runtimes[:4]) or "没找到"})

    checks.append({"label": "下载源", "status": "info", "value": sources.describe(cfg.source)})

    return {
        "version": __version__,
        "checks": checks,
        "java": [{"display": runtime.display, "path": str(runtime.path), "major": runtime.major}
                 for runtime in runtimes],
        "problems": problems,
    }


def about(cfg: Config) -> dict:
    """百宝箱 → 关于：版本、平台、路径、许可证。"""
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "config_path": str(config_path()),
        "game_dir": str(cfg.root()),
        "exports_dir": str(cfg.root() / "exports"),
        "license": "GPL-3.0-or-later",
        "repo": "https://github.com/EzraX21/mclauncher",
        "releases": "https://github.com/EzraX21/mclauncher/releases",
    }


def run(args, ui: UI, cfg: Config) -> int:
    """命令行版：把 report() 的结果按状态打出来。"""
    ui.title(f"mcl doctor  ·  {__version__}")
    data = report(cfg)
    printers = {"ok": ui.ok, "warn": ui.warn, "bad": ui.error}
    for check in data["checks"]:
        line = f"{check['label']:<10} {check['value']}"
        printers.get(check["status"], ui.info)(line)

    problems = data["problems"]
    if getattr(args, "network", False):
        from .manifest import Manifest

        ui.blank()
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
