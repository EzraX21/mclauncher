"""启动图形界面：本地 HTTP 服务 + Electron（可选）或浏览器。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from .config import Config
from .ui import UI
from .webui import serve


def _electron() -> tuple[Path, Path] | None:
    root = Path(__file__).resolve().parent.parent
    gui = root / "gui"
    binary = gui / "node_modules" / ".bin" / "electron"
    if binary.exists() and (gui / "dist" / "main.cjs").exists():
        return binary, gui
    return None


def _native_window(url: str) -> bool:
    """用 pywebview 开一个真正的桌面窗口（GTK/WebKit、WebView2、WKWebView）。"""
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.create_window("MCL · mclauncher", url, width=1180, height=760,
                              min_size=(900, 600), background_color="#f5f6f8")
        webview.start()
        return True
    except Exception:  # noqa: BLE001 - 没有可用的 webview 后端就交给后面的兜底
        return False


def _display_available() -> bool:
    if os.name == "nt" or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def run_default(ui: UI, cfg: Config) -> bool:
    """无参数启动：优先开原生窗口；没有后端/没有显示就返回 False，让调用方退回 TUI。"""
    if not _display_available():
        return False
    httpd, url = serve(cfg)
    ui.note(f"界面地址：{url}")
    try:
        ui.note("打开主窗口 …")
        return _native_window(url)
    finally:
        httpd.shutdown()


def run_gui(args, ui: UI, cfg: Config) -> int:
    httpd, url = serve(cfg, args.port)
    ui.note(f"界面地址：{url}")

    if not args.web and not getattr(args, "electron", False):
        ui.note("打开原生窗口 …")
        if _native_window(url):
            httpd.shutdown()
            return 0
        ui.warn("没有可用的原生窗口后端，尝试 Electron / 浏览器")

    electron = None if args.web else _electron()
    if electron is None:
        if not getattr(args, "no_browser", False):
            import webbrowser

            webbrowser.open(url)
            ui.note("已在浏览器打开；Ctrl+C 退出")
        else:
            ui.note("服务已启动；Ctrl+C 退出")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            httpd.shutdown()
        return 0

    binary, gui_dir = electron
    env = dict(os.environ, MCL_GUI_URL=url)
    ui.note("启动 Electron 窗口 …")
    process = subprocess.Popen([str(binary), str(gui_dir)], env=env)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 130
    finally:
        httpd.shutdown()
