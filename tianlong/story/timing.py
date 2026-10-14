"""
[INPUT]: 依赖 world/growth 的 stage_of / SITTING / STAGES / TEACH_MINUTES（研习的规则时长）、world/body 的 REST（养伤半日）、
         world/situation 的 captors / imperiled（险境不许歇）、world/pacing 的 CUTS / UNTIL（幕间省略的措辞）、world/effects 的 resolve、world/acts 的 expand（v9 事码的研习也主张时长）；World 门面的 clock / player / graph
[OUTPUT]: 对外提供 claim()（规则主张的戏内光阴下限与缘由，只看真会成立的拍）、study_minutes()（研习一回的规则时长）、cut_minutes()（幕间省略换算成分钟：一段长度或「到某一刻」）、LATER（选了「此后」之举的下限）、REST_WORDS
[POS]: story 层的时间结算——「时间是后果」(宪法第 10 条 v4)：导演只选措辞(pace/cut)，戏内光阴取措辞与规则主张的较大者：
       研习一部秘籍主张到下一阶的合理时长(初窥半个时辰、此后每回两个时辰)，求教主张一个时辰，歇息养伤主张两个时辰——
       数目都来自 growth 与 body，措辞都来自 clock 的同一张表(v5)；只看真会成立的拍(作废之拍、未授意的研习不主张)；
       玩家上回合选的是「此后」尺度的一件事(赶路、等人、找人)，无规则可依时也至少一顿饭。
       幕间省略可以是一段长度(一顿饭/半日/一夜/一日)，也可以是「到某一刻」(入夜/天明/正午，或场记里列出的某个时限)——
       「等钟万仇夫妇明日启程」不必再猜是半日还是一日。导演写片刻而拍里在练功，系统按规则补足，不算违例
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

from ..world import acts, body, effects, growth, situation
from ..world.clock import PER_DAY, PER_SHICHEN
from ..world.pacing import CUTS, UNTIL

REST_WORDS = re.compile(r"歇息|休息|歇宿|养伤|疗伤|睡下|睡了|安歇|过夜|将养|运功疗|静养|歇一夜|歇上")  # 调息、打坐是练功的字眼，不是歇息
SHORT = re.compile(r"片刻|一会|稍|少顷|略|喘口气")       # 「歇息片刻」不是养伤
LATER = 45                                               # 选了「此后」之举(赶路、等人、找人)而无规则可依：至少一顿饭
STUDY_NEXT = 2 * PER_SHICHEN                             # 已入门的秘籍，每回研习主张两个时辰
HOURS = {name: i * PER_SHICHEN for name, i in (("入夜", 9), ("天明", 3), ("正午", 6))}  # 酉时入夜、卯时天明、午时
MAX_CUT = 2 * PER_DAY                                    # 幕间省略至多跳两日：再远就是赶路，归道路结算


def _beats(plan, drop=()):
    """真会成立的拍：定稿时整拍作废的不算(drop)——被作废的研习与歇息不主张时长。"""
    return [b for i, b in enumerate(plan.get("beats") or [], 1) if i not in drop]


def study_minutes(world, src: str) -> int:
    """研习一回的规则时长：求教一门武学 TEACH_MINUTES，秘籍初窥 STAGES[0]，此后每回 STUDY_NEXT——选项上写的耗时也读这里。"""
    if world.graph.kind(src) == "skill":
        return growth.TEACH_MINUTES
    return growth.STAGES[0][1] if growth.stage_of(world, src) == 0 else STUDY_NEXT


def claim(world, plan: dict, deed: str = "", scale: str | None = None, allowed=None, drop=()) -> tuple[int, list[str]]:
    """规则主张的戏内光阴下限 (分钟, 缘由)：研习、求教、养伤各报一个数，取最大；险境里的「歇息」不算。
    只看真会成立的：整拍作废的拍、玩家没授意的研习(allowed 之外，会被剥掉)不主张时长。"""
    g, floors, beats = world.graph, [], _beats(plan, drop)
    if allowed is not None:  # 与授意同一口径：指着某人即可向他求教，指着秘籍即指着它所载的武学
        allowed = set(allowed) | {k for p in allowed if g.kind(p) == "person" for k in g.get(p, "skills") or []} \
            | {k for x in allowed if g.kind(x) in ("item", "skill") for k in growth.arts_of(g, x)}
    for op in (op for b in beats for op in acts.expand(world, b.get("ops") or []) if isinstance(op, dict)):  # 事码(v9)先化为指令
        if op.get("op") != "study":
            continue
        src = effects.resolve(world, op.get("value"))
        if allowed is not None and src not in allowed and not set(growth.arts_of(g, src)) & set(allowed):
            continue
        if g.kind(src) in ("skill", "item"):
            floors.append((study_minutes(world, src), f"{'求教' if g.kind(src) == 'skill' else '研习'}{src}"))
    texts = [deed or ""] + [b.get("text") or "" for b in beats if b.get("who") in (None, "player")]
    safe = not situation.captors(world, "player") and not situation.imperiled(world)
    if safe and any(REST_WORDS.search(t) and not SHORT.search(t) for t in texts):
        floors.append((body.REST, "歇息养伤"))
    if scale == "此后":
        floors.append((LATER, "一件持续之事"))
    return max(floors, default=(0, ""))[0], [why for _, why in floors]


def cut_minutes(world, cut) -> int | None:
    """幕间省略 → 分钟：长度措辞照 clock 换算；「到某一刻」算到下一个那一刻(入夜/天明/正午，或 stakes 里的时限 id)。"""
    if isinstance(cut, str) and cut in CUTS:
        return world.clock.minutes(cut)
    target = cut.get("until") if isinstance(cut, dict) else cut
    if not isinstance(target, str):
        return None
    if target in HOURS:
        now = world.clock.tick % PER_DAY
        gap = (HOURS[target] - now) % PER_DAY
        return gap or PER_DAY
    from . import stakes  # 时限账：cut 可以等到某个时限到期
    due = stakes.due_at(world, target)
    if due is not None and due > world.clock.tick:
        return min(due - world.clock.tick, MAX_CUT)
    return None
