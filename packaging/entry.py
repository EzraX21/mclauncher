"""PyInstaller 入口：直接调用 CLI。"""

import sys

from mclauncher.cli import main

if __name__ == "__main__":
    sys.exit(main())
