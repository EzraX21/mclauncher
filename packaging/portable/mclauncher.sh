#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHONPATH="$DIR/vendor${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec python3 -m mclauncher "$@"
