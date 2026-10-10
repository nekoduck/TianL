# world/
> L2 | 父级: /tianlong/CLAUDE.md

基础设施层。掌管世界的唯一真相——地理、器物、人物由创世数据给出，LLM 不新造；它服务于剧情：替导演记住一切、算好距离功力与时日、把剧情后果落账并传播。只经 effects 一个入口改变，本目录不 import 任何 LLM 代码。

成员清单
world.py: World 聚合根，创世(from_seed)、apply→record→advance→sync 状态流水线、观察校正认知、整世界 JSON 存读档
graph.py: 内存图数据库，节点属性 + 有向关系边 + 无向道路边(days 权重)，Dijkstra 距离与 BFS 跳数是消息延迟和 LOD 分层的度量
clock.py: 全局时钟，以时辰计数，advance 返回跨日/跨月数驱动 LOD 节拍，渲染元祐→绍圣→元符年号历法
blackboard.py: 玩家 JSON 黑板(坐标/气血/功力/姿态/物品/武学/叙事记忆)，经 effects 的 id="player" 通道写入，hp 下限 1
ledger.py: 双账本 + 消息队列——Truth 只追加事件；Knowledge 是公开属性的信念投影并记录已揭隐情；Messenger 以 速度×分量 的波前半径投递传闻(含场外剧情)
effects.py: 剧情落账器，7 指令 DSL(set/add/push/pull/link/unlink/reveal)，无新造指令；地理只可改 state、器物只可被发现或经主角拾取丢下流转；宽松规整(中文属性名、走向某人即其所在)后校验世界物理与在场性；导演触碰的节点记为因果污染
lod.py: 叙事 LOD 调度，按道路跳数分 0/1/2 层；LOD1 选出相邻区有图谋的人物并落账其场外剧情；LOD2 原著轨道按 前提破坏/污染/亲临 判脏，干净直落、脏则交史官
rag.py: 场景触发式 GraphRAG，scene 判定可见之物；build 产出玩家视锥(在场真相/场外认知/已知关系/传闻/前情)；backstage 产出导演后台(隐匿/暗藏/隐情/图谋/功力对比/道路/命运骰)；dossier 产出场外档案
seed.json: 创世数据——15 地点、20 人物、门派、景物、隐匿器物(带 hint)、道路、含 secret 的关系网、7 桩原著事件(带前提与效果)；世界的地理与器物只在此定义
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
