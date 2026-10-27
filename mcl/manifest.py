"""Mojang 官方 API：版本清单、版本 JSON、资源索引。"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional, Sequence

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
USER_AGENT = "mcl/1.2.0 (personal use)"


class ApiError(RuntimeError):
    """拉不到 Mojang 数据时抛出。"""


def fetch_json(url: str, retries: int = 3, timeout: int = 60) -> dict:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 网络异常种类太多，统一重试
            last = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise ApiError(f"无法访问 {url}：{last}")


@dataclass(frozen=True)
class VersionEntry:
    id: str
    type: str          # release / snapshot / old_beta / old_alpha
    release_time: str
    url: str

    @property
    def is_release(self) -> bool:
        return self.type == "release"


def fetch_json_any(urls: Sequence[str], retries: int = 2, timeout: int = 60) -> dict:
    """按顺序试多个地址（镜像 / 官方），全失败才抛错。"""
    last: Optional[Exception] = None
    for url in urls:
        try:
            return fetch_json(url, retries=retries, timeout=timeout)
        except ApiError as exc:
            last = exc
    raise ApiError(str(last) if last else "没有可用的下载源")


def fetch_text(url: str, retries: int = 3, timeout: int = 60) -> str:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise ApiError(f"无法访问 {url}：{last}")


def fetch_text_any(urls: Sequence[str], retries: int = 2, timeout: int = 60) -> str:
    last: Optional[Exception] = None
    for url in urls:
        try:
            return fetch_text(url, retries=retries, timeout=timeout)
        except ApiError as exc:
            last = exc
    raise ApiError(str(last) if last else "没有可用的下载源")


class Manifest:
    def __init__(self, raw: dict):
        self.raw = raw
        self.latest_release: str = raw["latest"]["release"]
        self.latest_snapshot: str = raw["latest"]["snapshot"]
        self.versions: list[VersionEntry] = [
            VersionEntry(
                id=item["id"],
                type=item.get("type", "release"),
                release_time=item.get("releaseTime", ""),
                url=item["url"],
            )
            for item in raw["versions"]
        ]

    @classmethod
    def load(cls, source: str = "official") -> "Manifest":
        from .sources import manifest_candidates

        return cls(fetch_json_any(manifest_candidates(source)))

    def resolve(self, name: str) -> VersionEntry:
        """支持 'latest' / 'latest-snapshot' 和具体版本号，找不到时给出候选。"""
        alias = {"latest": self.latest_release, "release": self.latest_release,
                 "snapshot": self.latest_snapshot, "latest-snapshot": self.latest_snapshot}
        wanted = alias.get(name.strip().lower(), name.strip())
        for entry in self.versions:
            if entry.id == wanted:
                return entry
        import difflib

        close = difflib.get_close_matches(wanted, [v.id for v in self.versions], n=3, cutoff=0.5)
        hint = f"，你是不是想找：{', '.join(close)}" if close else ""
        raise ApiError(f"官方清单里没有版本 “{wanted}”{hint}")

    def version_json(self, entry: VersionEntry) -> dict:
        data = fetch_json(entry.url)
        data.setdefault("id", entry.id)
        if data["id"] != entry.id:
            data["id"] = entry.id
        return data
