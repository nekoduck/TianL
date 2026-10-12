"""
[INPUT]: 依赖 world/situation 的 FOLLOW / CUSTODY / around（结构性关系与身边之人）、world/actor 的 vitals（伤人之前的气血），World 门面的 graph / player（鸭子类型）
[OUTPUT]: 对外提供 event()（记一件与主角有关的互动事件）、before() / derive()（从一拍已成立的指令里推出互动事件）、attitude()（导演写的态度 link 化作事件）、
          stance()（折叠出此人此刻对主角的立场与最近缘由）、structural()、migrate()（旧档的态度边折成事件）、STRUCTURAL、LOG
[POS]: world 层的关系账——「事件先于状态」(宪法第 15 条)的第一处落地：LLM 宣告发生了什么，系统推导这意味着什么。
       某人对主角的看法不再是一条可覆盖的边(写新即覆盖旧，再以五回合阻尼冻住)，而是恩与怨两本账：
       施救、赠予、相助、同行、求教记恩；伤人、夺物、擒拿、吸功、杀其亲故记怨；导演在拍上写的态度 link 按措辞轻重记一笔，note 即缘由。
       两本账按回合衰减(怨比恩消得慢)，读时折叠成立场措辞(托付/信任/友善/相识/戒备/嫌恶/仇视，恩怨都深则「感激中带着戒备」)——
       一两件小事改不动立场，救命之恩、杀亲之仇直接跨级；不再需要阻尼，也不再冻结。
       结构性关系(随行、拘押、师徒、结义……)与暗中的心思(secret)仍是图上的边，归 situation 与 perspective
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

from . import actor, situation

STRUCTURAL = {situation.FOLLOW, *situation.CUSTODY, "结义", "结拜", "师父", "徒弟", "师徒", "夫妻", "主仆", "同门", "效忠", "护卫"}
FAVOR_DECAY, GRUDGE_DECAY = 0.97, 0.985   # 每回合留下的比例：恩易淡，怨难消
LOG = 4                                     # 每人只记最近几件事
WHY_LEN = 24
# (恩减怨的下限, 立场)：自上而下取第一个
LEVELS = ((8, "托付"), (4, "信任"), (1.5, "友善"), (-1.5, "相识"), (-4, "戒备"), (-8, "嫌恶"), (float("-inf"), "仇视"))
MIXED = 2.5                                 # 恩怨都过此数：两样心思并存
# 态度措辞的轻重：强 ±3、弱 ±1.5、相识 +0.5
STRONG_BAD = re.compile(r"仇|恨|杀|敌|怒不可遏|切齿|誓报")
MILD_BAD = re.compile(r"疑|忌|戒|厌|恼|轻视|鄙|不满|提防|不悦|冷淡|怀疑|嫌|怒|恶")
STRONG_GOOD = re.compile(r"恩|感激|救命|敬重|敬服|信任|托付|倾慕|爱|钦佩|折服|生死|知交|知己")
MILD_GOOD = re.compile(r"好感|欣赏|关切|亲近|友|赏识|佩服|感谢|谢|好奇|投缘|留意|看重|喜|结交|投契")
ACQUAINT = re.compile(r"相识|结识|认得|认识|初识")
THANKS = re.compile(r"多谢|谢过|谢谢|感激|恩公|大恩")      # NPC 对主角说的话里：道谢
SCORN = re.compile(r"住口|放肆|大胆|找死|滚|无耻|狂妄|小贼|好大的胆")  # NPC 对主角说的话里：呵斥


def structural(rel: str) -> bool:
    return rel in STRUCTURAL


def _ledger(world, who: str) -> dict | None:
    node = world.graph.nodes.get(who)
    if not node or node.get("type") != "person":
        return None
    return node.setdefault("bond", {"favor": 0.0, "grudge": 0.0, "turn": world.player["turn"], "log": []})


def _decayed(b: dict, now: int) -> tuple[float, float]:
    gap = max(0, now - b.get("turn", now))
    return b["favor"] * FAVOR_DECAY ** gap, b["grudge"] * GRUDGE_DECAY ** gap


def event(world, who: str, weight: float, why: str):
    """记一件与主角有关的事：正为恩、负为怨。先把旧账按回合衰减到今天，再记这一笔。"""
    b = _ledger(world, who)
    if b is None or not weight:
        return
    now = world.player["turn"]
    favor, grudge = _decayed(b, now)
    if weight > 0:
        favor += weight
    else:
        grudge -= weight
    log = b["log"] + [{"turn": now, "w": round(weight, 1), "why": str(why)[:WHY_LEN]}]
    b.update(favor=round(favor, 2), grudge=round(grudge, 2), turn=now, log=log[-LOG:])


def weigh(text: str) -> float:
    """一句态度措辞的分量：先看强字眼，再看弱字眼；说不出好坏的「相识」只记一点。"""
    text = text or ""
    if STRONG_BAD.search(text):
        return -3
    if STRONG_GOOD.search(text):
        return 3
    if MILD_BAD.search(text):
        return -1.5
    if MILD_GOOD.search(text):
        return 1.5
    return 0.5 if ACQUAINT.search(text) else 0


def attitude(world, op: dict) -> bool:
    """导演写的「某人→主角」的非结构性关系(疑忌、感激、敬佩……)：不立边，记一笔事件，note 即缘由。返回是否已化作事件。"""
    if op.get("dst") != "player" or op.get("src") == "player" or structural(op.get("rel", "")) or op.get("secret"):
        return False
    rel, note = op.get("rel", ""), op.get("note") or ""
    event(world, op["src"], weigh(rel) or weigh(note) or 0.5, note or rel)
    return True


def stance(world, who: str) -> tuple[str, str] | None:
    """此人此刻对主角的立场与最近一次分量够重的缘由；没有往来即 None。"""
    b = world.graph.nodes.get(who, {}).get("bond")
    if not b:
        return None
    favor, grudge = _decayed(b, world.player["turn"])
    net = favor - grudge
    word = next(w for floor, w in LEVELS if net >= floor)
    if favor >= MIXED and grudge >= MIXED:
        word = ("感激中带着戒备" if net >= 0 else "怨中带着几分感念")
    weighty = [x for x in b["log"] if abs(x["w"]) >= 1.5] or b["log"]
    return word, (weighty[-1]["why"] if weighty else "")


# ============================================================
#  从一拍已成立的指令里推出互动事件：恩怨看的是做了什么，不是说了什么
# ============================================================
def before(world, ops: list) -> dict:
    """落账前的快照：指令碰到的器物在谁手里、在场之人的气血——事后才分得清是赠是夺、伤了谁。"""
    g = world.graph
    holders, hp = {}, {}
    for op in ops:
        if not isinstance(op, dict):
            continue
        for v in (op.get("id"), op.get("value")):
            if isinstance(v, str) and g.kind(v) == "item":
                holders[v] = g.get(v, "holder")
    for p in situation.around(world):
        hp[p] = actor.vitals(world, p)[0]
    edges = {(e["src"], e["dst"], e["rel"]) for e in g.edges if "player" in (e["src"], e["dst"])}
    return {"holders": holders, "hp": hp, "edges": edges,
            "dead": {p for p in situation.around(world) if g.get(p, "status") == "dead"}}


def derive(world, who, applied: list, snap: dict, text: str = "", to=None):
    """一拍落账之后：主角的拍里救人、赠物、夺物、伤人、擒人、吸功、杀人，NPC 的拍里随行与对主角说的话——各记一笔。"""
    g = world.graph
    mine = who in (None, "player")
    for op in applied:
        kind, key, v = op.get("op"), op.get("key"), op.get("value")
        if kind == "link" and (op.get("src"), op.get("dst"), op.get("rel")) in snap["edges"]:
            continue  # 重写一条已有的关系不是又一件事：擒住一回，记一回
        if kind == "link" and op.get("rel") == situation.FOLLOW and op.get("dst") == "player":
            event(world, op["src"], 1, "与你同行")
        if not mine:
            continue
        if kind == "unlink" and op.get("rel") in situation.CUSTODY and op.get("dst") != "player":
            event(world, op["dst"], 3, "你救了他")
        elif kind == "link" and op.get("rel") in situation.CUSTODY and op.get("src") == "player":
            event(world, op["dst"], -4, "被你擒住")
        elif kind == "set" and key == "holder" and g.kind(op.get("id")) == "item" and g.kind(v) == "person" \
                and snap["holders"].get(op["id"]) == "player":
            event(world, v, 2, f"你赠他{op['id']}")
        elif kind == "push" and op.get("id") == "player" and key == "inventory" and g.kind(snap["holders"].get(v)) == "person":
            event(world, snap["holders"][v], -3, f"你夺了他的{v}")
        elif kind == "drain":
            event(world, v, -4, "你吸了他的内力")
        elif kind == "study" and g.kind(v) == "skill":
            teacher = next((p for p in sorted(situation.around(world)) if v in (g.get(p, "skills") or [])), None)
            if teacher:
                event(world, teacher, 1, f"向他求教{v}")
    if mine:
        for p, hp in snap["hp"].items():
            if g.get(p, "status") == "dead" and p not in snap["dead"]:
                for kin in _kin(world, p):
                    event(world, kin, -5, f"你杀了{p}")
            elif g.kind(p) == "person" and "hp" in g.nodes[p] and g.nodes[p]["hp"] < hp:
                event(world, p, -3, "你伤了他")
    elif isinstance(who, str) and to == "player":
        if THANKS.search(text):
            event(world, who, 1, "向你道谢")
        elif SCORN.search(text):
            event(world, who, -1, "对你出言呵斥")


def _kin(world, dead: str) -> list[str]:
    """死者在场的亲故：与他有明面关系的活人。"""
    g, near = world.graph, situation.around(world)
    out = set()
    for e in g.relations(dead):
        other = e["dst"] if e["src"] == dead else e["src"]
        if other in near and other != "player" and not e.get("secret") and g.get(other, "status") != "dead":
            out.add(other)
    return sorted(out)


def migrate(world):
    """旧档里「某人→主角」的态度边折成事件：边上的 note 是缘由，回合是记下之时。"""
    g, keep = world.graph, []
    for e in g.edges:
        if e.get("dst") == "player" and e.get("src") != "player" and not structural(e["rel"]) and not e.get("secret") \
                and g.kind(e["src"]) == "person":
            event(world, e["src"], weigh(e["rel"]) or weigh(e.get("note") or "") or 0.5, e.get("note") or e["rel"])
            continue
        keep.append(e)
    g.edges = keep
