# TianL（《天龙世界》）

计划在 `docs/PLAN.md`，实现契约在 `docs/ARCHITECTURE.md`，决定记录在 `docs/DECISIONS.md`。动手前先读后两者。

## 常用命令
- 全部测试：`python3 -m unittest discover -s tests -t .`（慢测试：`TIANL_SLOW=1`）
- 玩：`python3 -m tianl`
- 验收报告：`python3 tools/acceptance.py`
- 参考原型回归基线：`reference/shaolin_spike.py`（哈希 49f6ddde04dfa7f5）、`reference/npc_spike.py`（哈希 e8f8209eeb8ca94a）。**只读，不得改。**

## 规矩（摘要，全文见 ARCHITECTURE 第 0 节）
只用标准库；一切随机用计数器式 `rnd`；一切状态变化走内核原语/命令；事件日志是感知与记忆的唯一来源；
定义用 TOML，键用 ASCII；原著原文不入库；运行时不调 LLM；数字不好看就如实报，不许调宽通过线。
