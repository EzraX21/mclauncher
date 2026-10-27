#!/usr/bin/env bash
# 把 PKGBUILD 推到 AUR。
# 前置：AUR 账号 + 已把 SSH 公钥加到 https://aur.archlinux.org/account
set -euo pipefail
cd "$(dirname "$0")"

VERSION="$(sed -n 's/^pkgver=//p' PKGBUILD)"
command -v makepkg >/dev/null || { echo "需要 makepkg（Arch）"; exit 1; }
makepkg --printsrcinfo > .SRCINFO

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --depth 1 "ssh://aur@aur.archlinux.org/mcl.git" "$TMP/aur"
cp PKGBUILD .SRCINFO "$TMP/aur/"
cd "$TMP/aur"
git add PKGBUILD .SRCINFO
git commit -m "mcl $VERSION"
git push
echo "已推送到 AUR：mcl $VERSION"
