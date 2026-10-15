"""
[INPUT]: 依赖 world/acts 的 expand / normalize / is_act / verb / SOFT（v9 事码）、world/crowd 的 handle / is_squad / squads / standing（人群）、world/stock 的 funds / is_cash / purse（银两），world/situation 的 shortnames（近处子地点的短名，与落账同一口径）、world/bond 的 before / derive（恩怨事件）、world/actor 的 feel（心境）、world/growth 的 studiable / arts_of / mastery / unearned（研习对象与进境账），
         world/effects 的 apply / describe / resolve（逐条落账）、world/lexicon 的 scan / table / find / secret_hits（拍文与账本的一致性体检）、
         world/situation 的 around / elsewhere / enlist / spawn / follow / join / free / rout / captive（情境层与连带）、world/perspective 的 audit / audience / hear / moment / calls（逐拍听写与称谓体检、那一拍的听众与遗体、导演宣告的识名须有拍文为据、「姓+称谓」的叫法），
         world/effects 的 unearth（场景物件认回现场的原著器物）、world/scenery 的 nicknames / TRIFLE（器物的简称、寻常之物），World 门面（graph / player / knowledge / here / turn / aliases）
         v13 另依赖 world/body 的 blow / mend_cap / hurt_word / SCRATCH / wound（伤疗归规则）、world/growth 的 studiable（授意标记 STUDY）、world/lexicon 的 STAY / NOT_STAY（留人）
[OUTPUT]: 对外提供 HARD / UNSURE 另有 afar（v12 望见之人开口）、judge(seek=…)（v12 小片区里寻人而至即遇：_found）、judge(stall=…) / SEIZED（v12 僵持到期押走：_seize）、physical()（v12 打算志向不算物理）、HANGING / hanging() / lines_to_player()（v12 须回应只认最后两拍里开口、回合末仍在眼前的人；各人对主角说的那一句）、pick()（v12 对象栏的一个名字：先在名表里整词认，人群叫法、眼前之人的叫法，落不到再交 effects.resolve）、MARKS / marked()（v12 授意标记 @书写 @交易 不是实体：选项验收只看实体；targets 判 @交易 之前先剔除 lexicon.TRADE_NOT，大喝、吃惊、点头不是吃喝买卖）、SERVED(v11 凭空端上桌的多半是店里的货：返工清单提示写买下)、TRADE(v11 玩家原话里起意买卖、吃喝、住店、请医、打听：主角的市井事码以此为授意)、names()（v11 名表里不随回合变的一大半——原著实体、别名、去「·」写法与类别——按图的结构版本缓存在 graph.memo，每回合只现算人群叫法、近处短名、见过之人的叫法与器物简称）、spoilers()（v11 一段要传开的话里的剧透：未揭隐情、尚未发生的擒与死、后台术语——场外剧情的说法用它；这桩事自己揭开的隐情(revealed)不算说破）、judge()（逐拍裁决导演的提议 → Ruling）、imply()（追认一回研习：玩家所指的秘籍在拍里被习练而导演漏写 study）、Ruling、doomed()（仍不成立须整拍作废的拍）、brief()（把硬违例译成给导演的修复清单：体检只陈述事实，怎么改(写 赶来、写 前往)与那件东西究竟在哪(暗藏在隔壁石室的，主角要先走过去)只写在这里，不随作废缘由流到编剧）、
          forged()（拍文或正文里拿出、递上的东西世上没有：v8 器物不得新造）、afterword()（编剧成文之后再对一次账：正文写了账上没有的得失去留生死擒放——v6 由 world/settle 在结算之后调用，记作分歧交下回合导演）、unbidden()（越权之举：主角做了玩家没指着的事，拍与结算单共用）、view()（回合起止两个切面）、names()（实体名表，含近处子地点的短名、本回合见过之人在主角眼中的叫法与「姓+称谓」——v7「容师叔毙命」死的是容子矩）、targets()（举动所指的实体）、physical()（改变物理状态的指令，节奏账据此判局面动没动）、HARD / RATIFY / UNSURE、WOUND / PARRY / HEAL / SCRATCH
[POS]: world 层的裁决器——「LLM 提议，世界裁决」的执行者。effects 只看一条指令成不成立；裁决器看拍与拍、拍与文字、拍与玩家之间：
       每一拍的后果挂在这一拍上，先授意（主角做的事——主角的拍、或写「你」而非别人给你的旁白——里取物、杀人、吸功、研习须是玩家所指：
       v5 只剥掉越权的那几条，这一拍其余照演(玩家要走就照走)，拍文后注明哪件事未曾发生、【未能成立】里明告编剧，越权之举降为下回合的候选选项；拍里只有越权之事则整拍不演），
       再落账，再以词表体检「写了变化却没有指令」的影子状态；随行、获救、败走这三种写漏了的连带由系统追认，其余硬违例交导演修复一次，
       仍不成立的拍整拍作废，化作一句失败的事实交编剧。
       一拍一事务(v3)：拍里改变物理状态的指令(去留、得失、生死、随行与拘押、赶来、研习、吸功、揭示)落不了，整拍即交返工；
       指令在拍文里无据即丢(无人说出口的识名、同拍写明被荡开的一击、研习之拍扣主角气血)；v13 起伤疗的数量不因拍文没写伤字眼而丢，封顶后落账、连带交编剧补写；
       主角自己的拍里无人出手又不涉险地，一拍至多伤 SCRATCH 点；
       台词的事实出处：尚未发生的原著(某人将被擒、将死)不得从任何人嘴里当作已知(foretold，返工不作废)；拍上的 mood 原样带给编剧、不入账；
       词表不再替导演挪人：只追认获救(解押)，随行、离去、叫错名字交返工但不作废；
       名册由事件写入(v5)：同在这一片的人被导演写进拍里(开口、下指令)即走到了主角跟前(_drawn)；
       事件先于状态(v4)：每拍落账之后 bond.derive 从已成立的指令推出恩怨事件、actor.feel 把拍上的情绪挂在此人脸上；研习是主角的举动，玩家没指着的秘籍导演不替他练(降为候选)；
       主角的去留有账可依(v5)：拍文写「你走进X」「你离开X」而账上没到、没走即 move 违例(台词里的去处、导演写了要去而止步关前的不算)；
       识名(v6)：逐拍先听再查——每一拍落账之后就地听写(听众是说话时在场的，连同这一拍赶来的，记在 turn["ears"])，听来的名字是识名指令、经 effects 入账；
       导演宣告的识名须有拍文为据(_grounded)：拍里没人说出口的名字丢掉，说出口的换成拍文听出来的那几条——谁听见由文字定，低声说给一人的只那人知道；
       时间轴(v7)：逐拍记下主角这一回合待过的每一处、那里的听众与眼前的遗体(turn["moments"]：{here, ears, bodies}，逐拍经 perspective.moment 进出那一刻)、
       每一拍发生在哪一刻(turn["beats_at"])——正文出闸时逐段逐句对齐到这里；
       view 公开回合起止两个切面，成文之后的对账与结算的复核共用；
       场景清单(v8)：名表收够得着之器物的简称(「青钢剑」即剑架青钢剑——玩家原话里的叫法认得出所指，不被当作越权剥掉)，寻常之物记作 trifle(取用只记软违例)；
       拍文里有人拿出、取来、递上一件世上没有的东西(forged)即 conjure 硬违例，交返工、仍不成立整拍作废；挪个方位(spot)不是物理；
       进境有账可依：主角的拍里写了账上没有的那一阶(「身如游龙」而未入门、「大成」而只初窥)即 mastery 违例，交返工不作废；同伴诸拍落定后才沿主角的路随行，擒者与人质须同处一地。纯规则、零 LLM 调用；同一份提议在同一世界上裁决两次结果相同（引擎据此先在副本上试演）
       事码(v9)：每拍的后果先经 acts.expand(平常之事化为指令、规则之事留作一件事)，授意、无据之检、一拍一事务照旧；事码写明主角做的，谁的拍都查授意——
       拿取、偷夺、毁撕须是玩家所指，对一群人杀伤须指着那一群，提笔书写须玩家起意(WRITE)；名表收人群的叫法(东宗弟子)，散了的人群不入；
       targets 认玩家说的钱(银子、钱)为够得着的碎银与钱袋、认写信留书为起意提笔；回合切面另记银两起止、经手之物(traded：拿了一部分、交出一部分)、有人倒下的人群；
       拍文里一群人有人倒下而账上人数没少即 fell(返工不作废)；forged 收紧为够得着之物(单字的名词须是器物名字的末字，「信」不是「内堂信笺」)，银两不是器物
       v10：回合开始记下眼前的人群(turn["flock0"]，主角先走一步他们仍可在后面的拍里结下随行)与眼前之人的银两(funds，谁的钱易手都对账)；WOUND 认一记耳光
       v12 P1-7 僵持到期(_seize)：场的僵持计数不小于 pacing.STALL_SEIZE、本回合导演仍没写结构性变化，围困主角的人群照它写下的打算(crowd.seizure)擒人押走——
       了断围攻、结下押解、那一群与被擒者前往去处，来源 RULED_BY(也是一处调遣)；先在副本上试，有一条落不了整桩不做、只记软违例；押的是主角即连那一群与在去处的首领上名册、
       时间轴补上去处那一刻；连带写明谁照其所图把谁擒下押往哪里(或就地扣下)、turn["seized"] 记下；体检在此之前，看的是导演的拍。_custody 对人群押着主角而两端异地，提示同一拍里写那一群与主角都前往同一处
       v13 否决即事件、授意是义务(P0-1/2/4、P1-5)：伤疗的数量归规则——_grounded 不再因拍文里没写伤字眼丢掉气血增减，落多少由 body.blow 封顶(导演报的血只是轻重)，同拍明写被避开的才不扣，
       落了账而拍文没写伤的记软违例 unwritten、连带交编剧补写(turn["hurt"])；conjure 降为 UNSURE(返工不作废，真碰了指令的指令自己落不了才作废)，泛称(灵草，GENERIC 首字+KINDS 末字)认回手边同类唯一之物(forged)；
       targets 另给授意标记 STUDY(起意研习)/SELF(起意自报家门、搭话)/VOW(起意立志)：玩家起意研习而本幕未被有来源地打断(_interrupted)，谁的拍都不得带主角走开(前往、脱身越权，turn["stay"])，
       漏写研习由 imply 补一拍(标 system，落不了只记缘由不交返工)；主角的姓名只有玩家自报才由导演宣告(识名 player 与拍文里听出来的都拦下，别人当面叫出他的名字不算)，主角的所求只有玩家立志或主角线了结(ARC_DONE)时才改；
       turn["aim"] 供 growth 认玩家所指的武学；主角吩咐同行者「在此藏好」(lexicon.STAY)而动身时没写了断随行：stay 交返工一次(UNSURE)，仍没写由系统替他了断、连带写明他留在原处(_stayers)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import logging
import re
from dataclasses import dataclass, field

from . import acts, actor, body, bond, crowd, effects, growth, lexicon, pacing, perspective, scenery, situation, stock, trade, venue
from .graph import holds

log = logging.getLogger("tianlong")

SEIZED = "押解"                   # 僵持到期押走(v12)：那一群 —押解→ 被擒者(situation.CUSTODY 之一)
HARD = {"foretold", "void", "acquire", "unnamed", "give", "absent", "kill", "drain", "bind", "spawn", "secret", "interrupt",
        "follow", "leave", "custody", "name", "mastery", "move", "conjure", "fell", "afar", "stay"}
RATIFY = {"free"}                 # 追认只解除拘押边（获救），从不挪动任何人：正则看错了，代价只是一条关系
UNSURE = {"follow", "leave", "name", "foretold", "mastery", "fell", "afar", "conjure", "stay"}  # 词表推断的去留、叫错的名字、疑似凭空的器物：交导演返工一次，仍不成立也不作废整拍——名字由 perspective.mask 兜底换掉；v13 凭空之物若真碰了指令，那条指令自己落不了（void）照样作废


@dataclass
class Ruling:
    beats: list[dict] = field(default_factory=list)       # 成立的拍 {who, to, text}
    applied: list[dict] = field(default_factory=list)     # 成立的指令
    void: list[str] = field(default_factory=list)         # 人话：未成立之事（指令驳回、整拍作废）
    hard: list = field(default_factory=list)              # 硬违例 Finding：交导演修复
    soft: list = field(default_factory=list)              # 软违例：只入日志
    notes: list[str] = field(default_factory=list)        # 连带后果（同伴跟上、研习进境、追认的获救与败走）
    candidates: list[str] = field(default_factory=list)   # 主角越权之举：不演，交编剧拟作下回合的选项
    addressed: list[str] = field(default_factory=list)    # 本回合对主角开口之人：下回合的选项须有回应
    said: dict[str, int] = field(default_factory=dict)    # v12 开口之人 → 他最后一次对主角开口是第几拍(已成立之拍，从 0 起)：须回应只认收尾时仍悬着的话
    question: dict = field(default_factory=dict)          # 本幕之问 {ask, state, by}
    spawned: list[str] = field(default_factory=list)


# ============================================================
#  实体名表：原著实体 + 别名 + 本回合的场景实体
# ============================================================
NAMED = ("person", "item", "group", "location", "skill")


def _base(world) -> tuple[dict, dict]:
    """名表里不随回合变的一大半(v11 按图的结构版本、别名表与散了的人群缓存)：原著实体、别名、去「·」的写法，连同它们的类别。"""
    g = world.graph
    key = (g.stamp[0], len(world.aliases), tuple(s for s in g.of(crowd.GROUP) if g.get(s, "disbanded")))
    hit = g.memo.get("names")
    if hit and hit[0] == key:
        return hit[1], hit[2]
    surface = {n: n for n in g.order(n for t in NAMED for n in g.of(t))
               if not g.get(n, "disbanded")}  # 散了的人群(v9)只是占住 id 的空壳，谁也看不见
    surface.update({a: n for a, n in world.aliases.items() if n in surface})
    surface.update({n.replace("·", ""): n for n in list(surface.values()) if "·" in n})
    kinds = {n: _kind(g, n) for n in set(surface.values())}
    g.memo["names"] = (key, surface, kinds)
    return surface, kinds


def _kind(g, n) -> str:
    node = g.nodes[n]
    return ("thing" if node.get("ephemeral") and node["type"] == "item" else
            "trifle" if node["type"] == "item" and node.get("grade") == scenery.TRIFLE else node["type"])  # 寻常之物(v8)：端起茶碗不必记账，取用只记软违例


def names(world) -> tuple[list, dict]:
    g = world.graph
    base, known = _base(world)
    surface = dict(base)
    squads = {crowd.handle(g, s): s for s in g.where(type=crowd.GROUP) if crowd.is_squad(g, s)}  # 「东宗弟子」即东宗弟子众(v9)
    surface.update(squads)
    surface.update({n.replace("·", ""): n for n in squads.values() if "·" in n})
    surface.update({short: loc for short, loc in situation.shortnames(world).items() if short not in surface})  # 「石级隧道」即琅嬛福地·石级隧道
    seen = {p for p in situation.seen(world) | set(situation.sighted(world)) if world.graph.kind(p) == "person"}  # v12 望见之人的叫法也认得
    surface.update({perspective.handle(world, p): p for p in seen
                    if not perspective.knows(world, "player", p)})  # 主角眼中的叫法：「大眼圆脸的少女」即钟灵——本回合见过的都算(v7：正文写到被甩在身后的人也认得)
    surface.update({c: p for c, p in perspective.calls(world, seen).items() if c not in surface})  # 「容师叔毙命」死的是容子矩，不是叫他的持剑少年(v7)
    surface.update({s: i for s, i in scenery.nicknames(world).items() if s not in surface})  # 「你取下青钢剑」说的是剑架青钢剑(v8 简称)
    kinds = {**known, **{n: _kind(g, n) for n in set(surface.values()) - known.keys() if g.has(n)}}
    return lexicon.table(surface), kinds


def pick(world, name, surface: dict | None = None):
    """对象栏里的一个名字落到实体(v12)：先在名表里整词认——人群的叫法(神农帮众)、眼前之人的叫法、近处短名，落不到再交 effects.resolve。"""
    if not isinstance(name, str):
        return name
    hit = (surface if surface is not None else dict(names(world)[0])).get(name.strip())
    return hit or effects.resolve(world, name)


def targets(world, deed: str, given=()) -> set[str]:
    """玩家举动所指的实体：选项自带的对象(v12 先在名表里整词认)，加上原话里认得出的名字（含主角对器物的近似叫法）。"""
    tab, _ = names(world)
    ents = lexicon.find(deed or "", tab)
    surface = dict(tab) if given else {}
    out = {pick(world, t, surface) for t in given if t} | {n for n, _, _ in ents}
    for word in filter(None, [lexicon.itemish(deed)]):
        hit = effects.resolve(world, word)
        if world.graph.kind(hit) == "item":
            out.add(hit)
    bare = lexicon.bare(deed or "", ents)  # 挖去实体名再看：「练武厅」不是练功
    practising = bool(lexicon.PRACTICE.search(bare))
    if practising and not any(world.graph.get(t, "grants") or world.graph.kind(t) == "skill" for t in out):
        out |= {s for s in growth.studiable(world) if world.graph.kind(s) == "item"}  # 「练功」而不说练哪部：手边的秘籍都算所指
    if lexicon.MONEYISH.search(lexicon.bare(deed or "", ents)):  # 「捡起那点银子」「拿他的钱」(v9)：够得着的碎银与钱袋都算所指
        g, close, around = world.graph, situation.near(world), situation.around(world) | {"player"}
        out |= {i for i in g.where(type="item") if (stock.is_cash(g, i) or stock.purse(g, i) > stock.EPS) and effects.usable(world, i)
                and (g.get(i, "holder") in around or (g.get(i, "holder") is None and g.get(i, "location") in close))}
    out = {t for t in out if isinstance(t, str) and world.graph.has(t)}
    deal = lexicon.TRADE_NOT.sub("", deed or "")  # 大喝、吃惊、点头不是吃喝买卖(v12)：先剔除再看，只为授意的精度
    taught = {k for p in out if world.graph.kind(p) == "person" for k in world.graph.get(p, "skills") or []}  # 指着某人，即可向他求教
    marks = {WRITE: lexicon.WRITING.search(deed or ""), TRADE: lexicon.TRADING.search(deal),
             STUDY: practising and growth.studiable(world, out | taught),  # v13 授意是义务：起意研习，这一回合主角就留在原处习练
             SELF: INTRO.search(deed or "") or (world.player["name"] and world.player["name"] in (deed or "")),
             VOW: VOWS.search(deed or "")}
    return out | {m for m, hit in marks.items() if hit}  # 起意提笔、花钱、研习、自报家门、立志：没有实体可指，以标记为记


# ============================================================
#  授意：主角做的事(主角的拍、或写「你」的旁白)里，取走他人或此地之物、毁物、杀人、吸功、研习，对象须在玩家所指之内
# ============================================================
TO_YOU = re.compile(r"(?:给|与|到|进|入)你|(?:向|朝)你(?:抛|掷|扔|递)")  # 你是收受的一方：东西是别人给的
WRITE = "@书写"   # 玩家原话里起意提笔(写信、写下、留书)：授意里没有实体可指，以此为记(v9)
TRADE = "@交易"   # 玩家原话里起意买卖、吃喝、住店、请医、打听(v11)：花的是主角的钱，以此为记
STUDY = "@研习"   # 玩家原话里起意研习、练功(v13 授意是义务)：这一回合主角留在原处习练，导演不得带他走开(本幕有来源地被打断除外)，漏写研习由系统补一拍
SELF = "@自报"    # 玩家原话里起意搭话、自报家门(v13)：主角的姓名只有玩家起意才由导演宣告
VOW = "@立志"     # 玩家原话里起意立志发愿(v13)：主角的所求只有玩家立志、或主角线已了结时才改
MARKS = frozenset({WRITE, TRADE, STUDY, SELF, VOW})  # 授意标记(v12)：不是实体——选项验收的可达与去重只看实体，标记由引擎下回合从原话重算
INTRO = re.compile(r"自报|报上|报出|报(?:个|出)?(?:名|姓名|名号|名字|家门)|通名|通报|自我介绍|介绍(?:一下)?自己|在下|我是|我叫|鄙人|小可|小生|"
                   r"搭话|攀谈|寒暄|招呼|拜见|拜会|拜访|求见|行礼|拱手|作揖|相认|结识|结交|攀交")  # 自报家门，与寻常的上前结交——后者自然要通名
VOWS = re.compile(r"立志|发誓|立誓|誓要|誓必|立下[^，。；！？]{0,4}[誓志]|立愿|发愿|宣誓|矢志|志向|所求")
ARC_DONE = 4      # story.arc.STAGES 里的「了结」：主角线已了，场记请导演提一条新的所求——这时导演写所求是系统请的
SERVED = re.compile(r"[壶碗杯盏碟盘酒茶菜饭面馍药丸散膏包]")  # 店里端上来的多半是这些：凭空出现时提示写买下(v11)


def marked(x) -> bool:
    """授意标记(v12)：@书写、@交易 不是实体，不当选项的对象。"""
    return x in MARKS


def _by_player(beat: dict) -> bool:
    """这一拍是不是主角在做事：主角的拍；或没有署名、写着「你」、又不是别人递给你的旁白(「你顺手拾起烛台」)。
    别人给主角东西(钟灵把解药塞给你、塞进你怀里)是他的举动，不归授意管。"""
    who, text = beat.get("who"), beat.get("text") or ""
    return who == "player" or (who is None and "你" in text and not TO_YOU.search(text))


def _hero_named(world, op) -> bool:
    """这条指令在宣告主角的姓名为人所知(自报家门)。"""
    named = effects.naming(world, op)
    return bool(named) and named.get("id") == "player"


def _arc_done(world) -> bool:
    """主角线已了结(v13)：场记请导演从最深的关系或最急的时限里提一条新的所求——这时导演写所求是系统请的，不算替主角做主。"""
    return (world.player.get("arc") or {}).get("stage") == ARC_DONE


def unbidden(world, ops: list, allowed: set[str]) -> list[tuple[dict, str, str]]:
    """越权之举：(那条指令, 一句人话, 所涉实体)。
    授意有两半(v13 授意是义务)：不做没选的(取走、杀人、吸功、毁物、提笔、花钱……)，也不替主角做主——
    研习这一回合主角留在原处(world.turn["stay"]：玩家起意研习而本幕未被有来源地打断)，导演带他走开即越权；
    主角的姓名与所求只有玩家自报、立志才由导演宣告(主角线了结时场记请导演写新的所求，不在此列)。"""
    g, out = world.graph, []
    stay = bool((getattr(world, "turn", None) or {}).get("stay"))
    allowed = allowed | {effects.resolve(world, a) for a in allowed}  # 玩家所指的叫法(蒲团里的帛卷)落回实体

    def ok(item):
        return item in allowed or g.get(item, "holder") in allowed or item in world.player["inventory"]
    taught = {k for p in allowed if g.kind(p) == "person" for k in g.get(p, "skills") or []}  # 指着某人，即可向他求教
    arts = {k for x in allowed if g.kind(x) in ("item", "skill") for k in growth.arts_of(g, x)}  # 指着秘籍，即指着它所载的武学

    for op in ops:
        if not isinstance(op, dict):
            continue
        if acts.is_act(op):  # 事码(v9)：主角拿、偷、夺、毁、撕、写、对人群下手，都须在玩家所指之内
            hit = _overreach(world, acts.normalize(world, op), allowed, ok, stay)
            if hit:
                out.append((op, *hit))
            continue
        kind, key = op.get("op"), op.get("key")
        nid, value = effects.resolve(world, op.get("id")), effects.resolve(world, op.get("value"))
        if stay and effects._moves_player(world, op):  # 玩家选了研习：导演不得带主角走开
            out.append((op, _leaving(effects.destination(op)), "player"))
            continue
        if SELF not in allowed and kind == "reveal" and _hero_named(world, op):  # 替主角自报家门
            out.append((op, "报上姓名", SELF))
            continue
        if VOW not in allowed and kind == "set" and nid == "player" and effects.PLAYER_ALIASES.get(key, key) == "goal" and not _arc_done(world):
            out.append((op, "改写你的所求", VOW))
            continue
        if kind == "push" and nid == "player" and key in ("inventory", "随身", "物品") and g.kind(value) == "item" and not ok(value):
            out.append((op, f"取走{value}", value))
        elif kind == "set" and key == "holder" and value == "player" and g.kind(nid) == "item" and not ok(nid):
            out.append((op, f"取走{nid}", nid))
        elif kind == "set" and key == "status" and value == "dead" and g.kind(nid) == "person" and nid not in allowed:
            out.append((op, f"杀了{nid}", nid))
        elif kind == "drain" and g.kind(value) == "person" and value not in allowed:
            out.append((op, f"吸取{value}的内力", value))
        elif kind == "study" and g.kind(value) in ("item", "skill") and value not in allowed \
                and not set(growth.arts_of(g, value)) & (allowed | taught | arts):
            out.append((op, f"研习{value}", value))  # 研习是主角的举动：玩家没指着这部秘籍或这门武学，导演不替他坐下来练
        elif kind == "set" and key == "state" and g.kind(nid) == "item" and isinstance(value, dict) \
                and value.get("exists") is False and nid not in allowed:
            out.append((op, f"毁去{nid}", nid))
        elif kind == "push" and key == "conditions" and value == "昏迷" and g.kind(nid) == "person" and nid not in allowed:
            out.append((op, f"打晕{nid}", nid))
    return out


def _leaving(dest) -> str:
    return f"离开此处前往{dest}" if isinstance(dest, str) and dest else "离开此处"


def _overreach(world, a: dict, allowed: set, ok, stay: bool = False) -> tuple[str, str] | None:
    """主角做的一件规则之事越不越权：(一句人话, 所涉实体)；不越权为 None。不是主角做的不归授意管。"""
    g, v = world.graph, a.get("做")
    if a.get("谁", "player") != "player":
        return None
    if stay and v == "脱身":  # 脱身也是走开(v13)
        return _leaving(a.get("到")), "player"
    item, src, to = a.get("物"), a.get("自"), a.get("对")
    if v == "拿取" and g.kind(item) == "item" and not ok(item):
        return f"取走{item}", item
    if v in ("偷取", "夺取") and src not in allowed and not (g.kind(item) == "item" and item in allowed):
        return f"{v}{crowd.handle(g, src) if crowd.is_squad(g, src) else src}的东西", src or item
    if v in ("杀死", "打晕") and crowd.is_squad(g, to) and to not in allowed:
        return f"{'杀' if v == '杀死' else '打倒'}{crowd.handle(g, to)}", to
    if v in ("毁去", "撕开") and g.kind(item) == "item" and item not in allowed and not (v == "撕开" and item in world.player["inventory"]):
        return f"{v}{item}", item
    if v == "书写" and WRITE not in allowed:
        return "提笔书写", WRITE
    if v in acts.MARKET and TRADE not in allowed and not (isinstance(item, str) and item in allowed):  # 花主角的钱、用主角的东西(v11)
        return f"{v}{item or a.get('事') or ''}", TRADE
    return None


# ============================================================
#  裁决
# ============================================================
DEATH = re.compile(f"{lexicon.KILL.pattern}|{lexicon.DIE.pattern}|死了|已死|遇害")


def _fates(world) -> list[tuple]:
    """尚未发生的原著里谁将被擒、谁将死：原著已演、或剧情里已成事实的(拘押边已在、人已死)不算。"""
    g, done, fates = world.graph, set(world.done), []
    for ev in world.canon:
        if ev["id"] in done:
            continue
        for op in ev["effects"]:
            if op.get("op") == "link" and op.get("rel") in situation.CUSTODY and not holds(g, op["src"], "~" + op["rel"], op["dst"]):
                fates.append((op["src"], op["dst"], lexicon.BIND))
            elif op.get("key") == "status" and op.get("value") == "dead" and g.get(op.get("id"), "status") != "dead":
                fates.append((op["id"], op["id"], DEATH))
    return fates


def spoilers(world, text: str, revealed=frozenset()) -> list[str]:
    """一段要传开的话(场外剧情的说法)里的剧透(v11)：说破未揭的隐情、把尚未发生的原著说成已成之事、带出后台术语。
    台词之外整段都查——它会变成传闻、传到编剧与玩家眼前。这桩事自己揭开的隐情(revealed：(src, rel, dst))不算说破：它随传闻一同抵达。"""
    tab = names(world)[0]
    named = {nid for nid, _, _ in lexicon.find(text, tab)}
    out = [f"说破了{s}与{d}之间的隐情" for s, _, d in lexicon.secret_hits(text, [x for x in _secrets(world) if x not in revealed], tab)]
    out += [f"把尚未发生的事（{b}{'被擒' if verb is lexicon.BIND else '身死'}）说成了已成之事"
            for a, b, verb in _fates(world) if {a, b} <= named and verb.search(text)]
    return out + [f"带出了后台术语「{x}」" for x in lexicon.leaks(text)]


def _foretold(world, shown, tab) -> list:
    """台词的事实出处：尚未发生的原著(某人将被擒、将死)不得从任何人嘴里当作已知说出——那是后台的原著近事，不是此刻的江湖。
    原著已演、或剧情里已成事实的(拘押边已在、人已死)不算。"""
    fates, out = _fates(world), []
    for i, beat in enumerate(shown, 1):
        for q in perspective.QUOTE.findall(beat.get("text") or ""):
            named = {nid for nid, _, _ in lexicon.find(q, tab)}
            for a, b, verb in fates:
                if {a, b} <= named and verb.search(q):
                    out.append(lexicon.Finding("foretold", i, b, f"第{i}拍的台词说出了尚未发生的事（{b}{'被擒' if verb is lexicon.BIND else '身死'}）："
                                                                 "原著近事只可借风声预兆，不得从人嘴里当作已知"))
                    break
    return out


def _secrets(world) -> list[tuple[str, str, str]]:
    return [(e["src"], e["rel"], e["dst"]) for e in world.graph.edges
            if e.get("secret") and not world.knowledge.knows_secret(e)]


def _drawn(world, beats: list) -> list[str]:
    """名册由事件写入(v5)：同在这一片、已露面而尚未到跟前的人(situation.elsewhere)，导演让他开口、对他下指令，
    就是写他走到了主角跟前——不必另写 arrive，也不因「不在你身边」整拍作废。远处的人照旧要 arrive、照旧核路程。"""
    near, out = set(situation.elsewhere(world)), []
    glimpsed = {acts.normalize(world, op).get("对") for b in beats for op in b.get("ops") or []
                if acts.is_act(op) and acts.normalize(world, op).get("做") == "望见"}  # 本回合望见的人(v12)：署名、写进事码也不拉上名册
    for b in beats:
        ops = [op for op in b.get("ops") or [] if isinstance(op, dict)]
        for x in [b.get("who"), b.get("to")] + [op.get(k) for op in ops for k in ("id", "src", "dst", "谁", "对", "自", "与")]:
            x = effects.resolve(world, x)
            if x in near and x not in out and x not in glimpsed:
                out.append(x)
    return out


def judge(world, plan: dict, allowed: set[str], *, embargo=frozenset(), cast=frozenset(),
          no_interrupt: bool = False, drop: dict | None = None, then=None, reserved=None, seek=(), stall: int = 0) -> Ruling:
    """逐拍裁决并落账到 world。allowed：玩家所指；embargo：原著近事里尚未到场的势力(门派级：只管补一队)；cast：此地原著的相关者（可作打断的来源）；
    reserved(v12 lod.reserved)：原著近事要用的人马 {人群: 事件}——写进 world.turn["reserved"]，effects 拦赶来、crowd 拦分人(试演与定稿各写一次，结算同样被拦)；
    seek(v12 menu.seeking)：玩家要找的人——诸拍与此地原著落定之后，他若同在主角近旁的小片区里而不在眼前，即上名册(连同同行者与扣着他的人)，寻到了；
    stall(v12 场的僵持计数，旧场没有按 0)：不小于 pacing.STALL_SEIZE 而本回合没有结构性变化，规则照围困人群写下的打算擒人押走(_seize)；
    drop：上一轮裁决仍不成立、此番整拍作废的拍号 → 缘由（0 号指 spawn 与本幕之问）；
    then：诸拍落账之后、体检之前要发生的事（此地上演的原著）——导演挪动过的人，原著再挪不动；原著挪走的人，拍文写他离去也不算漏记。
    一拍是一个事务：拍里改变物理状态的指令有一条落不了，整拍交返工、仍不成立即作废；伤疗的数量归规则（v13 _grounded：导演报的血只是轻重，规则封顶），不再因拍文里没写伤字眼而丢掉。
    同伴随行等诸拍落定才结算：拍中途解除了随行、被人擒住的，不会被主角先走一步带走。"""
    drop = drop or {}
    g, r = world.graph, Ruling(question=dict(plan.get("question") or {}))
    world.turn["reserved"] = dict(reserved or {})  # v12：带队之人级的禁令，物理(赶来、分人)与结算读它
    world.turn["sighted"] = []                     # v12：本回合望见的人(望见事码记下)，试演与定稿各从空起
    world.turn["hurt"] = 0                         # v13：主角这一回合真落了多少伤——收尾时连带写给编剧，免得账上有伤、正文没写
    world.turn["aim"] = set(allowed)               # v13：玩家所指(含授意标记)——研习练的是哪一门武学，growth 读它
    world.turn["stay"] = STUDY in allowed and not _interrupted(r.question)  # v13 授意是义务：玩家起意研习而本幕没有被有来源地打断，主角这一回合留在原处
    hp0 = world.player["hp"]
    situation.enlist(world, _drawn(world, plan["beats"]))  # 被导演写进拍里的同片之人：就当他走到了主角跟前
    here0, inv0, around0 = world.here, set(world.player["inventory"]), situation.around(world)
    money0 = stock.funds(world, "player")
    funds0 = {p: stock.funds(world, p) for p in around0 | {"player"} if p == "player" or g.kind(p) == "person"}  # v10 谁都对银两账
    flock0 = {s: crowd.standing(g, s) for s in crowd.squads(world)}  # 人群(v9)：回合开始时站着几人
    world.turn["present"] = around0  # 回合开始时身边之人：主角先走一步，他们仍可在后面的拍里跟上
    world.turn["flock0"] = set(crowd.squads(world))  # 回合开始时跟前的人群(v10)：主角先走一步，他们仍可在后面的拍里跟上
    world.turn["route"] = [here0]    # 主角本回合走过的路：同伴诸拍之后沿它跟上
    power0 = {p: g.get(p, "power") for p in around0}
    for spec in copy.deepcopy(plan.get("spawn") or []):
        canon = spec.get("kind") == situation.THING and effects.unearth(world, spec.get("name"))
        if canon:  # 导演另立的「帛卷」就是此地暗藏的原著秘籍：认回它、揭开暗藏，拍里的指令按此名落到它身上
            world.aliases[str(spec["name"]).strip()] = canon
            if g.get(canon, "hidden"):
                r.applied += effects.apply(world, [{"op": "set", "id": canon, "key": "hidden", "value": False}], "director")[0]
            continue
        nid, why = situation.spawn(world, spec, set(embargo))
        if nid:
            r.spawned.append(nid)
        elif 0 not in drop:
            r.hard.append(lexicon.Finding("spawn", 0, str(spec.get("name")), f"场景实体「{spec.get('name')}」不成立：{why}"))
    shown, touched, stripped, named = [], {}, set(), []
    beats = plan["beats"]
    moments = world.turn["moments"] = []  # 时间轴(v7)：主角这一回合待过的每一处与那里的听众——正文逐段对齐到这里
    world.turn["beats_at"] = []           # 每一拍发生在哪一刻：拍文与时刻，供正文对齐

    hero = {"speaks": False, "intro": False}  # 这一拍是不是主角在做事：他自己报的姓名才归授意管，别人当面叫出他的名字不算；intro 记下这一拍替他报了名而被拦下

    def vet(ops):  # 主角的姓名只有玩家起意自报才入账(v13)：拍文里替他报了的(导演宣告的与听写器听出的)，这一条不算，并明告编剧
        if SELF in allowed or not hero["speaks"] or not any(_hero_named(world, op) for op in ops):
            return ops
        hero["intro"] = True
        return [op for op in ops if not _hero_named(world, op)]

    def commit(ops):  # 听来的名字是识名指令(v6)：与一切后果同一条写入通道，成立的入本回合的账
        r.applied.extend(effects.apply(world, vet(ops), "director")[0])
    aimed = {effects.resolve(world, effects.destination(op)) for b in beats for op in acts.expand(world, b.get("ops") or [])
             if effects._moves_player(world, op)}
    for i, beat in enumerate(beats, 1):
        if i in drop:
            r.void.append(f"{(beat['text'] or '这一拍的后果').rstrip('。！')}——未曾发生：{'；'.join(drop[i])}")  # 与那件事同一句：词表整句看否定
            shown.append({**beat, "text": ""})
            continue
        raw, aside = acts.expand(world, beat.get("ops") or []), ""  # 事码(v9)：平常之事先化为指令，授意与无据之检照旧
        hero["speaks"] = _by_player(beat)
        stay = world.turn["stay"]
        over = unbidden(world, raw if hero["speaks"] else [op for op in raw if acts.is_act(op) or (stay and effects._moves_player(world, op))],
                        allowed)  # 事码写明了谁做(v9)：谁的拍都查；研习的回合里，谁的拍都不得带主角走开(v13)
        if over:  # 系统不替玩家做主：只剥掉越权的那几条，这一拍其余照演；越权之举留作下回合的选项，并明告编剧它没有发生
            deeds = [act for _, act, _ in over]
            r.candidates += [a for a in deeds if a not in r.candidates]
            r.void += [f"{a}——主角并未起意，未曾发生" for a in deeds]
            r.soft.append(lexicon.Finding("agency", i, "、".join(deeds), f"第{i}拍替主角{'、'.join(deeds)}，玩家并未授意"))
            stripped |= {ent for _, _, ent in over}
            raw = [op for op in raw if all(op is not o for o, _, _ in over)]
            if not raw:  # 这一拍只做了越权之事：整拍不演
                shown.append({**beat, "text": ""})
                continue
            aside = f"（其中{'、'.join(f'「{a}」' for a in deeds)}主角并未起意，未曾发生）"
        after = beats[i]["text"] if i < len(beats) and isinstance(beats[i].get("text"), str) else ""
        ops, dropped, odd = _grounded(world, copy.deepcopy(raw), beat.get("text") or "", after, beat.get("who"), beat.get("to"))
        hero["intro"] = False
        ops = vet(ops)  # 拍文里听出来的、替主角报了的姓名
        r.soft += [lexicon.Finding(kind, i, effects.describe(op), f"第{i}拍：{effects.describe(op)}——{why}", hard=False)
                   for op, kind, why in dropped]
        r.soft += [lexicon.Finding("unwritten", i, effects.describe(op), f"第{i}拍：{effects.describe(op)}——拍文里没写伤，伤照规则落账，由连带交编剧补写", hard=False)
                   for op in odd]
        at, ears, dead = world.here, perspective.audience(world), situation.bodies(world)
        if not moments or moments[-1]["here"] != at:
            moments.append({"here": at, "ears": set(), "bodies": set()})
        snap = bond.before(world, ops)
        hp_before = world.player["hp"]
        applied, rejected = effects.apply(world, ops, "director")  # 落账会就地规整指令：提议本身留给返工与定稿
        world.turn["hurt"] = world.turn.get("hurt", 0) + max(0, hp_before - world.player["hp"])  # 主角这一回合真落了多少伤（v13：交编剧补写进正文）
        r.applied += applied
        ears |= perspective.audience(world) & set(world.turn.get("arrived", ()))  # 这一拍说话时在场的，连同这一拍赶来的
        dead |= situation.bodies(world) if world.here == at else set()            # 这一拍眼前的遗体，连同这一拍倒下的
        with perspective.moment(world, ears, dead):
            named += perspective.audit(world, [beat], ears, commit, start=i)  # 逐拍先听再查：主角走开之后说的话，厅上的人听不见
        if hero["intro"] and "「报上姓名」" not in aside:  # 导演自己写了识名的，上面 unbidden 已经记过一回
            r.void.append("报上姓名——主角并未起意，未曾发生")
            r.soft.append(lexicon.Finding("agency", i, "报上姓名", f"第{i}拍替主角报上姓名，玩家并未授意"))
            aside += "（其中「报上姓名」主角并未起意，未曾发生）"
        moments[-1]["ears"] |= ears
        moments[-1]["bodies"] |= dead
        world.turn["beats_at"].append((beat.get("text") or "", len(moments) - 1))
        bond.derive(world, beat.get("who"), applied, snap, beat.get("text") or "", beat.get("to"))  # 事件先于状态：恩怨从做了什么里推出
        actor.feel(world, beat.get("who"), beat.get("mood"))  # 拍上的情绪挂在此人脸上几回合
        for nid in (i2 for op in applied for i2 in effects._ids(op)):
            touched[nid] = i
        for op, why in rejected:
            line = f"{effects.describe(op)}——{why}"
            r.void.append(line)
            partial = effects._moves_player(world, op) and world.here != at  # 远行止步关前：前半程成立，交编剧写明，不必返工
            hard = physical(op) and not partial and bool((beat.get("text") or "").strip()) and not beat.get("system")  # 无文字的拍(旧写法的顶层后果)没有拍文可违；系统补的拍不是导演写的，落不了只记缘由
            ent = _thing(world, op) or effects.describe(op)  # 落不了的是一件器物：返工清单写明它究竟在哪
            (r.hard if hard else r.soft).append(lexicon.Finding("void", i, ent, f"第{i}拍：{line}", hard=hard))
        r.beats.append({**{k: beat.get(k) for k in ("who", "to", "text", "mood")}, "text": (beat.get("text") or "") + aside})
        shown.append(beat)
        if beat.get("to") == "player" and beat.get("who") not in (None, "player"):
            speaker = effects.resolve(world, beat["who"])
            r.addressed.append(speaker)
            r.said[speaker] = len(r.beats) - 1
    route = world.turn.pop("route")
    if len(route) > 1:
        for pid, i in _stayers(world, shown):  # 主角吩咐留下的同行者(v13)：说了「在此藏好」而没写了断随行，交返工一次，仍没写即由系统替他了断、写明他留在原处
            r.hard.append(lexicon.Finding("stay", i, pid, f"第{i}拍你吩咐{pid}留在此处，却没有了断他的随行：他会跟着你走——要他留下就写 了断 {pid}→player 随行"))
            situation.part(world, pid)
            effects._note(world, f"{pid}留在了原处，没有跟你走")
        for pid in situation.party(world):
            touched.setdefault(pid, touched.get("player", 0))
        effects._note(world, situation.follow(world, route))
    if then:
        then()
    _found(world, seek)
    if not moments or moments[-1]["here"] != world.here:  # 主角最后到了哪里：那一刻的听众到成文时再看
        moments.append({"here": world.here, "ears": set(), "bodies": set()})
    _custody(world, r, touched)
    world.turn["start"] = {"here": here0, "inventory": inv0, "around": around0, "route": route, "aimed": aimed,
                           "money": money0, "flock": flock0, "funds": funds0, "hp": hp0}  # 编剧成文之后的对账也以此为准
    if world.turn["hurt"] > 0:  # v13 账上落了伤，正文就得写：连带交编剧（不报数字，只说轻重），拍文没写伤的由它补写
        effects._note(world, f"你受了{body.hurt_word(world.turn['hurt'], world.player['max_hp'])}：这一下确实落在你身上，须写进正文")
    _examine(world, r, shown, power0, stripped, named)
    _question(world, r, cast, no_interrupt and 0 not in drop)
    _seize(world, r, stall, world.here != here0)
    r.notes = list(world.turn.get("notes", []))
    return r


def _seize(world, r: Ruling, stall: int, moved: bool):
    """僵持到期(v12)：危局连着 STALL_SEIZE 回合没有结构性变化、本回合导演仍没写，围困主角的人群照它写下的打算(crowd.seizure)擒人押走——
    规则只照剧情写下的打算落账，不替导演编剧情。指令依次为：了断那一群对主角的围攻、结下 那一群 —押解→ 被擒者、有去处时那一群与被擒者都前往去处；
    来源 RULED_BY(也是一处调遣：本回合已被别处挪过的人押不走)。先在副本上试，全部成立才在本世界照做；有一条落不了(另有一群人也围着主角)整桩不做，只记软违例。
    押的是主角且有去处：那一群与在去处的首领上名册(押到首领跟前)，时间轴补上去处那一刻；押的是别人，不动主角的名册。体检在此之前，看的是导演的拍。"""
    if stall < pacing.STALL_SEIZE or pacing.structural(r.applied, moved):
        return
    plan = crowd.seizure(world, names(world)[0])
    if not plan:
        return
    g, s, who, to = world.graph, plan["by"], plan["who"], plan["to"]
    ops = [{"op": "unlink", "src": s, "dst": "player", "rel": crowd.BESIEGE}, {"op": "link", "src": s, "dst": who, "rel": SEIZED}]
    ops += [{"op": "set", "id": x, "key": "location", "value": to} for x in (s, who)] if to else []
    trial = copy.copy(world)
    trial.graph, trial.player, trial.turn, trial.knowledge = (copy.deepcopy(x) for x in (world.graph, world.player, world.turn, world.knowledge))
    _, rejected = effects.apply(trial, copy.deepcopy(ops), effects.RULED_BY)
    if rejected:
        why = "；".join(f"{effects.describe(op)}——{reason}" for op, reason in rejected)
        r.soft.append(lexicon.Finding("seize", 0, s, f"僵持到期，{crowd.handle(g, s)}照其所图擒人不成：{why}", hard=False))
        log.info("僵持到期押走不成：%s", why)
        return
    applied, _ = effects.apply(world, ops, effects.RULED_BY)
    r.applied += applied
    if who == "player" and to:
        lead = g.get(s, "leader")
        situation.enlist(world, [s] + ([lead] if lead and g.has(lead) and g.get(lead, "location") == to and g.get(lead, "status") != "dead" else []))
        moments = world.turn.setdefault("moments", [])
        if not moments or moments[-1]["here"] != world.here:  # 正文在去处听到的名字才落得到人
            moments.append({"here": world.here, "ears": set(), "bodies": set()})
    world.turn["seized"] = {"by": s, "who": who, "to": to}
    effects._note(world, f"{crowd.handle(g, s)}照其所图，将{'你' if who == 'player' else who}擒下，{f'押往{to}' if to else '就地扣下'}")
    log.info("僵持到期押走：%s", world.turn["seized"])


def _found(world, seek):
    """小片区里寻人而至即遇(v12)：玩家要找的人同在主角近旁的小片区里(situation.elsewhere 且 small_area)，到了这一片就寻到了——
    此人、他的同行者与扣着他的人一并上名册；只写名册不挪人，纯规则，试演与定稿一致。中原、大理城这种大地方不算。"""
    g, hidden = world.graph, set(situation.elsewhere(world))
    for p in seek or ():
        if p in hidden and situation.small_area(world, g.get(p, "location")):
            situation.enlist(world, [p, *situation.company(world, p), *situation.captors(world, p)])
            effects._note(world, f"你在这一带寻到了{p}")


HANGING = 2  # 须回应只认本回合最后两拍里对主角开口的人(v12)：那句话之后又过了三四拍(有人毙命、放貂、求情)，早已过时


def hanging(world, r: Ruling) -> list[str]:
    """收尾时仍悬着的话(v12)：对主角开口的那一拍在本回合最后 HANGING 拍之内、此人此刻仍在眼前——按开口先后排。
    编剧的【须回应】与选项验收的回应都只认这几人；被甩在身后的人、早已过时的话不再要求回应。"""
    last, close = len(r.beats) - HANGING, situation.around(world)
    return [p for p, i in sorted(r.said.items(), key=lambda x: x[1]) if i >= last and p in close]


def lines_to_player(world, r: Ruling) -> dict[str, str]:
    """本回合各人对主角说的最后一句(v12)：回应的措辞按那一句的主题定(盘问、拦阻、催促、赔罪)。"""
    return {effects.resolve(world, b["who"]): b.get("text") or "" for b in r.beats
            if b.get("to") == "player" and b.get("who") not in (None, "player")}


# ============================================================
#  一拍一事务：哪些指令是这一拍的筋骨，落不了整拍便不成立；哪些指令在拍文里无据
# ============================================================
WOUND = re.compile(r"伤|血|痛|跌|摔|撞|刺中|刺入|刺伤|砍中|劈中|击中|打中|拍中|掌中|中掌|中剑|中毒|毒发|擦破|咳|呕|吐出|昏|晕|反噬|岔气|走火|灼|烫|咬|抓破|划破|骨折|断了|掴|耳光|巴掌")  # 一记耳光也是伤(v10 实测)
PARRY = re.compile(r"荡开|荡了开|架开|格开|挡开|拦开|拨开.{0,2}(?:剑|刀|掌|招)|拨了开|避开|闪开|躲开|让开|落空|扑空|险险避过|堪堪避过|毫发无伤|毫发未伤")
SCRATCH = body.SCRATCH                           # 非较量场合一拍至多伤几点(v13 定义在 body)


def physical(op) -> bool:
    """改变物理状态的指令：去留、得失、生死伤病、擒放随行、赶来、研习吸功、揭开暗路与隐情。
    只有恩怨印象(其余关系)、未了之事、地点现状落不了是小事——丢那一条，拍照常成立。
    v12：打算、志向、所求与外号、神色一样是软状态，不算物理——落不了只丢这一条；节奏账也不把只改打算记成局面动了。"""
    if not isinstance(op, dict):
        return False
    if acts.is_act(op):  # 事码(v9)：规则之事都动物理(得失、撕合、书写、脱身、人群死伤)，软的几样不算
        return acts.verb(op) not in acts.SOFT
    kind, key = op.get("op"), op.get("key")
    if kind in ("link", "unlink"):
        return op.get("rel") == situation.FOLLOW or op.get("rel") in situation.CUSTODY
    if kind in ("arrive", "study", "drain", "reveal"):
        return not effects.named(op)  # 报个姓名是认知不是物理(v6)：落不了只丢这一条，拍照常成立
    return key not in ("threads", "未了之事", "state", "note", "epithet", "mood", "spot", "intent", "agenda", "goal")  # 器物挪个方位(v8)不是得失；打算志向(v12)不是物理


def _doer(world, name) -> str | None:
    """出手者的 id（v13）：主角、人、一群人的叫法都落得回实体；认不出为 None。"""
    if not isinstance(name, str) or not name.strip():
        return None
    who = pick(world, name)
    return who if who == "player" or world.graph.has(who) else None


def _grounded(world, ops: list, text: str, after: str, who=None, to=None) -> tuple[list, list, list]:
    """落账之前对一拍的指令再核一遍，返回 (照落的指令, 丢掉的 [(指令, 种类, 缘由)], 落了账而拍文没写伤的指令)。
    气血（v13 否决即事件）：伤人落多少血不再看拍文里有没有伤的字眼——导演报的数只是轻重，规则封顶（body.blow：攻守档位差×命运骰，
    一群人看胜算比，无人出手 SCRATCH、涉险 HAZARD），疗伤一拍至多 HEAL_CAP；落了账而拍文没写伤的，记一条软违例，由连带交编剧补写。
    只剩两种有因的不扣：同拍（或下一拍）明写那一击被避开了而没有一个伤字（拍文与指令相悖，以拍文为准），与研习之拍（顺逆归研习预裁）。
    识名（v6）：导演宣告某人的姓名为人所知，拍文里须真有人说出它(自报家门、互通姓名、认得的人当面叫出)——
    宣告换成拍文听出来的那几条(谁听见由文字定：低声说给一人的只那人知道)；没人说出口的名字，不因导演想在旁白里用它就算人人知道。"""
    moving = any(effects._moves_player(world, op) for op in ops)
    keep, drop, odd, heard = [], [], [], None
    studying = any(isinstance(op, dict) and op.get("op") == "study" for op in ops)
    for op in ops:
        if effects.naming(world, op):
            heard = perspective.hear(world, text, who, to) if heard is None else heard
            said = [h for h in heard if h["id"] == effects.naming(world, op)["id"]]
            keep += [h for h in said if h not in keep]
            if not said:
                drop.append((op, "baseless", "拍文里无据，不入账"))
            continue
        if isinstance(op, dict) and op.get("op") == "add" and op.get("key") in ("hp", "气血") \
                and isinstance(op.get("value"), (int, float)):
            target = effects.resolve(world, op.get("id"))
            if op["value"] < 0:
                if target == "player" and studying:
                    drop.append((op, "study_hurt", "研习的顺逆归研习预裁，不另扣血"))
                    continue
                if PARRY.search(text + after) and not WOUND.search(text):
                    drop.append((op, "parried", "同拍写明那一击被避开了"))
                    continue
                by = _doer(world, op.get("by")) or _doer(world, who)
                if by in (None, target) and who not in (None, "player") and _doer(world, who) != target:
                    by = _doer(world, who)  # 伤人没写谁出手（缺省是主角），而这是别人的拍：出手的是他
                op["value"] = -body.blow(world, by, target, op["value"], moving and target == "player")
                if not WOUND.search(text):
                    odd.append(op)
            else:
                op["value"] = body.mend_cap(op["value"])
        keep.append(op)
    return keep, drop, odd


def _stayers(world, shown: list) -> list[tuple[str, int]]:
    """主角这一回合吩咐留下、却仍与他同行的人(v13)：主角的拍里有一句「你在此藏好」「留在原处等我」「别跟来」，对象是同行者——点了名(或拍的 to)的那一位，
    没点名而恰有一位同行者的就是他。主角没走远则无从谈起（调用方只在主角动身时问）。返回 [(同行者, 第几拍)]。"""
    party, out = set(situation.party(world)), []
    if not party:
        return out
    tab = names(world)[0]
    for i, beat in enumerate(shown, 1):
        text = beat.get("text") or ""
        if not _by_player(beat) or not lexicon.STAY.search(text):
            continue
        for clause in lexicon._clauses(text):
            if not lexicon.STAY.search(clause) or lexicon.NEGATE.search(clause) or lexicon.NOT_STAY.search(clause):
                continue
            named = {n for n, _, _ in lexicon.find(clause, tab)} & party
            named |= {effects.resolve(world, beat.get("to"))} & party if beat.get("to") else set()
            hit = lexicon.STAY.search(clause)
            if not named and len(party) == 1 and "你" in clause[max(0, hit.start() - 4):hit.end()]:  # 没点名而恰有一位同行者：「你在此藏好」是对他说的，「你把通天草藏好」不是
                named = set(party)
            out += [(p, i) for p in sorted(named) if p in party and all(p != q for q, _ in out)]
    return out


def _custody(world, r: Ruling, touched: dict[str, int]):
    """不变量：擒者与人质同处一地。本回合碰过其中一方而两人分处两地，是哪一拍写歪了，就记在哪一拍上。
    v12 一群人押着主角而两端异地：押走就在同一拍里写那一群与主角都前往同一处，不押了就写了断。"""
    g = world.graph
    for e in g.edges:
        if e["rel"] not in situation.CUSTODY:
            continue
        a, b = e["src"], e["dst"]
        beat = max(touched.get(a, 0), touched.get(b, 0))
        pa, pb = effects.place(world, a), effects.place(world, b)
        if not (beat and pa and pb and pa != pb):
            continue
        if b == "player" and crowd.is_squad(g, a):
            r.hard.append(lexicon.Finding("custody", beat, b, f"第{beat}拍之后你在{pb}、押着你的{crowd.handle(g, a)}却在{pa}：押走就在同一拍里写"
                                                             f"那一群与主角都前往同一处；不押了就写 了断 {a}→player {e['rel']}"))
        else:
            r.hard.append(lexicon.Finding("custody", beat, b, f"第{beat}拍之后{b}在{pb}、擒住{b}的{a}却在{pa}：擒者走则人质随之；"
                                                             f"要{b}随你走，须先写明救下{b}（了断拘押、结下随行）"))


def _view(world, start: dict, power0=None) -> lexicon.View:
    """回合起止两个切面：拍文体检与成文之后的对账共用。v9 另有主角经手的东西(拿了一部分、交出一部分，traded)与银两的起止。"""
    g, here0 = world.graph, start["here"]
    return lexicon.View(here_start=start["around"], here_end=situation.around(world), arrived=set(world.turn.get("arrived", ())),
                        inventory_start=start["inventory"], inventory_end=set(world.player["inventory"]),
                        dead={p for p in g.where(type="person") if g.get(p, "status") == "dead"},
                        drained={p for p, v in (power0 or {}).items() if (g.get(p, "power") or 0) < (v or 0)},
                        captive=situation.captive(world), moved=world.here != here0,
                        here=world.here, route=set(start["route"]) | {here0, world.here}, aimed=set(start["aimed"]),
                        traded=set(world.turn.get("traded", ())), money_start=start.get("money", 0.0),
                        money_end=stock.funds(world, "player"),
                        funds={p: (v, stock.funds(world, p)) for p, v in (start.get("funds") or {}).items()},
                        felled={s for s, n in (start.get("flock") or {}).items() if not crowd.is_squad(g, s) or crowd.standing(g, s) < n},
                        sighted=set(situation.sighted(world)))


def _examine(world, r: Ruling, shown, power0, stripped=frozenset(), named=()):
    """落账之后体检拍文：写了变化却没有指令即为违例；随行、获救、败走照拍文追认，其余交导演。
    越权而被剥掉的那几件(取走、杀、吸)已明告编剧未曾发生，拍文里提到它们不再算违例。named 是逐拍听写时查出的称谓违例。"""
    tab_kinds = names(world)
    view = _view(world, world.turn["start"], power0)
    found = [f for f in lexicon.scan(shown, view, *tab_kinds)
             if not (f.kind in ("acquire", "kill", "drain", "give") and f.entity in stripped)
             and not (f.kind == "conjure" and not forged(world, f.entity))]  # 拍文里拿出来的东西世上有(或说的就是眼前某物)：不算凭空造
    found += list(named)
    secrets = _secrets(world)
    for i, beat in enumerate(shown, 1):
        for src, rel, dst in lexicon.secret_hits(beat.get("text") or "", secrets, tab_kinds[0]):
            found.append(lexicon.Finding("secret", i, f"{src}—{rel}—{dst}",
                                         f"第{i}拍说破了未揭的隐情（{src}与{dst}）：要揭开就写 揭开，否则只可伏笔"))
    found += _foretold(world, shown, tab_kinds[0])
    found += _mastery(world, shown)
    for f in found:
        if f.kind in RATIFY and _ratify(world, f):
            r.soft.append(f)
        elif f.kind in HARD and f.hard:
            r.hard.append(f)
        else:
            r.soft.append(f)


AFTER = {"acquire", "give", "kill", "drain", "bind", "free", "follow", "leave", "move"}  # 成文之后还要对账的变化


def view(world) -> lexicon.View | None:
    """本回合起止两个切面(裁决之后才有)：成文之后的对账与结算的复核共用。"""
    start = (getattr(world, "turn", None) or {}).get("start")
    return _view(world, start) if start else None


def afterword(world, text: str) -> list[str]:
    """编剧成文之后再对一次账(v5)：正文写了账上没有的得失、去留、生死、擒放(与拍文同一口径，以回合起止两个切面为准)——
    读者已经读到，改不回来，记作偏差，下回合交导演由剧情交代或圆回。须在本回合裁决之后调用(world.turn["start"])。"""
    v = view(world)
    if not v or not text:
        return []
    found = lexicon.scan([{"who": None, "text": text}], v, *names(world))
    return [f.message.replace("第1拍", "正文") for f in found if f.kind in AFTER and f.hard]


def _mastery(world, shown) -> list:
    """进境措辞有账可依：主角的拍里写了「练成」「身如游龙」，本回合却没有兑现任何一阶进境，即为违例——
    练到哪一步由研习账说了算(world/growth)，文字只渲染已成立的进境。"""
    out = []
    for i, beat in enumerate(shown, 1):
        words = growth.unearned(world, lexicon.mastery(beat.get("text") or "", beat.get("who")))
        if words:
            arts = "；".join(a["detail"] for a in growth.mastery(world)) or "主角尚无武学"
            out.append(lexicon.Finding("mastery", i, words[0], f"第{i}拍写主角「{'、'.join(words)}」，账上并无这一阶进境（{arts}）："
                                                             "进境以研习账为准，改写成正在习练、略有心得或尚未入门"))
    return out


def imply(world, plan: dict, allowed: set[str]) -> str | None:
    """追认一回研习：玩家所指的是够得着的秘籍或武学(或身边会它的人)，主角的拍里写着习练，导演却没写 study——
    系统替它补上这条指令(追认，不新造物理：研习本就是玩家所选之事)。返回追认的研习对象，没有即 None。
    v13 授意是义务：玩家起意研习(STUDY)而本幕没有被有来源地打断，主角的拍里一拍习练也没有——系统补一拍(标 system)，
    免得导演写段誉的催促、带主角走开，选了的研习却无声无息地没了(第 51 回)。"""
    beats = plan.get("beats") or []
    if any(isinstance(op, dict) and op.get("op") == "study" for b in beats for op in acts.expand(world, b.get("ops") or [])):
        return None  # 导演写了研习(指令或事码)
    aim = set(allowed) | {k for p in allowed if world.graph.kind(p) == "person" for k in world.graph.get(p, "skills") or []}
    sources = growth.studiable(world, aim) if aim else []
    if not sources:
        return None
    for b in beats:
        if b.get("who") in (None, "player") and lexicon.PRACTICE.search(b.get("text") or ""):
            b["ops"] = list(b.get("ops") or []) + [{"op": "study", "id": "player", "value": sources[0]}]
            return sources[0]
    if STUDY in allowed and not _interrupted(plan.get("question") or {}):
        beats.append({"who": "player", "to": None, "mood": None, "system": True, "text": f"你依先前所定，留在原处习练{sources[0]}。",
                      "ops": [{"op": "study", "id": "player", "value": sources[0]}]})
        return sources[0]
    return None


def _interrupted(q: dict) -> bool:
    """本幕被打断(导演报 断 并写明了 by)：来源成不成立由 _question 查，这里只看导演有没有报——打断了，研习才可以中断、主角才可以被带走。"""
    return q.get("state") == "interrupted" and bool(q.get("by"))


def _ratify(world, f) -> bool:
    """照拍文追认连带：只追认获救——解除拘押边，不挪动任何人。随行与败走是物理，交导演写明。"""
    if f.kind == "free":
        who = situation.free(world, f.entity)
        world.turn.setdefault("notes", []).append(f"{f.entity}脱离了{'、'.join(who)}的拘押")
        return True
    return False


def _question(world, r: Ruling, cast, no_interrupt: bool):
    """本幕之问被打断，须有来源：在场或赶来之人、刚立的群体、此地上演的原著相关者；连番打断之后，本回合必须了结。"""
    q = r.question
    if q.get("state") != "interrupted":
        return
    if no_interrupt:
        r.hard.append(lexicon.Finding("interrupt", 0, "", "本幕之问已连番被打断，本回合须让它有个了结（resolved 或 open），不得再打断"))
        return
    by = effects.resolve(world, q.get("by"))
    if by not in situation.around(world) | set(r.spawned) | set(cast):
        r.hard.append(lexicon.Finding("interrupt", 0, str(q.get("by")),
                                      f"打断须有来源：「{q.get('by')}」既不在场、也未赶来、不是原著此刻的相关者"))


# ============================================================
#  修复清单：硬违例 + 让导演改得对的线索（那件东西究竟在谁手里、那人究竟在哪）
# ============================================================
def doomed(ruling: Ruling) -> dict[int, list[str]]:
    """返工之后仍不成立、须整拍作废的拍号 → 缘由。拍里改变物理状态的指令落不了，拍文便与账本对不上，整拍作废；
    词表推断的去留(UNSURE)可能看错，只交返工、不作废。"""
    out: dict[int, list[str]] = {}
    for f in ruling.hard:
        if f.kind not in UNSURE and f.beat > 0:
            out.setdefault(f.beat, []).append(f.message)
    return out


def brief(world, ruling: Ruling) -> list[str]:
    g, lines = world.graph, []
    for f in ruling.hard:
        line = f.message
        if f.kind in ("acquire", "give", "void") and g.kind(f.entity) == "item":  # 暗藏在隔壁的东西：主角要先到那里(同一拍里先走过去也行)
            line += f"（{f.entity}现{_where(world, f.entity)}）"
        elif f.kind in ("unnamed", "conjure"):
            near = [i for i in effects.things(world, situation.near(world)) if not g.get(i, "hidden") and effects.usable(world, i)]
            shop = trade.shop(world)
            ware = trade.ware_of(world, shop, f.entity) if shop and f.kind == "conjure" else None
            if shop and f.kind == "conjure" and (ware or (venue.wares(world, shop) and SERVED.search(f.entity))):  # 店里的货：要买下才到得了桌上
                shelf = "、".join(k[2:] for k in venue.wares(world, shop))
                line += f"（此地与身边可及之物：{'、'.join(near) or '无'}）——这是铺子里的货(货架上有{shelf})：主角要它就写 买下(吃喝也可写 打尖)，钱照价目付；不买就别写端上来"
            else:
                line += f"（此地与身边可及之物：{'、'.join(near) or '无'}）"
        elif f.kind == "absent":
            line += f"（{f.entity}现在{g.get(f.entity, 'location')}；要他来，写 赶来，系统按路程裁定赶不赶得到）"
            if f.entity in situation.sightable(world):  # v12：他在望得见的地方
                line += "；只是远远望见就写 望见；主角走到别处才望见的，望见写在走到之后"
        elif f.kind == "afar":
            line += "（远远望见的人说什么主角听不到：删去他的台词，或写他赶来、主角走过去）"
        elif f.kind == "move":  # 体检只陈述事实，怎么改是给导演的话：不随作废缘由流到编剧那里
            line += "（主角真要去留就写 前往；没走成就改写成正要前往或止步）"
        lines.append(line)
    return lines


def forged(world, noun: str) -> bool:
    """拍文或正文里拿出、递上的这件东西此地没有(v8 场景清单)：够得着的器物与景物(此地与近旁、身边之人手里、主角身上，连同回合开始时的那几处与那几人)
    没有哪件的名字含着它(或它的后两个字)、也不被它所含，描述里也没说到它——「密图」「火折」「金创药」是凭空造的，「长剑」「那叠纸」(玉壁剑影图「一叠发黄的纸」)不是。
    v9 收紧：单字的名词须是器物名字的末字(「信」不是「内堂信笺」，是一封书信)；远处的东西拿不到眼前来；银两不是器物，有没有由银两账裁定(lexicon 另查得失)。"""
    if lexicon.COIN.search(noun):
        return False
    g, start = world.graph, (getattr(world, "turn", None) or {}).get("start") or {}
    spots = situation.near(world) | situation.near(world, start.get("here") or world.here) | set(start.get("route") or ())
    people = situation.around(world) | set(start.get("around") or ()) | {"player"}
    head = noun[-2:]
    reach = []
    for n, node in g.nodes.items():
        if node["type"] not in ("item", "feature") or not effects.usable(world, n):
            continue
        holder = node.get("holder")
        if not (holder in people or (holder is None and effects.place(world, n) in spots)):
            continue
        reach.append(n)
        if n.endswith(noun) or (len(noun) > 1 and (noun in n or n in noun or head in n)):
            return False
        desc = node.get("desc") or ""
        if (noun in desc) if len(noun) > 1 else re.search(re.escape(noun) + r"(?=[，。；！？、]|$)", desc):  # 「一叠发黄的纸，」说的是纸；「信笺」不是信
            return False
    if len(noun) == 2 and noun[0] in lexicon.GENERIC and noun[-1] in lexicon.KINDS:  # v13 「灵草」「宝剑」这样的泛称：手边同类的只有一件，说的就是它（第 8 回的「灵草」就是手里的通天草）；「断肠草」「密图」「金创药」这样有名有姓的不算
        return len([n for n in reach if g.kind(n) == "item" and n.endswith(noun[-1])]) != 1
    return True


def _thing(world, op) -> str | None:
    """一条指令要动的器物(取到手、交出去、研习)：没有就是 None。"""
    if not isinstance(op, dict):
        return None
    if acts.is_act(op):
        x = acts.normalize(world, op).get("物")
        return x if isinstance(x, str) and world.graph.kind(x) == "item" else None
    for x in (op.get("id"), op.get("value")):
        x = effects.resolve(world, x) if isinstance(x, str) else None
        if x and world.graph.kind(x) == "item":
            return x
    return None


def _where(world, item: str) -> str:
    g, holder = world.graph, world.graph.get(item, "holder")
    if holder == "player":
        return "在你身上"
    if holder:
        return f"由{holder}随身，{holder}在{g.get(holder, 'location')}"
    return f"在{g.get(item, 'location')}" + ("，藏而未露" if g.get(item, "hidden") else "")
