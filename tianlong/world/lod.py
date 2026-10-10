"""
[INPUT]: 依赖 world/world 的 World 门面（graph / clock / canon / done / taint / apply / record）
[OUTPUT]: 对外提供 tiers()、lod1_scope()、absorb()、due_canon()、dirt()、broken()、settle()
[POS]: world 层的叙事 LOD 调度器——只做确定性判定（谁在哪一层、何时刷新、是否被污染），
       把需要 LLM 的工作以"任务"形式交给 engine，并把 LLM 的结构化结果经 effects 策略过滤后落账
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
    """LOD1 战报落账：变更只经 lod1 策略执行，被拒的指令静默丢弃；战报本身成为真相并开始传播。"""
    events = []
    for r in reports:
        applied, _ = world.apply(r.get("effects", []), "lod1", scope)
        where = r.get("where") if r.get("where") in scope else None
        if where:
            events.append(world.record(f"{r.get('event', '')}：{r.get('result', '')}", where, applied, "lod1"))
    return events


# ============================================================
#  LOD2：原著平行轨道 + 因果涟漪(dirty flag)
#  结算节拍随距离变粗：LOD0 即时、LOD1 按日、LOD2 按月
# ============================================================
def _unmet(world, ev: dict) -> list[tuple]:
    return [(nid, key, want) for nid, key, want in ev["requires"] if world.graph.get(nid, key) != want]


def broken(world, ev: dict) -> bool:
    """原著前提是否已被破坏（区别于仅被污染）：决定史官失联时的兜底——前提破则不发生。"""
    return bool(_unmet(world, ev))


def dirt(world, ev: dict, tier: int) -> list[str]:
    g = world.graph
    reasons = [f"{nid}的{key}应为{want}，实为{g.get(nid, key)}" for nid, key, want in _unmet(world, ev)]
    reasons += [f"{a}曾受玩家影响" for a in ev["actors"] if a in world.taint]
    if tier == 0:
        reasons.append("玩家亲临现场")
    return reasons


def due_canon(world, days: int, months: int) -> list[tuple[dict, list[str]]]:
    t = tiers(world)
    due = []
    for ev in world.canon:
        if ev["id"] in world.done or ev["day"] > world.clock.day:
            continue
        tier = t.get(ev["where"], 2)
        if months or tier == 0 or (days and tier == 1):
            due.append((ev, dirt(world, ev, tier)))
    return due


def settle(world, ev: dict, outcome: dict, origin: str) -> dict | None:
    """结算一桩原著事件。outcome: {happens, summary, effects}；干净事件直接传入 ev 本身。"""
    world.done.append(ev["id"])
    if not outcome.get("happens", True):
        return None
    scope = set(ev["actors"]) | {ev["where"]}
    applied, _ = world.apply(outcome.get("effects", []), origin, scope)
    return world.record(outcome.get("summary") or ev["summary"], ev["where"], applied, origin, ev["weight"])
