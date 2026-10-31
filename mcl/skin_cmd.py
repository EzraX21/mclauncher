"""mcl skin：离线自定义皮肤。"""

from __future__ import annotations

from pathlib import Path

from . import skin
from .config import Config
from .ui import UI


def run(args, ui: UI, cfg: Config) -> int:
    action = getattr(args, "action", "show")
    if action == "off":
        skin.clear()
        cfg.custom_skin = False
        cfg.save()
        ui.ok("已关闭自定义皮肤")
        return 0

    if action == "set":
        name = getattr(args, "file", None)
        if not name:
            ui.error("用法：mcl skin set <skin.png> [--model classic|slim]")
            return 2
        path = Path(name).expanduser()
        try:
            data = path.read_bytes()
            width, height = skin.validate(data)
        except OSError as exc:
            ui.error(f"读不了 {path}：{exc}")
            return 1
        except skin.SkinError as exc:
            ui.error(str(exc))
            return 1
        model = getattr(args, "model", None) or "classic"
        skin.save(data, model)
        cfg.custom_skin = True
        cfg.skin_model = model if model in ("classic", "slim") else "classic"
        cfg.save()
        ui.ok(f"皮肤已保存：{width}×{height}，{cfg.skin_model}，启动时自动应用")
        return 0

    state = "开启" if cfg.custom_skin else "关闭"
    ui.title("离线自定义皮肤")
    ui.kv("状态", state)
    ui.kv("模型", cfg.skin_model)
    ui.kv("文件", str(skin.skin_path()) if skin.skin_path().exists() else "未选择")
    ui.note("设置：mcl skin set skin.png --model classic")
    ui.note("关闭：mcl skin off")
    return 0
