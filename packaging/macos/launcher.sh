#!/bin/bash
# 双击 .app 时打开 Terminal 跑 TUI
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$DIR/../Resources/app/mcl-cli/mcl"
osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "\"$BIN\""
end tell
APPLESCRIPT
