"""崩溃日志 / 最新日志的常见原因分析。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import Config


@dataclass
class Finding:
    title: str
    detail: str
    fix: str

    def as_dict(self) -> dict:
        return {"title": self.title, "detail": self.detail, "fix": self.fix}


JAVA_CLASS_VERSION = {45: 1, 46: 2, 47: 3, 48: 4, 49: 5, 50: 6, 51: 7, 52: 8,
                      53: 9, 54: 10, 55: 11, 56: 12, 57: 13, 58: 14, 59: 15,
                      60: 16, 61: 17, 62: 18, 63: 19, 64: 20, 65: 21, 66: 22,
                      67: 23, 68: 24, 69: 25}


def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[re.Match]:
    return re.search(pattern, text, flags)


def analyze(text: str) -> list[Finding]:
    findings: list[Finding] = []
    lowered = text.lower()

    if "unsupportedclassversionerror" in lowered or "class file version" in lowered:
        match = _search(r"class file version (\d+)", text)
        detail = match.group(1) if match else "未知"
        needed = JAVA_CLASS_VERSION.get(int(detail), "?") if detail.isdigit() else "?"
        findings.append(Finding(
            "Java 版本不对",
            f"某个模组/库是用 Java {needed} 编译的（class 版本 {detail}），当前 Java 版本太低。",
            "在设置里换对应主版本的 Java（1.12→8，1.17→16/17，1.21→21），MCL 会自动下载。",
        ))

    if "outofmemoryerror" in lowered:
        findings.append(Finding(
            "内存不够",
            "JVM 抛出 OutOfMemoryError，通常是内存给少了或模组太多。",
            "把内存调到 4096 MB 以上；大型整合包建议 6144–8192 MB，并确认系统内存够。",
        ))

    if "missing or unsupported mandatory dependencies" in lowered or "modresolutionexception" in lowered:
        missing = re.findall(r"Mod ID: '([^']+)'", text)
        names = re.findall(r"modid[: ]+([a-z0-9_\-]+)", text, re.IGNORECASE)
        detail = "、".join(dict.fromkeys(missing or names)) or "见日志里的依赖列表"
        findings.append(Finding(
            "缺少前置模组",
            f"加载器拒绝启动：缺少或不支持的前置：{detail}",
            "按日志里的 Mod ID 补装前置；用整合包安装通常会自动带依赖。",
        ))

    if "duplicatemodsfoundexception" in lowered or "duplicate mods" in lowered:
        findings.append(Finding(
            "模组重复",
            "同一个 Mod ID 出现了多个 jar（常见于整合包 + 手动又放了一份）。",
            "删掉 mods 里重复的旧版本，只保留一个。",
        ))

    if "mixin apply failed" in lowered or "mixin apply" in lowered and "failed" in lowered:
        mixins = re.findall(r"Mixin apply failed[^\n]*", text)
        detail = mixins[0][:160] if mixins else "某个 Mixin 注入失败"
        findings.append(Finding(
            "模组冲突（Mixin）",
            detail,
            "通常是两个模组改了同一个类；按日志里的类名/模组名禁用其中一个，或换兼容版本。",
        ))

    if "glfw error" in lowered or "failed to create window" in lowered or "pixel format not accelerated" in lowered:
        findings.append(Finding(
            "显卡/OpenGL 问题",
            "游戏创建窗口或 OpenGL 上下文失败。",
            "更新显卡驱动；Linux 下确认显卡加速正常；远程桌面/虚拟机可能不支持 OpenGL。",
        ))

    if "nosuchmethoderror" in lowered or "noclassdeffounderror" in lowered or "illegalaccesserror" in lowered:
        match = _search(r"(NoSuchMethodError|NoClassDefFoundError|IllegalAccessError)[^\n]*", text)
        findings.append(Finding(
            "模组/库版本不匹配",
            (match.group(0)[:180] if match else "运行时找不到类或方法"),
            "检查模组是否适配当前 Minecraft/加载器版本；删掉过期模组或补对应库。",
        ))

    if "accessdeniedexception" in lowered or "permission denied" in lowered:
        findings.append(Finding(
            "文件权限不足",
            "游戏无法读写某个文件或目录。",
            "确认游戏目录可写；Linux 下检查属主，Windows 下别装在受保护目录。",
        ))

    if not findings and "crashed" in lowered:
        findings.append(Finding(
            "游戏崩溃",
            "日志里有崩溃，但没有命中已知模式。",
            "查看下方日志末尾的 Caused by / Exception 行；带完整 crash-report 去 issue 里问。",
        ))
    return findings


def _latest(directory: Path, pattern: str) -> Optional[Path]:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def find_log(cfg: Config, version_id: Optional[str] = None) -> Optional[Path]:
    roots: list[Path] = []
    if version_id:
        roots.append(cfg.game_dir_for(version_id))
    roots.append(cfg.root())
    for root in roots:
        report = _latest(root / "crash-reports", "crash-*.txt")
        if report:
            return report
        latest = _latest(root / "logs", "latest.log")
        if latest:
            return latest
    return None


def analyze_version(cfg: Config, version_id: Optional[str] = None) -> dict:
    path = find_log(cfg, version_id)
    if path is None:
        return {"path": "", "findings": [], "tail": "",
                "message": "没找到崩溃报告或 latest.log，先启动一次游戏"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"path": str(path), "findings": [], "tail": "", "message": str(exc)}
    findings = analyze(text)
    tail = "\n".join(text.splitlines()[-40:])
    return {
        "path": str(path),
        "findings": [finding.as_dict() for finding in findings],
        "tail": tail,
        "message": "" if findings else "没有识别出常见崩溃原因，看日志末尾",
    }
