"""精度分档：眼前 / 个体 / 批三档、观察者、刻级叙述（计划 10，里程碑 C8）。

本步是空壳（只有钩子），之后由 C8 接手。已有的、并且必须保持的最小部分：
  * engine.set_observer(place)：观察者所在场所；
  * 钩子 observe(engine, ctx, day, slot)（engine.run_slot 第 5 步调用，在“落轨迹”之后、偷食与见证之前）：
    只读地数该场所的人（engine.narr 累计、engine.narr_last 是这个时辰的人），不改任何状态、不进任何哈希。
C8 要做的事：时辰内细分到刻（每时辰 8 刻）的逐条叙述；工位逐个预约；“批”一档按人群整批结算；
并把“观察者站在不同地方各跑一遍，时辰级轨迹哈希必须相同”做成自动测试（本步 test_npc_proto 已覆盖廊下一例）。
刻只用于叙述，不参与任何决定、不进入任何哈希（ARCHITECTURE 第 2 节）。C8 只改本文件，不改 engine.py。

钩子的签名：

    observe(engine, ctx, day, slot)     ctx 是 model.SlotCtx（ctx.dec：各人这个时辰的决定 ix -> (场所, 活动, 层, 原因)）；返回值不用

叙述若要随机，一律走 engine.rng 的计数器式键（现在是 rng(seed, 'narr', 日, 时辰, ix)）。
"""


def observe(engine, ctx, day, slot):
    """观察者所在场所的叙述入口。没有观察者就什么也不做；有就只读地数人（排序用计数器式随机数，所以与调用次序无关）。"""
    if engine.observer:
        here = sorted((i for i, d in ctx.dec.items() if d[0] == engine.observer),
                      key=lambda i: engine.rng(engine.seed, 'narr', day, slot, i))
        engine.narr += len(here)
        engine.narr_last = here
