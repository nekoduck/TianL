"""
[INPUT]: 依赖 world/body 的 wound / severity（伤势措辞）、world/actor 的 mood（心境）、world/bond 的 stance / structural（立场与结构性关系）、
         world/growth 的 mastery（主角的进境投影）、world/effects 的 usable（器物是否尚存），World 门面的 graph / player / knowledge（鸭子类型）
[OUTPUT]: 对外提供 profile()（某人此刻的状态切面）、power_tier()、tier_index()、TIERS、ties()（此人与主角之间看得见的结构性关系与立场，一行一句）
[POS]: world 层的单一投影——「主角此刻怎样」「这个人此刻怎样」只在这里算一次：
       rag.condition(界面标签)、rag.build(编剧视锥)、rag.backstage(导演后台)都从 profile 取字段，三者的差别只在取哪些切面，不在各自怎么算。
       主角与 NPC 同构：伤势、境况、随身、武学(主角带进境阶段与习练中的功夫)、NPC 另有心境、眼下之事(intent)与对主角的立场(由恩怨账折叠)。
       新加一种状态，只在这里加一次，三处同时看得见——研习进度只进导演后台、编剧照气氛写出「身如游龙」的事不再发生
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import actor, body, bond, growth
from .effects import usable

TIERS = ((15, "不会武功"), (35, "三流身手"), (60, "二流好手"), (85, "一流高手"), (10**9, "绝顶高手"))


def power_tier(power: int) -> str:
    return next(name for cap, name in TIERS if power < cap)


def tier_index(power: int) -> int:
    return next(i for i, (cap, _) in enumerate(TIERS) if power < cap)


def _held(world, pid: str) -> list[str]:
    g = world.graph
    return [i for i in g.where(type="item", holder=pid) if not g.get(i, "hidden") and usable(world, i)]


def ties(world, who: str) -> list[str]:
    """此人(及其门派)与主角之间主角看得见的一切：结构性关系边(暗中的心思揭开之前不算)与恩怨账折叠出的立场。"""
    g = world.graph
    sides = {who, g.get(who, "faction")} - {None}
    out = [(f"{e['src']}→你：{e['rel']}" if e["dst"] == "player" else f"你→{e['dst']}：{e['rel']}")
           + (f"（{e['note']}）" if e.get("note") else "")
           for e in g.edges if {e["src"], e["dst"]} & sides and "player" in (e["src"], e["dst"])
           and not (e.get("secret") and not world.knowledge.knows_secret(e))]
    st = bond.stance(world, who)
    if st:
        out.append(f"对你{st[0]}" + (f"（{st[1]}）" if st[1] else ""))
    return out


def profile(world, who: str) -> dict:
    """某人此刻的状态切面：{wound, tone, tier, conditions, carrying, arts, ...}；主角另有进境与姿态，NPC 另有心境、眼下之事、立场。"""
    g = world.graph
    wound, tone = body.wound(world, who)
    if who == "player":
        me = world.player
        return {"who": "player", "wound": wound, "tone": tone, "tier": power_tier(me["power"]), "posture": me["posture"],
                "conditions": list(me["conditions"]), "carrying": list(me["inventory"]), "arts": growth.mastery(world)}
    st = bond.stance(world, who)
    return {"who": who, "wound": wound, "tone": tone, "tier": power_tier(g.get(who, "power", 30)), "status": g.get(who, "status"),
            "conditions": list(g.get(who, "conditions") or []), "carrying": _held(world, who),
            "arts": [{"art": s, "stage": "已会", "learned": True, "detail": s} for s in g.get(who, "skills") or []],
            "mood": actor.mood(world, who), "intent": g.get(who, "intent"),
            "stance": {"word": st[0], "why": st[1]} if st else None, "ties": ties(world, who)}
