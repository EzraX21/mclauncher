#!/usr/bin/env bash
# 构建 Linux 发行包：deb / rpm / Arch，外加 wheel、源码 tar.gz 和 zip。
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION="$(python3 - <<'PY'
import re, pathlib
text = pathlib.Path("mclauncher/__init__.py").read_text(encoding="utf-8")
print(re.search(r'__version__ = "([^"]+)"', text).group(1))
PY
)"
echo "==> mclauncher $VERSION"

NFPM="${NFPM:-nfpm}"
command -v "$NFPM" >/dev/null || { echo "需要 nfpm：https://nfpm.goreleaser.com"; exit 1; }

rm -rf build/vendor dist
mkdir -p dist build

echo "==> 构建前端"
if [ -d gui/node_modules ]; then
  ( cd gui && npm run build >/dev/null )
else
  echo "    跳过：gui/node_modules 不存在（先 cd gui && npm install --include=dev）"
fi
if [ -d gui/dist ]; then
  rm -rf mclauncher/webui_dist
  cp -R gui/dist mclauncher/webui_dist
fi

echo "==> 收集依赖到 build/vendor"
uv pip install --target build/vendor --no-compile -q ".[cli]"
rm -rf build/vendor/bin

echo "==> deb / rpm / archlinux"
sed "s/@VERSION@/$VERSION/g" packaging/nfpm.yaml.tpl > build/nfpm.yaml
"$NFPM" package -f build/nfpm.yaml -p deb       -t dist/
"$NFPM" package -f build/nfpm.yaml -p rpm       -t dist/
"$NFPM" package -f build/nfpm.yaml -p archlinux -t dist/

echo "==> wheel"
uv build --wheel -o dist >/dev/null

echo "==> 便携压缩包（自带依赖，有 Python 就能跑）"
PORTABLE="build/portable/mclauncher-$VERSION"
rm -rf build/portable
mkdir -p "$PORTABLE"
cp -R build/vendor "$PORTABLE/vendor"
cp packaging/portable/mclauncher.sh packaging/portable/mclauncher.cmd "$PORTABLE/"
cp LICENSE README.md "$PORTABLE/"
( cd build/portable && zip -qr "../../dist/mclauncher-$VERSION-portable.zip" "mclauncher-$VERSION" )

echo "==> 源码包"
git archive --format=tar.gz --prefix="mclauncher-$VERSION/" -o "dist/mclauncher-$VERSION.tar.gz" HEAD
git archive --format=zip    --prefix="mclauncher-$VERSION/" -o "dist/mclauncher-$VERSION.zip" HEAD

ls -lh dist
