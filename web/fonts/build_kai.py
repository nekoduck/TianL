"""
[INPUT]: 霞鹜文楷原版 TTF（命令行参数，取自 https://github.com/lxgw/LxgwWenKai/releases）；构建时依赖 fontTools + brotli（运行时零依赖）
[OUTPUT]: web/fonts/lxgw-wenkai-subset.woff2 —— 界面所需的楷体子集
[POS]: web/fonts 的构建脚本，仅在字符集需要更新时手动执行：
       字符集 = GB2312 一级常用字 ∪ data/canon 全部用字（含原著证据摘录） ∪ web 界面用字 ∪ 常用标点与 ASCII；
       子集之外的生僻字由 css 的字族链逐字回落到系统楷体与宋体
       用法：pip install fonttools brotli && python web/fonts/build_kai.py LXGWWenKai-Regular.ttf
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("lxgw-wenkai-subset.woff2")
PUNCT = "，。、；：？！…—～·「」『』（）《》〈〉【】“”‘’　"


def gb2312_level1() -> set[str]:
    """GB2312 一级常用字 3755 个：区码 16~55（0xB0~0xD7），位码 0xA1~0xFE。"""
    chars = set()
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                chars.add(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return chars


def charset() -> str:
    chars = gb2312_level1() | set(PUNCT) | {chr(c) for c in range(0x20, 0x7F)}
    for f in (ROOT / "data" / "canon").glob("*.json"):
        chars |= set(f.read_text("utf-8"))
    for f in (ROOT / "web").rglob("*"):
        if f.suffix in (".html", ".js", ".css", ".md"):
            chars |= set(f.read_text("utf-8"))
    return "".join(sorted(c for c in chars if c.isprintable()))


def main(src: str):
    from fontTools import subset  # 仅构建时需要

    options = subset.Options()
    options.flavor = "woff2"
    options.hinting = False          # 网页渲染不需要 TrueType 微调，省下不少体积
    options.desubroutinize = True
    options.name_IDs = ["*"]          # 保留名称表：许可附加条款允许网页子集沿用原名
    options.layout_features = ["*"]   # 保留竖排(vert)等排版特性：信笺与书眉是竖排的
    text = charset()
    font = subset.load_font(src, options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    subset.save_font(font, str(OUT), options)
    print(f"{len(text)} 字 → {OUT.name}（{OUT.stat().st_size / 1024:.0f} KB）")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("用法：python web/fonts/build_kai.py LXGWWenKai-Regular.ttf")
    main(sys.argv[1])
