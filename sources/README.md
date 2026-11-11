# 原著文本放这里（本地，不入库）

本目录放《天龙八部》三联版全文：`sources/tianlong.txt`（UTF-8、LF，用户已提供；页面水印与分隔行在规范化时去除）。
`.gitignore` 忽略本目录下除本说明与 `.gitkeep` 外的全部文件；原文永不入库，`tests/test_no_text_leak.py` 守这条。
换成别的文本或版本时，同样放在这里（版本以你提供的为准，默认三联版），再重生成 `data/canon/text_manifest.json`（`python3 tools/canon_text.py manifest --write`）。

常用命令（版面、规范化与指针格式见 `docs/CANON_SCHEMA.md` 第 15、16 节）：

    python3 tools/canon_text.py info                      # 各回标题、段数、字数与规范化统计
    python3 tools/canon_text.py export --all              # 导出到 out/canon/chapters/chNN.txt，供抽取代理阅读
    python3 tools/canon_resolve.py data/canon/assertions/ch07.jsonl   # 证据里写的锚点 -> 指针，并补 "b":"text"
    python3 tools/canon_check.py --evidence               # 逐条核对证据指针
    python3 tools/canon_run.py --source sources/tianlong.txt   # 第 0–2 阶段：规范化、提及普查、消歧合并

证据只存指针 `[回,段,起,止,哈希]`，不存引文。没有这份文本时（例如在别的机器上只拿到仓库），世界照常运行，
只是断言全部标 `basis = recall`，`canon_check --evidence` 与 `canon_run` 会给出提示并跳过原文核对（见 docs/DECISIONS.md 第三节）。
