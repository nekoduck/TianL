"""
[INPUT]: 依赖 heapq 做 Dijkstra
[OUTPUT]: 对外提供 Graph（节点属性读写、关系边增删、道路图：出路/道路边/距离/路线(可由调用方逐步过滤)、按属性查询(of 一类、where 按类型与所在/持有走索引、order 排回创世次序)、stamp 戳记与 memo 缓存）、INDEXED、matches()（属性判定口径）、holds()（前提判定：属性相符，或 ~关系 有、!关系 无）、ROAD、
          PLIGHT（剧情上的带伤之身：「某人负伤」的前提读它，不读随气血涨落的 status）
[POS]: world 层的内存图数据库，世界客观状态的唯一载体；Truth 账本只记"发生过什么"，"现在是什么"永远在这里。
       道路边可携带有向关口 gates（以去向为键），图只负责存与走，关口如何放行由 world/access 经 through 过滤器裁定；
       v5：剧情前提与体征分开——原著里四十余桩「某人负伤」的前提由 PLIGHT 承载，养伤只改气血，不再把原著主线养断
       v11 索引：世界底座让图从六百多个节点长到上千(城坊、场所、按需布置的房间伙计货品)，查询不再每次扫一遍全图——
       节点表与边表是记着版本的容器(谁往里加、删、整个换掉都让版本加一)，按类型的节点清单、道路邻接表、关系边的查找表与每个节点的关系边都按版本惰性重建；
       节点的属性就地改不影响类型、边的属性就地改不影响两端与关系名，所以索引只在结构变了时才作废；深拷贝只拷数据，索引在副本上重建；
       节点的属性表是 _Node：location/holder 改了就地挪动属性索引(where(location=…)/where(holder=…) 只看那一处、那一人，结果仍按创世次序)，
       任何属性改动都让戳记 stamp 变——memo 是调用方按戳记作废的缓存(近旁、名表)，不入存档、深拷贝不带；order 把索引取出的一把节点排回创世次序；
       link 新添一条边就地记进索引(创世铺上千条路不必每条重建)，道路按两端查找表认
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
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
        has = graph._find(nid, want, key[1:]) is not None
        return has if key[0] == "~" else not has
    if key == "status" and want == "wounded" and cur is None:
        status = graph.get(nid, "status")
        return status == "wounded" or (status != "dead" and bool(graph.get(nid, PLIGHT)))
    return matches(graph.get(nid, key) if cur is None else cur, want)


INDEXED = ("location", "holder")  # 按值建索引的属性(v11)：某处有谁有什么、某人手里有什么——查一处、一人不必扫一类


class _Node(dict):
    """一个节点的属性表(v11)：改了 location/holder 即就地挪动图的属性索引，改了类型即让类型索引作废；
    任何属性改动都让图的戳记加一(近旁之类的查询据此缓存)。深拷贝与序列化只当它是个寻常字典。"""
    __slots__ = ("_owner", "_id")

    def __init__(self, data, owner, nid):
        super().__init__(data)
        self._owner, self._id = owner, nid

    def __setitem__(self, k, v):
        self._owner._touch(self, k, v)
        super().__setitem__(k, v)

    def __delitem__(self, k):
        self._owner._touch(self, k, None)
        super().__delitem__(k)

    def pop(self, k, *default):
        if k in self:
            self._owner._touch(self, k, None)
        return super().pop(k, *default)

    def popitem(self):
        k = next(reversed(self))
        return k, self.pop(k)

    def setdefault(self, k, v=None):
        if k not in self:
            self[k] = v
        return self[k]

    def update(self, *a, **kw):
        for k, v in dict(*a, **kw).items():
            self[k] = v

    def __ior__(self, other):
        self.update(other)
        return self

    def clear(self):
        for k in list(self):
            del self[k]

    def __reduce_ex__(self, protocol):
        return dict, (dict(self),)


class _Table(dict):
    """节点表：增、删、整个换值都让图的版本加一(属性就地改不算——经 _Node 就地更新索引)；存进来的属性表一律换成 _Node。"""

    def __init__(self, data, owner):
        super().__init__((k, owner._wrap(k, v)) for k, v in data.items())
        self._owner = owner

    def _bump(self):
        self._owner._version += 1

    def __setitem__(self, k, v):
        super().__setitem__(k, self._owner._wrap(k, v))
        self._bump()

    def __delitem__(self, k):
        super().__delitem__(k)
        self._bump()

    def pop(self, *a):
        out = super().pop(*a)
        self._bump()
        return out

    def popitem(self):
        out = super().popitem()
        self._bump()
        return out

    def setdefault(self, k, v=None):
        if k not in self:
            self[k] = v
        return self[k]

    def update(self, *a, **kw):
        for k, v in dict(*a, **kw).items():
            super().__setitem__(k, self._owner._wrap(k, v))
        self._bump()

    def clear(self):
        super().clear()
        self._bump()

    def __reduce_ex__(self, protocol):  # 深拷贝与序列化只当它是个寻常字典
        return dict, (dict(self),)


class _Edges(list):
    """边表：增、删、改顺序都让边的版本加一(边的属性就地改不算——两端与关系名不变)。"""

    def __init__(self, data, owner):
        super().__init__(data)
        self._owner = owner

    def _bump(self):
        self._owner._edge_version += 1

    def __reduce_ex__(self, protocol):
        return list, (list(self),)


def _bumping(name):
    base = getattr(list, name)

    def method(self, *a, **kw):
        out = base(self, *a, **kw)
        self._bump()
        return out
    method.__name__ = name
    return method


for _name in ("append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse", "__setitem__", "__delitem__", "__iadd__"):
    setattr(_Edges, _name, _bumping(_name))

_LOOSE = object()  # 属性值不可散列(写成了列表之类)的节点：查这一属性时一律在候选之列


def _file(bucket: dict, nid: str, value):
    try:
        bucket.setdefault(value, {})[nid] = None
    except TypeError:
        bucket.setdefault(_LOOSE, {})[nid] = None


def _unfile(bucket: dict, nid: str, value):
    try:
        bucket.get(value, {}).pop(nid, None)
    except TypeError:
        bucket.get(_LOOSE, {}).pop(nid, None)


class Graph:
    def __init__(self, nodes: dict | None = None, edges: list | None = None):
        self._version = self._edge_version = self._stamp = 0
        self._types: tuple[int, dict, dict] = (-1, {}, {})  # 版本 → {类型: [节点 id，按插入次序]}、{节点 id: 插入次序}
        self._attrs: tuple[int, dict] = (-1, {})            # 版本 → {属性: {值: {节点 id}}}，属性就地改时就地挪动
        self._edge_index: tuple[int, dict, dict, dict] = (-1, {}, {}, {})  # 版本 → 道路邻接表、关系边查找表、每个节点的关系边
        self.memo: dict = {}                                # 调用方按 stamp 作废的缓存(近旁)：深拷贝不带
        self.nodes = nodes or {}
        self.edges = edges or []

    @property
    def nodes(self) -> dict[str, dict]:
        return self._nodes

    @nodes.setter
    def nodes(self, value):
        self._nodes = value if isinstance(value, _Table) and value._owner is self else _Table(value, self)
        self._version += 1

    @property
    def edges(self) -> list[dict]:
        return self._edges

    @edges.setter
    def edges(self, value):
        self._edges = value if isinstance(value, _Edges) and value._owner is self else _Edges(value, self)
        self._edge_version += 1

    @property
    def stamp(self) -> tuple[int, int, int]:
        """图的戳记：结构、边、任何属性改动都让它变——调用方据此作废缓存。"""
        return self._version, self._edge_version, self._stamp

    def _wrap(self, nid, node):
        if isinstance(node, _Node) and node._owner is self and node._id == nid:
            return node
        return _Node(node, self, nid) if isinstance(node, dict) else node

    def _touch(self, node: _Node, k, new):
        self._stamp += 1
        if k == "type":
            if node.get("type") != new:
                self._version += 1
        elif k in INDEXED:
            version, index = self._attrs
            if version == self._version and self._nodes.get(node._id) is node:
                _unfile(index[k], node._id, node.get(k))
                _file(index[k], node._id, new)

    def __deepcopy__(self, memo):
        new = Graph()
        memo[id(self)] = new
        table = {}
        for nid, n in self._nodes.items():
            c = _Node({k: copy.deepcopy(v, memo) for k, v in n.items()}, new, nid) if isinstance(n, dict) else copy.deepcopy(n, memo)
            memo[id(n)] = c
            table[nid] = c
        new.nodes = table
        new.edges = copy.deepcopy(list(self._edges), memo)
        return new

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

    def _ranked(self) -> tuple[dict, dict]:
        version, index, rank = self._types
        if version != self._version:
            index, rank = {}, {}
            for i, (nid, n) in enumerate(self._nodes.items()):
                index.setdefault(n.get("type") if isinstance(n, dict) else None, []).append(nid)
                rank[nid] = i
            self._types = (self._version, index, rank)
        return index, rank

    def of(self, kind: str) -> list[str]:
        """某一类的全部节点 id(按插入次序)：按版本惰性重建的类型索引——人物、器物再多，查一类也不必扫全图。"""
        return self._ranked()[0].get(kind, [])

    def order(self, ids) -> list[str]:
        """按创世(插入)次序排好：从索引里取出的一把节点，排得与扫一遍全图时一样。"""
        rank = self._ranked()[1]
        return sorted((i for i in ids if i in rank), key=rank.__getitem__)

    def _bucket(self, key: str, value) -> list[str] | None:
        """属性 key 等于 value 的候选节点(按插入次序)；value 不可散列即 None(调用方退回逐个看)。"""
        version, index = self._attrs
        if version != self._version:
            index = {k: {} for k in INDEXED}
            for nid, n in self._nodes.items():
                if isinstance(n, dict):
                    for k in INDEXED:
                        _file(index[k], nid, n.get(k))
            self._attrs = (self._version, index)
        try:
            hits = [*index[key].get(value, ()), *index[key].get(_LOOSE, ())]
        except TypeError:
            return None
        rank = self._ranked()[1]
        return sorted(hits, key=rank.__getitem__)

    def where(self, **cond) -> list[str]:
        nodes, pools = self._nodes, []
        if "type" in cond:
            pools.append(self.of(cond["type"]))
        for k in INDEXED:
            if k in cond:
                hits = self._bucket(k, cond[k])
                if hits is not None:
                    pools.append(hits)
        pool = min(pools, key=len) if pools else nodes
        return [nid for nid in pool if all(nodes[nid].get(k) == v for k, v in cond.items())]

    # ------------------------------------------------------------
    #  关系边（有向；道路边视作无向）
    # ------------------------------------------------------------
    @staticmethod
    def _file_edge(adj: dict, pairs: dict, rels: dict, e: dict):
        if e["rel"] == ROAD:
            adj.setdefault(e["src"], []).append(e)
            adj.setdefault(e["dst"], []).append(e)
            pairs.setdefault((ROAD, frozenset((e["src"], e["dst"]))), e)
        else:
            pairs.setdefault((e["src"], e["dst"], e["rel"]), e)
            rels.setdefault(e["src"], []).append(e)
            if e["dst"] != e["src"]:
                rels.setdefault(e["dst"], []).append(e)

    def _index(self) -> tuple[dict, dict, dict]:
        version, adj, pairs, rels = self._edge_index
        if version != self._edge_version:
            adj, pairs, rels = {}, {}, {}
            for e in self._edges:
                self._file_edge(adj, pairs, rels, e)
            self._edge_index = (self._edge_version, adj, pairs, rels)
        return adj, pairs, rels

    def _find(self, src, dst, rel):
        if rel == ROAD:  # 道路按两端认(不论朝向)，再看存储朝向是否一致
            e = self._index()[1].get((ROAD, frozenset((src, dst))))
            return e if e is not None and e["src"] == src and e["dst"] == dst else None
        return self._index()[1].get((src, dst, rel))

    def link(self, src: str, dst: str, rel: str, **attrs):
        edge = self._find(src, dst, rel)
        if edge:
            edge.update(attrs)
            return
        edge = {"src": src, "dst": dst, "rel": rel, **attrs}
        version, adj, pairs, rels = self._edge_index
        fresh = version == self._edge_version
        self.edges.append(edge)
        if fresh:  # 新添一条边就地记进索引，不必整个重建(创世时连铺上千条路)
            self._file_edge(adj, pairs, rels, edge)
            self._edge_index = (self._edge_version, adj, pairs, rels)

    def unlink(self, src: str, dst: str, rel: str):
        self.edges = [e for e in self.edges if not (e["src"] == src and e["dst"] == dst and e["rel"] == rel)]

    def relations(self, nid: str) -> list[dict]:
        return list(self._index()[2].get(nid, ()))

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
        return self._index()[1].get((ROAD, frozenset((a, b))))

    def _roadmap(self) -> dict[str, list[dict]]:
        """道路的邻接表(按边的登记次序)：按边的版本惰性重建——关系边、道路增删都让它作废，道路属性就地改不影响。"""
        return self._index()[0]

    def ways(self, loc: str, through=None, adj=None) -> list[tuple[str, dict]]:
        """loc 出发的每一步：(去向, 道路边)；去向封闭或被 through 拦下者不计。"""
        out = []
        for e in (adj if adj is not None else self._roadmap()).get(loc, ()):
            other = e["dst"] if e["src"] == loc else e["src"]
            if self.open(other) and (through is None or through(loc, other, e)):
                out.append((other, e))
        return out

    def roads(self, loc: str, through=None, adj=None) -> list[tuple[str, int]]:
        return [(other, e["days"]) for other, e in self.ways(loc, through, adj)]

    def _dijkstra(self, src: str, through=None) -> tuple[dict[str, int], dict[str, str]]:
        dist, prev, heap, adj = {src: 0}, {}, [(0, src)], self._roadmap()
        while heap:
            d, loc = heapq.heappop(heap)
            if d > dist[loc]:
                continue
            for nxt, days in self.roads(loc, through, adj):
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
