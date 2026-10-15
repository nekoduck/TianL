"""
[INPUT]: 依赖 world/clock 的 PACES / PER_DAY / PER_SHICHEN（措辞换算）、world/effects 的 apply / RULED_BY / place / describe（规则自己落账）、world/acts 的 normalize / describe（后果的事码）、
         world/situation 的 party（主角身边的同行者动不得）、world/access 的 reach（前往要走得通），World 门面的 clock / player / graph / record（鸭子类型）
[OUTPUT]: 对外提供 plant()（导演立下一个时限，可带后果 then）、due()（到期的带后果的时限：交场记一次即除）、enforce()（到期的后果由规则执行）、consequence()（后果的人话）、
          due_at()（某个时限的到期时刻，供 cut.until）、urgent()（最急的一个及其余时措辞）、left()（余时措辞）、CAP / SOFT_CAP / THEN
[POS]: story 层的时限账——时间是后果的另一半：有了「钟万仇夫妇明日启程」「云中鹤的耐心只到天明」，选半日就有代价，片刻不再是默认的安全答案。
       时限存在黑板 clocks：{id, what, due, turn, then}；导演在顶层 clock 里立，到期那一回合交场记作主干、随即除去。
       v13 时限带后果：「死亡倒计时不具约束力」——立下的期限到了只是场记一句话，导演回回交代成「添岔气、同回合消」，司空玄「七日不见解药即杀钟灵」从没进过任何账。
       写了 then（事码：杀死、打晕、伤人、前往、结下、了断、境况、打算……，须写明谁做）的时限是承诺，到期由规则在回合开头执行（enforce）：前提照验——做的人与受的人都在世、
       动手的两人同处、前往要走得通、不碰主角与他的同行者；来源是 RULED_BY（与药力、僵持押走同一条通道，这一回合已被别处调遣的人不动）；成了的记进江湖账本随传闻抵达，
       结果写给场记作主干、写给身边的编剧作连带；不成的写明缘由交导演由剧情圆回。没写 then 的只是伏笔：不占 CAP、不写「赌注」、到期悄悄作罢（不再回回「时限已到」）。
       同一件事重立只能提前、不能延后（第 10→11→12 回同一件事三次重立，等于每回合把期限往后推）；「八个半时辰」「三日半」读得出
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

from ..world import access, acts, effects, situation
from ..world.clock import PACES, PER_DAY, PER_SHICHEN

CAP = 3            # 带后果的时限至多几个
SOFT_CAP = 2       # 只是伏笔的时限至多几个（不占 CAP）
WHAT = 40          # 时限的说法至多几字
THEN = {"杀死", "打晕", "伤人", "疗伤", "前往", "结下", "了断", "境况", "打算", "神色", "现状"}  # 规则肯替导演兑现的后果：不拿东西、不改主角
VIOLENT = {"杀死", "打晕", "伤人", "结下", "了断"}   # 两个人之间的事，动手的与受的须同处
SPAN = re.compile(r"(\d+|[一二两三四五六七八九十]+)\s*(个)?(半)?\s*(日|天|时辰)(半)?")
NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _int(s: str) -> int:
    """「七」「十二」「二十」→ 整数。"""
    if s.isdigit():
        return int(s)
    if "十" in s:
        head, tail = s.split("十", 1)
        return NUM.get(head, 1) * 10 + NUM.get(tail, 0)
    return NUM.get(s, 0)


def _minutes(world, span) -> int | None:
    if isinstance(span, (int, float)) and span > 0:
        return int(span) * PER_DAY
    if not isinstance(span, str):
        return None
    span = span.strip()
    if span in PACES:
        return world.clock.minutes(span)
    m = SPAN.search(span)
    if not m or not _int(m.group(1)):
        return None
    n = _int(m.group(1)) + (0.5 if m.group(3) or m.group(5) else 0)  # 「八个半时辰」「三日半」
    return round(n * (PER_DAY if m.group(4) in ("日", "天") else PER_SHICHEN))


def _same(a: str, b: str) -> bool:
    """两个时限说的是不是同一件事：说法相同、一句含着另一句，或字面相近（两字组重合过半）。"""
    a, b = re.sub(r"\W", "", a), re.sub(r"\W", "", b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ga, gb = {a[i:i + 2] for i in range(len(a) - 1)}, {b[i:i + 2] for i in range(len(b) - 1)}
    return bool(ga and gb) and len(ga & gb) / len(ga | gb) >= 0.5


def _then(raw) -> list[dict]:
    """到期的后果：事码的清单（单条也收），只留规则肯兑现的几种动词，至多两条。"""
    items = [raw] if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    return [dict(op) for op in items if isinstance(op, dict) and acts.verb(op) in THEN][:2]


def plant(world, spec) -> str | None:
    """立一个时限：{what: 一句话, in: 「一日」「三个时辰」「八个半时辰」, then: 到期的后果(事码，可省)}。
    带后果的是承诺（至多 CAP 个，到期规则兑现），不带的只是伏笔（至多 SOFT_CAP 个）。同一件事重立只能提前、不能延后，后果以新写的为准。返回 id。"""
    if not isinstance(spec, dict) or not str(spec.get("what") or "").strip():
        return None
    gap = _minutes(world, spec.get("in"))
    if not gap:
        return None
    me, what = world.player, str(spec["what"]).strip()[:WHAT]
    due, then = world.clock.tick + gap, _then(spec.get("then"))
    old = next((c for c in me["clocks"] if _same(c["what"], what)), None)
    clocks = [c for c in me["clocks"] if c is not old]
    if old:
        due, then, cid = min(due, old["due"]), then or old.get("then") or [], old["id"]
    else:
        cid = f"c{me['turn']}-{len(clocks)}"
    clocks.append({"id": cid, "what": what, "due": due, "turn": me["turn"], "then": then})
    keep = sorted([c for c in clocks if c.get("then")], key=lambda c: c["due"])[:CAP] + \
        sorted([c for c in clocks if not c.get("then")], key=lambda c: c["due"])[:SOFT_CAP]
    me.set("clocks", sorted(keep, key=lambda c: c["due"]))
    return cid if any(c["id"] == cid for c in keep) else None


def due(world) -> list[dict]:
    """到期的时限：从账上除去；带后果的返回（交场记作主干、由 enforce 兑现），只是伏笔的悄悄作罢。"""
    me, now = world.player, world.clock.tick
    gone = [c for c in me["clocks"] if c["due"] <= now]
    me.set("clocks", [c for c in me["clocks"] if c["due"] > now])
    return [c for c in gone if c.get("then")]


def due_at(world, key: str) -> int | None:
    """某个时限的到期时刻：认 id，也认 what 里的说法（伏笔也认，幕间省略可以等到它）。"""
    return next((c["due"] for c in world.player["clocks"] if key in (c["id"], c["what"]) or key in c["what"]), None)


def left(world, c: dict) -> str:
    gap = c["due"] - world.clock.tick
    if gap >= PER_DAY:
        return f"余{gap // PER_DAY}日" + ("有余" if gap % PER_DAY >= PER_SHICHEN * 3 else "")
    if gap >= PER_SHICHEN:
        return f"余{gap // PER_SHICHEN}个时辰"
    return "迫在眉睫"


def urgent(world) -> tuple[dict, str] | None:
    """最急的一个承诺（只是伏笔的不算赌注）及其余时措辞。"""
    clocks = [c for c in world.player["clocks"] if c.get("then")]
    return (clocks[0], left(world, clocks[0])) if clocks else None


def consequence(world, c: dict) -> str:
    """一个时限到期的后果，说成人话：「司空玄杀死钟灵」。"""
    return "；".join(acts.describe(acts.normalize(world, op)) for op in c.get("then") or [])


# ============================================================
#  到期兑现
# ============================================================
def _alive(g, who) -> bool:
    return g.kind(who) in ("person", "group") and g.get(who, "status") != "dead" and not g.get(who, "disbanded")


def _viable(world, ops: list[dict]) -> tuple[list[dict], str | None]:
    """后果的前提：做的人都点了名且在世，动手的两人同处，前往走得通，不碰主角与他的同行者。返回 (规整过的事码, 不成的缘由)。"""
    g, barred = world.graph, {"player", *situation.party(world)}
    out = []
    for raw in ops:
        a = acts.normalize(world, raw)
        who, to, dest = a.get("谁"), a.get("对"), a.get("到")
        if not isinstance(raw.get("谁"), str):
            return [], "时限的后果没写明是谁做的"
        if who in barred or (isinstance(to, str) and to in barred):
            return [], "牵涉主角与他的同行者：主角身边的事归近处导演"
        if not _alive(g, who):
            return [], f"{who}已不在人世或不在当下的江湖"
        if isinstance(to, str) and a["做"] != "前往":
            if not _alive(g, to):
                return [], f"{to}已不在人世或不在当下的江湖"
            if a["做"] in VIOLENT and effects.place(world, who) != effects.place(world, to) \
                    and g.distances(effects.place(world, who)).get(effects.place(world, to), 1) != 0:
                return [], f"{who}与{to}不在一处，够不着"
        if a["做"] == "前往" and (g.kind(dest) != "location" or dest not in access.reach(world, effects.place(world, who))):
            return [], f"{who}去不了{dest}"
        out.append(a)
    return out, None


def enforce(world, gone: list[dict]) -> list[str]:
    """到期的带后果的时限，由规则在回合开头兑现：前提照验（_viable），来源 RULED_BY（这一回合已被别处调遣的人不动）。
    c["result"] 写明结果（交场记作主干）；成了的记进江湖账本（随传闻抵达），事发在主角眼前的写给编剧作连带。返回成了的人话。"""
    done = []
    for c in gone:
        ops, why = _viable(world, c.get("then") or [])
        if why:
            c["result"] = f"原定的后果没能成真：{why}"
            continue
        applied, rejected = effects.apply(world, ops, effects.RULED_BY)
        if rejected or not applied:
            c["result"] = "原定的后果没能成真：" + ("；".join(r for _, r in rejected) or "情势已变")
            continue
        told = "；".join(effects.describe(op) for op in applied)
        where = effects.place(world, ops[0].get("谁")) or world.here
        weight = 2 if any(op.get("key") == "status" and op.get("value") == "dead" for op in applied) else 1
        world.record(f"{c['what']}——期限已到：{told}", where, applied, "rule", weight, public=True, witnessed=where == world.here)
        c["result"] = f"规则已照预设落账：{told}"
        if where in situation.near(world):
            effects._note(world, f"时限已到，{told}")
        done.append(told)
    return done
