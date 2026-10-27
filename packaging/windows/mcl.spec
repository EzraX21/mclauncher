# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas, binaries, hiddenimports = [], [], []
for package in ("textual", "rich", "questionary", "markdown_it", "mdit_py_plugins",
                "linkify_it", "pygments", "uc_micro", "webview", "clr_loader", "pythonnet"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden
    except Exception:
        pass

webui = os.path.join(ROOT, "mcl", "webui_dist")
if os.path.isdir(webui):
    datas.append((webui, "mcl/webui_dist"))

icon = os.path.join(ROOT, "gui", "assets", "mcl.ico")
if not os.path.isfile(icon):
    icon = None

a = Analysis(
    [os.path.join(ROOT, "packaging", "entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mcl",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=icon,
)

gui_a = Analysis(
    [os.path.join(ROOT, "packaging", "windows", "gui_entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["clr", "webview.platforms.winforms"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
gui_pyz = PYZ(gui_a.pure)
gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    gui_a.binaries,
    gui_a.datas,
    [],
    name="mclw",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)
