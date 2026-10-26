#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "首次运行：创建虚拟环境…"
  python3 -m venv .venv
  ./.venv/bin/python -m pip install --quiet --upgrade pip
fi
./.venv/bin/python -m pip install --quiet -r requirements.txt
exec ./.venv/bin/python -m mclauncher "$@"
