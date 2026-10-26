#!/bin/sh
# mclauncher 启动器（发行版包里的入口）
PYTHONPATH="/usr/lib/mclauncher${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec /usr/bin/python3 -m mclauncher "$@"
