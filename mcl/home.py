"""交互主菜单：把安装、版本、模组、启动、设置串起来。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from . import install_cmd, launch_cmd, loaders, mods_cmd, prompts, settings_cmd
from .config import Config
from .java import find_all, probe
from .ui import UI
from .versions import VersionError, resolve, scan

def _menu():
    """questionary 是可选依赖，菜单在真正用到时才构造。"""
    return [
        prompts.Choice(title="启动游戏", value="launch"),
        prompts.Choice(title="下载 / 安装游戏", value="install"),
        prompts.Choice(title="版本管理", value="versions"),
        prompts.Choice(title="模组管理", value="mods"),
        prompts.Choice(title="设置", value="settings"),
        prompts.Choice(title="退出", value="quit"),
    ]


def _open_path(path) -> None:
    print(f"  {path}")
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


def _install(ui: UI, cfg: Config) -> None:
    args = SimpleNamespace(
        target=None, directory=None, jobs=None, retries=3, assets=None,
        force=False, dry_run=False, yes=False, list=False,
    )
    if install_cmd.run(args, ui, cfg) == 0 and cfg.last_version:
        if prompts.confirm(ui, f"现在启动 {cfg.last_version}？", default=False):
            _launch(ui, cfg, cfg.last_version)


def _launch(ui: UI, cfg: Config, version_id: str | None = None) -> None:
    args = SimpleNamespace(version=version_id, java=None, username=None, memory=None,
                           dry_run=False, yes=False)
    launch_cmd.run_launch(args, ui, cfg)


def _versions(ui: UI, cfg: Config) -> None:
    installed = scan(cfg.root())
    if not installed:
        ui.note("还没有装任何版本。")
        return
    version_id = prompts.choose_installed(ui, installed, "选择版本")
    while True:
        action = prompts.select(ui, f"{version_id} 要做什么？", [
            prompts.Choice(title="启动", value="launch"),
            prompts.Choice(title="安装 Fabric 加载器", value="fabric"),
            prompts.Choice(title="安装 Quilt 加载器", value="quilt"),
            prompts.Choice(title="打开版本目录", value="open"),
            prompts.Choice(title="删除", value="delete"),
            prompts.Choice(title="返回", value="back"),
        ])
        if action == "back":
            return
        if action == "launch":
            _launch(ui, cfg, version_id)
            continue
        if action in ("fabric", "quilt"):
            resolved = resolve(cfg.root(), version_id)
            game = resolved.chain[0]
            new_id = prompts.spinner(
                ui, f"安装 {action} 到 {game}",
                lambda: loaders.install(action, game, cfg.root()),
            )
            ui.ok(f"已创建版本 {new_id}")
            version_id = new_id
            continue
        if action == "open":
            _open_path(cfg.version_dir(version_id))
            continue
        if action == "delete":
            if prompts.confirm(ui, f"确定删除 {version_id}？存档不会动，但版本文件会没", default=False):
                shutil.rmtree(cfg.version_dir(version_id), ignore_errors=True)
                ui.ok(f"已删除 {version_id}")
                return


def _mods(ui: UI, cfg: Config) -> None:
    installed = scan(cfg.root())
    if not installed:
        ui.note("还没有装任何版本。")
        return
    version_id = prompts.choose_installed(ui, installed, "给哪个版本管理模组？")
    while True:
        action = prompts.select(ui, f"{version_id} 的模组", [
            prompts.Choice(title="查看已装模组", value="list"),
            prompts.Choice(title="搜索并安装（Modrinth）", value="search"),
            prompts.Choice(title="启用 / 禁用", value="toggle"),
            prompts.Choice(title="删除", value="remove"),
            prompts.Choice(title="返回", value="back"),
        ])
        if action == "back":
            return
        base = SimpleNamespace(action=action, version=version_id, query=None,
                               project=None, loader=None, yes=False)
        if action == "search":
            base.query = prompts.text(ui, "搜索关键词", default="")
            if not base.query.strip():
                continue
        if action in ("toggle", "remove"):
            base.project = prompts.text(ui, "模组名（可部分匹配）", default="")
            if not base.project.strip():
                continue
        mods_cmd.run(base, ui, cfg)


def _settings(ui: UI, cfg: Config) -> None:
    while True:
        action = prompts.select(ui, "设置", [
            prompts.Choice(title="查看当前配置", value="show"),
            prompts.Choice(title="修改游戏目录", value="game_dir"),
            prompts.Choice(title="修改 Java 路径", value="java"),
            prompts.Choice(title="修改内存", value="memory"),
            prompts.Choice(title="修改用户名", value="username"),
            prompts.Choice(title="切换版本隔离", value="isolate"),
            prompts.Choice(title="切换下载源", value="source"),
            prompts.Choice(title="返回", value="back"),
        ])
        if action == "back":
            return
        if action == "show":
            settings_cmd.show(ui, cfg)
            continue
        if action == "game_dir":
            cfg.game_dir = str(prompts.choose_directory(ui, cfg.root(), hint=False))
        elif action == "java":
            runtimes = find_all(cfg)
            if runtimes:
                ui.title("已发现的 Java")
                for runtime in runtimes:
                    ui.info(f"{runtime.display:<26} {runtime.path}")
            value = prompts.text(ui, "Java 路径（留空 = 自动）", default="")
            if value.strip():
                runtime = probe(Path(value).expanduser())
                if runtime is None:
                    ui.error(f"{value} 不是可用的 Java")
                    continue
                cfg.java_path = str(runtime.path)
            else:
                cfg.java_path = None
        elif action == "memory":
            raw = prompts.text(ui, "内存（MB）", default=str(cfg.memory_mb),
                               validate=lambda value: value.isdigit() and 512 <= int(value) <= 65536
                               or "请输入 512-65536 的整数")
            cfg.memory_mb = int(raw)
        elif action == "username":
            cfg.username = prompts.text(ui, "离线用户名", default=cfg.username)
        elif action == "source":
            cfg.download_source = prompts.select(ui, "下载源", [
                prompts.Choice(title="BMCLAPI 镜像优先（国内快，PCL 同款）", value="auto"),
                prompts.Choice(title="仅官方源（慢但最正统）", value="official"),
                prompts.Choice(title="自定义镜像（BMCLAPI 兼容）", value="custom"),
            ])
            if cfg.download_source == "custom":
                cfg.mirror_url = prompts.text(
                    ui, "镜像 base URL", default=cfg.mirror_url or "https://").rstrip("/")
        elif action == "isolate":
            cfg.isolate_versions = prompts.confirm(
                ui, "每个版本独立存档/模组目录？", default=cfg.isolate_versions)
        cfg.save()
        ui.ok("已保存")


def run(ui: UI, cfg: Config) -> int:
    ui.title("mcl · 下载、管理、启动一条龙")
    ui.note(f"游戏目录：{cfg.root()}")
    while True:
        try:
            action = prompts.select(ui, "主菜单", _menu())
            if action == "quit":
                return 0
            if action == "launch":
                _launch(ui, cfg)
            elif action == "install":
                _install(ui, cfg)
            elif action == "versions":
                _versions(ui, cfg)
            elif action == "mods":
                _mods(ui, cfg)
            elif action == "settings":
                _settings(ui, cfg)
        except prompts.Cancelled:
            continue
        except (VersionError, RuntimeError, OSError) as exc:
            ui.error(str(exc))
        except KeyboardInterrupt:
            ui.blank()
            ui.warn("已中断。")
            return 130
