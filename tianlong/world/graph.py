"""
[INPUT]: 依赖 heapq 做 Dijkstra
[OUTPUT]: 对外提供 Graph（节点属性读写、关系边增删、道路图距离/跳数(尊重地点 state 的通断)、按属性查询）
[POS]: world 层的内存图数据库，世界客观状态的唯一载体；Truth 账本只记"发生过什么"，"现在是什么"永远在这里
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import heapq
from collections import deque

ROAD = "road"  # 道路是一种特殊的无向边，携带 days 权重


class Graph:
    def __init__(self, nodes: dict | None = None, edges: list | None = None):
        self.nodes: dict[str, dict] = nodes or {}
        self.edges: list[dict] = edges or []

    # ------------------------------------------------------------
    #  节点
    # ------------------------------------------------------------
    def has(self, nid) -> bool:
        return nid in self.nodes

    def get(self, nid: str, key: str, default=None):
        return self.nodes.get(nid, {}).get(key, default)

    def set(self, nid: str, key: str, value):
        self.nodes[nid][key] = value

    def kind(self, nid: str) -> str | None:
        return self.get(nid, "type")

    def where(self, **cond) -> list[str]:
        return [nid for nid, n in self.nodes.items() if all(n.get(k) == v for k, v in cond.items())]

    # ------------------------------------------------------------
    #  关系边（有向；道路边视作无向）
    # ------------------------------------------------------------
    def _find(self, src, dst, rel):
        return next((e for e in self.edges if e["src"] == src and e["dst"] == dst and e["rel"] == rel), None)

    def link(self, src: str, dst: str, rel: str, **attrs):
        edge = self._find(src, dst, rel)
        if edge:
            edge.update(attrs)
        else:
            self.edges.append({"src": src, "dst": dst, "rel": rel, **attrs})

    def unlink(self, src: str, dst: str, rel: str):
        self.edges = [e for e in self.edges if not (e["src"] == src and e["dst"] == dst and e["rel"] == rel)]

    def relations(self, nid: str) -> list[dict]:
        return [e for e in self.edges if e["rel"] != ROAD and nid in (e["src"], e["dst"])]

    # ------------------------------------------------------------
    #  道路拓扑：距离（日）与跳数——消息延迟与 LOD 分层的度量衡
    # ------------------------------------------------------------
    def open(self, loc: str) -> bool:
        """地点的 state 若声明 exists/accessible 为 false（地道塌毁、机关封闭），其道路即断。"""
        state = self.get(loc, "state")
        return not isinstance(state, dict) or (state.get("exists", True) and state.get("accessible", True))

    def roads(self, loc: str) -> list[tuple[str, int]]:
        out = []
        for e in self.edges:
            if e["rel"] == ROAD and loc in (e["src"], e["dst"]):
                other = e["dst"] if e["src"] == loc else e["src"]
                if self.open(other):
                    out.append((other, e["days"]))
        return out

    def distances(self, src: str) -> dict[str, int]:
        dist, heap = {src: 0}, [(0, src)]
        while heap:
            d, loc = heapq.heappop(heap)
            if d > dist[loc]:
                continue
            for nxt, days in self.roads(loc):
                if d + days < dist.get(nxt, 1 << 30):
                    dist[nxt] = d + days
                    heapq.heappush(heap, (d + days, nxt))
        return dist

    def hops(self, src: str) -> dict[str, int]:
        seen, queue = {src: 0}, deque([src])
        while queue:
            loc = queue.popleft()
            for nxt, _ in self.roads(loc):
                if nxt not in seen:
                    seen[nxt] = seen[loc] + 1
                    queue.append(nxt)
        return seen

    # ------------------------------------------------------------
    #  持久化
    # ------------------------------------------------------------
    def dump(self) -> dict:
        return {"nodes": self.nodes, "edges": self.edges}

    @classmethod
    def load(cls, d: dict) -> "Graph":
        return cls(d["nodes"], d["edges"])
