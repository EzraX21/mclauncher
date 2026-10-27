"""配置查看与修改。"""

from __future__ import annotations

from .config import Config
from .ui import UI

EDITABLE = {
    "game_dir": "游戏目录",
    "java_path": "Java 路径",
    "memory_mb": "内存（MB）",
    "username": "离线用户名",
    "isolate_versions": "版本隔离（true/false）",
    "jobs": "下载并发数",
    "download_source": "下载源（auto/official）",
    "curseforge_api_key": "CurseForge API key",
    "ms_client_id": "微软 Azure 应用 client id",
    "theme": "GUI 主题（light/dark/system）",
}


def show(ui: UI, cfg: Config) -> None:
    ui.title("当前配置")
    ui.kv("游戏目录", str(cfg.root()))
    ui.kv("Java", cfg.java_path or "（自动查找）")
    ui.kv("内存", f"{cfg.memory_mb} MB")
    ui.kv("用户名", cfg.username)
    ui.kv("版本隔离", "开" if cfg.isolate_versions else "关")
    ui.kv("并发", str(cfg.jobs))
    ui.kv("下载源", "BMCLAPI 优先" if cfg.download_source == "auto" else "仅官方（默认）")
    ui.kv("CurseForge", "已配置" if cfg.curseforge_api_key else "未配置（模组页可选 Modrinth）")
    ui.kv("微软登录", "已配置 client id" if cfg.ms_client_id else "未配置（可选）")
    ui.kv("主题", cfg.theme)
    ui.kv("上次版本", cfg.last_version or "—")


def _coerce(key: str, value: str):
    if key == "memory_mb" or key == "jobs":
        number = int(value)
        if key == "jobs" and not 1 <= number <= 32:
            raise ValueError("并发数要在 1-32 之间")
        if key == "memory_mb" and number < 512:
            raise ValueError("内存至少 512 MB")
        return number
    if key == "download_source":
        if value not in ("auto", "official"):
            raise ValueError("只能是 auto 或 official")
        return value
    if key == "theme":
        if value not in ("light", "dark", "system"):
            raise ValueError("只能是 light / dark / system")
        return value
    if key == "isolate_versions":
        if value.lower() not in ("true", "false", "1", "0", "on", "off", "开", "关"):
            raise ValueError("只能是 true / false")
        return value.lower() in ("true", "1", "on", "开")
    return value


def run(args, ui: UI, cfg: Config) -> int:
    if args.action == "show" or not args.key:
        show(ui, cfg)
        return 0

    if args.key not in EDITABLE:
        ui.error(f"不支持改 {args.key}，可改：{', '.join(EDITABLE)}")
        return 1
    if args.value is None:
        ui.error("缺少值")
        return 1
    try:
        value = _coerce(args.key, args.value)
    except ValueError as exc:
        ui.error(str(exc))
        return 1
    setattr(cfg, args.key, value)
    path = cfg.save()
    ui.ok(f"{EDITABLE[args.key]} -> {value}")
    ui.note(f"写入 {path}")
    return 0
