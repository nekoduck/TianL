"""原著 -> 数据 流水线（计划第 3 节）。

格式契约见 docs/CANON_SCHEMA.md；阶段：
  schema.py  封闭属性注册表、操作词表、校验函数、JSONL 读写与紧凑/完整互转
  text.py    第 0–2 阶段：规范化、提及普查、消歧合并（原文只在本地）
  llm.py     第 3–4 阶段的抽取器/复核器接口、离线桩、真实后端（建造期才用）
  merge.py   普查合并（tools/canon_merge.py）
  check.py   综合校验（tools/canon_check.py）
  run.py     tools/canon_run.py 的实现

只用标准库；运行时（tianl.kernel / tianl.npc）不得导入本包的 llm 模块。
"""
