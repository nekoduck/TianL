# 天龙八部 · 文字沙盒 - 基础设施掌管世界、LLM 编织剧情的武侠涌现沙盒
Python 3.11+ (纯标准库，零依赖) + Gemini REST (gemini-flash-latest，thinkingBudget=0) + unittest

<directory>
tianlong/ - 游戏本体 (2 子目录: world/ 基础设施, narrative/ 剧情层；engine.py 主循环, cli.py 终端界面)
data/ - 原著硬知识库 (EXTRACT_PROMPT.md 抽取提示词；待返回的 00_index~08_canon JSON，经导入校验后取代 seed.json)
tests/ - 离线验证 (剧情落账、地理器物归属、世界物理、延迟传播、隐情揭示、污染判定、跨回合延续)
</directory>

<config>
main.py - 命令行入口：python main.py [--offline] [--load 存档] [--name 名号] [--verbose]
.env - 本地密钥 GEMINI_API_KEY=… (已 gitignore，可选 GEMINI_MODEL)
.gitignore - 忽略 .env、saves/、__pycache__
</config>

## 宪法

1. **职责边界。** 基础设施掌管世界：地理（地点、道路）、器物、人物节点、时钟、账本；LLM 创造剧情与选项。
   LLM 不新造任何实体，也不改写地理与器物的定义；剧情所需的路人龙套只活在叙事中。
2. **不写死动作。** 没有动作列表、没有动作解析器：玩家原话直接交给导演，导演推演后果、自由拟定 3 个选项，选项即原话。
3. **基础设施服务剧情。** `rag.build` 给出玩家视锥，`rag.backstage` 只给导演：隐匿之人、暗藏之物、未揭隐情、图谋、
   功力对比、天下道路、种子化命运骰——记忆与算账由系统替 LLM 做好，剧情因此有根有据。
4. **剧情落账。** 剧情后果经 `world/effects.py` 的 7 指令 DSL 作用于既有世界（生死伤病、去留、恩怨、得失、揭开隐情、地点现状），
   宽松规整、只拦不可能之事；不成立的部分回告编剧，不留矛盾。跋涉时日按道路结算，不由 LLM 估算。
5. **双账本。** 真相与认知分离；传闻按道路距离延迟抵达，亲眼所见即时校正，隐情经 reveal 进入认知。
6. **兜底即离线。** 每个 Agent 都有朴素 fallback；`llm=None` 时游戏照常运转，测试据此运行。
7. **依赖方向。** `world/` 永不 import `narrative/`；narrative 只读 rag、只交 effects。

## 回合流水线 (engine.Game._turn)

rag.build + rag.backstage → 导演(剧情节拍/后果/时辰/事件/3选项) → effects.apply(director) → Truth.record
→ Clock.advance(max(导演估时, 道路里程)) → LOD1 推演 → LOD2 原著(干净直落/污染交史官)
→ Messenger.deliver + 观察校正 → rag.build → 编剧(正文，含未成立与新到传闻)

## 运行

```
python main.py                       # 需要 GEMINI_API_KEY（环境变量或 .env）
python main.py --offline             # 不调用模型
python -m unittest discover -s tests -t .
```

法则: 极简·稳定·导航·版本精确
