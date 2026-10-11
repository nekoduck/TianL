# data/
> L2 | 父级: /CLAUDE.md

原著硬知识库。世界的地理、通行条件、人物、门派、器物、武学、关系与原著时间线由此供给基础设施，经 tianlong/world/genesis.py 编译入世。
数据由外部 AI 依 EXTRACT_PROMPT.md 与 ACCESS_PROMPT.md 从《天龙八部》世纪新修版全文抽取；genesis 校验全部 id 引用与道路补丁，错一处即拒绝开局。

成员清单
EXTRACT_PROMPT.md: 抽取规范，定义 meta/00_index~08_canon 的格式、度量衡（功力锚点/路程/历法）、开端时间切片、隐情标记与分步自检流程
ACCESS_PROMPT.md: 通行条件补充规范，定义 14_access.json(有向通路的悬崖/机关/秘道/水路等条件、可硬判的 requires、隐秘通路)与 15_roads_patch.json(修正 0 日中枢造成的伪捷径)的格式
canon/meta.json: 版本(世纪新修版)、开端(元祐六年二月，第一回第四场比剑前)、源文校验和、对规范的扩展约定(器物 state/holder、门派 state.leader、reveal_scope 等)
canon/00_index.json: 全书统一 id 与别名(含通行补丁新增的 19 处地点)，另含 events 组供隐情揭示引用
canon/01_locations.json ~ 08_canon.json: 202 地点、191 原路(按步行估算，genesis 换算为骑马)、55 门派、242 人物、98 器物、119 武学、191 关系、235 原著事件——genesis 的输入
canon/14_access.json: 179 条有向通行条件 {from,to,kind,blocked,hidden,how,requires,risk}——blocked 与 requires(8 条，皆为某处 state)由系统硬判，hidden(21 条)须经剧情发现，how/risk 交导演兑现；阶段性条件(垂链、断桥、围庄)无时间字段，由 how 文字描述
canon/15_roads_patch.json: 原路补丁 remove 17 / add 45 / change 4（外部抽取），genesis 读入时先删再加再改、各只一次，修去 0 日中枢的伪捷径；notes 记每处修正的原著依据，new_locations 已并入 01；不依 01 的 parent 自动连路
canon/16_roads_fill.json: 走廊补丁，同 15 的格式、在其后读入，据既有数据补全而非另行抽取——汉中—长安(第47回段正淳自中原南行经梓潼)、陆凉州—洞庭湖(第9回少林使者南来至陆凉州、第10—11回鸠摩智一月内押段誉自大理抵姑苏)、吐蕃—大理城(两国比邻，鸠摩智自大轮寺赴天龙寺)；大理到中原、江南不再绕道西夏天山，合计 222 条道路连成一片
canon/09_index_updates.json ~ 13_chapter_coverage.json: 抽取过程记录——索引增补、问题清单(含 6 名开端未明人物)、933 条原文证据、自检报告、50 回覆盖表；不入世，供核对与后续修订
reports/: 通行补丁的过程记录，不入世——bundle_manifest(四个数据文件的校验和与应用顺序)、issues(未改的原数据矛盾、阶段条件的模型限制、与旧"父子直连"校验规则的冲突)、access/base_after_patch/bundle_validation(拓扑与引用自检)、source_evidence 与 candidate_evidence_history(原文证据)、zero_roads_audit(0 日道路审计)、chapter_coverage

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
