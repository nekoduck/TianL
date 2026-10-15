"""
[INPUT]: 依赖 world/trade 的 shop（v12 此处的铺子）、world/effects 的 resolve / place / usable、world/access 的 distances / exits(方向措辞与来路)、world/situation 的 around / party / quests / captors / imperiled、
         world/lexicon 的 leaks / secret_hits、world/pacing 的 tired（一再重复的诉求）、world/adjudicate 的 names / targets / marked / pick（v12 授意标记不是实体、对象栏的名字）、world/scenery 的 TRIFLE 与 world/stock 的 is_cash（v12 让位先挑只指着琐物碎银的），world/perspective 的 handle（不识名之人的叫法），World 门面（graph / player / knowledge / here）
[OUTPUT]: 对外提供 SEEK_PERSON / seeking()（v12 玩家要找的人）、FORCED / ANSWER（v12 强插至多几项、回应的措辞）、SHOPPING（v12 离不开铺子的事）、TOPIC（v12 话题里的人：名字前后的字眼）、SIMILAR / alike()（v12 两句是不是同一件事：去标点后的二字组 Jaccard）、check()（编剧拟的选项过出口检查 → [(文字, 对象 id 列表)] 恰好三项；later 是此后槽的兜底项，标了尺度而没有此后之事时补位）、OFFERED_TURNS / STALE / offer()（v12 P2-2 琐物衰减：记下入选选项的对象）
[POS]: world 层的选项出口检查——选项在落账之后由编剧拟定，再由规则验收：对象须够得着或走得到、不得说破未揭的隐情与后台术语、
       三项各不相同、至少一件「此后」之事(槽位覆盖，v4；险境里不要求)、兜底攀谈先找与主角有过交集的人、再找叫得出名字的人(v5，不按字码挑人)、有人刚对主角开口则至少一项回应他(一再重复同一诉求者除外，见 pacing)、主角上回合越权未演之举优先补进来；不合格的项以规则生成的兜底项替换——兜底看局面：途中先给续行，出路按方向措辞、不走回头路、不报节点全名，身处险境(命悬一线、受制于人)只给眼前的应对，不给走开与歇息；对不识名之人只用叫法。
       对象随选项一并交还引擎，玩家选中即成为下一回合的授意范围——选项与授意从此是同一份数据
       v12 选项链路：授意标记(@书写、@交易)不是实体，可达与去重只看实体、交还的对象不带标记(下回合引擎从原话重算)；买卖住店雇人此处没有铺子也没有当值伙计即办不成；
       只对物理对象验可达、话题放行——【对象】栏的实体与文字里的人是物理对象(报某人之名、问起某人的下落不是)，对象栏不空时文字里的地点器物是话题；眼前的遗体够得着；对象相同且文字相近才去重——同指段誉的挟持与劝和是两条路；
       按优先级合并、不按下标覆盖(越权候选 > 须回应 > 此后，已满足的跳过；满了才让位，强插至多两项、编剧原拟至少留一项)，须回应只认收尾时仍悬着的话(adjudicate.hanging)，措辞按那一句的主题；危局里(pacing.danger)兜底由状态生成，不给出路、歇息、四下察看；本回合望见的人与知其所在同等对待；
       P2-2 琐物衰减：只指着寻常之物或碎银的选项，这几样近三回合已入选两回(危局里一回)即不再入选(_stale 读黑板 offered，引擎验收之后经 offer 记下)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import re

from . import access, adjudicate, bond, crowd, effects, growth, lexicon, pacing, perspective, scenery, situation, stock, trade

log = logging.getLogger("tianlong")
SIZE = 3
FORCED = 2  # 强插(让位)至多几项(v12)：编剧原拟至少留一项
ANSWER = (("盘问", "答{}所问"), ("拦阻", "与{}理论去留"), ("催促", "依{}所言"), ("赔罪", "受{}这一礼"))  # 回应的措辞按那一句的主题(v12)
SEEK = re.compile(r"寻|找|去|往|赴|追|访|打听|探听|等候|守候|求见|传信|捎信|托人")  # 指向不在身边之人的选项，须是去找他、打听他
SEEK_PERSON = re.compile(r"寻|找|访|打听|探听|求见")  # 玩家要找某人(v12)：须与人名或叫法在同一分句——「往后山去，避开段誉」不是寻他
SHOPPING = re.compile(r"(?<!收)买|购|(?<!出)卖|典当|住店|投宿|打尖|结账|会钞|雇")  # 离不开铺子的事(v12)：此处没有铺子、眼前也没有当值的伙计，就办不成
TOPIC = (re.compile(r"(?:提起|说起|问起|谈起|冒充|假冒|借|以)$"),                    # 话题里的人(v12)：名字前是说起、冒充、借、以
         re.compile(r"^(?:之名|的名头|的名号|的名义|的下落|的来历|的往事|报仇)"))  # 名字后是之名、的下落、报仇——说的是他，不是要碰到他


SIMILAR = 0.6  # 两项物理对象相同、去标点后的二字组重合(Jaccard)过此，才算同一件事(v12)


def _grams(text: str) -> set[str]:
    t = re.sub(r"[\W_]", "", text)
    return {t[i:i + 2] for i in range(len(t) - 1)} or {t}


def alike(a: str, b: str) -> bool:
    """两句是不是同一件事的两种说法(v12)：「挺身护住段誉」与「挺身护住段誉退后」是，「挟持段誉保命」与「劝段誉讲和脱身」不是。"""
    x, y = _grams(a), _grams(b)
    return len(x & y) / max(1, len(x | y)) >= SIMILAR


def _things(world, text: str, given=()) -> list[str]:
    """选项所指的实体(v12)：授意标记(@书写、@交易)不是实体——可达与去重只看实体，交还引擎的对象也不带标记(下回合从原话重算)。"""
    return sorted(i for i in adjudicate.targets(world, text, given) if not adjudicate.marked(i))


def seeking(world, text: str, aim=()) -> list[str]:
    """玩家原话里要找的人(v12)：所指之人里，名字或叫法与寻、找、访、打听、求见同在一个分句的——引擎记作 rules["seek"]，小片区里寻人而至即遇。"""
    tab, kinds = adjudicate.names(world)
    out = []
    for clause in lexicon.CLAUSE.split(text or ""):
        if SEEK_PERSON.search(clause):
            out += [n for n, _, _ in lexicon.find(clause, tab) if kinds.get(n) == "person" and n in aim and n not in out]
    return out


def _topic(text: str, a: int, b: int) -> bool:
    before, after = TOPIC
    return bool(before.search(text[:a]) or after.match(text[b:]))


def _objects(world, text: str, given=()) -> tuple[list[str], list[str]]:
    """选项所指 (全部实体, 物理对象)(v12)：只对物理对象验可达，话题放行——
    【对象】栏解析出的实体是物理对象；文字里的人也是，除非他在话题里(报马五德之名、问起段誉的下落)；
    文字里的地点、器物在【对象】栏不空时是话题(只过泄密与后台术语)，为空时照旧验可达(旧写法)。"""
    every = _things(world, text, given)
    tab, kinds = adjudicate.names(world)
    surface = dict(tab) if given else {}
    body = {x for x in (adjudicate.pick(world, t, surface) for t in given if t) if isinstance(x, str) and world.graph.has(x)}
    talked = set()
    for nid, a, b in lexicon.find(text, tab):
        if kinds.get(nid) == "person":
            (talked if _topic(text, a, b) else body).add(nid)
    if not given:  # 旧写法没有对象栏：文字里认出的(话题里的人除外)都照旧验可达
        body |= set(every) - (talked - body)
    return every, sorted(i for i in body if not adjudicate.marked(i))


def _shopless(world, text: str) -> bool:
    """选项要在铺子里才办得成(买卖、住店、雇人)，此处却没有铺子、眼前也没有当值的伙计(v12)。大喝、卖个破绽不算。"""
    if not SHOPPING.search(lexicon.TRADE_NOT.sub("", text)):
        return False
    return not trade.shop(world) and not any(world.graph.get(p, "staff") for p in situation.around(world))


def _reachable(world, nid: str, text: str = "", ids=()) -> bool:
    """选项的对象够不够得着：地点走得到；人在身边或同行——不在身边的，选项须是去找他、打听他（或同时指向一处走得到的地方）；
    物在身上、身边，或主角知道在谁手里。"""
    g = world.graph
    kind = g.kind(nid)
    if kind == "location":
        return nid == world.here or nid in access.distances(world, world.here)
    if kind == "person":
        if g.get(nid, "status") == "dead":
            return nid in situation.bodies(world)  # 眼前的遗体(v12)：搜检、抬走都够得着
        if nid in situation.around(world) or nid in situation.party(world):
            return True
        return (bool(world.knowledge.view(nid).get("location")) or nid in situation.sighted(world)) and \
            (bool(SEEK.search(text)) or any(world.graph.kind(i) == "location" for i in ids))  # v12 本回合望见的人：与知其所在同等对待
    if kind == "item":
        if nid in world.player["inventory"]:
            return True
        holder = g.get(nid, "holder")
        return effects.usable(world, nid) and not g.get(nid, "hidden") and \
            (effects.place(world, nid) in situation.near(world) or (holder and world.knowledge.knows(holder)))
    return kind in ("group", "skill", "faction")


def _fallbacks(world, pack_options, danger=None, said=None) -> list[tuple[str, list[str]]]:
    """兜底项看局面：导演旧写法或离线说书人给的选项；途中则先是续行；再是推进未了之事、与身边之人攀谈、
    近处一条不是来路的出路(按方向措辞，不报节点全名)、歇息、四下察看。
    v12 危局里(pacing.danger)不给出路、歇息、四下察看，改由状态生成：被围即冲出那一群的包围、受制即挣脱、同伴受制即护住他、
    眼前有敌对之人即向他出言周旋，无论哪种都留一项不带对象的「强撑伤势，寻隙脱身」——命悬一线而无人可指时，它就是兜底。"""
    me = world.player
    danger = pacing.danger(world) if danger is None else danger
    out = [(o, []) for o in pack_options]
    if danger:
        out += _rescue(world, said) + [("强撑伤势，寻隙脱身", [])]
    elif me.get("en_route"):
        out.append((f"继续赶往{me['en_route']['to']}", [me["en_route"]["to"]]))
    for goal, meta in situation.quests(world).items():
        if goal in me["threads"]:
            out.append((f"继续：{goal}"[:20], [a for a in meta.get("about", []) if _reachable(world, a, "寻")]))
    g = world.graph  # 攀谈先找与主角有过交集的人、再找叫得出名字的人——不按字码挑人
    salient = sorted(situation.around(world), key=lambda p: (-len((g.get(p, "bond") or {}).get("log", [])),
                                                          not perspective.knows(world, "player", p), p))
    out += [(f"与{perspective.handle(world, p)}攀谈", [p]) for p in salient[:2]]
    if not danger:
        out += [(e["way"], [e["name"]]) for e in access.exits(world) if e["days"] == 0 and not e["back"]][:2]
        out.append(("歇息", []))
        out.append(("四下察看", []))
    return out


def _rescue(world, said=None) -> list[tuple[str, list[str]]]:
    """危局里由状态生成的应对(v12)：冲出包围、挣脱、护住同伴、向敌对之人出言周旋。"""
    g, out = world.graph, []
    sieges = crowd.besiegers(world)
    out += [(f"设法冲出{perspective.handle(world, s)}的包围", [s]) for s in sieges]
    out += [(f"设法挣脱{perspective.handle(world, c)}", [c]) for c in situation.captors(world, "player") if c not in sieges]
    close = situation.around(world) | set(crowd.squads(world))
    out += [(f"护住{perspective.handle(world, p)}", [p]) for p in situation.party(world)
            if any(c in close for c in situation.captors(world, p))]
    around = situation.around(world)
    foes = [c for c in situation.captors(world, "player") if c in around]
    foes += [p for p, text in (said or {}).items() if p in around and pacing.TENSE & set(pacing.tag(text))]
    foes += sorted(p for p in around if (bond.stance(world, p) or ("",))[0] in ("嫌恶", "仇视"))
    out += [(f"向{perspective.handle(world, p)}出言周旋", [p]) for p in list(dict.fromkeys(foes))[:1]]
    return out


def _petty(world, nid: str) -> bool:
    g = world.graph
    return g.kind(nid) == "item" and (g.get(nid, "grade") == scenery.TRIFLE or stock.is_cash(g, nid))


OFFERED_TURNS, STALE = 3, 2  # 琐物衰减(v12 P2-2)：只指着琐物碎银的选项，这几样近三回合已入选两回即不再入选(危局里一回)


def _stale(world, body, danger=None) -> bool:
    """只指着寻常之物或碎银的选项(v12 P2-2)：这几样近 OFFERED_TURNS 回合已在入选的选项里出现 STALE 回(危局里一回)即不再入选——
    日志第 1、2、4、5、6 回五次给碎银。指着人、地、要物的不衰减。"""
    if not body or not all(_petty(world, i) for i in body):
        return False
    seen = sum(1 for objs in (world.player.get("offered") or [])[-OFFERED_TURNS:] if set(objs) & set(body))
    return seen >= (1 if danger else STALE)


def offer(world, picked) -> None:
    """记下本回合入选选项的对象(v12 P2-2)：引擎在验收之后调，黑板 offered 只留近 OFFERED_TURNS 回合。check 本身不写黑板(验收可反复调)。"""
    objs = sorted({i for _, ids in picked for i in ids if isinstance(i, str)})
    world.player.set("offered", ((world.player.get("offered") or []) + [objs])[-OFFERED_TURNS:])


def _answer(world, p: str, said=None) -> str:
    """须回应的措辞按此人对主角那一句的主题(v12)：盘问即答其所问、拦阻即理论去留、催促即依其所言、赔罪即受这一礼，其余回应他。"""
    tags = pacing.tag((said or {}).get(p) or "")
    word = next((w for t, w in ANSWER if t in tags), "回应{}")
    return word.format(perspective.handle(world, p))


def _unattainable(world, text: str) -> bool:
    """选项许了研习账上够不着的进境(v13)：「练至大成」而下一阶还差光阴、或还要再隔几日——不给练不动的选项（研习账说了算，growth.ceiling）。"""
    levels = [lexicon.mastery_level(w) for w in lexicon.mastery(text, "player")]
    levels = [lv for lv in levels if lv > 0]
    if not levels:
        return False
    tab, _ = adjudicate.names(world)
    arts = {n for n, _, _ in lexicon.find(text, tab) if world.graph.kind(n) == "skill"}
    return max(levels) > growth.ceiling(world, arts)


def check(world, options: list[dict], addressed=(), candidates=(), fallback=(), later=(), said=None, danger=None) -> list[tuple[str, list[str]]]:
    """验收编剧拟的选项，返回恰好三项 (文字, 对象)。fallback：导演旧写法给的选项或离线说书人的朴素选项；
    later：此后槽的兜底项(story/choices 看局面给出)；addressed：收尾时仍悬着话的人(adjudicate.hanging)；said：各人对主角说的那一句(定回应的措辞)。
    v12 按优先级合并，不按下标覆盖：先收编剧选项里过了验收的(保持原序)，再依次看 越权候选 > 须回应 > 此后——已满足的跳过；
    不足三项直接追加，满了才找一项让位(没满足任何要求的编剧原拟：对象与别项重复的 > 只指着琐物碎银的 > 最后一项)，
    强插至多 FORCED 项、编剧原拟至少留一项，第三条要求就此作罢并记日志；仍不足三项以兜底补齐。"""
    tab, _ = adjudicate.names(world)
    secrets = [(e["src"], e["rel"], e["dst"]) for e in world.graph.edges
               if e.get("secret") and not world.knowledge.knows_secret(e)]
    picked: list[tuple[str, list[str]]] = []
    bodies: dict[str, list[str]] = {}  # 选项文字 → 物理对象(v12)：可达只验它们，去重也只比它们

    def fine(text, ids, body=None) -> bool:
        body = ids if body is None else body
        return bool(text) and not lexicon.leaks(text) and not lexicon.secret_hits(text, secrets, tab) \
            and all(_reachable(world, i, text, ids) for i in body) and not _shopless(world, text) and text not in [t for t, _ in picked] \
            and not _stale(world, body, danger) and not _unattainable(world, text) \
            and not (body and any(set(body) == set(bodies.get(t, o)) and alike(text, t) for t, o in picked))  # 对象相同且文字相近才是重复(v12)：同指段誉的挟持与劝和是两条路

    def take(text, given=()) -> tuple[list[str], list[str]]:
        ids, body = _objects(world, text, given)
        bodies[text] = body
        return ids, body

    for o in options:
        text = str(o.get("text") or "").strip()
        ids, body = take(text, o.get("targets") or [])
        if fine(text, ids, body):
            picked.append((text, ids))
    mine = {t for t, _ in picked}                     # 编剧原拟：让位只在它们里挑，至少留一项
    scales = {str(o.get("text") or "").strip(): o.get("scale") for o in options}
    tagged = any(scales.values())  # 编剧照槽位标了尺度才查覆盖：没标尺度的旧写法无从判断哪一项是此后
    want_later = bool(later) and tagged
    nagging = {k.split("|")[0] for k in pacing.tired(world.player.get("pacing") or [], "pleas")}
    hang = [p for p in dict.fromkeys(addressed) if p in situation.around(world) and p not in nagging]  # 一再重复同一诉求的人不再硬塞「回应」
    cands = [(want, *take(want)) for want in candidates]
    pinned, forced = set(), 0

    def answered(p, text, ids) -> bool:
        return p in ids or perspective.handle(world, p) in text

    def needed(text, ids) -> bool:  # 这一项满足了某条要求(候选、回应、此后)：不让位
        return text in pinned or any(set(ids) & set(c) for _, c, _ in cands if c) \
            or any(answered(p, text, ids) for p in hang) or (want_later and scales.get(text) == "此后")

    def victim() -> int | None:
        pool = [k for k, (t, ids) in enumerate(picked) if t in mine and not needed(t, ids)]
        dup = [k for k in pool if bodies.get(picked[k][0]) and any(
            j != k and set(bodies.get(picked[j][0], picked[j][1])) == set(bodies[picked[k][0]]) for j in range(len(picked)))]
        petty = [k for k in pool if picked[k][1] and all(_petty(world, i) for i in picked[k][1])]
        return (dup or petty or pool or [None])[-1]

    def insert(item, why: str) -> bool:
        nonlocal forced
        if len(picked) < SIZE:  # 不足三项：直接追加，不让位
            picked.append(item)
            pinned.add(item[0])
            return True
        k = victim() if forced < FORCED and sum(t in mine for t, _ in picked) > 1 else None
        if k is None:
            log.info("选项要求作罢（%s）：%s", why, item[0])
            return False
        del picked[k]
        picked.append(item)
        pinned.add(item[0])
        forced += 1
        return True

    for want, ids, body in cands:  # 上回合越权未演之举：玩家想做，自己选(至多一条)
        if not any(set(ids) & set(o) for _, o in picked) and fine(want, ids, body):
            insert((want, ids), "越权候选")
            break
    for p in reversed(hang):  # 收尾时仍悬着的话：只回应最后一个还没被回应的人
        if not any(answered(p, t, o) for t, o in picked):
            insert((_answer(world, p, said), [p]), "须回应")
            break
    if want_later and not any(scales.get(t) == "此后" for t, _ in picked):  # 槽位覆盖：至少一件持续之事，时间才往前走
        for text, ids in later:
            ids, body = take(text, ids)
            if fine(text, ids, body):
                insert((text, ids), "此后")
                break
    for text, ids in _fallbacks(world, fallback, danger, said):
        if len(picked) >= SIZE:
            break
        ids, body = take(text, ids)
        if fine(text, ids, body):
            picked.append((text, ids))
    return picked[:SIZE]
