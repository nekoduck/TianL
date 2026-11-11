"""持久化：每日 end_day 落盘到 npc_* 表，并可从表恢复引擎（ARCHITECTURE 6.3）。

本步是空壳（只有钩子），之后由集成步骤接手。要做的事：
  * 每日落盘：档案、需求、想法、见闻、好恶修正、案件、轨迹打包行（model.Trail 的 64 位整数，场所/活动/层/原因按 Symbols 还原）；
  * persist.load 从表恢复引擎，且“跑 30 日 → 存 → 读 → 再跑 30 日”与“直接跑 60 日”的 state_hash 相同；
  * 控制台的历史查询（迹/闻/情/案）读这些表，“此刻”的查询读内存。
恢复需要的全部状态：Profile 各字段、Opinions.mods、Norms.cases/announce_q、Perception.undisc、Rumor 的追踪量、
engine 的 stock/kit_staff/sight、已累积的哈希状态（或重放日志）、事件流水号与 Host 事件 id 的对应（EvRec.id / hid）、
各人轨迹的下一个应记时刻（Trail.nxt）与 Profile.gone_why、engine.controllers（操纵者不落盘，重启后由集成层重新挂上）。

钩子（engine.end_day 的最后一步调用，每个模拟日一次，在想法到期、修正项到期、传闻曲线之后）：

    flush(engine, day)

现在是空操作。集成步骤只改本文件里 flush 的函数体（和 load），不改 engine.py。flush 必须是只读的：不得改任何引擎状态、不进任何哈希
（落盘不能改变世界）。
"""


def flush(engine, day):
    """每日落盘的调用点（默认空操作）。"""
    return None
