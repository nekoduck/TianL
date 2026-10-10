"""
[INPUT]: 依赖 world/world 的 World 门面（graph / clock / canon / done / taint / apply / record）
[OUTPUT]: 对外提供 tiers()、lod1_scope()、absorb()、due_canon()、verdict()、dirt()、broken()、settle()
[POS]: world 层的叙事 LOD 调度器——只做确定性判定（谁在哪一层、何时刷新、是否被污染），
       把需要 LLM 的工作以"任务"形式交给 engine，并把场外剧情的后果经 effects 落账为真相
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

# ============================================================
#  分层：LOD0 = 玩家所在地；LOD1 = 一程可达的相邻地；LOD2 = 远端大世界
# ============================================================
def tiers(world) -> dict[str, int]:
    hops = world.graph.hops(world.here)
    return {loc: min(hops.get(loc, 2), 2) for loc in world.graph.where(type="location")}


def lod1_scope(world) -> tuple[list[str], set[str]]:
    """LOD1 推演对象：相邻地点上怀有图谋(agenda)、未隐匿的活人。"""
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
#  结算节拍随距离变粗：LOD0 即时、LOD1 按日、LOD2 按月；但永远按 order 依次结算，远事不会被近事插队
# ============================================================
def _holds(world, nid: str, key: str, want) -> bool:
    cur = world.graph.get(nid, key)
    return want in cur if isinstance(cur, list) and not isinstance(want, list) else cur == want


def _unmet(world, ev: dict) -> list[tuple]:
    return [(nid, key, want) for nid, key, want in ev["requires"] if not _holds(world, nid, key, want)]


def broken(world, ev: dict) -> bool:
    """原著前提是否已被破坏（区别于仅被污染）：决定史官失联时的兜底——前提破则不发生。"""
    return bool(_unmet(world, ev))


def dirt(world, ev: dict) -> list[str]:
    g = world.graph
    reasons = [f"{nid}的{key}应为{want}，实为{g.get(nid, key)}" for nid, key, want in _unmet(world, ev)]
    touched = set(ev["actors"]) | {r[0] for r in ev["requires"]} | {op.get("id") for op in ev["effects"]}
    reasons += [f"{n}曾受主角影响" for n in sorted(touched & world.taint)]
    return reasons


def verdict(world, ev: dict, tier: int) -> tuple[str, list[str]]:
    """裁定一桩到期原著事件的走向：canon 照原著 / chronicle 唤醒史官 / skip 悄然不发生。
    主角亲历而未被扰动的原著照常上演（主角是见证者）；史官只为"附近的破局"与"被扰动的大事"醒来，远方小事破局则作罢。"""
    reasons = dirt(world, ev)
    if not reasons:
        return "canon", []
    if broken(world, ev):
        return ("chronicle" if ev["weight"] >= 2 or tier <= 1 else "skip"), reasons
    return ("chronicle" if ev["weight"] >= 2 else "canon"), reasons


def due_canon(world, days: int, months: int) -> list[tuple[dict, int]]:
    """到期且到了刷新节拍的事件，连同排在它之前的全部到期事件，按 order 返回 (事件, 层级)。"""
    t = tiers(world)
    done = set(world.done)
    pending = [ev for ev in world.canon if ev["id"] not in done and ev["day"] <= world.clock.day]
    ripe = [i for i, ev in enumerate(pending)
            if months or t.get(ev["where"], 2) == 0 or (days and t.get(ev["where"], 2) == 1)]
    return [(ev, t.get(ev["where"], 2)) for ev in pending[:ripe[-1] + 1]] if ripe else []


def settle(world, ev: dict, outcome: dict, origin: str) -> dict | None:
    """结算一桩原著事件。outcome: {happens, summary, effects}；干净事件直接传入 ev 本身。"""
    world.done.append(ev["id"])
    if not outcome.get("happens", True):
        return None
    scope = set(ev["actors"]) | {ev["where"]} | {r[0] for r in ev["requires"]} | {op.get("id") for op in ev["effects"]}
    applied, _ = world.apply(outcome.get("effects", []), origin, scope)
    return world.record(outcome.get("summary") or ev["summary"], ev["where"], applied, origin, ev["weight"],
                        ev.get("public", True))
