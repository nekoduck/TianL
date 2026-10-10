"""
[INPUT]: 依赖 world/（World、lod、rag）与 narrative/agents；llm 可为 None（离线兜底）
[OUTPUT]: 对外提供 Game（open / act / debug），每回合返回一个纯 dict 的 Turn：
          time/clock(历法分段)/place/region/text/options/news(亲见与传闻)/status(身况标签)/void
[POS]: 两层唯一的交汇点——游戏主循环：取材(RAG+后台) → 导演编织剧情与选项 → 剧情后果落账 → 按道路结算时日
       → LOD1/LOD2 场外推演 → 传闻投递 → 编剧成文。基础设施在每一步替 LLM 记忆、算账、送信
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging

from .narrative import agents
from .world import lod, rag
from .world.clock import PER_DAY
from .world.world import World

log = logging.getLogger("tianlong")
MIN_ELAPSED = 1  # 主角有所行动，光阴至少流过一分钟——时长由导演按动作估计，系统只保证世界不在原地停摆


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
        journey = w.graph.distances(origin).get(w.here, 0) * PER_DAY  # 远行时日由道路决定，不由 LLM 估算
        days, months = w.advance(max(plan["elapsed"], journey, MIN_ELAPSED if deed else 0))
        self._offstage(days, months)
        news = [e for e in w.sync() if e["origin"] != "director"]  # 亲历之事不算传闻
        void = [f"{_describe(op)}（{why}）" for op, why in rejected]
        for v in void:
            log.info("未成立：%s", v)
        text = agents.write(self.llm, rag.build(w), deed or "环顾四周", plan["beats"], void,
                            [e["summary"] for e in news])
        self.options = plan["options"]
        w.player.remember(f"{w.clock.label()}·{w.here}：{plan['memory']}")
        return {"time": w.clock.label(), "clock": w.clock.parts(), "place": w.here,
                "region": w.graph.get(w.here, "region"), "text": text, "options": self.options,
                "news": [{"id": e["id"], "witnessed": bool(e.get("witnessed")), "date": w.clock.label(e["day"]),
                          "place": e["where"], "text": e["summary"]} for e in news],
                "status": rag.condition(w), "void": void}

    def _offstage(self, days: int, months: int):
        w = self.world
        if days:  # LOD1：日级刷新，一次调用覆盖所有流逝的日子
            actors, ring = lod.lod1_scope(w)
            if actors:
                reports = agents.simulate(self.llm, w.clock.label(), days, [rag.dossier(w, a) for a in actors])
                lod.absorb(w, reports, ring)
        for ev, tier in lod.due_canon(w, days, months):  # LOD2：按 order 依次结算，裁定在每桩结算前现场作出
            path, reasons = lod.verdict(w, ev, tier)
            if path == "canon":
                lod.settle(w, ev, ev, "canon")
            elif path == "skip":
                lod.settle(w, ev, {"happens": False}, "canon")
            else:
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
