# tianlong/
> L2 | 父级: /CLAUDE.md

游戏本体。两层一线：`world/` 掌管世界（地理、器物、人物、时间、账本、原著日程）并替剧情记忆、算账、裁决、送信；`narrative/` 编织剧情与选项；`engine.py` 是两者唯一的交汇处。

成员清单
world/: 基础设施——图数据库、时钟、黑板、双账本与消息队列、剧情落账 DSL、通行裁判、LOD 调度、GraphRAG 视锥与导演后台（见 world/CLAUDE.md）
narrative/: 剧情层——Gemini 网关、提示词与叙事纲领、导演/编剧/推演/史官四个 Agent（见 narrative/CLAUDE.md）
engine.py: 游戏主循环 Game(act 原话照收；一回合原子——中途抛错则世界与记忆回到回合开始；此地原著前提已破不照演；一批里每一程都算时日；主角做完便走的事以亲历、事发之日、事发之地入账；编剧没写梗概时以意图与核实过的后果代记)，串起"先了远方到期原著→此地到期的一桩原著交导演作主干→导演编织节拍/后果/时长措辞/选项→原著照常落账或因主角扰动由导演后果作准→导演后果落账(主角远行止步门前之关)→时长按措辞与走得通的道路结算→LOD1/新到期远方原著→传闻→编剧成文并写下真实梗概→事件门槛(众目之下的伤亡/易手/恩怨/重创)入江湖账本→近事溢出折叠梗概"；账本只记已成立之事；回合产物为结构化纯 dict(历法分段/身况标签/亲见与传闻)；可选监听逐步报告 stage→head(快照)→text 增量；附双账本对照 debug 视图
protocol.py: 前后端契约 tianlong/1.2 的 Python 实现——present 把引擎回合译成载荷(选项编号带回合序以识破过期)、relay 把引擎进度译成流式事件、resolve 把行动译回引擎原话(写明的卷与回合须与眼下一致，否则 409 stale_turn)、ProtocolError 携带 HTTP 状态与错误码；契约正文在 web/PROTOCOL.md
server.py: 传输层——标准库 ThreadingHTTPServer 托管 web/ 静态前端与 /api/session(续读/开卷)、/api/action(行动)；POST 只收同源 JSON(跨站 403)、Content-Length 须为非负整数；Accept 含 text/event-stream 时以 SSE 推送(首事件才开流，之前的错误仍为 JSON；读者离席回合照写)；Hub 单机单局、一锁一笔(忙则 409)、每回合自动存档(终端存档格式 + web 段)，Session 可开卷/续卷(续卷记得上回合末段)；开流前后读者离席都不打断回合；不含游戏逻辑
cli.py: 终端表现层，选名号与出身、展示正文/亲见与传闻/身况标签/导演的 3 个建议，处理自由输入(半角数字即第几个选项，此快捷写法只在终端)与 /save /load /me /debug 指令(读档失败只提示、不丢眼前这一局)，读取 .env；--web 时改为启动 server 并续读 --load 存档或上次的自动存档(坏档不覆盖)，--trace 记录大模型调用
__init__.py: 包标记，空

依赖方向: cli → (server → protocol) → engine → (narrative → world.rag 只读) + world；world 不依赖任何上层，engine 不知道 protocol 的存在

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
