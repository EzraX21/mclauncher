"""mclw.exe：双击直接开图形界面（不带控制台窗口）。"""

import os
import sys

# windowed 模式下 stdout/stderr 是 None，print 会炸；丢到 devnull
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

sys.argv = ["mcl", "gui"]

from mcl.cli import main

raise SystemExit(main())
