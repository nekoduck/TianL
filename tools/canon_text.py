#!/usr/bin/env python3
"""原著 -> 数据：canon_text（原文与证据锚点工具），实现在 tianl/canon/textcli.py。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tianl.canon.textcli import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
