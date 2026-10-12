"""
[INPUT]: 依赖 world/situation 的 around / party，World 门面的 graph / canon / done / clock / knowledge / player（鸭子类型）
[OUTPUT]: 对外提供 plant()（揭开之前该埋的系统伏笔：场记里一句，可选的一拍）、payoff()（本回合上演的原著正是某条伏笔的回收）、HORIZON、TIMES
[POS]: story 层的伏笔账——系统知道未来：隐情的 revealed_by 指明它在哪一桩原著里揭开、那桩原著何时到期。
       揭开前 HORIZON 日之内、当事人之一就在主角身边，场记便请导演让他言行间露出一点端倪(不得说破)，同一条至多提 TIMES 回；
       到了揭开的那一场，场记把它列为回收——读者先察觉、人物后知道，这是金庸常用的戏剧反讽，现在系统能有计划地安排它。
       编剧随手写的悬念(hooks)另记，仍受 v3 的阻尼(至多两条、身体不作伏笔、到期交代一次即作罢)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from ..world import situation

HORIZON = 5   # 揭开前几日之内才埋
TIMES = 2     # 同一条伏笔至多提几回


def _key(e: dict) -> str:
    return f"{e['src']}—{e['rel']}—{e['dst']}"


def plant(world) -> str:
    """一条该埋的系统伏笔(场记里一句)；没有即空。被提过 TIMES 回的不再提。"""
    g, today, me = world.graph, world.clock.day, world.player
    canon = {ev["id"]: ev for ev in world.canon}
    close = situation.around(world) | set(situation.party(world))
    shown = me["setups"]
    for e in g.edges:
        rb = e.get("revealed_by")
        if not e.get("secret") or not rb or rb in world.done or world.knowledge.knows_secret(e):
            continue
        ev = canon.get(rb)
        who = [p for p in (e["src"], e["dst"]) if p in close]
        if not ev or not who or not 0 <= ev["day"] - today <= HORIZON or shown.get(_key(e), 0) >= TIMES:
            continue
        shown[_key(e)] = shown.get(_key(e), 0) + 1
        me.set("setups", shown)
        return f"伏笔：{who[0]}身上有一桩将要揭开的隐情（{_key(e)}）——可让{who[0]}言行间露出一点端倪，只可暗示，不得说破"
    return ""


def payoff(world, staged: dict | None) -> str:
    """此地上演的原著正是某条隐情的揭示事件：场记列为回收。"""
    if not staged:
        return ""
    keys = [_key(e) for e in world.graph.edges if e.get("revealed_by") == staged["id"]]
    return f"回收：此前埋下的伏笔在本场揭开（{'；'.join(keys)}）" if keys else ""
