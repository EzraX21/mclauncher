"""平台识别与 version JSON 里的 rules 判定。

规则语义与官方启动器一致：
- 没有 rules → 允许；
- 有 rules → 从「不允许」开始，逐条判断，命中的规则把结果改成它的 action。
"""

from __future__ import annotations

import platform
import re
from typing import Iterable

OS_NAME = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}


def os_name() -> str:
    return OS_NAME.get(platform.system(), platform.system().lower())


def os_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    return "x86"


def _arch_matches(wanted: str) -> bool:
    """官方 rules 里 32 位写 x86；arm64 只匹配 arm64；其余按原样比。"""
    current = os_arch()
    if wanted == "x86":
        return current == "x86"
    return wanted == current


def rule_matches(rule: dict, features: dict, system: dict | None = None) -> bool:
    info = system or {}
    os_rule = rule.get("os") or {}
    if "name" in os_rule and os_rule["name"] != info.get("name", os_name()):
        return False
    if "arch" in os_rule and not _arch_matches(os_rule["arch"]):
        return False
    if "version" in os_rule:
        release = info.get("version", platform.release())
        try:
            if not re.search(os_rule["version"], release):
                return False
        except re.error:
            return False
    for key, wanted in (rule.get("features") or {}).items():
        if bool(features.get(key, False)) != bool(wanted):
            return False
    return True


def is_allowed(library: dict, features: dict, system: dict | None = None) -> bool:
    rules = library.get("rules")
    if not rules:
        return True
    allowed = False
    for rule in rules:
        if rule_matches(rule, features, system):
            allowed = rule.get("action") == "allow"
    return allowed


def dedupe(tasks: Iterable) -> list:
    """同一目标文件只保留一次（老版本里 artifact 与 classifier 会指向同一个 jar）。"""
    seen: set[str] = set()
    unique = []
    for task in tasks:
        key = str(task.dest)
        if key in seen:
            continue
        seen.add(key)
        unique.append(task)
    return unique
