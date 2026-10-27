#!/bin/sh
# mcl 启动器（发行版包里的入口）
PYTHONPATH="/usr/lib/mcl${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec /usr/bin/python3 -m mcl "$@"
