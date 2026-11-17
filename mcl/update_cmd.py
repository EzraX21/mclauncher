"""mcl update：检查有没有新版本（只查，不替换自己的二进制）。"""

from __future__ import annotations

from . import __version__, update
from .config import Config
from .ui import UI


def run(args, ui: UI, cfg: Config) -> int:
    ui.title("检查更新")
    ui.kv("当前版本", f"v{__version__}")
    try:
        data = update.check(__version__)
    except update.UpdateError as exc:
        ui.error(str(exc))
        ui.note("离线或者 GitHub 限流时查不到，不影响使用")
        return 1

    ui.kv("最新版本", data["latest"])
    if data["update_available"]:
        ui.warn(f"有新版本：{data['latest']}（当前 v{__version__}）")
        ui.note(f"下载：{data['page']}")
        for asset in data["assets"][:6]:
            ui.note(f"  {asset['name']}")
        return 0
    ui.ok("已经是最新版")
    return 0
