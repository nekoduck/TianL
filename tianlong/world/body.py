"""
[INPUT]: 依赖 world/situation 的 around（身边之人），World 门面的 graph / player / clock / seed / turn（鸭子类型）
[OUTPUT]: 对外提供 fate()（本回合的命运骰）、INJURIES / severity() / injure() / relieve() / recover()（内伤分层与病程）、
          risk() / forecast()（研习预裁）、wound()（伤势措辞）、INNER（拍文与境况里说的内伤）
[POS]: world 层的身体规则——与 growth（进境与功力）互为表里：growth 算「学到多少」，body 算「学得顺不顺、伤得多重、好得多快」。
       研习预裁与较量预裁同构：命运骰 + 懂行之人 + 伤势 → 顺利 / 小有所得 / 受阻 / 岔气，导演只演出、不得自编反噬；
       内伤是境况里的一个分级词（内息紊乱 → 经脉受损 → 经脉重创），只由规则升降：强练岔气至多一回合升一级，歇息与疗伤降级。
       伤势措辞以气血与内伤共同定：重伤只给气血三成以下或经脉受损以上——不再一掉血就重伤
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import random
import re

from . import situation

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
REST = 240                                   # 歇满半日(分钟)才算养伤
MEND = 0.15                                  # 每歇半日回复气血上限的一成半；经脉受损以上减半


def severity(world) -> int:
    return max((INJURIES.index(c) + 1 for c in world.player["conditions"] if c in INJURIES), default=0)


def _set(world, level: int):
    me = world.player
    me.set("conditions", [c for c in me["conditions"] if c not in INJURIES and not INNER.search(c)]
           + ([INJURIES[level - 1]] if level else []))


def injure(world, why: str = "") -> str:
    """内伤加重一级；一回合至多一级——强练再狠，也不会一下从安然到经脉重创。"""
    turn = world.turn
    if turn.get("injured"):
        return ""
    turn["injured"] = True
    level = min(severity(world) + 1, len(INJURIES))
    _set(world, level)
    return f"{why}，你{INJURIES[level - 1]}" if why else f"你{INJURIES[level - 1]}"


def relieve(world, why: str = "") -> str:
    """内伤减轻一级（服药、有人运功疗伤、歇息）；一回合至多一级。"""
    turn, level = world.turn, severity(world)
    if not level or turn.get("relieved"):
        return ""
    turn["relieved"] = True
    _set(world, level - 1)
    return (f"{why}，" if why else "") + (f"内伤减轻为{INJURIES[level - 2]}" if level > 1 else "内息已然平复")


def recover(world, minutes: int) -> str:
    """光阴里的自然恢复：歇满半日才算——气血按半日计回复，内伤降一级(本回合强练岔气则不降)。"""
    me, spans = world.player, minutes // REST
    if spans <= 0:
        return ""
    told = []
    if me["hp"] < me["max_hp"]:
        rate = MEND / (2 if severity(world) >= 2 else 1)
        me.add("hp", max(1, round(me["max_hp"] * rate * spans)))
        told.append("气血渐复")
    if not world.turn.get("injured"):
        told.append(relieve(world))
    return "；".join(t for t in told if t)


# 气血不报数字，只报身况：(气血比例下限, 措辞, 语气)；语气 plain/warn/alert 交由表现层决定着色
WOUNDS = ((0.8, "安然无恙", "plain"), (0.3, "轻伤", "warn"), (0.12, "重伤", "warn"), (0.0, "命悬一线", "alert"))


def wound(world) -> tuple[str, str]:
    """伤势措辞与语气：气血比例给底，内伤只往重里抬——经脉受损以上才是重伤。"""
    me = world.player
    ratio, level = me["hp"] / me["max_hp"], severity(world)
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
