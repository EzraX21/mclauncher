"""mclw.exe：双击直接开图形界面（不带控制台窗口）。"""

import sys

sys.argv = ["mcl", "gui"]

from mcl.cli import main

raise SystemExit(main())
