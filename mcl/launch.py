"""启动：合并后的版本 -> 参数、类路径、natives -> 真正跑起 JVM。"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import shlex
import subprocess
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import __version__, sources, vsettings
from .config import Config
from .java import JavaRuntime
from .net import DownloadTask, run_tasks
from .rules import is_allowed, os_arch, os_name
from .versions import Resolved, maven_path

LAUNCHER_NAME = "mcl"


@dataclass
class LaunchCommand:
    argv: list[str] = field(default_factory=list)
    cwd: Path = Path(".")
    java: Optional[JavaRuntime] = None
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def pretty(self) -> str:
        return " ".join(self.argv)


def offline_uuid(username: str) -> str:
    digest = hashlib.md5(f"OfflinePlayer:{username}".encode("utf-8")).digest()
    raw = bytearray(digest)
    raw[6] = (raw[6] & 0x0F) | 0x30
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def library_path(root: Path, library: dict) -> Optional[Path]:
    artifact = (library.get("downloads") or {}).get("artifact")
    if artifact:
        return root / "libraries" / artifact["path"]
    if library.get("name") and library.get("url"):
        try:
            return root / "libraries" / maven_path(library["name"])
        except ValueError:
            return None
    return None


def library_url(library: dict) -> Optional[str]:
    artifact = (library.get("downloads") or {}).get("artifact")
    if artifact:
        return artifact["url"]
    if library.get("name") and library.get("url"):
        try:
            return library["url"].rstrip("/") + "/" + maven_path(library["name"])
        except ValueError:
            return None
    return None


def native_classifier(library: dict) -> Optional[str]:
    classifier = (library.get("natives") or {}).get(os_name())
    if not classifier:
        return None
    bits = "64" if os_arch() in ("x86_64", "arm64") else "32"
    return classifier.replace("${arch}", bits)


def native_jar(library: dict, root: Path) -> Optional[Path]:
    classifier = native_classifier(library)
    if not classifier:
        return None
    entry = ((library.get("downloads") or {}).get("classifiers") or {}).get(classifier)
    if entry:
        return root / "libraries" / entry["path"]
    if library.get("name") and library.get("url"):
        try:
            return root / "libraries" / maven_path(f"{library['name']}:{classifier}")
        except ValueError:
            return None
    return None


def collect_libraries(resolved: Resolved, root: Path, features: Optional[dict] = None):
    features = features or {}
    jars: list[Path] = []
    natives: list[Path] = []
    for library in resolved.libraries:
        if not is_allowed(library, features):
            continue
        path = library_path(root, library)
        if path is not None:
            jars.append(path)
        native = native_jar(library, root)
        if native is not None:
            natives.append(native)
    return jars, natives


def ensure_libraries(
    resolved: Resolved,
    root: Path,
    jobs: int = 8,
    on_phase: Optional[Callable[[str, int, int], object]] = None,
    source: str = "official",
) -> int:
    """把缺的库补上（Fabric/Quilt 的库只有 maven 坐标，也能按坐标推 URL）。"""
    tasks: list[DownloadTask] = []
    for library in resolved.libraries:
        if not is_allowed(library, {}):
            continue
        path = library_path(root, library)
        url = library_url(library)
        if path is not None and url and not path.exists():
            candidates = sources.library_candidates(url, source)
            tasks.append(DownloadTask(candidates[0], path, None, None, tuple(candidates[1:])))

        classifier = native_classifier(library)
        native_path = native_jar(library, root)
        if native_path is not None and not native_path.exists():
            entry = ((library.get("downloads") or {}).get("classifiers") or {}).get(classifier or "")
            if entry:
                candidates = sources.library_candidates(entry["url"], source)
                tasks.append(DownloadTask(candidates[0], native_path, entry.get("sha1"),
                                          entry.get("size"), tuple(candidates[1:])))
            elif library.get("url"):
                try:
                    name = f"{library['name']}:{classifier}"
                    url = library["url"].rstrip("/") + "/" + maven_path(name)
                    candidates = sources.library_candidates(url, source)
                    tasks.append(DownloadTask(candidates[0], native_path, None, None,
                                              tuple(candidates[1:])))
                except ValueError:
                    pass

    if not tasks:
        return 0
    sink = on_phase("缺失的库", len(tasks), 0) if on_phase else None
    batch = run_tasks(tasks, jobs=jobs, progress=sink)
    if batch.errors:
        raise RuntimeError(f"{len(batch.errors)} 个库下载失败：{batch.errors[0]}")
    return batch.downloaded_files


def prepare_natives(resolved: Resolved, root: Path) -> Path:
    target = root / "versions" / resolved.id / "natives"
    target.mkdir(parents=True, exist_ok=True)
    for library in resolved.libraries:
        if not is_allowed(library, {}):
            continue
        jar = native_jar(library, root)
        if jar is None or not jar.exists():
            continue
        excludes = [item.get("pattern") for item in ((library.get("extract") or {}).get("exclude") or [])]
        try:
            with zipfile.ZipFile(jar) as archive:
                for member in archive.namelist():
                    if member.endswith("/") or member.startswith("META-INF/"):
                        continue
                    if any(fnmatch.fnmatch(member, pattern) for pattern in excludes if pattern):
                        continue
                    destination = target / member
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(member))
        except zipfile.BadZipFile:
            continue
    return target


def _flatten(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    result: list[str] = []
    for item in value:
        result.extend(_flatten(item))
    return result


def build_arguments(entries: list, context: dict, features: dict, warnings: list[str]) -> list[str]:
    collected: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            collected.append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        if not is_allowed(entry, features):
            continue
        collected.extend(_flatten(entry.get("value", [])))

    substituted: list[str] = []
    for value in collected:
        for key, replacement in context.items():
            value = value.replace("${" + key + "}", str(replacement))
        if "${" in value:
            warnings.append(f"参数里有没替换的占位符：{value}")
        substituted.append(value)
    return substituted


def _extra_args(text: str, label: str, warnings: list[str]) -> list[str]:
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError as exc:
        warnings.append(f"{label}解析失败：{exc}")
        return []


def build_command(
    resolved: Resolved,
    cfg: Config,
    java: Optional[JavaRuntime],
    username: Optional[str] = None,
    features: Optional[dict] = None,
    memory_mb: Optional[int] = None,
    account=None,
) -> LaunchCommand:
    features = features or {}
    username = account.name if account is not None else (username or cfg.username or "Player")
    account_uuid = account.uuid if account is not None else offline_uuid(username)
    access_token = account.access_token if account is not None else "0"
    user_type = "msa" if account is not None else "legacy"
    xuid = "0"
    options = vsettings.get(resolved.id)
    memory = int(memory_mb or options.get("memory_mb") or cfg.memory_mb or 2048)
    width = options.get("width") or cfg.width
    height = options.get("height") or cfg.height
    root = cfg.root()

    command = LaunchCommand(cwd=cfg.game_dir_for(resolved.id), java=java)
    natives_dir = root / "versions" / resolved.id / "natives"

    jars, _ = collect_libraries(resolved, root, features)
    classpath = [str(path) for path in jars]
    if resolved.client_jar.exists():
        classpath.append(str(resolved.client_jar))
    else:
        command.missing.append(str(resolved.client_jar))
    for path in jars:
        if not path.exists():
            command.missing.append(str(path))

    if resolved.assets_index:
        index_file = resolved.assets_dir / "indexes" / f"{resolved.assets_index}.json"
        if not index_file.exists():
            command.warnings.append(f"缺少资源索引 {index_file}，游戏里可能没有音效和语言文件")

    context = {
        "auth_player_name": username,
        "auth_uuid": account_uuid,
        "auth_access_token": access_token,
        "auth_session": access_token,
        "clientid": "0",
        "auth_xuid": xuid,
        "user_type": user_type,
        "version_name": resolved.id,
        "version_type": resolved.version_type,
        "game_directory": str(command.cwd),
        "assets_root": str(resolved.assets_dir),
        "assets_index_name": resolved.assets_index or "legacy",
        "natives_directory": str(natives_dir),
        "launcher_name": LAUNCHER_NAME,
        "launcher_version": __version__,
        "classpath": os.pathsep.join(classpath),
        "classpath_separator": os.pathsep,
        "library_directory": str(root / "libraries"),
        "user_properties": "{}",
        "resolution_width": str(width),
        "resolution_height": str(height),
    }

    executable = str(java.path) if java else "java"
    if java is None:
        command.warnings.append("没有找到 Java，下面用占位符 java 打印命令")

    argv = [executable]
    if memory:
        argv += [f"-Xms{min(memory, 512)}M", f"-Xmx{memory}M"]
    argv += [
        "-Dfile.encoding=UTF-8",
        f"-Dminecraft.launcher.brand={LAUNCHER_NAME}",
        f"-Dminecraft.launcher.version={__version__}",
    ]

    argv += _extra_args(options.get("jvm_args") or "", "JVM 参数", command.warnings)
    arguments = resolved.data.get("arguments") or {}
    jvm_entries = arguments.get("jvm") or []
    if not jvm_entries:
        jvm_entries = ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"]
    jvm_args = build_arguments(jvm_entries, context, features, command.warnings)

    log_config = resolved.log_config
    if log_config:
        config_path = resolved.assets_dir / "log_configs" / log_config["id"]
        if config_path.exists():
            jvm_args.insert(0, f"-Dlog4j.configurationFile={config_path}")
        else:
            command.warnings.append(f"缺少日志配置 {config_path}")

    argv += jvm_args

    if not resolved.main_class:
        raise RuntimeError(f"{resolved.id} 没有 mainClass，版本 JSON 可能不完整")
    argv.append(resolved.main_class)

    game_entries = arguments.get("game") or []
    if game_entries:
        argv += build_arguments(game_entries, context, features, command.warnings)
    else:
        legacy = resolved.data.get("minecraftArguments", "")
        argv += build_arguments(legacy.split() if legacy else [], context, features, command.warnings)

    argv += _extra_args(options.get("game_args") or "", "游戏参数", command.warnings)

    if java is not None and resolved.java_major and java.major != resolved.java_major:
        command.warnings.append(
            f"这个版本要求 Java {resolved.java_major}，当前是 Java {java.major}，可能不兼容"
        )

    deduped: list[str] = []
    seen: set[str] = set()
    for argument in argv:
        if argument.startswith(("-D", "-Xms", "-Xmx")):
            if argument in seen:
                continue
            seen.add(argument)
        deduped.append(argument)

    command.argv = deduped
    return command


def spawn(command: LaunchCommand) -> subprocess.Popen:
    """TUI 用：stdin/stdout 都丢掉，别把游戏输出糊到界面上。"""
    command.cwd.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        command.argv,
        cwd=str(command.cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait(process: subprocess.Popen) -> int:
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            return process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return 130


def run(command: LaunchCommand) -> int:
    command.cwd.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(command.argv, cwd=str(command.cwd), env=dict(os.environ))
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            return process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return 130
