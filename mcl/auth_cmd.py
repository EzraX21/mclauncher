"""mcl login / logout / account 子命令。"""

from __future__ import annotations

from . import auth
from .config import Config
from .ui import UI


def run_login(args, ui: UI, cfg: Config) -> int:
    client_id = getattr(args, "client_id", None) or cfg.ms_client_id
    if not client_id:
        ui.error("还没配置微软 client id")
        ui.note("先运行：mcl config set ms_client_id <你的 client id>")
        ui.note("注册方法见 README 的「微软登录」一节")
        return 2

    shown = {"done": False}

    def on_code(device: dict) -> None:
        shown["done"] = True
        ui.box("微软登录", [
            ("打开", device.get("verification_uri", "https://microsoft.com/devicelogin")),
            ("输入代码", device.get("user_code", "")),
            ("说明", "浏览器里登录拥有 Minecraft 的微软账号"),
        ])

    ui.note("正在向微软申请设备代码 …")
    try:
        account = auth.login(client_id, on_code=on_code, on_status=ui.note)
    except KeyboardInterrupt:
        ui.warn("已取消登录")
        return 130
    except auth.AuthError as exc:
        ui.error(str(exc))
        return 1

    cfg.ms_client_id = client_id
    cfg.save()
    ui.blank()
    ui.box("登录成功", [
        ("账号", account.name),
        ("UUID", account.uuid),
        ("有效期", f"{account.expires_in // 3600} 小时"),
    ])
    return 0


def run_logout(args, ui: UI, cfg: Config) -> int:
    if auth.load_account() is None:
        ui.note("当前没有登录")
        return 0
    auth.clear_account()
    ui.note("已退出微软账号，之后启动使用离线模式")
    return 0


def run_account(args, ui: UI, cfg: Config) -> int:
    account = auth.load_account()
    if account is None:
        ui.note("未登录（离线模式）")
        ui.note("登录：mcl login")
        return 1
    ui.box("当前账号", [
        ("账号", account.name),
        ("UUID", account.uuid),
        ("剩余", f"{account.expires_in // 60} 分钟"),
        ("Client ID", account.client_id or cfg.ms_client_id or "—"),
    ])
    return 0
