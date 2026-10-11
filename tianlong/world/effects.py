"""
[INPUT]: 依赖 world/access 的 walk / learn / steps / hidden（通行裁判）、world/graph 的 ROAD，依赖 World 门面的 graph / player / knowledge / here / taint（鸭子类型）
[OUTPUT]: 对外提供 apply()（规整→校验→落账剧情后果）、describe()（把一条指令译成人话，供回告编剧）、resolve()（别名/名号→id）、
          place()（任一节点此刻所在之地）、usable()、OPS、STATUSES
[POS]: world 层唯一的写入通道——LLM 创造的是剧情，剧情的后果经此作用于既有世界：
       人物生死伤病、去留、恩怨、武学、主角的得失与行止、器物易手、隐情与暗路的揭开。
       地理与器物属于基础设施：没有任何"新造"指令；地点/景物只可改 state，器物只可改流转属性(location/holder/hidden/state)。
       一批指令里主角的移动最后执行，在场性以回合开始时的所在为准（同伴随行不被误判为"不在此地"）；
       主角的移动交 access 裁定路线：途中遇关或绝路即止步于前，前半程成立、后半程回告编剧，走过的暗路记入认知；
       reveal 只在主角在场（导演）时当场入认知，原著揭开的隐情只入真相，经传闻（公开者）或亲历抵达——双账本不被抄近路；
       形状守恒：数值仍是数值、清单仍是清单，写歪的指令被驳回而非让世界崩溃；器物流转经 _hand，持有与落地不兼存、随身账与图上永远对得上；
       场外推演只碰得到推演区域之内的人与地，结恩怨亦然
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

# ============================================================
#  指令集（只作用于既有实体）
#    set/add/push/pull : 改人物、门派、器物流转或主角(id="player")的属性；地点与景物只可改 state
#    link/unlink       : 增删关系边（恩怨、结义、师承……可带 secret）
#    reveal            : 让主角得知一条既有隐情，或发现一条暗路（src/dst 为暗路两端的地点）
# ============================================================
from . import access
from .graph import ROAD

OPS = {"set", "add", "push", "pull", "link", "unlink", "reveal"}
STATUSES = {"alive", "wounded", "dead"}
FROZEN_PLAYER_KEYS = {"name", "journal", "max_hp"}
PLAYER_ALIASES = {"姿态": "posture", "气血": "hp", "功力": "power", "物品": "inventory", "随身": "inventory",
                  "武学": "skills", "武功": "skills", "位置": "location", "所在": "location"}
TERRAIN = {"location", "feature"}               # 地理：定义由创世数据给出，剧情只能改变其现状(state)
ITEM_FLOW = {"location", "holder", "hidden", "state"}  # 器物：定义不可改，只可流转、显隐、损耗
OFFSCREEN = {"lod1", "chronicle"}                # 场外推演：主角不在场，碰不到主角本人
RESOLVED_KEYS = {"location", "holder", "inventory", "skills", "faction"}  # 这些值是实体名，须经别名表归一
NUMERIC = {"hp", "power", "age"}                 # 数值属性：只可 set 或 add 一个数
LISTS = {"inventory", "skills", "conditions", "threads"}  # 清单属性：逐项 push/pull；境况与线头亦可整体 set 成一列文字
ENTITY_LISTS = {"inventory", "skills"}           # 实体清单只可逐件得失：整体改写会绕过"世上有没有此物"的校验
NOTE_LEN = 40                                    # 关系边上的印象一句话
STATUS_WORDS = {"alive": "安好无恙", "wounded": "负伤", "dead": "身亡"}


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


def resolve(world, name):
    """把 LLM 笔下的称呼落到实体 id：主角名号→player，别名（萧峰、乔帮主）与去「·」写法→正名；落不到就原样返回让校验驳回。"""
    if not isinstance(name, str) or name == "player" or world.graph.has(name):
        return name
    if name in (world.player["name"], "主角"):
        return "player"
    aliases = getattr(world, "aliases", {})
    return aliases.get(name) or aliases.get(name.replace("·", "").replace(" ", "")) or name


def describe(op) -> str:
    """一条指令的人话——回告编剧"什么没成立"时用，不让它去读 key=value。"""
    if not isinstance(op, dict):
        return str(op)
    kind, nid, key, v = op.get("op"), op.get("id"), op.get("key"), op.get("value")
    who = "主角" if nid == "player" else str(nid)
    name = lambda x: "主角" if x == "player" else str(x)
    if kind in ("link", "unlink"):
        return f"{name(op.get('src'))}与{name(op.get('dst'))}{'结下' if kind == 'link' else '了断'}「{op.get('rel')}」"
    if kind == "reveal" and op.get("rel") == ROAD:
        return f"发现{op.get('src')}与{op.get('dst')}之间的暗路"
    if kind == "reveal":
        return f"揭开隐情「{op.get('src')}—{op.get('rel')}—{op.get('dst')}」"
    if kind == "set" and key == "location":
        return f"{who}前往{v}"
    if kind == "set" and key == "status":
        return f"{who}{STATUS_WORDS.get(v, v)}"
    if kind == "set" and key == "holder":
        return f"{nid}归{name(v)}所有"
    if kind == "add":
        return f"{who}的{key}{'+' if isinstance(v, (int, float)) and v >= 0 else ''}{v}"
    if kind in ("push", "pull"):
        verb = {"push": "获得", "pull": "失去"}[kind] if key in ("inventory", "skills") else {"push": "添上", "pull": "去掉"}[kind]
        return f"{who}{verb}{v}"
    if kind == "set":
        return f"{who}的{key}变为{v}"
    return str(op)


# ------------------------------------------------------------
#  规整：替 LLM 消化不影响语义的写法差异
# ------------------------------------------------------------
def _normalize(world, op):
    g = world.graph
    for k in ("id", "src", "dst"):
        if k in op:
            op[k] = resolve(world, op[k])
    if op.get("id") == "player":
        op["key"] = PLAYER_ALIASES.get(op.get("key"), op.get("key"))
    if op.get("key") in RESOLVED_KEYS and isinstance(op.get("value"), str):
        op["value"] = resolve(world, op["value"])
    if op.get("op") == "reveal" and g.kind(op.get("src")) == g.kind(op.get("dst")) == "location":
        road = g.road(op["src"], op["dst"])  # 两地之间的揭露即发现暗路：落到道路边本身，不论 LLM 把 rel 写作什么
        if road:
            op.update(src=road["src"], dst=road["dst"], rel=ROAD)
    if op.get("op") == "link" and "note" in op:
        op["note"] = str(op["note"])[:NOTE_LEN] if op["note"] else None
    if op.get("op") == "set" and op.get("key") == "location" and g.kind(op.get("id")) != "item" \
            and g.kind(op.get("value")) not in ("location", None):
        op["value"] = place(world, op["value"])  # 走向某人/某物 = 走向其所在之地


# ------------------------------------------------------------
#  世界物理：与来源无关的一致性
# ------------------------------------------------------------
def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _shape(world, op) -> str | None:
    """形状守恒：数值仍是数值、清单仍是清单、主角的文字仍是文字——剧情可以改值，不能把属性改成别的东西，
    否则下一回合的视锥、身况与存档就会崩在一个写歪了的指令上。"""
    kind, nid, key, value = op["op"], op["id"], op["key"], op.get("value")
    cur = world.player.get(key) if nid == "player" else world.graph.get(nid, key)
    numeric = key in NUMERIC or _number(cur)
    if kind == "add" and not numeric:
        return f"{key}不是数值，无从增减"
    if numeric:
        return None if kind in ("set", "add") and _number(value) else f"{key}是数值，只可 set 或 add 一个数"
    if kind in ("push", "pull"):
        listy = isinstance(cur, list) or (cur is None and key in LISTS)
        return None if listy and isinstance(value, str) else f"{key}不是清单，无从增删"
    if key in ENTITY_LISTS:
        return "器物与武学只可逐件得失(push/pull)，不可整体改写"
    if key in LISTS or isinstance(cur, list):
        return None if isinstance(value, list) and all(isinstance(x, str) for x in value) else f"{key}是清单，须写成一列文字"
    if isinstance(value, (dict, list)) and key != "state":
        return f"{key}不可写成复合值"
    if nid == "player" and not isinstance(value, str):
        return f"{key}须为文字"
    return None


def _physics(world, op) -> str | None:
    g, kind = world.graph, op["op"]
    if kind in ("link", "unlink", "reveal"):
        if not all(isinstance(op.get(k), str) for k in ("src", "dst", "rel")):
            return "关系边缺字段"
        if not all(i == "player" or g.has(i) for i in _ids(op)):
            return "关系端点不在世界中"
        if op["rel"] == ROAD and kind != "reveal":
            return "道路属于地理，由系统掌管"
        if kind == "reveal" and op["rel"] == ROAD:  # 发现暗路：两地之间须有道路，且道路藏着暗路
            road = g.road(op["src"], op["dst"])
            return None if road and access.hidden(road) else "两地之间并无暗路"
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
    if kind == "set" and key == "status":
        if value not in STATUSES:
            return f"非法状态:{value}"
        if g.get(nid, "status") == "dead" and value != "dead":
            return f"{nid}已死，死者不能复生"
    if kind == "set" and key == "location" and (value is not None or nid == "player") and g.kind(value) != "location":
        return f"世上没有「{value}」这个地方"  # 主角去得了去不了，由 apply 交 access 按路线裁定
    if kind == "set" and key == "holder" and value is not None and value != "player" and g.kind(value) != "person":
        return f"「{value}」不是人，无法持有器物"
    if kind == "set" and key == "faction" and value is not None and g.kind(value) != "faction":
        return f"世上没有「{value}」这个门派"
    if kind in ("push", "pull") and key == "skills" and g.kind(value) != "skill":
        return f"世上没有「{value}」这门武学"
    if nid == "player" and key == "inventory" and kind in ("push", "pull"):
        if g.kind(value) != "item":
            return f"世上没有「{value}」这件器物"
        if kind == "pull" and value not in world.player["inventory"]:
            return f"主角身上并没有{value}"
        if kind == "push" and value not in world.player["inventory"]:
            if not usable(world, value):
                return f"{value}已不复存在"
            if place(world, value) != world.here:
                return f"{value}不在此地，够不着"
    return _shape(world, op)


# ------------------------------------------------------------
#  在场性：谁能碰到谁
# ------------------------------------------------------------
def _reach(world, op, origin, scope) -> str | None:
    if op["op"] == "reveal" and origin in OFFSCREEN:
        return "主角不在场，无从得知隐情"
    if op["op"] in ("link", "unlink") and origin in OFFSCREEN and scope is not None:  # 场外结恩怨，也只在推演区域之内
        far = [i for i in (op["src"], op["dst"]) if i != "player" and i not in scope and place(world, i) not in scope]
        if far:
            return f"{far[0]}不在推演区域内"
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
        if origin == "lod1" and op.get("key") == "location" and op["value"] not in access.steps(world, where):
            return "一日之内只能移动到相邻且走得通的地点"
        return None
    return f"未知来源:{origin}"


def _exec(world, op, origin):
    g, kind = world.graph, op["op"]
    if kind == "link":
        if "player" in (op["src"], op["dst"]):  # 某人对主角的关系只留最新一条：写新即覆盖旧，恩怨会演变而不会堆叠
            g.edges = [e for e in g.edges if not (e["src"] == op["src"] and e["dst"] == op["dst"])]
        attrs = {k: v for k, v in (("secret", op.get("secret") and True), ("note", op.get("note"))) if v}
        g.link(op["src"], op["dst"], op["rel"], **attrs)
    elif kind == "unlink":
        g.unlink(op["src"], op["dst"], op["rel"])
    elif kind == "reveal":
        if origin == "director":  # 远方原著揭开的身世，主角不会当场知道：随事件入账，由 Knowledge.learn 按传闻或亲历送达
            world.knowledge.reveal(op["src"], op["dst"], op["rel"])
    elif op["id"] == "player" and op["key"] == "inventory":  # 拾起则归主角随身，丢下则落在此地
        _hand(world, op["value"], **({"holder": "player"} if kind == "push" else {"location": world.here}))
    elif op["id"] == "player":
        getattr(world.player, kind)(op["key"], op["value"])
    elif g.kind(op["id"]) == "item" and op["key"] == "holder":  # 易手；脱手而无人接，便落在原处
        _hand(world, op["id"], holder=op["value"], location=None if op["value"] else place(world, op["id"]))
    elif g.kind(op["id"]) == "item" and op["key"] == "location":
        _hand(world, op["id"], location=op["value"])
    else:
        node, key, value = g.nodes[op["id"]], op["key"], op["value"]
        if kind == "set":
            node[key] = value
        elif kind == "add":
            node[key] = (node[key] if _number(node.get(key)) else 0) + value
        elif kind == "push" and value not in (node.get(key) or []):
            node[key] = (node.get(key) or []) + [value]
        elif kind == "pull" and value in (node.get(key) or []):
            node[key] = [x for x in node[key] if x != value]


def _hand(world, item: str, holder: str | None = None, location: str | None = None):
    """器物流转：持有与落地不兼存；交到主角手里即入随身，离开主角手里即出随身——黑板与图上的器物永远对得上账。"""
    node = world.graph.nodes[item]
    if node.get("holder") == "player" and holder != "player":
        world.player.pull("inventory", item)
    node.update(holder=holder, location=location)
    if holder == "player":
        world.player.push("inventory", item)
        node["hidden"] = False


def _moves_player(world, op) -> bool:
    return isinstance(op, dict) and op.get("op") == "set" and op.get("id") in ("player", "主角", world.player["name"]) \
        and PLAYER_ALIASES.get(op.get("key"), op.get("key")) == "location"


def apply(world, ops: list, origin: str, scope: set | None = None) -> tuple[list, list]:
    """逐条落账；返回 (已成立, [(未成立的指令, 原因)])。导演触碰过的节点记为因果污染。
    主角的移动排到最后：一回合内发生的事都发生在回合开始的所在，同伴随行、器物易手不会因主角先走一步而"不在此地"。"""
    applied, rejected = [], []
    ops = ops if isinstance(ops, list) else []  # 场外推演偶把一条指令写成单值：整批作废，不让世界崩
    ops = [op for op in ops if not _moves_player(world, op)] + [op for op in ops if _moves_player(world, op)]
    for op in ops:
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
        if _moves_player(world, op):  # 远行：途中遇关或绝路即止步于前，前半程照走，后半程回告编剧
            route, why = access.walk(world, op["value"])
            if why:
                rejected.append(({**op}, why))
                if len(route) < 2:
                    continue
                op["value"] = route[-1]
            access.learn(world, route)
        _exec(world, op, origin)
        applied.append(op)
        if origin == "director":
            world.taint.update(i for i in _ids(op) if i and i != "player")
    return applied, rejected
