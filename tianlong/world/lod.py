"""
[INPUT]: 依赖 world/graph 的 holds（前提核对口径）、world/situation 的 near / around / entangled / FOLLOW / CUSTODY（近旁、身边、纠缠与拘押）、
         world/effects 的 apply / describe / resolve / _note（场外后果的试演与落账、只记成立之事时的代笔、名字归一、原著挪人的连带）、
         world/adjudicate 的 names（实体名表）、world/lexicon 的 unbacked（场外说法对账）、world/perspective 的 knows（谁叫得出主角名号），
         World 门面（graph / clock / canon / done / taint / turn / player / here / apply / record）
[OUTPUT]: 对外提供 entangled()、tiers()、claimed()、held()、lod1_scope()、absorb()、split_due()、onstage()、upcoming()、ahead()、verdict()、dirt()、broken()、settle()、NEAR、HORIZON、LATE
[POS]: world 层的叙事 LOD 调度器——只做确定性判定（谁在哪一层、谁归谁调遣、何事到期、是否被污染），
       把需要 LLM 的工作以"任务"形式交给 engine：远方到期原著场外结算，主角眼前(onstage)到期的原著一回合一桩交导演作主干；
       场外剧情的后果经 effects 落账为真相，并盖原著排定之日的日戳（此地亲见者盖今日）。
       一人一主(v5)：同一个人此刻只归一处调遣——主角身边与近旁之人归导演，HORIZON 日内有原著的人归原著，与主角有过交集的近处之人等着主角的故事，
       剩下的自由之人才交场外推演；尚有原著之约的人，场外推演挪不动、杀不得(原著自会把人送到事发之地，中途被挪走，回来便是瞬移)。
       主角眼前(v5)：事发在此地或近旁(喊一声就到的同一处所)，或原著当其时(迟不过 LATE 日)要把主角身边的人带往别处——都交导演演出，
       在主角这一片上演的原著，上了台的相关者进眼前的名册(片区里也算在跟前；主角已先走一步离开事发之地则不算)，原著挪人之后谁来谁走写成连带交编剧；「分身不得」读眼前(around)而非同处一片；同行者与未了之事所系之人不在此列，主角把人带在身边，原著便不来要人；史官改写时看得见相关者此后的原著(ahead)。
       账本只记已成立之事：场外的说法在后果全数成立、且逐句对得上账(lexicon.unbacked)时才照录，有不成立的或对不上账的只记成立的要事，一事无成则不入账；
       原著先把人摆回事发之地、再送去终点，而那人已在终点(导演先一步演了这一走)：中间那一步被拦下无关紧要(_arrived)，不因此把原著的说法换成清单；
       场外的结算是一个事务：原著与史官的后果先在副本上试演，筋骨(去留、生死伤病、易手、擒放随行)有一条落不了，整桩不半截照演——原著视同前提已破，史官的改写不入账；
       原著的隐含前提——死者不再登场、正与主角同在一处(含近旁)的人分身不得、主角手中之物不会凭空飞走、救人之事须那人仍受制；
       情境前提(~关系/!关系)与属性前提同一口径(graph.holds)；与主角故事纠缠之人(同行者、未了之事所系者)的场外原著前提已破即作罢、不唤史官——他们的行止只听导演与此地剧情
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy

from . import adjudicate, effects, lexicon, perspective, situation
from .effects import describe
from .graph import holds

NEAR = 1      # 一日路程之内皆为近处：0 日路相连的山门、洞府同属一簇，不以跳数计
HORIZON = 7   # 原著认领：七日之内有戏的人，场外的行止只听原著
LATE = 1      # 原著要从主角身边带人走，至多迟这么多日：再旧的事不回头拽人


# ============================================================
#  分层：LOD0 = 主角所在及其近旁(喊一声就到)；LOD1 = 一日可达的近处；LOD2 = 远端大世界
#  按道路距离，不按跳数——半数道路是 0 日路；近旁是导演的地界：那里上演的原著交导演，那里的人场外动不得
# ============================================================
def tiers(world) -> dict[str, int]:
    dist, close = world.graph.distances(world.here), situation.near(world)
    return {loc: 0 if loc in close else 1 if dist.get(loc, NEAR + 1) <= NEAR else 2
            for loc in world.graph.where(type="location")}


# ============================================================
#  一人一主：谁此刻归谁调遣
# ============================================================
def _cast(ev: dict) -> set[str]:
    return set(ev["actors"]) | {op.get("id") for op in ev["effects"] if isinstance(op.get("id"), str)}


def claimed(world, within: int = HORIZON) -> set[str]:
    """原著认领之人：within 日之内有未结原著的相关者——他们的场外行止只听原著。"""
    today, done = world.clock.day, set(world.done)
    return {a for ev in world.canon if ev["id"] not in done and ev["day"] <= today + within for a in _cast(ev)}


def _tracked(world) -> set[str]:
    """尚有未结原著的人(不论远近)：场外推演挪不动他们的去向、要不了他们的命。"""
    done = set(world.done)
    return {a for ev in world.canon if ev["id"] not in done for a in _cast(ev)}


def held(world) -> set[str]:
    """主角的故事认领之人：身边与近旁之人、纠缠者，以及一日路程之内与主角有过交集的人(恩怨账上记过事、或叫得出主角名号)——
    他们等着主角的故事，场外推演不得把人带走、伤了、杀了。"""
    g, dist = world.graph, world.graph.distances(world.here)
    met = {p for p in g.where(type="person") if dist.get(g.get(p, "location"), NEAR + 1) <= NEAR
           and ((g.get(p, "bond") or {}).get("log") or perspective.knows(world, p, "player"))}
    return situation.around(world) | situation.entangled(world) | met


def lod1_scope(world) -> tuple[list[str], set[str]]:
    """LOD1 推演：近处(一日之内、近旁以外)的自由之人——未被原著认领、不在主角的故事里、活着、在江湖中、未隐匿。
    返回 (推演人物：自由之人里怀有图谋者, 推演范围：近处地点 + 全部自由之人)；推演只碰得到范围之内。"""
    ring = {loc for loc, t in tiers(world).items() if t == 1}
    g, busy = world.graph, claimed(world) | held(world)
    free = {p for p in g.where(type="person") if g.get(p, "location") in ring and p not in busy
            and g.get(p, "status") != "dead" and not g.get(p, "hidden") and not g.get(p, "dormant")}
    return sorted(p for p in free if g.get(p, "agenda")), ring | free


MATERIAL = {"status", "location", "holder", "faction", "title"}  # 江湖传得开的变化：生死、去留、易手、改换门庭
BONES = MATERIAL | {"hp", "skills"}                             # 一桩事的筋骨：落不了一条，就不是原来那件事


def _material(op) -> bool:
    return op.get("op") in ("link", "unlink") or op.get("key") in MATERIAL


def _bone(op) -> bool:
    if not isinstance(op, dict):
        return False
    if op.get("op") in ("link", "unlink"):
        return op.get("rel") == situation.FOLLOW or op.get("rel") in situation.CUSTODY
    return op.get("key") in BONES


def _stuck(world, ops, origin: str, scope: set) -> list[tuple[dict, str]]:
    """在副本上试演一批场外后果，返回落不了的筋骨。副本只复制效果会写到的几样(图、主角黑板、本回合的瞬时账)，
    账本与认知原样共用——场外来源的指令从不写它们。"""
    trial = copy.copy(world)
    trial.graph, trial.player, trial.turn = copy.deepcopy(world.graph), copy.deepcopy(world.player), copy.deepcopy(world.turn)
    batch = copy.deepcopy(ops if isinstance(ops, list) else [])
    _, rejected = effects.apply(trial, batch, origin, scope)
    return [(op, why) for op, why in rejected if _bone(op) and not _arrived(trial, batch, op)]


# ============================================================
#  场外的说法：与账对得上才照录
# ============================================================
def _unbacked(world, text: str, applied: list) -> list[str]:
    g = world.graph
    sets = lambda key, value: {op["id"] for op in applied if op.get("op") == "set" and op.get("key") == key and op.get("value") == value}
    facts = {"moved": {op["id"]: op["value"] for op in applied if op.get("op") == "set" and op.get("key") == "location"},
             "dead": sets("status", "dead"),
             "hurt": sets("status", "wounded") | {op["id"] for op in applied if (op.get("op") == "add" and op.get("key") == "hp"
                                                                               and isinstance(op.get("value"), (int, float)) and op["value"] < 0)
                                                    or (op.get("op") == "push" and op.get("key") == "conditions")},
             "custody": {x for op in applied if op.get("op") in ("link", "unlink") and op.get("rel") in situation.CUSTODY
                         for x in (op["src"], op["dst"])},
             "items": {op["id"] for op in applied if op.get("key") in ("holder", "location") and g.kind(op.get("id")) == "item"},
             "player": (world.player["name"], "主角")}
    return lexicon.unbacked(text, *adjudicate.names(world), facts)


def _told(world, claim: str, applied: list, rejected: list, bare: bool = True, verify: bool = False) -> str | None:
    """场外之事入账的一句话：后果全数成立、且说法逐句对得上账(verify)才照录；有不成立的、或说法对不上账，只记成立的要事
    （说法里多半正写着那不成立之事）；一事无成则不入账。bare 为真时，本无后果的叙事(原著里的一番谈话)照录；
    场外推演只动了心思而无要事，不成江湖事。"""
    facts = "；".join(describe(op) for op in applied if _material(op)).replace("主角", world.player["name"])
    if not bare and not facts:
        return None
    if rejected or (verify and _unbacked(world, claim, applied)):
        return facts or None
    return claim


def _foreign(world, op, scope: set, tracked: set) -> str | None:
    """一人一主：场外推演只碰得到推演范围之内的自由之人；尚有原著之约的人，去向与生死归原著。"""
    if not isinstance(op, dict):
        return None  # 形状交 effects 驳回
    g = world.graph
    who = [effects.resolve(world, op.get(k)) for k in ("id", "src", "dst")]
    if op.get("key") == "holder":
        who.append(effects.resolve(world, op.get("value")))
    for p in who:
        if isinstance(p, str) and g.kind(p) == "person" and p not in scope:
            return f"{p}的行止另有所主（原著或主角的故事），场外推演动不了"
    pid = who[0]
    if pid in tracked and op.get("op") == "set" and \
            (op.get("key") == "location" or (op.get("key") == "status" and op.get("value") == "dead")):
        return f"{pid}尚有原著之约，去向与生死归原著"
    return None


def absorb(world, reports: list[dict], scope: set[str]) -> list[dict]:
    """LOD1 战报落账：只收推演范围之内的事；碰到范围之外的人、挪动或杀死尚有原著之约的人，那一条不成立；
    后果经 effects 校验执行，说法与账对得上才照录，对不上只记成立的要事，没有要事不成江湖事。"""
    events, tracked = [], _tracked(world)
    for r in reports:
        where = r.get("where")
        if not isinstance(where, str) or where not in scope:
            continue
        ops = r.get("effects") if isinstance(r.get("effects"), list) else []
        blocked = [(op, why) for op in ops if (why := _foreign(world, op, scope, tracked))]
        applied, rejected = world.apply([op for op in ops if all(op is not b for b, _ in blocked)], "lod1", scope)
        summary = _told(world, f"{r.get('event', '')}：{r.get('result', '')}", applied, rejected + blocked, bare=False, verify=True)
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
    """按 order 遍历到期原著：场外的归入待结算 (事件, 层级)；遇到第一桩发生在主角眼前的(onstage)即停下，把它交出作本回合主干。"""
    t, offstage = tiers(world), []
    for ev in _pending(world):
        if onstage(world, ev):
            return offstage, ev
        offstage.append((ev, t.get(ev["where"], 2)))
    return offstage, None


def ahead(world, ev: dict, limit: int = 3) -> list[dict]:
    """这桩原著的相关者此后还有哪几桩原著(按 order)：交史官——改写这一桩时，别把后面几桩的前提一并改断。"""
    done, cast = set(world.done), set(ev["actors"])
    return [e for e in world.canon if e["order"] > ev["order"] and e["id"] not in done and set(e["actors"]) & cast][:limit]


def upcoming(world, skip: set[str] = frozenset(), within: int = 7, limit: int = 3) -> list[tuple[dict, int]]:
    """近处(LOD0/1)数日内将上演、尚未结算的原著，连同距今日数；相关者正在主角身边的，事发之地再远也列——交导演伏笔，不可提前上演。"""
    t, today, done, close = tiers(world), world.clock.day, set(world.done) | set(skip), situation.around(world)
    out = [(ev, ev["day"] - today) for ev in world.canon
           if ev["id"] not in done and ev["day"] <= today + within and (t.get(ev["where"], 2) <= 1 or set(ev["actors"]) & close)]
    return out[:limit]


entangled = situation.entangled  # 与主角故事纠缠之人：定义归情境层，effects 也据此拦场外调遣


def _premises(world, ev: dict) -> list[tuple]:
    """原著的前提(不论在不在主角眼前)：明写的前提、情境前提、死者不再登场、主角手中之物不会飞走。"""
    g = world.graph
    touched = sorted(set(ev["actors"]) | {op.get("id") for op in ev["effects"] if isinstance(op.get("id"), str)})
    unmet = [(nid, key, want) for nid, key, want in ev["requires"] if not holds(g, nid, key, want)]
    unmet += [(op["src"], "~" + op["rel"], op["dst"]) for op in ev["effects"]  # 救人的原著，须那人仍受制：已被主角救走便不必再救
              if op.get("op") == "unlink" and op.get("rel") in situation.CUSTODY and not holds(g, op["src"], "~" + op["rel"], op["dst"])]
    unmet += [(a, "status", "alive") for a in ev["actors"] if g.get(a, "status") == "dead"]       # 死者不再登场
    unmet += [(i, "holder", "非主角") for i in touched if g.kind(i) == "item" and g.get(i, "holder") == "player"]  # 主角手中之物
    return unmet


def onstage(world, ev: dict) -> bool:
    """这桩原著是否发生在主角眼前：事发之地是此地或近旁；或相关者正在主角身边、前提都在、正当其时(迟不过 LATE 日)——
    原著要把人从主角身边带走(段誉该去后山了)，不在场外悄悄把他传送走、也不就此作罢，交导演演出这一别：主角可以拦、可以同去、可以目送。
    同行者与未了之事所系之人不在此列：主角把人带在身边，他的原著便不再来要人(场外作罢，见 verdict)；过了时候的旧事也不回头拽人。"""
    if ev["where"] in situation.near(world):
        return True
    with_me = set(ev["actors"]) & situation.around(world)
    if not with_me or with_me & entangled(world):
        return False
    return world.clock.day - ev["day"] <= LATE and not _premises(world, ev)


def _unmet(world, ev: dict) -> list[tuple]:
    g, unmet = world.graph, _premises(world, ev)
    if not onstage(world, ev):  # 场外之事：正在主角眼前(此地、近旁、片区里被带到跟前)的人分身不得——非相关者被原著顺带写到，也一样
        close = situation.around(world)
        touched = sorted(set(ev["actors"]) | {op.get("id") for op in ev["effects"] if isinstance(op.get("id"), str)})
        unmet += [(n, "location", ev["where"]) for n in touched if g.kind(n) == "person" and n in close]
        unmet += [(n, "纠缠", ev["where"]) for n in touched if n in entangled(world) and n not in close]
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
    if key == "location" and cur in situation.near(world):
        return f"{nid}正在主角近旁的{cur}，无法在{want}现身"
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


def _arrived(world, ops: list, op) -> bool:
    """落不了的那一步是不是无关紧要：原著先把人摆回事发之地、再送他去终点，导演已先一步把他送到了终点——
    中间那一步被拦下，原著要的结局照样成立，不该因此把原著的说法换成一串清单。"""
    if not isinstance(op, dict) or op.get("op") != "set" or op.get("key") != "location":
        return False
    pid = op.get("id")
    last = [o.get("value") for o in ops if isinstance(o, dict) and o.get("op") == "set" and o.get("key") == "location" and o.get("id") == pid]
    return bool(last) and world.graph.get(pid, "location") == last[-1]


def _comings(world, before: set[str]) -> list[str]:
    """主角眼前的原著落账之后，谁因此来到或离开主角身边：交编剧写进正文——原著挪人，主角看得见。"""
    g, after = world.graph, situation.around(world)
    gone = [f"{p}离开了你身边，往{g.get(p, 'location')}去了" for p in sorted(before - after) if g.get(p, "status") != "dead"]
    came = [f"{p}来到了" + ("此地" if g.get(p, "location") == world.here else f"近旁的{g.get(p, 'location')}")
            for p in sorted(after - before)]
    return gone + came


def _scope(ev: dict) -> set:
    return set(ev["actors"]) | {ev["where"]} | {r[0] for r in ev["requires"]} | {op.get("id") for op in ev["effects"]}


def verdict(world, ev: dict, tier: int) -> tuple[str, list[str]]:
    """裁定一桩到期的场外原著：canon 照原著 / chronicle 唤醒史官 / skip 悄然不发生。
    未被扰动的原著照常上演；史官只为"附近的破局"与"被扰动的大事"醒来，远方小事破局则作罢。
    前提都在、后果却落不了地(此日已被别处调遣、物已不存)，等同前提已破：原著是一个事务，不半截照演。"""
    reasons, torn = dirt(world, ev), broken(world, ev)
    if not torn:
        stuck = [f"{describe(op)}落不了：{why}" for op, why in _stuck(world, ev["effects"], "canon", _scope(ev))]
        reasons, torn = reasons + stuck, bool(stuck)
    if not reasons:
        return "canon", []
    if torn:
        if set(ev["actors"]) & entangled(world):  # 纠缠者的行止只听导演与此地剧情：前提已破，连史官也不唤，作罢
            return "skip", reasons
        return ("chronicle" if ev["weight"] >= 2 or tier <= 1 else "skip"), reasons
    return ("chronicle" if ev["weight"] >= 2 else "canon"), reasons


def settle(world, ev: dict, outcome: dict, origin: str, day: int | None = None, witnessed: bool | None = None,
           partial: bool = False) -> dict | None:
    """结算一桩原著事件。outcome: {happens, summary, effects}；干净事件直接传入 ev 本身。
    场外结算是一个事务：后果先在副本上试演，筋骨落不了即整桩不入账(verdict 已据此把原著改道，这里是最后一道闸)；
    此地上演的原著(partial)在导演诸拍之后落账，导演挪动过的人原著挪不动——成立的部分照落，账上只记成立之事。
    真相盖原著排定之日的日戳——主角亲眼所见的那一桩则盖今日(day)：迟到才演的戏，传闻不该已在路上走了十天。"""
    world.done.append(ev["id"])
    if not outcome.get("happens", True):
        return None
    scope, ops = _scope(ev), outcome.get("effects", [])
    if not partial and _stuck(world, ops, origin, scope):
        return None
    before = situation.around(world)
    applied, rejected = world.apply(ops, origin, scope)
    rejected = [(op, why) for op, why in rejected if not _arrived(world, ops, op)]
    if partial:  # 主角眼前的原著：在主角这一片上演的，上了台的相关者就在跟前(片区里也一样)；谁因此来去写成连带
        close = situation.near(world)
        if ev["where"] in close:  # 主角已先走一步离开了事发之地：那里的人不跟着上他的名册
            situation.enlist(world, [a for a in ev["actors"] if world.graph.get(a, "location") in close])
        effects._note(world, _comings(world, before))
    summary = _told(world, outcome.get("summary") or ev["summary"], applied, rejected, verify=origin != "canon")
    if summary is None:
        return None
    return world.record(summary, ev["where"], applied, origin, ev["weight"], ev.get("public", True),
                        day=ev["day"] if day is None else day, witnessed=witnessed)
