"""启动图形界面：本地 HTTP 服务 + Electron（可选）或浏览器。"""

from __future__ import annotations

import os
import subprocess
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


def run_gui(args, ui: UI, cfg: Config) -> int:
    httpd, url = serve(cfg, args.port)
    ui.note(f"界面地址：{url}")
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
    env = dict(os.environ, MCLAUNCHER_GUI_URL=url)
    ui.note("启动 Electron 窗口 …")
    process = subprocess.Popen([str(binary), str(gui_dir)], env=env)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 130
    finally:
        httpd.shutdown()
