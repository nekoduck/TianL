"""
[INPUT]: 依赖 world/graph 的 Graph（观察时读取真相）
[OUTPUT]: 对外提供 Truth（绝对真实账本）、Knowledge（玩家认知账本：信念 + 已知事件 + 已知隐情）、Messenger（消息延迟队列）、PUBLIC_KEYS、FAME / famous()
[POS]: world 层的双重账本；Truth 只追加，Knowledge 是玩家视角下的世界投影，Messenger 是两者之间唯一的时间差通道（亲历之事即时送达，不等传闻）。
       开局常识只含地理、门派与 FAME(名号显赫或四大恶人)之人——无名之辈的下落与器物所在不是江湖常识，要亲见或听闻才知；
       限定知情者之事（public=false）唯亲历可知，江湖无从传开；每个节点记着最新消息的日子(asof)，迟到的旧闻不盖新见；
       传闻要有传话的人(v5)：主角这一片一个人也没有(独处石洞)时，旁人的事在外头等着，见到人再听说；
       识名(v6，reveal 的 id 形)当场已由 effects 落给听见的人，不是隐情、不随传闻——事件里带着它也不误读
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import re

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
FAME = re.compile(r"掌门|帮主|谷主|庄主|宫主|岛主|尊主|方丈|首座|法王|王|帝|太子|世子|公子|盟主|恶|圣|宗主|大师|名医|阎王|神医|镖头|寨主|将军")


def famous(node: dict) -> bool:
    """江湖闻名：头衔是一派之主、王侯、名号响亮的恶人，或身属四大恶人——主角久仰其名，却未必认得其面。"""
    return bool(FAME.search(node.get("title") or "")) or node.get("faction") == "四大恶人"


class Knowledge:
    def __init__(self, beliefs: dict | None = None, known: list | None = None, secrets: list | None = None,
                 asof: dict | None = None):
        self.beliefs: dict[str, dict] = beliefs or {}
        self.known: list[int] = known or []
        self.secrets: list[list[str]] = secrets or []
        self.asof: dict[str, int] = asof or {}  # 节点 → 关于它最新一条消息的日子：迟到的旧闻不得覆盖新见

    @classmethod
    def from_truth(cls, graph) -> "Knowledge":
        """开局常识：地理、门派、武学之名，与江湖闻名之人(一派之主、王侯、四大恶人……)的公开属性；
        无名小卒与器物的下落不是常识，须亲眼见过或听来。人物的隐秘字段(secret_fields，如诈死者的生死去处)不入常识。"""
        k = cls()
        k.observe(graph, [nid for nid, n in graph.nodes.items() if not n.get("hidden")
                          and (n["type"] not in ("person", "item") or (n["type"] == "person" and famous(n)))])
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

    def observe(self, graph, ids, day: int | None = None):
        """亲眼所见：直接以真相覆盖信念，并记下这是哪一天的见闻（开局常识不记日子，任何消息都比它新）。"""
        for nid in ids:
            node = graph.nodes[nid]
            self.beliefs[nid] = {k: node.get(k) for k in PUBLIC_KEYS if k in node}
            if day is not None:
                self.asof[nid] = max(self.asof.get(nid, day), day)

    def learn(self, event: dict):
        """传闻抵达：事件中的公开变更写入信念；只对少数人揭开的隐情(public=false)，唯有亲历者得知。"""
        if event["id"] in self.known:
            return
        self.known.append(event["id"])
        for op in event["effects"]:
            if op["op"] == "set" and op.get("id") != "player" and op["key"] in PUBLIC_KEYS:
                if event["day"] < self.asof.get(op["id"], event["day"]):
                    continue  # 迟到的旧闻：主角后来亲眼见过、或已听到更新的消息
                self.beliefs.setdefault(op["id"], {})[op["key"]] = op["value"]
                self.asof[op["id"]] = event["day"]
            elif op["op"] == "reveal" and "src" in op and (event.get("public", True) or event.get("witnessed")):  # 识名(id 形)当场已落，不随传闻
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

    def deliver(self, truth: Truth, knowledge: Knowledge, dist: dict[str, int], today: int, listening: bool = True) -> list[dict]:
        """listening 为假(v5)：主角身边一个传话的人也没有(独处石洞)，传闻在外头等着——亲历之事照记，旁人的事等他见到人再听说。"""
        arrived, waiting = [], []
        for eid in self.pending:
            event = truth.get(eid)
            if not event.get("public", True) and not event.get("witnessed"):
                continue  # 限定知情者之事，江湖无从传开：主角不在场，便永不得闻
            reach = (today - event["day"]) * NEWS_SPEED * event["weight"]
            seen = event.get("witnessed") or (listening and dist.get(event["where"], float("inf")) <= reach)  # 亲历之事不必等传闻
            (arrived if seen else waiting).append(event)
        self.pending = [e["id"] for e in waiting]
        for event in arrived:
            knowledge.learn(event)
        return arrived
