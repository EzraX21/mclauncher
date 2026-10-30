"""Java 运行时：探测已装的 Java，必要时从 Mojang 官方下载一份。"""

from __future__ import annotations

import lzma
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import platforms, sources
from .config import Config
from .manifest import fetch_json_any
from .net import DownloadTask, run_tasks

RUNTIME_INDEX = "https://launchermeta.mojang.com/v1/products/java-runtime/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"
_VERSION_RE = re.compile(r'version "([^"]+)"')
_COMPONENTS = {
    8: "jre-legacy",
    16: "java-runtime-alpha",
    17: "java-runtime-beta",
    21: "java-runtime-delta",
    25: "java-runtime-epsilon",
}


@dataclass(frozen=True)
class JavaRuntime:
    path: Path
    major: int
    version: str
    label: str = ""

    @property
    def display(self) -> str:
        return f"Java {self.major} ({self.version})"


def parse_version(text: str) -> Optional[tuple[str, int]]:
    match = _VERSION_RE.search(text)
    if not match:
        return None
    version = match.group(1)
    parts = re.split(r"[._+-]", version)
    try:
        if parts[0] == "1" and len(parts) > 1:
            major = int(parts[1])
        else:
            major = int(parts[0])
    except (ValueError, IndexError):
        return None
    return version, major


def probe(path: Path, timeout: int = 15) -> Optional[JavaRuntime]:
    if not path.exists():
        return None
    try:
        completed = subprocess.run(
            [str(path), "-version"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    parsed = parse_version((completed.stderr or "") + (completed.stdout or ""))
    if not parsed:
        return None
    version, major = parsed
    return JavaRuntime(path=path, major=major, version=version)


def mojang_runtimes(root: Path) -> list[Path]:
    base = root / "runtime"
    if not base.exists():
        return []
    found = []
    for candidate in base.glob("*/**/bin/java*"):
        if candidate.is_file():
            found.append(candidate)
    return found


def candidates(cfg: Config) -> list[Path]:
    paths: list[Path] = []
    configured = cfg.java()
    if configured:
        paths.append(configured)
    home = os.environ.get("JAVA_HOME")
    if home:
        name = "java.exe" if os.name == "nt" else "java"
        paths.append(Path(home) / "bin" / name)
    which = shutil.which("java")
    if which:
        paths.append(Path(which))
    paths.extend(mojang_runtimes(cfg.root()))
    paths.extend(platforms.java_candidates())
    return paths


def find_all(cfg: Config) -> list[JavaRuntime]:
    seen: set[str] = set()
    runtimes: list[JavaRuntime] = []
    for path in candidates(cfg):
        try:
            real = str(path.resolve())
        except OSError:
            continue
        if real in seen:
            continue
        seen.add(real)
        runtime = probe(path)
        if runtime:
            runtimes.append(runtime)
    return sorted(runtimes, key=lambda runtime: runtime.major)


def pick(runtimes: Iterable[JavaRuntime], required: Optional[int]) -> Optional[JavaRuntime]:
    """优先精确匹配需要的版本，其次选不小于要求的最低版本。"""
    runtimes = list(runtimes)
    if not runtimes:
        return None
    if required is None:
        return runtimes[-1]
    exact = [runtime for runtime in runtimes if runtime.major == required]
    if exact:
        return exact[0]
    bigger = [runtime for runtime in runtimes if runtime.major > required]
    if bigger:
        return min(bigger, key=lambda runtime: runtime.major)
    return max(runtimes, key=lambda runtime: runtime.major)


def pick_exact(runtimes: Iterable[JavaRuntime], required: int) -> Optional[JavaRuntime]:
    """只要主版本号完全一致的 Java（老版本不能用新 Java 凑合）。"""
    return next((runtime for runtime in runtimes if runtime.major == required), None)


def ensure_java(cfg: Config, required: Optional[int],
                on_phase: Optional[Callable[[str, int, int], object]] = None,
                note: Optional[Callable[[str], None]] = None,
                source: Optional[str] = None) -> JavaRuntime:
    """挑主版本号匹配的 Java；没有就下对应的 Mojang 运行时。

    不会拿 Java 21 去启动要求 Java 8 的版本——老版本会直接崩。
    """
    runtimes = find_all(cfg)
    if required is None:
        if runtimes:
            return max(runtimes, key=lambda runtime: runtime.major)
        required = 21
    else:
        exact = pick_exact(runtimes, required)
        if exact is not None:
            return exact

    component = component_for(required)
    if note:
        note(f"缺少 Java {required}，正在从 Mojang 下载 {component} …")
    try:
        path = install_runtime(component, cfg.root(), jobs=cfg.jobs, on_phase=on_phase,
                               source=source or cfg.source)
    except Exception as exc:  # noqa: BLE001 - 下载失败时退回最接近的版本并提示
        fallback = pick(runtimes, required)
        if fallback is not None and (required is None or fallback.major >= required):
            if note:
                note(f"下载 Java {required} 失败（{exc}），暂用 Java {fallback.major}，可能不兼容")
            return fallback
        raise

    runtime = probe(path)
    if runtime is None:
        raise RuntimeError(f"下载了 {component}，但 {path} 跑不起来")
    return runtime


def runtime_platform() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        if machine in ("arm64", "aarch64"):
            return "windows-arm64"
        return "windows-x64" if platform.architecture()[0] == "64bit" else "windows-x86"
    if system == "Darwin":
        return "mac-os-arm64" if machine in ("arm64", "aarch64") else "mac-os"
    if machine in ("i386", "i686", "x86"):
        return "linux-i386"
    return "linux"


def component_for(required: Optional[int], declared: Optional[str] = None) -> str:
    if declared and declared.startswith(("jre-", "java-runtime-")):
        return declared
    if required in _COMPONENTS:
        return _COMPONENTS[required]
    if required is None:
        return "java-runtime-delta"
    for major in sorted(_COMPONENTS):
        if major >= required:
            return _COMPONENTS[major]
    return _COMPONENTS[25]


def install_runtime(
    component: str,
    root: Path,
    jobs: int = 6,
    on_phase: Optional[Callable[[str, int, int], object]] = None,
    source: str = "official",
) -> Path:
    """下载并解包 Mojang 的 Java 运行时，返回 java 可执行文件路径。"""
    index = fetch_json_any(sources.java_index_candidates(source))
    plat = runtime_platform()
    entries = (index.get(plat) or {}).get(component) or []
    if not entries:
        raise RuntimeError(f"Mojang 没有为 {plat} 提供 {component}")
    entry = entries[0]
    version_name = entry["version"]["name"]
    manifest = fetch_json_any(sources.java_file_candidates(entry["manifest"]["url"], source))

    target = root / "runtime" / component / plat / version_name
    tasks: list[DownloadTask] = []
    compressed: list[tuple[Path, Path]] = []
    executables: list[str] = []

    for relative, info in manifest.get("files", {}).items():
        if info.get("type") == "directory":
            continue
        downloads = info.get("downloads") or {}
        raw = downloads.get("raw")
        destination = target / relative
        if raw:
            candidates = sources.java_file_candidates(raw["url"], source)
            tasks.append(DownloadTask(candidates[0], destination, raw.get("sha1"), raw.get("size"),
                                      tuple(candidates[1:])))
        else:
            lzma_entry = downloads.get("lzma")
            if lzma_entry:
                archive = target / (relative + ".lzma")
                candidates = sources.java_file_candidates(lzma_entry["url"], source)
                tasks.append(DownloadTask(candidates[0], archive, lzma_entry.get("sha1"),
                                          lzma_entry.get("size"), tuple(candidates[1:])))
                compressed.append((archive, destination))
        if info.get("executable"):
            executables.append(relative)

    total_bytes = sum(task.size or 0 for task in tasks)
    sink = on_phase(f"Java {version_name}", len(tasks), total_bytes) if on_phase else None
    batch = run_tasks(tasks, jobs=jobs, progress=sink)
    if batch.errors:
        raise RuntimeError(f"{len(batch.errors)} 个文件下载失败：{batch.errors[0]}")

    for archive, destination in compressed:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with lzma.open(archive) as source, open(destination, "wb") as handle:
            shutil.copyfileobj(source, handle)
        archive.unlink(missing_ok=True)

    for relative in executables:
        candidate = target / relative
        if candidate.exists():
            candidate.chmod(candidate.stat().st_mode | 0o755)

    java = target / "bin" / ("java.exe" if os.name == "nt" else "java")
    if not java.exists():
        raise RuntimeError(f"运行时装好了但找不到 {java}")
    java.chmod(java.stat().st_mode | 0o755)
    return java
