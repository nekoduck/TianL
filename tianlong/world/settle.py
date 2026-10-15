"""
[INPUT]: 依赖 world/perspective 的 hear / speaker / doer / mask / handle / guise / thing / knows / audience / moment / QUOTE（识名听写、说话人与行事者、视角掩码、叫法、时间轴上的那一刻）、world/profile 的 profile（单一投影：账房看的账本快照）、
         world/effects 的 apply / describe / resolve / place（唯一写入通道）、world/adjudicate 的 view / names / unbidden（回合起止切面、实体名表、授意）、
         world/situation 的 seen / around / near / party / captors / captive / bodies（在场、近处、随行、受制）、world/body 的 INNER（内伤分级词）、
         world/growth 的 unearned / mastery、world/lexicon 的 scan / mastery / SENTENCE / DEPART / NEGATE / REMOTE / YET（词表：结算的第二双眼睛，也判主角是否真动了身）、
         world/scenery 的 nicknames（v8 器物的简称）、world/adjudicate 的 forged（v8 世上没有的器物）、world/acts 的 expand / normalize / is_act / verb（v9 账房也说事码）、
         world/crowd 的 squads / standing / handle / besiegers / is_squad、world/stock 的 funds / say / measure / cn（银两、人群、数量的账）
[OUTPUT]: 对外提供 Gate（正文出闸：逐段逐句对齐到时刻 → 听 → 掩 → 放行，放行即存档；note 把补记接在正文之后(同过掩码与存档，但戏里没有人听见)；at 给一句话所在那一刻的听众与遗体）、partners()、
          books()（账房看的账本：定本正文、叫法对照、此刻账上、本回合已落账、本回合账上的变化、近处地点）、
          commit()（账房的结算单落账：据须是正文原句、规则之事正文改不了、主角之举须经授意，按据所在时刻的听众经 effects 裁决 → (成立的指令, 分歧)）、
          disputes()（词表这双眼睛：结算之后正文仍写着、账上仍没有的句子——交账房复核）、ruled()（正文写了账上没有的规则之事：生死、吸功、进境——只记分歧）、audit()（离线的对账：词表查出的一律只记分歧、不改账）、waive()（复核裁定不记的句子划掉）、
          glance() / delta()（回合首末两份主角看得见的账，两份之差即这一回合主角该读到的变化）、unwritten() / note()（差里正文没写到的，由账本生成补记）、admit()、rifts()
[POS]: v11 正文复述导演这一回合已办过的买卖、服用、办事、打探不再记一遍(_repeat)，也不算分歧；账房买的是货架上的货名，不是账上的 id。
        world 层的结算——账文同构的执行者。病根是双写：导演的指令进账本、编剧的正文给玩家，两份由模型各写各的；v6 让正文成为定本、账本是它经裁决的投影。
       v7 把对账补齐成四条轴：
       方向(两相对账)：文→账由账房开单入账；账→文由回合首末两份「主角看得见的账」(glance)求差(delta)——账上变了而正文没写到的(账房判、词表兜底)，由账本生成补记接在正文之后，一句一事、过视角掩码；
       身份(叫法即主键)：撞名的人在任何人落笔之前由 perspective.distinguish 分到稳定外号，账房的叫法对照、补记、正文说的是同一个人；
       校验(双录复核)：账房与词表是两个独立的记账员——结算之后词表仍查出、账上仍没有的句子(disputes)交账房逐句复核：是已然发生的就开单，不是就驳回；复核之后仍对不上的才是分歧；
       时间(正文有时间轴)：裁决时记下主角待过的每一处、那里的听众与遗体(turn["moments"])；正文每一截先按拍文重合度对齐到拍，
       再在主角换了地方之处切开——旁白写你出了眼下这一处(「你…出了练武厅」「出了厅门」)或到了之后那一处(「一路奔到后山」)，切在那一分句之首，
       台词里说的、别人的来去、想起与听说的、正欲与尚未的都不算；只进不退。从某一截听出的名字、从某句开出的变化，都在那一刻的听众里生效——
       同一段里动身之前在厅上报的名厅上的人听见，到了后山报的名后山的人听见。
       物理照旧只由世界裁定：账房只把正文里已发生的事交世界复核；伤病数值、生死、功力进境、远行归规则，只记分歧(player.drift)交下回合导演圆回。
       场景清单(v8)：寻常之物的取用不交复核、不记分歧；补记的「写到没有」认器物的简称(写「那柄青钢剑」就是写到了剑架青钢剑)；
       正文凭空写出世上没有的器物(有人拿出、去取、递上它)记作分歧(ruled)，下回合交导演圆回。
       事码(v9)：账房的结算单与导演说同一种话——平常之事先化为指令照旧过 admit，规则之事(易手、撕合、书写、脱身)交世界照规则复核，人群倒下几人归规则(只记分歧)；
       事码写明主角做的，不论单子署谁都过授意；账本给账房看主角的银两、地上器物的数量与在场人群，回合首末两份账另记银两、人群人数与围攻——银两多了少了、人群倒下几人、被围与脱围，正文没写到即补记。
       纯规则、不调 LLM(账房在 narrative)、不新造实体
       v10：账本里每个人写上身上的银两(NPC 之间给钱也有账可依)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import re

from . import access, acts, adjudicate, crowd, effects, growth, lexicon, perspective, scenery, situation, stock, venue
from . import body
from .body import INNER
from .graph import ROAD
from .profile import profile

RULED = {"status": "生死伤病", "hp": "气血", "max_hp": "气血", "power": "功力", "skills": "武学", "faction": "门派", "title": "名号头衔",
         "age": "年岁", "grants": "秘籍所载"}           # 归规则或归定义：正文写了，账房也改不了
BASIS = 4                                              # 据至少几个字：一个「你」字不算出处
RIFTS = 6                                              # 分歧至多交导演几条：多了便成了催债
DRIFT_TURNS = 2                                        # 规则性的分歧交导演几回：交代满了仍没圆回的作罢（v13；从前交一回即清，导演漏看了便再无下文）
TECHNICAL = re.compile(r"格式不可解|未知指令|不识的事码|缺少|缺字段|端点不在世界中|不是在场之人|不在世界中|不可写成复合值|须为文字|不是数值|不是清单|只可 set 或 add")  # 账房自己写歪了的（id、格式、形状）：是它的错，不是正文与账本的分歧
ALIGN = 0.4                                            # 一段正文与一拍拍文的字对(二字组)重合过此即算写的是那一拍
DOUBT = {"acquire", "give", "bind", "free", "follow", "leave", "move"}  # 词表查出而账房可复核的(叙述成立得了的)；生死吸功归规则
MARK = re.compile(r"[\s「」“”『』\"'‘’…—]")
log = logging.getLogger("tianlong")


def _plain(s: str) -> str:
    return MARK.sub("", s or "").strip("，。；！？、,.;!?")


def _pairs(s: str) -> set[str]:
    s = re.sub(r"[^一-鿿]", "", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _cues(loc: str) -> list[str]:
    """正文里提到某处的说法：全名、「·」后的短名、四字以上地名的末二字(无量后山→后山)。"""
    short = loc.split("·")[-1]
    return [x for x in dict.fromkeys([loc, short, short[-2:] if len(short) >= 4 else ""]) if x]


def _chain(g, loc: str | None) -> list[str]:
    """某处与它的上级：剑湖宫·练武厅 → 剑湖宫 → 无量山。"""
    out = []
    while loc and loc not in out:
        out.append(loc)
        loc = g.get(loc, "parent")
    return out


ROOMS = "厅堂殿室洞房屋阁楼院宫庙寺观庄府"                               # 「出了厅门」「离了大殿」：屋宇的末一字也说的是那一处
LEAVE = re.compile(rf"(?:{lexicon.DEPART.pattern}|出|离)$")             # 出了、走出、离开……紧跟着那一处的叫法
REACH = re.compile(r"(?:到|至|进|入|上|抵|回|往|赴|奔|去|在|于)[了得过]?$")  # 奔到后山、到了后山、往后山去、避在后山：到了那里或已在途中


# ============================================================
#  出闸：正文按段放行——对齐到时刻 → 听(报了姓名先入账，那一刻的听众听见) → 掩(按说话人) → 放行；放行的就是存下的
# ============================================================
class Gate:
    """正文出闸。一段齐了：先对齐到时刻(这一段写的是主角在哪一处、哪一拍的事)，在那一刻的听众里听这一段谁报了姓名
    (perspective.hear → effects)，再按每段台词的说话人过视角掩码，再放行。段与段之间的换行等下一段放行时才补上——
    头尾不留空行，放行的拼起来逐字就是存下的正文，流式与否一样。"""

    def __init__(self, world, near=()):
        self.world, self.near = world, list(near)
        self.parts: list[str] = []
        self.heard: list[dict] = []
        self.spans: list[tuple[str, int]] = []  # (这一段去标点的正文, 所在时刻)：结算单的据落在哪一段、哪一刻
        self.moment = 0
        self._buf, self._gap = "", ""

    @property
    def text(self) -> str:
        return "".join(self.parts)

    def feed(self, delta: str) -> str:
        """收一块正文增量，返回此刻可以放行的(齐了的段)；没有即空串。"""
        self._buf += delta or ""
        cut = self._buf.rfind("\n") + 1
        if not cut:
            return ""
        ready, self._buf = self._buf[:cut], self._buf[cut:]
        return self._let(ready)

    def close(self) -> str:
        """收尾：放行最后半段。"""
        rest, self._buf = self._buf, ""
        return self._let(rest)

    def note(self, lines: list[str]) -> str:
        """补记(v7)：账上变了、正文没写到的事，由账本生成的一段接在正文之后，与正文同过这道闸(拼接、掩码、存档)——
        但没有人听见它：补记是账本对读者说的话，不是戏里谁的台词或旁白，「青衫少年原来名叫段誉」不让满厅的人都知道了段誉。"""
        if not lines:
            return ""
        self._gap = "\n\n"
        return self._let(f"（{'；'.join(lines)}。）", listen=False)

    def at(self, basis: str):
        """一句正文所在的那一刻：(耳边的活人, 眼前的遗体)——结算单里从这句开出的识名，只那一刻在场的人听见、只那一刻眼前的人落得到；
        据跨了两刻的，按它开头几个字所在的一刻；找不到这句即 None(按此刻)。"""
        key = _plain(basis)
        k = next((m for plain, m in self.spans if key and key in plain), None)
        if k is None and len(key) >= BASIS * 2:
            k = next((m for plain, m in self.spans if key[:BASIS * 2] in plain), None)
        return None if k is None else self._at(k)

    def _let(self, chunk: str, listen: bool = True) -> str:
        out, lines = [], chunk.split("\n")
        for i, line in enumerate(lines):
            if line.strip():
                lead = ("\n\n" if len(self._gap) > 1 else self._gap) if (self.parts or out) else ""
                out.append(lead + self._paragraph(line, listen))
                self._gap = ""
            if i < len(lines) - 1:
                self._gap += "\n"
        released = "".join(out)
        if released:
            self.parts.append(released)
        return released

    def _aligned(self, text: str, k: int) -> int:
        """这一截正文写的是之后哪一拍的事：与那一拍的拍文字对(二字组)重合过 ALIGN，就走到那一拍所在的一刻；没有即仍是 k。"""
        mine = _pairs(text)
        hit = [m for beat, m in self.world.turn.get("beats_at") or []
               if m > k and (b := _pairs(beat)) and len(b & mine) >= ALIGN * len(b)]
        return max(hit, default=k)

    def _border(self, para: str, pos: int, k: int, quoted) -> tuple[int, int] | None:
        """para[pos:] 里主角头一回换了地方之处(台词里说的不算，别人的来去不算)：出了第 k 刻那一处(「你…出了练武厅」)即到下一刻，
        到了之后某一刻的地方(「一路奔到后山」)即到那一刻。切在那一分句之首(分句里先说的台词仍留在原处)。返回 (切点, 那一刻) 或 None。"""
        g, moments = self.world.graph, self.world.turn["moments"]
        outside = lambda i: not any(a <= i < b for a, b in quoted)
        mine = lambda i: perspective.doer(self.world, para, i, self.near) in (None, "player")  # 第二人称叙事：没写主语的多半是你

        def clause(i):  # 切点：那一分句之首，但不越过分句里已说完的台词
            head = para[:i]
            ends = [head.rfind(c) + 1 for c in "，,；;。！？：:"] + [b for a, b in quoted if b <= i]
            return max(pos, *ends)

        def real(i):  # 那一分句写的是已然的行止：想起、听说、正欲、尚未的都不算
            whole = para[clause(i):i] + re.split(r"[，,；;。！？]", para[i:], maxsplit=1)[0]
            return not (lexicon.NEGATE.search(whole) or lexicon.REMOTE.search(whole) or lexicon.YET.search(whole))
        here, nxt = moments[k]["here"], moments[k + 1]["here"]
        gone = [loc for loc in _chain(g, here) if loc not in _chain(g, nxt)]
        cues = {c for loc in gone for c in _cues(loc)} | {loc.split("·")[-1][-1] for loc in gone if loc.split("·")[-1][-1] in ROOMS}
        hits = [(clause(i), k + 1) for c in cues for i in _finds(para, c, pos)
                if outside(i) and LEAVE.search(para[max(pos, i - 3):i]) and real(i) and mine(i)]
        hits += [(clause(i), j) for j in range(k + 1, len(moments)) for c in _cues(moments[j]["here"]) for i in _finds(para, c, pos)
                 if outside(i) and REACH.search(para[max(pos, i - 3):i]) and real(i) and mine(i)]
        return min(hits, key=lambda h: (h[0], -h[1])) if hits else None

    def _segments(self, para: str) -> list[tuple[str, int]]:
        """一段正文按时刻切开(v7 正文有时间轴)：每一截先对齐到拍(_aligned)，再找主角换了地方之处(_border)切开——
        同一段里动身之前在厅上说的话厅上的人听见，到了后山说的话后山的人听见。只进不退。"""
        moments = self.world.turn.get("moments") or []
        quoted = [m.span() for m in perspective.QUOTE.finditer(para)]
        k, pos, out = self.moment, 0, []
        while True:
            cut = self._border(para, pos, k, quoted) if k + 1 < len(moments) else None
            end = cut[0] if cut else len(para)
            ahead = self._aligned(para[pos:end], k)
            if ahead > k:  # 这一截写的已是之后那一刻的事：从那一刻起重找界线
                k = ahead
                continue
            out.append((para[pos:end], k))
            if not cut:
                break
            pos, k = cut
        self.moment = k
        return [(text, m) for text, m in out if text]

    def _at(self, k: int):
        """第 k 刻在场的人：(耳边的活人, 眼前的遗体)；主角眼下这一处连同此刻的。没有时间轴(未经裁决)即 None。"""
        moments = self.world.turn.get("moments") or []
        if not moments:
            return None
        k = min(k, len(moments) - 1)
        ears, dead = set(moments[k]["ears"]), set(moments[k].get("bodies") or ())
        if k == len(moments) - 1 and moments[k]["here"] == self.world.here:
            ears |= perspective.audience(self.world)
            dead |= situation.bodies(self.world)
        return ears, dead

    def _paragraph(self, para: str, listen: bool = True) -> str:
        w = self.world
        for text, k in self._segments(para) if listen else ():  # 先听：读者读到了名字就知道了名字——听见的是那一刻在场的人
            with perspective.moment(w, *(self._at(k) or ())):
                applied, _ = effects.apply(w, perspective.hear(w, text, near=self.near), "director")
            self.heard += applied
            self.spans.append((_plain(text), k))
        out, last = [], 0
        for m in perspective.QUOTE.finditer(para):  # 再掩：台词按说话人——不知主角姓名的人叫不出主角
            who = perspective.speaker(w, para, m.start(), m.end(), near=self.near)
            out += [perspective.mask(w, para[last:m.start()]), perspective.mask(w, m.group(0), who)]
            last = m.end()
        out.append(perspective.mask(w, para[last:]))
        return "".join(out)


def _finds(text: str, word: str, pos: int = 0) -> list[int]:
    out, i = [], text.find(word, pos)
    while i != -1:
        out.append(i)
        i = text.find(word, i + 1)
    return out


def partners(ruling) -> list[str]:
    """本回合与主角打交道的人(先后有序)：主角对他说话的、对主角说话的——旁白里的「他」「那少女」「你二人」多半指他们。"""
    out = []
    for b in ruling.beats:
        who, to = b.get("who"), b.get("to")
        out += [to] if who == "player" and to not in (None, "player") else [who] if to == "player" and who not in (None, "player") else []
    return list(dict.fromkeys(out + list(ruling.addressed)))


# ============================================================
#  账本快照：账房对账用的「此刻账上」——人与物都取自单一投影 profile
# ============================================================
def books(world, text: str, applied=(), changes=()) -> dict:
    """账房看的账本：定本正文、叫法对照(正文里的「青衫少年」就是段誉)、此刻账上(主角、本回合见过的每个人、此地与地上器物)、
    本回合已落账之事(不必再记)、本回合账上的变化(看正文写到没有)、近处地点(来去只写这些)。"""
    g, me = world.graph, world.player
    people = sorted(p for p in situation.seen(world) if p != "player" and g.kind(p) == "person")
    alias: dict[str, list[str]] = {}
    for p in people:
        if not perspective.knows(world, "player", p):
            alias.setdefault(perspective.handle(world, p), []).append(p)
    legend = [f"{h}＝{ids[0]}" if len(ids) == 1 else f"{h}＝{'或'.join(ids)}（{len(ids)}人同此叫法，看正文里是谁在做事）"
              for h, ids in alias.items()]
    party, held = set(situation.party(world)), situation.captive(world)

    def line(p: str) -> str:
        pf = profile(world, p)
        cells = [p, f"在{g.get(p, 'location')}", pf["wound"] or ("已故" if pf.get("status") == "dead" else "安好")]
        cells += [f"{k}：{v}" for k, v in (("神色", pf["mood"]), ("眼下之事", pf["intent"]),
                                          ("境况", "、".join(pf["conditions"])), ("随身", "、".join(pf["carrying"])),
                                          ("银两", stock.say(pf["money"]) if pf.get("money", 0) > stock.EPS else ""),  # v10 NPC 的银两也在账上
                                          ("与你", "；".join(pf["ties"]))) if v]
        cells += ["随你同行"] * (p in party) + [f"受制于{'、'.join(situation.captors(world, p))}"] * (p in held)
        cells.append(f"主角{'叫得出' if perspective.knows(world, 'player', p) else '叫不出'}此人的名字")
        cells.append(f"此人{'知道' if perspective.knows(world, p, 'player') else '不知'}主角的名号")
        return "｜".join(cells)
    here = world.here
    items = [i for i in effects.things(world, situation.near(world)) if not g.get(i, "hidden")
             and g.get(i, "holder") is None and effects.usable(world, i)]
    ware = lambda i: i + (f"（{stock.measure(g, i)}）" if stock.measure(g, i) else "")  # 一叠几张、一堆几两(v9)：拿了多少由正文定
    flock = [f"{s}（叫作{crowd.handle(g, s)}，站着{stock.cn(crowd.standing(g, s))}人）" for s in crowd.squads(world)]
    return {"text": text, "legend": legend,
            "player": "｜".join([f"主角（{me['name']}）", f"在{here}", f"随身：{'、'.join(ware(i) for i in me['inventory']) or '无'}",
                                f"银两：{stock.say(stock.funds(world, 'player'))}",
                                f"境况：{'、'.join(me['conditions']) or '无'}", f"未了之事：{'；'.join(me['threads']) or '无'}"]),
            "people": [line(p) for p in people],
            "scene": f"{here}｜现状：{g.get(here, 'state') or '如常'}｜地上器物：{'、'.join(ware(i) for i in items) or '无'}"
                     + (f"｜人群：{'、'.join(flock)}" if flock else ""),
            "applied": [effects.describe(op) for op in applied if op.get("key") not in ("threads",)],
            "changes": [c["text"] for c in changes],
            "places": sorted(situation.near(world))}


# ============================================================
#  入账：账房的结算单——据须是正文原句；叙述成立得了的事交世界复核，成立即落账，落不了与规则之事记作分歧
# ============================================================
def _known(world, op) -> bool:
    """指令里提到的人、地、物都是账上有的(主角亦然)：账房把「左子穆」写成 zuo_zimu，那一条丢掉，不当作正文与账本的分歧。
    事码(v9)看它的人地物(物是银两、或书写的那种文书不算)。"""
    if acts.is_act(op):
        a = acts.normalize(world, op)
        ends = [a.get(k) for k in acts.ENTITY if a.get(k) is not None]
        ends += [a["物"]] if isinstance(a.get("物"), str) and a["物"] != acts.MONEY and a["做"] not in ("书写", "买下", "打探", "办事") \
            and not crowd.is_squad(world.graph, a.get("自")) else []  # 买的是货架上的货名、打听的是一件事(v11)：不是账上的 id
        ok = all(isinstance(x, str) and (x == "player" or world.graph.has(x)) for x in ends)
        if not ok:
            log.info("账房写错了 id，不收：%s", op)
        return ok
    ends = [op.get(k) for k in ("id", "src", "dst", "to") if op.get(k) is not None]
    ok = all(isinstance(x, str) and (effects.resolve(world, x) == "player" or world.graph.has(effects.resolve(world, x))) for x in ends)
    if not ok:
        log.info("账房写错了 id，不收：%s", op)
    return ok


def _repeat(world, op) -> bool:
    """正文复述了导演这一回合已经办过的买卖、服用、办事、打探(v11)：不再记一遍(否则一壶酒付两回钱)，也不是分歧。"""
    if not acts.is_act(op) or acts.verb(op) not in acts.MARKET:
        return False
    from . import trade  # 用时才引
    turn, v = getattr(world, "turn", None) or {}, acts.verb(op)
    if v == "办事":
        return op.get("事") in turn.get("served", ())
    if v == "打探":  # 一回合打听过了，正文怎么复述(问的是哪个伙计)都是那一回
        return bool(turn.get("asked"))
    item = op.get("物")
    if v == "买下":
        vid = trade.shop(world)
        gid = trade.ware_of(world, vid, item) if vid else None
        item = (venue.wares(world, vid).get(gid) or {}).get("id") if gid else item
    return item in turn.get("traded", ())


def admit(world, op) -> str | None:
    """正文成立得了这条变化吗：不成立返回缘由。伤病数值、生死、功力进境、研习吸功归规则；远行归道路与光阴——
    这几样正文写了也只是分歧，交下一回合的导演圆回。"""
    if not isinstance(op, dict):
        return "格式不可解"
    if acts.is_act(op):  # 平常之事已化为指令(见 commit)；留下的规则之事里，人群的死伤归规则，其余(易手、撕合、书写、脱身)交世界照规则复核
        v = acts.verb(op)
        if v in ("杀死", "打晕"):
            return "人群倒下几人由规则结算，正文改不了账"
        if v == "脱身" and op.get("到") and effects.resolve(world, op["到"]) not in situation.near(world):
            return "远行的路程与光阴由道路结算，正文改不了账"
        return None
    kind, key = op.get("op"), op.get("key")
    if kind in ("add", "study", "drain"):
        return "伤病多少、功力与研习由规则结算，正文改不了账"
    if key in RULED:
        return f"{RULED[key]}由规则与原著定义，正文改不了账"
    if key in ("conditions", "境况") and INNER.search(str(op.get("value") or "")):
        return "内伤分级由规则升降，正文改不了账"
    if effects._moves_player(world, op) and effects.resolve(world, op.get("value")) not in situation.near(world):
        return "远行的路程与光阴由道路结算，正文改不了账"
    return None


def commit(world, bill: dict, text: str, aim=frozenset(), gate: Gate | None = None) -> tuple[list, list[str]]:
    """账房的结算单 {changes:[{据, 谁, ops}], rifts:[{据, 账上}]} 落账。据须是正文原句(去掉标点空白后是正文的一段，至少 BASIS 字)——
    对不上的是账房自己编的，不收；规则之事与落不了的变化记作分歧。主角之举(谁=主角)须在玩家所指之内(adjudicate.unbidden)：
    编剧替主角做了玩家没选的事，读者读到了也只是分歧，不替玩家落账。每一张单子在据所在那一刻的听众里生效(gate.at)。返回 (成立的指令, 分歧)。"""
    plain, applied, rifts = _plain(text), [], []
    me = world.player["name"]
    for ch in bill.get("changes") or []:
        basis = str(ch.get("据") or "").strip()
        if len(_plain(basis)) < BASIS or _plain(basis) not in plain:
            continue
        mine = ch.get("谁") in ("player", "主角", me)
        actor = str(ch.get("谁") or "").strip()
        raw = [op for op in ch.get("ops") or [] if isinstance(op, dict)]
        if actor and not mine:  # v13 单子写明了是谁做的，事码里没写「谁」：缺省会被当成主角（第 7 回「段誉服毒」成了「主角服用断肠散」），谁的单子就是谁做的
            raw = [{**op, "谁": actor} if acts.is_act(op) and "谁" not in op else op for op in raw]
        ops = [op for op in acts.expand(world, [op for op in raw if _known(world, op)])
               if isinstance(op, dict) and not _repeat(world, op)]  # 写错了 id 是账房的错，不是账文分歧；事码(v9)先化为指令，规则之事留作一件事
        keep = []
        for op in ops:
            why = admit(world, op)
            if why:
                rifts.append(f"正文「{basis}」：{effects.describe(op)}——{why}")
            else:
                keep.append(op)
        for op, act, _ in adjudicate.unbidden(world, keep if mine else [o for o in keep if acts.is_act(o)],
                                              set(aim) | {adjudicate.SELF}):  # 事码写明了谁做：谁的单子都查；正文里主角已经开口报了名，读者读到的就是定本，照记（v13 授意管的是导演替主角报名）
            rifts.append(f"正文「{basis}」：主角{act}——玩家并未起意，不入账")
            keep = [o for o in keep if o is not op]
        with perspective.moment(world, *((gate.at(basis) if gate else None) or ())):  # 这句话是在哪一刻说的：那一刻在场的人听见
            ok, bad = effects.apply(world, keep, "director")
        applied += ok
        for op, why in bad:
            line = f"正文「{basis}」：{effects.describe(op)}——{why}"
            if TECHNICAL.search(why):  # v13 技术性的失败只记日志：第 8 回「从谁身上夺取？player 不是在场之人」曾交导演「圆回」，导演便把读者读过的「夺过」演成了「冷笑不接」
                log.info("账房的单子落不了(技术性，不算账文分歧)：%s", line)
            else:
                rifts.append(line)
    for r in bill.get("rifts") or []:
        basis, truth = str(r.get("据") or "").strip(), str(r.get("账上") or "").strip()
        if len(_plain(basis)) >= BASIS and _plain(basis) in plain and truth:
            rifts.append(f"正文「{basis}」，账上：{truth}")
    return applied, rifts


# ============================================================
#  双录复核(v7)：账房与词表是两个独立的记账员——结算之后词表仍查出、账上仍没有的句子，交账房逐句复核
# ============================================================
def disputes(world, text: str) -> list[dict]:
    """结算之后，正文里仍写着账上没有的得失、去留、随行、擒放的句子(词表逐句定位，与拍文同一口径)：
    [{"句": 那一句, "看出": 词表看出的那件事}]。生死、吸功归规则，不在复核之列(直接是分歧)。"""
    v = adjudicate.view(world)
    if not v or not text:
        return []
    sentences = [s for s in lexicon.SENTENCE.split(text) if s.strip()]
    out = []
    for f in lexicon.scan([{"who": None, "text": s} for s in sentences], v, *adjudicate.names(world), dedupe=False):
        if f.kind in DOUBT and f.hard:  # 寻常之物(v8)端起放下不对账：不交复核、不记分歧
            out.append({"句": sentences[f.beat - 1].strip(), "看出": f.message.split("，", 1)[0].replace(f"第{f.beat}拍", "正文")})
    return out


def ruled(world, text: str) -> list[str]:
    """正文写了账上没有的规则之事：生死、吸功(词表看出)与进境(研习账之外的「身如游龙」)——只记分歧，正文改不了账。"""
    v = adjudicate.view(world)
    out = []
    if v and text:
        out += [f.message.replace("第1拍", "正文") for f in lexicon.scan([{"who": None, "text": text}], v, *adjudicate.names(world))
                if f.kind in ("kill", "drain", "fell")]  # 人群里倒下几人(v9)同是规则之事
    out += [f"正文写到「{f.entity}」，世上并无此物" for f in lexicon.scan([{"who": None, "text": text}], v, *adjudicate.names(world))
            if f.kind == "conjure" and adjudicate.forged(world, f.entity)] if v and text else []  # 器物不得新造(v8)：正文凭空写出的东西交下回合导演圆回
    words = growth.unearned(world, lexicon.mastery(text, "player"))
    if words:
        arts = "；".join(a["detail"] for a in growth.mastery(world)) or "主角尚无武学"
        out.append(f"正文写主角「{'、'.join(words)}」，账上：{arts}")
    out += geography(world, text)
    turn = getattr(world, "turn", None) or {}  # v13 正文写你负了伤，账上你气血未减、身上也并无伤势：伤归规则，正文改不了账，记作分歧
    hurt = lexicon.hero_hurt(text, *adjudicate.names(world)) if v and text else []
    if hurt and not turn.get("hurt") and body.wound(world)[0] == "安然无恙" \
            and world.player["hp"] >= (turn.get("start") or {}).get("hp", world.player["hp"]):
        out.append(f"正文写你负了伤「{hurt[0]}」，账上你气血未减、并无伤势")
    return out


IMPASSABLE = re.compile(r"天堑|无法渡过?|无从渡|渡不过|过不去|无路可通|无路可走|插翅难飞|难以逾越|无法逾越")


def geography(world, text: str) -> list[str]:
    """地理之句体检(v13)：正文说此处与某地之间是天堑、过不去，图上却是一条零日而无关口的明路——编剧能写出图上没有的地理（第 55 回「隔着这道天堑」，
    第 56 回却沿岸走到了无量山）。只记软分歧交导演：读者读过的话不能当没说，导演在剧情里交代（沿岸绕行、另有渡口），不是改地图。"""
    if not text:
        return []
    tab = adjudicate.names(world)[0]
    plain = {e["name"] for e in access.exits(world) if not e["days"] and not e["kind"]}
    out = []
    for sent in (s for s in lexicon.SENTENCE.split(lexicon.QUOTED.sub("", text)) if IMPASSABLE.search(s) and not lexicon.NEGATE.search(s)):
        named = {n for n, _, _ in lexicon.find(sent, tab)}
        hit = sorted(named & plain) or (sorted(plain) if world.here in named and plain else [])
        if hit:
            out.append(f"正文写「{sent.strip()[:40]}」，图上{world.here.split('·')[-1]}往{'、'.join(h.split('·')[-1] for h in hit[:2])}是零日的明路、并无阻隔")
    return out


def audit(world, text: str) -> list[str]:
    """离线的对账(没有账房、复核无人)：词表查出而账上没有的，一律只记分歧、不改账——词表从不替正文挪人。"""
    return [f"正文「{d['句']}」：{d['看出']}，账上却没有" for d in disputes(world, text)] + ruled(world, text)


def rifts(*groups) -> list[str]:
    """几处查出的分歧并作一份交导演：去重，至多 RIFTS 条。"""
    return list(dict.fromkeys(r for g in groups for r in g))[:RIFTS]


def age(world) -> list[str]:
    """上回合留下的分歧已交导演过目(v13)：交代满 DRIFT_TURNS 回的清走，其余留到下回合再提。返回留下的。引擎在导演后台拿到分歧之后调。"""
    me = world.player
    seen = dict(me.get("drift_seen") or {})
    keep = []
    for d in me.get("drift") or []:
        n = seen.get(d, 0) + 1
        if n < DRIFT_TURNS:
            seen[d] = n
            keep.append(d)
    me.set("drift", keep)
    me.set("drift_seen", {d: seen[d] for d in keep})
    return keep


def addressed(world, entry: str, applied) -> bool:
    """导演这一回合的后果碰到了分歧里点名的人或物（v13）：碰了就算圆回了，不必再提。分歧只点了主角自己的，只靠 DRIFT_TURNS 回的期限作罢。"""
    named = {n for n, _, _ in lexicon.find(entry, adjudicate.names(world)[0])} - {"player"}
    touched = {i for op in applied if isinstance(op, dict) for i in (op.get("id"), op.get("src"), op.get("dst"), op.get("value")) if isinstance(i, str)}
    return bool(named & touched)


# ============================================================
#  补记(v7 两相对账)：回合首末两份主角看得见的账，两份之差即这一回合主角该读到的变化；正文没写到的，由账本补一句
# ============================================================
def glance(world) -> dict:
    """主角此刻看得见的账：在哪、眼前与同行、谁受制、谁已死、谁负伤、身上有什么、叫得出谁、知道哪些隐情、武学练到哪一阶，与眼中每个人的样子。"""
    g, me = world.graph, world.player
    seen = sorted(situation.seen(world) - {"player"})
    return {"here": world.here,
            "around": sorted(situation.around(world)),
            "party": sorted(situation.party(world)),
            "captive": {p: sorted(situation.captors(world, p)) for p in seen if situation.captors(world, p)},
            "dead": sorted(p for p in seen if g.get(p, "status") == "dead"),
            "wounded": sorted(p for p in situation.around(world) if g.get(p, "status") == "wounded"),
            "inventory": sorted(me["inventory"]),
            "money": round(stock.funds(world, "player"), 3),
            "squads": {s: crowd.standing(g, s) for s in crowd.squads(world)},
            "besieged": sorted(crowd.besiegers(world)),
            "known": sorted(me["acquaintances"]),
            "secrets": sorted("|".join(s) for s in world.knowledge.secrets),
            "arts": {a["art"]: a["stage"] for a in growth.mastery(world)},
            "guise": {p: perspective.guise(world, p) for p in seen if g.kind(p) == "person"}}


def delta(world, before: dict) -> list[dict]:
    """这一回合主角该读到的变化：[{key, text(主角视角的一句，叫法过掩码), marks(正文里出现即算写到了的字眼)}]。
    出了原来那一处，只报到了哪里、谁随你来、那里有谁；近旁之内(没挪步或只挪了几步)才报谁来谁走。"""
    g, now = world.graph, glance(world)
    face = lambda p: perspective.handle(world, p)
    core = lambda h: (h or "").replace("的", "")[-4:]  # 「无量剑西宗的少年」编剧常写「西宗少年」
    marks = lambda p: [face(p), before["guise"].get(p), now["guise"].get(p), core(before["guise"].get(p)), core(now["guise"].get(p)),
                       p if perspective.knows(world, "player", p) else None]
    out: list[dict] = []

    def add(key, text, *ms):
        out.append({"key": key, "text": text, "marks": [m for m in dict.fromkeys(ms) if m and len(m) >= 2]})
    was, cur, dead = set(before["around"]), set(now["around"]), set(now["dead"])
    far = before["here"] != now["here"] and before["here"] not in situation.near(world, now["here"])  # 出了原来那一处(近旁之内挪几步不算)
    with_you = set(now["party"]) & was & cur if far else set()
    if before["here"] != now["here"]:
        add(f"here:{now['here']}", f"你到了{now['here'].split('·')[-1]}", *_cues(now["here"]))
    if far:  # 主角走了：被留在原处的人不是「离开了」；跟着来的是同行者，那里本来就有的是「此地有」
        for p in sorted(with_you):
            add(f"with:{p}", f"{face(p)}随你同行", *marks(p))
        for p in sorted(cur - was - set(now["party"])):
            add(f"at:{p}", f"此地有{face(p)}", *marks(p))
    else:
        for p in sorted(cur - was):
            add(f"came:{p}", f"{face(p)}来到你跟前", *marks(p))
        for p in sorted(was - cur - dead):
            add(f"left:{p}", f"{before['guise'].get(p, face(p)) if not perspective.knows(world, 'player', p) else p}离开了", *marks(p))
    for p in sorted(set(now["party"]) - set(before["party"]) - with_you):
        add(f"join:{p}", f"{face(p)}随你同行", *marks(p))
    for p in sorted(set(before["party"]) - set(now["party"])):
        add(f"part:{p}", f"{face(p)}与你分开了", *marks(p))
    for p, captors in now["captive"].items():
        if p not in before["captive"]:
            add(f"bound:{p}", f"{face(p)}落入{'、'.join(face(c) if c != 'player' else '你' for c in captors)}之手", *marks(p))
    for p in before["captive"]:
        if p not in now["captive"] and p not in dead:
            add(f"free:{p}", f"{face(p)}脱身了", *marks(p))
    for p in sorted(dead - set(before["dead"])):
        add(f"dead:{p}", f"{face(p)}死了", *marks(p))
    for p in sorted(set(now["wounded"]) - set(before["wounded"]) - dead):
        if p in was:
            add(f"hurt:{p}", f"{face(p)}受了伤", *marks(p))
    nick: dict[str, list[str]] = {}  # 器物的简称(v8)：正文写「那柄青钢剑」就是写到了剑架青钢剑
    for short, i in scenery.nicknames(world).items():
        nick.setdefault(i, []).append(short)
    for i in sorted(set(now["inventory"]) - set(before["inventory"])):
        add(f"got:{i}", f"{perspective.thing(world, i)}到了你手上", i, perspective.thing(world, i), *nick.get(i, ()))
    for i in sorted(set(before["inventory"]) - set(now["inventory"])):
        add(f"lost:{i}", f"{perspective.thing(world, i)}已不在你身上", i, perspective.thing(world, i), *nick.get(i, ()))
    gained = now["money"] - before.get("money", now["money"])  # 银两(v9)：多了、少了几钱，正文写到「银」「钱」字即算写到
    if abs(gained) > stock.EPS:
        add(f"money:{round(gained, 3)}", f"你身上{'多' if gained > 0 else '少'}了{stock.say(abs(gained))}银子", "银", "钱")
    for s in sorted(set(before.get("squads") or {}) | set(now["squads"])):  # 人群(v9)：倒下几人、散了
        was_n, now_n = (before.get("squads") or {}).get(s), now["squads"].get(s)
        if was_n and not now_n and not crowd.is_squad(g, s):
            add(f"flock:{s}", f"{crowd.handle(g, s)}四散而去", crowd.handle(g, s), crowd.handle(g, s)[-2:])
        elif was_n and now_n and now_n < was_n:
            add(f"flock:{s}", f"{crowd.handle(g, s)}倒下了{stock.cn(was_n - now_n)}人", crowd.handle(g, s), crowd.handle(g, s)[-2:])
    for s in sorted(set(now["besieged"]) - set(before.get("besieged") or [])):
        add(f"siege:{s}", f"{crowd.handle(g, s)}将你团团围住", crowd.handle(g, s), "围")
    for s in sorted(set(before.get("besieged") or []) - set(now["besieged"])):
        if crowd.is_squad(g, s):
            add(f"siege:{s}", f"你脱出了{crowd.handle(g, s)}的围困", crowd.handle(g, s), "围")
    for p in sorted(set(now["known"]) - set(before["known"])):
        if g.kind(p) == "person":
            add(f"name:{p}", f"{before['guise'].get(p) or now['guise'].get(p) or perspective.guise(world, p)}原来名叫{p}", p)
    for s in sorted(set(now["secrets"]) - set(before["secrets"])):
        src, dst, rel = s.split("|")
        if rel == ROAD:  # 暗路是地图上的一条路，不是人与人的关系（补记曾把内部字段 road 露给读者）
            add(f"secret:{s}", f"你发现了{src.split('·')[-1]}与{dst.split('·')[-1]}之间的一条暗路", "暗路")
        else:
            add(f"secret:{s}", f"你得知{face(src)}是{face(dst)}的{rel}", rel)
    for art, stage in now["arts"].items():
        if before["arts"].get(art) != stage and now["arts"].get(art) and stage:
            add(f"art:{art}:{stage}", f"你的{art}已到{stage}", art)
    return out


EXACT = ("here:", "got:", "lost:", "name:", "secret:", "art:")  # 字眼确凿的变化(地名、物名、人名、隐情、功夫)：正文里一字未见即没写到


def unwritten(changes: list[dict], text: str, missed=None) -> list[dict]:
    """正文没写到的变化。账房在场(missed 不是 None：它看过正文与变化清单)时听它的，再并上字眼确凿的几样——到了哪里、得失何物、
    谁的名字、哪桩隐情、哪门功夫，正文里一字未见就是没写到；人来人走、受伤受制，编剧常换说法(那书呆子、那西宗少年)，交账房判。
    账房不在(离线)，一律按字眼：这件事的人、物、地在正文里一个字也没出现。宁可补记一句读者已知的，不让一件账上的事读者一字未读。"""
    plain = _plain(text)
    absent = lambda c: not any(_plain(m) in plain for m in c["marks"])
    if missed is None:
        return [c for c in changes if absent(c)]
    return [c for c in changes if c["key"] in set(missed) or (c["key"].startswith(EXACT) and absent(c))]


def waive(doubt: list[dict], verdict: dict | None) -> list[dict]:
    """复核之后仍待定的句子：账房裁定「不记」的(只是打算、比喻、看错了)划掉，其余的才是分歧。"""
    gone = [_plain(x.get("据")) for x in (verdict or {}).get("不记") or [] if len(_plain(x.get("据"))) >= BASIS]
    return [d for d in doubt if not any(g in _plain(d["句"]) or _plain(d["句"]) in g for g in gone)]
