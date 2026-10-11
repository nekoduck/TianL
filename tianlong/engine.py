"""
[INPUT]: 依赖 world/（World、lod、rag、access.distances、effects.describe、clock.PER_DAY）与 narrative/agents；llm 可为 None（离线兜底）
[OUTPUT]: 对外提供 Game（open / act / debug），每回合返回一个纯 dict 的 Turn：
          time/clock(历法分段)/place/region/text/options/news(亲见与传闻)/status(身况标签)/void；
          可选监听 on(kind, data) 逐步报告：stage(direct→settle→write) → head(除正文外的整回合) → text(正文增量)
[POS]: 两层唯一的交汇点——游戏主循环：先了远方到期的原著(场外推演可闻江湖近闻) → 此地到期的一桩原著交给导演作本回合主干 → 导演编织节拍/后果/时长/选项
       → 原著照常落账，或因主角扰动而由导演的后果作准 → 导演后果落账 → 时长按措辞与道路结算 → LOD1 场外推演与新到期的远方原著
       → 传闻投递 → 编剧成文并写下真实梗概 → 事件门槛判定是否入江湖账本 → 近事溢出则折叠梗概。
       基础设施在每一步替 LLM 记忆、算账、裁决、送信；账本只记已成立之事
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging

from .narrative import agents
from .world import access, lod, rag
from .world.clock import PER_DAY
from .world.effects import describe
from .world.world import World

log = logging.getLogger("tianlong")
TAIL = 240        # 交给编剧承接语气的上回合末段字数
WITNESSES = 3     # 众目之下（在场他人≥3）的伤亡、易手、恩怨、重创才成江湖事件
GRAVE_LOSS = 25   # 主角单回合失血至此即为重创


def _newsworthy(applied: list, witnesses: int, hp_loss: int) -> int:
    """事件分量：0 不值一传 / 1 寻常江湖事 / 2 有人身亡。门槛由系统判定，不靠 LLM 自觉。"""
    def grave(op) -> bool:
        kind, key = op["op"], op.get("key")
        if kind in ("link", "unlink"):
            return True
        if op.get("id") == "player":
            return kind == "push" and key == "skills"
        return (kind, key) in {("set", "status"), ("set", "holder")}
    if witnesses < WITNESSES or (hp_loss < GRAVE_LOSS and not any(grave(op) for op in applied)):
        return 0
    return 2 if any(op["op"] == "set" and op.get("key") == "status" and op.get("value") == "dead" for op in applied) else 1


class Game:
    def __init__(self, world: World, llm=None):
        self.world, self.llm = world, llm
        self.options: list[str] = []
        self.last_text = ""          # 上回合正文，末段交给编剧承接语气与悬念
        self.tempo: list[str] = []   # 近三回合张力，供导演调节节奏

    def open(self, on=None) -> dict:
        return self._turn("", on)

    def act(self, line: str, on=None) -> dict:
        line = line.strip()
        if line.isdigit() and 1 <= int(line) <= len(self.options):
            line = self.options[int(line) - 1]
        return self._turn(line, on)

    # ------------------------------------------------------------
    #  一个回合
    # ------------------------------------------------------------
    def _turn(self, deed: str, on=None) -> dict:
        """on(kind, data)：stage 报进度，head 在落笔前送出除正文外的整回合，text 随编剧送出正文增量。"""
        emit = on or (lambda kind, data: None)
        w = self.world
        origin, before, hp0 = w.here, w.clock.label(), w.player["hp"]
        offstage, staged = lod.split_due(w)
        for ev, tier in offstage:                     # 远方到期之事先了：原著永不插队
            self._settle(ev, tier)
        skip = {ev["id"] for ev, _ in offstage} | ({staged["id"]} if staged else set())
        gm = rag.backstage(w, stage=staged, upcoming=lod.upcoming(w, skip), tempo=self.tempo)
        witnesses = len(rag.scene(w)["people"])
        emit("stage", "direct")
        plan = agents.direct(self.llm, rag.build(w), gm, deed)
        emit("stage", "settle")
        if staged:                                    # 此地的原著是本回合主干：照常则系统落账，被主角扰动则导演的后果作准
            if plan["canon"]["unfolds"]:
                lod.settle(w, staged, staged, "canon")
            else:
                lod.settle(w, staged, {"happens": False}, "director")
                w.taint.update(staged["actors"])
                log.info("原著「%s」因主角扰动未照常发生：%s", staged["id"], plan["canon"]["why"])
        applied, rejected = w.apply(plan["effects"], "director")
        journey = access.distances(w, origin).get(w.here, 0) * PER_DAY       # 远行时日由主角走得通的道路决定，不由 LLM 估算
        days, _ = w.advance(max(w.clock.minutes(plan["pace"]), journey))     # 时长由措辞换算，不由 LLM 报数
        self._offstage(days)
        arrived = w.sync()
        void = [f"{describe(op)}——{why}" for op, why in rejected]
        for v in void:
            log.info("未成立：%s", v)
        span = f"{plan['pace']}（{before} → {w.clock.label()}）" + \
               (f"；另有 {journey // PER_DAY} 日路程，现已抵达{w.here}" if journey else "")
        news = [e for e in arrived if e["origin"] != "director"]
        turn = {"time": w.clock.label(), "clock": w.clock.parts(), "place": w.here,
                "region": w.graph.get(w.here, "region"), "text": "", "options": plan["options"],
                "news": [{"id": e["id"], "witnessed": bool(e.get("witnessed")), "date": w.clock.label(e["day"]),
                          "place": e["where"], "text": e["summary"]} for e in news],
                "status": rag.condition(w), "void": void}
        emit("stage", "write")
        emit("head", {**turn})  # 快照：之后要往 turn 里填正文，不能让监听者看到它变
        page = agents.write(self.llm, rag.build(w), {
            "deed": deed or "环顾四周", "beats": plan["beats"], "void": void, "span": span, "prev": self.last_text[-TAIL:],
            "news": [e["summary"] for e in arrived if not e.get("witnessed")]},  # 亲历之事已在节拍里，不再当传闻
            on_text=on and (lambda d: emit("text", d)))
        turn["text"] = page["text"]
        weight = _newsworthy(applied, witnesses, hp0 - w.player["hp"])
        if weight:                                    # 众目之下的大事才传开，记的是编剧核实过的一句话
            w.record(page["headline"] or page["memory"].replace("你", w.player["name"]), origin, applied, "director", weight)
        evicted = w.player.remember(f"{w.clock.label()}·{w.here}：{page['memory']}")
        if evicted:
            w.player.set("synopsis", agents.recap(self.llm, w.player["synopsis"], evicted))
        self.options, self.last_text = plan["options"], page["text"]
        self.tempo = (self.tempo + [plan["tension"]])[-3:]
        return turn

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
