"""
[INPUT]: 依赖 world/access 的 steps（近处子地点的短名）、world/bond 的 before / derive（恩怨事件）、world/actor 的 feel（心境）、world/growth 的 studiable / arts_of / mastery / unearned（研习对象与进境账），
         world/effects 的 apply / describe / resolve（逐条落账）、world/lexicon 的 scan / table / find / secret_hits（拍文与账本的一致性体检）、
         world/situation 的 around / spawn / follow / join / free / rout / captive（情境层与连带）、world/perspective 的 audit（识名体检），
         world/effects 的 unearth（场景物件认回现场的原著器物），World 门面（graph / player / knowledge / here / turn / aliases）
[OUTPUT]: 对外提供 judge()（逐拍裁决导演的提议 → Ruling）、imply()（追认一回研习：玩家所指的秘籍在拍里被习练而导演漏写 study）、Ruling、doomed()（仍不成立须整拍作废的拍）、brief()（把硬违例译成给导演的修复清单：体检只陈述事实，怎么改(写 arrive、写 set player location)只写在这里，不随作废缘由流到编剧）、
          afterword()（编剧成文之后再对一次账：正文写了账上没有的得失去留生死擒放 → 偏差交下回合导演）、names()（实体名表，含近处子地点的短名）、targets()（举动所指的实体）、physical()（改变物理状态的指令，节奏账据此判局面动没动）、HARD / RATIFY / UNSURE、WOUND / PARRY / HEAL / SCRATCH
[POS]: world 层的裁决器——「LLM 提议，世界裁决」的执行者。effects 只看一条指令成不成立；裁决器看拍与拍、拍与文字、拍与玩家之间：
       每一拍的后果挂在这一拍上，先授意（主角做的事——主角的拍、或写「你」而非别人给你的旁白——里取物、杀人、吸功、研习须是玩家所指：
       v5 只剥掉越权的那几条，这一拍其余照演(玩家要走就照走)，拍文后注明哪件事未曾发生、【未能成立】里明告编剧，越权之举降为下回合的候选选项；拍里只有越权之事则整拍不演），
       再落账，再以词表体检「写了变化却没有指令」的影子状态；随行、获救、败走这三种写漏了的连带由系统追认，其余硬违例交导演修复一次，
       仍不成立的拍整拍作废，化作一句失败的事实交编剧。
       一拍一事务(v3)：拍里改变物理状态的指令(去留、得失、生死、随行与拘押、赶来、研习、吸功、揭示)落不了，整拍即交返工；
       指令在拍文里无据即丢(无伤扣血、被荡开的一击、研习之拍扣主角气血)，主角自己的拍里无人出手又不涉险地，一拍至多伤 SCRATCH 点；
       台词的事实出处：尚未发生的原著(某人将被擒、将死)不得从任何人嘴里当作已知(foretold，返工不作废)；拍上的 mood 原样带给编剧、不入账；
       词表不再替导演挪人：只追认获救(解押)，随行、离去、叫错名字交返工但不作废；
       名册由事件写入(v5)：同在这一片的人被导演写进拍里(开口、下指令)即走到了主角跟前(_drawn)；
       事件先于状态(v4)：每拍落账之后 bond.derive 从已成立的指令推出恩怨事件、actor.feel 把拍上的情绪挂在此人脸上；研习是主角的举动，玩家没指着的秘籍导演不替他练(降为候选)；
       主角的去留有账可依(v5)：拍文写「你走进X」「你离开X」而账上没到、没走即 move 违例(台词里的去处、导演写了要去而止步关前的不算)；
       进境有账可依：主角的拍里写了账上没有的那一阶(「身如游龙」而未入门、「大成」而只初窥)即 mastery 违例，交返工不作废；同伴诸拍落定后才沿主角的路随行，擒者与人质须同处一地。纯规则、零 LLM 调用；同一份提议在同一世界上裁决两次结果相同（引擎据此先在副本上试演）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import re
from dataclasses import dataclass, field

from . import access, actor, bond, effects, growth, lexicon, perspective, situation
from .graph import holds

HARD = {"foretold", "void", "acquire", "unnamed", "give", "absent", "kill", "drain", "bind", "spawn", "secret", "interrupt",
        "follow", "leave", "custody", "name", "mastery", "move"}
RATIFY = {"free"}                 # 追认只解除拘押边（获救），从不挪动任何人：正则看错了，代价只是一条关系
UNSURE = {"follow", "leave", "name", "foretold", "mastery"}  # 词表推断的去留、叫错的名字：交导演返工一次，仍不成立也不作废整拍——名字由 perspective.mask 兜底换掉


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
    question: dict = field(default_factory=dict)          # 本幕之问 {ask, state, by}
    spawned: list[str] = field(default_factory=list)


# ============================================================
#  实体名表：原著实体 + 别名 + 本回合的场景实体
# ============================================================
def names(world) -> tuple[list, dict]:
    g = world.graph
    surface = {n: n for n, node in g.nodes.items() if node["type"] in ("person", "item", "group", "location", "skill")}
    surface.update({a: n for a, n in world.aliases.items() if n in surface})
    surface.update({n.replace("·", ""): n for n in list(surface.values()) if "·" in n})
    local = situation.near(world) | set(access.steps(world, world.here))  # 近处的子地点叫短名：「石级隧道」即琅嬛福地·石级隧道
    surface.update({loc.split("·", 1)[1]: loc for loc in sorted(local) if "·" in loc and loc.split("·", 1)[1] not in surface})
    surface.update({perspective.handle(world, p): p for p in situation.around(world)
                    if not perspective.knows(world, "player", p)})  # 主角眼中的叫法：「大眼圆脸的少女」即钟灵
    kinds = {n: ("thing" if g.get(n, "ephemeral") and node["type"] == "item" else node["type"])
             for n, node in g.nodes.items() if n in surface.values()}
    return lexicon.table(surface), kinds


def targets(world, deed: str, given=()) -> set[str]:
    """玩家举动所指的实体：选项自带的对象，加上原话里认得出的名字（含主角对器物的近似叫法）。"""
    tab, _ = names(world)
    out = {effects.resolve(world, t) for t in given if t} | {n for n, _, _ in lexicon.find(deed, tab)}
    for word in filter(None, [lexicon.itemish(deed)]):
        hit = effects.resolve(world, word)
        if world.graph.kind(hit) == "item":
            out.add(hit)
    if lexicon.PRACTICE.search(deed or "") and not any(world.graph.get(t, "grants") or world.graph.kind(t) == "skill" for t in out):
        out |= {s for s in growth.studiable(world) if world.graph.kind(s) == "item"}  # 「练功」而不说练哪部：手边的秘籍都算所指
    return {t for t in out if isinstance(t, str) and world.graph.has(t)}


# ============================================================
#  授意：主角做的事(主角的拍、或写「你」的旁白)里，取走他人或此地之物、毁物、杀人、吸功、研习，对象须在玩家所指之内
# ============================================================
TO_YOU = re.compile(r"(?:给|与|到|进|入)你|(?:向|朝)你(?:抛|掷|扔|递)")  # 你是收受的一方：东西是别人给的


def _by_player(beat: dict) -> bool:
    """这一拍是不是主角在做事：主角的拍；或没有署名、写着「你」、又不是别人递给你的旁白(「你顺手拾起烛台」)。
    别人给主角东西(钟灵把解药塞给你、塞进你怀里)是他的举动，不归授意管。"""
    who, text = beat.get("who"), beat.get("text") or ""
    return who == "player" or (who is None and "你" in text and not TO_YOU.search(text))


def _unbidden(world, ops: list, allowed: set[str]) -> list[tuple[dict, str, str]]:
    """越权之举：(那条指令, 一句人话, 所涉实体)。"""
    g, out = world.graph, []
    allowed = allowed | {effects.resolve(world, a) for a in allowed}  # 玩家所指的叫法(蒲团里的帛卷)落回实体

    def ok(item):
        return item in allowed or g.get(item, "holder") in allowed or item in world.player["inventory"]
    taught = {k for p in allowed if g.kind(p) == "person" for k in g.get(p, "skills") or []}  # 指着某人，即可向他求教
    arts = {k for x in allowed if g.kind(x) in ("item", "skill") for k in growth.arts_of(g, x)}  # 指着秘籍，即指着它所载的武学

    for op in ops:
        if not isinstance(op, dict):
            continue
        kind, key = op.get("op"), op.get("key")
        nid, value = effects.resolve(world, op.get("id")), effects.resolve(world, op.get("value"))
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
    return out


# ============================================================
#  裁决
# ============================================================
DEATH = re.compile(f"{lexicon.KILL.pattern}|{lexicon.DIE.pattern}|死了|已死|遇害")


def _foretold(world, shown, tab) -> list:
    """台词的事实出处：尚未发生的原著(某人将被擒、将死)不得从任何人嘴里当作已知说出——那是后台的原著近事，不是此刻的江湖。
    原著已演、或剧情里已成事实的(拘押边已在、人已死)不算。"""
    g, done, out = world.graph, set(world.done), []
    fates = []
    for ev in world.canon:
        if ev["id"] in done:
            continue
        for op in ev["effects"]:
            if op.get("op") == "link" and op.get("rel") in situation.CUSTODY and not holds(g, op["src"], "~" + op["rel"], op["dst"]):
                fates.append((op["src"], op["dst"], lexicon.BIND))
            elif op.get("key") == "status" and op.get("value") == "dead" and g.get(op.get("id"), "status") != "dead":
                fates.append((op["id"], op["id"], DEATH))
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
    for b in beats:
        ops = [op for op in b.get("ops") or [] if isinstance(op, dict)]
        for x in [b.get("who"), b.get("to")] + [op.get(k) for op in ops for k in ("id", "src", "dst")]:
            x = effects.resolve(world, x)
            if x in near and x not in out:
                out.append(x)
    return out


def judge(world, plan: dict, allowed: set[str], *, embargo=frozenset(), cast=frozenset(),
          no_interrupt: bool = False, drop: dict | None = None, then=None) -> Ruling:
    """逐拍裁决并落账到 world。allowed：玩家所指；embargo：原著近事里尚未到场的势力；cast：此地原著的相关者（可作打断的来源）；
    drop：上一轮裁决仍不成立、此番整拍作废的拍号 → 缘由（0 号指 spawn 与本幕之问）；
    then：诸拍落账之后、体检之前要发生的事（此地上演的原著）——导演挪动过的人，原著再挪不动；原著挪走的人，拍文写他离去也不算漏记。
    一拍是一个事务：拍里改变物理状态的指令有一条落不了，整拍交返工、仍不成立即作废；指令在拍文里无据（无伤而扣血），丢掉指令。
    同伴随行等诸拍落定才结算：拍中途解除了随行、被人擒住的，不会被主角先走一步带走。"""
    drop = drop or {}
    g, r = world.graph, Ruling(question=dict(plan.get("question") or {}))
    situation.enlist(world, _drawn(world, plan["beats"]))  # 被导演写进拍里的同片之人：就当他走到了主角跟前
    here0, inv0, around0 = world.here, set(world.player["inventory"]), situation.around(world)
    world.turn["present"] = around0  # 回合开始时身边之人：主角先走一步，他们仍可在后面的拍里跟上
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
    shown, touched, stripped = [], {}, set()
    beats = plan["beats"]
    aimed = {effects.resolve(world, op.get("value")) for b in beats for op in b.get("ops") or [] if effects._moves_player(world, op)}
    for i, beat in enumerate(beats, 1):
        if i in drop:
            r.void.append(f"{beat['text'] or '这一拍的后果'}——未曾发生：{'；'.join(drop[i])}")
            shown.append({**beat, "text": ""})
            continue
        raw, aside = beat.get("ops") or [], ""
        over = _unbidden(world, raw, allowed) if _by_player(beat) else []
        if over:  # 系统不替玩家做主：只剥掉越权的那几条，这一拍其余照演；越权之举留作下回合的选项，并明告编剧它没有发生
            acts = [act for _, act, _ in over]
            r.candidates += [a for a in acts if a not in r.candidates]
            r.void += [f"{a}——主角并未起意，未曾发生" for a in acts]
            r.soft.append(lexicon.Finding("agency", i, "、".join(acts), f"第{i}拍替主角{'、'.join(acts)}，玩家并未授意"))
            stripped |= {ent for _, _, ent in over}
            raw = [op for op in raw if all(op is not o for o, _, _ in over)]
            if not raw:  # 这一拍只做了越权之事：整拍不演
                shown.append({**beat, "text": ""})
                continue
            aside = f"（其中{'、'.join(f'「{a}」' for a in acts)}主角并未起意，未曾发生）"
        after = beats[i]["text"] if i < len(beats) and isinstance(beats[i].get("text"), str) else ""
        ops, baseless = _grounded(world, copy.deepcopy(raw), beat.get("text") or "", after, beat.get("who"))
        r.soft += [lexicon.Finding("baseless", i, effects.describe(op), f"第{i}拍：{effects.describe(op)}——拍文里无据，不入账", hard=False)
                   for op in baseless]
        at = world.here
        snap = bond.before(world, ops)
        applied, rejected = effects.apply(world, ops, "director")  # 落账会就地规整指令：提议本身留给返工与定稿
        r.applied += applied
        bond.derive(world, beat.get("who"), applied, snap, beat.get("text") or "", beat.get("to"))  # 事件先于状态：恩怨从做了什么里推出
        actor.feel(world, beat.get("who"), beat.get("mood"))  # 拍上的情绪挂在此人脸上几回合
        for nid in (i2 for op in applied for i2 in effects._ids(op)):
            touched[nid] = i
        for op, why in rejected:
            line = f"{effects.describe(op)}——{why}"
            r.void.append(line)
            partial = effects._moves_player(world, op) and world.here != at  # 远行止步关前：前半程成立，交编剧写明，不必返工
            hard = physical(op) and not partial and bool((beat.get("text") or "").strip())  # 无文字的拍(旧写法的顶层后果)没有拍文可违
            (r.hard if hard else r.soft).append(lexicon.Finding("void", i, effects.describe(op), f"第{i}拍：{line}", hard=hard))
        r.beats.append({**{k: beat.get(k) for k in ("who", "to", "text", "mood")}, "text": (beat.get("text") or "") + aside})
        shown.append(beat)
        if beat.get("to") == "player" and beat.get("who") not in (None, "player"):
            r.addressed.append(beat["who"])
    route = world.turn.pop("route")
    if len(route) > 1:
        for pid in situation.party(world):
            touched.setdefault(pid, touched.get("player", 0))
        effects._note(world, situation.follow(world, route))
    if then:
        then()
    _custody(world, r, touched)
    world.turn["start"] = {"here": here0, "inventory": inv0, "around": around0, "route": route, "aimed": aimed}  # 编剧成文之后的对账也以此为准
    _examine(world, r, shown, here0, inv0, around0, power0, stripped)
    _question(world, r, cast, no_interrupt and 0 not in drop)
    r.notes = list(world.turn.get("notes", []))
    return r


# ============================================================
#  一拍一事务：哪些指令是这一拍的筋骨，落不了整拍便不成立；哪些指令在拍文里无据
# ============================================================
WOUND = re.compile(r"伤|血|痛|跌|摔|撞|刺中|刺入|刺伤|砍中|劈中|击中|打中|拍中|掌中|中掌|中剑|中毒|毒发|擦破|咳|呕|吐出|昏|晕|反噬|岔气|走火|灼|烫|咬|抓破|划破|骨折|断了")
PARRY = re.compile(r"荡开|架开|格开|挡开|拦开|拨开.{0,2}(?:剑|刀|掌|招)|避开|闪开|躲开|让开|落空|扑空|险险避过|堪堪避过|毫发无伤|毫发未伤")
SCRATCH = 5                                      # 非较量场合一拍至多伤几点
HEAL = re.compile(r"药|丹|丸|调息|运功|歇|养|疗|敷|包扎|吐纳|平复|好转|缓过|回复|恢复|止血|顺气|气色")


def physical(op) -> bool:
    """改变物理状态的指令：去留、得失、生死伤病、擒放随行、赶来、研习吸功、揭开暗路与隐情。
    只有恩怨印象(其余关系)、未了之事、地点现状落不了是小事——丢那一条，拍照常成立。"""
    if not isinstance(op, dict):
        return False
    kind, key = op.get("op"), op.get("key")
    if kind in ("link", "unlink"):
        return op.get("rel") == situation.FOLLOW or op.get("rel") in situation.CUSTODY
    if kind in ("arrive", "study", "drain", "reveal"):
        return True
    return key not in ("threads", "未了之事", "state", "note", "epithet", "mood")


def _grounded(world, ops: list, text: str, after: str, who=None) -> tuple[list, list]:
    """反向证据：增减气血须拍文里有伤或疗的字眼；伤人的一击若在本拍或下一拍被荡开避过，那一下便没有伤。
    无据的数值变更直接丢弃——不让导演拿气血当佐料，一回合掉几点血却一字未写。
    研习之拍不扣主角气血(预裁已定顺逆)；主角自己的拍里既无人出手也不涉险地远行，一拍至多伤 SCRATCH 点。"""
    moving = any(effects._moves_player(world, op) for op in ops)
    keep, drop = [], []
    studying = any(isinstance(op, dict) and op.get("op") == "study" for op in ops)
    for op in ops:
        if isinstance(op, dict) and op.get("op") == "add" and op.get("key") in ("hp", "气血") \
                and isinstance(op.get("value"), (int, float)):
            mine = op.get("id") in ("player", "主角", world.player["name"])
            if op["value"] < 0 and (not WOUND.search(text) or PARRY.search(text + after) or (mine and studying)):
                drop.append(op)  # 研习的顺逆由预裁定，岔气的内伤系统已落：导演不另扣血
                continue
            if op["value"] < 0 and mine and who in (None, "player") and not moving:
                op["value"] = max(op["value"], -SCRATCH)  # 无人出手、不涉险地：自己磕碰，一拍至多伤五点
            if op["value"] > 0 and not HEAL.search(text):
                drop.append(op)
                continue
        keep.append(op)
    return keep, drop


def _custody(world, r: Ruling, touched: dict[str, int]):
    """不变量：擒者与人质同处一地。本回合碰过其中一方而两人分处两地，是哪一拍写歪了，就记在哪一拍上。"""
    for e in world.graph.edges:
        if e["rel"] not in situation.CUSTODY:
            continue
        a, b = e["src"], e["dst"]
        beat = max(touched.get(a, 0), touched.get(b, 0))
        pa, pb = effects.place(world, a), effects.place(world, b)
        if beat and pa and pb and pa != pb:
            r.hard.append(lexicon.Finding("custody", beat, b, f"第{beat}拍之后{b}在{pb}、擒住{b}的{a}却在{pa}：擒者走则人质随之；"
                                                             f"要{b}随你走，须先写明救下{b}（unlink 拘押、link 随行）"))


def _view(world, here0, inv0, around0, route, aimed, power0=None) -> lexicon.View:
    """回合起止两个切面：拍文体检与成文之后的对账共用。"""
    g = world.graph
    return lexicon.View(here_start=around0, here_end=situation.around(world), arrived=set(world.turn.get("arrived", ())),
                        inventory_start=inv0, inventory_end=set(world.player["inventory"]),
                        dead={p for p in g.where(type="person") if g.get(p, "status") == "dead"},
                        drained={p for p, v in (power0 or {}).items() if (g.get(p, "power") or 0) < (v or 0)},
                        captive=situation.captive(world), moved=world.here != here0,
                        here=world.here, route=set(route) | {here0, world.here}, aimed=set(aimed))


def _examine(world, r: Ruling, shown, here0, inv0, around0, power0, stripped=frozenset()):
    """落账之后体检拍文：写了变化却没有指令即为违例；随行、获救、败走照拍文追认，其余交导演。
    越权而被剥掉的那几件(取走、杀、吸)已明告编剧未曾发生，拍文里提到它们不再算违例。"""
    tab_kinds = names(world)
    view = _view(world, here0, inv0, around0, world.turn["start"]["route"], world.turn["start"]["aimed"], power0)
    found = [f for f in lexicon.scan(shown, view, *tab_kinds)
             if not (f.kind in ("acquire", "kill", "drain", "give") and f.entity in stripped)]
    found += perspective.audit(world, shown, around0 | view.here_end)  # 听来的名字入认知；叫出不该知道的名字即违例
    secrets = _secrets(world)
    for i, beat in enumerate(shown, 1):
        for src, rel, dst in lexicon.secret_hits(beat.get("text") or "", secrets, tab_kinds[0]):
            found.append(lexicon.Finding("secret", i, f"{src}—{rel}—{dst}",
                                         f"第{i}拍说破了未揭的隐情（{src}与{dst}）：要揭开就写 reveal，否则只可伏笔"))
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


def afterword(world, text: str) -> list[str]:
    """编剧成文之后再对一次账(v5)：正文写了账上没有的得失、去留、生死、擒放(与拍文同一口径，以回合起止两个切面为准)——
    读者已经读到，改不回来，记作偏差，下回合交导演由剧情交代或圆回。须在本回合裁决之后调用(world.turn["start"])。"""
    start = (getattr(world, "turn", None) or {}).get("start")
    if not start or not text:
        return []
    view = _view(world, start["here"], start["inventory"], start["around"], start["route"], start["aimed"])
    found = lexicon.scan([{"who": None, "text": text}], view, *names(world))
    return [f.message.replace("第1拍", "正文") for f in found if f.kind in AFTER]


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
    系统替它补上这条指令(追认，不新造物理：研习本就是玩家所选之事)。返回追认的研习对象，没有即 None。"""
    beats = plan.get("beats") or []
    if any(isinstance(op, dict) and op.get("op") == "study" for b in beats for op in b.get("ops") or []):
        return None
    aim = set(allowed) | {k for p in allowed if world.graph.kind(p) == "person" for k in world.graph.get(p, "skills") or []}
    sources = growth.studiable(world, aim) if aim else []
    if not sources:
        return None
    for b in beats:
        if b.get("who") in (None, "player") and lexicon.PRACTICE.search(b.get("text") or ""):
            b["ops"] = list(b.get("ops") or []) + [{"op": "study", "id": "player", "value": sources[0]}]
            return sources[0]
    return None


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
        if f.kind in ("acquire", "give") and g.kind(f.entity) == "item":
            line += f"（{f.entity}现{_where(world, f.entity)}）"
        elif f.kind == "unnamed":
            near = [i for i in g.where(type="item") if effects.place(world, i) in situation.near(world)
                    and not g.get(i, "hidden") and effects.usable(world, i)]
            line += f"（此地与身边可及之物：{'、'.join(near) or '无'}）"
        elif f.kind == "absent":
            line += f"（{f.entity}现在{g.get(f.entity, 'location')}；要他来，写 arrive，系统按路程裁定赶不赶得到）"
        elif f.kind == "move":  # 体检只陈述事实，怎么改是给导演的话：不随作废缘由流到编剧那里
            line += "（主角真要去留就写 set player location；没走成就改写成正要前往或止步）"
        lines.append(line)
    return lines


def _where(world, item: str) -> str:
    g, holder = world.graph, world.graph.get(item, "holder")
    if holder == "player":
        return "在你身上"
    if holder:
        return f"由{holder}随身，{holder}在{g.get(holder, 'location')}"
    return f"在{g.get(item, 'location')}" + ("，藏而未露" if g.get(item, "hidden") else "")
