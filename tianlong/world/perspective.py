"""
[INPUT]: 依赖 world/lexicon 的 Finding / table / find（实体名的最长匹配）、world/situation 的 seen / around / bodies（本回合见过的人、眼前之人、眼前的遗体），World 门面（graph / player / aliases / knowledge / turn）
[OUTPUT]: 对外提供 knows()（甲是否知乙姓名）、learn()、identified() / identify()（v12 识底：主角知不知道此人的头衔门派关系）、audience()（听得见的人：主角与此刻耳边的人——眼前与同行，时间轴上那一刻的听众优先）、sight() / remains()（v7 名字落得到的人：耳边的活人，连同眼前的遗体）、
          moment()（v7 在时间轴的某一刻听写与落账：那一刻的听众与遗体，出来即复原）、seed()（开局相识）、handle()（主角眼中某人的叫法）、by_handle()、surname()、
          guise()（不论识不识名，此人在主角眼中的样子：外号或外貌）、distinguish()（v7 叫法即主键：撞了叫法的几人各分一个稳定外号，返回 set epithet 指令）、
          calls()（v7「姓+称谓」→ 其人：称谓按男女分，同姓的几人都不收）、
          hear()（v6 听写器：一段文字里被说出来的名字 → 识名指令 reveal{id}，拍文与正文共用；miss 收下认不出是谁的「互通姓名」）、speaker()（台词的说话人）、doer()（v7 某处那件事是谁做的：台词不隔断，写着别人却认不出即 False，没写主语即 None）、
          audit()（逐拍：先听——听来的名字交调用方的 commit 落账；再查称谓——叫出不该知道的名字即违例，主角叫错与 NPC 叫出主角姓名交返工，NPC 之间只记一笔）、
          mask()（主角不识名之人换成叫法、不知主角姓名者口中的主角换成泛称；落不了账的自报家门只去掉名字）、
          veil()（把玩家视锥译成主角的视角：不识名之人只剩外貌叫法，身份与关系一概不露；v5 随身之物、地上器物、传闻、地点现状与设定一并过掩码；
          v8 器物是 world/scenery 的卡片(名字、等级、方位、类别、描述、属性、内容)，名字过 thing、其余过 mask，景物的描述与现状亦然）、
          thing()（器物在主角眼中的叫法：名字里带着不识之人的名号就只叫那件东西本身）
[POS]: v11 伙计(staff)只有职名：guise 叫他的职名(掌柜、店小二)，同职几人再由 distinguish 分外号。
        world 层的认知视角——「视角即上下文」：每段文字都从某个视角写出，那个视角不知道的名字就不给它。
       识名是认知最表层的一环：主角初见钟灵，只知是「大眼圆脸的少女」；她自报姓名、或认得她的人当面叫她，主角才知道她叫钟灵。
       人物之间：原著里有关系、同一门派即互相识名，戏里听见的另记在人物节点的 knows 上；主角所识之人记在黑板的 acquaintances 上（系统维护，导演写不动）。
       纯规则、零调用：追认只增加认知，从不挪动任何人；查不出的旁白漏名，由 mask 在交编剧之前确定性地换掉——不给即不泄露
       veil 连人物眼下之事(intent)一并过 mask——那一句是导演写的，里面的名字主角未必识得；
       v5：四十一件器物的名字本身带着人名(云中鹤钢爪)、近日传闻与器物描述也写着名字，都在交编剧之前换成主角看得见的说法；
       mask 以本回合见过的人(situation.seen)为「当面」：刚从眼前走开的生人(原著来把他带走)仍只叫外貌——走开了就换回名字，等于替主角认出了他
       v6 识名是一等事件、认知由叙述构成：玩家读到了谁的名字被说出来，就知道了它——听写器只产出指令(reveal 的 id 形)，落账归 effects，
       认知与物理同一条写入通道(本模块不 import effects：audit 收调用方给的 commit)；导演的拍与编剧的正文过同一张词表——
       自报家门(在下大理段誉、姓段单名一个誉字、小弟某某、某某便是在下)、旁白里的互报姓名与「自称某某」、认得的人当面点名；
       说话人认不出时名字本身就是说话人(「小生段誉」只能是段誉说的)；旁白里的「他」「那少女」「二人」落到此刻与主角打交道的人(near)；
       谁听见由文字定：当众说的满场皆闻，说给某人的(拍的 to、旁白里的「向某人」、低声耳语)只那人与主角知道；被主角甩在身后的人听不见；
       v7 叫法即主键：主角叫不出名字的人，叫法就是他在账上、正文、选项、补记里唯一的称呼——四个「无量剑东宗的少年」落笔之前各分一个外号
       (手里有兵刃的叫持剑的，否则按 id 的稳定散列取一个外貌字眼，同组不重样)，立下不改，人散了也不改回；「容师叔」「钟姑娘」也是叫法，calls 让它落得回原人；
       名字是谁的(看得见)与谁听见(在耳边)是两个角色：对着遗体叫出的名字落在死者身上，听见的是耳边的活人——时间轴上的某一刻两样都记着(moment)；
       称谓添了师叔、师伯、师父、师傅、师娘(同门之间最常见的叫法)
       v12：mask 把本回合望见的人当作见过(只叫外貌)，veil 另过远处可见；veil 对人群的首领与眼下之事过掩码；识名不等于识底——识名而未识底的人头衔门派不露、关系行只留两端都识底的，hear 在报名那一句里认出头衔即带 know:身份；
       v9：thing 让分出来的那一份(玉壁剑影图·1)叫回那件东西、剧中人写下的文书叫作「你写给某人的书信」(主角经手、读过或是收信人才知道谁写给谁，收信人照旧只叫外貌)；veil 另过人群的描述
       v10：handle 让一群人叫他们的叫法(东宗弟子)，随行的人群在编剧那里也是叫法
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import contextlib
import copy
import re
import zlib

from . import lexicon, situation
from .ledger import famous

KNOWS = "knows"                   # 人物节点属性：此人在戏里听来的名字（含 "player"）
COMPOUND = ("慕容", "司空", "南宫", "欧阳", "上官", "东方", "诸葛", "公孙", "皇甫", "令狐", "司马", "独孤", "赫连", "完颜",
            "耶律", "端木", "呼延", "尉迟", "宇文", "长孙", "夏侯", "澹台", "萧远")
TITLE = "兄台|兄弟|兄|大哥|大侠|少侠|公子|姑娘|姐姐|妹子|妹妹|小姐|夫人|先生|前辈|老爷子|老爷|大爷|掌门|帮主|谷主|施主|师兄|师弟|师姐|师妹|师叔|师伯|师父|师傅|师娘|娘子|大嫂|伯伯|叔叔|贤弟|贤侄|相公"
HERS = {"姑娘", "姐姐", "妹子", "妹妹", "小姐", "夫人", "师姐", "师妹", "师娘", "娘子", "大嫂"}  # 只叫女子的称谓
HIS = {"兄台", "兄弟", "兄", "大哥", "大侠", "少侠", "公子", "先生", "老爷子", "老爷", "大爷", "师兄", "师弟", "师叔", "师伯",
       "伯伯", "叔叔", "贤弟", "贤侄", "相公"}  # 只叫男子的称谓；其余(前辈、掌门、施主、师父……)男女皆可
QUOTE = re.compile(r"[「“『]([^」”』]*)[」”』]")
APPOSITIVE = re.compile(r"(?:少年|少女|汉子|老者|女子|妇人|僧人|书生|弟子|姑娘|公子|青年|道人|孩童|老汉|大汉|壮汉)$")  # 「东宗少年龚光杰」：前面已有叫法，名字直接去掉
NOUNS = "少年|少女|女子|汉子|老者|妇人|书生|和尚|僧人|番僧|道人|道士|道姑|壮汉|姑娘|公子|老人|老妇|孩童|男子|丫头|童子|大汉|姑子|婢女"
NOUN = re.compile(f"(?:{NOUNS})$")
# 听写的词表(v6)：自称之后可隔一个地名或门派(在下大理段誉)，隔着动词与虚词的不算(在下久闻段誉、我是来找段誉的)
SELF_WORDS = ("小生|在下|我叫|我是|我乃|我便是|我就是|本人|鄙人|区区|小可|晚生|晚辈|小弟|愚兄|小女子|小妹|奴家|妾身|老身|老夫|老衲|"
              "贫僧|贫道|贫尼|洒家|俺|老子|本姑娘|姑娘我|本座|本公子|学生|后学|小人|名叫|叫做|唤作|名唤")
GAP = r"[^，,。！？；;、…\s「」“”『』的之与和同跟替为给向对找寻见了着过把被让请也都还闻慕认识知听拜访想念问等候说道叫喊陪伴随带领将要会能可]"
SELF = re.compile(rf"(?:{SELF_WORDS})(?:乃是|便是|就是|正是|即是|乃|是)?{GAP}{{0,8}}$")
OWN = re.compile(r"^(?:便是|就是|正是|即是|乃是)(?:在下|我|小生|本人|老夫|贫僧|小女子|晚辈|小弟|区区|洒家|俺|本姑娘)|^是也")  # 「段誉便是在下」
SPELLED = re.compile(r"(?:复姓|姓)([\u4e00-\u9fff]{1,2})[，,、\s]*(?:单名一个|单名|双名|名叫|名唤|名为|名字叫|名字是|叫做|唤作|名|叫|唤)"
                     r"([\u4e00-\u9fff]{1,3}?)(?=字|[，,。！？；、\s」”』]|$)")  # 「小生姓段，单名一个誉字」
MUTUAL = re.compile(r"(?:互|彼此|相互|互相|各自?)(?:通|报|道|叙|告)(?:了|过)?(?:姓名|名号|名姓|名字)|通名报姓|通了姓名|叙了姓名|通过姓名|互通了?名")
TELL = re.compile(r"(?:自报|报上|报出|报了|报过|通报了?|道出|说出|说了|道了|告知|告以|自道)(?:了|过)?(?:自己的|他的|她的)?(?:姓名|名号|家门|来历|名字|名姓|身份)"
                  r"|以(?:姓名|名号)相告")
CALLED = re.compile(r"(?:自称|自报|名叫|叫做|唤作|名唤|原来叫|原来是|原来便是|正是|便是)$")  # 旁白点明：「那少年自称段誉」「原来她就叫钟灵」
GROUP = re.compile(r"二人|两人|你们|你俩|他俩|她俩|双方|彼此")
PLAIN = r"[^向对朝冲跟与和同把将被给替为从在见望看瞧听扯拉拽抓握扶，,。！？；;、\s「」“”『』]"  # 泛称之前的修饰语里没有介词与动作
LEAD = re.compile(r"^(?:那|这|只见|却见|但见|忽见|只听|忽听|却听|但听|此时|这时|当下|旁边|一旁|身旁|身边|座上|梁上|门外|厅中|便|又|也|却|已|早已|当即|随即|于是|的)+")
SAYS = re.compile(r"^[，,\s]*([^，,。！？「“『]{1,10}?)(?:道|说|问|答|喝|叫|喊|笑|叹|应)")


# ============================================================
#  识名：谁知道谁叫什么
# ============================================================
def knows(world, a: str, b: str) -> bool:
    """a 是否知道 b 的姓名。主角看黑板；人物之间看原著关系、同门与戏里听来的。"""
    if a == b:
        return True
    g = world.graph
    if a == "player":
        return b in world.player["acquaintances"]
    if g.kind(a) != "person":
        return True
    if b in (g.get(a, KNOWS) or []):
        return True
    if b == "player":
        return False
    fa = g.get(a, "faction")
    if fa and fa == g.get(b, "faction"):
        return True
    return any({e["src"], e["dst"]} == {a, b} for e in g.relations(a))


def learn(world, who: str, target: str) -> bool:
    """who 得知 target 的姓名；返回是否新知。"""
    if knows(world, who, target):
        return False
    if who == "player":
        world.player.push("acquaintances", target)
    else:
        node = world.graph.nodes[who]
        node[KNOWS] = (node.get(KNOWS) or []) + [target]
    return True


def identified(world, pid: str) -> bool:
    """主角知不知道此人的底细(v12)：头衔、门派、关系——识名不等于识底。段誉只报了「小生段誉」，主角不该就此知道他是镇南王世子。"""
    return pid == "player" or pid in (world.player.get("identified") or [])


def identify(world, pid: str) -> bool:
    """主角得知此人的底细(v12)：开局常识(seed)、或戏里有人说破来历(识名事码带 知:身份，听写器在报名的那句里认出他的头衔)。返回是否新知。"""
    if identified(world, pid) or world.graph.kind(pid) != "person":
        return False
    world.player.push("identified", pid)
    return True


def _titled(world, pid: str, text: str) -> bool:
    """这句话里说破了此人的来历(v12)：他头衔的某一段(两字以上)原样出现在报名的那一句里——「小生大理段誉，镇南王世子」。"""
    title = world.graph.get(pid, "title") or ""
    return any(len(part.strip()) >= 2 and part.strip() in text for part in re.split(r"[、，,]", title))


def audience(world) -> set[str]:
    """听得见的人(v6)：此刻在主角耳边的——主角、眼前之人与同行者(活着的)。回合开始时在、后来被主角甩在身后的人听不见：
    主角在密林里报的名，剑湖宫厅上的人不会知道。裁决器逐拍听写时把那一拍的听众记在 turn["ears"](说话时在场的，连同这一拍赶来的)。"""
    ears = (getattr(world, "turn", None) or {}).get("ears")
    if ears is not None:
        return set(ears) | {"player"}
    g, party = world.graph, set(situation.party(world))
    return {"player"} | {p for p in situation.around(world) | party
                         if g.kind(p) == "person" and g.get(p, "status") != "dead"
                         and (p in party or g.get(p, "location") == world.here or situation.area(world, g.get(p, "location") or ""))}  # v14 同一屋里的才听得见：大厅里一句「段公子」，门房的门丁听不见(run3 第 13、18 回)


def remains(world) -> set[str]:
    """眼前的遗体(v7)：叫得出名字、却听不见的人——时间轴上的某一刻(turn["ears"] 设着)取那一刻的，否则取此刻的。"""
    turn = getattr(world, "turn", None) or {}
    return set(turn.get("bodies") or ()) if turn.get("ears") is not None else situation.bodies(world)


def sight(world) -> set[str]:
    """名字落得到的人(v7)：耳边的活人，连同眼前的遗体。名字是谁的(看得见)与谁听见(在耳边)是两回事——
    对着遗体叫一声「容师叔」，满厅的人都知道了死者是谁；死者自己听不见，也不必听见。"""
    return audience(world) | remains(world)


@contextlib.contextmanager
def moment(world, ears=None, bodies=()):
    """在时间轴的某一刻听写与落账(v7)：那一刻耳边的活人听得见、那一刻眼前的遗体叫得出名字；ears 为 None 即此刻，不另设。
    裁决器的逐拍听写、出闸的逐段听写、结算单的落账都经这里进出那一刻，出来即复原——不留在本回合的瞬时账上。"""
    if ears is None:
        yield
        return
    world.turn["ears"], world.turn["bodies"] = set(ears), set(bodies)
    try:
        yield
    finally:
        world.turn.pop("ears", None)
        world.turn.pop("bodies", None)


HOSTS = re.compile(r"掌门|帮主|谷主|庄主|宫主|岛主|方丈")


def seed(world, also=()):
    """开局相识：出身里写到的人（随从之于马五德、王府小吏之于段誉）与主角互相识名；also 另加（旧档里与主角已有交情的人）。
    开场之地当众主持其事的一派之主（剑会上的左子穆、辛双清），主角与在座诸人都叫得出名字——他们却不识得一个随从。
    v12 识底：出身带来的人、当众主持的掌门、江湖闻名之人(ledger.famous)，主角开局即知其底细。"""
    g, tab = world.graph, lexicon.table(_surfaces(world))
    for p in {pid for pid, _, _ in lexicon.find(world.player["origin"] or "", tab)} | set(also):
        if g.kind(p) == "person":
            learn(world, "player", p)
            learn(world, p, "player")
            identify(world, p)
    present = g.where(type="person", location=world.here)
    for p in present:
        if HOSTS.search(g.get(p, "title") or ""):
            identify(world, p)
            for q in ["player", *present]:
                if q != p:
                    learn(world, q, p)
    for p in g.order(n for n in g.of("person") if famous(g.nodes[n])):
        identify(world, p)


# ============================================================
#  叫法：主角不识名之人，只叫得出外貌
# ============================================================
def surname(name: str) -> str | None:
    if not isinstance(name, str) or len(name) < 2 or len(name) > 3:
        return None
    return next((c for c in COMPOUND if name.startswith(c) and len(name) > len(c)), name[0])


FEMININE = re.compile(r"女|婢|娘|婆|妇|姑|嫂|姐|妹|妪|尼")


def _noun(g, pid: str) -> str:
    title, faction = g.get(pid, "title") or "", g.get(pid, "faction") or ""
    if "僧" in title or "方丈" in title or faction == "少林派":
        return "僧人"
    if any(w in title for w in ("幼儿", "幼子", "孩童", "小孩")):
        return "孩童"
    age = g.get(pid, "age")
    female = g.get(pid, "gender") == "女" or (not g.get(pid, "gender") and bool(FEMININE.search(title)))  # v14 伙计没写男女，看职名：婢女不叫「短须婢女」(run4 第 20 回)
    young = (age or 30) < 21 or any(w in title for w in ("少女", "弟子", "婢女", "小姐", "世子", "公子"))
    if female:
        return "少女" if young else "妇人" if any(w in title for w in ("夫人", "王妃", "遗孀", "主人")) else "女子"
    return "少年" if young else "老者" if "老" in (g.get(pid, "appearance") or "") else "汉子"


def handle(world, pid: str) -> str:
    """主角眼中此人的叫法：识名则叫名字；不识名则叫外号或外貌(guise)——前后一致。"""
    if world.graph.kind(pid) == "group":  # 一群人(v10)叫的是他们的叫法(东宗弟子)，不是 id
        return world.graph.get(pid, "handle") or pid
    if pid == "player" or world.graph.kind(pid) != "person" or knows(world, "player", pid):
        return pid
    return guise(world, pid)


def guise(world, pid: str) -> str:
    """不论识不识名，此人在主角眼中的样子：导演或系统立的外号(epithet)，没有就照外貌、门派生成。补记「青衫少年原来名叫段誉」要用它。"""
    g = world.graph
    if g.get(pid, "epithet"):
        return g.get(pid, "epithet")
    if g.get(pid, "staff") and g.get(pid, "role"):  # 伙计(v11)只有职名：掌柜、店小二、坐堂大夫——人人这样叫他
        return g.get(pid, "role")
    look = re.split(r"[，。；、]", g.get(pid, "appearance") or "")[0].strip()
    if look and NOUN.search(look) and len(look) <= 6:
        return look
    noun, faction = _noun(g, pid), g.get(pid, "faction")
    return f"{look[:5]}的{noun}" if look else f"{faction}的{noun}" if faction else f"一名{noun}"  # 无外貌可写：衣着门派是看得见的


def address(world, pid: str) -> str:
    """当面称呼一个不知其名的人：姑娘、兄台、前辈。"""
    g = world.graph
    if pid == "player":
        return "兄台"
    if g.get(pid, "gender") == "女":
        return "姑娘" if _noun(g, pid) == "少女" else "这位夫人" if _noun(g, pid) == "妇人" else "姑娘"
    return "大师" if _noun(g, pid) == "僧人" else "前辈" if _noun(g, pid) == "老者" else "兄台"


# ============================================================
#  叫法即主键(v7)：主角眼中叫不出名字的人，叫法两两不同——撞了名的几人在任何人落笔之前各分一个稳定的外号
# ============================================================
TRAITS = {"少年": ("高个", "瘦削", "黑脸", "白面", "方脸", "浓眉", "圆脸", "长脸"),
          "少女": ("瓜子脸", "鹅蛋脸", "梳双髻", "细眉", "圆脸", "高挑"),
          "女子": ("高挑", "瘦削", "细眉", "鹅蛋脸", "梳髻", "白净"),
          "妇人": ("高挑", "清瘦", "微胖", "白净", "细眉", "梳髻"),
          "汉子": ("络腮胡", "短须", "粗壮", "高个", "黑脸", "方脸", "独眼", "秃顶"),
          "老者": ("白须", "清瘦", "驼背", "矮胖", "长眉", "秃顶"),
          "僧人": ("高大", "瘦削", "长眉", "年轻", "黑脸", "矮胖")}
ARMS = re.compile(r"[剑刀枪棍鞭杖扇钩爪斧锤戟]$")


def distinguish(world) -> list[dict]:
    """主角眼前(含近旁遗体)叫不出名字的人里，叫法撞了的几个各分一个外号：手里有兵刃的叫「持剑的」，否则按 id 的稳定散列取一个外貌字眼
    (「无量剑东宗的高个少年」)，同组之内、同在眼前之人之间不重样。返回立外号的指令(set epithet)交 effects 落账——
    外号一经立下就是此人在主角眼中的名字，人散了也不改回：叫法是主角眼中的主键，正文、选项、账房、导演说的是同一个人。"""
    g = world.graph
    view = sorted(situation.around(world) | situation.bodies(world))
    groups: dict[str, list[str]] = {}
    for p in view:
        if not knows(world, "player", p):
            groups.setdefault(guise(world, p), []).append(p)
    taken, ops = set(groups), []
    for h, group in groups.items():
        if len(group) < 2:
            continue
        noun = next((n for n in NOUNS.split("|") if h.endswith(n)), "")
        head = (h[:-len(noun)] if noun else "").removeprefix("一名")
        for p in group:
            arms = [thing(world, i) for i in g.where(type="item", holder=p) if not g.get(i, "hidden") and ARMS.search(thing(world, i))]
            pool = [f"持{arms[0][-1]}"] if arms else []
            pool += sorted(TRAITS.get(noun) or TRAITS.get(_noun(g, p)) or TRAITS["汉子"], key=lambda t: zlib.crc32(f"{p}{t}".encode()))  # v14 婢女、书生这类叫法没有自己的外貌表，按此人是谁取
            name = next((f"{head}{t}{noun}" if noun else f"{t}的{h}" for t in pool
                         if (f"{head}{t}{noun}" if noun else f"{t}的{h}") not in taken), None)
            if name:
                taken.add(name)
                ops.append({"op": "set", "id": p, "key": "epithet", "value": name})
    return ops


def by_handle(world, name: str) -> str | None:
    """「绿衫少女」落到在场的那个人：编剧与玩家只知道叫法。"""
    if not isinstance(name, str) or not name:
        return None
    return next((p for p in sorted(situation.around(world)) if not knows(world, "player", p) and handle(world, p) == name), None)


def _surfaces(world) -> dict[str, str]:
    """人名的一切写法 → id：正名、别名、去「·」写法。"""
    g = world.graph
    out = {n: n for n in g.of("person")}
    out.update({a: n for a, n in world.aliases.items() if g.kind(n) == "person"})
    return out


def calls(world, people) -> dict[str, str]:
    """这几个人被「姓 + 称谓」叫的说法 → 其人(v7 叫法即主键：容师叔、钟姑娘、段公子也落得回原人)。
    称谓按男女分(马五德不是「马夫人」)；同姓的几人都不收——宁可认不出，不认错人。"""
    g, by = world.graph, {}
    for p in sorted(people):
        if g.kind(p) == "person" and surname(p):
            by.setdefault(surname(p), []).append(p)
    out = {}
    for s, (p, *more) in by.items():
        if not more:
            off = HIS if g.get(p, "gender") == "女" else HERS
            out.update({s + t: p for t in TITLE.split("|") if t not in off})
    return out


def _calls(text: str, pid: str, name: str) -> list[tuple[int, int]]:
    """text 里以「姓 + 称谓」叫 pid 的位置：钟姑娘、王兄、段公子。"""
    s = surname(name)
    if not s:
        return []
    return [(m.start(), m.end()) for m in re.finditer(re.escape(s) + f"(?:{TITLE})", text)]


# ============================================================
#  听写(v6)：文字里谁的名字被说了出来——拍文与正文共用一张词表；只产出指令，落账归 effects
# ============================================================
HEDGE = re.compile(r"莫非|难道|或许|也许|大概|似乎|只怕|想必|多半|未必|不知|若是|倘若|如果|心想|暗想|寻思|想来|猜")


def _unique(world, people) -> dict[str, str]:
    """在场生人的叫法 → 其人；两人同一叫法(四个「无量剑东宗的少年」)就都不收——宁可认不出，不认错人。"""
    out: dict[str, str | None] = {}
    for p in sorted(people):
        if p != "player" and world.graph.kind(p) == "person" and not knows(world, "player", p):
            h = handle(world, p)
            out[h] = None if h in out else p
    return {h: p for h, p in out.items() if p}


def _tables(world, present) -> tuple[list, list]:
    """听写的两张名表：names 只收真名(人名、别名、主角名号)——台词里说出来的才算名字；
    who 另收在场生人的叫法——认主语与说话人用(编剧笔下的「青衫少年」就是段誉)，叫法不是名字，说出叫法不算报了姓名。"""
    me, names = world.player["name"], _surfaces(world)
    if len(me) >= 2:
        names[me] = "player"
    return lexicon.table(names), lexicon.table({**_unique(world, present), **names})


def _subject(world, clause: str, tab, near) -> str | None | bool:
    """一个分句的主语：开头(去掉「那」「只见」之类)是人——「你」即主角，名字或叫法即其人，「他」「她」与泛称(那少女)落到 near 里唯一对得上的人；
    开头是个认不出的人返回 False；开头不是人(动词起句：「扯住你的衣袖低呼」)返回 None，承上一分句。"""
    c = LEAD.sub("", clause.strip().lstrip("「」“”『』"))  # 台词已换成「」占位：占位之后才是这一分句的主语
    if not c:
        return None
    if c.startswith("你"):
        return "player"
    hit = lexicon.find(c[:16], tab)
    if hit and hit[0][1] == 0:
        return hit[0][0]
    m = re.match(rf"^(他|她)|^{PLAIN}{{0,6}}?({NOUNS})", c)  # 「向那青衫少年抱拳」是介词短语，不是主语
    if not m:
        return None
    g = world.graph
    if m.group(1):
        pool = [p for p in near if p != "player" and (g.get(p, "gender") == "女") == (m.group(1) == "她")]
    else:
        pool = [p for p in near if p != "player" and (_noun(g, p) == m.group(2) or handle(world, p).endswith(m.group(2)))]
    pool = list(dict.fromkeys(pool))
    return pool[0] if len(pool) == 1 else False


def _agent(world, head: str, tab, near) -> str | None:
    """一句话里、某处之前那件事是谁做的：离它最近的有主语的分句(动词起句的分句承上一分句)；认不出即 None。"""
    for clause in reversed([c for c in re.split(r"[，,；;：:]", head) if c.strip()]):
        who = _subject(world, clause, tab, near)
        if who is not None:
            return who or None
    return None


def doer(world, text: str, at: int, near=(), tab=None) -> str | None | bool:
    """text[at] 处那件事是谁做的(v7)：同一句里它之前离它最近的主语，台词不隔断(「你朗声道：「告辞！」出了练武厅」仍是你)——
    主角即 "player"，认得的人即其 id，写着别人却认不出是谁即 False，整句没有主语即 None(第二人称叙事里多半是你)。"""
    tab = tab or _tables(world, audience(world))[1]
    head = re.split(r"[。！？\n]", QUOTE.sub("「」", text[:at]))[-1]
    for clause in reversed([c for c in re.split(r"[，,；;：:]", head) if c.strip()]):
        who = _subject(world, clause, tab, near)
        if who is not None:
            return who
    return None


def speaker(world, text: str, start: int, end: int, tab=None, near=()) -> str | None:
    """text[start:end] 这段台词是谁说的：台词之前同一句里离它最近的主语；台词之前没有人，看台词之后的「某某道」。
    认不出即 None——宁可不认，不认错人(不认的台词照旧过掩码，只是不替说话人补上他不该知道的名字)。"""
    tab = tab or _tables(world, audience(world))[1]
    who = _agent(world, re.split(r"[。！？\n」”』]", text[:start])[-1], tab, near)
    if who:
        return who
    m = SAYS.match(text[end:end + 14])
    return (_subject(world, m.group(1), tab, near) or None) if m else None


def _introduced(q: str, a: int, b: int) -> bool:
    """台词 q 里 q[a:b] 这个名字是自报家门报出来的(「小生段誉」「在下大理段誉」「段誉便是在下」)，不是「我是段誉的朋友」。"""
    return bool(SELF.search(q[max(0, a - 16):a]) and q[b:b + 1] not in ("的", "之", "们")) or bool(OWN.match(q[b:]))


def _spell(tab, sur: str, given: str) -> str | None:
    """「姓段，单名一个誉字」拼回全名，落到名表里的人。"""
    names = dict(tab)
    return next((names[f] for f in (sur + given, given, sur + given[:1], sur + given[:2]) if f in names), None)


WHISPER = re.compile(r"低声|悄声|压低|附耳|耳语|凑近|俯身|轻声")
TOWARD = re.compile(r"(?:向|对|朝|冲|跟)着?(?:那位|这位|那|这)?$")  # 「向那青衫少年」「对着这位姑娘」


def _listeners(world, head: str, s, to, tab, near) -> set[str] | None:
    """这段台词说给谁听(v6)：拍写了对象，或旁白写着「向那青衫少年」「压低嗓子」，就只有那人(与在场的主角)听见；
    否则是当众说的，在场的人都听见(None)。满厅十几个人，主角凑上去低声报的名，梁上的人听不见。"""
    if not to:
        hit = [p for p, a, _ in lexicon.find(head, tab) if TOWARD.search(head[max(0, a - 4):a]) and p != s]
        to = hit[-1] if hit else (near[0] if WHISPER.search(head) and len(near) == 1 and near[0] != s else None)
    return None if not to or to == s else {to, "player"} - {s}


def hear(world, text: str, who=None, to=None, near=(), present=None, miss=None) -> list[dict]:
    """一段文字里被说出来的名字 → 识名指令 [{"op":"reveal","id":某人,"key":"name"(,"to":听者)}]。
    当众说的在场者都听见；说给某人听的(拍的 to、旁白里的「向某人」、低声耳语)只那人与主角听见。
    who/to：拍的说话人与对象(正文没有，台词的说话人由 speaker 认出)；near：此刻与主角打交道的人(旁白里的「他」「那少女」「二人」所指)；
    present：听得见的人(缺省 audience)，说出名字的得在其中；被叫出名字的可以是其中之人，也可以是眼前的遗体(v7 remains)。
    miss 给了就收下认不出是谁的「互通姓名」「自报家门」。"""
    if not text:
        return []
    me = world.player["name"]
    present = audience(world) if present is None else set(present) | {"player"}
    faces = present | remains(world)  # 名字落得到的人：耳边的活人，连同眼前的遗体
    names, whos = _tables(world, present)
    who = "player" if who in ("player", "主角", me) else who
    to = "player" if to in ("player", "主角", me) else to
    to = to if to in present else None
    near = [p for p in dict.fromkeys([who, to, *near]) if p and p in present]
    said: list[tuple] = []
    known: set[str] = set()  # 报名的那一句里连来历一并说破的人(v12 识底)

    def say(pid, ears=None, where=""):
        if pid not in faces:
            return
        if where and _titled(world, pid, where):
            known.add(pid)
        for ear in ([None] if ears is None else sorted(set(ears) - {pid})):
            if (pid, ear) not in said:
                said.append((pid, ear))

    for m in QUOTE.finditer(text):  # 台词：自报家门、认得的人当面点名
        q, head = m.group(1), re.split(r"[。！？\n」”』]", text[:m.start()])[-1]
        s = who if who in present else speaker(world, text, m.start(), m.end(), whos, near)
        aimed = to if who in present else None
        ears = _listeners(world, head, s, aimed, whos, near)
        for pid, a, b in lexicon.find(q, names):
            if _introduced(q, a, b):  # 「小生段誉」「在下郑大风」只能是本人说的：名字本身就是说话人，听者按本人说给谁算
                say(pid, ears if s == pid else _listeners(world, head, pid, aimed if who == pid else None, whos, near), q)
            elif s and s != pid and knows(world, s, pid):
                say(pid, ears, q)  # 认得他的人当面叫出(连来历一并说破即识底)
        for x in SPELLED.finditer(q):  # 「姓段，单名一个誉字」：说的人认不认得都一样，读者读到了这个名字
            pid = _spell(names, x.group(1), x.group(2))
            if pid:
                say(pid, ears, q)
        if s:
            for p in sorted(faces - {s}):
                if knows(world, s, p) and _calls(q, p, me if p == "player" else p):
                    say(p, ears, q)
    last: list[str] = []
    for sent in re.split(r"[。！？\n]", QUOTE.sub("「」", text)):  # 旁白：互通姓名、自报家门、点明某人叫什么
        people = [p for p, _, _ in lexicon.find(sent, whos) if p != "player" and p in present]
        for clause in re.split(r"[，,；;：:]", sent):
            if not clause.strip() or HEDGE.search(clause) or lexicon.NEGATE.search(clause) or lexicon.REMOTE.search(clause):
                continue
            for pid, a, _ in lexicon.find(clause, names):
                if CALLED.search(clause[max(0, a - 4):a]):
                    say(pid, {to, "player"} - {None} if to else None, sent)
            if MUTUAL.search(clause):
                pair = list(dict.fromkeys((["player"] if "你" in sent else []) + people))
                pool = [p for p in dict.fromkeys([*near, *last]) if p not in pair and p != "player"]
                if len(pair) < 2 and len(pool) == 1 or (GROUP.search(clause) and not pair):
                    pair += pool[:2 - len(pair)]
                if len(pair) == 2:
                    say(pair[0], {pair[1], "player"})  # 互通姓名：两人彼此知道了，主角在场也听见
                    say(pair[1], {pair[0], "player"})
                elif miss is not None:
                    miss.append(sent)
            elif (m := TELL.search(clause)):
                head = sent[:sent.index(clause) + m.start()]
                teller = _agent(world, head, whos, near or last) or (who if who in present else None)
                if teller:
                    say(teller, {to, "player"} - {None} if to else None, sent)
                elif miss is not None:
                    miss.append(sent)
        last = people or last
    return [{"op": "reveal", "id": pid, "key": "name", **({"to": ear} if ear else {}), **({"know": "身份"} if pid in known else {})}
            for pid, ear in said]


# ============================================================
#  逐拍体检：先听，再查称谓——叫出不该知道的名字即违例
# ============================================================
def audit(world, beats: list[dict], present: set[str], commit=None, start: int = 1) -> list:
    """beats: [{who, to, text}]（作废的拍 text 为空）。按拍序：先听——本拍里自报家门、互通姓名、当面点名而让在场者听来的名字，
    以识名指令交 commit 落账(调用方经 effects：认知与物理同一条写入通道)；再查说话者的台词——叫出在场之人的名字或「姓+称谓」
    而说话者并不知其名，或不知主角姓名者叫出主角的名号，记一条违例。旁白的拍(who 为空)只听不查：说话人是猜的，不为猜测耗一轮返工。"""
    tab = lexicon.table(_surfaces(world))
    me = world.player["name"]
    people = set(present) | {"player"}
    out = []
    for i, beat in enumerate(beats, start):
        text, who = beat.get("text") or "", beat.get("who")
        who = "player" if who in ("player", "主角", me) else who
        if not text:
            continue
        if commit:
            commit(hear(world, text, who, beat.get("to"), present=people))
        if who != "player" and world.graph.kind(who) != "person":
            continue
        for q in QUOTE.findall(text):
            for pid, a, _ in lexicon.find(q, tab):
                if pid != who and pid in people and not knows(world, who, pid):
                    out.append(lexicon.Finding("name", i, pid, f"第{i}拍{_who(who)}叫出了{pid}的名字，可{_who(who)}并不知{pid}姓名",
                                               hard=who == "player"))
            for pid in people - {who, "player"}:
                if not knows(world, who, pid) and _calls(q, pid, pid):
                    out.append(lexicon.Finding("name", i, pid, f"第{i}拍{_who(who)}以姓氏称呼{pid}，可{_who(who)}并不知{pid}姓名",
                                               hard=who == "player"))
            if who != "player" and not knows(world, who, "player") and (me in q or _calls(q, "player", me)):
                out.append(lexicon.Finding("name", i, "player", f"第{i}拍{who}叫出了主角的名号，可{who}并不知主角姓名："
                                                                 f"要他知道，先让主角自报家门或由认得主角的人当面叫出", hard=False))  # v14 掩码会把它换成「兄台」：不值得为此返工(run3 第 9 回)
    return out


def _who(pid: str) -> str:
    return "主角" if pid == "player" else pid


# ============================================================
#  交编剧之前：不给即不泄露
# ============================================================
def _hereabouts(world) -> frozenset:
    """一日路程之内的人(v14)：两字人名只在这些人里才当名字掩——按图的戳记与主角所在缓存。"""
    g = world.graph
    key = ("hereabouts", world.here)
    hit = g.memo.get(key)
    if hit and hit[0] == g.stamp:
        return hit[1]
    dist = g.distances(world.here)
    out = frozenset(p for p in g.of("person") if dist.get(g.get(p, "location"), 99) <= 1)
    g.memo[key] = (g.stamp, out)
    return out


def mask(world, text: str, speaker: str | None = None) -> str:
    """主角不识名之人：旁白里换成叫法，台词里换成当面的称呼；说话者不知主角姓名，他口中的主角名号与「王兄」换成泛称。"""
    if not text:
        return text
    seen = situation.seen(world) | set(situation.sighted(world))  # 本回合见过的人(v5)：刚从眼前走开的生人仍只叫外貌——换回名字就替主角认出了他；v12 远远望见的也一样(名号显赫的司空玄亦然)
    met = seen | set(world.player.get("met") or {}) | situation.cast(world)
    tab = lexicon.table({s: p for s, p in _surfaces(world).items()  # 当面不识其人，或连其名都未曾听过——久仰的不在眼前，照叫其名
                         if not knows(world, "player", p) and (p in seen or not identified(world, p))  # v14 不在眼前时照叫其名的只有闻名已久(识底)的人：见过而不知其名的仍只叫外貌(run4 第 5 回「容子矩的尸首」)
                         and (len(s) >= 3 or p in met or p in _hereabouts(world))})  # v14 两字人名撞上寻常字眼(「石室里」的「室里」是一位远在辽国的武将、「知道清楚」里有「道清」)：只掩见过的与一日路程之内的

    me = world.player["name"]
    speaker = "player" if speaker in ("player", "主角", me) else speaker

    def speech(q: str) -> str:
        q = _swap(q, tab, lambda p: address(world, p), _introduced)  # 落不了账的自报家门只去掉名字：「小生，大理人氏」，不是「小生兄台」
        if speaker and speaker != "player" and world.graph.kind(speaker) == "person" and not knows(world, speaker, "player"):
            q = q.replace(me, "兄台")
            for a, b in reversed(_calls(q, "player", me)):
                q = q[:a] + ("兄台" if q[a + len(surname(me)):b] in ("兄", "兄弟", "兄台") else q[a + len(surname(me)):b]) + q[b:]
        for p in seen:
            if not knows(world, "player", p):
                for a, b in reversed(_calls(q, p, p)):
                    q = q[:a] + q[a + len(surname(p)):b] + q[b:]
        return q

    out, last = [], 0
    for m in QUOTE.finditer(text):
        out.append(_swap(text[last:m.start(1)], tab, lambda p: handle(world, p), APPOSITIVE))
        out.append(speech(m.group(1)))
        last = m.end(1)
    out.append(_swap(text[last:], tab, lambda p: handle(world, p), APPOSITIVE))
    return "".join(out)


def thing(world, name: str) -> str:
    """器物在主角眼中的叫法(v5)：名字里带着主角不识之人的名号(云中鹤钢爪、钟灵黄金钿盒)，便只叫那件东西本身——
    编剧看见「钢爪」，看不见「云中鹤」；选项写「钢爪」，器物近似名照样落回原物。"""
    if not name:
        return name
    doc = world.graph.get(name, "doc") if world.graph.has(name) else None
    if doc and doc.get("form"):  # 剧中人写下的文书(v9)：主角经手、读过或是收信人才知道是谁写给谁的
        mine = "player" in (doc.get("author"), doc.get("to")) or "player" in (doc.get("read_by") or [])
        who = lambda p: "你" if p == "player" else p if knows(world, "player", p) else handle(world, p)
        return (f"{who(doc['author'])}写给{who(doc['to'])}的{doc['form']}" if doc.get("to") else f"{who(doc['author'])}写的{doc['form']}") \
            if mine and doc.get("author") else f"一{'封' if doc['form'] == '书信' else '张'}{doc['form']}"
    name = re.sub(r"·\d+$", "", name)  # 分出来的那一份(v9 玉壁剑影图·1)：叫的还是那件东西，几张另写在数量里
    head, _, tail = name.rpartition("·")
    if head and tail and world.graph.has(head) and world.graph.kind(head) == "location":  # v14 场景清单的器物 id 带着所在地(琅嬛福地·铜镜后室·石桌铜镜)：主角眼中只叫那件东西
        name = tail
    tab = lexicon.table({s: p for s, p in _surfaces(world).items() if not knows(world, "player", p)})
    out = name
    for _, a, b in reversed(lexicon.find(out, tab)):
        out = out[:a] + out[b:].removeprefix("的")
    return out.strip() or name


def _swap(text: str, tab, word, drop=None) -> str:
    """把名字换成 word(pid)；drop 命中(名字之前已有叫法作同位语，或 drop(text, 起, 止) 为真：自报家门)则直接去掉名字。"""
    for pid, a, b in reversed(lexicon.find(text, tab)):
        gone = drop and (drop(text, a, b) if callable(drop) else drop.search(text[:a]))
        text = text[:a] + ("" if gone else word(pid)) + text[b:]
    return text


def veil(world, pack: dict) -> dict:
    """玩家视锥译成主角的视角（给编剧）：不识名之人只剩叫法，头衔门派与关系不露；同行、近旁、近事、梗概里的名字一并换掉。"""
    out = copy.deepcopy(pack)
    for p in out["people"]:
        pid = p["name"]
        if not knows(world, "player", pid):
            p.update(name=handle(world, pid), title="来历不明", faction="门派不明",
                     toward_you=[mask(world, t) for t in p["toward_you"]])
        elif not identified(world, pid):  # 识名不识底(v12)：叫得出名字，头衔门派仍不露
            p.update(title="来历未明", faction="门派不明")
        p["carrying"] = [thing(world, c) for c in p["carrying"]]
        if p.get("intent"):
            p["intent"] = mask(world, p["intent"])
        p["seen_as"] = None
    out["squads"] = [{**q, "desc": mask(world, q.get("desc") or ""), "leader": handle(world, q["leader"]) if q.get("leader") else None,
                      "intent": mask(world, q["intent"]) if q.get("intent") else q.get("intent")}
                     for q in out.get("squads", [])]  # 人群(v9)：叫法本就是外貌门派；v12 首领与眼下之事也从主角的视角说
    out["relations"] = [r for r in out["relations"] if mask(world, r) == r and _bared(world, r)]  # v12 关系行只留两端都识底(或一端是主角)的
    out["party"] = [handle(world, p) for p in out.get("party", [])]
    g, shown = world.graph, {p["name"] for p in pack["people"]}
    out["nearby"] = [f"{handle(world, p)}" + (f"（{g.get(p, 'title')}）" if identified(world, p) and knows(world, "player", p) else "") + f"在{g.get(p, 'location')}"
                     for p in sorted(situation.around(world) - shown)]
    out["dead"] = [handle(world, p) for p in out.get("dead", [])]
    out["afar"] = [{**a, "name": handle(world, a["name"]) if a.get("kind") != "group" else a["name"],
                    "appearance": mask(world, a.get("appearance") or "")} for a in out.get("afar", [])]  # v12 远处可见：生人只叫外貌
    out["journal"] = [mask(world, j) for j in out["journal"]]
    out["news"] = [mask(world, n) for n in out.get("news", [])]  # 传闻也从主角的视角说：不识的人只剩叫法
    out["items"] = [_card(world, i) for i in out.get("items", [])]
    out["scene"] = {**out["scene"], "state": mask(world, out["scene"]["state"]) if isinstance(out["scene"].get("state"), str) else out["scene"].get("state"),
                    "lore": [mask(world, x) for x in out["scene"].get("lore") or []]}
    out["player"] = {**out["player"], "synopsis": mask(world, out["player"]["synopsis"]),
                     "threads": [mask(world, t) for t in out["player"]["threads"]],
                     "inventory": [_card(world, i) for i in out["player"]["inventory"]]}
    out["features"] = [{**f, "name": thing(world, f["name"]) if f.get("name") else f.get("name"),  # v14 景物也只叫它本身(「万劫谷厅案」→「厅案」)
                        "desc": mask(world, f.get("desc") or ""), "state": mask(world, f["state"]) if isinstance(f.get("state"), str) else f.get("state")}
                       for f in out.get("features", [])]
    return out


def _bared(world, line: str) -> bool:
    """一行关系「甲—关系—乙（…）」两端主角都识底(或一端是主角)：段誉只报了姓名，「段正淳—父子—段誉」不该给编剧。"""
    m = re.match(r"^(.+?)—(.+?)—(.+?)(?:（|$)", line)
    return not m or all(x == "player" or identified(world, x) for x in (m.group(1), m.group(3)))


def _card(world, c: dict) -> dict:
    """一件器物在主角眼中(v8 场景清单)：名字不带生人名号，描述、方位、属性与内容一并过掩码；形状与 world/scenery.card 相同。"""
    return {**c, "name": thing(world, c["name"]), "desc": mask(world, c.get("desc") or ""),
            "spot": mask(world, c["spot"]) if c.get("spot") else c.get("spot"),
            "props": {k: mask(world, v) for k, v in (c.get("props") or {}).items()},
            "text": mask(world, c["text"]) if c.get("text") else c.get("text")}
