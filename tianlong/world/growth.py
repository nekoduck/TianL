"""
[INPUT]: 依赖 world/body 的 forecast / injure（研习预裁与岔气）、world/actor 的 declare（被吸者负伤）、world/stock 的 cap / base（v9 残卷），World 门面（graph / player / clock / turn，鸭子类型）
[OUTPUT]: 对外提供 study()（研习一部秘籍或向人求教一门武学：累计时长、分阶兑现武学与功力；v13 账键是武学、一回合同一门只计一次）、drain()（北冥吸功：双边结算）、
          stage_of()、progress()（后台用的研习进度：这部书载着的每门功夫各一句）、mastery()（主角每门武学的进境投影：已会者带阶名、习练中者带已习时长）、
          studiable()（够得着的研习对象：手边与此地的秘籍、身边有人会的武学）、source_of()（研习一门武学：手边载着它的秘籍即那部秘籍）、arts_of()、
          STAGES、DRAINERS、SITTING（研习一回至少一顿饭，引擎据此给本回合光阴兜底）、TEACH_MINUTES
[POS]: world 层的数值规则——凡是有数量的后果都由这里算：导演只说「发生了研习」「发生了吸功」，增减多少不由 LLM 报数。
       研习先过 body 的预裁：顺利计一倍半时长、小有所得照计、受阻折半、有懂易理者解卦位再翻倍、岔气则折半并添一级内伤；
       受阻与岔气的那一回跨不过下一道门槛(v5)：预裁说「受阻」，账上就不会同时写「小有所成」；
       研习按三阶兑现(初窥/小成/大成)，每阶有累计时长与间隔日数的门槛，同一部秘籍每人只兑现一次——
       十五分钟的调息不会再让人从二流升到一流；吸功按北冥阶段取对方功力的一定比例，吸者有损耗，被吸者当场负伤。
       进境是一等状态(v4)：mastery 把研习账投影成「凌波微步：未入门（已习练40分钟，初窥须60分钟）」，界面、编剧、导演同看这一份——
       文字里写「身如游龙」而账上未入门，是文字错了，不是账错了；兑现阶段时记下 turn["advanced"]，裁决器据此辨认进境措辞有没有账可依
       残卷(v9)：一部书撕散的几份共一本研习账(按 base 记)，只存几份的残卷只研习得到 stock.cap 那一阶——功夫只在书上有的那几页里，拼全了接着练
       按武学分账(v13)：研习账 {武学: {src 来源, minutes 真实光阴, credit 功候, stage, since}}——北冥神功卷轴一部书载着两门功夫，练凌波微步就记凌波微步的账，
       不再连带北冥的阶与功力(第 41、50 回)；玩家所指的武学定账(原话或对象里有武学名，没有即这部书的第一门)；一回合同一门武学只计一次(第 41 回导演在两拍里各写一条研习，60 分钟记成了 240)；
       minutes 是世界里真流过的光阴，credit 是预裁顺逆折算之后的功候(顺利×1.5、通晓易理者解卦位再翻倍)，进阶的门槛看 credit，两项后台与界面都报；
       书上的功力(grants.power)只在它的第一门功夫进阶时兑现，附带的功夫(grants_extra)各兑各的；旧档按秘籍记账，读到时并入它所授的第一门武学
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
    """研习账 {武学: {src, minutes, credit, stage, since}}。旧档按秘籍记账：读到时并入它所授的第一门武学(功候取当时的累计)。"""
    log, g = world.player.data.setdefault("study", {}), world.graph
    for key in [k for k, rec in log.items() if "src" not in rec]:
        rec = log.pop(key)
        art = key if g.kind(key) == "skill" else (arts_of(g, key) or [key])[0]
        log.setdefault(art, {"src": key, "minutes": rec["minutes"], "credit": rec["minutes"], "stage": rec["stage"], "since": rec["since"]})
    return log


def art_of(world, source: str, art: str | None = None) -> str:
    """这回研习的是哪一门：导演点名的武学，不然玩家所指的(本回合授意里有哪门)，再不然这部书的第一门。"""
    arts = arts_of(world.graph, source)
    if art in arts:
        return art
    aim = getattr(world, "turn", None) or {}
    return next((a for a in arts if a in (aim.get("aim") or ())), None) or (arts[0] if arts else source)


def stage_of(world, source: str, art: str | None = None) -> int:
    return _log(world).get(art_of(world, source, art), {}).get("stage", 0)


def next_art(world, source: str) -> str | None:
    """这部书上下一门该练的功夫(v13)：先接着练已起头而未到顶的，再练没练过的；都到顶了即 None——选项据此不给练不动的。"""
    g, log = world.graph, _log(world)
    top = 1 if g.kind(source) == "skill" else stock.cap(g, source)
    left = [a for a in arts_of(g, source) if log.get(a, {}).get("stage", 0) < top]
    return next((a for a in left if a in log), None) or (left[0] if left else None)


def source_of(world, name: str) -> str:
    """研习 name 要去读哪一部：name 是武学而手边(随身或此地)有载着它的秘籍，就是那部秘籍；否则 name 自己(向人求教，或本就是秘籍)。"""
    g, me = world.graph, world.player
    if g.kind(name) != "skill":
        return name
    return next((i for i in [*me["inventory"], *g.where(type="item", location=world.here)] if name in _skills_of(g, i)), name)


def study(world, source: str, minutes: int, art: str | None = None) -> str:
    """主角研习 source（随身或此地的秘籍 / 身边人会的武学）minutes 分钟；返回一句连带说明（写给编剧）。
    v13 账键是武学：art 是这回练的那一门(导演点名的，或玩家所指的，不然这部书的第一门)；一回合同一门只计一次，重复的研习事码不另算光阴。"""
    g, me, day = world.graph, world.player, world.clock.day
    top = stock.cap(g, source) if g.kind(source) == "item" else len(STAGES)  # 残卷(v9)：只存几页，功夫也只到那几页
    if g.kind(source) == "item" and g.has(stock.base(g, source)):
        source = stock.base(g, source)  # 同一部书撕散的几份共一本研习账：拼全了接着练
    art = art_of(world, source, art)
    done = world.turn.setdefault("studied", set())
    if art in done:
        return ""
    done.add(art)
    rec = _log(world).setdefault(art, {"src": source, "minutes": 0, "credit": 0, "stage": 0, "since": day})
    luck = body.forecast(world, source, art)
    spent = max(minutes, 15)
    before, stall = rec["credit"], luck["tier"] in STALL
    rec["minutes"] += spent
    rec["credit"] += round(spent * luck["factor"])
    if stall:  # 受阻、岔气：这一回有所积累，却跨不过下一道门槛——预裁定的是这一回成不成，不只是折几成；已攒下的不倒扣
        rec["credit"] = min(rec["credit"], max(before, _need(g, source, rec["stage"]) - 1))
    said = f"研习{luck['tier']}" + (f"（{luck['why']}）" if luck["why"] else "")
    if luck["strain"]:
        said += "；" + body.injure(world, "真气走岔")
    if not stall:
        return said + "：" + _gain(world, source, rec, art, top)
    held = ((f"你随人熟习{art}的招式（已{rec['minutes']}分钟）" if rec["stage"] else f"你随人习练{art}，尚未入门（已{rec['minutes']}分钟）")
            if g.kind(source) == "skill" else progress(world, source, art))
    return said + "：" + held


STALL = ("受阻", "岔气")


def _need(g, source: str, stage: int) -> int:
    """跨入下一阶须累计的分钟；已到顶则无穷。"""
    if g.kind(source) == "skill":
        return TEACH_MINUTES if stage == 0 else float("inf")
    return STAGES[stage][1] if stage < len(STAGES) else float("inf")


def _gain(world, source: str, rec: dict, art: str, top: int = len(STAGES)) -> str:
    g, me, day = world.graph, world.player, world.clock.day
    if g.kind(source) == "skill":  # 求教：入门即会，不涨功力
        if rec["stage"] == 0 and rec["credit"] >= TEACH_MINUTES:
            rec["stage"] = 1
            me.push("skills", source)
            world.turn.setdefault("advanced", set()).add(source)
            return f"你学会了{source}的入门功夫"
        if rec["stage"] >= 1:  # v14 已入门：随人再练只是熟习招式，求教到此为止(run5 第 14 回已入门了又报「尚未入门」)
            return f"你随人熟习{source}的招式（已{rec['minutes']}分钟）：求教只到入门，再进一层须得剑谱秘籍"
        return f"你随人习练{source}，尚未入门（已{rec['minutes']}分钟）"
    grant = _grant(g, source, art)
    told = []
    if rec["stage"] >= top and top < len(STAGES):
        return f"{source}只是残卷，功夫只到「{STAGES[top - 1][0]}」，余下的在别的几份上"
    while rec["stage"] < top:
        name, need, gap, share = STAGES[rec["stage"]]
        if rec["credit"] < need or (rec["stage"] and day - rec["since"] < gap):
            break
        rec["stage"] += 1
        rec["since"] = day
        world.turn.setdefault("advanced", set()).add(art)  # 本回合真有进境：进境措辞有账可依
        gain = round((grant.get("power") or 0) * share)
        me.add("power", gain)
        if rec["stage"] == 1:
            me.push("skills", art)
        told.append(f"{art}{name}" + (f"，功力+{gain}" if gain else ""))
    return "；".join(told) or progress(world, source, art)


def _grant(g, source: str, art: str) -> dict:
    """这部书授 art 时兑现的东西(v13)：第一门功夫兑现书上的功力，附带的功夫(grants_extra)各兑各的。"""
    main = g.get(source, "grants") or {}
    if main.get("skill") == art:
        return main
    return next((x for x in g.get(source, "grants_extra") or [] if x.get("skill") == art), {})


def progress(world, source: str, art: str | None = None) -> str:
    """后台用的研习进度：给了 art 只说那一门，不然这部书载着的每门功夫各一句。"""
    arts = [art] if art else arts_of(world.graph, source) or [source]
    return "；".join(_progress(world, source, a) for a in arts)


def _progress(world, source: str, art: str) -> str:
    rec = _log(world).get(art)
    skill = world.graph.kind(source) == "skill"
    if not rec:
        return f"{art}：尚未研习（{'入门' if skill else '初窥'}须累计{TEACH_MINUTES if skill else STAGES[0][1]}分钟）"
    if rec["stage"] >= len(STAGES) and not skill:
        return f"{art}：{STAGES[-1][0]}，此书已无可再得"
    name, need, gap, _ = STAGES[rec["stage"]] if not skill else ("入门", TEACH_MINUTES, 0, 0)
    wait = max(0, rec["since"] + gap - world.clock.day) if rec["stage"] else 0
    spent = f"（已习练{rec['minutes']}分钟，折合功候{rec['credit']}）" if rec["credit"] != rec["minutes"] else ""
    return (f"{art}：{STAGES[rec['stage'] - 1][0] if rec['stage'] and not skill else ('入门' if rec['stage'] else '未入门')}，"
            + (f"火候已到「{name}」的门槛，只差一回顺利的研习{spent}" if 0 < need - rec["credit"] <= 1 else  # v14 受阻卡在门槛下：不报「尚需1分钟」
             f"距「{name}」尚需研习{max(0, need - rec['credit'])}分钟{spent}") + (f"、且须再隔{wait}日" if wait else ""))


def drain(world, target: str, art: str) -> str:
    """主角以 art 吸 target 的内力：按阶取比例，被吸者功力当场下降并负伤，吸者只留一半。返回连带说明。"""
    g, me = world.graph, world.player
    ratios = DRAINERS[art]
    rec = _log(world).get(art)  # 吸功之术练到哪一阶(原本就会、账上没有的按入门)
    ratio = ratios[min(max(rec["stage"] if rec else 1, 1), len(ratios)) - 1]
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
    for art, rec in _log(world).items():  # v13 账键是武学：练到哪一门就是哪一门，不连带同一部书上的别的功夫
        seen.add(art)
        skill = g.kind(rec["src"]) == "skill"
        if rec["stage"]:
            name = "入门" if skill else STAGES[rec["stage"] - 1][0]
            out.append({"art": art, "stage": name, "learned": art in me["skills"], "detail": f"{art}：{name}"})
        else:
            need = TEACH_MINUTES if skill else STAGES[0][1]
            spent = f"已习练{rec['minutes']}分钟" + (f"，折合功候{rec['credit']}" if rec["credit"] != rec["minutes"] else "")
            out.append({"art": art, "stage": "未入门", "learned": False, "detail": f"{art}：未入门（{spent}，{'入门' if skill else '初窥'}须{need}分钟）"})
    out += [{"art": s, "stage": "已会", "learned": True, "detail": f"{s}：已会"} for s in me["skills"] if s not in seen]
    return out


def ceiling(world, arts=()) -> int:
    """再坐下来练一回，最高能到第几阶(v13)：研习账上各门的下一阶，若还要隔几日（STAGES 的间隔）就够不着；没练过的功夫入门是第一阶。
    选项许的进境高过它，就是账上够不着的（第 52 回「继续练功至最高层」、第 54 回「练凌波微步至大成」，后台却写着距下一阶还须再隔 3 日）。"""
    g, log, day = world.graph, _log(world), world.clock.day
    names = list(arts) or sorted({a for s in studiable(world) for a in arts_of(g, s)} | set(log))
    best = 0
    for art in names:
        rec = log.get(art)
        stage = rec["stage"] if rec else 0
        top = 1 if g.kind(rec["src"] if rec else art) == "skill" else len(STAGES)
        if stage < top:
            gap = STAGES[stage][2] if top == len(STAGES) else 0
            stage += 0 if rec and stage and day - rec["since"] < gap else 1
        best = max(best, stage)
    return best or 1


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
