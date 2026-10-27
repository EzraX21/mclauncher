"""Linux 桌面启动项：让应用菜单 / launcher 搜得到 MCL。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ENTRY = """[Desktop Entry]
Type=Application
Name=MCL
GenericName=Minecraft Launcher
Comment=Minecraft: Java Edition launcher (GUI)
Exec=mcl gui
Icon=mcl
Terminal=false
Categories=Game;
Keywords=minecraft;launcher;mcl;mods;
StartupWMClass=mcl
"""


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def desktop_path() -> Path:
    return _data_home() / "applications" / "mcl.desktop"


def icon_path() -> Path:
    return _data_home() / "icons" / "hicolor" / "256x256" / "apps" / "mcl.png"


def _refresh() -> None:
    apps = desktop_path().parent
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(apps)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    icon_root = _data_home() / "icons" / "hicolor"
    if shutil.which("gtk-update-icon-cache") and icon_root.exists():
        subprocess.run(["gtk-update-icon-cache", "-f", "-t", str(icon_root)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install() -> tuple[Path, Path]:
    if sys.platform != "linux":
        raise RuntimeError("桌面启动项只支持 Linux；Windows/macOS 用安装包或 mclw")
    entry = desktop_path()
    icon = icon_path()
    entry.parent.mkdir(parents=True, exist_ok=True)
    icon.parent.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent / "assets" / "mcl.png"
    if source.exists():
        shutil.copy2(source, icon)
    command = shutil.which("mcl") or "mcl"
    entry.write_text(ENTRY.replace("Exec=mcl gui", f"Exec={command} gui"), encoding="utf-8")
    entry.chmod(0o644)
    _refresh()
    return entry, icon


def ensure() -> bool:
    """首次打开 GUI 时静默补桌面项；已存在就不动。"""
    if sys.platform != "linux":
        return False
    if desktop_path().exists():
        if not icon_path().exists():
            try:
                install()
            except OSError:
                pass
        return False
    try:
        install()
        return True
    except OSError:
        return False


def remove() -> bool:
    removed = False
    for path in (desktop_path(), icon_path()):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    if removed:
        _refresh()
    return removed
