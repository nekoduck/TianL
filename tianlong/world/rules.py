"""
[INPUT]: 依赖 world/world 的 World 门面（graph / player / clock / seed / here），依赖 random.Random 做种子化判定
[OUTPUT]: 对外提供 scene()、legal_actions()、resolve()、COST
[POS]: world 层的确定性规则引擎——把玩家意图裁决为「事实 + 变更指令 + 时间成本 + 公开事件」；
       胜负、得失、生死只在这里决定，LLM 只能从 legal_actions 中挑选，无权裁决
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import math
import random

COST = {"look": 0, "talk": 1, "examine": 1, "take": 1, "fight": 2, "rest": 6, "study": 24, "emote": 1}  # 单位：时辰
FREE_VERBS = {"look", "emote"}  # 永远合法、不改变世界的动作


def _act(verb, target, label):
    return {"verb": verb, "target": target, "label": label}


def _out(facts, effects=(), cost=0, event=None):
    return {"facts": list(facts), "effects": list(effects), "cost": cost, "event": event}


def scene(world) -> dict:
    """玩家此刻能亲眼看见的一切（真相，排除隐秘节点）。"""
    g = world.graph

    def at(kind):
        return [n for n in g.where(type=kind, location=world.here) if not g.get(n, "hidden")]

    people = at("person")
    return {"people": [p for p in people if g.get(p, "status") != "dead"],
            "dead": [p for p in people if g.get(p, "status") == "dead"],
            "features": at("feature"), "items": at("item")}


def legal_actions(world) -> list[dict]:
    g, me, s = world.graph, world.player, scene(world)
    acts = [_act("go", loc, f"前往{loc}（{days}日路程）") for loc, days in g.roads(world.here)]
    for p in s["people"]:
        acts += [_act("talk", p, f"与{p}交谈"), _act("fight", p, f"向{p}出手")]
    acts += [_act("examine", f, f"察看{f}") for f in s["features"]]
    acts += [_act("take", i, f"拾取{i}") for i in s["items"]]
    acts += [_act("study", i, f"研习{i}") for i in me["inventory"]
             if g.get(i, "grants") and g.get(i, "grants")["skill"] not in me["skills"]]
    acts.append(_act("rest", None, "歇息调息"))
    return acts


# ============================================================
#  动作裁决
# ============================================================
def _look(world, _):
    return _out([f"你身在{world.here}。"])


def _emote(world, _):
    return _out([], cost=COST["emote"])


def _go(world, dest):
    days = dict(world.graph.roads(world.here))[dest]
    return _out([f"你自{world.here}动身，跋涉{days}日，抵达{dest}。"],
                [{"op": "set", "id": "player", "key": "location", "value": dest},
                 {"op": "set", "id": "player", "key": "posture", "value": "风尘仆仆"}],
                cost=days * 12)


def _talk(world, who):
    return _out([f"你与{who}攀谈。"],
                [{"op": "link", "src": "player", "dst": who, "rel": "相识"},
                 {"op": "set", "id": "player", "key": "posture", "value": "站立"}],
                cost=COST["talk"])


def _examine(world, feat):
    g, item = world.graph, world.graph.get(feat, "reveals")
    if item and g.get(item, "location") is None and item not in world.player["inventory"]:
        return _out([f"你仔细察看{feat}，发现其中藏着{item}！"],
                    [{"op": "set", "id": item, "key": "location", "value": world.here},
                     {"op": "set", "id": feat, "key": "reveals", "value": None}],
                    cost=COST["examine"])
    return _out([f"你仔细察看{feat}。"], cost=COST["examine"])


def _take(world, item):
    return _out([f"你拾起了{item}。"],
                [{"op": "set", "id": item, "key": "location", "value": None},
                 {"op": "push", "id": "player", "key": "inventory", "value": item}],
                cost=COST["take"])


def _study(world, item):
    grants = world.graph.get(item, "grants")
    return _out([f"你闭门研习{item}两日，习得{grants['skill']}，功力大进。"],
                [{"op": "push", "id": "player", "key": "skills", "value": grants["skill"]},
                 {"op": "add", "id": "player", "key": "power", "value": grants["power"]},
                 {"op": "set", "id": "player", "key": "posture", "value": "打坐"}],
                cost=COST["study"])


def _rest(world, _):
    return _out(["你盘膝调息，气血渐复。"],
                [{"op": "add", "id": "player", "key": "hp", "value": 40},
                 {"op": "set", "id": "player", "key": "posture", "value": "打坐"}],
                cost=COST["rest"])


def _fight(world, foe):
    g, me = world.graph, world.player
    mine, theirs = me["power"], g.get(foe, "power", 30)
    rng = random.Random(f"{world.seed}:{world.clock.tick}:{foe}")  # 同一时刻同一对手，结果可复现
    hostile = [{"op": "link", "src": foe, "dst": "player", "rel": "仇"}]
    if rng.random() < 1 / (1 + math.exp((theirs - mine) / 12)):
        killed = g.get(foe, "status") == "wounded"
        verb = "击毙" if killed else "击伤"
        faction = g.get(foe, "faction")
        effects = [{"op": "set", "id": foe, "key": "status", "value": "dead" if killed else "wounded"},
                   {"op": "set", "id": "player", "key": "posture", "value": "戒备"}] + hostile
        if faction:
            effects.append({"op": "link", "src": faction, "dst": "player", "rel": "仇"})
        return _out([f"你与{foe}交手，将其{verb}。"], effects, COST["fight"],
                    {"summary": f"{me['name']}在{world.here}{verb}{foe}", "weight": 2 if killed else 1})
    effects = [{"op": "add", "id": "player", "key": "hp", "value": -max(10, theirs - mine)},
               {"op": "set", "id": "player", "key": "posture", "value": "负伤"}] + hostile
    return _out([f"你与{foe}交手，不敌，身受内伤。"], effects, COST["fight"],
                {"summary": f"{me['name']}在{world.here}向{foe}挑衅，反被打伤", "weight": 1})


HANDLERS = {"look": _look, "emote": _emote, "go": _go, "talk": _talk, "examine": _examine,
            "take": _take, "study": _study, "rest": _rest, "fight": _fight}


def resolve(world, intent: dict) -> dict:
    verb, target = intent.get("verb"), intent.get("target")
    legal = verb in FREE_VERBS or any(a["verb"] == verb and a["target"] == target for a in legal_actions(world))
    if not legal:
        return _out([f"你想做的事（{verb} {target or ''}）此刻无从下手。"])
    return HANDLERS[verb](world, target)
