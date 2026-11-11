"""NPC 事件类型：大写英文代码 <-> 中文渲染。

哈希、控制台、日报都用同一张表渲染。原型哈希里事件种类写的是中文（偷食、失窃…），
所以代码与中文必须一一对应、不得改字。

本步实际发出的只有 EMITTED 里的七种（与原型逐条对应）；其余代码先登记，由之后的集成步骤使用。
"""

FOOD_THEFT = 'FOOD_THEFT'
THEFT_FOUND = 'THEFT_FOUND'
REPORT = 'REPORT'
SANCTION = 'SANCTION'
ABSENCE = 'ABSENCE'
SLACK = 'SLACK'
BED_EMPTY = 'BED_EMPTY'
# 以下已登记、本步不发（见 docs/NPC_ENGINE.md 第 6 节）
CASE_OPENED = 'CASE_OPENED'
CONFESS = 'CONFESS'
SUMMON = 'SUMMON'
ANNOUNCE = 'ANNOUNCE'
ILL = 'ILL'
RECOVER = 'RECOVER'
CHAT = 'CHAT'

LABELS = {
    FOOD_THEFT: '偷食', THEFT_FOUND: '失窃', REPORT: '举报', SANCTION: '处分', ABSENCE: '缺课',
    SLACK: '怠工', BED_EMPTY: '夜不在寮',
    CASE_OPENED: '立案', CONFESS: '认错', SUMMON: '传讯', ANNOUNCE: '公告', ILL: '生病', RECOVER: '痊愈',
    CHAT: '闲谈',
}
EMITTED = (FOOD_THEFT, THEFT_FOUND, REPORT, SANCTION, ABSENCE, SLACK, BED_EMPTY)


def label(kind):
    """事件种类的中文渲染；未登记的代码原样返回。"""
    return LABELS.get(kind, kind)
