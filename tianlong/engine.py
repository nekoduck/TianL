"""
[INPUT]: 依赖 world/（World、adjudicate、menu、lod、rag、situation、perspective(编剧视角)、body.recover(歇息养伤)、pacing.record / calm(节奏账、幕间省略的闸门)、growth.SITTING(研习至少一顿饭)、adjudicate.physical、access.distances、effects.describe、clock.PER_DAY）与 narrative/agents；llm 可为 None（离线兜底）
[OUTPUT]: 对外提供 Game（open / act(原话照收，选项编号的快捷写法归终端) / flush(汇合后台折叠的梗概) / debug / menu(选项→对象)），每回合返回一个纯 dict 的 Turn：
          time/clock(历法分段)/place/region/text/options/news(亲见与传闻)/status(身况标签)/void；
          可选监听 on(kind, data) 逐步报告：stage(direct→settle→write) → head(除正文与选项外的整回合) → text(正文增量)
[POS]: 两层唯一的交汇点——游戏主循环，「LLM 提议，世界裁决，文字只渲染已成立之事」：
       授意(选项自带的对象 + 原话里的名字) → 先了远方到期的原著 → 焦点检索与后台 → 导演逐拍提议
       → 在世界副本上试演(逐拍落账 → 此地原著 → 词表体检)，硬违例交导演返工一次，仍不成立的拍号交定稿整拍作废 → 定稿落账
       → 时长按措辞与道路结算(研习至少一顿饭)，一幕了结、无人相逼时导演写的幕间省略(cut)再让光阴跳过(歇满半日即按规则养伤) → 传闻投递 → 编剧从主角视角(视锥与节拍先过 veil/mask，成文按段再过一遍 mask——编剧熟读原著，名字可能是它自己带来的)只凭已成立之事成文、拟选项与伏笔(场外推演与新到期的远方原著同时在后台进行，其传闻下回合才到)
       → 选项过出口检查、对象记入 menu 作下一回合的授意 → 事件门槛判定入江湖账本 → 近事、未了之事的推进与了结、伏笔账(至多两条，身体不作伏笔)、节奏账(主题与僵持，下回合交导演作阻尼)、场景实体回收；近事溢出交后台折叠梗概。
       节奏看本幕之问的结局：连番被打断，下一回合不得再打断。主角做完便走的事，以亲历之人、事发之日、事发之地入账；
       编剧没写梗概时，以意图与系统核实过的后果代记。一回合是原子的：中途抛错，世界与说书人的记忆都回到回合开始之时——重试不会把一件事做两遍
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from .narrative import agents
from .world import access, adjudicate, body, growth, lexicon, lod, menu, pacing, perspective, rag, situation
from .world.clock import PER_DAY
from .world.effects import describe
from .world.world import World

log = logging.getLogger("tianlong")
TAIL = 240        # 交给编剧承接语气的上回合末段字数
WITNESSES = 3     # 众目之下（在场他人≥3）的伤亡、易手、恩怨、重创才成江湖事件
GRAVE_LOSS = 25   # 主角单回合失血至此即为重创
BODILY = re.compile(r"伤|毒|病|血|疼|痛|反噬|岔气|走火|经脉|内息")  # 关于身体的伏笔一律不收
HOOKS = 2         # 未兑现的伏笔至多记这么多条：悬念是稀缺品，多了便成了催债


def _newsworthy(applied: list, witnesses: int, hp_loss: int) -> int:
    """事件分量：0 不值一传 / 1 寻常江湖事 / 2 有人身亡。门槛由系统判定，不靠 LLM 自觉。"""
    def grave(op) -> bool:
        kind, key = op["op"], op.get("key")
        if kind in ("link", "unlink", "drain"):
            return True
        if op.get("id") == "player":
            return kind == "push" and key == "skills"
        return (kind, key) in {("set", "status"), ("set", "holder")}
    if witnesses < WITNESSES or (hp_loss < GRAVE_LOSS and not any(grave(op) for op in applied)):
        return 0
    return 2 if any(op["op"] == "set" and op.get("key") == "status" and op.get("value") == "dead" for op in applied) else 1



def _paragraphs(send):
    """正文增量按段送出：一段齐了才过视角掩码——名字与引号不会被拦腰切开，整段掩码与整篇掩码逐字相同。"""
    buf = []

    def feed(delta):
        buf.append(delta)
        text = "".join(buf)
        cut = text.rfind("\n") + 1
        if cut:
            send(text[:cut])
            buf[:] = [text[cut:]]
    def flush():
        rest = "".join(buf)
        buf.clear()
        if rest:
            send(rest)
    feed.flush = flush
    return feed

class Game:
    def __init__(self, world: World, llm=None):
        self.world, self.llm = world, llm
        self.options: list[str] = []
        self.menu: dict[str, list[str]] = {}  # 选项文字 → 对象：玩家选中即成为下一回合的授意范围
        self.last_text = ""          # 上回合正文，末段交给编剧承接语气与悬念
        self.tempo: list[str] = []   # 近三回合本幕之问的结局，供导演调节节奏
        self._recap = None           # 后台折叠中的梗概：下一回合开始前汇合

    def open(self, on=None) -> dict:
        return self._turn("", on)

    def act(self, deed: str, on=None) -> dict:
        """玩家原话照收（选项即原话）；"打 1 选第一项"之类的快捷写法是终端的事，不在内核里猜。"""
        return self._turn(deed.strip(), on)

    def flush(self):
        """汇合后台折叠的梗概：存档之前、下一回合之前调用。"""
        if self._recap is not None:
            self.world.player.set("synopsis", self._recap.result())
            self._recap = None

    # ------------------------------------------------------------
    #  一个回合：原子的——要么整个成立，要么不曾发生
    # ------------------------------------------------------------
    def _turn(self, deed: str, on=None) -> dict:
        self.flush()
        before = json.dumps(self.world.dump(), ensure_ascii=False), self.options, self.menu, self.last_text, self.tempo
        try:
            return self._play(deed, on)
        except Exception:
            dump, self.options, self.menu, self.last_text, self.tempo = before
            self.world = World.from_dump(json.loads(dump))
            self._recap = None
            raise

    def _play(self, deed: str, on=None) -> dict:
        """on(kind, data)：stage 报进度，head 在落笔前送出除正文与选项外的整回合，text 随编剧送出正文增量。"""
        emit = on or (lambda kind, data: None)
        w = self.world
        w.turn = {}
        w.player.set("turn", w.player["turn"] + 1)
        origin, day0, before, hp0 = w.here, w.clock.day, w.clock.label(), w.player["hp"]
        aim = adjudicate.targets(w, deed, self.menu.get(deed, ()))  # 玩家所指：选项自带的对象 + 原话里认得出的名字
        offstage, staged = lod.split_due(w)
        for ev, tier in offstage:                     # 远方到期之事先了：原著永不插队
            self._settle(ev, tier)
        skip = {ev["id"] for ev, _ in offstage} | ({staged["id"]} if staged else set())
        soon = lod.upcoming(w, skip)
        gm = rag.backstage(w, stage=staged, upcoming=soon, tempo=self.tempo, aim=aim)
        w.player.set("drift", [])                     # 上回合正文的偏差已交导演后台：交代一次即清
        pack = rag.build(w)
        witnesses = len(rag.scene(w)["people"])
        emit("stage", "direct")
        plan = agents.direct(self.llm, pack, gm, deed)
        emit("stage", "settle")
        rules = {"embargo": {w.graph.get(a, "faction") for ev, _ in soon for a in ev["actors"]
                             if a not in situation.around(w)} - {None},
                 "cast": set(staged["actors"]) if staged else set(),
                 "no_interrupt": self.tempo[-2:] == ["interrupted", "interrupted"]}
        plan, drop = self._rehearse(plan, aim, staged, day0, rules, pack, gm, deed)
        ruling = self._enact(w, plan, aim, staged, day0, rules, drop)  # 定稿：仍不成立的拍整拍作废
        if 0 in drop and ruling.question.get("state") == "interrupted":
            ruling.question["state"] = "open"
        applied = ruling.applied
        w.witness(applied)                            # 主角眼前发生的变化当场入认知，随即离开也记得
        stops = [origin, *(op["value"] for op in applied if op.get("id") == "player" and op.get("key") == "location")]
        journey = sum(access.distances(w, a).get(b, 0) for a, b in zip(stops, stops[1:])) * PER_DAY  # 每一程都算，不由 LLM 估算
        spent = max(w.turn["minutes"], journey)
        days, _ = w.advance(spent)                    # 时长由措辞换算，不由 LLM 报数
        scene_end = w.clock.label()
        cut = plan.get("cut")
        veto = cut and pacing.calm(w, ruling.question.get("state"), ruling.beats)  # 幕间省略：一幕了了、无人相逼才许跳
        if cut and not veto:
            gap = w.clock.minutes(cut)                # 「一夜」算到次日辰时：按收束之时起算
            more, _ = w.advance(gap)
            days, spent = days + more, spent + gap
        elif veto:
            log.info("幕间省略不成立：%s（%s）", cut, veto)
        w.turn["days"] = days
        mend = body.recover(w, spent)                 # 歇满半日，气血渐复、内伤降一级：伤病的好转也归规则
        arrived = w.sync()
        void = ruling.void
        for v in void:
            log.info("未成立：%s", v)
        for f in ruling.hard + ruling.soft:
            log.info("体检·%s：%s", f.kind, f.message)
        span = f"{plan['pace']}（{before} → {scene_end}）" + \
               (f"；另有 {journey // PER_DAY} 日路程，现已抵达{w.here}" if journey else "") + \
               (f"；此幕收束，光阴跳过{cut}（→ {w.clock.label()}）：正文末尾以一两句过场写出这段空白" if cut and not veto else "")
        news = [e for e in arrived if e["origin"] != "director"]
        turn = {"time": w.clock.label(), "clock": w.clock.parts(), "place": w.here,
                "region": w.graph.get(w.here, "region"), "text": "", "options": [],
                "news": [{"id": e["id"], "witnessed": bool(e.get("witnessed")), "date": w.clock.label(e["day"]),
                          "place": e["where"], "text": e["summary"]} for e in news],
                "status": rag.condition(w), "void": void}
        emit("stage", "write")
        emit("head", copy.deepcopy(turn))  # 快照：之后要往 turn 里填正文与选项，不能让监听者看到它变
        view = perspective.veil(w, rag.build(w))  # 编剧从主角的视角写：不识名之人只剩叫法，不给即不泄露
        veil = lambda text, who=None: perspective.mask(w, text, who)
        frame = {"deed": deed or "环顾四周", "beats": [veil(b["text"], b["who"]) + (f"〔{b['mood']}〕" if b.get("mood") else "") for b in ruling.beats if b["text"]],
                 "void": [veil(v) for v in void], "span": span, "prev": self.last_text[-TAIL:],
                 "notes": [veil(n) for n in ruling.notes + ([mend] if mend else [])], "addressed": [perspective.handle(w, p) for p in ruling.addressed],
                 "candidates": [veil(c) for c in ruling.candidates],
                 "news": [e["summary"] for e in arrived if not e.get("witnessed")]}  # 亲历之事已在节拍里，不再当传闻
        with ThreadPoolExecutor(max_workers=1) as pool:  # 场外推演与新到期的远方原著，与编剧落笔并行：其传闻本就迟到
            offstage_job = pool.submit(self._offstage, days)
            stream = on and _paragraphs(lambda d: emit("text", veil(d)))
            page = agents.write(self.llm, view, frame, on_text=stream)
            if stream:
                stream.flush()
            offstage_job.result()
        page["text"] = veil(page["text"])            # 编剧熟读原著，名字可能是它自己带来的：成文也过一遍主角的视角
        drift = [] if w.turn.get("advanced") else lexicon.mastery(page["text"], "player")
        if drift:  # 正文已送出读者，改不回来：记下偏差，下回合交导演由剧情交代
            arts = "；".join(a["detail"] for a in growth.mastery(w)) or "主角尚无武学"
            w.player.set("drift", [f"正文写主角「{'、'.join(drift)}」，账上：{arts}"])
            log.info("正文偏差·进境：%s", drift)
        turn["text"] = page["text"]
        picked = menu.check(w, page["options"], ruling.addressed, ruling.candidates, plan["options"])  # 兜底项看局面，归 menu
        self.menu = {text: ids for text, ids in picked}
        turn["options"] = [text for text, _ in picked]
        facts = "；".join(describe(op) for op in applied if op.get("key") not in ("threads", "conditions"))
        memory = veil(page["memory"] or (f"你意欲{deed}" if deed else "你凝神四顾") + (f"：{facts.replace('主角', '你')}" if facts else ""))
        weight = _newsworthy(applied, witnesses, hp0 - w.player["hp"])
        if weight:  # 众目之下的大事才传开：记编剧核实过的一句话，没有便记系统核实过的后果；亲历、事发之日、事发之地
            told = page["headline"] or (page["memory"] or facts).replace("你", w.player["name"]).replace("主角", w.player["name"])
            w.record(told, origin, applied, "director", weight, day=day0, witnessed=True)
        self._close(ruling, page, memory, moved=w.here != origin)
        self.options, self.last_text = turn["options"], page["text"]
        self.tempo = (self.tempo + [ruling.question.get("state") or "open"])[-3:]
        return turn

    # ------------------------------------------------------------
    #  试演与定稿：先在世界的副本上裁决，硬违例交导演返工一次；仍不成立的拍号交定稿作废
    # ------------------------------------------------------------
    def _rehearse(self, plan, aim, staged, day0, rules, pack, gm, deed) -> tuple[dict, dict]:
        trial = copy.deepcopy(self.world)
        ruling = self._enact(trial, plan, aim, staged, day0, rules)
        if not ruling.hard:
            return plan, {}
        problems = adjudicate.brief(trial, ruling)
        log.info("导演返工：%s", "；".join(problems))
        fixed = agents.repair(self.llm, pack, gm, deed, plan, problems)
        if fixed:
            trial = copy.deepcopy(self.world)
            again = self._enact(trial, fixed, aim, staged, day0, rules)
            if len(again.hard) <= len(ruling.hard):
                plan, ruling = fixed, again
        return plan, adjudicate.doomed(ruling)

    @staticmethod
    def _enact(world, plan, aim, staged, day0, rules, drop=None):
        """一份提议在一个世界上演出：先逐拍落账导演的后果，再落此地原著——照常(且前提未破)则系统落账、盖今日之戳，
        被主角扰动则作罢；导演已挪动的人原著挪不动，同一个人不会被两处同时调遣。最后体检拍文。"""
        adjudicate.imply(world, plan, aim)              # 拍里在习练玩家所指的秘籍、导演却没写 study：系统追认这一回研习
        studies = any(op.get("op") == "study" for b in plan["beats"] for op in b.get("ops") or [] if isinstance(op, dict))
        world.turn["minutes"] = max(world.clock.minutes(plan["pace"]), growth.SITTING if studies else 0)  # 研习至少一顿饭
        broken = staged and lod.broken(world, staged)  # 前提以回合开始时为准：主角这一举之前，原著本该如何

        def canon():
            if not staged:
                return
            if plan["canon"]["unfolds"] and not broken:
                lod.settle(world, staged, staged, "canon", day=day0, witnessed=True)  # 主角眼前上演，随即离开也是亲历
            else:
                lod.settle(world, staged, {"happens": False}, "director", day=day0)
                if not plan["canon"]["unfolds"]:
                    world.taint.update(staged["actors"])
        return adjudicate.judge(world, plan, aim, drop=drop, then=canon, **rules)

    def _close(self, ruling, page, memory, moved=False):
        """回合收尾：近事、未了之事的推进与了结、伏笔账、节奏账、场景实体回收；近事溢出则交后台折叠梗概。"""
        w, me = self.world, self.world.player
        touched = {i for op in ruling.applied for i in (op.get("id"), op.get("src"), op.get("dst"), op.get("value"))
                   if isinstance(i, str)}
        situation.touch(w, touched)
        for goal in situation.settle(w):
            log.info("未了之事了结：%s", goal)
        situation.sweep(w)
        hooks = [h for h in me["hooks"] if h["due"] > me["turn"] - 1]  # 到期之后再给导演一回合交代，然后静默作罢
        pacing.record(w, ruling.beats, moved or any(adjudicate.physical(op) for op in ruling.applied))
        if page.get("hook") and not BODILY.search(page["hook"]["text"]):  # 身体归规则，伤病不作悬念
            hooks.append({"text": page["hook"]["text"], "due": me["turn"] + page["hook"]["turns"]})
        me.set("hooks", hooks[-HOOKS:])
        evicted = me.remember(f"{w.clock.label()}·{w.here}：{memory[:60]}")
        if evicted:
            synopsis = me["synopsis"]
            self._recap = ThreadPoolExecutor(max_workers=1).submit(agents.recap, self.llm, synopsis, evicted)

    def _settle(self, ev: dict, tier: int):
        """场外原著的结算：干净照原著、被扰动的大事与近处破局交史官、远方小事破局作罢。"""
        w = self.world
        path, reasons = lod.verdict(w, ev, tier)
        if path == "canon":
            lod.settle(w, ev, ev, "canon")
        elif path == "skip":
            lod.settle(w, ev, {"happens": False}, "canon")
        else:
            outcome = agents.chronicle(self.llm, ev, reasons, [rag.dossier(w, a) for a in ev["actors"]], lod.broken(w, ev),
                                       rag.heard(w, [ev["where"]]))
            lod.settle(w, ev, outcome, "chronicle")

    def _offstage(self, days: int):
        w = self.world
        if days:  # LOD1：日级刷新，一次调用覆盖所有流逝的日子
            actors, ring = lod.lod1_scope(w)
            if actors:
                reports = agents.simulate(self.llm, w.clock.label(), days, [rag.dossier(w, a) for a in actors],
                                          rag.heard(w, [w.graph.get(a, "location") for a in actors]))
                lod.absorb(w, reports, ring)
        for ev, tier in lod.split_due(w)[0]:  # 时光流过后新到期的远方原著；此地的留待下回合作主干
            self._settle(ev, tier)

    # ------------------------------------------------------------
    #  调试视图：双账本对照
    # ------------------------------------------------------------
    def debug(self) -> dict:
        w = self.world
        drift = {nid: {"真相": {k: w.graph.get(nid, k) for k in b}, "认知": b}
                 for nid, b in w.knowledge.beliefs.items()
                 if any(w.graph.get(nid, k) != v for k, v in b.items())}
        return {"tokens": getattr(self.llm, "tokens", 0), "pending_news": len(w.messenger.pending),
                "canon_done": w.done, "taint": sorted(w.taint), "secrets_known": w.knowledge.secrets,
                "recent_truth": [f"{e['origin']}·{e['where']}：{e['summary']}" for e in w.truth.events[-5:]],
                "belief_drift": drift}
