"""mcl desktop install / remove。"""

from __future__ import annotations

from . import desktop
from .config import Config
from .ui import UI


def run(args, ui: UI, cfg: Config) -> int:
    action = getattr(args, "action", None) or "install"
    try:
        if action == "remove":
            ui.note("已移除桌面启动项" if desktop.remove() else "没有找到桌面启动项")
            return 0
        entry, icon = desktop.install()
    except RuntimeError as exc:
        ui.error(str(exc))
        return 1
    ui.ok("已安装桌面启动项")
    ui.kv("菜单项", str(entry))
    ui.kv("图标", str(icon))
    ui.note("如果 launcher 还搜不到，重新登录一次或重启 launcher 刷新缓存")
    return 0
