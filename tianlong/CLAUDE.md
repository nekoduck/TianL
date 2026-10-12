# tianlong/
> L2 | 父级: /CLAUDE.md

游戏本体。两层一线：`world/` 掌管世界（地理、器物、人物、时间、账本、原著日程、情境）并替剧情记忆、算账、裁决、送信——它是唯一的事实源与裁判；`narrative/` 提议剧情、成文、拟选项；`engine.py` 是两者唯一的交汇处：LLM 提议，世界裁决，文字只渲染已成立之事。

成员清单
world/: 基础设施——图数据库、时钟、黑板、双账本与消息队列、剧情落账 DSL、情境层、数值规则、裁决器与变化词表、选项出口检查、通行裁判、LOD 调度、GraphRAG 视锥与导演后台（见 world/CLAUDE.md）
narrative/: 剧情层——Gemini 网关、提示词与叙事纲领、导演(含返工)/编剧/书记/推演/史官 Agent（见 narrative/CLAUDE.md）
engine.py: 游戏主循环 Game(act 原话照收；一回合原子——中途抛错则世界与记忆回到回合开始；flush 汇合后台折叠的梗概)，串起"授意(选项自带的对象+原话里的名字)→先了远方到期原著→焦点检索与后台→导演逐拍提议→在世界副本上试演(逐拍落账→此地原著(导演挪动过的人原著挪不动)→词表体检)，硬违例返工一次、仍不成立的拍整拍作废→定稿落账→时长按措辞与走得通的道路结算(歇满半日按规则养伤)→传闻→编剧从主角视角(perspective.veil/mask：不识名之人只剩叫法；成文按段再过一遍 mask)只凭已成立之事成文并拟选项伏笔(场外推演与新到期的远方原著同时在后台进行)→选项过出口检查、对象记作下一回合授意→事件门槛入江湖账本→近事、未了之事推进与了结、伏笔账(至多两条，身体不作伏笔)、节奏账(pacing)、场景实体回收，近事溢出交后台折叠梗概"；节奏看本幕之问的结局(连番被打断则不得再打断)；回合产物为结构化纯 dict(历法分段/身况标签/亲见与传闻)；可选监听逐步报告 stage→head(快照，选项为空)→text 增量(按段送出)；附双账本对照 debug 视图
protocol.py: 前后端契约 tianlong/1.3 的 Python 实现(1.3：选项随 done 放出，head 的 options 为空)——present 把引擎回合译成载荷(选项编号带回合序以识破过期)、relay 把引擎进度译成流式事件、resolve 把行动译回引擎原话(写明的卷与回合须与眼下一致，否则 409 stale_turn)、ProtocolError 携带 HTTP 状态与错误码；契约正文在 web/PROTOCOL.md
server.py: 传输层——标准库 ThreadingHTTPServer 托管 web/ 静态前端与 /api/session(续读/开卷)、/api/action(行动)；POST 只收同源 JSON(跨站 403)、Content-Length 须为非负整数；Accept 含 text/event-stream 时以 SSE 推送(首事件才开流，之前的错误仍为 JSON；读者离席回合照写)；Hub 单机单局、一锁一笔(忙则 409)、每回合自动存档(终端存档格式 + web 段)，Session 可开卷/续卷(续卷记得上回合末段)；开流前后读者离席都不打断回合；不含游戏逻辑
cli.py: 终端表现层，选名号与出身、展示正文/亲见与传闻/身况标签/验收过的 3 个选项，处理自由输入(半角数字即第几个选项，此快捷写法只在终端)与 /save(先汇合后台梗概) /load /me /debug 指令(读档失败只提示、不丢眼前这一局)，读取 .env；--web 时改为启动 server 并续读 --load 存档或上次的自动存档(坏档不覆盖)，--trace 记录大模型调用
__init__.py: 包标记，空

依赖方向: cli → (server → protocol) → engine → (narrative → world.rag 只读) + world；world 不依赖任何上层，engine 不知道 protocol 的存在

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
