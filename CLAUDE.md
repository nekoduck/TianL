# 天龙八部 · 文字沙盒 - 基础设施服务于 LLM 的武侠涌现世界
Python 3.11+ (纯标准库，零依赖) + Gemini REST (gemini-flash-latest，thinkingBudget=0) + unittest

<directory>
tianlong/ - 游戏本体 (2 子目录: world/ 基础设施, narrative/ 大模型创作层；engine.py 主循环, cli.py 终端界面)
tests/ - 离线验证 (创造物化、世界物理、延迟传播、隐情揭示、污染判定、跨回合延续)
</directory>

<config>
main.py - 命令行入口：python main.py [--offline] [--load 存档] [--name 名号] [--verbose]
.env - 本地密钥 GEMINI_API_KEY=… (已 gitignore，可选 GEMINI_MODEL)
.gitignore - 忽略 .env、saves/、__pycache__
</config>

## 宪法

1. **LLM 创造，基础设施成全。** 导演 Agent 裁定主角举动的后果，并自由创造人物、地点、器物、恩怨与转折；
   基础设施负责让这些创造"有据可依"（RAG + 后台）与"落笔成真"（物化、记忆、传播、结算时日）。
2. **有据可依。** `rag.build` 给出玩家视锥，`rag.backstage` 只给导演：隐匿之人、暗藏之物、未揭隐情、图谋、功力对比、
   天下道路、种子化命运骰——LLM 不擅长记忆与算账，这些由系统替它算好。
3. **落笔成真。** 一切变更经 `world/effects.py` 的 8 指令 DSL（含 create / reveal）物化为真相，规整宽松、只守世界物理：
   引用须存在、死者不复生、主角只能触碰此地之人与物、场外推演碰不到主角本人。不成立的部分回告编剧，不留矛盾。
4. **双账本。** 真相与认知分离；传闻按道路距离延迟抵达，亲眼所见即时校正，隐情经 reveal 进入认知。
5. **兜底即离线。** 每个 Agent 都有朴素 fallback；`llm=None` 时游戏照常运转，测试据此运行。
6. **依赖方向。** `world/` 永不 import `narrative/`；narrative 只读 rag、只交 effects 提案。

## 回合流水线 (engine.Game._turn)

rag.build + rag.backstage → 导演(节拍/创造/时辰/事件/3建议) → effects.apply(director) → Truth.record
→ Clock.advance(max(导演估时, 道路里程)) → LOD1 推演 → LOD2 原著(干净直落/污染交史官)
→ Messenger.deliver + 观察校正 → rag.build → 编剧(正文，含未成立与新到传闻)

## 运行

```
python main.py                       # 需要 GEMINI_API_KEY（环境变量或 .env）
python main.py --offline             # 不调用模型
python -m unittest discover -s tests -t .
```

法则: 极简·稳定·导航·版本精确
