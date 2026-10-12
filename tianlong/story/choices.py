"""
[INPUT]: 依赖 story/stakes（时限）、world/growth 的 studiable / progress（研习对象与进度）、world/access 的 exits（出路与日程）、world/situation 的 imperiled / captors / quests、
         world/body 的 severity，world/perspective 的 handle；World 门面的 player / graph（鸭子类型）
[OUTPUT]: 对外提供 slots()（给编剧的三个槽位：此刻 / 此后 / 机缘，各写明它要回答什么与可用的素材）、later()（此后槽的兜底项 [(文字, 对象)]，供 menu.check 补位）、
          SCALES、peril()
[POS]: story 层的选项编排——选项从「正文的附录」变成「先定槽位、再让编剧措辞」：
       A 此刻：用还没试过的路数推进本场之问；B 此后：一件持续之事或一次过场(赶路、研习、养伤、等人、找人)，写出代价；C 机缘：一个两难或机会(时限冲突、图谋的破绽)。
       槽位只规定每项回答什么，不规定措辞；险境里 B 槽改为脱身一类的此刻之举。编剧在每项后写「｜尺度：此刻/此后/机缘」，
       引擎记下玩家所选之举的尺度：选了此后，下一回合的场记要求略写、时长按那件事的规则结算——选项与时间从此互相咬合
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from ..world import access, body, growth, situation
from . import stakes

SCALES = ("此刻", "此后", "机缘")


def peril(world) -> bool:
    return situation.imperiled(world) or bool(situation.captors(world, "player"))


def later(world) -> list[tuple[str, list[str]]]:
    """此后槽的素材(也是兜底项)：续行、出路(带日程)、研习手边的秘籍、带伤歇息、去推进未了之事。险境里没有此后。"""
    if peril(world):
        return []
    me, out = world.player, []
    if me.get("en_route"):
        out.append((f"继续赶往{me['en_route']['to']}（余{me['en_route']['left']}日）", [me["en_route"]["to"]]))
    for src in [b for b in growth.studiable(world) if world.graph.kind(b) == "item"][:1]:  # 手边的秘籍；求教要对人开口，是此刻之举
        out.append((f"静心研习{src}（约一个时辰）", [src]))
    if body.severity(world) or me["hp"] < me["max_hp"] * 0.8:
        out.append(("寻个僻静处歇息养伤（半日）", []))
    for e in access.exits(world):
        if e["days"] >= 1 and not e["back"]:
            out.append((f"{e['way']}（约{e['days']}日）", [e["name"]]))
            break
    return out


def slots(world) -> list[str]:
    """给编剧的三个槽位说明(每行一个)。"""
    sc, hurry = world.player["scene"] or {}, stakes.urgent(world)
    a = f"A 此刻：用一种还没试过的路数(力、智、情、术、退)推进本场之问「{sc.get('ask') or '眼前之事'}」"
    if sc.get("tried"):
        a += f"（已试：{'、'.join(sc['tried'][-3:])}）"
    if peril(world):
        b = "B 此后→此刻：主角身处险境，这一项改为脱身或自保的此刻之举"
    else:
        stuff = [t for t, _ in later(world)]
        b = "B 此后：一件持续之事或一次过场(赶路、研习、养伤、等人、去找某人)，写出代价或耗时" + (f"；可用：{'、'.join(stuff)}" if stuff else "")
    hooks = []
    if hurry:
        hooks.append(f"时限「{hurry[0]['what']}」{hurry[1]}")
    g = world.graph
    hooks += [f"{p}的图谋" for p in sorted(situation.around(world)) if g.get(p, "agenda")][:2]
    c = "C 机缘：一个两难或一个机会" + (f"（可从{'、'.join(hooks)}里找）" if hooks else "；没有时，换一种与 A 迥异的路数")
    return [a, b, c]
