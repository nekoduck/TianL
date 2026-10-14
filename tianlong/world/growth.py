"""
[INPUT]: 依赖 world/body 的 forecast / injure（研习预裁与岔气）、world/actor 的 declare（被吸者负伤）、world/stock 的 cap / base（v9 残卷），World 门面（graph / player / clock / turn，鸭子类型）
[OUTPUT]: 对外提供 study()（研习一部秘籍或向人求教一门武学：累计时长、分阶兑现武学与功力）、drain()（北冥吸功：双边结算）、
          stage_of()、progress()（后台用的研习进度一句话）、mastery()（主角每门武学的进境投影：已会者带阶名、习练中者带已习时长）、
          studiable()（够得着的研习对象：手边与此地的秘籍、身边有人会的武学）、arts_of()、STAGES、DRAINERS、SITTING（研习一回至少一顿饭，引擎据此给本回合光阴兜底）、TEACH_MINUTES
[POS]: world 层的数值规则——凡是有数量的后果都由这里算：导演只说「发生了研习」「发生了吸功」，增减多少不由 LLM 报数。
       研习先过 body 的预裁：顺利计一倍半时长、小有所得照计、受阻折半、有懂易理者解卦位再翻倍、岔气则折半并添一级内伤；
       受阻与岔气的那一回跨不过下一道门槛(v5)：预裁说「受阻」，账上就不会同时写「小有所成」；
       研习按三阶兑现(初窥/小成/大成)，每阶有累计时长与间隔日数的门槛，同一部秘籍每人只兑现一次——
       十五分钟的调息不会再让人从二流升到一流；吸功按北冥阶段取对方功力的一定比例，吸者有损耗，被吸者当场负伤。
       进境是一等状态(v4)：mastery 把研习账投影成「凌波微步：未入门（已习练40分钟，初窥须60分钟）」，界面、编剧、导演同看这一份——
       文字里写「身如游龙」而账上未入门，是文字错了，不是账错了；兑现阶段时记下 turn["advanced"]，裁决器据此辨认进境措辞有没有账可依
       残卷(v9)：一部书撕散的几份共一本研习账(按 base 记)，只存几份的残卷只研习得到 stock.cap 那一阶——功夫只在书上有的那几页里，拼全了接着练
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import actor, body, situation, stock

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
    top = stock.cap(g, source) if g.kind(source) == "item" else len(STAGES)  # 残卷(v9)：只存几页，功夫也只到那几页
    if g.kind(source) == "item" and g.has(stock.base(g, source)):
        source = stock.base(g, source)  # 同一部书撕散的几份共一本研习账：拼全了接着练
    rec = _log(world).setdefault(source, {"minutes": 0, "stage": 0, "since": day})
    luck = body.forecast(world, source)
    before, stall = rec["minutes"], luck["tier"] in STALL
    rec["minutes"] += round(max(minutes, 15) * luck["factor"])
    if stall:  # 受阻、岔气：这一回有所积累，却跨不过下一道门槛——预裁定的是这一回成不成，不只是折几成；已攒下的不倒扣
        rec["minutes"] = min(rec["minutes"], max(before, _need(g, source, rec["stage"]) - 1))
    said = f"研习{luck['tier']}" + (f"（{luck['why']}）" if luck["why"] else "")
    if luck["strain"]:
        said += "；" + body.injure(world, "真气走岔")
    if not stall:
        return said + "：" + _gain(world, source, rec, top)
    held = f"你随人习练{source}，尚未入门（已{rec['minutes']}分钟）" if g.kind(source) == "skill" else progress(world, source)
    return said + "：" + held


STALL = ("受阻", "岔气")


def _need(g, source: str, stage: int) -> int:
    """跨入下一阶须累计的分钟；已到顶则无穷。"""
    if g.kind(source) == "skill":
        return TEACH_MINUTES if stage == 0 else float("inf")
    return STAGES[stage][1] if stage < len(STAGES) else float("inf")


def _gain(world, source: str, rec: dict, top: int = len(STAGES)) -> str:
    g, me, day = world.graph, world.player, world.clock.day
    if g.kind(source) == "skill":  # 求教：入门即会，不涨功力
        if rec["stage"] == 0 and rec["minutes"] >= TEACH_MINUTES:
            rec["stage"] = 1
            me.push("skills", source)
            world.turn.setdefault("advanced", set()).add(source)
            return f"你学会了{source}的入门功夫"
        return f"你随人习练{source}，尚未入门（已{rec['minutes']}分钟）"
    grants = g.get(source, "grants") or {}
    skills = [grants.get("skill")] + [x.get("skill") for x in g.get(source, "grants_extra") or []]
    told = []
    if rec["stage"] >= top and top < len(STAGES):
        return f"{source}只是残卷，功夫只到「{STAGES[top - 1][0]}」，余下的在别的几份上"
    while rec["stage"] < top:
        name, need, gap, share = STAGES[rec["stage"]]
        if rec["minutes"] < need or (rec["stage"] and day - rec["since"] < gap):
            break
        rec["stage"] += 1
        rec["since"] = day
        world.turn.setdefault("advanced", set()).update(filter(None, skills))  # 本回合真有进境：进境措辞有账可依
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
        actor.declare(world, target, "wounded")  # 被吸者当场负伤：气血随之对齐，养回来即安好
    gain = round(loss * DRAIN_KEEP)
    me.add("power", gain)
    return f"你以{art}吸去{target}的内力：{target}功力-{loss}，你功力+{gain}"


def _skills_of(g, source: str) -> list[str]:
    grants = g.get(source, "grants") or {}
    return [grants.get("skill")] + [x.get("skill") for x in g.get(source, "grants_extra") or []]


def arts_of(g, source: str) -> list[str]:
    """一个研习对象载着哪些武学：武学即自身，秘籍即它所授。"""
    return [source] if g.kind(source) == "skill" else [s for s in _skills_of(g, source) if s]


def mastery(world) -> list[dict]:
    """主角的进境投影：[{art, stage, learned, detail}]。已会的武学带上阶名(来自研习账；原本就会的写「已会」)，
    习练中尚未入门的写明已习多久、初窥还差多少——这一份同时给界面、编剧与导演。"""
    g, me, out, seen = world.graph, world.player, [], set()
    for source, rec in _log(world).items():
        for art in arts_of(g, source):
            if art in seen:
                continue
            seen.add(art)
            if rec["stage"]:
                name = "入门" if g.kind(source) == "skill" else STAGES[rec["stage"] - 1][0]
                out.append({"art": art, "stage": name, "learned": art in me["skills"], "detail": f"{art}：{name}"})
            else:
                need = TEACH_MINUTES if g.kind(source) == "skill" else STAGES[0][1]
                out.append({"art": art, "stage": "未入门", "learned": False,
                            "detail": f"{art}：未入门（已习练{rec['minutes']}分钟，入门须{need}分钟）"})
    out += [{"art": s, "stage": "已会", "learned": True, "detail": f"{s}：已会"} for s in me["skills"] if s not in seen]
    return out


def unearned(world, words: list[str]) -> list[str]:
    """进境措辞里账上没有的：所需之阶高过研习账上最高的一阶(原本就会的武学算入门)，或说「功力大进」而本回合并无进境。"""
    from .lexicon import mastery_level  # 词表只在核对进境措辞时用到
    top = max([r["stage"] for r in _log(world).values()] + [1 if world.player["skills"] else 0])
    fresh = bool(world.turn.get("advanced"))
    return [w for w in words if (mastery_level(w) == 0 and not fresh) or mastery_level(w) > top]


def studiable(world, aim=(), extra=()) -> list[str]:
    """够得着的研习对象：手边与此地(含 extra 里暗藏)的秘籍、身边有人会的武学；给了 aim 只留玩家所指的(秘籍所授的武学也认作那部秘籍)。"""
    g, me = world.graph, world.player
    here = [i for i in g.where(type="item", location=world.here) if not g.get(i, "hidden")]
    books = [i for i in dict.fromkeys([*me["inventory"], *here, *extra]) if g.get(i, "grants")]
    taught = sorted({k for p in situation.around(world) for k in g.get(p, "skills") or []} - set(me["skills"]))
    if not aim:
        return books + taught
    aim = set(aim)
    return [b for b in books if b in aim or aim & set(arts_of(g, b))] + [k for k in taught if k in aim]
