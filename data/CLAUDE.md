# data/
> L2 | 父级: /CLAUDE.md

原著硬知识库。世界的地理、人物、门派、器物、武学、关系与原著时间线由此供给基础设施，取代 tianlong/world/seed.json 中的手写样本。
数据由外部 AI 依 EXTRACT_PROMPT.md 从原著抽取，经导入校验器（待建）核对 id 引用、道路连通与时间线前提后，才进入世界。

成员清单
EXTRACT_PROMPT.md: 抽取提示词，定义 meta/00_index~08_canon 共 10 个 JSON 文件的格式、度量衡（功力锚点/路程/历法）、开端时间切片、隐情标记与分步自检流程
（待返回）meta.json、00_index.json ~ 08_canon.json: 外部抽取结果，格式以 EXTRACT_PROMPT.md 为准

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
