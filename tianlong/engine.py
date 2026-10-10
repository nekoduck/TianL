"""
[INPUT]: 依赖 world/（World、lod、rag）与 narrative/agents；llm 可为 None（离线兜底）
[OUTPUT]: 对外提供 Game（open / act / debug），每回合返回一个纯 dict 的 Turn
[POS]: 两层唯一的交汇点——游戏主循环：取材(RAG+后台) → 导演编织剧情与选项 → 剧情后果落账 → 按道路结算时日
       → LOD1/LOD2 场外推演 → 传闻投递 → 编剧成文。基础设施在每一步替 LLM 记忆、算账、送信
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging

from .narrative import agents
from .world import lod, rag
from .world.world import World

log = logging.getLogger("tianlong")


def _describe(op) -> str:
    return "，".join(f"{k}={v}" for k, v in op.items() if k != "op") if isinstance(op, dict) else str(op)


class Game:
    def __init__(self, world: World, llm=None):
        self.world, self.llm = world, llm
        self.options: list[str] = []

    def open(self) -> dict:
        return self._turn("")

    def act(self, line: str) -> dict:
        line = line.strip()
        if line.isdigit() and 1 <= int(line) <= len(self.options):
            line = self.options[int(line) - 1]
        return self._turn(line)

    # ------------------------------------------------------------
    #  一个回合
    # ------------------------------------------------------------
    def _turn(self, deed: str) -> dict:
        w = self.world
        origin = w.here
        plan = agents.direct(self.llm, rag.build(w), rag.backstage(w), deed)
        applied, rejected = w.apply(plan["effects"], "director")
        if plan["event"]:
            w.record(plan["event"]["summary"], w.here, applied, "director", plan["event"]["weight"])
        journey = w.graph.distances(origin).get(w.here, 0) * 12  # 远行时日由道路决定，不由 LLM 估算
        days, months = w.advance(max(plan["elapsed"], journey))
        self._offstage(days, months)
        news = [e for e in w.sync() if e["origin"] != "director"]  # 亲历之事不算传闻
        void = [f"{_describe(op)}（{why}）" for op, why in rejected]
        for v in void:
            log.info("未成立：%s", v)
        text = agents.write(self.llm, rag.build(w), deed or "环顾四周", plan["beats"], void,
                            [e["summary"] for e in news])
        self.options = plan["options"]
        w.player.remember(f"{w.clock.label()}·{w.here}：{plan['memory']}")
        me = w.player
        return {"time": w.clock.label(), "place": w.here, "text": text,
                "news": [f"{w.clock.label(e['day'])}·{e['where']}：{e['summary']}" for e in news],
                "options": self.options, "void": void,
                "status": f"气血 {me['hp']}/{me['max_hp']}｜{rag.power_tier(me['power'])}｜{me['posture']}"
                          f"｜随身：{'、'.join(me['inventory']) or '无'}"}

    def _offstage(self, days: int, months: int):
        w = self.world
        if days:  # LOD1：日级刷新，一次调用覆盖所有流逝的日子
            actors, ring = lod.lod1_scope(w)
            if actors:
                reports = agents.simulate(self.llm, w.clock.label(), days, [rag.dossier(w, a) for a in actors])
                lod.absorb(w, reports, ring)
        for ev, reasons in lod.due_canon(w, days, months):  # LOD2：干净走原著轨道，污染则唤醒史官
            if not reasons:
                lod.settle(w, ev, ev, "canon")
                continue
            outcome = agents.chronicle(self.llm, ev, reasons, [rag.dossier(w, a) for a in ev["actors"]],
                                       lod.broken(w, ev))
            lod.settle(w, ev, outcome, "chronicle")

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
