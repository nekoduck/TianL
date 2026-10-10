# tianlong/
> L2 | 父级: /CLAUDE.md

游戏本体。两层一线：`world/` 是确定性的真相机器，`narrative/` 是可替换的渲染器，`engine.py` 是两者唯一的交汇处。

成员清单
world/: 状态逻辑层——图数据库、时钟、黑板、双账本与消息队列、效果 DSL、规则、LOD 调度、GraphRAG（见 world/CLAUDE.md）
narrative/: 大模型生成层——Gemini 网关、提示词组装、五个 Agent（见 narrative/CLAUDE.md）
engine.py: 游戏主循环 Game，串起"裁决→落账→推进→LOD1/LOD2→传闻→RAG→导演→编剧"，回合产物为纯 dict，并提供双账本对照的 debug 视图
cli.py: 终端表现层，展示正文/传闻/状态栏/3 选项，处理自由输入与 /save /load /me /debug 指令，读取 .env
__init__.py: 包标记，空

依赖方向: cli → engine → (narrative → world.rag 只读) + world；world 不依赖任何上层

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
