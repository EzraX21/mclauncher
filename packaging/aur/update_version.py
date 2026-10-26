#!/usr/bin/env python3
"""更新 AUR 的 PKGBUILD/.SRCINFO 版本，可选重算源码 sha256。

用法：
    update_version.py 2.3.1            # 只改版本
    update_version.py 2.3.1 --checksum # 顺便下载 GitHub 源码包算 sha256
"""

from __future__ import annotations

import hashlib
import re
import sys
import urllib.request
from pathlib import Path

here = Path(__file__).resolve().parent
args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
version = args[0].lstrip("v") if args else ""
if not version:
    raise SystemExit("用法: update_version.py <version> [--checksum]")

pkgbuild = here / "PKGBUILD"
text = pkgbuild.read_text(encoding="utf-8")
text = re.sub(r"^pkgver=.*$", f"pkgver={version}", text, flags=re.MULTILINE)
pkgbuild.write_text(text, encoding="utf-8")

checksum = None
if "--checksum" in sys.argv:
    match = re.search(r'^url="([^"]+)"', text, re.MULTILINE)
    if match:
        url = f"{match.group(1)}/archive/v{version}.tar.gz"
        print(f"计算 {url} 的 sha256 …")
        digest = hashlib.sha256()
        request = urllib.request.Request(url, headers={"User-Agent": "mclauncher-packaging"})
        with urllib.request.urlopen(request, timeout=120) as response:
            for chunk in iter(lambda: response.read(1 << 20), b""):
                digest.update(chunk)
        checksum = digest.hexdigest()
        text = re.sub(r"^sha256sums=\(.*\)$", f"sha256sums=('{checksum}')", text,
                      flags=re.MULTILINE)
        pkgbuild.write_text(text, encoding="utf-8")

srcinfo = here / ".SRCINFO"
info = srcinfo.read_text(encoding="utf-8")
info = re.sub(r"^(\tpkgver = ).*$", rf"\g<1>{version}", info, flags=re.MULTILINE)
url_match = re.search(r'^url="([^"]+)"', text, re.MULTILINE)
if url_match:
    source_url = f"{url_match.group(1)}/archive/v{version}.tar.gz"
    info = re.sub(r"^(\tsource = ).*$",
                  rf"\g<1>mclauncher-{version}.tar.gz::{source_url}", info, flags=re.MULTILINE)
if checksum:
    info = re.sub(r"^(\tsha256sums = ).*$", rf"\g<1>{checksum}", info, flags=re.MULTILINE)
srcinfo.write_text(info, encoding="utf-8")
print(f"PKGBUILD / .SRCINFO -> {version}" + (f"，sha256 {checksum}" if checksum else ""))
