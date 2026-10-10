# 天龙八部 · 文字沙盒 - 以确定性基础设施框住大模型的武侠涌现世界
Python 3.11+ (纯标准库，零依赖) + Gemini REST (gemini-flash-latest，thinkingBudget=0) + unittest

<directory>
tianlong/ - 游戏本体 (2 子目录: world/ 状态逻辑层, narrative/ 大模型生成层；engine.py 主循环, cli.py 终端界面)
tests/ - 离线验证 (状态流转、延迟传播、污染判定、LLM 越权拦截)
</directory>

<config>
main.py - 命令行入口：python main.py [--offline] [--load 存档] [--name 名号] [--verbose]
.env - 本地密钥 GEMINI_API_KEY=… (已 gitignore，可选 GEMINI_MODEL)
.gitignore - 忽略 .env、saves/、__pycache__
</config>

## 宪法

1. **系统代码管状态，LLM 只负责艺术渲染。** `world/` 永不 import `narrative/`；依赖方向只有 narrative → world(只读 rag)。
2. **唯一写入通道。** 一切世界变更都是 `world/effects.py` 的 6 指令 DSL（set/add/push/pull/link/unlink），
   按来源 origin 分级授权：rules > canon > chronicle(限相关者) > lod1(只能挪动相邻/改心境)。LLM 只交"提案"。
3. **LLM 只能选，不能造。** 动作解析器与导演只能从 `rules.legal_actions()` 里挑序号；胜负生死由 `rules.resolve()` 种子化裁定。
4. **玩家视锥。** `world/rag.py` 在场取真相、场外取认知账本，secret 边 / hidden 节点永不进入提示词。
5. **兜底即离线。** 每个 Agent 都有确定性 fallback；`llm=None` 时整套游戏照常运转，测试据此运行。

## 回合流水线 (engine.Game._turn)

裁决 rules.resolve → effects.apply(rules) → Truth.record → Clock.advance
→ LOD1 (跨日: simulate → lod.absorb) → LOD2 (跨月/近距: 原著干净则 settle，污染则 chronicle)
→ Messenger.deliver + 观察校正 → rag.build → 导演(节拍+3选项) → 编剧(正文)

## 运行

```
python main.py                       # 需要 GEMINI_API_KEY（环境变量或 .env）
python main.py --offline             # 不调用模型
python -m unittest discover -s tests -t .
```

法则: 极简·稳定·导航·版本精确
