# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas, binaries, hiddenimports = [], [], []
for package in ("textual", "rich", "questionary", "markdown_it", "mdit_py_plugins",
                "linkify_it", "pygments", "uc_micro"):
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
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="mcl", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="mcl-cli")
