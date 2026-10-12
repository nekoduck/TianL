"""
[INPUT]: 依赖 world/ 下 genesis(原著硬知识)、graph、clock、blackboard、ledger、effects、rag、perspective(开局相识) 全部基础设施
[OUTPUT]: 对外提供 World 门面（create 创世(含出身、道路挂上有向关口) / 写入 / 记事(可盖指定日戳) / 推进时间 / 同步认知 / 原子存档与读档 /
          remap 以当前舆图重绘地理 / witness 导演后果当场入认知），持有 aliases 别名表与 turn（本回合的瞬时账：谁被哪处调遣过、谁赶来、回合开始时身边有谁、连带说明——不入存档）
[POS]: world 层的聚合根——上层（engine）只与 World 对话；它把"变更→记账→传闻→观察"串成唯一的状态流水线。
       存档只存现状、地理随数据走：读档即以当前创世数据重绘地点定义、道路关口、关系的静态标注(secret/revealed_by)与别名，旧档自动用上新地图；
       开局即播下相识(出身带来的人互相识名、当众主持的掌门主角识名)，旧档以已与主角结下关系之人补种；主角名号不得与书中人物、地名、别名重名——否则剧情里写到这个名字，系统分不清是谁
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import os
from pathlib import Path

from . import effects, genesis, perspective, rag
from .blackboard import ORIGINS, Blackboard
from .clock import Clock
from .graph import ROAD, Graph
from .ledger import Knowledge, Messenger, Truth


def _lay(graph: Graph, d: dict):
    """道路铺上图，有向关口挂在道路边上、以去向为键。"""
    for a, b, days in d["roads"]:
        graph.link(a, b, ROAD, days=days)
    for a, b, gate in d.get("gates", []):
        graph.road(a, b).setdefault("gates", {})[b] = gate


class World:
    def __init__(self, graph, player, clock, truth, knowledge, messenger, canon, done, taint, seed, aliases=None):
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
        self.aliases: dict[str, str] = aliases or {}  # 别名→id：LLM 写「萧峰」「乔帮主」亦能落到乔峰
        self.turn: dict = {}                # 本回合的瞬时账（谁被谁挪动过、谁到场、连带说明）——不入存档

    # ------------------------------------------------------------
    #  创世：以原著硬知识(genesis)为蓝本；data 可注入，便于测试
    # ------------------------------------------------------------
    @classmethod
    def create(cls, name: str | None = None, data: dict | None = None, origin: str | None = None) -> "World":
        d = data or genesis.load()
        if name and (name in d["nodes"] or name in (d.get("aliases") or {}) or name in ("player", "主角")):
            raise ValueError(f"「{name}」已是书中的人名或地名，请另取一个名号")
        birth = ORIGINS.get(origin) or next(iter(ORIGINS.values()))  # 出身：主角为何在此、为何而动
        graph = Graph(d["nodes"])
        _lay(graph, d)
        for r in d["relations"]:
            graph.link(**r)
        player = Blackboard({**d["player"], **birth, **({"name": name} if name else {})})
        world = cls(graph, player, Clock(d["start_tick"]), Truth(), Knowledge.from_truth(graph),
                    Messenger(), d["canon"], [], set(), d["seed"], d.get("aliases"))
        perspective.seed(world)
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
               public: bool = True, day: int | None = None, witnessed: bool | None = None) -> dict:
        """写入绝对真实账本，并把传闻投进消息队列；主角身在事发之地即为亲历者（亦可明说，如主角做完便离开的事）。
        day 缺省为今日，原著事件传其排定之日。"""
        event = self.truth.record(self.clock.day if day is None else day, where, summary, applied, origin, weight)
        event.update(public=public, witnessed=where == self.here if witnessed is None else witnessed)
        self.messenger.post(event)
        return event

    def witness(self, ops: list):
        """导演写下的后果都发生在主角眼前：其中的公开变化当场入认知——即便主角随即离开，也记得刚才所见。隐匿者不因此现形。"""
        g = self.graph
        seen = {op.get("id") for op in ops} - {None, "player"}
        self.knowledge.observe(g, sorted(n for n in seen if g.has(n) and not g.get(n, "hidden")), self.clock.day)

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
        self.knowledge.observe(self.graph, seen, self.clock.day)

    # ------------------------------------------------------------
    #  存读档：整个世界就是一份 JSON
    # ------------------------------------------------------------
    def dump(self) -> dict:
        return {"graph": self.graph.dump(), "player": self.player.data, "tick": self.clock.tick,
                "truth": self.truth.events, "beliefs": self.knowledge.beliefs, "known": self.knowledge.known,
                "secrets": self.knowledge.secrets, "asof": self.knowledge.asof,
                "pending": self.messenger.pending, "canon": self.canon, "done": self.done,
                "taint": sorted(self.taint), "seed": self.seed, "aliases": self.aliases}

    @classmethod
    def from_dump(cls, d: dict, atlas: dict | None = None) -> "World":
        """读档：现状取自存档，地理取自当前创世数据（atlas 可注入，便于测试）。"""
        world = cls(Graph.load(d["graph"]), Blackboard(d["player"]), Clock(d["tick"]), Truth(d["truth"]),
                    Knowledge(d["beliefs"], d["known"], d.get("secrets"), d.get("asof")), Messenger(d["pending"]), d["canon"], d["done"],
                    set(d["taint"]), d["seed"], d.get("aliases"))
        world.remap(atlas or genesis.load())
        if "acquaintances" not in d["player"]:  # 旧档没有识名账：出身里的人与已有交情的人算作相识
            perspective.seed(world, {e["src"] if e["dst"] == "player" else e["dst"] for e in world.graph.edges
                                     if "player" in (e["src"], e["dst"])} - {"player"})
        return world

    def remap(self, atlas: dict):
        """以当前舆图重绘地理：地点定义、道路与关口、别名换成创世数据，地点现状(state)与剧情所致的一切照存档保留。
        旧档由此用上新地图；道路补丁只在创世时打一次，存档从不重放补丁，重绘多少次都是同一张图。"""
        g = self.graph
        for nid, node in atlas["nodes"].items():
            if node["type"] != "location":
                continue
            kept = g.nodes.get(nid)
            g.nodes[nid] = {**node, **({"state": kept["state"]} if kept and "state" in kept else {})}
            if kept is None:  # 新入图的地点进入常识，与开局时一样
                self.knowledge.observe(g, [nid])
        roads = Graph(g.nodes)
        _lay(roads, atlas)
        g.edges = roads.edges + [e for e in g.edges if e["rel"] != ROAD]
        marks = {(r["src"], r["dst"], r["rel"]): r for r in atlas.get("relations", [])}
        for e in g.edges:  # 关系的静态标注随数据走：旧档里缺了 revealed_by，第四十八回的隐情就会在第一回摆上桌
            r = marks.get((e["src"], e["dst"], e["rel"]))
            if r:
                e.update({k: r[k] for k in ("secret", "revealed_by") if k in r})
        self.aliases = atlas.get("aliases") or self.aliases

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
