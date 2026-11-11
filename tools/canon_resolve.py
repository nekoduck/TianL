#!/usr/bin/env python3
"""原著 -> 数据：canon_resolve（证据锚点解析），实现在 tianl/canon/anchors.py。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tianl.canon.anchors import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
