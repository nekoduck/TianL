"""
[INPUT]: 依赖 world/profile 的 profile / power_tier / TIERS（单一投影：人与主角此刻的状态切面）、world/actor 的 mood（场外档案的心境），
         world/pacing 的 advise / calm（阻尼、幕间省略的闸门），world/body 的 fate / forecast / wound（命运骰、研习预裁、伤势措辞），依赖 world/lod 的 dirt / NEAR（原著前提核对、近处半径）、world/access（主角眼中的出路与里程、关口、暗路、场外人物可去之地）、
         world/situation（近旁、同行、受制、命悬一线、久悬之事）、world/growth 的 progress / mastery / studiable（研习进度、进境投影、研习对象）
         与 world/ledger 的 NEWS_SPEED、world/scenery 的 card / feature / rooms / dossiers（v8 场景清单）、world/crowd 的 squads / card / lines / agility / besiegers / handle / STEAL_ROLL（v9 人群）、world/stock 的 funds / say / measure / purses / purse（v9 银两），依赖 World 门面的 graph / knowledge / player / clock / truth / canon / done / seed
[OUTPUT]: 对外提供 vista()（v12 隔着关口望得见的人与人群，给导演）、scene()（此刻可见之物，人以「眼前」为准）、build()（玩家视锥上下文包）、backstage()（导演后台包）、focus()（举动所指之物的真相）、rule()（较量预裁）、acquainted()（近处的熟人）、
          heard()（已传到某处的江湖近闻）、dossier()、power_tier()、condition()（主角身况标签）
[POS]: v11 世界底座：视锥另有此处铺面(shop：招牌、货与价目、能办的事)与主角听来的消息(heard)；后台另有铺子底细、此处打听得到(假的附真相)、国法与规矩、风物天时、人物底子(取自 world/locale)；近处去向不列近旁的房间。
        world 层朝向 narrative 层的只读出口，也是基础设施"服务 LLM"的主要形态：
       状态字段一律取自 profile(v4 单一投影)：condition、build、backstage 只取不同切面，不各算一遍——进境、伤势、心境、眼下之事、立场三处同时看得见；
       场景清单(v8)：视锥里的景物与器物按等级详略(寻常只有名字与方位，器物另有类别、描述与属性，主角身上的要物连内容)，后台另列近旁各处摆着、藏着什么与要物的内容底细；
       build 给编剧——在场取真相、场外取认知，只含玩家已知（他人暗中的心思在揭开之前不入视锥），人物带伤势、神色、眼下之事、境况与对你的立场，主角带武学与进境，另列近旁之人与同行者；近日传闻不含主角自己的作为（那在近来里）；
       backstage 给导演——此地另有其人(v5：同在近旁片区、此刻不在眼前，要他们登场写 arrive)、近处的熟人(一日之内主角认得或有过交集的人)、上回合的账文分歧(v6：正文写了、账上却不成立的事)、原著近事相关者到位时写「可随时上演」、焦点(玩家所指之物此刻在谁手里、多远、主角以为在哪)、受制、
       主角眼前上演的原著(v5：在此地、在近旁的哪一间(next_door)、或要把身边哪几人带往别处(away)；v11 或要把哪几人送到主角这里(coming))、近日将至的原著、较量预裁、隐匿之人、暗藏之物、
       到时候的隐情(暗藏之物写明发现时用的名字)、各方图谋、功力对比、在场武学、研习进度与研习预裁(玩家所指的秘籍或武学)、此地出发的关口、近处未被发现的暗路、主角走得到的去处、未兑现的伏笔、久悬之事、命运骰、
       原著近事前提已破者标明只作背景、不得进台词，节奏(看本幕之问的结局：一问已解宜开新问、局面平静则提示幕间省略，连番被打断则必须了结；另有 pacing 的阻尼：同一主题、同一诉求连番出现，或在一处僵持而局面不动)，让它编织的剧情有据可依；裁决与日程由系统算定，导演只负责演出
       v9：scene 另有眼前的人群(squads)，build 给出人群卡片(叫法、站着几人、人人带着什么、是否正围攻你)与主角的银两；
       backstage 另有群战预裁 crowd(整群之力、脱身、偷取，与 acts 执行的是同一套规则)、各人身上的银两 money、较量预裁每行加上夺不夺得下与偷不偷得到(WIN 是算赢的那几档，acts 夺取同用)；
       condition 另有被一群人围住与身上的银两；暗藏之物与研习的提示写成事码(揭开、拿取、研习)
       v10：后台另有 flocks——近处不在跟前的人群(要他们来写赶来，要几人从中分出)
       v12：后台另有 reserved——原著近事要用的人马(事前不得登场，远远望见可以)，flocks 不再列它们；近处的熟人另收三日内见过的人(MET_DAYS)，熟人与此地另有其人各行附与谁同行、押着谁；焦点里同在这一片而不在眼前的人写明主角正在寻他；视锥另有远处可见(afar)，后台另有隔着关口望得见(vista)；身况标签把人群的押解与围攻并列(被X押着)
       v11：近事里场外编剧排进日程的衍生事件标作「场外剧情」，与原著一样只可借风声伏笔；dossier 是场外编剧任务书里一个人的底子
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from . import access, actor, body, crowd, growth, locale, lod, pacing, perspective, scenery, situation, stock
from .effects import usable
from .ledger import NEWS_SPEED
from .profile import TIERS, power_tier, profile, ties
from .profile import tier_index as _tier_index

NEWS_WINDOW = 3
PLACES_SHOWN = 15  # 后台只列最近的若干去处；更远之地导演仍可直呼其名，距离由系统结算
SECRET_HORIZON = 30  # 隐情的揭示事件须在一月内到期（或已发生）才交给导演——第四十八回的真相不该在第一回就摆上桌
FEEBLE = 5           # 功力不及此者（孩童、文弱之辈）不入较量预裁


def condition(world) -> list[dict]:
    """主角身况的文字标签：伤势、功力档、姿态、境况、随身器物、所负武学(带进境)与习练中的功夫——数值隐于其后，字段取自 profile。"""
    me = profile(world, "player")
    tags = [{"text": me["wound"], "tone": me["tone"]}, {"text": me["tier"], "tone": "plain"}]
    if me["posture"] and me["posture"] != "站立":
        tags.append({"text": me["posture"], "tone": "plain"})
    tags += [{"text": c, "tone": "warn"} for c in me["conditions"]]
    tags += [{"text": f"被{crowd.handle(world.graph, s)}围住", "tone": "warn"} for s in crowd.besiegers(world)]  # 人群(v9)
    tags += [{"text": f"被{crowd.handle(world.graph, s)}押着", "tone": "warn"} for s, rel in crowd.holders(world) if rel != crowd.BESIEGE]  # v12
    tags += [{"text": f"持有{i}" + (f"（{stock.measure(world.graph, i)}）" if stock.measure(world.graph, i) else ""), "tone": "plain"}
             for i in me["carrying"]]
    if me["money"] > stock.EPS:  # 银两(v9)：是数不是器物
        tags.append({"text": f"银两{stock.say(me['money'])}", "tone": "plain"})
    tags += [{"text": f"身负{a['art']}" + ("" if a["stage"] in ("已会", "入门") else f"·{a['stage']}"), "tone": "plain"}
             for a in me["arts"] if a["learned"]]
    tags += [{"text": f"习练{a['art']}中", "tone": "plain"} for a in me["arts"] if not a["learned"]]
    return tags


def scene(world) -> dict:
    """玩家此刻能亲眼看见的一切（真相，排除隐匿节点）。人以「眼前」为准(situation.around)：
    主角站在片区里(无量山、中原)，只看得见被剧情带到跟前的人，同在一片的其余人交导演(elsewhere)。"""
    g, close = world.graph, situation.around(world)
    wide = situation.area(world, world.here)

    def at(kind):
        return [n for n in g.where(type=kind, location=world.here) if not g.get(n, "hidden")]

    people = at("person")
    return {"people": [p for p in people if p in close],
            "dead": [p for p in people if g.get(p, "status") == "dead" and (not wide or p in situation.cast(world))],
            "features": at("feature"), "items": [i for i in at("item") if usable(world, i)],
            "squads": crowd.squads(world)}  # 无名之众(v9)：一群算一个，近旁之内都在眼前


def _salient(world, p) -> tuple:
    """近处之人的轻重：与主角有过交集的在前，叫得出名字的次之。"""
    return (-len((world.graph.get(p, "bond") or {}).get("log", [])), not perspective.knows(world, "player", p), p)


MET_DAYS = 3  # 近处的熟人另收几日内见过的人(v12)：钟灵在厅上当着主角放貂救人，没报过名、没交过手，也是熟人


def _ties(world, p) -> str:
    """此人带着谁(v12)：与谁同行、押着谁——导演叫他来，同行者与人质会一并来(situation.carried)。"""
    band, held = situation.company(world, p), situation.hostages(world, p)
    return (f"｜与{'、'.join(band)}同行" if band else "") + (f"｜押着{'、'.join(held)}" if held else "")


def acquainted(world, limit: int = 6) -> list[str]:
    """近处的熟人(v5)：一日路程之内、此刻不在眼前，主角叫得出名字或与之有过交集的人——导演知道他们就在不远处，剧情需要时可以让他们找来。
    v12 另收 MET_DAYS 日内见过的人(黑板 met)，未识名的注明主角只识其貌；每行附与谁同行、押着谁；至多六人。"""
    g, dist, close = world.graph, world.graph.distances(world.here), situation.around(world) | set(situation.elsewhere(world))
    met, today = world.player.get("met") or {}, world.clock.day
    known = [p for p in g.where(type="person") if p not in close and g.get(p, "status") != "dead" and not g.get(p, "dormant")
             and dist.get(g.get(p, "location"), lod.NEAR + 1) <= lod.NEAR
             and (perspective.knows(world, "player", p) or (g.get(p, "bond") or {}).get("log") or today - met.get(p, -10 ** 6) <= MET_DAYS)]
    out = []
    for p in sorted(known, key=lambda p: _salient(world, p))[:limit]:
        where, belief = g.get(p, "location"), world.knowledge.view(p).get("location")
        out.append(f"{p}：身在{where}（距此{dist.get(where, '?')}日）" + (f"，主角以为在{belief}" if belief and belief != where else "")
                   + ("" if perspective.knows(world, "player", p) else f"｜主角只识其貌：{perspective.guise(world, p)}") + _ties(world, p))
    return out


# ============================================================
#  玩家视锥（编剧与导演共享）
# ============================================================
def _believed(world, nid: str) -> str:
    b = world.knowledge.view(nid)
    if b.get("status") == "dead":
        return "据你所知已故"
    return f"据你所知身在{b['location']}" if b.get("location") else "下落不明"


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
               "status": g.get(p, "status"), "tier": (pf := profile(world, p))["tier"], "wound": pf["wound"],
               "persona": g.get(p, "persona"), "appearance": g.get(p, "appearance"), "speech": g.get(p, "speech"),
               "carrying": pf["carrying"], "toward_you": pf["ties"], "mood": pf["mood"], "intent": pf["intent"],
               "conditions": pf["conditions"],
               "seen_as": None if perspective.knows(world, "player", p) else perspective.handle(world, p),  # 主角不知其名：只叫得出外貌
               "knows_you": perspective.knows(world, p, "player")} for p in s["people"]]
    carried = [scenery.card(world, i, inside=True) for i in me["inventory"]]  # 主角身上的要物连内容一起给：读得到
    news = [f"{world.clock.label(e['day'])}·{e['where']}：{e['summary']}"  # 主角自己的作为已在【近来】里，不再当传闻
            for e in (world.truth.get(i) for i in world.knowledge.known) if e["origin"] != "director"][-NEWS_WINDOW:]
    return {
        "time": world.clock.label(),
        "player": {"name": me["name"], "hp": f"{me['hp']}/{me['max_hp']}", "tier": power_tier(me["power"]),
                   "posture": me["posture"], "skills": me["skills"], "inventory": carried,
                   "wound": body.wound(world)[0], "arts": [a["detail"] for a in growth.mastery(world)],
                   "origin": me["origin"], "goal": me["goal"], "conditions": me["conditions"], "threads": me["threads"],
                   "synopsis": me["synopsis"], "en_route": me.get("en_route"), "money": stock.say(stock.funds(world, "player"))},
        "scene": {"name": here, "region": g.get(here, "region"), "desc": g.get(here, "desc"),
                  "state": g.get(here, "state"), "lore": g.get(here, "lore", [])},
        "features": [scenery.feature(world, f) for f in s["features"]],
        "items": [scenery.card(world, i) for i in s["items"]],  # 场景清单(v8)：寻常之物只有名字与方位，器物另有类别、描述与属性
        "people": people,
        "squads": [crowd.card(world, q) for q in s["squads"]],  # 人群(v9)：叫法、站着几人、人人带着什么
        "dead": s["dead"],
        "relations": _relation_lines(world, s["people"] + s["dead"], visible),
        "party": situation.party(world),
        "nearby": [f"{p}（{g.get(p, 'title')}）在{g.get(p, 'location')}" for p in sorted(situation.around(world) - set(s["people"]))],
        "exits": access.exits(world),
        "news": news,
        "journal": me["journal"],
        "afar": _afar(world),                     # 远处可见(v12)：本回合望见的人与人群——隔着关口望得见、听不见、够不着
        "shop": locale.shop(world, writer=True),  # 此处的铺面(v11)：招牌、货与价目、能办的事——进了店都看得见
        "heard": locale.heard(world),             # 主角听来的消息(v11)：照原样，未必是真
    }


def _afar(world) -> list[dict]:
    """远处可见(v12，给编剧)：本回合望见的人(叫法由 veil 换、外貌、所在)与人群(叫法、约多少人、所在)。"""
    g, out = world.graph, []
    for x in situation.sighted(world):
        if crowd.is_squad(g, x):
            out.append({"kind": "group", "name": crowd.handle(g, x), "count": crowd.standing(g, x), "where": g.get(x, "location")})
        elif g.kind(x) == "person":
            out.append({"kind": "person", "name": x, "appearance": g.get(x, "appearance"), "where": g.get(x, "location")})
    return out


def vista(world, reserved=None) -> list[str]:
    """隔着关口望得见的人与人群(v12，给导演)：带关口种类——「段誉（镇南王世子）在无量山（隔着险径）」；原著近事要用的人马也列，注明只可望见。"""
    g, gates, out = world.graph, situation._vistas(world), []
    able = situation.sightable(world)
    for loc in sorted(gates):
        across = "、".join(sorted(gates[loc]))
        for x in sorted(able):
            if g.get(x, "location") != loc:
                continue
            if crowd.is_squad(g, x):
                out.append(f"{x}（{crowd.handle(g, x)}，站着{stock.cn(crowd.standing(g, x))}人）在{loc}（隔着{across}）"
                           + ("：原著近事要用的人马，只可望见" if x in (reserved or {}) else ""))
            else:
                out.append(f"{x}（{g.get(x, 'title') or '无名'}）在{loc}（隔着{across}）")
    return out


# ============================================================
#  导演后台：玩家看不见、但剧情必须依据的一切
# ============================================================
rule, WIN = body.rule, body.WIN  # 较量预裁(v13 起定义在 body：伤人的封顶与后台给导演看的是同一张表、同一颗命运骰)；WIN 是算赢的那几档，acts 夺取同用


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
                + (f"，受制于{'、'.join(held)}" if held else "") + ("，正随你同行" if nid in situation.party(world) else "") \
                + ("｜主角正在寻他：要他现身写赶来；寻不到也要在拍里交代缘由" if nid in situation.elsewhere(world) else "")  # v12 同在这一片而不在眼前
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


def backstage(world, stage: dict | None = None, upcoming=(), tempo=(), aim=(), ready=frozenset(), reserved=None) -> dict:
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
            sly = crowd.agility(world, "player") - _tier_index(g.get(p, "power", 30))  # 偷取看身法(v9)：与 acts 同一口径
            ruling.append(f"与{p}：{outcome}" + (f"，主角失气血约{loss}" if loss != "0" else "，主角无损")
                          + f"｜夺取其身上之物{'夺得下' if outcome in WIN else '夺不下'}"
                          + f"｜偷取{'得手' if sly >= 1 or (sly == 0 and fate >= crowd.STEAL_ROLL) else '必被察觉'}")
    study = growth.studiable(world, aim, [h for h in hidden if g.kind(h) == "item"])  # 玩家所指的秘籍与武学：出研习预裁
    dist = access.distances(world, here)  # 主角走得到的去处：绕开不通、条件未备与未被发现之路
    return {
        "fate": fate,
        "stage": {"event": stage, "dirt": lod.dirt(world, stage), "broken": lod.broken(world, stage),
                  "next_door": stage["where"] if stage["where"] != here and stage["where"] in situation.near(world) else None,
                  "away": sorted(set(stage["actors"]) & situation.around(world)) if stage["where"] not in situation.near(world) else [],
                  "coming": lod.coming(world, stage) if stage["where"] not in situation.near(world) else []}
        if stage else None,  # 近旁上演的原著、要把身边之人带往别处的原著、要把人送到主角这里的原著(v11)，都交导演
        "upcoming": [f"{'场外剧情' if ev.get('derived') else '原著'}里此时{ev['summary']}——本局已不成立，只作背景，不得写进任何人的台词" if lod.broken(world, ev) else
                     f"{'场外剧情·' if ev.get('derived') else ''}{'相关者已到位，可随时上演' if ev['id'] in ready else '今日稍后' if n <= 0 else f'最迟{n}日后'}·{ev['where']}：{ev['summary']}（{'、'.join(ev['actors'])}）"
                     for ev, n in upcoming],  # 场外剧情(v11)：场外编剧排进日程的衍生事件，与原著同样只可借风声伏笔
        "ruling": ruling,
        "crowd": crowd.lines(world),  # 群战预裁(v9)：整群之力、脱身、偷取
        "flocks": crowd.afar(world, held=reserved),  # 近处不在跟前的人群(v10)：要他们来写赶来，要几人从中分出
        "reserved": crowd.reserved_lines(world, reserved or {}),  # 原著近事要用的人马(v12 lod.reserved)：事前不得登场，远远望见可以
        "vista": vista(world, reserved),     # 隔着关口望得见的人与人群(v12)：远远看见写 望见，要他到跟前写 赶来
        "money": _money(world, s["people"]),  # 各人身上的银两(v9)：掏得出多少由账定
        "tempo": _tempo(world, tempo),
        "fatigue": pacing.advise(world),
        "peril": "主角命悬一线：本回合必须以昏迷、被救、被俘或脱身收场，不得再受重创" if situation.imperiled(world) else "",
        "hidden": [f"{n}（{g.get(n, 'type')}）：{g.get(n, 'persona') or g.get(n, 'desc')}"
                   + (f"｜{g.get(n, 'hint')}" if g.get(n, "hint") else "")
                   + (f"｜找出来写 揭开 {n}、拿到手写 拿取 {n}（拍文里怎么称呼都行，事码里用此名，不要另立物件）"
                      if g.kind(n) == "item" else "") for n in hidden],
        "secrets": secrets,
        "agendas": [f"{p}：{g.get(p, 'agenda')}" for p in s["people"] if g.get(p, "agenda")],
        "odds": odds,
        "grants": [f"{growth.progress(world, i)}（可得「{g.get(i, 'grants')['skill']}」；功力由系统分阶兑现，写 研习 即可）"
                   + (f"｜研习预裁：{_luck(world, i)}" if i in study else "")
                   for i in [*me["inventory"], *s["items"], *(h for h in hidden if g.kind(h) == "item")]
                   if g.get(i, "grants")]
                  + [f"{growth.progress(world, k)}（求教身边会的人，写 研习 {k}）｜研习预裁：{_luck(world, k)}"
                     for k in study if g.kind(k) == "skill"],
        "focus": focus(world, aim),
        "drift": list(me.get("drift") or []),
        "hooks": [f"{h['text']}" + (f"（已到期：本回合兑现或交代其落空）" if h["due"] <= me.get("turn", 0) else
                                    f"（{h['due'] - me.get('turn', 0)}回合内兑现）") for h in me.get("hooks", [])],
        "stale": situation.stale(world),
        "custody": [f"{e['dst']}受制于{e['src']}（{e['rel']}）" for e in g.edges if e["rel"] in situation.CUSTODY
                    and situation.around(world) & {e["src"], e["dst"]}],
        "arts": _arts(world, ["player", *s["people"]]),
        "passes": access.passes(world),
        "secret_ways": access.secret_ways(world, {loc for loc, d in dist.items() if d <= lod.NEAR}),
        "places": [f"{loc}（{d}日）" for loc, d in sorted(dist.items(), key=lambda x: x[1])
                   if loc != here and loc not in situation.near(world)][:PLACES_SHOWN],  # 近旁的房间不占名额(v11)：它们在【近旁】里
        "elsewhere": [f"{p}（{g.get(p, 'title') or '无名'}）在{g.get(p, 'location')}一带" + _ties(world, p)  # 有过交集的、怀有图谋的在前；v12 附同行、押着
                      for p in sorted(situation.elsewhere(world), key=lambda p: (*_salient(world, p)[:2], not g.get(p, "agenda"), p))][:8],
        "acquainted": acquainted(world),
        "rooms": scenery.rooms(world),        # 近旁各处摆着、藏着什么(v8 场景清单)：导演知道隔壁有什么，不必凭空添置
        "dossiers": scenery.dossiers(world),  # 要物的内容与底细：有人翻看就照此写
        "shop": locale.shop(world),           # 铺子底细(v11)：当值的伙计、货架存货、能办的事、招工
        "asks": locale.asks(world),           # 此处打听得到的消息(v11)：向谁、怎么问、赏钱多少，假的附真相
        "law": locale.law(world),             # 此地的国法与在场门派的规矩(v11)
        "season": locale.season(world),       # 天时：四季气候、节令集期、此地的险(v11)
        "traits": locale.traits(world),       # 在场有名之人的底子(v11)：名声、好恶软肋、手段底线、能替人做的事
    }


def _money(world, people) -> list[str]:
    """主角与在场之人身上有多少银两(零钱与钱袋里的)——拍里有人掏钱，掏得出多少由这笔账定。"""
    g, out = world.graph, [f"主角：{stock.say(stock.funds(world, 'player'))}"]
    for p in people:
        bags = [i for i in stock.purses(world, p) if stock.purse(g, i) > stock.EPS]
        if stock.funds(world, p) > stock.EPS:
            out.append(f"{p}：{stock.say(stock.funds(world, p))}" + (f"（{'、'.join(f'{i}里{stock.say(stock.purse(g, i))}' for i in bags)}）" if bags else ""))
    return out


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
    """单个人物的真相档案——场外编剧(v11)任务书里一个人的底子（远处看真相，不看玩家认知）。"""
    g = world.graph
    loc = g.get(pid, "location")
    return {"name": pid, "title": g.get(pid, "title"), "status": g.get(pid, "status"), "location": loc,
            "faction": g.get(pid, "faction"), "agenda": g.get(pid, "agenda"), "mood": actor.mood(world, pid),
            "intent": g.get(pid, "intent"),
            "tier": power_tier(g.get(pid, "power", 30)), "persona": g.get(pid, "persona"),
            "exits": access.steps(world, loc) if loc else []}
