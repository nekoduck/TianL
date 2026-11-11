"""十类定义（计划 4.2）与它们下面的具体“种类”（kind）。

稳定编号形如  kind:scope:name，例如 place:shaolin:cangjingge、facility:base:chandeng。
kind 取自下表；加载器据此识别“看起来像编号的字符串”并做引用完整性检查。
需要新增 kind 时：在这里追加（只追加，不改名），并在 docs/ARCHITECTURE.md 第 4 节补一行说明。
"""

CATEGORIES = {
    '历法': ['calendar'],
    '空间': ['place', 'route', 'region'],
    '设施与交互': ['facility', 'interaction'],
    '物': ['item', 'commodity'],
    '武学': ['martial'],
    '组织': ['archetype', 'org', 'site'],
    '岗位与规则': ['post', 'rule', 'package', 'job', 'trait'],
    '规范': ['norm', 'ladder'],
    '经济': ['account', 'process', 'price', 'param'],
    '知识与事件': ['secret', 'document', 'event', 'flag', 'pulse', 'thought', 'modifier', 'scenario'],
}

ALL_KINDS = tuple(k for ks in CATEGORIES.values() for k in ks)
CATEGORY_OF = {k: c for c, ks in CATEGORIES.items() for k in ks}
