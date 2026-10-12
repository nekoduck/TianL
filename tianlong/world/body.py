"""
[INPUT]: 依赖 world/situation 的 around（身边之人）、world/actor 的 vitals / mend / conditions / set_conditions（任何人的身体），World 门面的 graph / player / clock / seed / turn（鸭子类型）
[OUTPUT]: 对外提供 fate()（本回合的命运骰）、INJURIES / severity() / injure() / relieve() / recover()（内伤分层与病程）、
          risk() / forecast()（研习预裁）、wound()（伤势措辞）、INNER（拍文与境况里说的内伤）
[POS]: world 层的身体规则——与 growth（进境与功力）互为表里：growth 算「学到多少」，body 算「学得顺不顺、伤得多重、好得多快」。
       研习预裁与较量预裁同构：命运骰 + 懂行之人 + 伤势 → 顺利 / 小有所得 / 受阻 / 岔气，导演只演出、不得自编反噬；
       内伤是境况里的一个分级词（内息紊乱 → 经脉受损 → 经脉重创），只由规则升降：强练岔气至多一回合升一级，歇息与疗伤降级。
       伤势措辞以气血与内伤共同定：重伤只给气血三成以下或经脉受损以上——不再一掉血就重伤。
       主角与 NPC 同构(v4)：内伤升降、伤势措辞、歇息养伤对任何人成立(who 缺省为主角)，一回合各人至多升降一级；光阴流过，天下负伤之人一同将养
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import random
import re

from . import actor, situation

# ============================================================
#  命运骰：本回合一次，较量预裁与研习预裁共用；同一世界同一时刻掷出同一点，试演与定稿结果一致
# ============================================================
def fate(world) -> int:
    return random.Random(f"{world.seed}:{world.clock.tick}").randint(1, 100)


# ============================================================
#  内伤：境况里的分级词，规则升降
# ============================================================
INJURIES = ("内息紊乱", "经脉受损", "经脉重创")
INNER = re.compile(r"内伤|岔气|走火|经脉|内息|真气(?:乱|逆|岔)|气血翻涌")
REST = 240                                   # 歇满两个时辰(分钟)才算养伤
MEND = 0.15                                  # 每歇两个时辰回复气血上限的一成半；经脉受损以上减半


def severity(world, who: str = "player") -> int:
    return max((INJURIES.index(c) + 1 for c in actor.conditions(world, who) if c in INJURIES), default=0)


def _set(world, level: int, who: str = "player"):
    actor.set_conditions(world, who, [c for c in actor.conditions(world, who) if c not in INJURIES and not INNER.search(c)]
                         + ([INJURIES[level - 1]] if level else []))


def _once(world, flag: str, who: str) -> bool:
    """一回合里每人每种升降至多一次：第一次返回真并记下。"""
    done = world.turn.setdefault(flag, set())
    if who in done:
        return False
    done.add(who)
    return True


def _you(world, who: str) -> str:
    return "你" if who == "player" else who


def injure(world, why: str = "", who: str = "player") -> str:
    """内伤加重一级；一回合至多一级——强练再狠、挨得再重，也不会一下从安然到经脉重创。"""
    if not _once(world, "injured", who):
        return ""
    level = min(severity(world, who) + 1, len(INJURIES))
    _set(world, level, who)
    return f"{why}，{_you(world, who)}{INJURIES[level - 1]}" if why else f"{_you(world, who)}{INJURIES[level - 1]}"


def relieve(world, why: str = "", who: str = "player") -> str:
    """内伤减轻一级（服药、有人运功疗伤、歇息）；一回合至多一级。"""
    level = severity(world, who)
    if not level or not _once(world, "relieved", who):
        return ""
    _set(world, level - 1, who)
    head = "" if who == "player" else who
    return (f"{why}，" if why else "") + head + (f"内伤减轻为{INJURIES[level - 2]}" if level > 1 else "内息已然平复")


def recover(world, minutes: int) -> str:
    """光阴里的自然恢复：歇满两个时辰才算——气血按两个时辰计回复，内伤降一级(本回合强练岔气则不降)。
    主角之外，天下负过伤的人(图上已有气血账的)一同将养；返回的说明只讲主角与身边之人。"""
    spans = minutes // REST
    if spans <= 0:
        return ""
    near, told = situation.around(world), []
    hurt = ["player"] + [p for p, n in world.graph.nodes.items() if n.get("type") == "person" and "hp" in n
                         and n.get("status") != "dead" and (n["hp"] < n["max_hp"] or severity(world, p))]
    for who in hurt:
        hp, cap = actor.vitals(world, who)
        said = []
        if hp < cap:
            rate = MEND / (2 if severity(world, who) >= 2 else 1)
            actor.mend(world, who, max(1, round(cap * rate * spans)))
            said.append("气血渐复" if who == "player" else f"{who}伤势渐复")
        if who not in world.turn.get("injured", ()):
            said.append(relieve(world, who=who))
        if who == "player" or who in near:
            told += [t for t in said if t]
    return "；".join(told)


# 气血不报数字，只报身况：(气血比例下限, 措辞, 语气)；语气 plain/warn/alert 交由表现层决定着色
WOUNDS = ((0.8, "安然无恙", "plain"), (0.3, "轻伤", "warn"), (0.12, "重伤", "warn"), (0.0, "命悬一线", "alert"))


def wound(world, who: str = "player") -> tuple[str, str]:
    """伤势措辞与语气：气血比例给底，内伤只往重里抬——经脉受损以上才是重伤。"""
    if who != "player" and world.graph.get(who, "status") == "dead":
        return "已故", "alert"
    hp, cap = actor.vitals(world, who)
    ratio, level = hp / cap, severity(world, who)
    text, tone = next((t, tone) for floor, t, tone in WOUNDS if ratio >= floor)
    if level >= 2 and text in ("安然无恙", "轻伤"):
        return "重伤", "warn"
    if level == 1 and text == "安然无恙":
        return "轻伤", "warn"
    return text, tone


# ============================================================
#  研习预裁：命运骰 + 懂行之人 + 伤势 → 档位；倍率作用于这次研习计入的时长
# ============================================================
RISK = {"北冥神功": "低", "凌波微步": "低"}   # 段誉照图自学并无反噬：逍遥派这两门初学无凶险
RISKY_TYPES = {"内功": "中"}                    # 其余内功强练有岔气之虞；招式身法初学无碍
VERSED = re.compile(r"易经|易理|卦")             # 武学里有卦位，懂易理的人便能指点
MENTOR, KNOWING, HURT, FEEBLE = 30, 15, 15, 20   # 会这门的人指点 / 懂相关学问 / 每级内伤 / 气血不足一半
# (分数下限, 档位, 时长倍率)
TIERS = ((75, "顺利", 1.5), (40, "小有所得", 1.0), (0, "受阻", 0.5))


def risk(world, skill: str) -> str:
    g = world.graph
    return RISK.get(skill) or RISKY_TYPES.get(g.get(skill, "type"), "低")


def _arts(world, source: str) -> list[str]:
    g = world.graph
    if g.kind(source) == "skill":
        return [source]
    grants = g.get(source, "grants") or {}
    return [s for s in [grants.get("skill")] + [x.get("skill") for x in g.get(source, "grants_extra") or []] if s]


def forecast(world, source: str) -> dict:
    """主角此刻研习 source 的结局：{tier, factor, strain, why}。strain 为真即岔气——只在骰值极低且武学有凶险或带伤强练时出现。"""
    g, me = world.graph, world.player
    arts, roll = _arts(world, source), fate(world)
    score, why, factor = roll, [], 1.0
    people = situation.around(world)
    mentor = next((p for p in sorted(people) if set(arts) & set(g.get(p, "skills") or [])), None)
    if mentor:
        score += MENTOR
        why.append(f"{mentor}会这门功夫，从旁指点")
    elif any(VERSED.search(f"{g.get(a, 'desc') or ''}{g.get(a, 'requires') or ''}") for a in arts):
        sage = next((p for p in sorted(people) if VERSED.search(f"{g.get(p, 'persona') or ''}{g.get(p, 'title') or ''}")), None)
        if sage:
            score += KNOWING
            factor = 2.0
            why.append(f"{sage}通晓易理，替你解开卦位")
    level, weak = severity(world), me["hp"] < me["max_hp"] / 2
    if level or weak:
        score -= level * HURT + (FEEBLE if weak else 0)
        why.append("带伤强练")
    perilous = any(risk(world, a) != "低" for a in arts) or level or weak
    if roll <= 8 and perilous:
        return {"tier": "岔气", "factor": 0.5, "strain": True, "why": "；".join(why + ["真气走岔"])}
    tier, mult = next((t, m) for floor, t, m in TIERS if score >= floor)
    return {"tier": tier, "factor": mult * factor, "strain": False, "why": "；".join(why)}
