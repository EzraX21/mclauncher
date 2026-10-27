#!/usr/bin/env python3
"""交互式发版：问版本号，统一改版本文件和 README，再提交打 tag。

用法：
    python3 packaging/release.py                 # 交互问版本
    python3 packaging/release.py --version 3.7.0-beta.1 --commit
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pep440(version: str) -> str:
    return version.replace("-beta.", "b").replace("-rc.", "rc")


def current_version() -> str:
    match = re.search(r'__version__ = "([^"]+)"', (ROOT / "mcl" / "__init__.py").read_text())
    return match.group(1) if match else "0.0.0"


def set_version(version: str) -> None:
    tag_style = version
    pep = pep440(version)

    path = ROOT / "mcl" / "__init__.py"
    path.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{pep}"', path.read_text()),
                    encoding="utf-8")
    path = ROOT / "pyproject.toml"
    path.write_text(re.sub(r'^version = "[^"]+"', f'version = "{pep}"', path.read_text(),
                           flags=re.MULTILINE), encoding="utf-8")
    path = ROOT / "gui" / "package.json"
    path.write_text(re.sub(r'"version": "[^"]+"', f'"version": "{pep}"', path.read_text(),
                           count=1), encoding="utf-8")
    path = ROOT / "README.md"
    path.write_text(re.sub(r"v\d+\.\d+\.\d+(?:-[a-z]+\.\d+)? · Minecraft 启动器",
                           f"v{tag_style} · Minecraft 启动器", path.read_text()),
                    encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="3.7.0 / 3.7.0-beta.1 / 3.7.0-rc.1")
    parser.add_argument("--commit", action="store_true", help="提交并打 tag（不推送）")
    parser.add_argument("--yes", action="store_true", help="提交前不再确认")
    args = parser.parse_args()

    version = args.version
    if not version:
        print(f"当前版本：{current_version()}")
        version = input("发布版本（如 3.7.0 / 3.7.0-beta.1）: ").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:beta|rc)\.\d+)?", version):
        print("版本格式不对：只支持 X.Y.Z 或 X.Y.Z-beta.N / X.Y.Z-rc.N")
        return 2

    pep = pep440(version)
    set_version(version)
    print(f"\n版本：{version}（代码/PEP 440：{pep}）")
    print("已更新：mcl/__init__.py、pyproject.toml、gui/package.json、README")
    subprocess.run(["git", "diff", "--stat"], cwd=ROOT, check=False)

    if not args.commit:
        print("\n确认后提交：")
        print(f"  git add -A && git commit -m 'release: MCL {version}'")
        print(f"  git tag -a v{version} -m 'MCL {version}'")
        print(f"  git push origin main && git push origin v{version}")
        return 0

    if not args.yes:
        if input("提交并打 tag？[y/N] ").strip().lower() not in ("y", "yes"):
            print("已取消（版本文件已改，未提交）")
            return 1
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", f"release: MCL {version}"], cwd=ROOT, check=True)
    subprocess.run(["git", "tag", "-a", f"v{version}", "-m", f"MCL {version}"], cwd=ROOT, check=True)
    print(f"\n已提交并打 tag v{version}，推送：")
    print("  git push origin main && git push origin v" + version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
