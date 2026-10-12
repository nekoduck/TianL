"""
[INPUT]: 依赖 world/body 的 forecast / injure（研习预裁与岔气），World 门面（graph / player / clock / turn，鸭子类型）
[OUTPUT]: 对外提供 study()（研习一部秘籍或向人求教一门武学：累计时长、分阶兑现武学与功力）、drain()（北冥吸功：双边结算）、
          stage_of()、progress()（后台用的研习进度一句话）、STAGES、DRAINERS、SITTING（研习一回至少一顿饭，引擎据此给本回合光阴兜底）
[POS]: world 层的数值规则——凡是有数量的后果都由这里算：导演只说「发生了研习」「发生了吸功」，增减多少不由 LLM 报数。
       研习先过 body 的预裁：顺利计一倍半时长、小有所得照计、受阻折半、有懂易理者解卦位再翻倍、岔气则折半并添一级内伤；
       研习按三阶兑现(初窥/小成/大成)，每阶有累计时长与间隔日数的门槛，同一部秘籍每人只兑现一次——
       十五分钟的调息不会再让人从二流升到一流；吸功按北冥阶段取对方功力的一定比例，吸者有损耗，被吸者当场负伤
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import body

# (阶名, 累计研习分钟, 距上一阶至少几日, 兑现 grants.power 的比例)
STAGES = (("初窥门径", 60, 0, 0.4), ("小有所成", 12 * 60, 1, 0.3), ("登堂入室", 48 * 60, 3, 0.3))
SITTING = 45                           # 研习一回至少一顿饭：调息运功是坐下来的事，片刻练不成——时长随指令走，不随措辞
TEACH_MINUTES = 120                    # 向身边之人求教一门招式：两个时辰入门，不涨功力
DRAINERS = {"北冥神功": (0.3, 0.5, 0.7)}  # 吸功之术 → 各阶吸取对方功力的比例
DRAIN_KEEP = 0.5                       # 吸来的内力，吸者只留下一半


def _log(world) -> dict:
    return world.player.data.setdefault("study", {})


def stage_of(world, source: str) -> int:
    return _log(world).get(source, {}).get("stage", 0)


def study(world, source: str, minutes: int) -> str:
    """主角研习 source（随身或此地的秘籍 / 身边人会的武学）minutes 分钟；返回一句连带说明（写给编剧）。"""
    g, me, day = world.graph, world.player, world.clock.day
    rec = _log(world).setdefault(source, {"minutes": 0, "stage": 0, "since": day})
    luck = body.forecast(world, source)
    rec["minutes"] += round(max(minutes, 15) * luck["factor"])
    said = f"研习{luck['tier']}" + (f"（{luck['why']}）" if luck["why"] else "")
    if luck["strain"]:
        said += "；" + body.injure(world, "真气走岔")
    return said + "：" + _gain(world, source, rec)


def _gain(world, source: str, rec: dict) -> str:
    g, me, day = world.graph, world.player, world.clock.day
    if g.kind(source) == "skill":  # 求教：入门即会，不涨功力
        if rec["stage"] == 0 and rec["minutes"] >= TEACH_MINUTES:
            rec["stage"] = 1
            me.push("skills", source)
            return f"你学会了{source}的入门功夫"
        return f"你随人习练{source}，尚未入门（已{rec['minutes']}分钟）"
    grants = g.get(source, "grants") or {}
    skills = [grants.get("skill")] + [x.get("skill") for x in g.get(source, "grants_extra") or []]
    told = []
    while rec["stage"] < len(STAGES):
        name, need, gap, share = STAGES[rec["stage"]]
        if rec["minutes"] < need or (rec["stage"] and day - rec["since"] < gap):
            break
        rec["stage"] += 1
        rec["since"] = day
        gain = round((grants.get("power") or 0) * share)
        me.add("power", gain)
        if rec["stage"] == 1:
            for s in filter(None, skills):
                me.push("skills", s)
        told.append(f"{source}{name}" + (f"，功力+{gain}" if gain else ""))
    return "；".join(told) or progress(world, source)


def progress(world, source: str) -> str:
    rec = _log(world).get(source)
    if not rec:
        return f"{source}：尚未研习（初窥须累计{STAGES[0][1]}分钟）"
    if rec["stage"] >= len(STAGES):
        return f"{source}：{STAGES[-1][0]}，此书已无可再得"
    name, need, gap, _ = STAGES[rec["stage"]]
    wait = max(0, rec["since"] + gap - world.clock.day) if rec["stage"] else 0
    return (f"{source}：{STAGES[rec['stage'] - 1][0] if rec['stage'] else '未入门'}，距「{name}」尚需研习"
            f"{max(0, need - rec['minutes'])}分钟" + (f"、且须再隔{wait}日" if wait else ""))


def drain(world, target: str, art: str) -> str:
    """主角以 art 吸 target 的内力：按阶取比例，被吸者功力当场下降并负伤，吸者只留一半。返回连带说明。"""
    g, me = world.graph, world.player
    ratios = DRAINERS[art]
    source = next((s for s, rec in _log(world).items() if art in _skills_of(g, s)), None)
    ratio = ratios[min(max(stage_of(world, source) if source else 1, 1), len(ratios)) - 1]
    power = g.get(target, "power") or 0
    loss = round(power * ratio)
    g.set(target, "power", power - loss)
    if g.get(target, "status") == "alive":
        g.set(target, "status", "wounded")
    gain = round(loss * DRAIN_KEEP)
    me.add("power", gain)
    return f"你以{art}吸去{target}的内力：{target}功力-{loss}，你功力+{gain}"


def _skills_of(g, source: str) -> list[str]:
    grants = g.get(source, "grants") or {}
    return [grants.get("skill")] + [x.get("skill") for x in g.get(source, "grants_extra") or []]
