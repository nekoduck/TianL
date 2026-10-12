"""
[INPUT]: 只依赖 re；实体名表由调用方给出（surface → id 与实体类别），状态以 View（回合起止两个切面）给出
[OUTPUT]: 对外提供 View、table()（实体名表）、find()（文中提到的实体，最长优先）、scan()（拍文与账本的一致性体检 → Finding 列表）、
          leaks()（后台术语）、secret_hits()（未揭隐情两端与关系词同现）、itemish()、mastery()（主角的进境措辞）、MASTERY / PRACTICE
[POS]: world 层的变化词表与一致性体检——"文字只渲染已成立之事"的第一道闸：拍文写了得失、去留、生死、擒放、吸功、
       或让不在场的人开口，账本里却没有对应的变化，即为一条 Finding；纯函数、零调用，裁决器(adjudicate)在落账后用它查遗漏，
       回放工具(tools/replay.py)用它统计旧对局的违例。只认"动词与实体同在一个分句"的强证据，否定、假设、回忆、远处一律不算；
       「二人」「众人」只回指上一句点到的人，不把同句里的旁人一并算作随行；
       进境(v4)：「练成、学会、身如游龙、功力大进」之类成就性措辞是第九类变化——说了就意味着账上该有一阶进境，没有即为违例；
       「练、参、研、演」之类习练措辞不是违例，是追认一回研习的线索(adjudicate.imply)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re
from dataclasses import dataclass, field

# ============================================================
#  词表：每类变化一组强动词——只收"说了就意味着状态变了"的词，宁缺毋滥
# ============================================================
ACQUIRE = re.compile(r"夺(?:过|下|走|得)|抢(?:过|走|得)|取走|拿走|取得|取下|摘下|拾起|捡起|揣入|揣进|收入怀|纳入怀|藏入怀|塞入怀|"
                     r"拔起|采下|采了|顺手.{0,2}(?:拔|取|摘|拿|牵)|据为己有|收下|接过|到手")
GIVE = re.compile(r"递给|递与|交给|交与|交到|塞给|塞到|奉上|献上|送给|还给|抛给|掷给|丢下|扔下|弃下|抛下")
LEAVE = re.compile(r"逃走|逃去|逃离|逃遁|遁走|遁去|遁入|飞遁|远遁|退走|离去|走远|溜走|掠走|飞退|倒纵|远去|扬长而去|拂袖而去|告辞而去|消失在")
FOLLOW = re.compile(r"携着|携了|携起|携|带着|带了|揽住|揽着|扶着|背着|抱着|拉住|拉着|领着|同行|随你|跟着你|随后跟上|紧随")
KILL = re.compile(r"杀死|杀了|刺死|打死|劈死|砍死|击杀|害死|杀害|击毙|掌毙|斩杀|格杀")       # 及物：死者在动词之后
DIE = re.compile(r"身亡|毙命|气绝|殒命|丧命|断气|死于|一命呜呼")                                 # 不及物：死者在动词之前
DRAIN = re.compile(r"吸尽|吸干|吸走|吸取|吸去|吸了|吸夺|夺人功力|(?:内力|真气|功力)[^，。；！？]{0,6}(?:尽失|全失|被吸|溃堤|倒灌|流泻|涌入你|源源不绝地涌入)|化去.{0,2}(?:内力|功力)")
FREE = re.compile(r"救出|救下|斩断.{0,4}(?:绳|索|锁)|割断.{0,4}(?:绳|索)|松绑|解开.{0,3}(?:绳|索|绑)|放走|放了")
BIND = re.compile(r"擒住|擒下|擒获|生擒|绑了|绑住|捆住|押走|押着|扣下|扣为人质|挟为人质|劫走|劫持|掳走|掳去|掳了|掳在|掳")
ACT = re.compile(r"^[^，。；！？“”「」的之与和及、]{0,4}?(?:道|说|喝|笑|叫|怒|答|问|喊|叹|哼|呼|嚷|骂|应声|点头|摇头|拱手|抱拳|冷|厉|急|颤|惊|扑|抢|拔|挥|掠|跃|奔|跪|拜|递|接|攥|握|抓|跑|立在|站在|坐在|望|瞧|伸|抬|转身|回身|迎上|迎了)")
REMOTE = re.compile(r"远远|远处|遥遥|传来|想起|忆起|回想|记得|昔日|当日|曾经|曾|据说|听说|传闻|传言|若是|倘若|如果|只怕|担心|料想|心想|念及|挂念|不知|下落|生死未卜")
NEGATE = re.compile(r"未能|未曾|不曾|没有|没能|险些|几乎|差点|欲要|正欲|正要|想要|将要|似要|不敢|不肯|岂能|休想|妄图|企图")
BACKSTAGE = re.compile(r"命运骰|骰子|骰点|预裁|较量预裁|档位|功力\s*\d|气血\s*\d|后台|LOD|原著结局|系统")
MASTERY_LEVELS = (  # 进境措辞所需的阶：1 入门即可、2 小成、3 大成；0 是「此刻才长进」，须本回合真有一阶进境
    (0, r"功力大进|内力大增|内力大进|神功初成|脱胎换骨"),
    (3, r"大成|登堂入室|融会贯通|炉火纯青|随心所欲|如臂使指|了然于胸"),
    (2, r"小成"),
    (1, r"练成|学会|学成|领悟了|运转如意|得心应手|身如游龙|已然入门|初窥门径|入门|练熟了|使得有模有样|摸到了门径"),
)
MASTERY = re.compile("|".join(rx for _, rx in MASTERY_LEVELS))
PRACTICE = re.compile(r"练|演|参研|参悟|研习|研读|修习|习练|运功|拆解|揣摩|照着.{0,6}(?:图|谱|卷|书)|比划|修炼|吐纳|打坐|依法|按图")
YET = re.compile(r"尚未|还未|未曾|不曾|远未|仍未|未能|没能|不能|难以|无法|何时才能|若能|但愿|盼着|梦想")
ITEMISH = re.compile(r"[^，。；！？的了在入下起走]{0,4}(?:药|丹|丸|散|膏|秘籍|秘笈|卷轴|帛卷|经书|剑谱|刀谱|图谱|珠|钏|镯|盒|匣|瓶|信|令牌|钥匙|锦囊|宝剑|宝刀|草)")
CLAUSE = re.compile(r"[，。；！？：\n]|——")
SENTENCE = re.compile(r"[。；！？\n]")
GROUP = re.compile(r"二女|二人|两人|三人|众人|诸人|她们|他们|一行人|一众")
PLAYER = ("你",)


@dataclass
class View:
    """回合起止两个切面中，体检需要的那几样：谁在场、谁身亡、谁被吸、谁受制、主角带着什么。"""
    here_start: set[str] = field(default_factory=set)     # 回合开始时在场(含近旁)之人
    here_end: set[str] = field(default_factory=set)       # 回合结束时在主角身边(含近旁)之人
    arrived: set[str] = field(default_factory=set)        # 本回合以 arrive 来到主角身边之人
    inventory_start: set[str] = field(default_factory=set)
    inventory_end: set[str] = field(default_factory=set)
    dead: set[str] = field(default_factory=set)           # 回合结束时已死之人
    drained: set[str] = field(default_factory=set)        # 本回合功力下降之人
    captive: set[str] = field(default_factory=set)        # 回合结束时仍受制之人
    moved: bool = False                                   # 主角本回合是否换了地方


@dataclass
class Finding:
    kind: str      # acquire/give/leave/follow/kill/drain/free/bind/absent/unnamed/backstage/secret
    beat: int      # 第几拍（从 1 起；-1 表示不针对某拍，如正文）
    entity: str
    message: str
    hard: bool = True


def table(names: dict[str, str]) -> list[tuple[str, str]]:
    """surface → id 的列表，长名在前：「闪电貂毒解药」先于「闪电貂」被认出，不让短名截胡。"""
    return sorted(names.items(), key=lambda kv: -len(kv[0]))


def find(text: str, tab: list[tuple[str, str]]) -> list[tuple[str, int, int]]:
    """文中提到的实体 (id, 起, 止)：最长优先、互不重叠。"""
    taken, out = [False] * len(text), []
    for surface, nid in tab:
        if not surface:
            continue
        start = text.find(surface)
        while start != -1:
            end = start + len(surface)
            if not any(taken[start:end]):
                for i in range(start, end):
                    taken[i] = True
                out.append((nid, start, end))
            start = text.find(surface, end)
    return sorted(out, key=lambda x: x[1])


def _clauses(text: str) -> list[str]:
    return [c for c in CLAUSE.split(text) if c.strip()]


def leaks(text: str) -> list[str]:
    return sorted(set(BACKSTAGE.findall(text)))


def secret_hits(text: str, secrets: list[tuple[str, str, str]], tab) -> list[tuple[str, str, str]]:
    """未揭隐情 (src, rel, dst)：两端同时被提到，且关系词(或其要字，如「生母」之「母」配「母女」)出现——即视为说破。"""
    named = {nid for nid, _, _ in find(text, tab)}
    hits = []
    for src, rel, dst in secrets:
        if {src, dst} <= named and (rel in text or any(k in text for k in _kin(rel))):
            hits.append((src, rel, dst))
    return hits


def _kin(rel: str) -> tuple[str, ...]:
    """亲缘隐情的口语变体：生母/生父/父女/母女……说成「母女」「父女」「亲生」都算说破。"""
    out = []
    if "母" in rel:
        out += ["母女", "母子", "亲娘", "娘亲"]
    if "父" in rel:
        out += ["父女", "父子", "亲爹", "生父"]
    if "生" in rel:
        out += ["亲生"]
    return tuple(out)


def mastery_level(word: str) -> int:
    return next(level for level, rx in MASTERY_LEVELS if re.fullmatch(rx, word))


def mastery(text: str, who=None) -> list[str]:
    """主角的进境措辞：分句里有「你」(或这一拍是主角的拍)、命中成就性措辞、且不在否定假设之中。返回命中的词。"""
    out = []
    for clause in _clauses(text or ""):
        if ("你" in clause or who in (None, "player")) and not YET.search(clause) and not REMOTE.search(clause):
            out += MASTERY.findall(clause)
    return list(dict.fromkeys(out))


def itemish(text: str) -> str | None:
    m = ITEMISH.search(text)
    return m.group(0) if m else None


# ============================================================
#  体检：逐拍逐分句，强动词 × 实体 × 起止切面
# ============================================================
def scan(beats: list[dict], view: View, tab, kinds: dict[str, str]) -> list[Finding]:
    """beats: [{who, text}]；kinds: id → person/item/thing/...。返回违例清单；hard 违例交导演修复，soft 只入 trace。
    得失与现身按分句看（动词与实体须在同一分句）；去留、生死、擒放、吸功按整句看（主语常在前一分句）；
    否定、假设、回忆、远处所在的句子一概不算。"""
    out: list[Finding] = []
    prev: list[str] = []
    for i, beat in enumerate(beats, 1):
        text, who = beat.get("text") or "", beat.get("who")
        out += [Finding("backstage", i, w, f"第{i}拍写出了后台术语「{w}」", hard=False) for w in leaks(text)]
        for sent in (x for x in SENTENCE.split(text) if x.strip()):
            far = bool(REMOTE.search(sent))  # 「远处传来钟万仇的呼喝」：整句都不算他现身
            for clause in _clauses(sent):
                if not NEGATE.search(clause) and not REMOTE.search(clause):
                    out += _clause(i, clause, who, view, tab, kinds, far)
            if not NEGATE.search(sent) and not far:
                found, prev = _sentence(i, sent, who, view, tab, kinds, prev)
                out += found
    return _dedupe(out)


def _clause(i, clause, who, view, tab, kinds, far: bool) -> list[Finding]:
    """分句内：你取得了什么、交出了什么，谁开口动手。"""
    out, ents = [], find(clause, tab)
    mine = who == "player" or "你" in clause
    things = [n for n, _, _ in ents if kinds.get(n) in ("item", "thing")]
    m = ACQUIRE.search(clause)
    if mine and m:
        out += [Finding("acquire", i, t, f"第{i}拍写你取得{t}，账上却没有这件东西到你手里")
                for t in things if t not in view.inventory_end and t not in view.inventory_start]
        noun = None if things or any(kinds.get(n) == "person" for n, _, _ in ents) else itemish(clause[m.end():][:10])
        if noun:
            out.append(Finding("unnamed", i, noun, f"第{i}拍写你取得「{noun}」，世上却没有这件器物：用既有之物，或以 spawn 立一件寻常物件"))
    if mine and GIVE.search(clause):
        out += [Finding("give", i, t, f"第{i}拍写你交出{t}，它却仍在你身上")
                for t in things if t in view.inventory_start and t in view.inventory_end]
    for nid, _, end in ents:
        if far or kinds.get(nid) != "person" or nid == "player" or nid in view.dead:
            continue
        if (who == nid or ACT.match(clause[end:])) and nid not in view.here_start | view.here_end | view.arrived:
            out.append(Finding("absent", i, nid, f"第{i}拍让{nid}现身言行，{nid}此刻却不在你身边"))
    return out


def _sentence(i, sent, who, view, tab, kinds, prev) -> tuple[list[Finding], list[str]]:
    """整句内：谁死、谁被吸、谁获救或被擒、谁随你走、谁离去。返回 (违例, 本句提到的人——下一句的「二人」多半指他们)。"""
    out = []
    ents = [(n, a, b) for n, a, b in find(sent, tab) if kinds.get(n) == "person" and n != "player"]
    people = [n for n, _, _ in ents]
    mine = who == "player" or "你" in sent
    if DRAIN.search(sent):
        out += [Finding("drain", i, p, f"第{i}拍写{p}内力被吸，账上{p}的功力却分毫未减")
                for p in (people or prev)[:2] if p not in view.drained]
    kill, die = KILL.search(sent), DIE.search(sent)
    for p, a, b in ents:  # 死者须紧挨着致死之词：「龚光杰刺死褚师弟」死的是褚师弟，「左子穆惊呼，容子矩早已气绝」死的是容子矩
        if ((kill and 0 <= a - kill.end() <= 4) or (die and 0 <= die.start() - b <= 8)) and p not in view.dead:
            out.append(Finding("kill", i, p, f"第{i}拍写{p}身亡，账上{p}却仍活着"))
    bind = BIND.search(sent)
    for p, a, b in ents:
        if FREE.search(sent) and p in view.captive:
            out.append(Finding("free", i, p, f"第{i}拍写{p}获救，账上{p}却仍受制于人"))
        # 被擒者紧跟在擒拿之词后（「擒住钟灵」），或以「被」字句在前（「钟灵被神农帮众掳走」）
        if bind and (0 <= a - bind.end() <= 4 or ("被" in sent[b:bind.start()] and 0 <= bind.start() - b <= 12)) \
                and p not in view.captive and p not in view.dead:
            out.append(Finding("bind", i, p, f"第{i}拍写{p}被擒，账上却没有这层拘押：写 link 扣为人质或囚禁"))
    follow = bool(mine and FOLLOW.search(sent) and view.moved)
    if follow:
        company = people + ([p for p in prev if p not in people] if GROUP.search(sent) else [])  # 「二人」只指上一句里的人，不扩到全场
        out += [Finding("follow", i, p, f"第{i}拍写{p}随你同行，账上{p}却留在原地")
                for p in company if p in view.here_start and p not in view.here_end]
    m = LEAVE.search(sent)
    if m and not follow:
        for p, a, b in ents:  # 去者须是动词之前的主语，且与动词之间没有「你」——「你掠过司空玄遁去」走的是你
            if a < m.start() and "你" not in sent[b:m.start()] and p in view.here_end:
                out.append(Finding("leave", i, p, f"第{i}拍写{p}离去，账上{p}却仍在你身边"))
    return out, people or prev


def _dedupe(found: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in found:
        key = (f.kind, f.entity)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out
