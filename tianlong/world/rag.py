"""
[INPUT]: 依赖 world/rules 的 scene()，依赖 World 门面的 graph / knowledge / player / clock / truth
[OUTPUT]: 对外提供 build()（场景触发式 GraphRAG 上下文包）、dossier()（远端推演用人物真相档案）、power_tier()
[POS]: world 层朝向 narrative 层的唯一只读出口——在场者取真相，场外者取玩家认知，secret 边与 hidden 节点一律过滤；
       LLM 看到的世界永远是"玩家视锥"，从结构上杜绝剧透与幻觉
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import rules

TIERS = ((15, "不会武功"), (35, "三流身手"), (60, "二流好手"), (85, "一流高手"), (10**9, "绝顶高手"))
NEWS_WINDOW = 3


def power_tier(power: int) -> str:
    return next(name for cap, name in TIERS if power < cap)


def _believed(world, nid: str) -> str:
    b = world.knowledge.view(nid)
    if b.get("status") == "dead":
        return "据你所知已故"
    return f"据你所知身在{b['location']}" if b.get("location") else "下落不明"


def _toward_player(world, p: str) -> list[str]:
    g = world.graph
    sides = {p, g.get(p, "faction")} - {None}
    return [f"{e['src']}→你：{e['rel']}" if e["dst"] == "player" else f"你→{e['dst']}：{e['rel']}"
            for e in g.edges if {e["src"], e["dst"]} & sides and "player" in (e["src"], e["dst"])]


def _relation_lines(world, people: list[str], visible: set[str]) -> list[str]:
    g, lines = world.graph, []
    for p in people:
        for e in g.relations(p):
            other = e["dst"] if e["src"] == p else e["src"]
            if e.get("secret") or other == "player":
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


def dossier(world, pid: str) -> dict:
    """单个人物的真相档案——供 LOD1/LOD2 推演使用（远端推演看真相，不看玩家认知）。"""
    g = world.graph
    loc = g.get(pid, "location")
    return {"name": pid, "title": g.get(pid, "title"), "status": g.get(pid, "status"), "location": loc,
            "faction": g.get(pid, "faction"), "agenda": g.get(pid, "agenda"), "mood": g.get(pid, "mood"),
            "exits": [n for n, _ in g.roads(loc)] if loc else []}


def build(world) -> dict:
    g, me, here = world.graph, world.player, world.here
    s = rules.scene(world)
    visible = {here, *s["people"], *s["dead"], *s["features"], *s["items"]}
    people = [{"name": p, "title": g.get(p, "title"), "faction": g.get(p, "faction"),
               "status": g.get(p, "status"), "tier": power_tier(g.get(p, "power", 30)),
               "persona": g.get(p, "persona"), "agenda": g.get(p, "agenda"),
               "toward_you": _toward_player(world, p)} for p in s["people"]]
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
        "exits": [f"{loc}（{days}日）" for loc, days in g.roads(here)],
        "news": news,
        "journal": me["journal"],
    }
