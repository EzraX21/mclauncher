"""mcl resources 子命令。"""

from __future__ import annotations

from . import resources
from .config import Config
from .ui import UI


def run(args, ui: UI, cfg: Config) -> int:
    kind = args.kind
    version = getattr(args, "version", None) or cfg.last_version
    if not version:
        ui.error("先指定 --version，例如 --version 1.20.1")
        return 2
    action = args.action
    try:
        if action == "search":
            if not args.query:
                ui.error("搜索要带关键词")
                return 2
            hits = resources.search(kind, args.query, version, cfg.source)
            if not hits:
                ui.warn("没有搜到")
                return 1
            for hit in hits:
                ui.kv(hit["title"], f"{hit['slug']}  ·  {hit['downloads']:,} 次")
            return 0
        if action == "install":
            path = resources.install(kind, version, args.query or "", cfg)
            ui.ok(f"已安装 {path.name}")
            return 0
        if action == "list":
            items = resources.local(kind, cfg, version)
            if not items:
                ui.note("还没有安装")
                return 0
            for item in items:
                ui.kv(item["name"], f"{item['size'] / 1048576:.1f} MB")
            return 0
        if action == "remove":
            if resources.remove(kind, cfg, version, args.query or ""):
                ui.ok("已删除")
                return 0
            ui.error("找不到这个文件")
            return 1
    except resources.ResourceError as exc:
        ui.error(str(exc))
        return 1
    ui.error(f"未知操作：{action}")
    return 2
