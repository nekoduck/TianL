"""
[INPUT]: 依赖 world/（World、rules、lod、rag）与 narrative/agents；llm 可为 None（离线兜底）
[OUTPUT]: 对外提供 Game（open / act / debug），每回合返回一个纯 dict 的 Turn
[POS]: 两层唯一的交汇点——游戏主循环：裁决 → 落账 → 推进时钟 → LOD1/LOD2 调度 → 传闻投递 → RAG → 导演 → 编剧。
       状态流向永远是 world→narrative 读、narrative→world 只交"提案"
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from .narrative import agents
from .world import lod, rag, rules
from .world.world import World

LOOK = {"verb": "look", "target": None, "label": "环顾四周"}


class Game:
    def __init__(self, world: World, llm=None):
        self.world, self.llm = world, llm
        self.options: list[dict] = []

    def open(self) -> dict:
        return self._turn(LOOK)

    def act(self, line: str) -> dict:
        line = line.strip()
        if line.isdigit() and 1 <= int(line) <= len(self.options):
            intent = self.options[int(line) - 1]
        else:
            intent = agents.parse(self.llm, line, rules.legal_actions(self.world))
        return self._turn(intent)

    # ------------------------------------------------------------
    #  一个回合 = 基础设施核对 → RAG → LOD0 生成
    # ------------------------------------------------------------
    def _turn(self, intent: dict) -> dict:
        w = self.world
        out = rules.resolve(w, intent)
        applied, _ = w.apply(out["effects"], "rules")
        if out["event"]:
            w.record(out["event"]["summary"], w.here, applied, "rules", out["event"]["weight"])
        days, months = w.advance(out["cost"])
        self._simulate(days, months)
        news = [e for e in w.sync() if e["origin"] != "rules"]  # 自己做的事已在事实里，不算传闻
        return self._render(intent, out["facts"], news)

    def _simulate(self, days: int, months: int):
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

    def _render(self, intent: dict, facts: list[str], news: list[dict]) -> dict:
        w = self.world
        pack = rag.build(w)
        actions = rules.legal_actions(w)
        act = intent["label"] + (f"（{intent['manner']}）" if intent.get("manner") else "")
        facts = facts + [f"传闻抵达：{e['summary']}" for e in news]
        plan = agents.direct(self.llm, pack, act, facts, actions)
        text = agents.write(self.llm, pack, act, facts, plan["beats"])
        self.options = plan["options"]
        w.player.remember(f"{w.clock.label()}·{w.here}：{act}。{plan['beats'][0]}"[:90])
        me = w.player
        return {"time": w.clock.label(), "place": w.here, "text": text,
                "news": [f"{w.clock.label(e['day'])}·{e['where']}：{e['summary']}" for e in news],
                "options": [o["label"] for o in self.options],
                "status": f"气血 {me['hp']}/{me['max_hp']}｜{rag.power_tier(me['power'])}｜{me['posture']}"
                          f"｜随身：{'、'.join(me['inventory']) or '无'}"}

    # ------------------------------------------------------------
    #  调试视图：双账本对照
    # ------------------------------------------------------------
    def debug(self) -> dict:
        w = self.world
        drift = {nid: {"真相": {k: w.graph.get(nid, k) for k in b}, "认知": b}
                 for nid, b in w.knowledge.beliefs.items()
                 if any(w.graph.get(nid, k) != v for k, v in b.items())}
        return {"tokens": getattr(self.llm, "tokens", 0), "pending_news": len(w.messenger.pending),
                "canon_done": w.done, "taint": sorted(w.taint),
                "recent_truth": [f"{e['origin']}·{e['where']}：{e['summary']}" for e in w.truth.events[-5:]],
                "belief_drift": drift}
