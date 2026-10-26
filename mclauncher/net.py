"""下载与校验：单文件下载、批量并发、SHA-1 校验、断点续传。"""

from __future__ import annotations

import hashlib
import http.client
import os
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

USER_AGENT = "mclauncher/1.2.0 (personal use)"
CHUNK = 1 << 20

# 每个线程复用 HTTPS 连接：资源文件动辄几千个小文件，省掉每次的 TCP + TLS 握手
_local = threading.local()


def _pool() -> dict:
    pool = getattr(_local, "pool", None)
    if pool is None:
        pool = _local.pool = {}
    return pool


def _connection(url: str):
    parts = urllib.parse.urlsplit(url)
    key = (parts.scheme, parts.netloc)
    pool = _pool()
    connection = pool.get(key)
    if connection is None:
        factory = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        connection = factory(parts.netloc, timeout=60)
        pool[key] = connection
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return connection, path


def _drop(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    connection = _pool().pop((parts.scheme, parts.netloc), None)
    if connection is not None:
        try:
            connection.close()
        except OSError:
            pass


def _stream_keepalive(url: str, handle, cancel: Optional[threading.Event] = None) -> int:
    connection, path = _connection(url)
    connection.request("GET", path, headers={"User-Agent": USER_AGENT})
    response = connection.getresponse()
    if response.status != 200:
        _drop(url)
        raise http.client.HTTPException(f"HTTP {response.status}")
    total = 0
    while True:
        chunk = response.read(CHUNK)
        if not chunk:
            break
        handle.write(chunk)
        total += len(chunk)
    return total


def _proxied(url: str) -> bool:
    """走了代理就别用自建连接（那条路会绕过代理直连）。"""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    try:
        if urllib.request.proxy_bypass(host):
            return False
    except OSError:
        pass
    proxies = urllib.request.getproxies()
    return bool(proxies.get(parts.scheme) or proxies.get("all"))


def _stream_urllib(url: str, handle) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = 0
        while True:
            chunk = response.read(CHUNK)
            if not chunk:
                break
            handle.write(chunk)
            total += len(chunk)
        return total


class Cancelled(Exception):
    """用户点了取消。"""


class ProgressSink(Protocol):
    def add(self, nbytes: int) -> None: ...
    def tick(self) -> None: ...


@dataclass(frozen=True)
class DownloadTask:
    url: str
    dest: Path
    sha1: Optional[str] = None
    size: Optional[int] = None
    alternates: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.dest.name


@dataclass
class BatchResult:
    downloaded_files: int = 0
    downloaded_bytes: int = 0
    skipped_files: int = 0
    cancelled: bool = False
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_installed(task: DownloadTask, force: bool) -> bool:
    if force or not task.dest.exists():
        return False
    if task.sha1 is not None and sha1_file(task.dest) != task.sha1:
        return False
    if task.size is not None and task.dest.stat().st_size != task.size:
        return False
    if task.sha1 is None and task.size is None and task.dest.stat().st_size == 0:
        return False
    return True


def download(task: DownloadTask, retries: int = 3, force: bool = False, timeout: int = 60,
             cancel: Optional[threading.Event] = None) -> int:
    """下载单个文件，返回实际写入字节数；已存在且校验通过时返回 0。

    url 失败会依次尝试 alternates（镜像 / 官方互为备份）。
    """
    if cancel is not None and cancel.is_set():
        raise Cancelled("已取消")
    if _looks_installed(task, force):
        return 0

    task.dest.parent.mkdir(parents=True, exist_ok=True)
    temp = task.dest.with_name(task.dest.name + ".part")
    urls = list(dict.fromkeys([task.url, *task.alternates]))
    last_error: Optional[Exception] = None

    for attempt in range(1, max(1, retries) + 1):
        for url in urls:
            try:
                with open(temp, "wb") as handle:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled("已取消")
                    if _proxied(url):
                        # 有代理时交给 urllib（它会读 HTTPS_PROXY / https_proxy）
                        _stream_urllib(url, handle, cancel)
                    else:
                        try:
                            _stream_keepalive(url, handle, cancel)
                        except Cancelled:
                            raise
                        except Exception:  # noqa: BLE001 - 连接复用失败就退回一次性请求
                            handle.seek(0)
                            handle.truncate(0)
                            _stream_urllib(url, handle, cancel)
                if task.sha1 is not None and sha1_file(temp) != task.sha1:
                    raise ValueError("SHA-1 校验不通过")
                if task.size is not None and temp.stat().st_size != task.size:
                    raise ValueError("文件大小不符")
                os.replace(temp, task.dest)
                return task.dest.stat().st_size
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        if attempt < retries:
            time.sleep(1.5 * attempt)

    temp.unlink(missing_ok=True)
    raise RuntimeError(f"{task.url} 失败：{last_error}")


def run_tasks(
    tasks: list[DownloadTask],
    jobs: int = 8,
    retries: int = 3,
    force: bool = False,
    progress: Optional[ProgressSink] = None,
    cancel: Optional[threading.Event] = None,
) -> BatchResult:
    result = BatchResult()
    if not tasks:
        return result

    def work(task: DownloadTask) -> int:
        return download(task, retries=retries, force=force, cancel=cancel)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(work, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                written = future.result()
            except Cancelled:
                result.cancelled = True
                if progress:
                    progress.tick()
                continue
            except Exception as exc:  # noqa: BLE001
                result.errors.append(str(exc))
                if progress:
                    progress.tick()
                continue
            if written:
                result.downloaded_files += 1
                result.downloaded_bytes += written
                if progress:
                    progress.add(written)
            else:
                result.skipped_files += 1
            if progress:
                progress.tick()
    return result
