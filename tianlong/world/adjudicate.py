"""
[INPUT]: 依赖 world/effects 的 apply / describe / resolve（逐条落账）、world/lexicon 的 scan / table / find / secret_hits（拍文与账本的一致性体检）、
         world/situation 的 around / spawn / join / free / rout / captive（情境层与连带），World 门面（graph / player / knowledge / here / turn / aliases）
[OUTPUT]: 对外提供 judge()（逐拍裁决导演的提议 → Ruling）、Ruling、doomed()（仍不成立须整拍作废的拍）、brief()（把硬违例译成给导演的修复清单）、names()（实体名表）、targets()（举动所指的实体）、HARD
[POS]: world 层的裁决器——「LLM 提议，世界裁决」的执行者。effects 只看一条指令成不成立；裁决器看拍与拍、拍与文字、拍与玩家之间：
       每一拍的后果挂在这一拍上，先授意（主角的拍里取物、杀人、吸功须是玩家所指——越俎代庖的拍不演，降为下回合的候选选项），
       再落账，再以词表体检「写了变化却没有指令」的影子状态；随行、获救、败走这三种写漏了的连带由系统追认，其余硬违例交导演修复一次，
       仍不成立的拍整拍作废，化作一句失败的事实交编剧。纯规则、零 LLM 调用；同一份提议在同一世界上裁决两次结果相同（引擎据此先在副本上试演）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
from dataclasses import dataclass, field

from . import effects, lexicon, situation

HARD = {"void", "acquire", "unnamed", "give", "absent", "kill", "drain", "bind", "spawn", "secret", "interrupt"}
RATIFY = {"follow", "free", "leave"}  # 写漏了也无妨的连带：系统照拍文追认，不劳导演返工


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
    return {t for t in out if isinstance(t, str) and world.graph.has(t)}


# ============================================================
#  授意：主角的拍里，取走他人或此地之物、毁物、杀人、吸功，对象须在玩家所指之内
# ============================================================
def _unbidden(world, ops: list, allowed: set[str]) -> list[str]:
    g, out = world.graph, []

    def ok(item):
        return item in allowed or g.get(item, "holder") in allowed or item in world.player["inventory"]

    for op in ops:
        if not isinstance(op, dict):
            continue
        kind, key = op.get("op"), op.get("key")
        nid, value = effects.resolve(world, op.get("id")), effects.resolve(world, op.get("value"))
        if kind == "push" and nid == "player" and key in ("inventory", "随身", "物品") and g.kind(value) == "item" and not ok(value):
            out.append(f"取走{value}")
        elif kind == "set" and key == "holder" and value == "player" and g.kind(nid) == "item" and not ok(nid):
            out.append(f"取走{nid}")
        elif kind == "set" and key == "status" and value == "dead" and g.kind(nid) == "person" and nid not in allowed:
            out.append(f"杀了{nid}")
        elif kind == "drain" and g.kind(value) == "person" and value not in allowed:
            out.append(f"吸取{value}的内力")
        elif kind == "set" and key == "state" and g.kind(nid) == "item" and isinstance(value, dict) \
                and value.get("exists") is False and nid not in allowed:
            out.append(f"毁去{nid}")
    return out


# ============================================================
#  裁决
# ============================================================
def _secrets(world) -> list[tuple[str, str, str]]:
    return [(e["src"], e["rel"], e["dst"]) for e in world.graph.edges
            if e.get("secret") and not world.knowledge.knows_secret(e)]


def judge(world, plan: dict, allowed: set[str], *, embargo=frozenset(), cast=frozenset(),
          no_interrupt: bool = False, drop: dict | None = None) -> Ruling:
    """逐拍裁决并落账到 world。allowed：玩家所指；embargo：原著近事里尚未到场的势力；cast：此地原著的相关者（可作打断的来源）；
    drop：上一轮裁决仍不成立、此番整拍作废的拍号 → 缘由（0 号指 spawn 与本幕之问）。"""
    drop = drop or {}
    g, r = world.graph, Ruling(question=dict(plan.get("question") or {}))
    here0, inv0, around0 = world.here, set(world.player["inventory"]), situation.around(world)
    power0 = {p: g.get(p, "power") for p in around0}
    for spec in copy.deepcopy(plan.get("spawn") or []):
        nid, why = situation.spawn(world, spec, set(embargo))
        if nid:
            r.spawned.append(nid)
        elif 0 not in drop:
            r.hard.append(lexicon.Finding("spawn", 0, str(spec.get("name")), f"场景实体「{spec.get('name')}」不成立：{why}"))
    shown = []
    for i, beat in enumerate(plan["beats"], 1):
        if i in drop:
            r.void.append(f"{beat['text'] or '这一拍的后果'}——未曾发生：{'；'.join(drop[i])}")
            shown.append({**beat, "text": ""})
            continue
        if beat.get("who") == "player":
            over = _unbidden(world, beat.get("ops") or [], allowed)
            if over:  # 系统不替玩家做主：这一拍不演，越权之举留作下回合的选项
                r.candidates += over
                r.soft.append(lexicon.Finding("agency", i, "、".join(over), f"第{i}拍替主角{'、'.join(over)}，玩家并未授意"))
                shown.append({**beat, "text": ""})
                continue
        applied, rejected = effects.apply(world, copy.deepcopy(beat.get("ops") or []), "director")  # 落账会就地规整指令：提议本身留给返工与定稿
        r.applied += applied
        for op, why in rejected:
            line = f"{effects.describe(op)}——{why}"
            r.void.append(line)
            soft = effects._moves_player(world, op)  # 远行止步关前：前半程成立，交编剧写明，不必返工
            (r.soft if soft else r.hard).append(lexicon.Finding("void", i, effects.describe(op), f"第{i}拍：{line}", hard=not soft))
        r.beats.append({k: beat.get(k) for k in ("who", "to", "text")})
        shown.append(beat)
        if beat.get("to") == "player" and beat.get("who") not in (None, "player"):
            r.addressed.append(beat["who"])
    _examine(world, r, shown, here0, inv0, around0, power0)
    _question(world, r, cast, no_interrupt and 0 not in drop)
    r.notes = list(world.turn.get("notes", []))
    return r


def _examine(world, r: Ruling, shown, here0, inv0, around0, power0):
    """落账之后体检拍文：写了变化却没有指令即为违例；随行、获救、败走照拍文追认，其余交导演。"""
    g, tab_kinds = world.graph, names(world)
    view = lexicon.View(here_start=around0, here_end=situation.around(world), arrived=set(world.turn.get("arrived", ())),
                        inventory_start=inv0, inventory_end=set(world.player["inventory"]),
                        dead={p for p in g.where(type="person") if g.get(p, "status") == "dead"},
                        drained={p for p, v in power0.items() if (g.get(p, "power") or 0) < (v or 0)},
                        captive=situation.captive(world), moved=world.here != here0)
    found = lexicon.scan(shown, view, *tab_kinds)
    secrets = _secrets(world)
    for i, beat in enumerate(shown, 1):
        for src, rel, dst in lexicon.secret_hits(beat.get("text") or "", secrets, tab_kinds[0]):
            found.append(lexicon.Finding("secret", i, f"{src}—{rel}—{dst}",
                                         f"第{i}拍说破了未揭的隐情（{src}与{dst}）：要揭开就写 reveal，否则只可伏笔"))
    for f in found:
        if f.kind in RATIFY and _ratify(world, f):
            r.soft.append(f)
        elif f.kind in HARD and f.hard:
            r.hard.append(f)
        else:
            r.soft.append(f)


def _ratify(world, f) -> bool:
    """照拍文追认连带：某人随你同行、某人获救、某人败走。追认不了（如败走无处可去）的仍算违例。"""
    g, pid, notes = world.graph, f.entity, world.turn.setdefault("notes", [])
    if f.kind == "follow":
        notes += situation.join(world, pid)
        g.set(pid, "location", world.here)
        notes.append(f"{pid}随你同行")
        return True
    if f.kind == "free":
        who = situation.free(world, pid)
        notes.append(f"{pid}脱离了{'、'.join(who)}的拘押")
        return True
    if f.kind == "leave":
        to = situation.rout(world, pid)
        if to:
            notes.append(f"{pid}离去")
        return bool(to)
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
    """返工之后仍不成立、须整拍作废的拍号 → 缘由。单条指令被驳回不算：那一条本就没落账，拍里其余的事照常成立。"""
    out: dict[int, list[str]] = {}
    for f in ruling.hard:
        if f.kind != "void":
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
        lines.append(line)
    return lines


def _where(world, item: str) -> str:
    g, holder = world.graph, world.graph.get(item, "holder")
    if holder == "player":
        return "在你身上"
    if holder:
        return f"由{holder}随身，{holder}在{g.get(holder, 'location')}"
    return f"在{g.get(item, 'location')}" + ("，藏而未露" if g.get(item, "hidden") else "")
