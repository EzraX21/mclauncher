"""questionary 提示封装：选版本、选目录、确认、spinner。"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional

from .config import default_game_dir
from .manifest import Manifest, VersionEntry
from .ui import UI, display_width

try:
    import questionary
    from questionary import Choice, Separator
except ImportError:  # pragma: no cover
    questionary = None
    Choice = Separator = None


class Cancelled(Exception):
    """用户在提示里取消 / 中断。"""


class PromptsUnavailable(RuntimeError):
    pass


def require() -> None:
    if questionary is None:
        raise PromptsUnavailable("交互模式需要 questionary：pip install -r requirements.txt")
    if not sys.stdin.isatty():
        raise PromptsUnavailable("当前不是交互式终端，请加 -y 或直接传参数")


def style():
    return questionary.Style([
        ("qmark", "fg:#5fd7ff bold"),
        ("question", "bold"),
        ("answer", "fg:#5fd7ff bold"),
        ("pointer", "fg:#5fd7ff bold"),
        ("highlighted", "fg:#5fd7ff bold"),
        ("selected", "fg:#5fd7ff"),
        ("separator", "fg:#6c6c6c"),
        ("instruction", "fg:#6c6c6c"),
        ("disabled", "fg:#6c6c6c italic"),
    ])


def ask(prompt, ui: UI):
    answer = prompt.ask()
    if answer is None:
        ui.blank()
        raise Cancelled
    return answer


def confirm(ui: UI, message: str, default: bool = True) -> bool:
    require()
    return bool(ask(questionary.confirm(message, default=default, qmark="›", style=style()), ui))


def select(ui: UI, message: str, choices: list, default=None):
    require()
    return ask(questionary.select(message, choices=choices, default=default,
                                  qmark="›", style=style()), ui)


def text(ui: UI, message: str, default: str = "", validate=None) -> str:
    require()
    return ask(questionary.text(message, default=default, validate=validate,
                                qmark="›", style=style()), ui)


def choose_version(manifest: Manifest, ui: UI) -> VersionEntry:
    require()
    choices = [
        Choice(title=f"最新正式版   {manifest.latest_release}", value=manifest.latest_release),
        Choice(title=f"最新快照     {manifest.latest_snapshot}", value=manifest.latest_snapshot),
        Separator("──────────── 全部版本（输入可搜索） ────────────"),
    ]
    labels = {"release": "正式版", "snapshot": "快照", "old_beta": "远古 Beta", "old_alpha": "远古 Alpha"}
    for version in manifest.versions:
        choices.append(Choice(
            title=f"{version.id:<24}{labels.get(version.type, version.type):<10}{version.release_time[:10]}",
            value=version.id,
        ))
    answer = ask(questionary.select(
        "要装哪个版本？",
        choices=choices,
        use_search_filter=True,
        use_jk_keys=False,
        instruction="输入关键字过滤，↑↓ 选择，回车确认",
        qmark="›",
        style=style(),
    ), ui)
    return manifest.resolve(answer)


def _validate_directory(value: str):
    if not value.strip():
        return "目录不能为空"
    path = Path(value).expanduser()
    if path.exists() and not path.is_dir():
        return f"{path} 是个文件，不是目录"
    import os
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    if not os.access(probe, os.W_OK):
        return f"没有写权限：{probe}"
    return True


def choose_directory(ui: UI, preset: Optional[Path] = None, hint: bool = True) -> Path:
    require()
    if hint:
        ui.note("选 PCL 现有的 .minecraft 可以共用库和资源；想单独放一份就新建目录。")
    answer = ask(questionary.path(
        "安装目录",
        default=str(preset or default_game_dir()),
        validate=_validate_directory,
        qmark="›",
        style=style(),
    ), ui)
    return Path(answer).expanduser().resolve()


def ask_assets(ui: UI, asset_bytes: int) -> bool:
    from .progress import human_size

    if asset_bytes <= 0:
        return True
    return confirm(ui, f"下载资源文件？（音效、语言等，约 {human_size(asset_bytes)}）", default=True)


def ask_jobs(ui: UI) -> int:
    if not confirm(ui, "要调整下载设置吗？（并发数，默认 8）", default=False):
        return 8

    def check(value: str):
        value = value.strip()
        if not value.isdigit() or not 1 <= int(value) <= 32:
            return "请输入 1-32 的整数"
        return True

    return int(text(ui, "并发数", default="8", validate=check))


def choose_installed(ui: UI, versions: list, message: str = "选择版本"):
    require()
    if not versions:
        raise Cancelled
    labels = {"fabric": "Fabric", "quilt": "Quilt", "forge": "Forge", "neoforge": "NeoForge", "vanilla": "原版"}
    choices = [
        Choice(title=f"{version.id:<34}{labels.get(version.loader, version.loader):<9}"
                    f"Java {version.java_major or '?':<4}",
               value=version.id)
        for version in versions
    ]
    return select(ui, message, choices)


def spinner(ui: UI, label: str, func):
    if not sys.stdout.isatty():
        ui.note(f"{label} …")
        return func()

    stop = threading.Event()

    def spin() -> None:
        frames = "|/-\\"
        index = 0
        while not stop.wait(0.12):
            sys.stdout.write(f"\r  {frames[index % 4]} {label} …")
            sys.stdout.flush()
            index += 1

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    try:
        return func()
    finally:
        stop.set()
        thread.join(timeout=1)
        sys.stdout.write("\r" + " " * (display_width(f"  {label} …") + 4) + "\r")
        sys.stdout.flush()
