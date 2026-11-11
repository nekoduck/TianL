#!/usr/bin/env python3
"""原著 -> 数据：canon_merge 的命令行入口（实现在 tianl/canon/merge.py）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tianl.canon.merge import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
