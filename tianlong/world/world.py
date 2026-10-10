"""
[INPUT]: 依赖 world/ 下 genesis(原著硬知识)、graph、clock、blackboard、ledger、effects、rag 全部基础设施
[OUTPUT]: 对外提供 World 门面（create 创世 / 写入 / 记事 / 推进时间 / 同步认知 / 原子存档与读档）
[POS]: world 层的聚合根——上层（engine）只与 World 对话；它把"变更→记账→传闻→观察"串成唯一的状态流水线
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import os
from pathlib import Path

from . import effects, genesis, rag
from .blackboard import Blackboard
from .clock import Clock
from .graph import ROAD, Graph
from .ledger import Knowledge, Messenger, Truth

class World:
    def __init__(self, graph, player, clock, truth, knowledge, messenger, canon, done, taint, seed):
        self.graph: Graph = graph
        self.player: Blackboard = player
        self.clock: Clock = clock
        self.truth: Truth = truth
        self.knowledge: Knowledge = knowledge
        self.messenger: Messenger = messenger
        self.canon: list[dict] = canon      # 原著时间线（平行轨道）
        self.done: list[str] = done         # 已结算的原著事件 id
        self.taint: set[str] = taint        # 因果涟漪：被玩家亲手触碰过的节点
        self.seed: int = seed

    # ------------------------------------------------------------
    #  创世：以原著硬知识(genesis)为蓝本；data 可注入，便于测试
    # ------------------------------------------------------------
    @classmethod
    def create(cls, name: str | None = None, data: dict | None = None) -> "World":
        d = data or genesis.load()
        graph = Graph(d["nodes"])
        for a, b, days in d["roads"]:
            graph.link(a, b, ROAD, days=days)
        for r in d["relations"]:
            graph.link(**r)
        player = Blackboard({**d["player"], **({"name": name} if name else {})})
        world = cls(graph, player, Clock(d["start_tick"]), Truth(), Knowledge.from_truth(graph),
                    Messenger(), d["canon"], [], set(), d["seed"])
        world.sync()
        return world

    @property
    def here(self) -> str:
        return self.player["location"]

    # ------------------------------------------------------------
    #  状态流水线：apply → record → advance → sync
    # ------------------------------------------------------------
    def apply(self, ops: list, origin: str, scope: set | None = None):
        return effects.apply(self, ops, origin, scope)

    def record(self, summary: str, where: str, applied: list, origin: str, weight: int = 1,
               public: bool = True) -> dict:
        """写入绝对真实账本，并把传闻投进消息队列；主角身在事发之地即为亲历者。"""
        event = self.truth.record(self.clock.day, where, summary, applied, origin, weight)
        event.update(public=public, witnessed=where == self.here)
        self.messenger.post(event)
        return event

    def advance(self, shichen: int) -> tuple[int, int]:
        return self.clock.advance(shichen)

    def sync(self) -> list[dict]:
        """投递已抵达的传闻，再以亲眼所见校正认知；返回本次抵达的传闻。"""
        news = self.messenger.deliver(self.truth, self.knowledge, self.graph.distances(self.here), self.clock.day)
        self._observe()
        return news

    def _observe(self):
        s = rag.scene(self)
        seen = [self.here] + s["people"] + s["dead"] + s["features"] + s["items"]
        for nid, belief in self.knowledge.beliefs.items():  # 以为在此、实则不在的人：下落不明
            if belief.get("location") == self.here and nid not in seen and self.graph.kind(nid) == "person":
                belief["location"] = None
        self.knowledge.observe(self.graph, seen)

    # ------------------------------------------------------------
    #  存读档：整个世界就是一份 JSON
    # ------------------------------------------------------------
    def dump(self) -> dict:
        return {"graph": self.graph.dump(), "player": self.player.data, "tick": self.clock.tick,
                "truth": self.truth.events, "beliefs": self.knowledge.beliefs, "known": self.knowledge.known,
                "secrets": self.knowledge.secrets,
                "pending": self.messenger.pending, "canon": self.canon, "done": self.done,
                "taint": sorted(self.taint), "seed": self.seed}

    @classmethod
    def from_dump(cls, d: dict) -> "World":
        return cls(Graph.load(d["graph"]), Blackboard(d["player"]), Clock(d["tick"]), Truth(d["truth"]),
                   Knowledge(d["beliefs"], d["known"], d["secrets"]), Messenger(d["pending"]), d["canon"], d["done"],
                   set(d["taint"]), d["seed"])

    def save(self, path, extra: dict | None = None):
        """整世界存档；extra 供上层附带自己的段落（如 Web 的回合记录），读档时被 from_dump 忽略。
        先写临时文件再原子替换：写到一半断电，旧档依然完好。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({**self.dump(), **(extra or {})}, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path) -> "World":
        return cls.from_dump(json.loads(Path(path).read_text("utf-8")))
