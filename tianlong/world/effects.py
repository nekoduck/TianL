"""
[INPUT]: 依赖 world/graph 的 ROAD；依赖 World 门面的 graph / player / here / taint（鸭子类型）
[OUTPUT]: 对外提供 apply()（规整→校验→落账 LLM 的创造）、OPS、TYPES、STATUSES
[POS]: world 层唯一的写入通道，也是 LLM 创造力的"物化器"——导演、推演、史官写下的新人物、新地点、新器物、新恩怨
       经此成为持久真相。先宽松规整（中文属性名、走向某人即走向其所在、造物即随身、道路缺省），
       再只守"世界物理"（引用存在、死者不复生、远方够不着、新地须有路），不审查创意
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from .graph import ROAD

# ============================================================
#  指令集
#    set/add/push/pull : 改节点或玩家(id="player")的属性
#    link/unlink       : 增删关系边（可带 secret）
#    create            : 创造新节点（人物/地点/器物/景物/门派），新地点须以 road 接入地图
#    reveal            : 让玩家得知一条隐情（secret 边）
# ============================================================
OPS = {"set", "add", "push", "pull", "link", "unlink", "create", "reveal"}
TYPES = {"person", "location", "item", "feature", "faction"}
STATUSES = {"alive", "wounded", "dead"}
FROZEN_PLAYER_KEYS = {"name", "journal", "max_hp"}
PLAYER_ALIASES = {"姿态": "posture", "气血": "hp", "功力": "power", "物品": "inventory", "随身": "inventory",
                  "武学": "skills", "武功": "skills", "位置": "location", "所在": "location"}
OFFSCREEN = {"lod1", "chronicle"}  # 场外推演：玩家不在场，碰不到玩家本人


def _ids(op) -> list[str]:
    return [op.get("src"), op.get("dst")] if op["op"] in ("link", "unlink", "reveal") else [op.get("id")]


# ------------------------------------------------------------
#  规整：替 LLM 补齐它不必操心的默认值
# ------------------------------------------------------------
def _normalize(world, op, origin):
    g = world.graph
    if op.get("id") == "player":
        op["key"] = PLAYER_ALIASES.get(op.get("key"), op.get("key"))
    if op.get("op") == "set" and op.get("key") == "location" and g.kind(op.get("value")) not in ("location", None):
        op["value"] = g.get(op["value"], "location")  # 走向某人/某物 = 走向其所在之地
    if op.get("op") != "create":
        return
    attrs = op.get("attrs")
    if not isinstance(attrs, dict):
        attrs = op["attrs"] = {}
    kind = op.get("type")
    if kind == "location":  # 道路写在 attrs 里也认；导演在场景中新辟之地，缺省与此地相连
        road = op.get("road") or attrs.pop("road", None)
        if not isinstance(road, dict) and origin == "director":
            road = {"to": world.here, "days": 0}
        if isinstance(road, dict):
            road.setdefault("days", 1)
        op["road"] = road
    if kind == "person":
        attrs.setdefault("status", "alive")
        attrs.setdefault("power", 30)
    if kind == "item" and attrs.get("location") == "player":  # 造出即随身
        attrs["location"], op["carry"] = None, True
    if kind in ("person", "item", "feature") and origin == "director" and not op.get("carry"):
        attrs.setdefault("location", world.here)


# ------------------------------------------------------------
#  世界物理：与来源无关的一致性
# ------------------------------------------------------------
def _physics(world, op) -> str | None:
    g, kind = world.graph, op["op"]
    if kind == "create":
        nid, attrs = op.get("id"), op["attrs"]
        if not isinstance(nid, str) or not nid or nid == "player" or g.has(nid):
            return f"无法创造「{nid}」：名字为空或已存在"
        if op.get("type") not in TYPES:
            return f"未知类型:{op.get('type')}"
        if op["type"] == "location":
            road = op.get("road") or {}
            if g.kind(road.get("to")) != "location" or not isinstance(road.get("days"), int) or road["days"] < 0:
                return f"新地点「{nid}」须以 road:{{to:已有地点, days:整数}} 接入地图"
        loc = attrs.get("location")
        if loc is not None and g.kind(loc) != "location":
            return f"「{nid}」所在地「{loc}」不存在"
        if op["type"] == "person" and loc is None:
            return f"新人物「{nid}」须有所在地"
        return None
    if kind in ("link", "unlink", "reveal"):
        if not all(isinstance(op.get(k), str) for k in ("src", "dst", "rel")):
            return "关系边缺字段"
        if not all(i == "player" or g.has(i) for i in _ids(op)):
            return "关系端点不存在"
        if kind == "reveal" and not any(e["src"] == op["src"] and e["dst"] == op["dst"] and e["rel"] == op["rel"]
                                        for e in g.edges):
            return "要揭露的隐情并不存在"
        return None

    nid, key, value = op.get("id"), op.get("key"), op.get("value")
    if nid != "player" and not g.has(nid):
        return f"「{nid}」不存在（若是新角色，先 create）"
    if not isinstance(key, str):
        return "缺少 key"
    if nid == "player" and (key not in world.player.data or key in FROZEN_PLAYER_KEYS):
        return f"玩家属性「{key}」不可写"
    if kind == "add" and not isinstance(value, (int, float)):
        return "add 需要数值"
    if kind == "set" and key == "status":
        if value not in STATUSES:
            return f"非法状态:{value}"
        if g.get(nid, "status") == "dead" and value != "dead":
            return f"{nid}已死，死者不能复生"
    if kind == "set" and key == "location":
        if value is None and (nid == "player" or g.kind(nid) == "person"):
            return "人物必须身处某地"
        if value is not None and g.kind(value) != "location":
            return f"地点「{value}」不存在（若是新地点，先 create）"
        if nid == "player" and value not in g.distances(world.here):
            return f"{value}与此地不相通"
    if kind == "push" and nid == "player" and key == "inventory":
        if g.kind(value) != "item":
            return f"「{value}」不是器物（先 create 为 item）"
        if value not in world.player["inventory"] and g.get(value, "location") != world.here:
            return f"{value}不在此地，够不着"
    return None


# ------------------------------------------------------------
#  在场性：谁能碰到谁
# ------------------------------------------------------------
def _reach(world, op, origin, scope) -> str | None:
    if origin == "canon" or op["op"] in ("link", "unlink", "reveal"):
        if origin in OFFSCREEN and op["op"] == "reveal":
            return "玩家不在场，无从得知隐情"
        return None
    g, nid = world.graph, op.get("id")
    if origin == "director":
        if nid == "player" or g.kind(nid) == "faction" or op["op"] == "create":
            return None
        where = nid if g.kind(nid) == "location" else g.get(nid, "location")
        carried = nid in world.player["inventory"]
        return None if where == world.here or carried else f"{nid}不在此地，主角够不着"
    if origin in OFFSCREEN:
        if nid == "player":
            return "场外推演不得改动主角本人"
        if op["op"] == "create":
            loc = op["attrs"].get("location")
            road = (op.get("road") or {}).get("to")
            return None if scope is None or loc in scope or road in scope or op["type"] == "faction" \
                else "场外推演只能在本区域内创造"
        here = nid if g.kind(nid) == "location" else g.get(nid, "location")
        if scope is not None and nid not in scope and here not in scope:
            return f"{nid}不在推演区域内"
        if origin == "lod1" and op.get("key") == "location" and op["value"] not in {n for n, _ in g.roads(here)} | {here}:
            return "一日之内只能移动到相邻地点"
        return None
    return f"未知来源:{origin}"


def _exec(world, op):
    g, kind = world.graph, op["op"]
    if kind == "create":
        g.nodes[op["id"]] = {"type": op["type"], **op["attrs"]}
        if op["type"] == "location":
            g.link(op["id"], op["road"]["to"], ROAD, days=op["road"]["days"])
        if op.get("carry"):
            world.player.push("inventory", op["id"])
    elif kind == "link":
        g.link(op["src"], op["dst"], op["rel"], **({"secret": True} if op.get("secret") else {}))
    elif kind == "unlink":
        g.unlink(op["src"], op["dst"], op["rel"])
    elif kind == "reveal":
        world.knowledge.reveal(op["src"], op["dst"], op["rel"])
    elif op["id"] == "player":
        getattr(world.player, kind)(op["key"], op["value"])
        if op["key"] == "inventory":  # 物品随身则离地，丢下则落地
            g.set(op["value"], "location", None if kind == "push" else world.here)
    else:
        node, key, value = g.nodes[op["id"]], op["key"], op["value"]
        if kind == "set":
            node[key] = value
        elif kind == "add":
            node[key] = node.get(key, 0) + value
        elif kind == "push" and value not in node.setdefault(key, []):
            node[key].append(value)
        elif kind == "pull" and value in node.get(key, []):
            node[key].remove(value)


def apply(world, ops: list, origin: str, scope: set | None = None) -> tuple[list, list]:
    """逐条落账；返回 (已成立, [(未成立的指令, 原因)])。同一批中先 create 的节点，后续指令即可引用。"""
    scope = set(scope) if scope is not None else None
    applied, rejected = [], []
    for op in ops or []:
        if not isinstance(op, dict) or op.get("op") not in OPS:
            rejected.append((op, "未知指令"))
            continue
        try:
            _normalize(world, op, origin)
            reason = _physics(world, op) or _reach(world, op, origin, scope)
        except (TypeError, AttributeError, KeyError):  # 畸形值（如列表当 id）：单条不成立，游戏不崩
            reason = "格式不可解"
        if reason:
            rejected.append((op, reason))
            continue
        _exec(world, op)
        applied.append(op)
        if op["op"] == "create" and scope is not None:
            scope.add(op["id"])
        if origin == "director":
            world.taint.update(i for i in _ids(op) if i and i != "player")
    return applied, rejected
