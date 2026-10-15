"""
[INPUT]: 依赖 world/graph 的 holds（前提核对口径）、world/situation 的 near / around / entangled / FOLLOW / CUSTODY（近旁、身边、纠缠与拘押）、
         world/effects 的 apply / describe / resolve / _note（场外后果的试演与落账、只记成立之事时的代笔、名字归一、原著挪人的连带）、
         world/access 的 reach（场外人物可走的里程：衍生事件的人赶不赶得到）、
         world/adjudicate 的 names / spoilers（实体名表、剧透）、world/lexicon 的 unbacked（场外说法对账）、world/perspective 的 knows（谁叫得出主角名号），
         world/crowd 的 GROUP / is_squad / present（v12 原著近事要用的人马），World 门面（graph / clock / canon / done / taint / turn / player / here / apply / record）
[OUTPUT]: 对外提供 reserved()（v12 原著近事要用的人马：带队之人是近事相关者的人群 → 事件）、entangled()、tiers()、claimed()、held()、split_due()、coming()、onstage()、upcoming()、verdict()、dirt()、broken()、intact()、settle()、unbacked()、stray()、NEAR、HORIZON、LATE
[POS]: world 层的叙事 LOD 调度器——只做确定性判定（谁在哪一层、谁归谁调遣、何事到期、前提破没破），
       把需要 LLM 的工作以"任务"形式交给 engine：远方到期之事场外结算，主角眼前(onstage)到期的一桩一回合交导演作主干；
       日程里有原著，也有场外编剧写的衍生事件(v11，与原著同一格式、带 derived)，到期一样按 order 结算、一样过前提——另有一条隐含前提：人赶得到(「赶不到」：
       衍生事件排定之后人被别处挪走了；原著要用的人被场外剧情带去了远处(strayed)，赶不回来)。
       场外剧情的后果经 effects 落账为真相，并盖排定之日的日戳（此地亲见者盖今日）。
       一人一主(v5)：同一个人此刻只归一处调遣——主角身边与近旁之人归导演，HORIZON 日内有原著的人归原著，与主角有过交集的近处之人等着主角的故事，
       剩下的人的下一步交场外编剧(world/plot)；尚有原著之约的人，场外挪不动(原著自会把人送到事发之地，中途被挪走，回来便是瞬移)。
       主角眼前(v5)：事发在此地或近旁(喊一声就到的同一处所)，或原著当其时(迟不过 LATE 日)要把主角身边的人带往别处——都交导演演出，
       在主角这一片上演的原著，上了台的相关者进眼前的名册(片区里也算在跟前；主角已先走一步离开事发之地则不算)，原著挪人之后谁来谁走写成连带交编剧；「分身不得」读眼前(around)而非同处一片；同行者与未了之事所系之人不在此列，主角把人带在身边，原著便不来要人。
       一地一主(v11)：原著或衍生事件要把人送到主角这里(事发在远处、后果却是来人，coming)，同样交导演演出来人，远处的结算不把人悄悄塞到主角跟前。
       账本只记已成立之事：LLM 写的说法(衍生事件)在后果全数成立、逐句对得上账(lexicon.unbacked)、且不剧透(adjudicate.spoilers)时才照录，否则只记成立的要事，一事无成则不入账；
       原著先把人摆回事发之地、再送去终点，而那人已在终点(导演先一步演了这一走)：中间那一步被拦下无关紧要(_arrived)，不因此把原著的说法换成清单；
       场外的结算是一个事务：后果先在副本上试演，筋骨(去留、生死伤病、易手、擒放随行)有一条落不了，整桩不半截照演——视同前提已破；
       原著的隐含前提——死者不再登场、正与主角同在一处(含近旁)的人分身不得、主角手中之物不会凭空飞走、救人之事须那人仍受制；
       情境前提(~关系/!关系)与属性前提同一口径(graph.holds)；与主角故事纠缠之人(同行者、未了之事所系者)的场外之事前提已破即作罢——他们的行止只听导演与此地剧情。
       演绎与创作(v11 verdict)：原著前置未变就照原著演(被主角扰动过也照演，不调模型)；前提破了——附近的、或分量重的交场外编剧改写(rewrite：按原著的逻辑写新的剧情线)，
       远方小事作罢；衍生事件前提破了即作罢。作罢的那一桩，相关的活人记作原著线已变(adrift)，往后的路交场外编剧续写——原著线可以断，断了不必接回
       v13 一人一主不冻结(P1-3)：held 只拦主角身边的、纠缠者(同行者、未了之事所系者)与扣着他们的人、被他们扣着的人，不再算上「一日路程之内、叫得出主角名号」的人——
       认得主角不等于等着主角(司空玄 held 了 60 回、推力 4，从未进过 plot.idle)；承诺另有时限带后果(story/stakes)，由规则兑现
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy

from . import access, adjudicate, crowd, effects, lexicon, perspective, situation
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


def held(world) -> set[str]:
    """主角的故事认领之人：身边与近旁之人、纠缠者（同行者、未了之事所系者），与扣着他们的人、被他们扣着的人——
    他们的去留生死牵着主角的故事：场外编剧只可写他们来到主角跟前(交导演当面演出)，不得把人带走、伤了、杀了。
    v13 不再算上「一日路程之内与主角有过交集的人」（恩怨账上记过事、叫得出主角名号）：认得主角不等于等着主角——那条口径把方圆一日内认得主角的人冻了 60 回
    （司空玄 held、推力 4、从未进过 plot.idle）；他们的承诺另有时限带后果（story/stakes），由规则兑现。"""
    tied = situation.around(world) | situation.entangled(world)
    cast = set(tied)
    for p in tied:
        cast |= set(situation.captors(world, p)) | set(situation.hostages(world, p))
    return cast - {"player"}


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
def unbacked(world, text: str, applied: list) -> list[str]:
    """一句场外的说法里，账上没有的变化(去留、生死、伤病、擒放、得失)：场外编剧的规则审与到期结算共用。"""
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
    （说法里多半正写着那不成立之事）；一事无成则不入账。bare 为真时，本无后果的叙事(原著里的一番谈话)照录。
    LLM 写的说法(verify：衍生事件)另过剧透的筛子(v11)：它会变成传闻、传到编剧与玩家眼前。"""
    facts = "；".join(describe(op) for op in applied if _material(op)).replace("主角", world.player["name"])
    if not bare and not facts:
        return None
    revealed = {(op["src"], op["rel"], op["dst"]) for op in applied if op.get("op") == "reveal" and "src" in op}
    if rejected or (verify and (unbacked(world, claim, applied) or adjudicate.spoilers(world, claim, revealed))):
        return facts or None  # 说破未揭的隐情、把尚未发生的原著说成已成之事(v11)：这话要随传闻传到主角耳边，只记核实过的后果
    return claim


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


def upcoming(world, skip: set[str] = frozenset(), within: int = 7, limit: int = 3) -> list[tuple[dict, int]]:
    """近处(LOD0/1)数日内将上演、尚未结算的原著，连同距今日数；相关者正在主角身边的，事发之地再远也列——交导演伏笔，不可提前上演。"""
    t, today, done, close = tiers(world), world.clock.day, set(world.done) | set(skip), situation.around(world)
    out = [(ev, ev["day"] - today) for ev in world.canon
           if ev["id"] not in done and ev["day"] <= today + within and (t.get(ev["where"], 2) <= 1 or set(ev["actors"]) & close)]
    return out[:limit]


entangled = situation.entangled  # 与主角故事纠缠之人：定义归情境层，effects 也据此拦场外调遣


def reserved(world, upcoming) -> dict[str, str]:
    """原著近事要用的人马(v12)：带队之人(leader)是某桩近事的相关者(在 upcoming 里、尚未结算、前提未破)，且这一群此刻不在主角跟前——
    事前叫不来、分不出人(effects 拦赶来、crowd 拦分人，都只读 world.turn["reserved"])，远远望见可以。返回 {人群 id: 事件 id}。
    同一群对上几桩：记事发之地就是这一群所在(或同属一处)的那一桩，否则记最早的一桩。门派级的禁令另管「补一队」，不在此列；
    有名有姓的相关者不拦——主角要寻得到他们。upcoming 由调用方给出(已除去本回合拉上台的那一桩：上了台的原著用得着它的人马)。"""
    g, done, out = world.graph, set(world.done), {}
    events = [ev for ev, _ in upcoming if ev["id"] not in done and not broken(world, ev)]
    for s in sorted(g.where(type=crowd.GROUP)):
        leader = g.get(s, "leader")
        if not leader or not crowd.is_squad(g, s) or crowd.present(world, s):
            continue
        mine = [ev for ev in events if leader in ev["actors"]]
        at = g.get(s, "location")
        local = [ev for ev in mine if at and (ev["where"] == at or ev["where"] in situation.near(world, at)
                                              or ev["where"].split("·")[0] == at.split("·")[0])]
        if mine:
            out[s] = (local or mine)[0]["id"]
    return out


def _premises(world, ev: dict) -> list[tuple]:
    """原著的前提(不论在不在主角眼前)：明写的前提、情境前提、死者不再登场、主角手中之物不会飞走。"""
    g = world.graph
    touched = sorted(set(ev["actors"]) | {op.get("id") for op in ev["effects"] if isinstance(op.get("id"), str)})
    unmet = [(nid, key, want) for nid, key, want in ev["requires"] if not holds(g, nid, key, want)]
    unmet += [(op["src"], "~" + op["rel"], op["dst"]) for op in ev["effects"]  # 救人的原著，须那人仍受制：已被主角救走便不必再救
              if op.get("op") == "unlink" and op.get("rel") in situation.CUSTODY and not holds(g, op["src"], "~" + op["rel"], op["dst"])]
    unmet += [(a, "status", "alive") for a in ev["actors"] if g.get(a, "status") == "dead"]       # 死者不再登场
    unmet += [(i, "holder", "非主角") for i in touched if g.kind(i) == "item" and g.get(i, "holder") == "player"]  # 主角手中之物
    for a in ev["actors"]:  # 人要赶得到(v11)：衍生事件排定时赶得到，到期时也要赶得到；原著要用的人被场外剧情带去了远处(strayed)，得赶得回来
        since = ev.get("made", ev["day"]) if ev.get("derived") else g.get(a, "strayed")
        loc = g.get(a, "location")
        if not isinstance(since, int) or loc == ev["where"] or g.get(a, "status") == "dead":
            continue
        d = access.reach(world, loc).get(ev["where"]) if loc else None
        if d is None or d > max(0, ev["day"] - since) + 1:
            unmet.append((a, "赶不到", ev["where"]))
    return unmet


def intact(world, ev: dict) -> bool:
    """一桩尚未到期之事的前提此刻是否还在(v11，场外编剧的「原著前置未变」)：只看再也挽不回的——要上场的人死了、赶不到了。
    别的前提(某人负伤、某人扣着人质)多半由此前的原著一桩桩造成，此刻不成立不等于破了；谁正在主角身边也是到期那一刻才判的事。"""
    g = world.graph
    if any(g.get(a, "status") == "dead" for a in ev["actors"]) or \
            any(key == "status" and want != "dead" and g.get(nid, "status") == "dead" for nid, key, want in ev["requires"]):
        return False
    return not any(key == "赶不到" for _, key, _ in _premises(world, ev))


def stray(world, ev: dict, applied: list):
    """场外剧情挪动了的人记下那一日(strayed)：他离了原著的轨道，原著要用他时得赶得回来；原著与导演再挪动他，即回到轨道上(effects 清掉)。"""
    g = world.graph
    for op in applied:
        if op.get("op") == "set" and op.get("key") == "location" and g.kind(op.get("id")) == "person":
            g.nodes[op["id"]]["strayed"] = ev["day"]


def coming(world, ev: dict) -> list[str]:
    """原著要把哪几人送到主角这里(此地或近旁)：事发在远处，后果却让人来到主角眼前(v11)。"""
    g, close = world.graph, situation.near(world)
    return sorted({op["id"] for op in ev["effects"] if isinstance(op, dict) and op.get("op") == "set" and op.get("key") == "location"
                   and g.kind(op.get("id")) == "person" and op.get("value") in close
                   and g.get(op["id"], "location") not in close and g.get(op["id"], "status") != "dead"})


def onstage(world, ev: dict) -> bool:
    """这桩原著是否发生在主角眼前：事发之地是此地或近旁；或相关者正在主角身边、前提都在、正当其时(迟不过 LATE 日)——
    原著要把人从主角身边带走(段誉该去后山了)，不在场外悄悄把他传送走、也不就此作罢，交导演演出这一别：主角可以拦、可以同去、可以目送。
    同行者与未了之事所系之人不在此列：主角把人带在身边，他的原著便不再来要人(场外作罢，见 verdict)；过了时候的旧事也不回头拽人。
    原著要把人送到主角这里(v11)，同样交导演演出来人：主角眼前的变化只有一个主，远处的结算不把人悄悄塞到他跟前。"""
    if ev["where"] in situation.near(world):
        return True
    fresh = world.clock.day - ev["day"] <= LATE
    if coming(world, ev) and fresh and not _premises(world, ev):
        return True
    with_me = set(ev["actors"]) & situation.around(world)
    if not with_me or with_me & entangled(world):
        return False
    return fresh and not _premises(world, ev)


def _unmet(world, ev: dict) -> list[tuple]:
    g, unmet = world.graph, _premises(world, ev)
    if not onstage(world, ev):  # 场外之事：正在主角眼前(此地、近旁、片区里被带到跟前)的人分身不得——非相关者被原著顺带写到，也一样
        close = situation.around(world)
        touched = sorted(set(ev["actors"]) | {op.get("id") for op in ev["effects"] if isinstance(op.get("id"), str)})
        unmet += [(n, "location", ev["where"]) for n in touched if g.kind(n) == "person" and n in close]
        unmet += [(n, "纠缠", ev["where"]) for n in touched if n in entangled(world) and n not in close]
    return unmet


def broken(world, ev: dict) -> bool:
    """原著前提是否已被破坏（区别于仅被污染，含"相关者正在主角身边"）：决定场外这一桩照演还是作罢(或交场外编剧改写)——前提破则不发生。"""
    return bool(_unmet(world, ev))


def _why(world, nid: str, key: str, want) -> str:
    if key == "纠缠":
        return f"{nid}正与主角同行或系于主角未了之事，其行止已不照原著"
    if key == "赶不到":
        return f"{nid}身在{world.graph.get(nid, 'location')}，赶不到{want}"
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
    return list(dict.fromkeys(reasons))


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
    """裁定一桩到期的场外之事(v11 演绎与创作)：canon 照演 / rewrite 交场外编剧改写 / skip 作罢。
    原著前置未变就照原著演——被主角扰动过、相关者染了因果，也照演(演绎家不调模型)；衍生事件前提都在，也照演。
    前提破了：附近的、或分量重的原著交场外编剧，按原著的逻辑或接近原著的手法写出新的剧情线；远方小事作罢；
    衍生事件前提破了即作罢(相关者往后的路由续写接上)；纠缠者的场外之事前提已破即作罢——他们的行止只听导演与此地剧情。
    前提都在、后果却落不了地(此日已被别处调遣、物已不存)，等同前提已破：一桩事是一个事务，不半截照演。"""
    reasons, torn = dirt(world, ev), broken(world, ev)
    if not torn:
        stuck = [f"{describe(op)}落不了：{why}" for op, why in _stuck(world, ev["effects"], "derived" if ev.get("derived") else "canon", _scope(ev))]
        reasons, torn = reasons + stuck, bool(stuck)
    if not torn:
        return "canon", reasons
    if ev.get("derived") or set(ev["actors"]) & entangled(world):
        return "skip", reasons
    return ("rewrite" if ev["weight"] >= 2 or tier <= 1 else "skip"), reasons


def _adrift(world, ev: dict):
    """这一桩没有发生：相关的活人原著线已变，往后的路交场外编剧(world/plot 的创作家)。"""
    g = world.graph
    for a in ev["actors"]:
        if g.kind(a) == "person" and g.get(a, "status") != "dead":
            g.nodes[a]["adrift"] = True


def settle(world, ev: dict, outcome: dict, origin: str, day: int | None = None, witnessed: bool | None = None,
           partial: bool = False) -> dict | None:
    """结算一桩到期之事(原著或衍生事件)。outcome: {happens, summary, effects}；照演即传入 ev 本身。
    场外结算是一个事务：后果先在副本上试演，筋骨落不了即整桩不入账(verdict 已据此改道，这里是最后一道闸)；
    此地上演的(partial)在导演诸拍之后落账，导演挪动过的人原著挪不动——成立的部分照落，账上只记成立之事。
    没有发生的那一桩，相关的活人记作原著线已变(adrift)。衍生事件的说法是 LLM 写的：逐句对账、过剧透的筛子才照录。
    真相盖排定之日的日戳——主角亲眼所见的那一桩则盖今日(day)：迟到才演的戏，传闻不该已在路上走了十天。"""
    world.done.append(ev["id"])
    scope, ops = _scope(ev), outcome.get("effects", [])
    if not outcome.get("happens", True) or (not partial and _stuck(world, ops, origin, scope)):
        _adrift(world, ev)
        return None
    before = situation.around(world)
    applied, rejected = world.apply(ops, origin, scope)
    rejected = [(op, why) for op, why in rejected if not _arrived(world, ops, op)]
    if ev.get("derived"):
        stray(world, ev, applied)
    if partial:  # 主角眼前的原著：在主角这一片上演的，上了台的相关者就在跟前(片区里也一样)；谁因此来去写成连带
        close = situation.near(world)
        if ev["where"] in close:  # 主角已先走一步离开了事发之地：那里的人不跟着上他的名册
            situation.enlist(world, [a for a in ev["actors"] if world.graph.get(a, "location") in close])
        effects._note(world, _comings(world, before))
    summary = _told(world, outcome.get("summary") or ev["summary"], applied, rejected, verify=origin != "canon" or bool(ev.get("derived")))
    if summary is None:
        return None
    return world.record(summary, ev["where"], applied, origin, ev["weight"], ev.get("public", True),
                        day=ev["day"] if day is None else day, witnessed=witnessed)
