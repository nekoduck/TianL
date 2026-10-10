# tianlong/
> L2 | 父级: /CLAUDE.md

游戏本体。两层一线：`world/` 掌管世界（地理、器物、人物、时间、账本）并替剧情记忆、算账、送信；`narrative/` 编织剧情与选项；`engine.py` 是两者唯一的交汇处。

成员清单
world/: 基础设施——图数据库、时钟、黑板、双账本与消息队列、剧情落账 DSL、LOD 调度、GraphRAG 视锥与导演后台（见 world/CLAUDE.md）
narrative/: 剧情层——Gemini 网关、提示词与叙事纲领、导演/编剧/推演/史官四个 Agent（见 narrative/CLAUDE.md）
engine.py: 游戏主循环 Game，串起"取材→导演编织剧情与选项→后果落账→按道路结算时日→LOD1/LOD2→传闻→编剧"，时间按动作流逝(导演以分钟估计，系统兜底至少 1 分钟)，未成立之事回告编剧，回合产物为纯 dict，附双账本对照 debug 视图
cli.py: 终端表现层，展示正文/传闻/状态栏/导演的 3 个建议，处理自由输入与 /save /load /me /debug 指令，读取 .env
__init__.py: 包标记，空

依赖方向: cli → engine → (narrative → world.rag 只读) + world；world 不依赖任何上层

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
