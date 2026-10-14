"""
[INPUT]: 依赖 world/growth 的 STAGES（研习账）、world/body 的 severity、world/situation 的 party / captors，World 门面的 player / graph / truth / here（鸭子类型）
[OUTPUT]: 对外提供 track()（按已成立的事实推进主角线，返回本回合跨入的阶段或 None）、line()（场记里的主角线一句）、STAGES
[POS]: story 层的主角线——出身给的「所求」升格为一条有阶段的线：起意 → 入局 → 受挫 → 抉择 → 了结。
       阶段由已成立的事实推进(只进不退)，规则按所求的类别写死在这里，不靠 LLM 判断：求武学看秘籍到手、研习受阻或带伤、练到小成；
       挣名字看众目之下的作为传开了几桩；护人看那人随行、被擒、平安到地头。抉择是叙事上的一刻，规则测不出，场记在受挫之后提示导演安排。
       了结之后场记请导演从主角最深的关系或最急的时限里提一条新的所求，写 所求(v9 事码；旧写法 set player goal 照收)——这是唯一交给 LLM 的一步；
       goal 一变，主角线即从起意重新开始。读者：场记的主干调度、选项的此后槽
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from ..world import body, situation

STAGES = ("起意", "入局", "受挫", "抉择", "了结")
HINTS = {"起意": "给主角一个够得着这件事的机会，让他看见门在哪里",
         "入局": "让这件事有进展，也要他付出点什么",
         "受挫": "让他为此失去或险些失去什么，逼出一个两难",
         "抉择": "让他在这件事与某个人或某条道义之间取舍",
         "了结": "此线已了：从主角此刻最深的关系或最急的时限里，提一条新的所求，写 {\"做\":\"所求\",\"为\":\"一句话\"}"}
WARD = "段誉"   # 「护世子周全」所护之人


def _kind(goal: str) -> str:
    if "武" in goal:
        return "art"
    if "名" in goal:
        return "fame"
    if "护" in goal or "世子" in goal:
        return "ward"
    return "other"


def _fame(world) -> int:
    name = world.player["name"]
    return sum(1 for e in world.truth.events if e.get("origin") == "director" and name in (e.get("summary") or ""))


def _reached(world, kind: str, arc: dict) -> int:
    """按事实看主角线至少到了哪一阶(下标)。"""
    g, me = world.graph, world.player
    study = me["study"] or {}
    if kind == "art":
        books = [i for i in me["inventory"] if g.get(i, "grants")]
        if any(r["stage"] >= 2 for r in study.values()):
            return 4
        if (study or books) and (body.severity(world) or any(i not in me["inventory"] and g.kind(i) == "item" for i in study)):
            return 2
        return 1 if study or books or me["skills"] else 0
    if kind == "fame":
        n = _fame(world)
        if n >= 3:
            return 4
        if n and (situation.captors(world, "player") or me["hp"] <= me["max_hp"] // 2):
            return 2
        return 1 if n else 0
    if kind == "ward":
        if situation.captors(world, WARD) or g.get(WARD, "status") == "dead":
            return 2
        if world.here == "镇南王府" and g.get(WARD, "location") == "镇南王府" and arc["stage"] >= 1:
            return 4
        return 1 if WARD in situation.party(world) else 0
    return 1 if me["turn"] - arc["since"] >= 3 else 0


def track(world) -> str | None:
    """推进主角线：goal 变了即重开；阶段只进不退，受挫之后一回合即到抉择(由场记提示导演安排)。返回本回合跨入的阶段。"""
    me = world.player
    arc = me["arc"]
    if not arc or arc.get("goal") != me["goal"]:
        arc = {"goal": me["goal"], "stage": 0, "since": me["turn"]}
    stage = max(arc["stage"], _reached(world, _kind(me["goal"] or ""), arc))
    if arc["stage"] == 2 and stage == 2 and me["turn"] > arc["since"]:
        stage = 3
    moved = STAGES[stage] if stage != arc["stage"] else None
    me.set("arc", {**arc, "stage": stage, "since": me["turn"] if moved else arc["since"]})
    return moved


def line(world) -> str:
    arc = world.player["arc"]
    if not arc or not arc.get("goal"):
        return ""
    stage = STAGES[arc["stage"]]
    return f"主角线：{arc['goal']}（{stage}）——{HINTS[stage]}"
