"""把版本 JSON 变成一份可执行的下载计划，并落地成 .minecraft 目录结构。"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .manifest import fetch_json
from .net import DownloadTask, ProgressSink, run_tasks
from . import sources
from .rules import dedupe, is_allowed, os_arch, os_name

ASSET_BASE = "https://resources.download.minecraft.net"


class PlanError(RuntimeError):
    """版本 JSON 不完整，没法生成计划。"""


@dataclass
class Plan:
    version_id: str
    root: Path
    version_json: dict
    version_tasks: list[DownloadTask] = field(default_factory=list)
    asset_tasks: list[DownloadTask] = field(default_factory=list)
    asset_index: Optional[dict] = None
    asset_index_id: Optional[str] = None
    legacy_mapping: list[tuple[str, Path]] = field(default_factory=list)

    @property
    def all_tasks(self) -> list[DownloadTask]:
        return self.version_tasks + self.asset_tasks

    @property
    def version_bytes(self) -> int:
        return sum(task.size or 0 for task in self.version_tasks)

    @property
    def asset_bytes(self) -> int:
        return sum(task.size or 0 for task in self.asset_tasks)

    @property
    def total_bytes(self) -> int:
        return self.version_bytes + self.asset_bytes

    @property
    def total_files(self) -> int:
        return len(self.all_tasks)

    @property
    def java_major(self) -> Optional[int]:
        return (self.version_json.get("javaVersion") or {}).get("majorVersion")


@dataclass
class InstallResult:
    downloaded_files: int = 0
    downloaded_bytes: int = 0
    skipped_files: int = 0
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _task(url: str, dest: Path, sha1, size, candidates: list[str]) -> DownloadTask:
    urls = candidates or [url]
    return DownloadTask(urls[0], dest, sha1, size, tuple(urls[1:]))


def _library_tasks(library: dict, root: Path, features: dict, source: str) -> list[DownloadTask]:
    downloads = library.get("downloads") or {}
    tasks: list[DownloadTask] = []

    artifact = downloads.get("artifact")
    if artifact:
        tasks.append(_task(
            artifact["url"],
            root / "libraries" / artifact["path"],
            artifact.get("sha1"),
            artifact.get("size"),
            sources.library_candidates(artifact["url"], source),
        ))

    # 旧格式（1.5 及更早）：natives 放在 classifiers 里
    classifier = (library.get("natives") or {}).get(os_name())
    if classifier:
        classifier = classifier.replace("${arch}", "64" if os_arch() in ("x86_64", "arm64") else "32")
        entry = (downloads.get("classifiers") or {}).get(classifier)
        if entry:
            tasks.append(_task(
                entry["url"],
                root / "libraries" / entry["path"],
                entry.get("sha1"),
                entry.get("size"),
                sources.library_candidates(entry["url"], source),
            ))
    return tasks


def build_plan(
    version_json: dict,
    root: Path,
    with_assets: bool = True,
    features: Optional[dict] = None,
    system: Optional[dict] = None,
    index_loader: Callable[[str], dict] = fetch_json,
    source: str = "official",
) -> Plan:
    version_id = version_json["id"]
    root = Path(root).expanduser()
    features = features or {}
    system = system or {}

    client = (version_json.get("downloads") or {}).get("client")
    if not client:
        raise PlanError(f"版本 {version_id} 的元数据里没有 client 下载项")

    plan = Plan(version_id=version_id, root=root, version_json=version_json)
    plan.version_tasks.append(_task(
        client["url"],
        root / "versions" / version_id / f"{version_id}.jar",
        client.get("sha1"),
        client.get("size"),
        sources.meta_candidates(client["url"], source),
    ))

    for library in version_json.get("libraries", []):
        if is_allowed(library, features, system):
            plan.version_tasks.extend(_library_tasks(library, root, features, source))

    log_config = ((version_json.get("logging") or {}).get("client") or {}).get("file")
    if log_config:
        plan.version_tasks.append(_task(
            log_config["url"],
            root / "assets" / "log_configs" / log_config["id"],
            log_config.get("sha1"),
            log_config.get("size"),
            sources.meta_candidates(log_config["url"], source),
        ))

    plan.version_tasks = dedupe(plan.version_tasks)

    asset_index_meta = version_json.get("assetIndex")
    if with_assets and asset_index_meta:
        index = index_loader(asset_index_meta["url"])
        plan.asset_index = index
        plan.asset_index_id = asset_index_meta["id"]
        virtual = bool(index.get("virtual")) or bool(index.get("map_to_resources"))
        tasks = []
        for name, obj in (index.get("objects") or {}).items():
            digest = obj["hash"]
            destination = root / "assets" / "objects" / digest[:2] / digest
            url = f"{ASSET_BASE}/{digest[:2]}/{digest}"
            tasks.append(_task(
                url,
                destination,
                digest,
                obj.get("size"),
                sources.asset_candidates(url, source),
            ))
            if virtual:
                plan.legacy_mapping.append((name, destination))
        plan.asset_tasks = dedupe(tasks)

    return plan


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _materialize(mapping: list[tuple[str, Path]], index: dict, index_id: str, root: Path) -> int:
    """把 pre-1.6 的虚拟资源铺到游戏会去找的位置（硬链接，省空间）。"""
    base = root / "resources" if index.get("map_to_resources") else root / "assets" / "virtual" / index_id
    made = 0
    for name, source in mapping:
        destination = base / name
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except OSError:
            shutil.copyfile(source, destination)
        made += 1
    return made


def execute(
    plan: Plan,
    jobs: int = 8,
    retries: int = 3,
    force: bool = False,
    on_phase: Optional[Callable[[str, int, int], Optional[ProgressSink]]] = None,
    on_note: Optional[Callable[[str], None]] = None,
    cancel=None,
) -> InstallResult:
    note = on_note or (lambda _message: None)
    result = InstallResult()

    version_dir = plan.root / "versions" / plan.version_id
    _write_json(version_dir / f"{plan.version_id}.json", plan.version_json)
    note(f"版本描述：versions/{plan.version_id}/{plan.version_id}.json")

    phases: list[tuple[str, list[DownloadTask], int]] = [("版本文件", plan.version_tasks, plan.version_bytes)]
    if plan.asset_index is not None and plan.asset_index_id is not None:
        _write_json(plan.root / "assets" / "indexes" / f"{plan.asset_index_id}.json", plan.asset_index)
        note(f"资源索引：assets/indexes/{plan.asset_index_id}.json")
        phases.append(("资源文件", plan.asset_tasks, plan.asset_bytes))

    for label, tasks, total_bytes in phases:
        sink = on_phase(label, len(tasks), total_bytes) if on_phase else None
        batch = run_tasks(tasks, jobs=jobs, retries=retries, force=force, progress=sink,
                          cancel=cancel)
        result.downloaded_files += batch.downloaded_files
        result.downloaded_bytes += batch.downloaded_bytes
        result.skipped_files += batch.skipped_files
        result.errors.extend(batch.errors)
        if batch.cancelled:
            result.cancelled = True
            note("已取消：已下载的文件保留，重跑会续传")
            break

    if plan.asset_index is not None and plan.legacy_mapping:
        made = _materialize(plan.legacy_mapping, plan.asset_index, plan.asset_index_id or "", plan.root)
        if made:
            note(f"老版本资源已铺开 {made} 个文件")

    return result
