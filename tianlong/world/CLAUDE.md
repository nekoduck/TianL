# world/
> L2 | 父级: /tianlong/CLAUDE.md

基础设施层。掌管世界的唯一真相——地理、人物、器物、武学由 genesis 从 data/canon 原著硬知识编译而来，LLM 不新造；它服务于剧情：替导演记住一切、算好距离功力与时日、把剧情后果落账并传播。只经 effects 一个入口改变，本目录不 import 任何 LLM 代码。

成员清单
genesis.py: 创世导入器，读 data/canon 编译世界：裁剪抽取元数据、按 order 排定原著日程(同月均匀铺开且单调)、开端未明者休眠(dormant)、路程按骑马换算(PACE=0.6)、校验全部 id 引用，错一处即拒绝开局；编译结果缓存、每次深拷贝
world.py: World 聚合根，create 创世(genesis)、apply→record(标记亲历/公开)→advance→sync 状态流水线、观察校正认知、整世界 JSON 存读档
graph.py: 内存图数据库，节点属性 + 有向关系边 + 无向道路边(days 权重)；地点 state.accessible/exists 为 false 则道路断绝；Dijkstra 距离与 BFS 跳数是消息延迟和 LOD 分层的度量
clock.py: 全局时钟，以分钟计数(一刻十五分、一时辰八刻)、原点元祐元年正月初一，advance 返回跨日/跨月数驱动 LOD 节拍，parts 分段(年/日/时刻)、label 成句、day_of 解析元祐→绍圣→元符年号历法
blackboard.py: 玩家 JSON 黑板(坐标/气血/功力/姿态/物品/武学/叙事记忆)，经 effects 的 id="player" 通道写入，hp 下限 1
ledger.py: 双账本 + 消息队列——Truth 只追加事件；Knowledge 是公开属性的信念投影(开局排除 secret_fields)并记录已揭隐情(限定知情者唯亲历可知)；Messenger 以 速度×分量 的波前半径投递传闻(含场外剧情)
effects.py: 剧情落账器，7 指令 DSL(set/add/push/pull/link/unlink/reveal)，无新造指令；地理只可改 state、武学定义不可改、器物只可流转(location/holder/hidden/state)且随持有者走；place() 求任一节点所在；宽松规整后校验世界物理与在场性(休眠者不可触)；导演触碰的节点记为因果污染
lod.py: 叙事 LOD 调度，按道路跳数分 0/1/2 层；LOD1 选出相邻区有图谋的人物并落账其场外剧情；LOD2 原著按 order 依次结算(远事不被近事插队)，verdict 裁定：干净照原著、被扰动的大事与附近破局交史官、远方小事破局作罢
rag.py: 场景触发式 GraphRAG，scene 判定可见之物；build 产出玩家视锥(在场真相/场外认知/已知关系/传闻/前情)；人物含外貌/言谈/随身器物；backstage 产出导演后台(隐匿/暗藏/隐情/图谋/功力对比/在场武学/近处去向/命运骰)；dossier 产出场外档案；condition 把主角身况译为文字标签(伤势/功力档/姿态/随身/武学，数值隐于其后)
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
