"""
[INPUT]: 依赖 world/world 的 World 门面（graph / clock / canon / done / taint / apply / record）
[OUTPUT]: 对外提供 tiers()、lod1_scope()、absorb()、split_due()、upcoming()、verdict()、dirt()、broken()、settle()
[POS]: world 层的叙事 LOD 调度器——只做确定性判定（谁在哪一层、何事到期、是否被污染），
       把需要 LLM 的工作以"任务"形式交给 engine：远方到期原著场外结算，此地到期原著一回合一桩交导演作主干；
       场外剧情的后果经 effects 落账为真相，并盖原著排定之日的日戳
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

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


def absorb(world, reports: list[dict], scope: set[str]) -> list[dict]:
    """LOD1 战报落账：后果经 effects 校验执行（违背世界物理的部分不成立）；战报本身成为真相并开始传播。"""
    events = []
    for r in reports:
        applied, _ = world.apply(r.get("effects", []), "lod1", scope)
        where = r.get("where")
        if world.graph.kind(where) == "location":
            events.append(world.record(f"{r.get('event', '')}：{r.get('result', '')}", where, applied, "lod1"))
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


def _holds(world, nid: str, key: str, want) -> bool:
    cur = world.graph.get(nid, key)
    return want in cur if isinstance(cur, list) and not isinstance(want, list) else cur == want


def _unmet(world, ev: dict) -> list[tuple]:
    unmet = [(nid, key, want) for nid, key, want in ev["requires"] if not _holds(world, nid, key, want)]
    if ev["where"] != world.here:  # 场外之事的隐含前提：正与主角同在一处的人分身不得——同伴随行，他的原著便在别处断了
        unmet += [(a, "location", ev["where"]) for a in ev["actors"] if world.graph.get(a, "location") == world.here]
    return unmet


def broken(world, ev: dict) -> bool:
    """原著前提是否已被破坏（区别于仅被污染，含"相关者正在主角身边"）：决定史官失联时的兜底——前提破则不发生。"""
    return bool(_unmet(world, ev))


def dirt(world, ev: dict) -> list[str]:
    g = world.graph
    reasons = [f"{nid}正与主角同在{world.here}，无法在{want}现身" if key == "location" and g.get(nid, key) == world.here
               else f"{nid}的{key}应为{want}，实为{g.get(nid, key)}" for nid, key, want in _unmet(world, ev)]
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
        return ("chronicle" if ev["weight"] >= 2 or tier <= 1 else "skip"), reasons
    return ("chronicle" if ev["weight"] >= 2 else "canon"), reasons


def settle(world, ev: dict, outcome: dict, origin: str) -> dict | None:
    """结算一桩原著事件。outcome: {happens, summary, effects}；干净事件直接传入 ev 本身。真相盖原著排定之日的日戳。"""
    world.done.append(ev["id"])
    if not outcome.get("happens", True):
        return None
    scope = set(ev["actors"]) | {ev["where"]} | {r[0] for r in ev["requires"]} | {op.get("id") for op in ev["effects"]}
    applied, _ = world.apply(outcome.get("effects", []), origin, scope)
    return world.record(outcome.get("summary") or ev["summary"], ev["where"], applied, origin, ev["weight"],
                        ev.get("public", True), day=ev["day"])
