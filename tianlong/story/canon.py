"""
[INPUT]: 依赖 world/lod 的 broken（前提核对）、world/situation 的 near / around / party / CUSTODY（此地与近旁同属 LOD0），World 门面的 canon / done / clock / here / graph / player
[OUTPUT]: 对外提供 pull()（主角在场、相关者到位的原著提前上演：窗口的「拉」）、consume()（导演演掉的原著按后果签名记作兑现）、signature()、
          ready()（此刻拉得起来的原著 id，后台近事据此改写措辞）、PULL、WITHIN
[POS]: story 层的原著窗口——「原著是有窗口的因果轨道」(宪法第 6 条 v4)：原著排定之日不再是一个冻住的日子，而是窗口的锚：
       拉——主角就在事发之地或其近旁、相关者都在身边、前提未破、按 order 之前没有牵涉同一批人的原著悬着，PULL 日之内将至的那一桩今天就可以上演；
       推——过了排定之日仍未上演，照旧由 lod.split_due 交场外结算(v11：前提未变照原著演，破了延后、作罢或交场外编剧改写)；
       消费——导演已成立的后果与某桩未演原著的「后果签名」(擒放、生死、易手、人物去向)过半重合，那桩原著记作已兑现(变体)，不再到期、不交场外编剧。
       消费只记账、不改物理状态；签名先比筋骨(擒放、生死、易手)，没有筋骨的原著才比人物去向，过半且至少一条重合
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from ..world import lod, situation

PULL = 3      # 几日之内将至的原著，相关者到位即可提前上演
WITHIN = 10   # 消费只看几日之内的未演原著：太远的，剧情碰巧相似也不算演掉了它


def _pending(world) -> list[dict]:
    done = set(world.done)
    return [ev for ev in world.canon if ev["id"] not in done]


def _gathered(world, ev: dict) -> bool:
    g, close = world.graph, situation.around(world) | set(situation.party(world))
    return all(a in close and g.get(a, "status") != "dead" for a in ev["actors"])


def ready(world, skip=frozenset()) -> list[dict]:
    """此刻拉得起来的原著：事发之地就是此地或其近旁(与 lod 的 LOD0 同一口径)、PULL 日内将至、相关者都在身边、前提未破、之前没有牵涉同一批人的原著悬着。"""
    today, out, waiting, close = world.clock.day, [], set(), situation.near(world)
    for ev in _pending(world):  # canon 按 order 排好：先到的先占住它的相关者
        if ev["id"] in skip:
            continue
        early = ev["day"] - today
        if 0 < early <= PULL and ev["where"] in close and not (set(ev["actors"]) & waiting) \
                and _gathered(world, ev) and not lod.broken(world, ev):
            out.append(ev)
        if ev["day"] <= today + PULL and not lod.broken(world, ev):  # 前提已破的旧事占不住人：段誉已在谷底，后山那桩便不再挡路
            waiting |= set(ev["actors"])
    return out


def pull(world, skip=frozenset()) -> dict | None:
    """本回合可提前上演的那一桩(至多一桩，与到期的此地原著同一口径交导演作主干)。"""
    found = ready(world, skip)
    return found[0] if found else None


def signature(ev: dict) -> list[tuple]:
    """原著的后果签名：只取主要后果——擒放、生死、易手、人物去向。"""
    out = []
    for op in ev["effects"]:
        kind, key = op.get("op"), op.get("key")
        if kind in ("link", "unlink") and op.get("rel") in situation.CUSTODY:
            out.append((kind, "custody", op.get("dst")))
        elif kind == "set" and key == "status" and op.get("value") == "dead":
            out.append(("dead", op.get("id")))
        elif kind == "set" and key == "holder":
            out.append(("holder", op.get("id"), op.get("value")))
        elif kind == "set" and key == "location" and op.get("id") in ev["actors"]:
            out.append(("location", op.get("id"), op.get("value")))
    return out


def _marks(world, applied: list) -> set[tuple]:
    out = set()
    for op in applied:
        kind, key = op.get("op"), op.get("key")
        if kind in ("link", "unlink") and op.get("rel") in situation.CUSTODY:
            out.add((kind, "custody", op.get("dst")))
        elif kind == "set" and key == "status" and op.get("value") == "dead":
            out.add(("dead", op.get("id")))
        elif kind == "set" and key == "holder":
            out.add(("holder", op.get("id"), op.get("value")))
        elif kind == "set" and key == "location":
            out.add(("location", op.get("id"), op.get("value")))
        elif kind == "arrive":
            out.add(("location", op.get("id"), world.here))
    return out


def consume(world, applied: list) -> list[dict]:
    """导演演掉的原著记作兑现：WITHIN 日内未演的原著，签名过半重合(至少一条)即入 done，返回被兑现的那几桩。"""
    marks, today, out = _marks(world, applied), world.clock.day, []
    if not marks:
        return out
    for ev in _pending(world):
        if ev["day"] > today + WITHIN:
            break
        sig = signature(ev)
        major = [x for x in sig if x[0] != "location"] or sig  # 擒放、生死、易手是筋骨；只有去向的原著才看去向
        hit = [x for x in major if x in marks or (x[0] == "holder" and ("holder", x[1], "player") in marks)]
        if hit and len(hit) * 2 >= len(major):
            world.done.append(ev["id"])
            out.append(ev)
    return out
