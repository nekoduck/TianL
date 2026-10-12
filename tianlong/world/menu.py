"""
[INPUT]: 依赖 world/effects 的 resolve / place / usable、world/access 的 distances / exits(方向措辞与来路)、world/situation 的 around / party / quests / captors / imperiled、
         world/lexicon 的 leaks / secret_hits、world/pacing 的 tired（一再重复的诉求）、world/adjudicate 的 names / targets，world/perspective 的 handle（不识名之人的叫法），World 门面（graph / player / knowledge / here）
[OUTPUT]: 对外提供 check()（编剧拟的选项过出口检查 → [(文字, 对象 id 列表)] 恰好三项；later 是此后槽的兜底项，标了尺度而没有此后之事时补位）
[POS]: world 层的选项出口检查——选项在落账之后由编剧拟定，再由规则验收：对象须够得着或走得到、不得说破未揭的隐情与后台术语、
       三项各不相同、至少一件「此后」之事(槽位覆盖，v4；险境里不要求)、有人刚对主角开口则至少一项回应他(一再重复同一诉求者除外，见 pacing)、主角上回合越权未演之举优先补进来；不合格的项以规则生成的兜底项替换——兜底看局面：途中先给续行，出路按方向措辞、不走回头路、不报节点全名，身处险境(命悬一线、受制于人)只给眼前的应对，不给走开与歇息；对不识名之人只用叫法。
       对象随选项一并交还引擎，玩家选中即成为下一回合的授意范围——选项与授意从此是同一份数据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

from . import access, adjudicate, effects, lexicon, pacing, perspective, situation

SIZE = 3
SEEK = re.compile(r"寻|找|去|往|赴|追|访|打听|探听|等候|守候|求见|传信|捎信|托人")  # 指向不在身边之人的选项，须是去找他、打听他


def _reachable(world, nid: str, text: str = "", ids=()) -> bool:
    """选项的对象够不够得着：地点走得到；人在身边或同行——不在身边的，选项须是去找他、打听他（或同时指向一处走得到的地方）；
    物在身上、身边，或主角知道在谁手里。"""
    g = world.graph
    kind = g.kind(nid)
    if kind == "location":
        return nid == world.here or nid in access.distances(world, world.here)
    if kind == "person":
        if g.get(nid, "status") == "dead":
            return False
        if nid in situation.around(world) or nid in situation.party(world):
            return True
        return bool(world.knowledge.view(nid).get("location")) and \
            (bool(SEEK.search(text)) or any(world.graph.kind(i) == "location" for i in ids))
    if kind == "item":
        if nid in world.player["inventory"]:
            return True
        holder = g.get(nid, "holder")
        return effects.usable(world, nid) and not g.get(nid, "hidden") and \
            (effects.place(world, nid) in situation.near(world) or (holder and world.knowledge.knows(holder)))
    return kind in ("group", "skill", "faction")


def _fallbacks(world, pack_options) -> list[tuple[str, list[str]]]:
    """兜底项看局面：导演旧写法或离线说书人给的选项；途中则先是续行；再是推进未了之事、与身边之人攀谈、
    近处一条不是来路的出路(按方向措辞，不报节点全名)、歇息——身处险境(命悬一线、受制于人)时只给眼前的应对，不给走开与歇息。"""
    me = world.player
    peril = situation.imperiled(world) or bool(situation.captors(world, "player"))
    out = [(o, []) for o in pack_options]
    if me.get("en_route") and not peril:
        out.append((f"继续赶往{me['en_route']['to']}", [me["en_route"]["to"]]))
    for goal, meta in situation.quests(world).items():
        if goal in me["threads"]:
            out.append((f"继续：{goal}"[:20], [a for a in meta.get("about", []) if _reachable(world, a, "寻")]))
    out += [(f"与{perspective.handle(world, p)}攀谈", [p]) for p in sorted(situation.around(world))[:2]]
    if not peril:
        out += [(e["way"], [e["name"]]) for e in access.exits(world) if e["days"] == 0 and not e["back"]][:2]
        out.append(("歇息", []))
    out.append(("四下察看", []))
    return out


def check(world, options: list[dict], addressed=(), candidates=(), fallback=(), later=()) -> list[tuple[str, list[str]]]:
    """验收编剧拟的选项，返回恰好三项 (文字, 对象)。fallback：导演旧写法给的选项或离线说书人的朴素选项；
    later：此后槽的兜底项(story/choices 看局面给出)——三项里没有一件「此后」之事(编剧标的尺度)，就以它换下最后一项。"""
    tab, _ = adjudicate.names(world)
    secrets = [(e["src"], e["rel"], e["dst"]) for e in world.graph.edges
               if e.get("secret") and not world.knowledge.knows_secret(e)]
    picked: list[tuple[str, list[str]]] = []

    def fine(text, ids) -> bool:
        return bool(text) and not lexicon.leaks(text) and not lexicon.secret_hits(text, secrets, tab) \
            and all(_reachable(world, i, text, ids) for i in ids) and text not in [t for t, _ in picked] \
            and not (ids and any(set(ids) == set(o) for _, o in picked))  # 三项各有所指：同一对象只留一项

    for o in options:
        text = str(o.get("text") or "").strip()
        ids = sorted(adjudicate.targets(world, text, o.get("targets") or []))
        if fine(text, ids):
            picked.append((text, ids))
    for want in candidates:  # 上回合越权未演之举：玩家想做，自己选
        ids = sorted(adjudicate.targets(world, want))
        if not any(set(ids) & set(o) for _, o in picked) and fine(want, ids):
            picked = picked[:SIZE - 1] + [(want, ids)]
    nagging = {k.split("|")[0] for k in pacing.tired(world.player.get("pacing") or [], "pleas")}
    for p in dict.fromkeys(addressed):  # 有人刚对主角开口：至少一项回应他——一再重复同一句诉求的人不再硬塞「回应」，免得原地打转
        if p in situation.around(world) and p not in nagging and not any(p in o for _, o in picked):
            picked = picked[:SIZE - 1] + [(f"回应{perspective.handle(world, p)}", [p])]
    scales = {str(o.get("text") or "").strip(): o.get("scale") for o in options}
    tagged = any(scales.values())  # 编剧照槽位标了尺度才查覆盖：没标尺度的旧写法无从判断哪一项是此后
    if later and tagged and not any(scales.get(t) == "此后" for t, _ in picked):  # 槽位覆盖：至少一件持续之事，时间才往前走
        for text, ids in later:
            ids = sorted(adjudicate.targets(world, text, ids))
            if fine(text, ids):
                picked = picked[:SIZE - 1] + [(text, ids)]
                break
    for text, ids in _fallbacks(world, fallback):
        if len(picked) >= SIZE:
            break
        ids = sorted(adjudicate.targets(world, text, ids))
        if fine(text, ids):
            picked.append((text, ids))
    return picked[:SIZE]
