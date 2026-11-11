"""持久化：每日 end_day 落盘到 npc_* 表，并可从表恢复引擎（ARCHITECTURE 6.3）。

本步是空壳，之后由集成步骤接手。要做的事：
  * 每日落盘：档案、需求、想法、见闻、好恶修正、案件、轨迹打包行（model.Trail 的 64 位整数，场所/活动/层/原因按 Symbols 还原）；
  * persist.load 从表恢复引擎，且“跑 30 日 → 存 → 读 → 再跑 30 日”与“直接跑 60 日”的 state_hash 相同；
  * 控制台的历史查询（迹/闻/情/案）读这些表，“此刻”的查询读内存。
恢复需要的全部状态：Profile 各字段、Opinions.mods、Norms.cases/announce_q、Perception.undisc、Rumor 的追踪量、
engine 的 stock/kit_staff/sight、已累积的哈希状态（或重放日志）。
"""
