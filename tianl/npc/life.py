"""一生：月、年脉冲与事件池、人口调节器（计划 9.4，里程碑 C7）。

本步是空壳（只有钩子），之后由 C7 接手。要做的事（见 PLAN 9.4 与 ARCHITECTURE 6）：
  * 每月、每年各有一次脉冲；脉冲时对每个人从事件池里按权重抽取，权重受性格、处境和好恶修正（CK3 的 on_action）；
  * 寺院每年：剃度、受戒、升座、闭关、游方、还俗、圆寂；通用每月：生病、痊愈、结怨、和解；
  * 人口调节器：寺里僧数低于目标，就提高剃度的权重；
  * 心情第二、三道线（低于 20 回避集体；低于 5 且持续触发人生事件）也在这里接（线的数值已在 SiteSpec.mood.lines，enabled 目前是 1）。
接口约定：只通过 NpcEngine 的公开方法与 Host 事件改变世界；随机一律走 engine.rng 的计数器式键。

钩子（engine.begin_day 的第一步调用，每个模拟日一次，在生病抽签与监院派人之前）：

    pulse(engine, day)

现在是空操作。C7 只改本文件里 pulse 的函数体（要自己判断今天是不是月初 / 岁首：engine 不替它判断，历法用 tianl.core.cal(day)）；
不要改 engine.py。注意：pulse 里若收人 / 送人（engine.add_person / on_person_removed）或发事件，会改变基线哈希，要按
docs/NPC_ENGINE.md 的规矩重立基线并写明原因。
"""


def pulse(engine, day):
    """月 / 年脉冲的调用点（默认空操作）。"""
    return None
