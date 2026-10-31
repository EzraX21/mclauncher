"""每个版本的启动覆盖项（内存、窗口、JVM/游戏参数）。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from .platforms import config_dir

FIELDS = ("memory_mb", "width", "height", "jvm_args", "game_args")


def _path() -> Path:
    return config_dir() / "version_options.json"


def load() -> dict:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get(version_id: str) -> dict:
    data = load().get(version_id)
    result = {field: None for field in FIELDS}
    if isinstance(data, dict):
        result.update({key: data.get(key) for key in FIELDS})
    result["jvm_args"] = result["jvm_args"] or ""
    result["game_args"] = result["game_args"] or ""
    return result


def _number(value, minimum: int, maximum: int, label: str) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} 必须是整数")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是整数") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} 需要在 {minimum} 到 {maximum} 之间")
    return number


def update(version_id: str, values: dict) -> dict:
    if not version_id or "/" in version_id or "\\" in version_id or version_id in (".", ".."):
        raise ValueError("版本名不合法")
    cleaned = {
        "memory_mb": _number(values.get("memory_mb"), 512, 65536, "内存"),
        "width": _number(values.get("width"), 320, 10000, "窗口宽度"),
        "height": _number(values.get("height"), 240, 10000, "窗口高度"),
        "jvm_args": str(values.get("jvm_args") or "").strip()[:4000],
        "game_args": str(values.get("game_args") or "").strip()[:4000],
    }
    data = load()
    data[version_id] = cleaned
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=".version-options-", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as handle_file:
            json.dump(data, handle_file, ensure_ascii=False, indent=2)
            handle_file.write("\n")
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return cleaned
