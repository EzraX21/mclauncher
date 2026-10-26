#!/usr/bin/env python3
"""把 PKGBUILD/.SRCINFO 里的版本改掉（CI 用，不需要 makepkg）。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
version = sys.argv[1].lstrip("v")

pkgbuild = here / "PKGBUILD"
text = pkgbuild.read_text(encoding="utf-8")
text = re.sub(r"^pkgver=.*$", f"pkgver={version}", text, flags=re.MULTILINE)
pkgbuild.write_text(text, encoding="utf-8")

srcinfo = here / ".SRCINFO"
info = srcinfo.read_text(encoding="utf-8")
info = re.sub(r"^(\tpkgver = ).*$", rf"\g<1>{version}", info, flags=re.MULTILINE)
srcinfo.write_text(info, encoding="utf-8")
print(f"PKGBUILD / .SRCINFO -> {version}")
