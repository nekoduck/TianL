"""
[INPUT]: 依赖 world/access 的 walk / learn / steps / hidden（通行裁判）、world/situation 的 near / around / seen / shortnames / party / join / part / follow / captors / track / carried / enlist（情境层与连带；v12 同行与押解随调遣）、
         world/growth 的 study / drain / DRAINERS（数值规则）、world/body 的 INNER / injure / relieve（内伤分级，任何人）、
         world/actor 的 hurt / declare / feel（任何人的气血、生死与心境）、world/bond 的 attitude（态度 link 化作关系账上的事件）、world/graph 的 ROAD、world/clock 的 PER_DAY，
         world/acts 的 expand / perform / is_act / describe（v9 事码）、world/crowd 的 besiegers / is_squad / handle（人群与围攻）、world/stock（银两与数量的说法），World 门面的 graph / player / knowledge / here / taint / turn（鸭子类型）
[OUTPUT]: 对外提供 apply()（规整→校验→落账剧情后果）、describe()（把一条指令译成人话，供回告编剧）、resolve()（别名/名号/近处子地点的短名/器物近似名→id）、
          named() / naming()（v6 识名指令：是不是、几种写法规整成 reveal{id}）、
          unearth()（导演要立的物件认作现场既有的器物——v8 物件不再另立，认得回就用它）、
          place()（任一节点此刻所在之地）、things()（v11 此刻在某几处的器物：地上的连同那里的人手里的，按索引取、与 place 同一口径）、usable()、destination()（一条指令或事码里主角要去的地方）、OPS、STATUSES、MOVERS
[POS]: v11 世界底座：RULED_BY 规则自己落的账(药力、医治)不算哪一方写的剧情、不顺带降内伤；describe 说买卖(trade)、服务(service)、打听来的话(lore)；主角走进一处新立的场所即进它的前堂(venue.door)，走到哪里近处的场所便布好(venue.settle)，过关付关钱。
       world 层唯一的写入通道——LLM 创造的是剧情，剧情的后果经此作用于既有世界：10 指令(set/add/push/pull/link/unlink/reveal + arrive/study/drain)，
       人物生死伤病、去留、恩怨、主角的得失与行止、器物易手、隐情与暗路的揭开、有人赶来、研习与吸功。单条指令的规整、物理与执行在此，拍与拍之间的关系归 adjudicate。
       地理与器物属于基础设施：没有任何"新造"指令；地点/景物只可改 state，器物只可改流转属性(location/holder/hidden/state)与方位 spot(v8 场景清单：
       剑架上、茶几上——软的：_hand 流转即清，到了谁手里没有方位、落下便是「地上」；「去掉方位」之类的写法与主角的方位不算错也不入账，原样不动的方位不是一件事)。
       数值归规则：导演不得直接增减功力或凭空授武学——研习写 study、吸功写 drain，多少由 growth 算；
       内伤归 body：导演往境况里写内伤(岔气、经脉、内息…)即按分级升一级、去掉即降一级，有据的疗伤(气血回升)顺带降一级，每回合每人各至多一级；
       主角与 NPC 同构(v4)：add hp、push/pull conditions 对任何活人成立，NPC 的气血归 actor、status 由气血推出(写 set status 则气血随之对齐)，
       set intent 改写此人眼下之事(一句话)、set mood 记下此人此刻的情绪(写到主角身上即不入账、不算错：主角的心思归玩家)；
       器物近似名分三层认：先现场(此地、近旁、身边人手里与暗藏的)，再主角认知，后全局；字面包含 > 最长公共子串过半 > 现场器物描述里的说法；
       在场即「近旁」：同一处所之内零日可达的子地点都算身边——片区(v5)里的人须被剧情带到跟前(赶来即上名册)，主角走出近旁名册即清空，
       导演碰得到的人只以「眼前」为准(situation.seen：此刻眼前、回合开始时在、本回合赶来)；原著里尚未登场的人赶不来；导演结关系(含随行、拘押)两端须在身边或回合开始时在身边，赶来(arrive)须本回合光阴够其路程；
       一回合里一个人只听一处来源调遣(导演 / 原著与场外剧情：衍生事件与原著同一条轨道)；
       随行入账即解押、主角走则同伴随之、过不去的关留下；一批指令里主角的移动最后执行；
       主角的移动交 access 裁定路线：途中遇关或绝路即止步于前，本回合光阴走满即途中歇脚(记下 en_route 去向与余程、came_from 来路)，前半程成立、后半程回告编剧，走过的暗路记入认知；
       reveal 只在主角在场（导演）时当场入认知，原著揭开的隐情只入真相，经传闻（公开者）或亲历抵达——双账本不被抄近路；
       揭示须有来由(v5)：暗路要主角身在路的一端或其近旁、本回合走过或正要去那一端，隐情要当事人之一在主角身边(_seen)；
       取物只有一个口径(v5 _handy)：就在此地、或本批指令里主角要去的地方、或近旁而不是暗藏的——push inventory 与 set holder player 一样；
       形状守恒：数值仍是数值、清单仍是清单，写歪的指令被驳回而非让世界崩溃；器物流转经 _hand，持有与落地不兼存、随身账与图上永远对得上；
       原样不动的指令(人已在那里——主角「去」他正站着的地方也是，路线只有起点不是一程路、物已在那人手里、关系本就如此)不算一件事(v5)：既不成立也不驳回，不入账、不成传闻——剧情上的伤明写治好不在此列；
       场外剧情(v11 衍生事件，origin=derived)只碰得到那一桩事所及的人与地，结恩怨亦然；纠缠者(situation.entangled)的去留、生死、拘押场外一概动不了；
       事件先于状态(v4)：某人对主角的非结构性关系(疑忌、感激……)不再立边、不再覆盖与阻尼，而是记进 bond 的恩怨账、由系统折叠成立场；
       结构性关系(随行、拘押、师徒、结义……)与暗中的心思仍是边；
       识名是一等指令(v6)：reveal 的 id 形 {"op":"reveal","id":某人,"key":"name"(,"to":某人)}——某人的姓名被说了出来，此刻在场的人都听见(to 则只那一人)；
       导演宣告与闸门从文字里听出来的是同一条指令、同一条写入通道。宽松规整导演的几种写法(set epithet 为本名、reveal 关系形 rel=姓名、push acquaintances/knows)；
       名字是谁的要看得见、谁听见要在耳边(v7)：被叫出名字的人须在 perspective.sight(耳边的活人或眼前的遗体——对着遗体叫出「容师叔」，满厅皆知死者是谁)，
       听的人须在 perspective.audience，场外无从得知；人人早已知道即原样不动；识名不是物理(落不了不废整拍)、不算因果污染；
       v7 立外号(set epithet)亦不算因果污染——叫法是主角眼中的主键(perspective.distinguish)，不是对原著的扰动；
       事码(v9)：一批后果先经 acts.expand——平常之事化为这十条指令照旧裁决，规则之事(拿取放下交给偷夺、撕合书写封拆读、脱身、对人群的杀伤)交 acts.perform 执行，
       记录写成下游认得的形状(易手仍是 set holder / push inventory，另有 money / squad / forge / doc 四种记录，describe 都说成人话)；
       银两(money)、器物的数量与钱袋(qty / purse / pages)、人群的人数伤亡与身上之物只经事码流转，直接写即驳回；人群只在近旁走动；被一群人围住(围攻)，主角的去留只有脱身
       人群随剧情走(v10)：赶来认人群(按道路里程核光阴)，在场性与结关系以 crowd.present 为准；一群人前往去哪都行，换了地方即不再围着谁；原著与场外剧情挪走带队之人，同处的人群随他走(_exec 外包一层)
       场外剧情(v11)：衍生事件是场外编剧写的、过了 world/plot 的规则审才排进日程，到期与原著同一条轨道落账(合不合天龙世界的规矩归 plot，这里只管物理)；
       场外叫不来人(要谁来到主角跟前，归近处导演写赶来)、报不了姓名(主角不在场)；揭开的隐情只入真相，随传闻抵达；
       近处导演改了某人的志向(set agenda)，此人的原著线就此变了(adrift)，往后的路交场外编剧
       v12 同行与押解随调遣：导演挪动一个人(前往、赶来)，他的同行者与人质(situation.carried)一并到同一处，每一次连带挪动都是一条成立的指令(带 by)——擒者走则人质随之由系统连带，不再交返工；原著与场外剧情挪人不带人
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

# ============================================================
#  指令集（只作用于既有实体）
#    set/add/push/pull : 改人物、门派、器物流转或主角(id="player")的属性；地点与景物只可改 state
#    link/unlink       : 增删关系边（恩怨、结义、师承……可带 secret）
#    reveal            : 让主角得知一条既有隐情，或发现一条暗路（src/dst 为暗路两端的地点）；id 形(v6)：某人的姓名被说了出来，在场者皆闻
#    arrive            : 不在身边的人来到此地——系统按其所在与道路、本回合光阴判断赶不赶得到
#    study / drain     : 研习秘籍或求教武学 / 以北冥神功吸人内力——增减多少由 world/growth 计算，不由 LLM 报数
# ============================================================
import re

from . import access, actor, body, bond, growth, perspective, situation, venue
from . import acts, crowd, stock  # 事码(v9)：LLM 说的类代码在这里化为指令或交 acts 执行；人群与银两的数由规则管
from .clock import PER_DAY
from .graph import PLIGHT, ROAD

OPS = {"set", "add", "push", "pull", "link", "unlink", "reveal", "arrive", "study", "drain"}
STATUSES = {"alive", "wounded", "dead"}
FROZEN_PLAYER_KEYS = {"name", "journal", "max_hp", "quests", "study", "hooks", "turn", "acquaintances", "cast", "pacing", "came_from", "en_route", "money",
                      "drift", "scene", "clocks", "arc", "spines", "setups"}
PLAYER_ALIASES = {"姿态": "posture", "气血": "hp", "功力": "power", "物品": "inventory", "随身": "inventory",
                  "武学": "skills", "武功": "skills", "位置": "location", "所在": "location"}
TERRAIN = {"location", "feature"}               # 地理：定义由创世数据给出，剧情只能改变其现状(state)
ITEM_FLOW = {"location", "holder", "hidden", "state", "spot"}  # 器物：定义不可改，只可流转、显隐、损耗，挪个方位(v8 spot：剑架上、茶几上)
OFFSCREEN = {"derived"}                          # 场外剧情(v11 衍生事件)：主角不在场，碰不到主角本人
RULED_BY = "rule"                                # 规则自己落的账(v11 药力、医治)：调用方(trade)已核过在场，不算哪一方写的剧情
RESOLVED_KEYS = {"location", "holder", "inventory", "skills", "faction"}  # 这些值是实体名，须经别名表归一
NUMERIC = {"hp", "power", "age"}                 # 数值属性：只可 set 或 add 一个数
LISTS = {"inventory", "skills", "conditions", "threads"}  # 清单属性：逐项 push/pull；境况与线头亦可整体 set 成一列文字
ENTITY_LISTS = {"inventory", "skills"}           # 实体清单只可逐件得失：整体改写会绕过"世上有没有此物"的校验
NOTE_LEN = 40                                    # 关系边上的印象一句话
SENTENCE = {"intent": actor.INTENT_LEN, "mood": actor.MOOD_LEN, "spot": 16}  # 人物身上的一句话属性；器物在一处地方的方位(v8)
STATUS_WORDS = {"alive": "安好无恙", "wounded": "负伤", "dead": "身亡"}
NAME = "name"                                    # reveal 的 id 形(v6)：某人的姓名被说了出来——认知唯一的落账通道
NAMEISH = {"姓名", "名字", "名号", "名姓", "真名", "身份", "来历", "name"}  # reveal 写成关系形、rel 说的是姓名


def _ids(op) -> list[str]:
    if op["op"] in ("link", "unlink") or (op["op"] == "reveal" and op.get("key") != NAME):
        return [op.get("src"), op.get("dst")]
    return [op.get("id")]


def named(op) -> bool:
    """识名指令(v6)：reveal 的 id 形。"""
    return isinstance(op, dict) and op.get("op") == "reveal" and op.get("key") == NAME


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


def things(world, spots) -> list[str]:
    """此刻在这些地方的器物(v11 按索引取，不扫全部器物)：落在那里的，连同那里的人(主角在其中即主角)手里、怀里所装的——
    与 place(器物) in spots 同一口径，按创世次序。"""
    g, spots, out = world.graph, set(spots), set()
    todo = ["player"] if world.here in spots else []
    for s in spots:
        for n in g.where(location=s):
            if g.kind(n) == "item":
                out.add(n)
            if n != "player":
                todo.append(n)
    while todo:
        for i in g.where(type="item", holder=todo.pop()):
            if i not in out:
                out.add(i)
                todo.append(i)
    return g.order(out)


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
    """一条指令的人话——回告编剧"什么没成立"时用，不让它去读 key=value。事码与它的记录(银两、人群、造物、文书)也在这里说成人话。"""
    if not isinstance(op, dict):
        return str(op)
    if acts.is_act(op):
        return acts.describe(op)
    kind, nid, key, v = op.get("op"), op.get("id"), op.get("key"), op.get("value")
    if kind == "money":
        who, src = ("主角" if x == "player" else str(x) for x in (nid, op.get("from")))
        return f"{who}{'得了' if v > 0 else '付出'}{stock.say(abs(v))}银子" + (f"（{src}给的）" if op.get("from") == "player"
                                                                        else f"（从{src}）" if op.get("from") and v > 0 else "")
    if kind == "squad":
        return f"{nid}被{'杀' if key == 'dead' else '打倒'}{stock.cn(v)}人"
    if kind == "trade":  # 买卖与服用(v11)
        word = {"bought": "买下", "sold": "卖出", "pawned": "当掉", "used": "服用了"}.get(key, key)
        return f"主角{word}{nid}" + (f"，花了{stock.say(op['price'])}" if key == "bought" and op.get("price")
                                    else f"，得了{stock.say(op['price'])}" if key in ("sold", "pawned") and op.get("price") else "")
    if kind == "service":
        return f"{op.get('by')}替主角办了{key}" + (f"（{stock.say(op['price'])}）" if op.get("price") else "")
    if kind == "lore":  # 打听来的话照原样说(可以是假的)：编剧照这句写进台词
        return f"{op.get('by')}说起：{v}"
    if kind == "forge":
        return f"{'主角' if op.get('by') == 'player' else op.get('by')}写成了{nid}"
    if kind == "doc":  # 逐键说成人话(不预先格式化：撕成几份只对 torn 有数可说)
        if key == "state":
            return f"{nid}{v}"
        if key == "read_by":
            return f"{'主角' if v == 'player' else v}读了{nid}"
        if key == "torn":
            return f"{nid}被撕成{stock.cn(v)}份"
        return f"{nid}拼合了" if key == "joined" else f"{nid}{key}"
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
    if kind == "reveal" and key == NAME:
        whose = "主角的名号" if nid == "player" else f"{nid}的姓名"
        return f"{name(op['to'])}得知{whose}" if op.get("to") else f"在场之人得知{whose}"
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
    if kind == "set" and key == "spot":
        return f"{nid}放到了{v}"
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
    for k in ("id", "src", "dst", "to"):
        if k in op:
            op[k] = resolve(world, op[k])
    _naming(world, op)
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


def _naming(world, op):
    """识名的几种写法规整成 reveal 的 id 形(v6)：导演想宣告「已知其名」时会写成——
    set epithet 为其本名(给段誉立外号「段誉」)、reveal 的关系形 rel=姓名、push 主角的 acquaintances 或某人的 knows。"""
    g, kind, key = world.graph, op.get("op"), op.get("key")
    person = lambda x: x == "player" or g.kind(x) == "person"
    if kind == "reveal" and op.get("rel") in NAMEISH and person(op.get("src")):
        who, to = op["src"], op.get("dst")
    elif kind == "reveal" and "src" not in op and "dst" not in op and op.get("id"):
        who, to = op["id"], op.get("to")
    elif kind == "set" and key == "epithet" and isinstance(op.get("value"), str) and g.kind(op.get("id")) == "person" \
            and op["id"] in (op["value"].strip(), world.aliases.get(op["value"].strip())):
        who, to = op["id"], None  # 给人立的「外号」就是他的本名：说的是他的名字被叫了出来
    elif kind == "push" and key in ("acquaintances", perspective.KNOWS) and person(op.get("id")):
        who, to = resolve(world, op.get("value")), op["id"]
    else:
        return
    op.clear()
    op.update({"op": "reveal", "id": who, "key": NAME, **({"to": to} if person(to) else {})})


def naming(world, op) -> dict | None:
    """这条指令若是在宣告识名(几种写法之一)，返回规整后的 reveal{id}；否则 None。不改动原指令——裁决器据此先核拍文有没有这回事。"""
    if not isinstance(op, dict):
        return None
    probe = {k: (resolve(world, v) if k in ("id", "src", "dst", "to") else v) for k, v in op.items()}
    _naming(world, probe)
    return probe if named(probe) else None


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
    if named(op):
        ends = [op.get("id"), *([op["to"]] if "to" in op else [])]
        return None if all(x == "player" or g.kind(x) == "person" for x in ends) else "说出姓名与听见的须是人"
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
        return None if g.kind(nid) == "person" or crowd.is_squad(g, nid) else f"「{nid}」不是人，无从到来"  # 死者亦可：遗体被人抬来；一群人(v10)也赶得来
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
        return f"器物由系统掌管，{nid}的定义不可改" + ("：数量与银两只经事码拿取、交给、偷取、夺取流转" if key in ("qty", "purse", "pages") else "")
    if key == "money":
        return "银两由规则结算：只经拿取、交给、偷取、夺取流转，不得直接增减"
    if crowd.is_squad(g, nid) and key in ("count", "down", "dead", "power", "pool", "kit", "disbanded", "hp", "status", "conditions"):
        return "人群的人数、伤亡与身上之物由规则结算：伤了倒了写打晕或杀死(数写几人)，拿东西写偷取、夺取"
    if key == "spot" and g.kind(nid) != "item":
        return "方位只记器物摆在哪里"
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


MOVERS = {"director": "director", "canon": "canon", "derived": "canon"}  # 调遣人物的两处来源：导演，与日程(原著连同场外剧情)


def _travel(world, op, origin) -> str | None:
    """一回合里一个人只听一处来源调遣：日程(原著连同场外编剧写的衍生事件)依序走位是一条轨道，导演是另一处——
    谁先挪动了他，别处就不能再把他挪走。日程不受里程约束：原著的日程本就压缩了旅途，衍生事件的路程在排进日程时已由 plot 核过(到期再核赶不赶得到)。"""
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
    return None


# ------------------------------------------------------------
#  在场性：谁能碰到谁
# ------------------------------------------------------------
def _reach(world, op, origin, scope, heading=frozenset()) -> str | None:
    if named(op):  # 名字是谁的要看得见(活人或眼前的遗体)，谁听见要在耳边(v7)：对着遗体叫出「容师叔」，满厅的人都知道了死者是谁
        if origin in OFFSCREEN:
            return "主角不在场，无从听见"
        if op["id"] not in perspective.sight(world):
            return f"{op['id']}不在你眼前，名字落不到人身上"
        to = op.get("to")
        return f"{to}不在你身边，听不见" if to and to not in perspective.audience(world) else None
    if op["op"] == "reveal" and origin == "director":
        return _seen(world, op, heading)
    if op["op"] == "arrive" and origin in OFFSCREEN:  # 主角眼前的人只有一个来路：近处导演写赶来，系统核路程(v11)
        return "场外叫不来人：要谁来到主角跟前，归近处导演写赶来"
    if origin in OFFSCREEN:  # 纠缠者的去留、生死、拘押只听导演与此地剧情；主角身边的人(v11)场外一概动不了——主角跟前的事归近处导演
        bound = [i for i in _ids(op) if i in situation.entangled(world)]
        if bound and (op["op"] in ("link", "unlink", "arrive") or op.get("key") in ("location", "status", "hp")):
            return f"{bound[0]}的行止系于主角，场外动不了"
        close = situation.around(world)
        by = [i for i in _ids(op) + ([op.get("value")] if op.get("key") == "holder" else []) if i in close]
        if by:
            return f"{by[0]}正在主角身边：主角跟前的事归近处导演"
    if op["op"] in ("link", "unlink") and origin in OFFSCREEN and scope is not None:  # 场外结恩怨，也只在那一桩事所及之处
        far = [i for i in (op["src"], op["dst"]) if i != "player" and i not in scope and place(world, i) not in scope]
        if far:
            return f"{far[0]}不在这桩事所及之处"
    if origin == "director" and op["op"] in ("link", "unlink"):
        return _bond(world, op)
    if origin in ("canon", RULED_BY) or op["op"] in ("link", "unlink", "reveal"):
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
            return "功力由系统结算：研习写 研习，吸功写 吸功，不得直接增减"
        close = situation.near(world)
        if g.kind(nid) == "person":  # 人在不在眼前只有一个口径：片区里没被带到跟前的人，导演够不着(要他来写 arrive)
            if nid not in situation.seen(world):
                return f"{nid}不在你身边，主角够不着"
        if crowd.is_squad(g, nid) and not crowd.present(world, nid) and nid not in set(getattr(world, "turn", {}).get("flock0", ())):
            return f"{crowd.handle(g, nid)}不在你跟前，要他们来写 赶来(系统按路程裁定)"
        if op.get("key") == "holder" and op.get("value") not in (None, "player") \
                and place(world, op["value"]) not in close:
            return f"{op['value']}不在此地，接不过{nid}"
        if op.get("key") == "holder" and op.get("value") == "player" and g.kind(nid) == "item":
            return None if _handy(world, nid, heading) else f"{nid}不在此地，够不着"
        return None if where in close else f"{nid}不在你身边，主角够不着"
    if origin in OFFSCREEN:
        if nid == "player" or op.get("value") == "player":
            return "场外剧情不得改动主角本人"
        if scope is not None and nid not in scope and where not in scope:
            return f"{nid}不在这桩事所及之处"
        return None
    return f"未知来源:{origin}"


def _self(world, op) -> str | None:
    """导演改主角本人：功力只由研习与吸功结算；武学须有来路——手边的秘籍(改作研习)或身边会它的人(求教)。"""
    key, v = op.get("key"), op.get("value")
    if op.get("id") != "player":
        return None
    if key == "power" and op["op"] in ("add", "set"):
        return "功力由系统结算：研习写 研习，吸功写 吸功，不得直接增减"
    if key == "skills" and op["op"] == "push" and v not in world.player["skills"]:
        return f"无从凭空习得{v}：手边有秘籍就写 研习，身边有人会就写 研习(物写那门武学)向他求教"
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
    flock = set(crowd.squads(world)) | set(getattr(world, "turn", {}).get("flock0", ()))  # 一群人(v10)：在跟前或回合开始时在跟前
    for end in (op["src"], op["dst"]):
        if end != "player" and g.kind(end) == "person" and end not in close:
            if op["op"] == "unlink" and op["rel"] == situation.FOLLOW:
                continue
            return f"{end}不在你身边，结不下「{op['rel']}」"
        if end != "player" and crowd.is_squad(g, end) and end not in flock and op["op"] == "link":
            return f"{crowd.handle(g, end)}不在你跟前，结不下「{op['rel']}」"
    return None


def _arrival(world, pid: str) -> str | None:
    """不在身边的人来到此地：须活着、在江湖中、不在溃退期，且本回合的光阴够他从所在之处赶来。"""
    g = world.graph
    if pid in situation.around(world) or (crowd.is_squad(g, pid) and crowd.present(world, pid)):
        return None
    if g.get(pid, "dormant") or g.get(pid, "hidden") or (crowd.is_squad(g, pid) and not crowd.active(world, pid)):
        return f"{pid}不在当下的江湖中"
    if crowd.is_squad(g, pid) and crowd.standing(g, pid) <= 0:
        return f"{crowd.handle(g, pid)}已无人站着"
    if situation.routed(world, pid):
        return f"{pid}新败而逃，不会这么快卷土重来"
    if situation.captors(world, pid):
        return f"{pid}身受拘押，来不了"
    where = g.get(pid, "location")
    days = g.distances(where).get(world.here, 99) if where else 99
    allow = getattr(world, "turn", {}).get("minutes", 0) // PER_DAY
    if days > allow:
        return f"{pid}身在{where}，距此{days}日路程，此刻赶不到"
    if crowd.is_squad(g, pid):
        return None  # 一群人的出没已由 active 判过
    return None if situation.debuted(world, pid) else f"{pid}此时还没在江湖上露面"  # 原著里还没登场的人：等他自己的那一回


def _note(world, text: str | list):
    """连带后果的说明（同伴跟上、研习进境、吸功多少）：交给编剧写进正文，交给近事记下。"""
    turn = getattr(world, "turn", None)
    if turn is not None and text:
        turn.setdefault("notes", []).extend([text] if isinstance(text, str) else text)


def _exec(world, op, origin) -> list[dict]:
    """一条指令落账，返回随之连带落账的指令(v12)。人群(v10)：一群人换了地方(前往、赶来)即不再围着原先的人；日程(原著与场外剧情)挪走带队之人，同在一处的这一门人群随他走。
    同行与押解随调遣(v12)：导演挪动一个人(前往、赶来)，他的同行者与人质(situation.carried)一并到同一处——每一次连带挪动都是一条成立的指令(带 by)；
    原著与场外剧情挪人不带人(回合末 situation.sunder 了断异地的同行)；人群不在此列，沿用随首领的规矩。"""
    g, nid = world.graph, op.get("id")
    moving = op["op"] == "set" and op.get("key") == "location"
    if (moving or op["op"] == "arrive") and crowd.is_squad(g, nid):
        crowd.relocate(world, nid, world.here if op["op"] == "arrive" else op.get("value"))
        if op["op"] == "arrive":
            situation.enlist(world, [nid])
            if getattr(world, "turn", None) is not None:
                world.turn.setdefault("arrived", set()).add(nid)
        return []
    old = g.get(nid, "location") if moving and g.kind(nid) == "person" else None
    band = situation.carried(world, nid, g.get(nid, "location")) if origin == "director" and (moving or op["op"] == "arrive") else []
    _exec_one(world, op, origin)
    if old is not None and origin in ("canon", "derived"):
        crowd.escort(world, nid, old)
    return _carry(world, op, nid, band)


def _carry(world, op, pid: str, band: list[str]) -> list[dict]:
    """同行者与人质随 pid 到同一处(v12)：记进本回合的调遣(movers)，赶来的上名册、记作赶来；连带写一句交编剧(用 id，引擎交编剧前过掩码)。"""
    if not band:
        return []
    g, turn = world.graph, getattr(world, "turn", None)
    dest, out = g.get(pid, "location"), []
    for q in band:
        g.set(q, "location", dest)
        g.nodes[q].pop("strayed", None)  # 导演挪动了他：回到原著的轨道上
        if turn is not None:
            turn.setdefault("movers", {})[q] = "director"
        if op["op"] == "arrive":
            situation.enlist(world, [q])
            if turn is not None:
                turn.setdefault("arrived", set()).add(q)
            out.append({"op": "arrive", "id": q, "by": pid})
        else:
            out.append({"op": "set", "id": q, "key": "location", "value": dest, "by": pid})
    _note(world, f"{'、'.join(band)}随{pid}" + ("一同来到" if op["op"] == "arrive" else f"同往{dest}"))
    return out


def _exec_one(world, op, origin):
    g, kind = world.graph, op["op"]
    turn = getattr(world, "turn", None)
    if kind == "set" and op.get("key") == "location" and g.kind(op.get("id")) == "person" and turn is not None \
            and g.get(op["id"], "location") != op.get("value"):
        turn.setdefault("movers", {}).setdefault(op["id"], MOVERS.get(origin, origin))
    if kind in ("set", "arrive") and (kind == "arrive" or op.get("key") == "location") and origin != "derived" \
            and g.kind(op.get("id")) == "person":
        g.nodes[op["id"]].pop("strayed", None)  # 原著与导演挪动了他：回到原著的轨道上(场外剧情带走的那一日由 lod.stray 记下)
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
    elif named(op):  # 姓名被说了出来：此刻在场的人都听见了(to 则只那一人)
        for who in _hearers(world, op):
            perspective.learn(world, who, op["id"])
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
        if op["value"] == "dead":
            g.nodes[op["id"]]["died"] = world.clock.day  # 死在这一局里(v11)：志向系于他的人，心愿了了或落了空(world/plot.awaken)
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
        if kind == "set" and key == "agenda" and origin == "director" and node.get("type") == "person" and value != node.get(key):
            node["adrift"] = True  # 眼前的剧情改了他的志向(心愿了了、另有所图)：原著线就此变了，往后的路交场外编剧(v11)
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
    """器物流转：持有与落地不兼存；交到主角手里即入随身，离开主角手里即出随身——黑板与图上的器物永远对得上账。
    方位(v8 spot)随流转而变：到了谁手里就没有方位，落在某处便是地上；原地没动(只是显露出来)则方位照旧。"""
    node = world.graph.nodes[item]
    if node.get("holder") == "player" and holder != "player":
        world.player.pull("inventory", item)
    if (node.get("holder"), node.get("location")) != (holder, location):
        node["spot"] = None if holder else "地上"
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
    if named(op):  # 人人早已知道他叫什么：不是一件事
        return all(perspective.knows(world, who, op.get("id")) for who in _hearers(world, op))
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
    return key in ("location", "holder", "faction", "hidden", "spot") and g.get(nid, key) == op.get("value")


def _hearers(world, op) -> list[str]:
    """识名指令的听者：写了 to 只那一人，否则此刻在场的人(说名字的人自己不算)。"""
    return [op["to"]] if op.get("to") else sorted(perspective.audience(world) - {op.get("id")})


def _moves_player(world, op) -> bool:
    if acts.is_act(op):
        return acts.moves_player(world, op)
    return isinstance(op, dict) and op.get("op") == "set" and op.get("id") in ("player", "主角", world.player["name"]) \
        and PLAYER_ALIASES.get(op.get("key"), op.get("key")) == "location"


def destination(op):
    """主角这一步要去的地方(指令的 value、事码的「到」)。"""
    return acts.destination(op) if acts.is_act(op) else (op.get("value") if isinstance(op, dict) else None)


def apply(world, ops: list, origin: str, scope: set | None = None) -> tuple[list, list]:
    """逐条落账；返回 (已成立, [(未成立的指令, 原因)])。导演触碰过的节点记为因果污染。
    主角的移动排到最后：一回合内发生的事都发生在回合开始的所在，同伴随行、器物易手不会因主角先走一步而"不在此地"。
    一回合里一个人只听一处来源调遣；主角走了，同伴随行跟上。"""
    applied, rejected = [], []
    ops = ops if isinstance(ops, list) else []  # 偶有把一条指令写成单值的：整批作废，不让世界崩
    ops = acts.expand(world, ops)  # 事码(v9)：平常之事化为指令，规则之事留作一件事交 acts 执行；旧写法的指令原样照收
    ops = [op for op in ops if not _moves_player(world, op)] + [op for op in ops if _moves_player(world, op)]
    heading = {v for op in ops if _moves_player(world, op) and isinstance(v := resolve(world, destination(op)), str)}  # 本批里主角要去的地方：先取物、后动身，取的是那里的东西
    for op in ops:
        if acts.is_act(op):  # 规则之事：前提、规则、执行都在 acts；不成即整条不成，什么也不动
            try:
                done, reason = acts.perform(world, op, origin, scope, heading)
            except (TypeError, AttributeError, KeyError, ValueError):
                done, reason = [], "格式不可解"
            if reason:
                rejected.append((op, reason))
                continue
            applied += done
            if origin == "director":
                world.taint.update(i for r in done for i in _ids(r) if isinstance(i, str) and i != "player")
            continue
        if not isinstance(op, dict) or op.get("op") not in OPS:
            rejected.append((op, "未知指令"))
            continue
        try:
            _normalize(world, op)
            if op.get("id") == "player" and op.get("key") in SENTENCE:
                continue  # 主角的心思与神色归玩家：导演替他写下的打算不算错，只是不入账，免得为此返工
            if op.get("key") == "spot" and (op.get("op") != "set" or not op.get("value")):
                continue  # 方位是软的(v8)：拿走时清掉方位由系统记，「去掉方位」之类不必写、也不算错
            _summon(world, op, origin)
            if _noop(world, op):
                continue  # 本就如此：既非成立也非驳回
            reason = _physics(world, op, heading) or _reach(world, op, origin, scope, heading) or _travel(world, op, origin)
        except (TypeError, AttributeError, KeyError):  # 畸形值（如列表当 id）：单条不成立，游戏不崩
            reason = "格式不可解"
        if reason:
            rejected.append((op, reason))
            continue
        if _moves_player(world, op) and crowd.besiegers(world) and op["value"] != world.here:  # 被一群人围住(v9)：走不脱，只有脱身
            rejected.append((op, f"被{'、'.join(crowd.handle(world.graph, x) for x in crowd.besiegers(world))}团团围住，走不脱：写脱身，成败看群战预裁"))
            continue
        if _moves_player(world, op):  # 远行：途中遇关或绝路即止步于前，光阴走满即途中歇脚；前半程照走，后半程回告编剧
            front = venue.door(world, op["value"])  # 走进店里(v11)：进的是前堂，掌柜伙计与货都在屋里
            if front:
                op["value"] = front
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
            applied += _exec(world, op, origin)
            toll = access.tolls(world, route)
            if toll and stock.pay(world, "player", toll):  # 过关付的关钱(v11)：barrier 已核过够不够
                _note(world, f"过关付了关钱{stock.say(toll)}")
            situation.muster(world, before)  # 走出了原来的近旁：跟前的人留在原处
            venue.settle(world)  # 走进店里、站到街上(v11)：近处的场所布好近景——伙计、陈设、货架
            applied.append(op)
            turn = getattr(world, "turn", None)
            if turn is not None and "route" in turn:  # 裁决器在场：同伴等诸拍落定再跟（拍中途解除随行的人不被带走）
                turn["route"] += route[1:]
            else:
                _note(world, situation.follow(world, route))
            continue
        extra = _exec(world, op, origin)
        applied.append(op)
        applied += extra  # 同行者与人质随之同去(v12)：连带挪动也是成立的指令
        if origin == "director" and not named(op) and op.get("key") != "epithet":  # 报个姓名、立个外号不算扰动原著：因果污染只记碰过的人与物
            world.taint.update(i for o in [op, *extra] for i in _ids(o) if i and i != "player")
    return applied, rejected
