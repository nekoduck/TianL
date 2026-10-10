# tianlong/
> L2 | 父级: /CLAUDE.md

游戏本体。两层一线：`world/` 掌管世界（地理、器物、人物、时间、账本）并替剧情记忆、算账、送信；`narrative/` 编织剧情与选项；`engine.py` 是两者唯一的交汇处。

成员清单
world/: 基础设施——图数据库、时钟、黑板、双账本与消息队列、剧情落账 DSL、LOD 调度、GraphRAG 视锥与导演后台（见 world/CLAUDE.md）
narrative/: 剧情层——Gemini 网关、提示词与叙事纲领、导演/编剧/推演/史官四个 Agent（见 narrative/CLAUDE.md）
engine.py: 游戏主循环 Game，串起"取材→导演编织剧情与选项→后果落账→按道路结算时日→LOD1/LOD2→传闻→编剧"，时间按动作流逝(导演以分钟估计，系统兜底至少 1 分钟)，未成立之事回告编剧；回合产物为结构化纯 dict(历法分段/身况标签/亲见与传闻)；可选监听逐步报告 stage→head(快照)→text 增量；附双账本对照 debug 视图
protocol.py: 前后端契约 tianlong/1.1 的 Python 实现——present 把引擎回合译成载荷(选项编号带回合序以识破过期)、relay 把引擎进度译成流式事件、resolve 把行动译回引擎原话、ProtocolError 携带 HTTP 状态与错误码；契约正文在 web/PROTOCOL.md
server.py: 传输层——标准库 ThreadingHTTPServer 托管 web/ 静态前端与 /api/session(续读/开卷)、/api/action(行动)；Accept 含 text/event-stream 时以 SSE 推送(首事件才开流，之前的错误仍为 JSON；读者离席回合照写)；Hub 单机单局、一锁一笔(忙则 409)、每回合自动存档(终端存档格式 + web 段)，Session 可开卷/续卷；不含游戏逻辑
cli.py: 终端表现层，展示正文/亲见与传闻/身况标签/导演的 3 个建议，处理自由输入与 /save /load /me /debug 指令，读取 .env；--web 时改为启动 server，续读 --load 存档或上次的自动存档(坏档不覆盖)
__init__.py: 包标记，空

依赖方向: cli → (server → protocol) → engine → (narrative → world.rag 只读) + world；world 不依赖任何上层，engine 不知道 protocol 的存在

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
