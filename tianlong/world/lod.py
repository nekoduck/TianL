"""
[INPUT]: 依赖 world/graph 的 holds（前提核对口径）、world/situation 的 entangled / CUSTODY（纠缠与拘押）、world/effects 的 describe（只记成立之事时的代笔），
         world/world 的 World 门面（graph / clock / canon / done / taint / apply / record）
[OUTPUT]: 对外提供 entangled()、tiers()、lod1_scope()、absorb()、split_due()、upcoming()、verdict()、dirt()、broken()、settle()
[POS]: world 层的叙事 LOD 调度器——只做确定性判定（谁在哪一层、何事到期、是否被污染），
       把需要 LLM 的工作以"任务"形式交给 engine：远方到期原著场外结算，此地到期原著一回合一桩交导演作主干；
       场外剧情的后果经 effects 落账为真相，并盖原著排定之日的日戳（此地亲见者盖今日）。
       账本只记已成立之事：场外的说法在后果全数成立时才照录，有不成立的只记成立的部分，一事无成则不入账；
       原著的隐含前提——死者不再登场、正与主角同在一处的人分身不得、主角手中之物不会凭空飞走、救人之事须那人仍受制；
       情境前提(~关系/!关系)与属性前提同一口径(graph.holds)；与主角故事纠缠之人(同行者、未了之事所系者)的场外原著前提已破即作罢、不唤史官——他们的行止只听导演与此地剧情
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from . import situation
from .effects import describe
from .graph import holds

NEAR = 1  # 一日路程之内皆为近处：0 日路相连的山门、洞府同属一簇，不以跳数计


# ============================================================
#  分层：LOD0 = 玩家所在地；LOD1 = 一日可达的近处；LOD2 = 远端大世界（按道路距离，不按跳数——半数道路是 0 日路）
# ============================================================
def tiers(world) -> dict[str, int]:
    dist = world.graph.distances(world.here)
    return {loc: 0 if loc == world.here else 1 if dist.get(loc, NEAR + 1) <= NEAR else 2
            for loc in world.graph.where(type="location")}


def lod1_scope(world) -> tuple[list[str], set[str]]:
    """LOD1 推演对象：近处怀有图谋(agenda)、未隐匿的活人。"""
    ring = {loc for loc, t in tiers(world).items() if t == 1}
    g = world.graph
    actors = [p for p in g.where(type="person") if g.get(p, "location") in ring and g.get(p, "agenda")
              and g.get(p, "status") != "dead" and not g.get(p, "hidden")]
    return actors, ring


MATERIAL = {"status", "location", "holder", "faction", "title"}  # 江湖传得开的变化：生死、去留、易手、改换门庭


def _told(world, claim: str, applied: list, rejected: list, bare: bool = True) -> str | None:
    """场外之事入账的一句话：后果全数成立才照录其说法；有不成立的，只记成立的要事（说法里多半正写着那不成立之事）；
    一事无成则不入账。bare 为真时，本无后果的叙事(原著里的一番谈话)照录；推演者空口无凭的战报则不算数。"""
    if rejected:
        facts = [describe(op) for op in applied if op["op"] in ("link", "unlink") or op.get("key") in MATERIAL]
        return "；".join(facts).replace("主角", world.player["name"]) or None
    return claim if applied or bare else None


def absorb(world, reports: list[dict], scope: set[str]) -> list[dict]:
    """LOD1 战报落账：只收推演区域之内的事；后果经 effects 校验执行，战报按 _told 的口径成为真相并开始传播。"""
    events = []
    for r in reports:
        where = r.get("where")
        if not isinstance(where, str) or where not in scope:
            continue
        applied, rejected = world.apply(r.get("effects", []), "lod1", scope)
        summary = _told(world, f"{r.get('event', '')}：{r.get('result', '')}", applied, rejected, bare=False)
        if summary:
            events.append(world.record(summary, where, applied, "lod1"))
    return events


# ============================================================
#  LOD2：原著平行轨道 + 因果涟漪(dirty flag)
#  到期即结算，永远按 order 依次：远事不被近事插队；此地上演的一回合只交出一桩，让主角有介入的余地
# ============================================================
def _pending(world) -> list[dict]:
    done = set(world.done)
    return [ev for ev in world.canon if ev["id"] not in done and ev["day"] <= world.clock.day]


def split_due(world) -> tuple[list[tuple[dict, int]], dict | None]:
    """按 order 遍历到期原著：场外的归入待结算 (事件, 层级)；遇到第一桩在此地上演的即停下，把它交出作本回合主干。"""
    t, offstage = tiers(world), []
    for ev in _pending(world):
        tier = t.get(ev["where"], 2)
        if tier == 0:
            return offstage, ev
        offstage.append((ev, tier))
    return offstage, None


def upcoming(world, skip: set[str] = frozenset(), within: int = 7, limit: int = 3) -> list[tuple[dict, int]]:
    """近处(LOD0/1)数日内将上演、尚未结算的原著，连同距今日数——交导演伏笔，不可提前上演。"""
    t, today, done = tiers(world), world.clock.day, set(world.done) | set(skip)
    out = [(ev, ev["day"] - today) for ev in world.canon
           if ev["id"] not in done and ev["day"] <= today + within and t.get(ev["where"], 2) <= 1]
    return out[:limit]


entangled = situation.entangled  # 与主角故事纠缠之人：定义归情境层，effects 也据此拦场外调遣


def _unmet(world, ev: dict) -> list[tuple]:
    g = world.graph
    touched = sorted(set(ev["actors"]) | {op.get("id") for op in ev["effects"] if isinstance(op.get("id"), str)})
    unmet = [(nid, key, want) for nid, key, want in ev["requires"] if not holds(g, nid, key, want)]
    unmet += [(op["src"], "~" + op["rel"], op["dst"]) for op in ev["effects"]  # 救人的原著，须那人仍受制：已被主角救走便不必再救
              if op.get("op") == "unlink" and op.get("rel") in situation.CUSTODY and not holds(g, op["src"], "~" + op["rel"], op["dst"])]
    unmet += [(a, "status", "alive") for a in ev["actors"] if g.get(a, "status") == "dead"]       # 死者不再登场
    unmet += [(i, "holder", "非主角") for i in touched if g.kind(i) == "item" and g.get(i, "holder") == "player"]  # 主角手中之物
    if ev["where"] != world.here:  # 场外之事：正与主角同在一处的人分身不得——同伴随行，他的原著便在别处断了
        unmet += [(n, "location", ev["where"]) for n in touched if g.kind(n) == "person" and g.get(n, "location") == world.here]
        unmet += [(n, "纠缠", ev["where"]) for n in touched if n in entangled(world) and g.get(n, "location") != world.here]
    return unmet


def broken(world, ev: dict) -> bool:
    """原著前提是否已被破坏（区别于仅被污染，含"相关者正在主角身边"）：决定史官失联时的兜底——前提破则不发生。"""
    return bool(_unmet(world, ev))


def _why(world, nid: str, key: str, want) -> str:
    if key == "纠缠":
        return f"{nid}正与主角同行或系于主角未了之事，其行止已不照原著"
    if key[:1] == "~":
        return f"{nid}与{want}之间已无「{key[1:]}」"
    if key[:1] == "!":
        return f"{nid}与{want}之间已有「{key[1:]}」"
    cur = world.graph.get(nid, key)
    if key == "location" and cur == world.here:
        return f"{nid}正与主角同在{world.here}，无法在{want}现身"
    if key == "holder" and cur == "player":
        return f"{nid}正在主角手中"
    if key == "status" and cur == "dead" and want != "dead":
        return f"{nid}已死"
    return f"{nid}的{key}应为{want}，实为{cur}"


def dirt(world, ev: dict) -> list[str]:
    reasons = [_why(world, *u) for u in _unmet(world, ev)]
    touched = set(ev["actors"]) | {r[0] for r in ev["requires"]} | {op.get("id") for op in ev["effects"]}
    reasons += [f"{n}曾受主角影响" for n in sorted(touched & world.taint)]
    return reasons


def verdict(world, ev: dict, tier: int) -> tuple[str, list[str]]:
    """裁定一桩到期的场外原著：canon 照原著 / chronicle 唤醒史官 / skip 悄然不发生。
    未被扰动的原著照常上演；史官只为"附近的破局"与"被扰动的大事"醒来，远方小事破局则作罢。"""
    reasons = dirt(world, ev)
    if not reasons:
        return "canon", []
    if broken(world, ev):
        if set(ev["actors"]) & entangled(world):  # 纠缠者的行止只听导演与此地剧情：前提已破，连史官也不唤，作罢
            return "skip", reasons
        return ("chronicle" if ev["weight"] >= 2 or tier <= 1 else "skip"), reasons
    return ("chronicle" if ev["weight"] >= 2 else "canon"), reasons


def settle(world, ev: dict, outcome: dict, origin: str, day: int | None = None, witnessed: bool | None = None) -> dict | None:
    """结算一桩原著事件。outcome: {happens, summary, effects}；干净事件直接传入 ev 本身。
    真相盖原著排定之日的日戳——主角亲眼所见的那一桩则盖今日(day)：迟到才演的戏，传闻不该已在路上走了十天。"""
    world.done.append(ev["id"])
    if not outcome.get("happens", True):
        return None
    scope = set(ev["actors"]) | {ev["where"]} | {r[0] for r in ev["requires"]} | {op.get("id") for op in ev["effects"]}
    applied, rejected = world.apply(outcome.get("effects", []), origin, scope)
    summary = _told(world, outcome.get("summary") or ev["summary"], applied, rejected)
    if summary is None:
        return None
    return world.record(summary, ev["where"], applied, origin, ev["weight"], ev.get("public", True),
                        day=ev["day"] if day is None else day, witnessed=witnessed)
