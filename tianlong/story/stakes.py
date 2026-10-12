"""
[INPUT]: 依赖 world/clock 的 PACES / PER_DAY / PER_SHICHEN（措辞换算），World 门面的 clock / player（鸭子类型）
[OUTPUT]: 对外提供 plant()（导演立下一个时限）、due()（到期的时限：交场记一次即除）、due_at()（某个时限的到期时刻，供 cut.until）、
          urgent()（最急的一个及其余时措辞）、left()（余时措辞）、CAP
[POS]: story 层的时限账——时间是后果的另一半：有了「钟万仇夫妇明日启程」「云中鹤的耐心只到天明」，选半日就有代价，片刻不再是默认的安全答案。
       时限存在黑板 clocks(至多 CAP 个)：{id, what, due, turn}；导演在顶层 clock 里立，到期那一回合交场记作主干、随即除去；
       场记、选项编排(赶在…之前)、幕间省略(until 某个时限)都读它
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

from ..world.clock import PACES, PER_DAY, PER_SHICHEN

CAP = 3
SPAN = re.compile(r"(\d+|[一二两三四五六七八九十])\s*(日|天|个?时辰)")
NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _minutes(world, span) -> int | None:
    if isinstance(span, (int, float)) and span > 0:
        return int(span) * PER_DAY
    if not isinstance(span, str):
        return None
    span = span.strip()
    if span in PACES:
        return world.clock.minutes(span)
    m = SPAN.search(span)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1)]
    return n * (PER_DAY if m.group(2) in ("日", "天") else PER_SHICHEN)


def plant(world, spec) -> str | None:
    """立一个时限：{what: 一句话, in: 「一日」「三个时辰」「半日」}。同一件事不重复立；满额挤掉最晚到期的。返回 id。"""
    if not isinstance(spec, dict) or not str(spec.get("what") or "").strip():
        return None
    gap = _minutes(world, spec.get("in"))
    if not gap:
        return None
    me, what = world.player, str(spec["what"]).strip()[:30]
    clocks = [c for c in me["clocks"] if c["what"] != what]
    cid = f"c{me['turn']}-{len(clocks)}"
    clocks.append({"id": cid, "what": what, "due": world.clock.tick + gap, "turn": me["turn"]})
    me.set("clocks", sorted(clocks, key=lambda c: c["due"])[:CAP])
    return cid


def due(world) -> list[dict]:
    """到期的时限：返回并从账上除去——到期那一回合交场记作主干，交代一次即了。"""
    me, now = world.player, world.clock.tick
    gone = [c for c in me["clocks"] if c["due"] <= now]
    me.set("clocks", [c for c in me["clocks"] if c["due"] > now])
    return gone


def due_at(world, key: str) -> int | None:
    """某个时限的到期时刻：认 id，也认 what 里的说法。"""
    return next((c["due"] for c in world.player["clocks"] if key in (c["id"], c["what"]) or key in c["what"]), None)


def left(world, c: dict) -> str:
    gap = c["due"] - world.clock.tick
    if gap >= PER_DAY:
        return f"余{gap // PER_DAY}日" + ("有余" if gap % PER_DAY >= PER_SHICHEN * 3 else "")
    if gap >= PER_SHICHEN:
        return f"余{gap // PER_SHICHEN}个时辰"
    return "迫在眉睫"


def urgent(world) -> tuple[dict, str] | None:
    clocks = world.player["clocks"]
    return (clocks[0], left(world, clocks[0])) if clocks else None
