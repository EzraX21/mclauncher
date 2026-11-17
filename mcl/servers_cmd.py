"""mcl servers：服务器列表（读写游戏自己的 servers.dat）。"""

from __future__ import annotations

from . import servers
from .config import Config
from .ui import UI
from .versions import scan


def _default_version(cfg: Config) -> str:
    configured = (cfg.last_version or "").strip()
    installed = [item.id for item in scan(cfg.root())]
    if configured and configured in installed:
        return configured
    return installed[0] if installed else ""


def run(args, ui: UI, cfg: Config) -> int:
    version_id = (getattr(args, "version", None) or "").strip() or _default_version(cfg)
    if not version_id:
        ui.error("还没有装任何版本：先 mcl install <版本>")
        return 1

    action = getattr(args, "action", "list") or "list"
    try:
        if action == "add":
            address = (getattr(args, "address", None) or "").strip()
            if not address:
                ui.error("用法：mcl servers add <名字> <地址>，例如 mcl servers add Hypixel mc.hypixel.net")
                return 2
            name = (getattr(args, "name", None) or "").strip() or address
            servers.add(cfg, version_id, name, address)
            ui.ok(f"已添加 {name}")
        elif action == "remove":
            index = getattr(args, "index", None)
            if index is None:
                ui.error("用法：mcl servers remove --index 0")
                return 2
            servers.remove(cfg, version_id, index)
            ui.ok(f"已删除第 {index} 个服务器")
        data = servers.listing(cfg, version_id)
    except servers.ServerError as exc:
        ui.error(str(exc))
        return 1

    items = data["servers"]
    ui.title(f"服务器列表 · {version_id}")
    ui.note(data["path"])
    if not items:
        ui.info("还没有服务器：mcl servers add <名字> <地址>")
        return 0

    statuses = servers.ping_servers(items) if getattr(args, "ping", False) else []
    rows = []
    for item, status in zip(items, statuses or [None] * len(items)):
        if status is None:
            extra = ""
        elif status["online"]:
            extra = f"{status['latency_ms']} ms · {status['players']['online']}/{status['players']['max']} 人"
        else:
            extra = "离线"
        rows.append((f"[{item['index']}] {item['name']}", f"{item['ip']}{'  ' + extra if extra else ''}"))
    ui.box("", rows)
    return 0
