"""检查有没有新版本。

只做「查 + 告诉用户」，不下载、不替换自己的二进制：换二进制要处理权限、
运行中的进程、各平台安装位置，那部分得单独验证，先不碰。
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable, Optional

REPO = "EzraX21/mclauncher"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.]?(alpha|a|beta|b|rc)\.?(\d+))?$", re.I)
# 同一主次修订号下：正式版 > rc > beta > alpha
_STAGES = {"": 3, "rc": 2, "beta": 1, "b": 1, "a": 0, "alpha": 0}


class UpdateError(RuntimeError):
    """查不到新版本信息（网络、限流、返回格式不对）。"""


def version_key(text: str) -> Optional[tuple[int, int, int, int]]:
    """把 `v3.14.0` / `3.14.0-beta.1` / `3.14.0b1` 变成可比较的元组。"""
    match = _VERSION_RE.match((text or "").strip())
    if not match:
        return None
    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
    stage = _STAGES.get((match.group(4) or "").lower(), 0)
    return (major, minor, patch, stage)


def is_newer(latest: str, current: str) -> bool:
    new_key, cur_key = version_key(latest), version_key(current)
    if new_key is None or cur_key is None:
        return False
    return new_key > cur_key


def _fetch_latest(timeout: float = 8.0) -> dict:
    request = urllib.request.Request(
        LATEST_API,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "mcl-update-check"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - 网络问题一律收成 UpdateError
        raise UpdateError(f"查不到最新版本：{exc}") from exc


def check(current: str, fetch: Optional[Callable[[], dict]] = None,
          timeout: float = 8.0) -> dict:
    """返回当前版本 / 最新版本 / 是否有更新。查不到就抛 UpdateError。"""
    payload = (fetch or (lambda: _fetch_latest(timeout)))()
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("GitHub 返回里没有 tag_name")
    assets = []
    for asset in payload.get("assets") or []:
        name = asset.get("name")
        if name:
            assets.append({"name": str(name), "size": asset.get("size") or 0,
                           "url": str(asset.get("browser_download_url") or "")})
    return {
        "current": current,
        "latest": tag,
        "update_available": is_newer(tag, current),
        "page": str(payload.get("html_url") or RELEASES_PAGE),
        "published": str(payload.get("published_at") or ""),
        "prerelease": bool(payload.get("prerelease", False)),
        "assets": assets,
    }
