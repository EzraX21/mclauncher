"""跨平台：配置/缓存目录、打开文件管理器、系统 Java 位置。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def system() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def config_dir() -> Path:
    if system() == "windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "mclauncher"
    if system() == "macos":
        return Path.home() / "Library" / "Application Support" / "mclauncher"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "mclauncher"


def cache_dir() -> Path:
    if system() == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "mclauncher" / "cache"
    if system() == "macos":
        return Path.home() / "Library" / "Caches" / "mclauncher"
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "mclauncher"


def data_dir() -> Path:
    if system() == "windows":
        return Path(os.environ.get("APPDATA", Path.home())) / "mclauncher"
    if system() == "macos":
        return Path.home() / "Library" / "Application Support" / "mclauncher"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mclauncher"


def open_in_file_manager(path: Path) -> bool:
    """在文件管理器里打开目录；成功返回 True。"""
    path = str(path)
    try:
        if system() == "windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif system() == "macos":
            subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def java_candidates() -> list[Path]:
    """各平台常见的 Java 安装位置（PATH / JAVA_HOME 由 java.py 单独处理）。"""
    found: list[Path] = []
    if system() == "windows":
        patterns = [
            r"C:\Program Files\Java",
            r"C:\Program Files\Eclipse Adoptium",
            r"C:\Program Files\Microsoft",
            r"C:\Program Files\BellSoft",
            r"C:\Program Files\Zulu",
        ]
        for pattern in patterns:
            root = Path(pattern)
            if root.exists():
                found.extend(root.glob("*/bin/java.exe"))
    elif system() == "macos":
        home = Path("/usr/libexec/java_home")
        if home.exists():
            try:
                output = subprocess.run([str(home)], capture_output=True, text=True, timeout=10)
                if output.returncode == 0 and output.stdout.strip():
                    found.append(Path(output.stdout.strip()) / "bin" / "java")
            except (OSError, subprocess.SubprocessError):
                pass
        found.extend(Path("/Library/Java/JavaVirtualMachines").glob("*/Contents/Home/bin/java"))
    else:
        found.extend(Path("/usr/lib/jvm").glob("*/bin/java") if Path("/usr/lib/jvm").exists() else [])
        found.extend([Path("/usr/bin/java"), Path("/usr/local/bin/java")])
    return found
