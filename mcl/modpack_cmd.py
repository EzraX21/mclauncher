"""mcl modpack info / install。"""

from __future__ import annotations

from . import modpacks
from .config import Config
from .ui import UI


def run(args, ui: UI, cfg: Config) -> int:
    action = getattr(args, "action", None)
    if not action:
        ui.error("用法：mcl modpack info <文件> 或 mcl modpack install <文件>")
        return 2
    path = args.file
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
