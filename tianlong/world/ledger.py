"""
[INPUT]: 依赖 world/graph 的 Graph（观察时读取真相）
[OUTPUT]: 对外提供 Truth（绝对真实账本）、Knowledge（玩家认知账本：信念 + 已知事件 + 已知隐情）、Messenger（消息延迟队列）、PUBLIC_KEYS
[POS]: world 层的双重账本；Truth 只追加，Knowledge 是玩家视角下的世界投影，Messenger 是两者之间唯一的时间差通道（亲历之事即时送达，不等传闻）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

PUBLIC_KEYS = ("status", "location", "title", "faction", "state", "holder")  # 江湖可传闻、可目睹的属性
NEWS_SPEED = 1.0  # 传闻每日扩散的道路距离（日）× 事件分量 weight


# ============================================================
#  绝对真实账本：世界上客观发生过的一切，按时间追加
# ============================================================
class Truth:
    def __init__(self, events: list | None = None):
        self.events: list[dict] = events or []

    def record(self, day: int, where: str, summary: str, effects: list, origin: str, weight: int = 1) -> dict:
        event = {"id": len(self.events), "day": day, "where": where, "summary": summary,
                 "effects": effects, "origin": origin, "weight": weight}
        self.events.append(event)
        return event

    def get(self, eid: int) -> dict:
        return self.events[eid]


# ============================================================
#  玩家认知账本：信念（node → 公开属性）+ 已知事件 + 已知隐情（secret 边）
# ============================================================
class Knowledge:
    def __init__(self, beliefs: dict | None = None, known: list | None = None, secrets: list | None = None):
        self.beliefs: dict[str, dict] = beliefs or {}
        self.known: list[int] = known or []
        self.secrets: list[list[str]] = secrets or []

    @classmethod
    def from_truth(cls, graph) -> "Knowledge":
        """开局常识：所有非隐秘节点的公开属性，但人物的隐秘字段(secret_fields，如诈死者的生死去处)不入常识。"""
        k = cls()
        k.observe(graph, [nid for nid, n in graph.nodes.items() if not n.get("hidden")])
        for nid, belief in k.beliefs.items():
            for key in graph.get(nid, "secret_fields") or []:
                belief.pop(key, None)
        return k

    def view(self, nid: str) -> dict:
        return self.beliefs.get(nid, {})

    def knows(self, nid: str) -> bool:
        return nid in self.beliefs

    def reveal(self, src: str, dst: str, rel: str):
        if [src, dst, rel] not in self.secrets:
            self.secrets.append([src, dst, rel])

    def knows_secret(self, edge: dict) -> bool:
        return [edge["src"], edge["dst"], edge["rel"]] in self.secrets

    def observe(self, graph, ids):
        """亲眼所见：直接以真相覆盖信念。"""
        for nid in ids:
            node = graph.nodes[nid]
            self.beliefs[nid] = {k: node.get(k) for k in PUBLIC_KEYS if k in node}

    def learn(self, event: dict):
        """传闻抵达：事件中的公开变更写入信念；只对少数人揭开的隐情(public=false)，唯有亲历者得知。"""
        if event["id"] in self.known:
            return
        self.known.append(event["id"])
        for op in event["effects"]:
            if op["op"] == "set" and op.get("id") != "player" and op["key"] in PUBLIC_KEYS:
                self.beliefs.setdefault(op["id"], {})[op["key"]] = op["value"]
            elif op["op"] == "reveal" and (event.get("public", True) or event.get("witnessed")):
                self.reveal(op["src"], op["dst"], op["rel"])


# ============================================================
#  消息延迟队列：传闻以 NEWS_SPEED×weight 的速度沿道路扩散，波前覆盖玩家所在节点即送达
#  以"波前半径"而非"预计到达日"建模，玩家移动途中也能被正确追上或迎上
# ============================================================
class Messenger:
    def __init__(self, pending: list | None = None):
        self.pending: list[int] = pending or []

    def post(self, event: dict):
        self.pending.append(event["id"])

    def deliver(self, truth: Truth, knowledge: Knowledge, dist: dict[str, int], today: int) -> list[dict]:
        arrived, waiting = [], []
        for eid in self.pending:
            event = truth.get(eid)
            reach = (today - event["day"]) * NEWS_SPEED * event["weight"]
            seen = event.get("witnessed") or dist.get(event["where"], float("inf")) <= reach  # 亲历之事不必等传闻
            (arrived if seen else waiting).append(event)
        self.pending = [e["id"] for e in waiting]
        for event in arrived:
            knowledge.learn(event)
        return arrived
