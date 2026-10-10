"""
[INPUT]: 依赖 random.Random（种子化命运骰），依赖 World 门面的 graph / knowledge / player / clock / truth / seed
[OUTPUT]: 对外提供 scene()（此刻可见之物）、build()（玩家视锥上下文包）、backstage()（导演后台包）、dossier()、power_tier()、condition()（主角身况标签）
[POS]: world 层朝向 narrative 层的只读出口，也是基础设施"服务 LLM"的主要形态：
       build 给编剧——在场取真相、场外取认知，只含玩家已知；
       backstage 给导演——隐匿之人、暗藏之物、未揭隐情、各方图谋、功力对比、在场武学、远近道路、命运骰，让它编织的剧情有据可依
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import random

from .effects import usable

TIERS = ((15, "不会武功"), (35, "三流身手"), (60, "二流好手"), (85, "一流高手"), (10**9, "绝顶高手"))
NEWS_WINDOW = 3
PLACES_SHOWN = 15  # 后台只列最近的若干去处；更远之地导演仍可直呼其名，距离由系统结算


def power_tier(power: int) -> str:
    return next(name for cap, name in TIERS if power < cap)


# 气血不报数字，只报身况：(气血比例下限, 措辞, 语气)；语气 plain/warn/alert 交由表现层决定着色
WOUNDS = ((0.9, "安然无恙", "plain"), (0.6, "轻伤", "warn"), (0.3, "重伤", "warn"), (0.0, "命悬一线", "alert"))


def condition(world) -> list[dict]:
    """主角身况的文字标签：伤势、功力档、姿态、随身器物、所负武学——数值隐于其后。"""
    me = world.player
    ratio = me["hp"] / me["max_hp"]
    wound, tone = next((text, tone) for floor, text, tone in WOUNDS if ratio >= floor)
    tags = [{"text": wound, "tone": tone}, {"text": power_tier(me["power"]), "tone": "plain"}]
    if me["posture"] and me["posture"] != "站立":
        tags.append({"text": me["posture"], "tone": "plain"})
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
    sides = {p, world.graph.get(p, "faction")} - {None}
    return [f"{e['src']}→你：{e['rel']}" if e["dst"] == "player" else f"你→{e['dst']}：{e['rel']}"
            for e in world.graph.edges if {e["src"], e["dst"]} & sides and "player" in (e["src"], e["dst"])]


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
               "carrying": _held(world, p), "toward_you": _toward_player(world, p)} for p in s["people"]]
    carried = [{"name": i, "desc": g.get(i, "desc")} for i in me["inventory"]]
    news = [f"{world.clock.label(e['day'])}·{e['where']}：{e['summary']}"
            for e in (world.truth.get(i) for i in world.knowledge.known[-NEWS_WINDOW:])]
    return {
        "time": world.clock.label(),
        "player": {"name": me["name"], "hp": f"{me['hp']}/{me['max_hp']}", "tier": power_tier(me["power"]),
                   "posture": me["posture"], "skills": me["skills"], "inventory": carried},
        "scene": {"name": here, "region": g.get(here, "region"), "desc": g.get(here, "desc"),
                  "state": g.get(here, "state"), "lore": g.get(here, "lore", [])},
        "features": [{"name": f, "desc": g.get(f, "desc")} for f in s["features"]],
        "items": [{"name": i, "desc": g.get(i, "desc")} for i in s["items"]],
        "people": people,
        "dead": s["dead"],
        "relations": _relation_lines(world, s["people"] + s["dead"], visible),
        "exits": [{"name": loc, "days": days} for loc, days in g.roads(here)],
        "news": news,
        "journal": me["journal"],
    }


# ============================================================
#  导演后台：玩家看不见、但剧情必须依据的一切
# ============================================================
def backstage(world) -> dict:
    g, me, here = world.graph, world.player, world.here
    s = scene(world)
    hidden = [n for n in g.where(location=here) if g.get(n, "hidden") and not g.get(n, "dormant")]
    cast = set(s["people"]) | set(s["dead"]) | set(hidden) | {"player"}
    secrets = [f"{e['src']}—{e['rel']}—{e['dst']}" for e in g.edges
               if e.get("secret") and {e["src"], e["dst"]} & cast and not world.knowledge.knows_secret(e)]
    mine = _tier_index(me["power"])
    odds = []
    for p in s["people"]:
        gap = _tier_index(g.get(p, "power", 30)) - mine
        odds.append(f"{p}：{power_tier(g.get(p, 'power', 30))}，" +
                    ("与主角相当" if gap == 0 else f"{'强' if gap > 0 else '弱'}于主角{abs(gap)}档"))
    dist = g.distances(here)
    return {
        "fate": random.Random(f"{world.seed}:{world.clock.tick}").randint(1, 100),
        "hidden": [f"{n}（{g.get(n, 'type')}）：{g.get(n, 'persona') or g.get(n, 'desc')}"
                   + (f"｜{g.get(n, 'hint')}" if g.get(n, "hint") else "") for n in hidden],
        "secrets": secrets,
        "agendas": [f"{p}：{g.get(p, 'agenda')}" for p in s["people"] if g.get(p, "agenda")],
        "odds": odds,
        "grants": [f"{i}：研习可得「{g.get(i, 'grants')['skill']}」，功力+{g.get(i, 'grants')['power']}"
                   for i in [*me["inventory"], *s["items"], *(h for h in hidden if g.kind(h) == "item")]
                   if g.get(i, "grants")],
        "arts": _arts(world, ["player", *s["people"]]),
        "places": [f"{loc}（{d}日）" for loc, d in sorted(dist.items(), key=lambda x: x[1]) if loc != here][:PLACES_SHOWN],
    }


def _arts(world, cast: list[str]) -> list[str]:
    """在场诸人所会武学及其原著表现——导演编排交手时的依据。"""
    g, owners = world.graph, {}
    for p in cast:
        for sk in (world.player["skills"] if p == "player" else g.get(p, "skills") or []):
            owners.setdefault(sk, []).append("主角" if p == "player" else p)
    return [f"{sk}（{'、'.join(who)}）：{g.get(sk, 'desc') or ''}" for sk, who in owners.items()]


def dossier(world, pid: str) -> dict:
    """单个人物的真相档案——供 LOD1/LOD2 场外推演使用（远端推演看真相，不看玩家认知）。"""
    g = world.graph
    loc = g.get(pid, "location")
    return {"name": pid, "title": g.get(pid, "title"), "status": g.get(pid, "status"), "location": loc,
            "faction": g.get(pid, "faction"), "agenda": g.get(pid, "agenda"), "mood": g.get(pid, "mood"),
            "tier": power_tier(g.get(pid, "power", 30)), "persona": g.get(pid, "persona"),
            "exits": [n for n, _ in g.roads(loc)] if loc else []}
