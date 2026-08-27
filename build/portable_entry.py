"""PyInstaller 构建入口：python -m PyInstaller build/portable_entry.py 之外的正式配置见 build 脚本。"""

import sys

from thesislint.cli import main

if __name__ == "__main__":
    sys.exit(main())
