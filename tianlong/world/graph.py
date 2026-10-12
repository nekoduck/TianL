"""
[INPUT]: 依赖 heapq 做 Dijkstra
[OUTPUT]: 对外提供 Graph（节点属性读写、关系边增删、道路图：出路/道路边/距离/路线(可由调用方逐步过滤)、按属性查询）、matches()（属性判定口径）、holds()（前提判定：属性相符，或 ~关系 有、!关系 无）、ROAD、
          PLIGHT（剧情上的带伤之身：「某人负伤」的前提读它，不读随气血涨落的 status）
[POS]: world 层的内存图数据库，世界客观状态的唯一载体；Truth 账本只记"发生过什么"，"现在是什么"永远在这里。
       道路边可携带有向关口 gates（以去向为键），图只负责存与走，关口如何放行由 world/access 经 through 过滤器裁定；
       v5：剧情前提与体征分开——原著里四十余桩「某人负伤」的前提由 PLIGHT 承载，养伤只改气血，不再把原著主线养断
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import heapq

ROAD = "road"  # 道路是一种特殊的无向边，携带 days 权重，可带 gates：{去向: 通行条件}


def matches(cur, want) -> bool:
    """属性是否满足期望——原著前提与通行前提共用的口径：列表须含之；期望为字典时逐项相符，
    缺省的开关(exists/accessible…)视为 true（与 open 同一口径，地点 state 写成一句话即视为畅通）；其余须相等。"""
    if isinstance(cur, list) and not isinstance(want, list):
        return want in cur
    if isinstance(want, dict):
        cur = cur if isinstance(cur, dict) else {}
        return all(cur.get(k, True) == v for k, v in want.items())
    return cur == want


PLIGHT = "canon_wounded"  # 剧情上的「带伤之身」：由原著或明写的 status 立、由明写的痊愈或死亡消，不随气血涨落


def holds(graph, nid: str, key: str, want, cur=None) -> bool:
    """一条前提是否成立：[id, 属性, 期望] 属性相符；[src, "~关系", dst] 有此关系边；[src, "!关系", dst] 没有。
    原著的情境前提（钟灵仍被扣为人质）与未了之事的了结谓词共用这一口径。cur 可由调用方给出（主角属性在黑板上）。
    「某人负伤」是剧情前提，不是体征：气血养回八成五、status 翻回安好，只要剧情上的伤未被明写治好，前提照旧成立。"""
    if isinstance(key, str) and key[:1] in ("~", "!"):
        has = any(e["src"] == nid and e["dst"] == want and e["rel"] == key[1:] for e in graph.edges)
        return has if key[0] == "~" else not has
    if key == "status" and want == "wounded" and cur is None:
        status = graph.get(nid, "status")
        return status == "wounded" or (status != "dead" and bool(graph.get(nid, PLIGHT)))
    return matches(graph.get(nid, key) if cur is None else cur, want)


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
    #  道路拓扑：距离（日）与路线——消息延迟、LOD 分层与跋涉的度量衡
    #  through(a, b, edge) -> bool 逐步过滤：不给即纯地理（传闻、分层），给了即某人眼中可走的路（主角、场外人物）
    # ------------------------------------------------------------
    def open(self, loc: str) -> bool:
        """地点的 state 若声明 exists/accessible 为 false（地道未通、机关封闭），其道路即断。"""
        state = self.get(loc, "state")
        return not isinstance(state, dict) or (state.get("exists", True) and state.get("accessible", True))

    def road(self, a: str, b: str) -> dict | None:
        """a 与 b 之间的道路边（不论存储朝向）。"""
        return next((e for e in self.edges if e["rel"] == ROAD and {e["src"], e["dst"]} == {a, b}), None)

    def ways(self, loc: str, through=None) -> list[tuple[str, dict]]:
        """loc 出发的每一步：(去向, 道路边)；去向封闭或被 through 拦下者不计。"""
        out = []
        for e in self.edges:
            if e["rel"] == ROAD and loc in (e["src"], e["dst"]):
                other = e["dst"] if e["src"] == loc else e["src"]
                if self.open(other) and (through is None or through(loc, other, e)):
                    out.append((other, e))
        return out

    def roads(self, loc: str, through=None) -> list[tuple[str, int]]:
        return [(other, e["days"]) for other, e in self.ways(loc, through)]

    def _dijkstra(self, src: str, through=None) -> tuple[dict[str, int], dict[str, str]]:
        dist, prev, heap = {src: 0}, {}, [(0, src)]
        while heap:
            d, loc = heapq.heappop(heap)
            if d > dist[loc]:
                continue
            for nxt, days in self.roads(loc, through):
                if d + days < dist.get(nxt, 1 << 30):
                    dist[nxt], prev[nxt] = d + days, loc
                    heapq.heappush(heap, (d + days, nxt))
        return dist, prev

    def distances(self, src: str, through=None) -> dict[str, int]:
        return self._dijkstra(src, through)[0]

    def path(self, src: str, dst: str, through=None) -> list[str] | None:
        """src 到 dst 的最短路线（含两端）；不可达为 None。"""
        dist, prev = self._dijkstra(src, through)
        if dst not in dist:
            return None
        route = [dst]
        while route[-1] != src:
            route.append(prev[route[-1]])
        return route[::-1]

    # ------------------------------------------------------------
    #  持久化
    # ------------------------------------------------------------
    def dump(self) -> dict:
        return {"nodes": self.nodes, "edges": self.edges}

    @classmethod
    def load(cls, d: dict) -> "Graph":
        return cls(d["nodes"], d["edges"])
