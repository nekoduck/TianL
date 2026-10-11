"""
[INPUT]: 依赖 world/effects 的 resolve / place / usable、world/access 的 distances / exits、world/situation 的 around / party / quests、
         world/lexicon 的 leaks / secret_hits、world/adjudicate 的 names / targets，World 门面（graph / player / knowledge / here）
[OUTPUT]: 对外提供 check()（编剧拟的选项过出口检查 → [(文字, 对象 id 列表)] 恰好三项）
[POS]: world 层的选项出口检查——选项在落账之后由编剧拟定，再由规则验收：对象须够得着或走得到、不得说破未揭的隐情与后台术语、
       三项各不相同、有人刚对主角开口则至少一项回应他、主角上回合越权未演之举优先补进来；不合格的项以规则生成的兜底项替换。
       对象随选项一并交还引擎，玩家选中即成为下一回合的授意范围——选项与授意从此是同一份数据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

from . import access, adjudicate, effects, lexicon, situation

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
    """兜底项：导演旧写法或离线说书人给的选项，再是推进未了之事、与身边之人攀谈、走一条出路、歇息——都只指向够得着的东西。"""
    out = [(o, []) for o in pack_options]
    for goal, meta in situation.quests(world).items():
        if goal in world.player["threads"]:
            out.append((f"继续：{goal}"[:20], [a for a in meta.get("about", []) if _reachable(world, a, "寻")]))
    out += [(f"与{p}攀谈", [p]) for p in sorted(situation.around(world))[:2]]
    out += [(f"前往{e['name']}", [e["name"]]) for e in access.exits(world)[:2]]
    out += [("歇息片刻", []), ("四下察看", [])]
    return out


def check(world, options: list[dict], addressed=(), candidates=(), fallback=()) -> list[tuple[str, list[str]]]:
    """验收编剧拟的选项，返回恰好三项 (文字, 对象)。fallback：导演旧写法给的选项或离线说书人的朴素选项。"""
    tab, _ = adjudicate.names(world)
    secrets = [(e["src"], e["rel"], e["dst"]) for e in world.graph.edges
               if e.get("secret") and not world.knowledge.knows_secret(e)]
    picked: list[tuple[str, list[str]]] = []

    def fine(text, ids) -> bool:
        return bool(text) and not lexicon.leaks(text) and not lexicon.secret_hits(text, secrets, tab) \
            and all(_reachable(world, i, text, ids) for i in ids) and text not in [t for t, _ in picked] \
            and not (ids and any(set(ids) == set(o) and t[:2] == text[:2] for t, o in picked))

    for o in options:
        text = str(o.get("text") or "").strip()
        ids = sorted(adjudicate.targets(world, text, o.get("targets") or []))
        if fine(text, ids):
            picked.append((text, ids))
    for want in candidates:  # 上回合越权未演之举：玩家想做，自己选
        ids = sorted(adjudicate.targets(world, want))
        if not any(set(ids) & set(o) for _, o in picked) and fine(want, ids):
            picked = picked[:SIZE - 1] + [(want, ids)]
    for p in dict.fromkeys(addressed):  # 有人刚对主角开口：至少一项回应他
        if p in situation.around(world) and not any(p in o for _, o in picked):
            picked = picked[:SIZE - 1] + [(f"回应{p}", [p])]
    for text, ids in _fallbacks(world, fallback):
        if len(picked) >= SIZE:
            break
        ids = sorted(adjudicate.targets(world, text, ids))
        if fine(text, ids):
            picked.append((text, ids))
    return picked[:SIZE]
