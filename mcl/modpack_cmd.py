"""mcl modpack info / install / export。"""

from __future__ import annotations

from pathlib import Path

from . import modpacks
from .config import Config
from .ui import UI


def run(args, ui: UI, cfg: Config) -> int:
    action = getattr(args, "action", None)
    if not action:
        ui.error("用法：mcl modpack info <文件> 或 mcl modpack install <文件>")
        return 2
    path = getattr(args, "file", None)
    if action == "info":
        info = modpacks.inspect(path)
        ui.box("整合包信息", [
            ("名称", info.name),
            ("版本", info.version or "—"),
            ("格式", info.format),
            ("Minecraft", info.minecraft or "—"),
            ("加载器", f"{info.loader} {info.loader_version}".strip()),
            ("文件数", str(len(info.files))),
            ("overrides", str(len(info.overrides) + len(info.client_overrides))),
        ])
        if info.needs_curseforge_key:
            ui.warn("CurseForge 整合包需要 API key")
        return 0
    if action == "export":
        version_id = (getattr(args, "version", None) or "").strip()
        if not version_id:
            ui.error("用法：mcl modpack export <版本> [-o 输出.mrpack] [--with-saves]")
            return 2
        output = getattr(args, "output", None)
        try:
            result = modpacks.export(
                cfg, version_id, dest=Path(output).expanduser() if output else None,
                name=getattr(args, "name", None),
                include_saves=bool(getattr(args, "with_saves", False)),
            )
        except modpacks.PackError as exc:
            ui.error(str(exc))
            return 1
        for warning in result["warnings"]:
            ui.warn(warning)
        ui.ok(f"已导出 {result['files']} 个文件")
        ui.box("整合包", [
            ("文件", result["path"]),
            ("名称", result["name"]),
            ("Minecraft", result["game"]),
            ("加载器", f"{result['loader']} {result['loader_version']}".strip()),
            ("大小", f"{result['size'] / 1048576:.1f} MB"),
        ])
        return 0
    if action == "install":
        try:
            version_id = modpacks.install(path, cfg, name=getattr(args, "name", None),
                                          on_log=ui.note)
        except modpacks.PackError as exc:
            ui.error(str(exc))
            return 1
        ui.ok(f"整合包已安装：{version_id}")
        ui.note(f"启动：mcl launch {version_id}")
        return 0
    ui.error(f"未知操作：{action}")
    return 2
