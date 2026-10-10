# data/
> L2 | 父级: /CLAUDE.md

原著硬知识库。世界的地理、人物、门派、器物、武学、关系与原著时间线由此供给基础设施，经 tianlong/world/genesis.py 编译入世。
数据由外部 AI 依 EXTRACT_PROMPT.md 从《天龙八部》世纪新修版全文抽取；genesis 校验全部 id 引用，错一处即拒绝开局。

成员清单
EXTRACT_PROMPT.md: 抽取规范，定义 meta/00_index~08_canon 的格式、度量衡（功力锚点/路程/历法）、开端时间切片、隐情标记与分步自检流程
canon/meta.json: 版本(世纪新修版)、开端(元祐六年二月，第一回第四场比剑前)、源文校验和、对规范的扩展约定(器物 state/holder、门派 state.leader、reveal_scope 等)
canon/00_index.json: 全书统一 id 与别名，另含 events 组供隐情揭示引用
canon/01_locations.json ~ 08_canon.json: 183 地点、191 道路、55 门派、242 人物、98 器物、119 武学、191 关系、235 原著事件——genesis 的输入
canon/09_index_updates.json ~ 13_chapter_coverage.json: 抽取过程记录——索引增补、问题清单(含 6 名开端未明人物)、933 条原文证据、自检报告、50 回覆盖表；不入世，供核对与后续修订

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
