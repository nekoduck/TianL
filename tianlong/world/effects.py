"""
[INPUT]: 依赖 world/world 的 World 门面（graph / player / taint），仅鸭子类型访问
[OUTPUT]: 对外提供 apply()（校验并执行变更指令）、validate()、OPS、STATUSES
[POS]: world 层唯一的写入通道——规则、原著、LOD1 推演、LOD2 史官的所有变更都必须以这套 6 指令 DSL 表达，
       并按来源 origin 的策略过滤；LLM 产出的变更在这里被"框住"
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

# ============================================================
#  指令集：set/add/push/pull 作用于节点或玩家(id="player")，link/unlink 作用于关系边
# ============================================================
OPS = {"set", "add", "push", "pull", "link", "unlink"}
STATUSES = {"alive", "wounded", "dead"}
LOD1_KEYS = {"location", "mood"}
CHRONICLE_KEYS = {"status", "location", "title", "faction", "state", "mood", "hidden", "power"}


def _ids(op) -> list[str]:
    return [op["src"], op["dst"]] if op["op"] in ("link", "unlink") else [op.get("id")]


def _basic(world, op) -> str | None:
    """与来源无关的结构与世界一致性校验。"""
    if not isinstance(op, dict) or op.get("op") not in OPS:
        return "未知指令"
    g = world.graph
    if op["op"] in ("link", "unlink"):
        if not all(isinstance(op.get(k), str) for k in ("src", "dst", "rel")):
            return "关系边缺字段"
        return None if all(i == "player" or g.has(i) for i in _ids(op)) else "关系端点不存在"
    nid, key = op.get("id"), op.get("key")
    if nid != "player" and not g.has(nid):
        return f"节点不存在:{nid}"
    if not isinstance(key, str):
        return "缺少 key"
    if nid == "player" and key not in world.player.data:
        return f"玩家无此属性:{key}"
    value = op.get("value")
    if op["op"] == "set" and key == "status" and value not in STATUSES:
        return f"非法状态:{value}"
    if op["op"] == "set" and key == "location":
        if value is None and (nid == "player" or g.kind(nid) == "person"):
            return "人物必须身处某地"
        if value is not None and g.kind(value) != "location":
            return f"非法地点:{value}"
    if op["op"] == "add" and not isinstance(op.get("value"), (int, float)):
        return "add 需要数值"
    return None


# ============================================================
#  来源策略：越远离"确定性规则"的来源，权限越窄
# ============================================================
def _policy(world, op, origin: str, scope: set | None) -> str | None:
    if origin == "rules":
        return None
    if "player" in _ids(op):
        return f"{origin} 不得改动玩家"
    if origin == "canon":
        return None
    if origin == "lod1":
        nid, key = op.get("id"), op.get("key")
        if op["op"] != "set" or key not in LOD1_KEYS or world.graph.kind(nid) != "person":
            return "LOD1 只能调整人物的位置与心境"
        here = world.graph.get(nid, "location")
        if scope is not None and here not in scope:
            return "LOD1 越出推演区域"
        if key == "location" and op["value"] not in {n for n, _ in world.graph.roads(here)}:
            return "LOD1 人物只能移动到相邻地点"
        return None
    if origin == "chronicle":
        if scope is not None and not set(_ids(op)) <= scope:
            return "史官越出事件相关者"
        if op["op"] not in ("set", "link", "unlink") or (op["op"] == "set" and op["key"] not in CHRONICLE_KEYS):
            return "史官指令越权"
        return None
    return f"未知来源:{origin}"


def validate(world, op, origin: str, scope: set | None = None) -> str | None:
    return _basic(world, op) or _policy(world, op, origin, scope)


def _exec(world, op):
    kind = op["op"]
    if kind == "link":
        world.graph.link(op["src"], op["dst"], op["rel"])
    elif kind == "unlink":
        world.graph.unlink(op["src"], op["dst"], op["rel"])
    elif op["id"] == "player":
        getattr(world.player, kind)(op["key"], op["value"])
    else:
        node = world.graph.nodes[op["id"]]
        key, value = op["key"], op["value"]
        if kind == "set":
            node[key] = value
        elif kind == "add":
            node[key] = node.get(key, 0) + value
        elif kind == "push":
            node.setdefault(key, [])
            if value not in node[key]:
                node[key].append(value)
        elif kind == "pull" and value in node.get(key, []):
            node[key].remove(value)


def apply(world, ops: list, origin: str, scope: set | None = None) -> tuple[list, list]:
    """逐条校验并执行；返回 (已执行, [(被拒指令, 原因)])。玩家亲手触碰的节点被标记为"因果污染"。"""
    applied, rejected = [], []
    for op in ops or []:
        reason = validate(world, op, origin, scope)
        if reason:
            rejected.append((op, reason))
            continue
        _exec(world, op)
        applied.append(op)
        if origin == "rules":
            world.taint.update(i for i in _ids(op) if i != "player")
    return applied, rejected
