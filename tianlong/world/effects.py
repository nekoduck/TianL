"""
[INPUT]: 依赖 world/access 的 walk / learn / steps / hidden（通行裁判）、world/situation 的 near / around / seen / shortnames / party / join / part / follow / captors / track（情境层与连带）、
         world/growth 的 study / drain / DRAINERS（数值规则）、world/body 的 INNER / injure / relieve（内伤分级，任何人）、
         world/actor 的 hurt / declare / feel（任何人的气血、生死与心境）、world/bond 的 attitude（态度 link 化作关系账上的事件）、world/graph 的 ROAD、world/clock 的 PER_DAY，World 门面的 graph / player / knowledge / here / taint / turn（鸭子类型）
[OUTPUT]: 对外提供 apply()（规整→校验→落账剧情后果）、describe()（把一条指令译成人话，供回告编剧）、resolve()（别名/名号/近处子地点的短名/器物近似名→id）、
          unearth()（场景物件认作现场的原著器物）、
          place()（任一节点此刻所在之地）、usable()、OPS、STATUSES、MOVERS
[POS]: world 层唯一的写入通道——LLM 创造的是剧情，剧情的后果经此作用于既有世界：10 指令(set/add/push/pull/link/unlink/reveal + arrive/study/drain)，
       人物生死伤病、去留、恩怨、主角的得失与行止、器物易手、隐情与暗路的揭开、有人赶来、研习与吸功。单条指令的规整、物理与执行在此，拍与拍之间的关系归 adjudicate。
       地理与器物属于基础设施：没有任何"新造"指令；地点/景物只可改 state，器物只可改流转属性(location/holder/hidden/state)。
       数值归规则：导演不得直接增减功力或凭空授武学——研习写 study、吸功写 drain，多少由 growth 算；
       内伤归 body：导演往境况里写内伤(岔气、经脉、内息…)即按分级升一级、去掉即降一级，有据的疗伤(气血回升)顺带降一级，每回合每人各至多一级；
       主角与 NPC 同构(v4)：add hp、push/pull conditions 对任何活人成立，NPC 的气血归 actor、status 由气血推出(写 set status 则气血随之对齐)，
       set intent 改写此人眼下之事(一句话)、set mood 记下此人此刻的情绪(写到主角身上即不入账、不算错：主角的心思归玩家)；
       器物近似名分三层认：先现场(此地、近旁、身边人手里与暗藏的)，再主角认知，后全局；字面包含 > 最长公共子串过半 > 现场器物描述里的说法；
       在场即「近旁」：同一处所之内零日可达的子地点都算身边——片区(v5)里的人须被剧情带到跟前(赶来即上名册)，主角走出近旁名册即清空，
       导演碰得到的人只以「眼前」为准(situation.seen：此刻眼前、回合开始时在、本回合赶来)；原著里尚未登场的人赶不来；导演结关系(含随行、拘押)两端须在身边或回合开始时在身边，赶来(arrive)须本回合光阴够其路程；
       一回合里一个人只听一处来源调遣(导演 / 原著与史官 / 场外推演)，LLM 写的场外移动第一程不得超过一日加流逝日数；
       随行入账即解押、主角走则同伴随之、过不去的关留下；一批指令里主角的移动最后执行；
       主角的移动交 access 裁定路线：途中遇关或绝路即止步于前，本回合光阴走满即途中歇脚(记下 en_route 去向与余程、came_from 来路)，前半程成立、后半程回告编剧，走过的暗路记入认知；
       reveal 只在主角在场（导演）时当场入认知，原著揭开的隐情只入真相，经传闻（公开者）或亲历抵达——双账本不被抄近路；
       揭示须有来由(v5)：暗路要主角身在路的一端或其近旁、本回合走过或正要去那一端，隐情要当事人之一在主角身边(_seen)；
       取物只有一个口径(v5 _handy)：就在此地、或本批指令里主角要去的地方、或近旁而不是暗藏的——push inventory 与 set holder player 一样；
       形状守恒：数值仍是数值、清单仍是清单，写歪的指令被驳回而非让世界崩溃；器物流转经 _hand，持有与落地不兼存、随身账与图上永远对得上；
       原样不动的指令(人已在那里——主角「去」他正站着的地方也是，路线只有起点不是一程路、物已在那人手里、关系本就如此)不算一件事(v5)：既不成立也不驳回，不入账、不成传闻——剧情上的伤明写治好不在此列；
       场外推演只碰得到推演区域之内的人与地，结恩怨亦然；纠缠者(situation.entangled)的去留、生死、拘押场外一概动不了；
       事件先于状态(v4)：某人对主角的非结构性关系(疑忌、感激……)不再立边、不再覆盖与阻尼，而是记进 bond 的恩怨账、由系统折叠成立场；
       结构性关系(随行、拘押、师徒、结义……)与暗中的心思仍是边
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

# ============================================================
#  指令集（只作用于既有实体）
#    set/add/push/pull : 改人物、门派、器物流转或主角(id="player")的属性；地点与景物只可改 state
#    link/unlink       : 增删关系边（恩怨、结义、师承……可带 secret）
#    reveal            : 让主角得知一条既有隐情，或发现一条暗路（src/dst 为暗路两端的地点）
#    arrive            : 不在身边的人来到此地——系统按其所在与道路、本回合光阴判断赶不赶得到
#    study / drain     : 研习秘籍或求教武学 / 以北冥神功吸人内力——增减多少由 world/growth 计算，不由 LLM 报数
# ============================================================
import re

from . import access, actor, body, bond, growth, perspective, situation
from .clock import PER_DAY
from .graph import PLIGHT, ROAD

OPS = {"set", "add", "push", "pull", "link", "unlink", "reveal", "arrive", "study", "drain"}
STATUSES = {"alive", "wounded", "dead"}
FROZEN_PLAYER_KEYS = {"name", "journal", "max_hp", "quests", "study", "hooks", "turn", "acquaintances", "cast", "pacing", "came_from", "en_route",
                      "drift", "scene", "clocks", "arc", "spines", "setups"}
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
SENTENCE = {"intent": actor.INTENT_LEN, "mood": actor.MOOD_LEN}  # 人物身上的一句话属性
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
    return aliases.get(name) or aliases.get(name.replace("·", "").replace(" ", "")) or perspective.by_handle(world, name) \
        or situation.shortnames(world).get(name) or _akin(world, name) or name  # 「玉像石室」：近处子地点的短名(与体检同一口径)


def _common(a: str, b: str) -> int:
    """最长公共子串的长度。"""
    return max((k for i in range(len(a)) for k in range(1, len(a) - i + 1) if a[i:i + k] in b), default=0)


def _akin(world, name: str, scene_only: bool = False) -> str | None:
    """器物名的宽松认法，三档字面、三层先验：
    字面——一方包含另一方或字字都在对方之中只差一两个字(「闪电貂解药」→「闪电貂毒解药」，字数最近者优先，不认作那只貂)
          > 最长公共子串过半且至少三字(「北冥神功帛卷」→「北冥神功卷轴」) > 现场器物描述里有这个说法(「帛卷」→ 蒲团内藏帛卷)；
    先验——现场(随身、此地与近旁、身边人手里，暗藏的也算) > 主角认知 > 全局。认不出唯一的一件就不认，交校验驳回。"""
    if len(name) < 2:
        return None
    g, reach = world.graph, situation.near(world)
    where, _, head = name.rpartition("的")

    def tier(n):
        if g.get(n, "holder") == "player" or place(world, n) in reach:
            return 0
        return 1 if world.knowledge.knows(n) else 2

    def rank(n):
        t = tier(n)
        if name in n or n in name or (set(name) <= set(n) and len(n) - len(name) <= 2):
            return (0, abs(len(n) - len(name)), t, 0)
        common = _common(name, n)
        if common >= max(3, (len(name) + 1) // 2):
            return (1, t, -common, 0)
        desc = g.get(n, "desc") or ""
        if t == 0 and _common(where, n) < 2 and any(head[i:i + 2] in desc for i in range(len(head) - 1) if THINGISH.search(head[i:i + 2])):
            return (2, t, 0, 0)  # 「蒲团里的帛卷」：说的是帛卷，那蒲团只是它藏身之处
        return None
    pool = [n for n in g.where(type="item") if not scene_only or tier(n) == 0]
    ranked = sorted((r, n) for n in pool if (r := rank(n)))
    if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None
    return ranked[0][1]


THINGISH = re.compile(r"[药丹丸散膏卷册谱经珠钏镯盒匣瓶信牌钥囊剑刀簪玉佩]")  # 描述里的说法须是物件的叫法(帛卷、药瓶)，不是「蒲团」「石室」


def unearth(world, name: str) -> str | None:
    """导演要立的场景物件若就是现场的原著器物(多半是暗藏的那件)，认回它：不另立新物，揭开它的暗藏。"""
    hit = _akin(world, str(name or "").strip(), scene_only=True)
    return hit if hit and not world.graph.get(hit, "ephemeral") else None


def describe(op) -> str:
    """一条指令的人话——回告编剧"什么没成立"时用，不让它去读 key=value。"""
    if not isinstance(op, dict):
        return str(op)
    kind, nid, key, v = op.get("op"), op.get("id"), op.get("key"), op.get("value")
    who = "主角" if nid == "player" else str(nid)
    name = lambda x: "主角" if x == "player" else str(x)
    if kind in ("link", "unlink"):
        return f"{name(op.get('src'))}与{name(op.get('dst'))}{'结下' if kind == 'link' else '了断'}「{op.get('rel')}」"
    if kind == "arrive":
        return f"{who}来到此地"
    if kind == "study":
        return f"主角研习{v}"
    if kind == "drain":
        return f"主角吸取{v}的内力"
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
    if (op.get("key") in RESOLVED_KEYS or op.get("op") in ("study", "drain")) and isinstance(op.get("value"), str):
        op["value"] = resolve(world, op["value"])
    if op.get("op") in ("study", "drain"):
        op.setdefault("id", "player")
    if op.get("key") in NUMERIC and isinstance(op.get("value"), str) and re.fullmatch(r"[+-]?\d+", op["value"].strip()):
        op["value"] = int(op["value"])  # 结构化输出把数写成了字串：「-3」仍是 -3
    if op.get("op") == "reveal" and g.kind(op.get("src")) == g.kind(op.get("dst")) == "location":
        road = g.road(op["src"], op["dst"])  # 两地之间的揭露即发现暗路：落到道路边本身，不论 LLM 把 rel 写作什么
        if road:
            op.update(src=road["src"], dst=road["dst"], rel=ROAD)
    if op.get("op") == "link" and "note" in op:
        op["note"] = str(op["note"])[:NOTE_LEN] if op["note"] else None
    if op.get("op") == "set" and op.get("key") == "conditions" and isinstance(op.get("value"), str):
        op["op"] = "push"  # 「conditions 变为中毒」：说的是添上一样境况，不是把清单改成一个字
    if op.get("op") == "set" and op.get("key") in SENTENCE and isinstance(op.get("value"), str):
        op["value"] = op["value"].strip()[:SENTENCE[op["key"]]]
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
        if key == "threads" and isinstance(value, dict):  # 未了之事可带了结谓词：{"goal": 一句话, "done_when": [...]}
            return None if listy and isinstance(value.get("goal"), str) and value["goal"].strip() else "未了之事须有一句 goal"
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


def _handy(world, item: str, heading=frozenset()) -> bool:
    """主角够得着这件东西(v5，取物的唯一口径)：就在此地；或在本批指令里主角要去的地方；或在近旁、且不是暗藏的——
    暗藏之物要人到了那里才找得着。push inventory 与 set holder player 同一口径。"""
    where = place(world, item)
    return where == world.here or where in heading or (where in situation.near(world) and not world.graph.get(item, "hidden"))


def _physics(world, op, heading=frozenset()) -> str | None:
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

    if kind == "arrive":
        nid = op.get("id")
        return None if g.kind(nid) == "person" else f"「{nid}」不是人，无从到来"  # 死者亦可：遗体被人抬来
    if kind in ("study", "drain"):
        return _growth(world, op)

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
            if not _handy(world, value, heading):
                return f"{value}不在此地，够不着"
    return _shape(world, op)


def _growth(world, op) -> str | None:
    """研习与吸功的物理：研习须有书在手边、或有人在身边可求教；吸功须身负吸功之术、对方是活人。"""
    g, me, v = world.graph, world.player, op.get("value")
    if op.get("id") != "player":
        return "研习与吸功只结算主角本人"
    if op["op"] == "drain":
        if not any(a in me["skills"] for a in growth.DRAINERS):
            return "主角不会吸人内力的武功"
        return None if g.kind(v) == "person" and g.get(v, "status") != "dead" else f"{v}无从吸取"
    if g.kind(v) == "skill":  # 研习某门武学：手边有载此武学的秘籍，就改作研习那部秘籍
        book = next((i for i in [*me["inventory"], *g.where(type="item", location=world.here)]
                     if v in growth._skills_of(g, i)), None)
        if book:
            op["value"] = v = book
    if g.kind(v) == "item":
        if not g.get(v, "grants"):
            return f"{v}没有可研习的武学"
        return None if v in me["inventory"] or place(world, v) == world.here else f"{v}不在手边，无从研习"
    if g.kind(v) == "skill":
        return None if any(v in (g.get(p, "skills") or []) for p in situation.around(world)) else f"身边无人会{v}，无从求教"
    return f"世上没有「{v}」这部秘籍或武学"


MOVERS = {"director": "director", "canon": "canon", "chronicle": "canon", "lod1": "lod1"}  # 调遣人物的三处来源


def _travel(world, op, origin) -> str | None:
    """一回合里一个人只听一处来源调遣：原著(连同史官改写)依序走位是一条轨道，导演、场外推演各是一处——
    谁先挪动了他，别处就不能再把他挪走；场外推演与史官是 LLM 写的，第一程还不得超过一日加本回合流逝的日数。
    原著本身不受里程约束：它的日程本就压缩了旅途。"""
    turn = getattr(world, "turn", None)
    if turn is None or origin == "director" or op.get("op") != "set" or op.get("key") != "location" \
            or world.graph.kind(op.get("id")) != "person":
        return None  # 导演演的是此刻眼前之事，此地原著的走位以它为准；它挪动过的人，别处再挪不动
    pid, mine = op["id"], MOVERS.get(origin, origin)
    cur, dst = world.graph.get(pid, "location"), op.get("value")
    if cur == dst:  # 原地不动不算调遣
        return None
    prior = turn.get("movers", {}).get(pid)
    if prior and prior != mine:
        return f"{pid}此日已另有去向"
    if origin in OFFSCREEN and cur and dst:
        d = world.graph.distances(cur).get(dst, 99)
        if d > 1 + turn.get("days", 0):
            return f"{pid}身在{cur}，{d}日路程赶不到{dst}"
    return None


# ------------------------------------------------------------
#  在场性：谁能碰到谁
# ------------------------------------------------------------
def _reach(world, op, origin, scope, heading=frozenset()) -> str | None:
    if op["op"] == "reveal" and origin in OFFSCREEN:
        return "主角不在场，无从得知隐情"
    if op["op"] == "reveal" and origin == "director":
        return _seen(world, op, heading)
    if origin in OFFSCREEN:  # 纠缠者的去留、生死、拘押只听导演与此地剧情；史官与场外推演可写风声，动不了他们
        bound = [i for i in _ids(op) if i in situation.entangled(world)]
        if bound and (op["op"] in ("link", "unlink", "arrive") or op.get("key") in ("location", "status", "hp")):
            return f"{bound[0]}的行止系于主角，场外动不了"
    if op["op"] in ("link", "unlink") and origin in OFFSCREEN and scope is not None:  # 场外结恩怨，也只在推演区域之内
        far = [i for i in (op["src"], op["dst"]) if i != "player" and i not in scope and place(world, i) not in scope]
        if far:
            return f"{far[0]}不在推演区域内"
    if origin == "director" and op["op"] in ("link", "unlink"):
        return _bond(world, op)
    if origin == "canon" or op["op"] in ("link", "unlink", "reveal"):
        return None
    g, nid = world.graph, op.get("id")
    where = place(world, nid)
    if origin == "director":
        if op["op"] == "arrive":
            return _arrival(world, nid)
        if op["op"] == "drain" and op.get("value") not in situation.around(world):
            return f"{op['value']}不在你身边，吸不到他的内力"
        if nid == "player" or g.kind(nid) == "faction":
            return _self(world, op)
        if g.get(nid, "dormant"):
            return f"{nid}不在当下的江湖中"
        if op.get("key") == "power":
            return "功力由系统结算：研习写 study，吸功写 drain，不得直接增减"
        close = situation.near(world)
        if g.kind(nid) == "person":  # 人在不在眼前只有一个口径：片区里没被带到跟前的人，导演够不着(要他来写 arrive)
            if nid not in situation.seen(world):
                return f"{nid}不在你身边，主角够不着"
        if op.get("key") == "holder" and op.get("value") not in (None, "player") \
                and place(world, op["value"]) not in close:
            return f"{op['value']}不在此地，接不过{nid}"
        if op.get("key") == "holder" and op.get("value") == "player" and g.kind(nid) == "item":
            return None if _handy(world, nid, heading) else f"{nid}不在此地，够不着"
        return None if where in close else f"{nid}不在你身边，主角够不着"
    if origin in OFFSCREEN:
        if nid == "player" or op.get("value") == "player":
            return "场外推演不得改动主角本人"
        if scope is not None and nid not in scope and where not in scope:
            return f"{nid}不在推演区域内"
        if origin == "lod1" and op.get("key") == "location" and op["value"] not in access.steps(world, where):
            return "一日之内只能移动到相邻且走得通的地点"
        return None
    return f"未知来源:{origin}"


def _self(world, op) -> str | None:
    """导演改主角本人：功力只由研习与吸功结算；武学须有来路——手边的秘籍(改作研习)或身边会它的人(求教)。"""
    key, v = op.get("key"), op.get("value")
    if op.get("id") != "player":
        return None
    if key == "power" and op["op"] in ("add", "set"):
        return "功力由系统结算：研习写 study，吸功写 drain，不得直接增减"
    if key == "skills" and op["op"] == "push" and v not in world.player["skills"]:
        return f"无从凭空习得{v}：手边有秘籍就写 study 研习，身边有人会就写 study 求教"
    return None


def _seen(world, op, heading=frozenset()) -> str | None:
    """导演写的揭示须有来由(v5)：暗路要主角身在路的一端或其近旁、本回合走过或正要去那一端；
    隐情要当事人之一在主角身边(或回合开始时还在)——隔着千山万水，没有人能当场得知。"""
    turn = getattr(world, "turn", None) or {}
    if op["rel"] == ROAD:
        ends = {op["src"], op["dst"]}
        seen = situation.near(world) | set(turn.get("route", ())) | set(heading)
        return None if ends & seen else f"主角不在{op['src']}或{op['dst']}，发现不了这条暗路"
    close = situation.around(world) | set(turn.get("present", ())) | {"player"}
    return None if {op["src"], op["dst"]} & close else f"{op['src']}与{op['dst']}都不在你身边，此事无从得知"


def _bond(world, op) -> str | None:
    """导演结恩怨、定随行、写拘押：另一端是人的，须在主角身边（或正与主角同行，或回合开始时还在身边——主角先走一步，他随后跟上）；
    不在场的人结不下新的关系。"""
    g = world.graph
    close = situation.around(world) | set(situation.party(world)) | set(getattr(world, "turn", {}).get("present", ()))
    for end in (op["src"], op["dst"]):
        if end != "player" and g.kind(end) == "person" and end not in close:
            if op["op"] == "unlink" and op["rel"] == situation.FOLLOW:
                continue
            return f"{end}不在你身边，结不下「{op['rel']}」"
    return None


def _arrival(world, pid: str) -> str | None:
    """不在身边的人来到此地：须活着、在江湖中、不在溃退期，且本回合的光阴够他从所在之处赶来。"""
    g = world.graph
    if pid in situation.around(world):
        return None
    if g.get(pid, "dormant") or g.get(pid, "hidden"):
        return f"{pid}不在当下的江湖中"
    if situation.routed(world, pid):
        return f"{pid}新败而逃，不会这么快卷土重来"
    if situation.captors(world, pid):
        return f"{pid}身受拘押，来不了"
    where = g.get(pid, "location")
    days = g.distances(where).get(world.here, 99) if where else 99
    allow = getattr(world, "turn", {}).get("minutes", 0) // PER_DAY
    if days > allow:
        return f"{pid}身在{where}，距此{days}日路程，此刻赶不到"
    return None if situation.debuted(world, pid) else f"{pid}此时还没在江湖上露面"  # 原著里还没登场的人：等他自己的那一回


def _note(world, text: str | list):
    """连带后果的说明（同伴跟上、研习进境、吸功多少）：交给编剧写进正文，交给近事记下。"""
    turn = getattr(world, "turn", None)
    if turn is not None and text:
        turn.setdefault("notes", []).extend([text] if isinstance(text, str) else text)


def _exec(world, op, origin):
    g, kind = world.graph, op["op"]
    turn = getattr(world, "turn", None)
    if kind == "set" and op.get("key") == "location" and g.kind(op.get("id")) == "person" and turn is not None \
            and g.get(op["id"], "location") != op.get("value"):
        turn.setdefault("movers", {}).setdefault(op["id"], MOVERS.get(origin, origin))
    if kind == "link" and op["rel"] == situation.FOLLOW and op["dst"] == "player":
        _note(world, situation.join(world, op["src"]))
        if op["src"] not in situation.around(world):  # 主角已先走一步：随行者跟到主角身边
            g.set(op["src"], "location", world.here)
    elif kind == "unlink" and op["rel"] == situation.FOLLOW:
        situation.part(world, op["src"])
    elif kind == "link" and bond.attitude(world, op):  # 某人对主角的一时看法：记进恩怨账，立场由系统折叠
        return
    elif kind == "link":
        if op["src"] == "player" and not bond.structural(op["rel"]):  # 主角对某人的看法只留最新一条
            g.edges = [e for e in g.edges if not (e["src"] == "player" and e["dst"] == op["dst"] and not bond.structural(e["rel"]))]
        attrs = {k: v for k, v in (("secret", op.get("secret") and True), ("note", op.get("note"))) if v}
        g.link(op["src"], op["dst"], op["rel"], **attrs)
        if op["rel"] in situation.CUSTODY:  # 被擒者不再随行
            situation.part(world, op["dst"])
    elif kind == "unlink":
        g.unlink(op["src"], op["dst"], op["rel"])
    elif kind == "arrive":
        g.set(op["id"], "location", world.here)
        situation.enlist(world, [op["id"]])  # 来到主角跟前：片区里也算在眼前
        if turn is not None:
            turn.setdefault("movers", {})[op["id"]] = "director"
            turn.setdefault("arrived", set()).add(op["id"])
    elif kind == "study":
        _note(world, growth.study(world, op["value"], (turn or {}).get("minutes", 15)))
    elif kind == "drain":
        art = next(a for a in growth.DRAINERS if a in world.player["skills"])
        _note(world, growth.drain(world, op["value"], art))
    elif kind == "reveal":
        if origin == "director":  # 远方原著揭开的身世，主角不会当场知道：随事件入账，由 Knowledge.learn 按传闻或亲历送达
            world.knowledge.reveal(op["src"], op["dst"], op["rel"])
    elif op["id"] == "player" and op["key"] == "threads" and kind == "push":
        _quest(world, op["value"])
    elif op["id"] == "player" and op["key"] == "threads" and kind == "pull":
        goal = op["value"] if isinstance(op["value"], str) else op["value"].get("goal", "")
        hit = next((t for t in world.player["threads"] if t == goal or goal in t or t in goal), goal)
        world.player.pull("threads", hit)
    elif op["key"] == "conditions" and _bodily(world, op["id"]) and isinstance(op["value"], str) \
            and body.INNER.search(op["value"]) and kind in ("push", "pull"):  # 内伤只按分级升降，不由导演随手写重；主角与 NPC 同一规则
        who = op["id"]
        _note(world, body.injure(world, who=who) if kind == "push" else body.relieve(world, who=who))
    elif op["key"] == "hp" and _bodily(world, op["id"]) and kind in ("add", "set"):  # 气血归 actor：NPC 的 status 随之推出
        who = op["id"]
        delta = op["value"] if kind == "add" else op["value"] - actor.vitals(world, who)[0]
        actor.hurt(world, who, delta)
        if delta > 0 and origin == "director":
            _note(world, body.relieve(world, "调治得法", who=who))
    elif op["key"] == "status" and g.kind(op["id"]) == "person" and kind == "set":
        actor.declare(world, op["id"], op["value"])
        g.nodes[op["id"]][PLIGHT] = op["value"] == "wounded"  # 明写的负伤是剧情上的伤：气血养好不算痊愈，明写安好或身亡才消
    elif op["key"] == "mood" and g.kind(op["id"]) == "person" and kind == "set":
        actor.feel(world, op["id"], op["value"])
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


def _bodily(world, nid) -> bool:
    return nid == "player" or world.graph.kind(nid) == "person"


def _quest(world, value):
    """登记一条未了之事：对象由句中提到的人与物推定；可带了结谓词。满四条挤掉最久未推进的。"""
    from . import lexicon  # 词表只在登记未了之事时用到
    goal, cond = (value, None) if isinstance(value, str) else (value["goal"].strip(), value.get("done_when"))
    g = world.graph
    names = {n: n for n, node in g.nodes.items() if node["type"] in ("person", "item", "group")}
    names.update({a: n for a, n in world.aliases.items() if g.kind(n) in ("person", "item")})
    about = [n for n, _, _ in lexicon.find(goal, lexicon.table(names))]
    world.player.push("threads", goal)
    _note(world, situation.track(world, goal, about, cond))


def _hand(world, item: str, holder: str | None = None, location: str | None = None):
    """器物流转：持有与落地不兼存；交到主角手里即入随身，离开主角手里即出随身——黑板与图上的器物永远对得上账。"""
    node = world.graph.nodes[item]
    if node.get("holder") == "player" and holder != "player":
        world.player.pull("inventory", item)
    node.update(holder=holder, location=location)
    if holder == "player":
        world.player.push("inventory", item)
        node["hidden"] = False


def _summon(world, op, origin):
    """导演把不在身边的人「set location 此地」：那是有人赶来，按 arrive 的物理裁定（光阴够不够他赶到）。"""
    if origin == "director" and op.get("op") == "set" and op.get("key") == "location" \
            and op.get("value") == world.here and world.graph.kind(op.get("id")) == "person" \
            and op["id"] not in situation.around(world):
        pid = op["id"]
        op.clear()
        op.update(op="arrive", id=pid)


def _progress(world, route: list[str]) -> bool:
    """半途止步的这段路走出了至少一日：真正的远行在关前歇脚；零日的近处兜圈不算前进。"""
    return sum((world.graph.road(a, b) or {}).get("days", 0) for a, b in zip(route, route[1:])) >= 1


def _noop(world, op) -> bool:
    """原样不动的指令：人已在那里、物已在那人手里、关系本就如此——不是一件事，不入账、不成传闻(v5)。
    「龚光杰前往剑湖宫·练武厅」而他本就站在那里，写进传闻便是一句假话。主角本人的指令只认一种：去他已经站着的地方。"""
    g, kind = world.graph, op.get("op")
    if kind in ("link", "unlink") and all(isinstance(op.get(k), str) for k in ("src", "dst", "rel")):
        has = any(e["src"] == op["src"] and e["dst"] == op["dst"] and e["rel"] == op["rel"] for e in g.edges)
        return has if kind == "link" else not has
    nid, key = op.get("id"), op.get("key")
    if nid == "player":  # 主角「去」他已经站着的地方：不是一程路(路线只有起点，记不出来路)
        return kind == "set" and key == "location" and op.get("value") == world.here
    if kind != "set" or not isinstance(nid, str) or not g.has(nid):
        return False
    if key == "status":  # 剧情上的伤另有一笔：气血养好而原著之伤仍在的人，明写「安好」不是空话
        return g.get(nid, key) == op.get("value") and bool(g.get(nid, PLIGHT)) == (op.get("value") == "wounded")
    return key in ("location", "holder", "faction", "hidden") and g.get(nid, key) == op.get("value")


def _moves_player(world, op) -> bool:
    return isinstance(op, dict) and op.get("op") == "set" and op.get("id") in ("player", "主角", world.player["name"]) \
        and PLAYER_ALIASES.get(op.get("key"), op.get("key")) == "location"


def apply(world, ops: list, origin: str, scope: set | None = None) -> tuple[list, list]:
    """逐条落账；返回 (已成立, [(未成立的指令, 原因)])。导演触碰过的节点记为因果污染。
    主角的移动排到最后：一回合内发生的事都发生在回合开始的所在，同伴随行、器物易手不会因主角先走一步而"不在此地"。
    一回合里一个人只听一处来源调遣；主角走了，同伴随行跟上。"""
    applied, rejected = [], []
    ops = ops if isinstance(ops, list) else []  # 场外推演偶把一条指令写成单值：整批作废，不让世界崩
    ops = [op for op in ops if not _moves_player(world, op)] + [op for op in ops if _moves_player(world, op)]
    heading = {v for op in ops if _moves_player(world, op) and isinstance(v := resolve(world, op.get("value")), str)}  # 本批里主角要去的地方：先取物、后动身，取的是那里的东西
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in OPS:
            rejected.append((op, "未知指令"))
            continue
        try:
            _normalize(world, op)
            if op.get("id") == "player" and op.get("key") in SENTENCE:
                continue  # 主角的心思与神色归玩家：导演替他写下的打算不算错，只是不入账，免得为此返工
            _summon(world, op, origin)
            if _noop(world, op):
                continue  # 本就如此：既非成立也非驳回
            reason = _physics(world, op, heading) or _reach(world, op, origin, scope, heading) or _travel(world, op, origin)
        except (TypeError, AttributeError, KeyError):  # 畸形值（如列表当 id）：单条不成立，游戏不崩
            reason = "格式不可解"
        if reason:
            rejected.append((op, reason))
            continue
        if _moves_player(world, op):  # 远行：途中遇关或绝路即止步于前，光阴走满即途中歇脚；前半程照走，后半程回告编剧
            dest, turn = op["value"], getattr(world, "turn", None)
            budget = max(1, turn["minutes"] // PER_DAY) if turn and turn.get("minutes") else None
            route, why = access.walk(world, dest, budget)
            if len(route) < 2 and not why:  # 无路可走也无缘由：原地未动
                continue
            if why:
                rejected.append(({**op}, why))
                if len(route) < 2 or not _progress(world, route):  # 受阻不倒退：近处绕了一圈仍过不去，便原地不动
                    continue
                op["value"] = route[-1]
            before = situation.near(world)
            access.learn(world, route)
            me = world.player
            me.set("came_from", route[-2])
            me.set("en_route", {"to": dest, "left": world.graph.distances(route[-1]).get(dest, 0)}
                   if why and why.startswith(access.ON_ROAD) else None)  # 途中：记着去向，下回合可续行，也可在途中生事
            _exec(world, op, origin)
            situation.muster(world, before)  # 走出了原来的近旁：跟前的人留在原处
            applied.append(op)
            turn = getattr(world, "turn", None)
            if turn is not None and "route" in turn:  # 裁决器在场：同伴等诸拍落定再跟（拍中途解除随行的人不被带走）
                turn["route"] += route[1:]
            else:
                _note(world, situation.follow(world, route))
            continue
        _exec(world, op, origin)
        applied.append(op)
        if origin == "director":
            world.taint.update(i for i in _ids(op) if i and i != "player")
    return applied, rejected
