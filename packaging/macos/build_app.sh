#!/usr/bin/env bash
# 在 macOS 上构建 mcl.app 和 dmg
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION="$(python3 - <<'PY'
import re, pathlib
print(re.search(r'__version__ = "([^"]+)"', pathlib.Path("mcl/__init__.py").read_text()).group(1))
PY
)"

python3 -m pip install --upgrade pip
python3 -m pip install ".[cli]" pyinstaller

if [ -d gui/dist ]; then
    rm -rf mcl/webui_dist
    cp -R gui/dist mcl/webui_dist
fi

python3 -m PyInstaller packaging/macos/mcl.spec --noconfirm \
    --distpath dist --workpath build/pyinstaller-macos

APP="dist/mcl.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp -R dist/mcl-cli "$APP/Contents/Resources/app"
sed "s/@VERSION@/$VERSION/g" packaging/macos/Info.plist.tpl > "$APP/Contents/Info.plist"
cp packaging/macos/launcher.sh "$APP/Contents/MacOS/mcl"
chmod +x "$APP/Contents/MacOS/mcl"

hdiutil create -volname mcl -srcfolder "$APP" -ov -format UDZO \
    "dist/mcl-$VERSION-macos.dmg"
echo "完成：dist/mcl-$VERSION-macos.dmg"
