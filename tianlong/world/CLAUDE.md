# world/
> L2 | 父级: /tianlong/CLAUDE.md

状态逻辑层。世界的唯一真理在此，且只经 effects 一个入口改变。本目录不 import 任何 LLM 代码，没有大模型也能完整推演。

成员清单
world.py: World 聚合根，创世(from_seed)、apply→record→advance→sync 状态流水线、观察校正认知、整世界 JSON 存读档
graph.py: 内存图数据库，节点属性 + 有向关系边 + 无向道路边(days 权重)，Dijkstra 距离与 BFS 跳数是消息延迟和 LOD 分层的度量
clock.py: 全局时钟，以时辰计数，advance 返回跨日/跨月数驱动 LOD 节拍，渲染元祐→绍圣→元符年号历法
blackboard.py: 玩家 JSON 黑板(坐标/气血/功力/姿态/物品/武学/叙事记忆)，经 effects 的 id="player" 通道写入，hp 下限 1
ledger.py: 双账本 + 消息队列——Truth 只追加事件；Knowledge 是公开属性的信念投影；Messenger 以 速度×分量 的波前半径投递传闻
effects.py: 6 指令变更 DSL 与来源策略(rules/canon/chronicle/lod1 逐级收窄)，LLM 提案在此被框住；rules 来源写入的节点记为因果污染
rules.py: 确定性规则引擎，legal_actions 枚举可行动作，resolve 裁决为 事实+指令+时辰成本+公开事件，战斗以种子化 Random 判定
lod.py: 叙事 LOD 调度，按道路跳数分 0/1/2 层；LOD1 选出相邻区有图谋的人物并经 lod1 策略吸收战报；LOD2 原著轨道按 前提破坏/污染/亲临 判脏，干净直落、脏则交史官
rag.py: 场景触发式 GraphRAG，build 产出玩家视锥上下文包(在场真相/场外认知/设定/关系链/传闻/前情)，dossier 产出远端推演用真相档案
seed.json: 创世数据——14 地点、20 人物、门派、景物、隐藏器物、道路、含 secret 的关系网、7 桩原著事件(带前提与效果)
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
