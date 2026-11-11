# 原著文本放这里（本地，不入库）

把《天龙八部》文本（UTF-8，纯文本，按回分章；版本以你提供的为准，默认三联版）放在本目录，
例如 `sources/tianlong.txt`。`.gitignore` 已忽略本目录下除本说明外的全部文件。

放入后运行：

    python3 tools/canon_run.py --source sources/tianlong.txt

会重做第 0–2 阶段（规范化、提及普查、消歧合并），为已有断言补上证据指针，并把能在原文中找到支撑的断言的 `basis` 从 `recall` 升为 `text`。
没有原文时世界照常运行，只是断言全部标 `basis = recall`（见 docs/DECISIONS.md 第三节）。
