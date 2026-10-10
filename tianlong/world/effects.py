"""
[INPUT]: 依赖 World 门面的 graph / player / knowledge / here / taint（鸭子类型）
[OUTPUT]: 对外提供 apply()（规整→校验→落账剧情后果）、place()（任一节点此刻所在之地）、usable()、OPS、STATUSES
[POS]: world 层唯一的写入通道——LLM 创造的是剧情，剧情的后果经此作用于既有世界：
       人物生死伤病、去留、恩怨、武学、主角的得失与行止、器物易手、隐情的揭开。
       地理与器物属于基础设施：没有任何"新造"指令；地点/景物只可改 state，器物只可改流转属性(location/holder/hidden/state)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

# ============================================================
#  指令集（只作用于既有实体）
#    set/add/push/pull : 改人物、门派、器物流转或主角(id="player")的属性；地点与景物只可改 state
#    link/unlink       : 增删关系边（恩怨、结义、师承……可带 secret）
#    reveal            : 让主角得知一条既有隐情
# ============================================================
OPS = {"set", "add", "push", "pull", "link", "unlink", "reveal"}
STATUSES = {"alive", "wounded", "dead"}
FROZEN_PLAYER_KEYS = {"name", "journal", "max_hp"}
PLAYER_ALIASES = {"姿态": "posture", "气血": "hp", "功力": "power", "物品": "inventory", "随身": "inventory",
                  "武学": "skills", "武功": "skills", "位置": "location", "所在": "location"}
TERRAIN = {"location", "feature"}               # 地理：定义由创世数据给出，剧情只能改变其现状(state)
ITEM_FLOW = {"location", "holder", "hidden", "state"}  # 器物：定义不可改，只可流转、显隐、损耗
OFFSCREEN = {"lod1", "chronicle"}                # 场外推演：主角不在场，碰不到主角本人


def _ids(op) -> list[str]:
    return [op.get("src"), op.get("dst")] if op["op"] in ("link", "unlink", "reveal") else [op.get("id")]


def place(world, nid: str) -> str | None:
    """任一节点此刻所在之地：地点即自身；器物随持有者走；主角在 here。"""
    g = world.graph
    if nid == "player":
        return world.here
    if g.kind(nid) == "location":
        return nid
    if g.kind(nid) == "item" and g.get(nid, "holder"):
        return place(world, g.get(nid, "holder"))
    return g.get(nid, "location")


def usable(world, item: str) -> bool:
    state = world.graph.get(item, "state")
    return not isinstance(state, dict) or (state.get("exists", True) and state.get("available", True))


# ------------------------------------------------------------
#  规整：替 LLM 消化不影响语义的写法差异
# ------------------------------------------------------------
def _normalize(world, op):
    g = world.graph
    if op.get("id") == "player":
        op["key"] = PLAYER_ALIASES.get(op.get("key"), op.get("key"))
    if op.get("op") == "set" and op.get("key") == "location" and g.kind(op.get("id")) != "item" \
            and g.kind(op.get("value")) not in ("location", None):
        op["value"] = place(world, op["value"])  # 走向某人/某物 = 走向其所在之地


# ------------------------------------------------------------
#  世界物理：与来源无关的一致性
# ------------------------------------------------------------
def _physics(world, op) -> str | None:
    g, kind = world.graph, op["op"]
    if kind in ("link", "unlink", "reveal"):
        if not all(isinstance(op.get(k), str) for k in ("src", "dst", "rel")):
            return "关系边缺字段"
        if not all(i == "player" or g.has(i) for i in _ids(op)):
            return "关系端点不在世界中"
        if kind == "reveal" and not any(e["src"] == op["src"] and e["dst"] == op["dst"] and e["rel"] == op["rel"]
                                        for e in g.edges):
            return "要揭露的隐情并不存在"
        return None

    nid, key, value = op.get("id"), op.get("key"), op.get("value")
    if nid != "player" and not g.has(nid):
        return f"「{nid}」不在世界中"
    if not isinstance(key, str):
        return "缺少 key"
    if nid == "player" and (key not in world.player.data or key in FROZEN_PLAYER_KEYS):
        return f"玩家属性「{key}」不可写"
    if g.kind(nid) == "item" and key not in ITEM_FLOW:
        return f"器物由系统掌管，{nid}的定义不可改"
    if g.kind(nid) in TERRAIN and key != "state":
        return f"地理由系统掌管，{nid}只可改变现状(state)"
    if g.kind(nid) == "skill":
        return f"武学由系统掌管，{nid}的定义不可改"
    if kind == "add" and not isinstance(value, (int, float)):
        return "add 需要数值"
    if kind == "set" and key == "status":
        if value not in STATUSES:
            return f"非法状态:{value}"
        if g.get(nid, "status") == "dead" and value != "dead":
            return f"{nid}已死，死者不能复生"
    if kind == "set" and key == "location" and value is not None:
        if g.kind(value) != "location":
            return f"世上没有「{value}」这个地方"
        if nid == "player" and value not in g.distances(world.here):
            return f"{value}与此地不相通"
    if kind == "set" and key == "holder" and value is not None and value != "player" and g.kind(value) != "person":
        return f"「{value}」不是人，无法持有器物"
    if kind in ("push", "pull") and key == "skills" and g.kind(value) != "skill":
        return f"世上没有「{value}」这门武学"
    if nid == "player" and key == "inventory" and kind in ("push", "pull"):
        if g.kind(value) != "item":
            return f"世上没有「{value}」这件器物"
        if kind == "push" and value not in world.player["inventory"]:
            if not usable(world, value):
                return f"{value}已不复存在"
            if place(world, value) != world.here:
                return f"{value}不在此地，够不着"
    return None


# ------------------------------------------------------------
#  在场性：谁能碰到谁
# ------------------------------------------------------------
def _reach(world, op, origin, scope) -> str | None:
    if op["op"] == "reveal" and origin in OFFSCREEN:
        return "主角不在场，无从得知隐情"
    if origin == "canon" or op["op"] in ("link", "unlink", "reveal"):
        return None
    g, nid = world.graph, op.get("id")
    where = place(world, nid)
    if origin == "director":
        if nid == "player" or g.kind(nid) == "faction":
            return None
        if g.get(nid, "dormant"):
            return f"{nid}不在当下的江湖中"
        if op.get("key") == "holder" and op.get("value") not in (None, "player") \
                and place(world, op["value"]) != world.here:
            return f"{op['value']}不在此地，接不过{nid}"
        return None if where == world.here else f"{nid}不在此地，主角够不着"
    if origin in OFFSCREEN:
        if nid == "player" or op.get("value") == "player":
            return "场外推演不得改动主角本人"
        if scope is not None and nid not in scope and where not in scope:
            return f"{nid}不在推演区域内"
        if origin == "lod1" and op.get("key") == "location" and op["value"] not in {n for n, _ in g.roads(where)}:
            return "一日之内只能移动到相邻地点"
        return None
    return f"未知来源:{origin}"


def _exec(world, op):
    g, kind = world.graph, op["op"]
    if kind == "link":
        g.link(op["src"], op["dst"], op["rel"], **({"secret": True} if op.get("secret") else {}))
    elif kind == "unlink":
        g.unlink(op["src"], op["dst"], op["rel"])
    elif kind == "reveal":
        world.knowledge.reveal(op["src"], op["dst"], op["rel"])
    elif op["id"] == "player":
        getattr(world.player, kind)(op["key"], op["value"])
        if op["key"] == "inventory":  # 随身则归主角，丢下则落地
            item = g.nodes[op["value"]]
            item.update({"holder": "player", "location": None, "hidden": False} if kind == "push"
                        else {"holder": None, "location": world.here})
    else:
        node, key, value = g.nodes[op["id"]], op["key"], op["value"]
        if node.get("type") == "item" and key == "holder" and node.get("holder") == "player" and value != "player":
            world.player.pull("inventory", op["id"])  # 器物从主角手中易主
        if kind == "set":
            node[key] = value
        elif kind == "add":
            node[key] = node.get(key, 0) + value
        elif kind == "push" and value not in node.setdefault(key, []):
            node[key].append(value)
        elif kind == "pull" and value in node.get(key, []):
            node[key].remove(value)


def apply(world, ops: list, origin: str, scope: set | None = None) -> tuple[list, list]:
    """逐条落账；返回 (已成立, [(未成立的指令, 原因)])。导演触碰过的节点记为因果污染。"""
    applied, rejected = [], []
    for op in ops or []:
        if not isinstance(op, dict) or op.get("op") not in OPS:
            rejected.append((op, "未知指令"))
            continue
        try:
            _normalize(world, op)
            reason = _physics(world, op) or _reach(world, op, origin, scope)
        except (TypeError, AttributeError, KeyError):  # 畸形值（如列表当 id）：单条不成立，游戏不崩
            reason = "格式不可解"
        if reason:
            rejected.append((op, reason))
            continue
        _exec(world, op)
        applied.append(op)
        if origin == "director":
            world.taint.update(i for i in _ids(op) if i and i != "player")
    return applied, rejected
