"""
[INPUT]: 依赖 world/pacing 的 advise / calm（阻尼、幕间省略的闸门），world/body 的 fate / forecast / wound（命运骰、研习预裁、伤势措辞），依赖 world/lod 的 dirt / NEAR（原著前提核对、近处半径）、world/access（主角眼中的出路与里程、关口、暗路、场外人物可去之地）、
         world/situation（近旁、同行、受制、命悬一线、久悬之事）、world/growth 的 progress（研习进度）
         与 world/ledger 的 NEWS_SPEED，依赖 World 门面的 graph / knowledge / player / clock / truth / canon / done / seed
[OUTPUT]: 对外提供 scene()（此刻可见之物）、build()（玩家视锥上下文包）、backstage()（导演后台包）、focus()（举动所指之物的真相）、rule()（较量预裁）、
          heard()（已传到某处的江湖近闻）、dossier()、power_tier()、condition()（主角身况标签）
[POS]: world 层朝向 narrative 层的只读出口，也是基础设施"服务 LLM"的主要形态：
       build 给编剧——在场取真相、场外取认知，只含玩家已知（他人暗中的心思在揭开之前不入视锥），另列近旁之人与同行者；近日传闻不含主角自己的作为（那在近来里）；
       backstage 给导演——焦点(玩家所指之物此刻在谁手里、多远、主角以为在哪)、受制、此地上演的原著、近日将至的原著、较量预裁、隐匿之人、暗藏之物、
       到时候的隐情(暗藏之物写明发现时用的名字)、各方图谋、功力对比、在场武学、研习进度与研习预裁(玩家所指的秘籍或武学)、此地出发的关口、近处未被发现的暗路、主角走得到的去处、未兑现的伏笔、久悬之事、命运骰、
       原著近事前提已破者标明只作背景、不得进台词，节奏(看本幕之问的结局：一问已解宜开新问、局面平静则提示幕间省略，连番被打断则必须了结；另有 pacing 的阻尼：同一主题、同一诉求连番出现，或在一处僵持而局面不动)，让它编织的剧情有据可依；裁决与日程由系统算定，导演只负责演出
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from . import access, body, growth, lod, pacing, perspective, situation
from .effects import usable
from .ledger import NEWS_SPEED

TIERS = ((15, "不会武功"), (35, "三流身手"), (60, "二流好手"), (85, "一流高手"), (10**9, "绝顶高手"))
NEWS_WINDOW = 3
PLACES_SHOWN = 15  # 后台只列最近的若干去处；更远之地导演仍可直呼其名，距离由系统结算
SECRET_HORIZON = 30  # 隐情的揭示事件须在一月内到期（或已发生）才交给导演——第四十八回的真相不该在第一回就摆上桌
FEEBLE = 5           # 功力不及此者（孩童、文弱之辈）不入较量预裁


def power_tier(power: int) -> str:
    return next(name for cap, name in TIERS if power < cap)


def condition(world) -> list[dict]:
    """主角身况的文字标签：伤势、功力档、姿态、随身器物、所负武学——数值隐于其后。"""
    me = world.player
    wound, tone = body.wound(world)  # 气血与内伤共同定伤势：重伤只给气血三成以下或经脉受损以上
    tags = [{"text": wound, "tone": tone}, {"text": power_tier(me["power"]), "tone": "plain"}]
    if me["posture"] and me["posture"] != "站立":
        tags.append({"text": me["posture"], "tone": "plain"})
    tags += [{"text": c, "tone": "warn"} for c in me["conditions"]]
    tags += [{"text": f"持有{i}", "tone": "plain"} for i in me["inventory"]]
    tags += [{"text": f"身负{s}", "tone": "plain"} for s in me["skills"]]
    return tags


def _tier_index(power: int) -> int:
    return next(i for i, (cap, _) in enumerate(TIERS) if power < cap)


def scene(world) -> dict:
    """玩家此刻能亲眼看见的一切（真相，排除隐匿节点）。"""
    g = world.graph

    def at(kind):
        return [n for n in g.where(type=kind, location=world.here) if not g.get(n, "hidden")]

    people = at("person")
    return {"people": [p for p in people if g.get(p, "status") != "dead"],
            "dead": [p for p in people if g.get(p, "status") == "dead"],
            "features": at("feature"), "items": [i for i in at("item") if usable(world, i)]}


def _held(world, pid: str) -> list[str]:
    return [i for i in world.graph.where(type="item", holder=pid) if not world.graph.get(i, "hidden") and usable(world, i)]


# ============================================================
#  玩家视锥（编剧与导演共享）
# ============================================================
def _believed(world, nid: str) -> str:
    b = world.knowledge.view(nid)
    if b.get("status") == "dead":
        return "据你所知已故"
    return f"据你所知身在{b['location']}" if b.get("location") else "下落不明"


def _toward_player(world, p: str) -> list[str]:
    """此人(及其门派)与主角之间的关系与印象；暗中的心思(secret)在揭开之前不入视锥——编剧看得见的，主角就看得见。"""
    sides = {p, world.graph.get(p, "faction")} - {None}
    return [(f"{e['src']}→你：{e['rel']}" if e["dst"] == "player" else f"你→{e['dst']}：{e['rel']}")
            + (f"（{e['note']}）" if e.get("note") else "")
            for e in world.graph.edges if {e["src"], e["dst"]} & sides and "player" in (e["src"], e["dst"])
            and not (e.get("secret") and not world.knowledge.knows_secret(e))]


def _relation_lines(world, people: list[str], visible: set[str]) -> list[str]:
    g, lines = world.graph, []
    for p in people:
        for e in g.relations(p):
            other = e["dst"] if e["src"] == p else e["src"]
            if other == "player" or (e.get("secret") and not world.knowledge.knows_secret(e)):
                continue
            if other in visible:
                line = f"{e['src']}—{e['rel']}—{e['dst']}"
            elif world.knowledge.knows(other):
                line = f"{e['src']}—{e['rel']}—{e['dst']}（{other}{_believed(world, other)}）"
            else:
                continue
            if line not in lines:
                lines.append(line)
    return lines


def build(world) -> dict:
    g, me, here = world.graph, world.player, world.here
    s = scene(world)
    visible = {here, *s["people"], *s["dead"], *s["features"], *s["items"]}
    people = [{"name": p, "title": g.get(p, "title"), "faction": g.get(p, "faction"),
               "status": g.get(p, "status"), "tier": power_tier(g.get(p, "power", 30)),
               "persona": g.get(p, "persona"), "appearance": g.get(p, "appearance"), "speech": g.get(p, "speech"),
               "carrying": _held(world, p), "toward_you": _toward_player(world, p),
               "seen_as": None if perspective.knows(world, "player", p) else perspective.handle(world, p),  # 主角不知其名：只叫得出外貌
               "knows_you": perspective.knows(world, p, "player")} for p in s["people"]]
    carried = [{"name": i, "desc": g.get(i, "desc")} for i in me["inventory"]]
    news = [f"{world.clock.label(e['day'])}·{e['where']}：{e['summary']}"  # 主角自己的作为已在【近来】里，不再当传闻
            for e in (world.truth.get(i) for i in world.knowledge.known) if e["origin"] != "director"][-NEWS_WINDOW:]
    return {
        "time": world.clock.label(),
        "player": {"name": me["name"], "hp": f"{me['hp']}/{me['max_hp']}", "tier": power_tier(me["power"]),
                   "posture": me["posture"], "skills": me["skills"], "inventory": carried,
                   "origin": me["origin"], "goal": me["goal"], "conditions": me["conditions"], "threads": me["threads"],
                   "synopsis": me["synopsis"], "en_route": me.get("en_route")},
        "scene": {"name": here, "region": g.get(here, "region"), "desc": g.get(here, "desc"),
                  "state": g.get(here, "state"), "lore": g.get(here, "lore", [])},
        "features": [{"name": f, "desc": g.get(f, "desc")} for f in s["features"]],
        "items": [{"name": i, "desc": g.get(i, "desc")} for i in s["items"]],
        "people": people,
        "dead": s["dead"],
        "relations": _relation_lines(world, s["people"] + s["dead"], visible),
        "party": situation.party(world),
        "nearby": [f"{p}（{g.get(p, 'title')}）在{g.get(p, 'location')}" for p in sorted(situation.around(world) - set(s["people"]))],
        "exits": access.exits(world),
        "news": news,
        "journal": me["journal"],
    }


# ============================================================
#  导演后台：玩家看不见、但剧情必须依据的一切
# ============================================================
def rule(gap: int, fate: int) -> tuple[str, str]:
    """较量预裁：档位差 × 命运骰 → (结局, 主角失血区间)。裁决在导演开口前由系统算定，导演只负责把它演出来。"""
    if gap >= 2:
        return ("侥幸脱身，未能得手", "0") if fate >= 95 else ("大败，必受重创", "25~40")
    if gap == 1:
        return ("险胜", "5~10") if fate >= 85 else ("僵持不下", "0~10") if fate >= 55 else ("落败受伤", "15~25")
    if gap == 0:
        return ("小胜", "0~5") if fate >= 55 else ("僵持不下", "0~10") if fate >= 40 else ("小败", "10~20")
    if gap == -1:
        return ("得胜", "0") if fate >= 20 else ("一时失手，僵持", "0~5")
    return ("大胜，手到擒来", "0") if fate >= 5 else ("轻敌失手，仍占上风", "0~5")


def _secret_open(world, edge: dict, canon_by_id: dict) -> bool:
    """隐情何时可交给导演：无揭示事件者随时；有者须其揭示事件已发生，或将在一月内到期。"""
    rb = edge.get("revealed_by")
    if not rb or rb in world.done:
        return True
    ev = canon_by_id.get(rb)
    return ev is not None and ev["day"] - world.clock.day <= SECRET_HORIZON


QUESTION = {"resolved": "已了结", "open": "悬而未决", "interrupted": "被打断"}


def _tempo(world, tempo) -> str:
    """节奏看本幕之问的结局，而不只看张力标签：一问已解宜开新问(局面平静则提示幕间省略)，连番被打断则本回合必须了结。"""
    if not tempo:
        return ""
    line = "近来本幕之问：" + "、".join(QUESTION.get(t, t) for t in tempo)
    if list(tempo[-2:]) == ["interrupted", "interrupted"]:
        line += "——连番被打断，本回合必须让主角此问有个了结，不得再打断"
    elif tempo[-1] == "resolved":
        line += "——上一问已解，宜由人物的图谋或主角的所求引出新问，不必非起刀兵"
        if pacing.calm(world, tempo[-1]) is None:
            line += "；眼下无人相逼：本回合了结此问后宜用 cut 跳到下一处有戏的时刻，不必在此地逐刻细磨"
    elif list(tempo[-3:]) == ["open"] * 3:
        line += "——久悬未决，本回合宜推进或了结"
    return line


def focus(world, ids) -> list[str]:
    """玩家举动所指之物的真相：在哪、谁拿着、多远、主角以为在哪——导演看不见解药在谁身上，就会凭空变出一瓶来。"""
    g, dist, out = world.graph, world.graph.distances(world.here), []
    for nid in sorted(ids):
        kind = g.kind(nid)
        if kind == "person":
            where, held = g.get(nid, "location"), situation.captors(world, nid)
            line = f"{nid}：{STATUS_WORD.get(g.get(nid, 'status'), '')}，身在{where}（距此{dist.get(where, '?')}日）" \
                + (f"，受制于{'、'.join(held)}" if held else "") + ("，正随你同行" if nid in situation.party(world) else "")
        elif kind == "item":
            holder = g.get(nid, "holder")
            line = f"{nid}：" + ("在你身上" if holder == "player" else f"由{holder}随身（{holder}在{g.get(holder, 'location')}）"
                                 if holder else f"在{g.get(nid, 'location')}" + ("，藏而未露" if g.get(nid, "hidden") else ""))
        elif kind == "location":
            line = f"{nid}：距此{dist.get(nid, '?')}日" + ("" if nid in access.distances(world, world.here) else "，主角眼下走不到")
        else:
            continue
        belief = world.knowledge.view(nid) if kind == "person" else {}
        if belief.get("location") and belief["location"] != g.get(nid, "location"):
            line += f"；主角以为在{belief['location']}"
        out.append(line)
    return out


STATUS_WORD = {"alive": "安好", "wounded": "负伤", "dead": "已死"}


def backstage(world, stage: dict | None = None, upcoming=(), tempo=(), aim=()) -> dict:
    g, me, here = world.graph, world.player, world.here
    s = scene(world)
    hidden = [n for n in g.where(location=here) if g.get(n, "hidden") and not g.get(n, "dormant")]
    cast = set(s["people"]) | set(s["dead"]) | set(hidden) | {"player"}
    canon_by_id = {ev["id"]: ev for ev in world.canon}
    secrets = [f"{e['src']}—{e['rel']}—{e['dst']}" for e in g.edges
               if e.get("secret") and {e["src"], e["dst"]} & cast and not world.knowledge.knows_secret(e)
               and _secret_open(world, e, canon_by_id)]
    mine = _tier_index(me["power"])
    fate = body.fate(world)
    odds, ruling = [], []
    for p in s["people"]:
        gap = _tier_index(g.get(p, "power", 30)) - mine
        odds.append(f"{p}：{power_tier(g.get(p, 'power', 30))}，" +
                    ("与主角相当" if gap == 0 else f"{'强' if gap > 0 else '弱'}于主角{abs(gap)}档"))
        if g.get(p, "power", 30) >= FEEBLE:
            outcome, loss = rule(gap, fate)
            ruling.append(f"与{p}：{outcome}" + (f"，主角失气血约{loss}" if loss != "0" else "，主角无损"))
    study = _studies(world, aim, hidden)  # 玩家所指的秘籍与武学：出研习预裁
    dist = access.distances(world, here)  # 主角走得到的去处：绕开不通、条件未备与未被发现之路
    return {
        "fate": fate,
        "stage": {"event": stage, "dirt": lod.dirt(world, stage), "broken": lod.broken(world, stage)} if stage else None,
        "upcoming": [f"原著里此时{ev['summary']}——本局已不成立，只作背景，不得写进任何人的台词" if lod.broken(world, ev) else
                     f"{'今日稍后' if n <= 0 else f'{n}日后'}·{ev['where']}：{ev['summary']}（{'、'.join(ev['actors'])}）"
                     for ev, n in upcoming],
        "ruling": ruling,
        "tempo": _tempo(world, tempo),
        "fatigue": pacing.advise(world),
        "peril": "主角命悬一线：本回合必须以昏迷、被救、被俘或脱身收场，不得再受重创" if situation.imperiled(world) else "",
        "hidden": [f"{n}（{g.get(n, 'type')}）：{g.get(n, 'persona') or g.get(n, 'desc')}"
                   + (f"｜{g.get(n, 'hint')}" if g.get(n, "hint") else "")
                   + (f"｜发现即写 push player inventory {n}（拍文里怎么称呼都行，指令用此名，不要另立物件）"
                      if g.kind(n) == "item" else "") for n in hidden],
        "secrets": secrets,
        "agendas": [f"{p}：{g.get(p, 'agenda')}" for p in s["people"] if g.get(p, "agenda")],
        "odds": odds,
        "grants": [f"{growth.progress(world, i)}（可得「{g.get(i, 'grants')['skill']}」；功力由系统分阶兑现，写 study 即可）"
                   + (f"｜研习预裁：{_luck(world, i)}" if i in study else "")
                   for i in [*me["inventory"], *s["items"], *(h for h in hidden if g.kind(h) == "item")]
                   if g.get(i, "grants")]
                  + [f"{growth.progress(world, k)}（求教身边会的人，写 study {k}）｜研习预裁：{_luck(world, k)}"
                     for k in study if g.kind(k) == "skill"],
        "focus": focus(world, aim),
        "hooks": [f"{h['text']}" + (f"（已到期：本回合兑现或交代其落空）" if h["due"] <= me.get("turn", 0) else
                                    f"（{h['due'] - me.get('turn', 0)}回合内兑现）") for h in me.get("hooks", [])],
        "stale": situation.stale(world),
        "custody": [f"{e['dst']}受制于{e['src']}（{e['rel']}）" for e in g.edges if e["rel"] in situation.CUSTODY
                    and situation.around(world) & {e["src"], e["dst"]}],
        "arts": _arts(world, ["player", *s["people"]]),
        "passes": access.passes(world),
        "secret_ways": access.secret_ways(world, {loc for loc, d in dist.items() if d <= lod.NEAR}),
        "places": [f"{loc}（{d}日）" for loc, d in sorted(dist.items(), key=lambda x: x[1]) if loc != here][:PLACES_SHOWN],
    }


def _studies(world, aim, hidden) -> list[str]:
    """玩家这一举指向的研习对象：够得着的秘籍，或身边有人会的武学。"""
    g, s = world.graph, scene(world)
    books = {i for i in [*world.player["inventory"], *s["items"], *hidden] if g.get(i, "grants")}
    taught = {k for p in situation.around(world) for k in g.get(p, "skills") or []}
    return [i for i in aim if i in books or (g.kind(i) == "skill" and i in taught)]


def _luck(world, source: str) -> str:
    luck = body.forecast(world, source)
    return luck["tier"] + (f"（{luck['why']}）" if luck["why"] else "") + \
        ("——系统已落一级内伤，照此演出" if luck["strain"] else "——照此演出进境，不得另写反噬受伤")


def _arts(world, cast: list[str]) -> list[str]:
    """在场诸人所会武学及其原著表现——导演编排交手时的依据。"""
    g, owners = world.graph, {}
    for p in cast:
        for sk in (world.player["skills"] if p == "player" else g.get(p, "skills") or []):
            owners.setdefault(sk, []).append("主角" if p == "player" else p)
    return [f"{sk}（{'、'.join(who)}）：{g.get(sk, 'desc') or ''}" for sk, who in owners.items()]


def heard(world, locs, limit: int = 5) -> list[str]:
    """已传到这些地方的江湖近闻（含主角的作为）：场外之人据此反应，主角的所为由此真正传开。"""
    today, dists, out, seen = world.clock.day, {}, [], set()
    for loc in locs:
        if loc and loc not in dists:
            dists[loc] = world.graph.distances(loc)
    for e in reversed(world.truth.events):
        if e["id"] in seen or not e.get("public", True):
            continue
        if any(d.get(e["where"], float("inf")) <= (today - e["day"]) * NEWS_SPEED * e["weight"] for d in dists.values()):
            seen.add(e["id"])
            out.append(f"{world.clock.label(e['day'])}·{e['where']}：{e['summary']}")
            if len(out) >= limit:
                break
    return out[::-1]


def dossier(world, pid: str) -> dict:
    """单个人物的真相档案——供 LOD1/LOD2 场外推演使用（远端推演看真相，不看玩家认知）。"""
    g = world.graph
    loc = g.get(pid, "location")
    return {"name": pid, "title": g.get(pid, "title"), "status": g.get(pid, "status"), "location": loc,
            "faction": g.get(pid, "faction"), "agenda": g.get(pid, "agenda"), "mood": g.get(pid, "mood"),
            "tier": power_tier(g.get(pid, "power", 30)), "persona": g.get(pid, "persona"),
            "exits": access.steps(world, loc) if loc else []}
