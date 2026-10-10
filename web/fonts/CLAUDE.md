# web/fonts/
> L2 | 父级: /web/CLAUDE.md

自托管字体。楷体是界面的"手迹"——书眉身况、回合抬头、玩家举动、"记"、信笺、扉页小字皆用它，不能指望玩家系统里恰好装了楷体。
采用霞鹜文楷（LXGW WenKai，OFL 1.1）的常用字子集：其许可附加条款明许"仅供网页字体交付的子集/WOFF2 转换版"沿用原名。
宋体正文仍由 Google Fonts 的 Noto Serif SC 提供；两者缺字时由 css 字族链逐字回落到系统字体。

成员清单
lxgw-wenkai-subset.woff2: 楷体子集（4183 字、约 930 KB）——GB2312 一级常用字 ∪ data/canon 全部用字 ∪ 界面用字 ∪ 标点；去微调、留竖排(vert)特性
build_kai.py: 子集构建脚本，仅在字符集需要更新时手动运行；构建时依赖 fontTools + brotli（运行时零依赖），源字体取自霞鹜文楷官方发布页
OFL.txt: 霞鹜文楷的 SIL Open Font License 1.1 全文（含保留字体名与附加许可），随子集一并分发

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
