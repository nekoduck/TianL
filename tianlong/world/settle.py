"""
[INPUT]: 依赖 world/perspective 的 hear / speaker / mask / handle / knows / QUOTE（识名听写、说话人、视角掩码）、world/profile 的 profile（单一投影：账房看的账本快照）、
         world/effects 的 apply / describe / named / resolve（唯一写入通道）、world/adjudicate 的 afterword / unbidden（词表对账、授意）、
         world/situation 的 seen / near / party / captors（在场、近处、随行、受制）、world/body 的 INNER（内伤分级词）、world/growth 的 unearned / mastery、world/lexicon 的 mastery（进境账）
[OUTPUT]: 对外提供 Gate（正文出闸：逐段 听→掩→放行，放行即存档）、partners()（本回合与主角打交道的人）、
          books()（账房看的账本：定本正文、叫法对照、此刻账上每人每物、本回合已落账、近处地点）、
          commit()（账房的结算单落账：据须是正文原句、规则之事正文改不了、主角之举须经授意，经 effects 照常裁决 → (成立的指令, 分歧)）、
          audit()（词表对账：结算之后正文仍对不上账的去留得失生死擒放与进境，记作分歧；离线时它就是全部的对账）、admit()
[POS]: world 层的结算——v6「账文同构」的执行者。病根是双写：导演的指令进账本、编剧的正文给玩家，两份由模型各写各的，系统只拿正则对几类动词，
       账与文必然分叉(名字只是其中一种：去留、随行、持物、神色打算、看法、场景现状都会分叉，下一回合便在一本与玩家所读不符的账上接着演)。
       根治：玩家读到的正文是本回合的定本，账本是定本经世界裁决的投影——
       出闸(Gate)：正文按段放行，段里有人报了姓名先入账再过掩码(不涂成「小生兄台」)，放行的拼起来就是存下的正文；
       入账(books → narrative 的账房 → commit)：账房读定本与账本快照，开出正文确立而账上没有的变化，每条附正文原句为据、写明是谁做的；
       系统核对原句、只收叙述成立得了的事(去留、来人、随行擒放、易手、识名与隐情、神色打算、对主角的看法、现状、外号、应承之事)，经 effects 照常裁决——
       物理照旧只由世界裁定，账房只是把正文里已发生的事交给世界复核；伤病数值、生死、功力进境与远行归规则，正文写了账上没有的这几样，
       与落不了的变化一起记作分歧(player.drift)，下回合交导演由剧情圆回。结算之后账与文同构：下一回合的视锥、后台、记忆、选项都从它出发。
       纯规则、不调 LLM(账房在 narrative)、不新造实体
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import re

from . import adjudicate, effects, growth, lexicon, perspective, situation
from .body import INNER
from .profile import profile

RULED = {"status": "生死伤病", "hp": "气血", "max_hp": "气血", "power": "功力", "skills": "武学", "faction": "门派", "title": "名号头衔",
         "age": "年岁", "grants": "秘籍所载"}           # 归规则或归定义：正文写了，账房也改不了
BASIS = 4                                              # 据至少几个字：一个「你」字不算出处
RIFTS = 6                                              # 分歧至多交导演几条：多了便成了催债
MARK = re.compile(r"[\s「」“”『』\"'‘’…—]")
log = logging.getLogger("tianlong")


# ============================================================
#  出闸：正文按段放行——听(报了姓名先入账)→ 掩(按说话人)→ 放行；放行的就是存下的
# ============================================================
class Gate:
    """正文出闸。一段齐了：先听这一段里谁报了姓名(perspective.hear → effects，与拍文同一张词表、同一条写入通道)，
    再按每段台词的说话人过视角掩码，再放行。段与段之间的换行等下一段放行时才补上——头尾不留空行，
    放行的拼起来逐字就是存下的正文，流式与否一样。"""

    def __init__(self, world, near=()):
        self.world, self.near = world, list(near)
        self.parts: list[str] = []
        self.heard: list[dict] = []
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

    def _let(self, chunk: str) -> str:
        out, lines = [], chunk.split("\n")
        for i, line in enumerate(lines):
            if line.strip():
                lead = ("\n\n" if len(self._gap) > 1 else self._gap) if (self.parts or out) else ""
                out.append(lead + self._paragraph(line))
                self._gap = ""
            if i < len(lines) - 1:
                self._gap += "\n"
        released = "".join(out)
        if released:
            self.parts.append(released)
        return released

    def _paragraph(self, para: str) -> str:
        w = self.world
        applied, _ = effects.apply(w, perspective.hear(w, para, near=self.near), "director")  # 先听：读者读到了名字，就知道了名字
        self.heard += applied
        out, last = [], 0
        for m in perspective.QUOTE.finditer(para):  # 再掩：台词按说话人——不知主角姓名的人叫不出主角
            who = perspective.speaker(w, para, m.start(), m.end(), near=self.near)
            out += [perspective.mask(w, para[last:m.start()]), perspective.mask(w, m.group(0), who)]
            last = m.end()
        out.append(perspective.mask(w, para[last:]))
        return "".join(out)


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
def books(world, text: str, applied=()) -> dict:
    """账房看的账本：定本正文、叫法对照(正文里的「青衫少年」就是段誉)、此刻账上(主角、本回合见过的每个人、此地与地上器物)、
    本回合已落账之事(不必再记)、近处地点(来去只写这些)。"""
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
                                          ("与你", "；".join(pf["ties"]))) if v]
        cells += ["随你同行"] * (p in party) + [f"受制于{'、'.join(situation.captors(world, p))}"] * (p in held)
        cells.append(f"主角{'叫得出' if perspective.knows(world, 'player', p) else '叫不出'}此人的名字")
        cells.append(f"此人{'知道' if perspective.knows(world, p, 'player') else '不知'}主角的名号")
        return "｜".join(cells)
    here = world.here
    items = [i for i in g.where(type="item") if effects.place(world, i) in situation.near(world) and not g.get(i, "hidden")
             and g.get(i, "holder") is None]
    return {"text": text, "legend": legend,
            "player": "｜".join([f"主角（{me['name']}）", f"在{here}", f"随身：{'、'.join(me['inventory']) or '无'}",
                                f"境况：{'、'.join(me['conditions']) or '无'}", f"未了之事：{'；'.join(me['threads']) or '无'}"]),
            "people": [line(p) for p in people],
            "scene": f"{here}｜现状：{g.get(here, 'state') or '如常'}｜地上器物：{'、'.join(items) or '无'}",
            "applied": [effects.describe(op) for op in applied if op.get("key") not in ("threads",)],
            "places": sorted(situation.near(world))}


# ============================================================
#  入账：账房的结算单——据须是正文原句；叙述成立得了的事交世界复核，成立即落账，落不了与规则之事记作分歧
# ============================================================
def _plain(s: str) -> str:
    return MARK.sub("", s or "").strip("，。；！？、,.;!?")


def _known(world, op) -> bool:
    """指令里提到的人、地、物都是账上有的(主角亦然)：账房把「左子穆」写成 zuo_zimu，那一条丢掉，不当作正文与账本的分歧。"""
    ends = [op.get(k) for k in ("id", "src", "dst", "to") if op.get(k) is not None]
    ok = all(isinstance(x, str) and (effects.resolve(world, x) == "player" or world.graph.has(effects.resolve(world, x))) for x in ends)
    if not ok:
        log.info("账房写错了 id，不收：%s", op)
    return ok


def admit(world, op) -> str | None:
    """正文成立得了这条变化吗：不成立返回缘由。伤病数值、生死、功力进境、研习吸功归规则；远行归道路与光阴——
    这几样正文写了也只是分歧，交下一回合的导演圆回。"""
    if not isinstance(op, dict):
        return "格式不可解"
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


def commit(world, bill: dict, text: str, aim=frozenset()) -> tuple[list, list[str]]:
    """账房的结算单 {changes:[{据, 谁, ops}], rifts:[{据, 账上}]} 落账。据须是正文原句(去掉标点空白后是正文的一段，至少 BASIS 字)——
    对不上的是账房自己编的，不收；规则之事与落不了的变化记作分歧。主角之举(谁=主角)须在玩家所指之内(adjudicate.unbidden)：
    编剧替主角做了玩家没选的事，读者读到了也只是分歧，不替玩家落账。返回 (成立的指令, 分歧)。"""
    plain, applied, rifts = _plain(text), [], []
    me = world.player["name"]
    for ch in bill.get("changes") or []:
        basis = str(ch.get("据") or "").strip()
        if len(_plain(basis)) < BASIS or _plain(basis) not in plain:
            continue
        ops = [op for op in (ch.get("ops") or []) if isinstance(op, dict) and _known(world, op)]  # 写错了 id 是账房的错，不是账文分歧
        keep = []
        for op in ops:
            why = admit(world, op)
            if why:
                rifts.append(f"正文「{basis}」：{effects.describe(op)}——{why}")
            else:
                keep.append(op)
        if ch.get("谁") in ("player", "主角", me):
            for op, act, _ in adjudicate.unbidden(world, keep, set(aim)):
                rifts.append(f"正文「{basis}」：主角{act}——玩家并未起意，不入账")
                keep = [o for o in keep if o is not op]
        ok, bad = effects.apply(world, keep, "director")
        applied += ok
        rifts += [f"正文「{basis}」：{effects.describe(op)}——{why}" for op, why in bad]
    for r in bill.get("rifts") or []:
        basis, truth = str(r.get("据") or "").strip(), str(r.get("账上") or "").strip()
        if len(_plain(basis)) >= BASIS and _plain(basis) in plain and truth:
            rifts.append(f"正文「{basis}」，账上：{truth}")
    return applied, rifts


def audit(world, text: str) -> list[str]:
    """词表对账：结算之后，正文仍写着账上没有的得失、去留、生死、擒放(adjudicate.afterword)与进境(growth.unearned)——记作分歧。
    账房离线或失声时，这就是全部的对账：只记分歧、不改账(词表从不替正文挪人)。"""
    rifts = adjudicate.afterword(world, text)
    words = growth.unearned(world, lexicon.mastery(text, "player"))
    if words:
        arts = "；".join(a["detail"] for a in growth.mastery(world)) or "主角尚无武学"
        rifts.append(f"正文写主角「{'、'.join(words)}」，账上：{arts}")
    return rifts


def rifts(*groups) -> list[str]:
    """几处查出的分歧并作一份交导演：去重，至多 RIFTS 条。"""
    return list(dict.fromkeys(r for g in groups for r in g))[:RIFTS]
