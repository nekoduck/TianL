#!/usr/bin/env python3
"""原著 -> 数据：canon_review（第 4 阶段复核工具），实现在 tianl/canon/review.py。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tianl.canon.review import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
