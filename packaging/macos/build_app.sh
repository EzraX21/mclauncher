#!/usr/bin/env bash
# 在 macOS 上构建 mclauncher.app 和 dmg
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION="$(python3 - <<'PY'
import re, pathlib
print(re.search(r'__version__ = "([^"]+)"', pathlib.Path("mclauncher/__init__.py").read_text()).group(1))
PY
)"

python3 -m pip install --upgrade pip
python3 -m pip install ".[cli]" pyinstaller

python3 -m PyInstaller packaging/macos/mclauncher.spec --noconfirm \
    --distpath dist --workpath build/pyinstaller-macos

APP="dist/mclauncher.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp -R dist/mclauncher-cli "$APP/Contents/Resources/app"
sed "s/@VERSION@/$VERSION/g" packaging/macos/Info.plist.tpl > "$APP/Contents/Info.plist"
cp packaging/macos/launcher.sh "$APP/Contents/MacOS/mclauncher"
chmod +x "$APP/Contents/MacOS/mclauncher"

hdiutil create -volname mclauncher -srcfolder "$APP" -ov -format UDZO \
    "dist/mclauncher-$VERSION-macos.dmg"
echo "完成：dist/mclauncher-$VERSION-macos.dmg"
