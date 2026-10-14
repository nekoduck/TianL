"""
[INPUT]: 依赖 world/lod 的 intact / held / tiers / unbacked / stray / _unmet / _scope（日程、前提与一人一主的判定口径）、world/effects 的 resolve / describe / place / apply / STATUSES / NAME、
         world/access 的 reach（场外人物可走的里程）、world/situation 的 around / near / entangled / CUSTODY / FOLLOW、world/bond 的 structural（名分）、
         world/crowd 的 force / might / is_squad / GROUP / FORCE（武力）、world/growth 的 _skills_of（秘籍所载）、world/ledger 的 famous（名号显赫）、
         world/rag 的 dossier / heard（场外档案与已传到某处的近闻）、world/adjudicate 的 spoilers（剧透）、world/graph 的 ROAD / holds（心愿的 done_when 与原著前提同一口径）
[OUTPUT]: 对外提供 mode()（演绎还是创作）、drive()（剧情推力 0~5）、awaken()（心愿了了、志向所系之人死了：原著线就此变了）、idle()（谁该有下一步）、rewrite() / sequel()（两种任务）、brief()（交创作家的任务书）、
          vet()（规则审：合不合天龙世界的物理与规矩——落地的剧情安排，或退回的缘由；安排可写 drops：这条线一走，自己这几人原著里哪几桩不再发生）、
          render()（交审稿人看的人话）、adopt()（排进日程、登记剧情线、断掉 drops 那几桩原著）、
          postpone()（只差路程的原著延后到赶得到之日）、origin()、lines_of()、DRIVES / CADENCE / MAX_TASKS / MAX_EVENTS / MAX_DAYS / QUIET / TRIES
[POS]: v11 世界底座：任务书另有原著剧情线 canon_lines(27：这一桩在哪条线上、因果动机结局、线上还没演的几桩、情理前提与前提破了大约会怎样)与天龙世界的准则 precepts(24，审稿人用)。
        world 层的场外剧情线(v11)——主角不在的地方，江湖照样在走。场外编剧是两个角色：
       演绎家——原著前置未变，就照原著演：原著事件照日程由系统结算，不调模型(lod.verdict 的 canon)；七日之内照原著要上场的人归原著，创作家不先一步改掉他；
       创作家——原著线变了(他的原著演不成了、被主角拦下、心愿了了或落了空、志向被眼前的剧情改了，记作 adrift)或原著里已没有他的戏，此人往后的路交 LLM：
       照志向与剧情推力(drive：不甘现状者推力强，心愿了了也会生出新的图谋，写得勤；安于现状者少动；无欲无求者不写)创作前所未有的剧情线，
       写成与原著同一格式的衍生事件(derived)排进日程，到期与原著一样按前提结算，写到主角跟前即交近处导演当面演出。原著线可以断，断了不必接回：
       新的剧情线可明说让自己这几人此后的哪几桩原著不再发生(drops——乔峰不去聚贤庄了，聚贤庄那一场大战便不会再有)，交审稿人看断得有没有道理。
       合理才入日程，审两道：本模块是规则审(确定性)——名实(只用世上有的人、地、物、武学)、时空(道路走得通、日子够、同一人不分身、事后的去向一日之内)、
       归属(主角身边与同行之人归近处导演，一日之内与主角有过交集的人等着主角的故事——写他来到主角跟前另当别论；七日之内照原著要上场、前提也都在的人归原著)、
       胜负(武功高低定胜负，以弱胜强须有手段，也不能太悬殊)、武学来路(秘籍在手或师父在侧，功力不凭空涨)、暗藏之物只有知情者(known)找得到、地理不动、
       说法对得上后果且不剧透(在副本上演过之后再查：这桩事自己杀了的人、揭开的隐情不算剧透)；
       志向与性情、天龙世界的准则、精彩与读者心理归审稿人(LLM，见 narrative)。规则审不审原著保不保得住：会因此改变的原著只列给审稿人参考(ripples)，连锁反应要合情合理
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import math
import re

from . import access, adjudicate, bond, crowd, effects, growth, lod, rag, situation
from .graph import ROAD, holds
from .ledger import famous

MAX_TASKS = 3        # 一回交给创作家的任务数(改写与续写合计)
MAX_EVENTS = 3       # 一条剧情安排至多几桩事
MAX_DAYS = 60        # 至多排到几日之后
MAX_DROPS = 5        # 一条剧情线至多让几桩原著不再发生
QUIET = 7            # 七日之内另有安排(原著或场外剧情)的人不续写；七日之内照原著要上场的人归原著
TRIES = 3            # 创作家一份任务至多写几稿(规则审或审稿退回即连同缘由重写一稿)
POSTPONE = 2         # 只差路程的原著至多延后几回
DRIVES = {0: "无欲无求", 1: "安于现状", 2: "守成", 3: "进取", 4: "不甘现状", 5: "野心炽烈"}
CADENCE = {5: 3, 4: 5, 3: 8, 2: 15, 1: 30}  # 剧情推力 → 隔几日再写此人的下一步；推力为零的人不写
KILL, HARM = 1.0, 0.6  # 杀人、废人武功须出手一方之力不逊于对方；伤人、擒人、夺物须有对方六成
TRICKS = 0.25        # 用毒、设伏、偷袭、以众凌寡：以弱胜强的余地——也不能太悬殊
TRICK = re.compile(r"毒|暗算|偷袭|设伏|埋伏|伏击|陷阱|迷药|迷香|蒙汗|围攻|以众|夜袭|智取|计")
SELF = re.compile(r"自尽|自刎|病|意外|走火|失足|坠崖|自残|忧愤|老死")
HIGH = re.compile(r"野心|复国|称霸|不甘|报仇|复仇|雪耻|夺|谋|争|狠|毒|恶|阴|权|吞并")
LOW = re.compile(r"隐居|无争|淡泊|安分|老实|温顺|忠厚|看破|出家|修行|慈悲")
KINDS = {"set", "add", "push", "pull", "link", "unlink", "reveal"}
PERSON = {"location", "status", "hp", "power", "skills", "conditions", "intent", "mood", "agenda", "title", "faction"}


def origin(ev: dict) -> str:
    """结算来源：衍生事件是场外编剧写的(说法要对账)，原著是数据。"""
    return "derived" if ev.get("derived") else "canon"


def _pending(world, derived=None) -> list[dict]:
    done = set(world.done)
    return [e for e in world.canon if e["id"] not in done and (derived is None or bool(e.get("derived")) == derived)]


def _event(world, eid: str) -> dict:
    return next(e for e in world.canon if e["id"] == eid)


# ============================================================
#  演绎还是创作；剧情推力
# ============================================================
def mode(world, pid: str) -> str:
    """演绎：原著前置未变，此人照原著演。创作：他的原著线变了(adrift——原著演不成了、被主角拦下、志向被眼前的剧情改了、心愿了了或落了空)，
    或原著里已没有他的戏——往后的路交创作家。"""
    if world.graph.get(pid, "adrift"):
        return "创作"
    return "演绎" if any(pid in e["actors"] for e in _pending(world, derived=False)) else "创作"


def _moot(world, pid: str) -> bool:
    """志向所系之人在这一局里死了(died：开局之前就已死去的不算——白世镜要掩盖的杀马大元之事，马大元本就死了)：这桩心愿便了了，或者落了空。"""
    g, text = world.graph, world.graph.get(pid, "agenda") or ""
    return bool(text) and any(p != pid and p in text and g.get(p, "status") == "dead" and g.get(p, "died") is not None
                              for p in g.where(type="person"))


def _holds(g, cond) -> bool:
    return isinstance(cond, list) and bool(cond) and all(isinstance(c, list) and len(c) == 3 and holds(g, *c) for c in cond)


def awaken(world) -> list[str]:
    """心愿了了(数据里的 done_when 成立)、或志向所系之人在这一局里死了：此人的原著线就此变了(adrift)，往后的路交创作家。
    一桩心愿只醒一次(心愿记下了结之日，死讯以 woke 为界)；引擎每回合收尾时调一次。"""
    g, today, out = world.graph, world.clock.day, []
    died = {p: g.get(p, "died") for p in g.where(type="person") if g.get(p, "status") == "dead" and g.get(p, "died") is not None}
    for p in g.where(type="person"):
        node = g.nodes[p]
        if node.get("status") == "dead" or node.get("dormant"):
            continue
        hit = False
        for w in node.get("wishes") or []:
            if isinstance(w, dict) and not w.get("done") and _holds(g, w.get("done_when")):
                w["done"], hit = today, True
        text = node.get("agenda") or ""
        hit |= any(q != p and q in text and d > node.get("woke", -1) for q, d in died.items())
        if hit:
            node["adrift"], node["woke"] = True, today
            out.append(p)
    return out


def drive(world, pid: str) -> int:
    """剧情推力(0~5)：抽取的数据写了就照数据；没写按性情与图谋估——有所图谋、不甘现状、野心与仇怨在身、名号显赫的推力强，隐退淡泊之人推力弱。"""
    g = world.graph
    v = g.get(pid, "drive")
    if isinstance(v, int) and not isinstance(v, bool):
        return max(0, min(5, v))
    text = f"{g.get(pid, 'persona') or ''}{g.get(pid, 'agenda') or ''}"
    n = 2 + bool(g.get(pid, "agenda")) + bool(HIGH.search(text)) - bool(LOW.search(text)) + famous(g.nodes[pid])
    return max(0, min(5, n))


def idle(world, limit: int = MAX_TASKS) -> list[str]:
    """该有下一步的人，交创作家续写：创作之中(原著线变了或原著已尽)、活着、在江湖上(未休眠、未隐匿)、不在主角的故事里、
    七日之内没有别的安排，且离上回写他已隔够了推力定的日子。原著线变了的人都写；没变的只写推力强的(不甘现状以上)，或近处推力不弱的。
    原著线变了的先写，其次推力强的，再次近处的。"""
    g, today = world.graph, world.clock.day
    busy = situation.around(world) | situation.entangled(world) | lod.held(world)
    soon = {a for e in _pending(world) if e["day"] <= today + QUIET for a in e["actors"]}
    ring = {loc for loc, t in lod.tiers(world).items() if t <= 1}
    pool = []
    for p in g.where(type="person"):
        node = g.nodes[p]
        if node.get("status") == "dead" or node.get("dormant") or node.get("hidden") or p in busy or p in soon:
            continue
        d = drive(world, p)
        if not d or today - world.plotted.get(p, -999) < CADENCE[d] or mode(world, p) != "创作":
            continue
        changed, near = bool(node.get("adrift")), node.get("location") in ring
        if changed or d >= 4 or (d >= 3 and near):
            pool.append((not changed, -d, not near, -(node.get("power") or 0), p))
    return [p for *_, p in sorted(pool)[:limit]]


# ============================================================
#  任务与任务书
# ============================================================
def rewrite(world, ev: dict, reasons) -> dict:
    """原著演不成了的那一桩(前提破了，已作罢、相关者记作原著线已变)：交创作家按原著的逻辑或接近原著的手法写这几人接下来怎样。"""
    return {"kind": "改写", "key": f"改写·{ev['id']}", "event": ev["id"], "reasons": list(reasons)[:4]}


def sequel(world, pid: str) -> dict:
    """创作之中的人：照他的志向与推力写他的下一步。"""
    return {"kind": "续写", "key": f"续写·{pid}", "who": pid}


def brief(world, task: dict) -> dict:
    """交创作家的任务书：都是真相(远处的编剧是后台)，但只给这件事用得着的人、地、物——抽象层，不给茶碗桌椅。"""
    g = world.graph
    if task["kind"] == "改写":
        ev = _event(world, task["event"])
        people = [a for a in ev["actors"] if g.get(a, "status") != "dead" and g.kind(a) == "person"]
        head = {"event": {"id": ev["id"], "where": ev["where"], "when": world.clock.label(ev["day"]), "summary": ev["summary"],
                          "outcome": [effects.describe(op) for op in ev["effects"] if op.get("key") != "location"]},
                "reasons": task["reasons"]}
        home = ev["where"]
    else:
        pid = task["who"]
        home = g.get(pid, "location")
        mates = [p for p in g.where(type="person", location=home) if p != pid and g.get(p, "status") != "dead" and not g.get(p, "dormant")]
        people, head = [pid] + mates[:3], {"who": pid}
    roads = access.reach(world, home) if home else {}
    others = _others(world, people)
    places = sorted((d, x) for x, d in roads.items() if x != home and d <= 5)[:12]
    places += sorted({(roads[g.get(o, "location")], g.get(o, "location")) for o in others
                      if g.get(o, "location") in roads and roads[g.get(o, "location")] > 5})
    things = [i for i in g.where(type="item") if g.get(i, "holder") in people or (g.get(i, "location") == home and not g.get(i, "hidden"))]
    cards = [_card(world, p) for p in people]
    for c in cards:  # 各人到这里要几日：赶不到的人别写进今天的事
        c["far"] = access.reach(world, c["location"]).get(home) if c.get("location") and home else None
    return {"key": task["key"], "kind": task["kind"], **head, "today": world.clock.label(), "home": home,
            "people": cards,
            "others": [_brief_card(world, o, roads) for o in others],
            "places": [f"{x}（{d}日）" for d, x in places],
            "things": [f"{i}（{g.get(i, 'kind') or '杂物'}，{'在' + g.get(i, 'holder') + '手里' if g.get(i, 'holder') else '在' + str(g.get(i, 'location'))}）"
                       for i in things[:10]],
            "lines": lines_of(world, people),
            "canon_lines": canon_lines(world, task.get("event"), people),  # 原著剧情线(v11 27)：按原著的逻辑改写要靠它
            "precepts": precepts(world),                                   # 天龙世界的准则(v11 24)：审稿人据此判合不合理
            "heard": rag.heard(world, sorted({g.get(p, "location") for p in people} - {None}))}


def _others(world, people) -> list[str]:
    """这几人的恩怨所系之人(关系两端、图谋里点着名的)：心愿往往落在他们身上，创作家要知道他们此刻在哪、是死是活。"""
    g, out = world.graph, []
    for p in people:
        text = f"{g.get(p, 'agenda') or ''}{g.get(p, 'goal') or ''}"
        tied = [e["dst"] if e["src"] == p else e["src"] for e in g.edges
                if p in (e["src"], e["dst"]) and e["rel"] != ROAD and "player" not in (e["src"], e["dst"])]
        tied += [q for q in g.where(type="person") if q != p and q in text]
        out += [q for q in tied if g.kind(q) == "person" and q not in people and q not in out]
    return out[:6]


def _brief_card(world, p: str, roads: dict) -> str:
    g = world.graph
    loc = g.get(p, "location")
    far = roads.get(loc)
    return (f"{p}｜{'已死' if g.get(p, 'status') == 'dead' else effects.STATUS_WORDS.get(g.get(p, 'status'), '')}"
            f"｜身在{loc}" + (f"（{far}日）" if far is not None else "（无路可通）") +
            f"｜{g.get(p, 'faction') or '无门派'}｜功力{g.get(p, 'power') or 0}")


def _card(world, p: str) -> dict:
    """一个人的真相：性情、志向与推力、武功、关系、原著里此后的戏、近来的遭遇(主角做过的事也在里头——心愿也许已经了了)。"""
    g = world.graph
    d = rag.dossier(world, p)
    d.pop("exits", None)
    d.update(power=g.get(p, "power"), skills=list(g.get(p, "skills") or [])[:6], drive=drive(world, p), mode=mode(world, p),
             goal=g.get(p, "goal"), wishes=g.get(p, "wishes"), moot=_moot(world, p),
             means=g.get(p, "means"), limits=g.get(p, "limits"), arc=g.get(p, "arc"),  # 世界底座 22 的补注(v11 草案)：手段、底线、原著走向
             sect=g.get(g.get(p, "faction"), "goal") if g.get(p, "faction") else None,  # 23 的门派所图
             ties=[f"{e['src']}—{e['rel']}—{e['dst']}" for e in g.edges
                   if p in (e["src"], e["dst"]) and e["rel"] != ROAD and "player" not in (e["src"], e["dst"])][:6],
             canon=[f"〔{e['id']}〕{world.clock.label(e['day'])}·{e['where']}：{e['summary']}" for e in _pending(world, derived=False) if p in e["actors"]][:2],
             recent=[f"{world.clock.label(e['day'])}·{e['where']}：{e['summary']}" for e in reversed(world.truth.events) if p in e["summary"]][:3])
    return d


def canon_lines(world, ev_id=None, persons=()) -> list[str]:
    """原著剧情线(v11 27)：这一桩在哪条线上、这几人是哪几条线的主人——因果、动机、原著结局、线上还没演的几桩；
    这一桩自己的情理前提与「前提破了按原著的逻辑大约会怎样」。只是参考，不是规定：原著线可以断。"""
    atlas = getattr(world, "atlas", None) or {}
    lines, notes, done = atlas.get("lines") or {}, atlas.get("notes") or {}, set(world.done)
    picked = [notes[ev_id]["line"]] if ev_id in notes and notes[ev_id].get("line") in lines else []
    picked += [lid for lid, ln in lines.items() if set(ln.get("owners") or []) & set(persons) and lid not in picked]
    out = []
    for lid in picked[:3]:
        ln = lines[lid]
        todo = [e for e in ln.get("events") or [] if e not in done]
        out.append(f"「{ln.get('name')}」因果：{ln.get('spine')}｜动机：{ln.get('motive')}｜原著结局：{ln.get('outcome')}"
                   + (f"｜线上还没演的：{'→'.join(todo[:4])}" if todo else "｜已走完"))
    if ev_id in notes:
        n = notes[ev_id]
        out.append(f"〔{ev_id}〕在线里是「{n.get('role')}」｜靠什么成立：{n.get('needs')}｜前提破了，按原著的逻辑大约会：{n.get('if_broken') or '—'}")
    return out


def precepts(world) -> list[str]:
    """天龙世界的准则(v11 24)：这部书里事情怎样发生的道理，审稿人判一条剧情线合不合理用。"""
    return [f"{p.get('id', '')[2:]}：{p.get('text')}" for p in ((getattr(world, "atlas", None) or {}).get("precepts") or {}).values()]


def lines_of(world, persons) -> list[str]:
    """这几人身上的场外剧情线：已演的与待演的——续写要接得上自己写过的东西。"""
    out, done = [], set(world.done)
    for lid, ln in world.lines.items():
        if not set(ln["owners"]) & set(persons):
            continue
        todo = [e for e in world.canon if e.get("line") == lid and e["id"] not in done]
        out.append(f"「{ln['name']}」{ln['goal']}" + (f"｜待演：{'；'.join(world.clock.label(e['day']) + '·' + e['summary'] for e in todo)}"
                                                    if todo else "｜已演完"))
    return out[-4:]


# ============================================================
#  规则审：合不合天龙世界的物理与规矩
# ============================================================
def _offset(e: dict) -> int:
    try:
        return max(0, min(MAX_DAYS, int(e.get("day") or 0)))
    except (TypeError, ValueError):
        return 0


def _yes(v, default: bool) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() not in {"false", "no", "否", "0", "none", "null", ""} if isinstance(v, str) else bool(v)


def vet(world, task: dict, draft) -> tuple[dict | None, list[str]]:
    """一份剧情安排的规则审：返回 (落地的安排, 退回的缘由)。有一条缘由即整份退回——退回的缘由原样交创作家重写。
    落地的安排另带 ripples：会因此改变的原著(不拦，交审稿人看是不是合情合理的连锁反应)。"""
    if not isinstance(draft, dict):
        return None, ["格式不可解"]
    raw = [e for e in (draft.get("events") if isinstance(draft.get("events"), list) else []) if isinstance(e, dict)]
    if not raw:
        return None, ["没有写事：一条剧情安排至少一桩事"]
    problems = [f"一条剧情安排至多{MAX_EVENTS}桩事"] if len(raw) > MAX_EVENTS else []
    drops, more = _drops(world, draft.get("drops"))
    problems += more
    origin_ev = _event(world, task["event"]) if task["kind"] == "改写" else None
    seen, events = {}, []  # 人 → (此前所在, 那一日)：同一条线里先后几桩按先后算路程
    for e in sorted(raw[:MAX_EVENTS], key=_offset):
        ev, errs = _one(world, task, e, seen, drops)
        problems += errs
        events.append(ev)
    cast = {a for ev in events for a in ev["actors"]} | set(origin_ev["actors"] if origin_ev else ())
    chain = lambda d: origin_ev and _root(_event(world, d)["where"]) == _root(origin_ev["where"]) and _event(world, d)["day"] >= origin_ev["day"]
    problems += [f"「{d}」的相关者不在这条线里：只能让这几人的原著、或改写的那一桩在同一处的后续不再发生"
                 for d in drops if not (set(_event(world, d)["actors"]) & cast or chain(d))]
    if task["kind"] == "续写" and _moot(world, task["who"]) and not any(
            o["op"] == "set" and o.get("key") == "agenda" and o.get("id") == task["who"] for ev in events for o in ev["effects"]):
        problems.append(f"{task['who']}的心愿已了(或落了空)：写明他的新志向(set agenda)")
    ripples = []
    if not problems:
        ripples, stuck = _trial(world, events, drops)
        problems += stuck
    if problems:
        return None, list(dict.fromkeys(problems))[:8]
    name = re.sub(r"[·\s]", "", str(draft.get("line") or ""))[:12] or (task.get("who") or events[0]["actors"][0]) + "的新路"
    return {"line": name, "goal": str(draft.get("goal") or "")[:40], "events": events, "drops": drops, "ripples": ripples}, []


def _root(loc: str) -> str:
    return str(loc).split("·")[0]


def _drops(world, raw) -> tuple[list[str], list[str]]:
    """这条线一走，原著里这几桩便不再发生(drops)：原著线可以断——只能断这几人的(或改写的那一桩在同一处的后续：乔峰不来聚贤庄，聚贤庄那一场大战、
    单氏兄弟战死、游氏兄弟自尽便都不会有)、尚未演的、不在主角跟前(事发之地与相关者都不在)的原著，至多 MAX_DROPS 桩。"""
    out, errs, close = [], [], situation.near(world)
    mine = situation.around(world) | situation.entangled(world)
    pending = {e["id"]: e for e in _pending(world, derived=False)}
    for d in (raw if isinstance(raw, list) else [raw] if isinstance(raw, str) else [])[:MAX_DROPS]:
        d = str(d).strip("〔〕[] ")
        if d not in pending:
            errs.append(f"原著里没有尚未演的「{d}」")
        elif pending[d]["where"] in close or set(pending[d]["actors"]) & mine:
            errs.append(f"「{d}」就在主角跟前、或有人正在主角身边：归近处导演")
        elif d not in out:
            out.append(d)
    return out, errs


def _one(world, task: dict, e: dict, seen: dict, drops=()) -> tuple[dict, list[str]]:
    g, today, errs = world.graph, world.clock.day, []
    if e.get("day") is not None and not str(e.get("day")).strip().isdigit():
        errs.append("day 写几日之后(整数)")
    day = today + _offset(e)
    where = effects.resolve(world, e.get("where"))
    if g.kind(where) != "location":
        errs.append(f"世上没有「{e.get('where')}」这个地方")
        where = None
    actors = []
    for a in e.get("actors") if isinstance(e.get("actors"), list) else []:
        pid = effects.resolve(world, a)
        if pid == "player" or a in ("主角", "你"):
            errs.append("不写主角：主角的事归近处导演")
        elif g.kind(pid) != "person":
            errs.append(f"世上没有「{a}」这个人")
        elif g.get(pid, "status") == "dead":
            errs.append(f"{pid}已死")
        elif g.get(pid, "dormant"):
            errs.append(f"{pid}尚未在江湖上露面")
        elif pid not in actors:
            actors.append(pid)
    if not actors:
        errs.append("这桩事没有写谁(actors)")
    if len(actors) > 8:
        errs.append("一桩事至多八人")
    summary, how = str(e.get("summary") or "").strip(), str(e.get("how") or "").strip()[:40]
    if not summary:
        errs.append("要写 summary：这桩事是什么")
    if where:
        errs += _travel(world, actors, where, day, seen) + _owned(world, task, actors, where, day, drops)
    ops, harms = [], []
    for op in e.get("effects") if isinstance(e.get("effects"), list) else []:
        o, more, harm = _op(world, op, actors, where, how)
        errs += more
        if o:
            ops.append(o)
        if harm:
            harms.append(harm)
    errs += _growth(world, ops, actors, where, day - today)
    for i, (victim, agents, kind) in enumerate(harms):
        others = [a for a in actors if a != victim]
        if not agents and len(others) == 1 and not SELF.search(how):  # 这桩事里只有一个旁人：不写 by，也知道是谁出的手
            harms[i] = (victim, others, kind)
        errs += _fight(world, victim, harms[i][1], kind, how, actors)
    for o in ops:  # 事后的行止：一日之内到得了；再远的路另写一桩事
        if where and o["op"] == "set" and o.get("key") == "location" and g.kind(o["id"]) == "person":
            d = access.reach(world, where).get(o["value"])
            if d is None or d > 1:
                errs.append(f"{o['id']}事后从{where}去{o['value']}{'无路可通' if d is None else f'要{d}日'}：远行另写一桩事")
            else:
                seen[o["id"]] = (o["value"], day)
    place = [{"op": "set", "id": a, "key": "location", "value": where} for a in actors] if where else []  # 与原著同一格式：先把人摆到事发之地
    return {"day": day, "where": where, "weight": 2 if str(e.get("weight")) == "2" else 1, "public": _yes(e.get("public"), True),
            "actors": actors, "requires": [], "effects": place + ops, "summary": summary[:80],
            "motive": str(e.get("motive") or "")[:40], "how": how, "drama": str(e.get("drama") or "")[:40],
            "by": {v: a for v, a, _ in harms if a}}, errs


def _travel(world, actors, where, day, seen) -> list[str]:
    """时空：从此刻所在(或这条线上一桩事之处)到事发之地，道路走得通、日子够；路按场外人物的口径走——不通之路拦所有人，暗路不拦。"""
    g, today, errs = world.graph, world.clock.day, []
    for a in actors:
        start, since = seen.get(a, (g.get(a, "location"), today))
        d = access.reach(world, start).get(where) if start else None
        if d is None:
            errs.append(f"{a}身在{start}，到不了{where}(无路可通)")
        elif d > day - since:
            errs.append(f"{a}身在{start}，到{where}要{d}日，只有{day - since}日")
        seen[a] = (where, day)
        for c in _pending(world, derived=True):  # 另一条场外剧情线上的他：两头都赶得及才行，不分身
            if a in c["actors"]:
                gap = access.reach(world, c["where"]).get(where)
                if gap is None or gap > abs(c["day"] - day):
                    errs.append(f"{a}在{world.clock.label(c['day'])}另有安排（{c['summary']}），两头赶不及")
    return errs


def _owned(world, task, actors, where, day, drops=()) -> list[str]:
    """归属：主角身边与同行之人归近处导演；一日之内与主角有过交集的人等着主角的故事(写他来到主角跟前另当别论：那是交给近处导演当面演出)；
    七日之内照原著要上场、前提也都在的人归原著——原著前置未变就照原著演，创作家不先一步改掉他；这条线明说让那一桩不再发生(drops)的不在此列。"""
    today, close, errs = world.clock.day, situation.near(world), []
    mine, held = situation.around(world) | situation.entangled(world), lod.held(world)
    for a in actors:
        if a in mine:
            errs.append(f"{a}正在主角身边或与主角同行：他的去留归近处导演")
        elif a in held and where not in close:
            errs.append(f"{a}一日之内与主角有过交集，正等着主角的故事")
        for c in _pending(world, derived=False):
            if a in c["actors"] and c["day"] <= today + QUIET and day <= c["day"] and c["id"] != task.get("event") \
                    and c["id"] not in drops and lod.intact(world, c):
                errs.append(f"{a}七日之内照原著要演〔{c['id']}〕{c['summary']}：原著前置未变就照原著演——排在那之后、换人，或写明这条线让它不再发生(drops)")
                break
    return errs


def _op(world, op, actors, where, how) -> tuple[dict | None, list[str], tuple | None]:
    """一条后果的名实与形状；伤、杀、擒、夺、废记下由谁所为，交 _fight 核胜负。"""
    g = world.graph
    if not isinstance(op, dict) or op.get("op") not in KINDS:
        return None, ["后果只写 set/add/push/pull/link/unlink/reveal 几种指令"], None
    r = lambda x: effects.resolve(world, x) if isinstance(x, str) else x
    o = {k: v for k, v in op.items() if k != "by"}
    by = [r(x) for x in (op["by"] if isinstance(op.get("by"), list) else [op.get("by")]) if isinstance(x, str) and x]
    kind = o["op"]
    if kind in ("link", "unlink") or (kind == "reveal" and o.get("key") != effects.NAME):
        src, dst, rel = r(o.get("src")), r(o.get("dst")), o.get("rel")
        o.update(src=src, dst=dst)
        if not (isinstance(rel, str) and rel):
            return None, ["关系要写 rel"], None
        if dst == "player" and kind == "link" and src in actors and not bond.structural(rel) and rel not in situation.CUSTODY:
            return o, [], None  # 听了传闻、念着旧事，对主角起了心思：记进恩怨账
        if "player" in (src, dst):
            return None, ["不写主角：主角的事归近处导演(只可写某人对主角起了什么心思)"], None
        if kind == "reveal":
            if not any(e["src"] == src and e["dst"] == dst and e["rel"] == rel and e.get("secret") for e in g.edges):
                return None, [f"{src}与{dst}之间并无「{rel}」这桩隐情"], None
            return (o, [], None) if {src, dst} & set(actors) else (None, [f"说破{src}与{dst}的隐情，当事人得在这桩事里"], None)
        if not all(g.kind(x) == "person" for x in (src, dst)):
            return None, [f"「{src}」「{dst}」须是世上有的人"], None
        if rel == situation.FOLLOW:
            return None, ["随行是跟着主角走的，场外不写"], None
        if (rel in situation.CUSTODY or bond.structural(rel)) and not {src, dst} <= set(actors):
            return None, [f"「{rel}」须两人都在这桩事里"], None
        if src not in actors and dst not in actors:
            return None, [f"{src}与{dst}都不在这桩事里"], None
        return o, [], ((dst, by or [src], "擒") if kind == "link" and rel in situation.CUSTODY else None)
    if kind == "reveal":
        return None, ["场外不报姓名"], None
    nid, key, v = r(o.get("id")), o.get("key"), o.get("value")
    o["id"] = nid
    if nid == "player" or v == "player":
        return None, ["不写主角"], None
    k = g.kind(nid)
    if k == "person":
        if nid not in actors:
            return None, [f"{nid}不在这桩事里：动谁就把谁写进 actors"], None
        if key not in PERSON:
            return None, [f"{nid}的{key}场外改不得"], None
        if key in ("location", "faction"):
            o["value"] = v = r(v)
            if g.kind(v) != key:
                return None, [f"世上没有「{v}」这个{'地方' if key == 'location' else '门派'}"], None
        if key == "status":
            if v not in effects.STATUSES:
                return None, [f"状态只有 alive/wounded/dead，不是{v}"], None
            return o, [], ((nid, by, "杀" if v == "dead" else "伤") if v != "alive" else None)
        if key in ("hp", "power"):
            if kind != "add" or not isinstance(v, (int, float)) or isinstance(v, bool):
                return None, [f"{key}只写 add 一个数"], None
            return o, [], ((nid, by, "伤" if key == "hp" else "废") if v < 0 else None)
        if key == "skills":
            o["value"] = v = r(v)
            if kind not in ("push", "pull") or g.kind(v) != "skill":
                return None, [f"世上没有「{v}」这门武学"], None
            return o, [], ((nid, by, "废") if kind == "pull" else None)
        return o, [], None
    if k == "item":
        if key not in ("holder", "location", "hidden", "state"):
            return None, [f"{nid}的{key}改不得"], None
        holder = g.get(nid, "holder")
        if holder == "player":
            return None, [f"{nid}在主角手里"], None
        if holder and holder not in actors:
            return None, [f"{nid}在{holder}手里：{holder}得在这桩事里"], None
        if not holder and effects.place(world, nid) != where:
            return None, [f"{nid}不在{where}，也不在这几人手里"], None
        if g.get(nid, "hidden") and not set(g.get(nid, "known") or []) & set(actors):
            return None, [f"{nid}暗藏未现：只有知情者找得到"], None
        if key == "holder":
            o["value"] = to = r(v)
            if to is not None and to not in actors:
                return None, [f"{to}不在这桩事里，接不过{nid}"], None
            return o, [], ((holder, by, "夺") if by and holder in actors and holder != to else None)
        if key == "location" and r(v) != where:
            return None, [f"{nid}只落得在这桩事所在之处"], None
        if key == "hidden" and not _yes(v, True) and not set(g.get(nid, "known") or []) & set(actors):
            return None, [f"{nid}暗藏未现：只有知情者找得到"], None
        return o, [], None
    if k == "location":
        if key == "state" and isinstance(v, str) and where and _root(nid) == _root(where):
            return o, [], None  # 这桩事所在之处(连同同一处所里的各间)的现状
        return None, ["地点只可改这桩事所在之处的现状(一句话)，地理不动"], None
    if k == "faction":
        if key == "state" and isinstance(v, dict) and set(v) == {"leader"} and r(v["leader"]) in actors:
            o["value"] = {"leader": r(v["leader"])}
            return o, [], None
        return None, ["门派只可改由谁执掌(state.leader 写这桩事里的人)"], None
    return None, [f"「{op.get('id')}」改不得：人群随首领走，武学、景物归系统"], None


def _growth(world, ops, actors, where, offset) -> list[str]:
    """武学来路：学会一门武学，须有载它的秘籍在手或在此(暗藏的要知情)、或会它的人在侧(照秘籍自学至少一日)；
    功力增长只能来自传功吸功(对方失去相应功力)或研习秘籍。"""
    g, errs = world.graph, []
    books = [i for i in g.where(type="item") if g.get(i, "holder") in actors or
             (effects.place(world, i) == where and (not g.get(i, "hidden") or set(g.get(i, "known") or []) & set(actors)))]
    for o in ops:
        pid = o.get("id")
        if o["op"] == "push" and o.get("key") == "skills":
            art = o["value"]
            teacher = any(art in (g.get(a, "skills") or []) for a in actors if a != pid)
            book = any(art in growth._skills_of(g, i) for i in books)
            if not (teacher or book):
                errs.append(f"{pid}学{art}无从学起：须有载此武学的秘籍在手或在此，或会它的人在这桩事里")
            elif not teacher and offset < 1:
                errs.append(f"{pid}照秘籍自学{art}，至少要过一日")
        if o["op"] == "add" and o.get("key") == "power" and o["value"] > 0:
            given = sum(-x["value"] for x in ops if x["op"] == "add" and x.get("key") == "power" and x.get("id") != pid and x["value"] < 0)
            cap = max([0.4 * (g.get(i, "grants") or {}).get("power", 0) for i in books], default=0)
            if o["value"] > max(given, cap):
                errs.append(f"{pid}的功力不会凭空涨{o['value']}：须是传功吸功(对方失去相应功力)或研习手边的秘籍")
    return errs


def _side(world, people) -> float:
    """一方之力：这几人的武力，连同他们带着的门人(人群跟着首领、同在一处)。"""
    g = world.graph
    return sum(crowd.force(g.get(a, "power") or 0) for a in people) + \
        sum(crowd.might(world, s) for s in g.where(type=crowd.GROUP) if crowd.is_squad(g, s) and g.get(s, "leader") in people
            and g.get(s, "location") == g.get(g.get(s, "leader"), "location"))


def _fight(world, victim, agents, kind, how, actors) -> list[str]:
    """胜负：武功高低定胜负——出手一方(连同他带来的门人)之力，杀人废人须不逊于对方(连同护着他的门人)，伤人擒人夺物须有对方六成；
    用毒、设伏、偷袭、以众凌寡可以以弱胜强，却也不能太悬殊。自尽、病故、意外不必有人出手。"""
    if not agents:
        return [] if kind in ("杀", "伤", "废") and SELF.search(how) else [f"{victim}被{kind}是谁所为：写明 by"]
    if victim in agents:
        return []
    if not set(agents) <= set(actors):
        return [f"by 里的人须在这桩事里：{'、'.join(a for a in agents if a not in actors)}"]
    mine, theirs, trick = _side(world, agents), _side(world, [victim]), bool(TRICK.search(how))
    if mine < theirs * (KILL if kind in ("杀", "废") else HARM) * (TRICKS if trick else 1):
        gap = round(math.log(theirs / mine, crowd.FORCE))
        return [f"{'、'.join(agents)}武功不及{victim}(约差{gap}点功力)，{kind}不了他" +
                ("：手段也救不了这么悬殊" if trick else "：以弱胜强须有手段(用毒、设伏、偷袭、以众凌寡)写进 how")]
    return []


def _trial(world, events, drops=()) -> tuple[list[str], list[str]]:
    """在世界副本上把这份安排依次演一遍：落不了的后果即退回；演过之后再查说法——对得上后果、不剧透(这桩事自己杀了的人、揭开的隐情不算剧透)；
    前提由此改变了的原著列作 ripples，交审稿人参考(明说不再发生的 drops 另列)。"""
    trial = copy.deepcopy(world)
    trial.turn = {}
    trial.done.extend(drops)
    stuck = []
    for ev in events:
        applied, rejected = effects.apply(trial, copy.deepcopy(ev["effects"]), "derived", lod._scope(ev))
        lod.stray(trial, ev, applied)
        stuck += [f"{effects.describe(op)}落不了：{why}" for op, why in rejected]
        stuck += [f"summary 说了「{x}」，effects 里却没有" for x in lod.unbacked(trial, ev["summary"], applied)]
        revealed = {(op["src"], op["rel"], op["dst"]) for op in applied if op.get("op") == "reveal" and "src" in op}
        stuck += [f"summary {x}：它会传开去" for x in adjudicate.spoilers(trial, ev["summary"], revealed)]
    ripples = [f"{c['summary']}（{world.clock.label(c['day'])}）" for c in _pending(world, derived=False)
               if c["id"] not in drops and lod.intact(world, c) and not lod.intact(trial, c)]
    return ripples[:6], stuck


def render(world, plan: dict) -> list[str]:
    """交审稿人看的人话：一条剧情线、每一桩事(时地人、手段、动机、戏眼、后果)，与会因此改变的原著。"""
    out = [f"剧情线「{plan['line']}」：{plan['goal'] or '（未写目标）'}"]
    for ev in plan["events"]:
        by = ev.get("by") or {}
        facts = [effects.describe(op) + (f"（{'、'.join(by[op['id']])}所为）" if op.get("id") in by and op.get("key") in ("status", "hp", "power", "skills") else "")
                 for op in ev["effects"] if not (op.get("key") == "location" and op.get("value") == ev["where"])]
        out.append(f"{world.clock.label(ev['day'])}·{ev['where']}｜{'、'.join(ev['actors'])}｜{ev['summary']}"
                   f"｜手段：{ev['how'] or '—'}｜动机：{ev['motive'] or '—'}｜戏眼：{ev['drama'] or '—'}"
                   f"｜后果：{'；'.join(facts) or '无可记之变'}")
    if plan.get("drops"):
        out.append("这条线一走，原著里不再发生：" + "；".join(f"{_event(world, d)['summary']}（{world.clock.label(_event(world, d)['day'])}）"
                                                  for d in plan["drops"]))
    if plan["ripples"]:
        out.append("会因此改变的原著：" + "；".join(plan["ripples"]))
    return out


# ============================================================
#  落地：排进日程、登记剧情线；只差路程的原著延后
# ============================================================
def _order(world, day: int, skip=None) -> float:
    """夹在当日最后一桩与次日第一桩之间：日程仍按 order 走，日子仍随 order 单调。"""
    rest = [e for e in world.canon if e is not skip]
    lo = max((e["order"] for e in rest if e["day"] <= day), default=0)
    hi = min((e["order"] for e in rest if e["day"] > day), default=lo + 2)
    return lo + (hi - lo) / 2


def adopt(world, task: dict, plan: dict) -> list[str]:
    """一份过了规则审与审稿的安排排进日程：衍生事件与原著同一格式，记下剧情线(谁的、要走到哪里、已排了哪几桩)；
    改写的那一桩原著由新剧情接手；写过的人原著线的变动已有了下文(不再记作 adrift)，记下日子，按推力隔几日再写。"""
    today, g = world.clock.day, world.graph
    owners = sorted({a for ev in plan["events"] for a in ev["actors"]})
    lid = plan["line"]
    ln = world.lines.get(lid)
    if ln is None or not set(ln["owners"]) & set(owners):
        lid = lid if lid not in world.lines else f"{lid}{len(world.lines) + 1}"
        ln = world.lines.setdefault(lid, {"name": plan["line"], "goal": plan["goal"], "owners": [], "from": task["key"], "made": today, "events": []})
    ln["owners"] = sorted(set(ln["owners"]) | set(owners))
    if plan["goal"]:
        ln["goal"] = plan["goal"]
    if task["kind"] == "改写" and task["event"] not in world.done:
        world.done.append(task["event"])
    for d in plan.get("drops") or []:  # 原著线断在这里：那几桩不再发生，其中别的人原著线也变了
        if d not in world.done:
            lod.settle(world, _event(world, d), {"happens": False}, "canon")
    ids = []
    for ev in plan["events"]:
        eid = f"衍·{lid}·{len(ln['events']) + 1}"
        world.canon.append({**ev, "id": eid, "order": _order(world, ev["day"]), "derived": True, "line": lid, "made": today})
        world.canon.sort(key=lambda e: e["order"])
        ln["events"].append(eid)
        ids.append(eid)
    for a in owners:
        world.plotted[a] = today
        g.nodes[a].pop("adrift", None)
    return ids


def postpone(world, ev: dict) -> bool:
    """先贴原著：前提只差路程的原著(相关者活着、只是不在事发之地、也不在主角身边)延后到赶得到之日，至多 POSTPONE 回——不必改写。"""
    if ev.get("derived"):
        return False
    g, unmet = world.graph, lod._unmet(world, ev)
    mine = situation.around(world) | situation.entangled(world)
    if not unmet or ev.get("postponed", 0) >= POSTPONE or not all(
            key == "location" and n not in mine and g.get(n, "status") != "dead" for n, key, _ in unmet):
        return False
    need = [access.reach(world, g.get(n, "location")).get(want) for n, _, want in unmet]
    if not all(d is not None and d <= 30 for d in need):
        return False
    ev.update(day=world.clock.day + max(need) + 1, postponed=ev.get("postponed", 0) + 1)
    ev["order"] = _order(world, ev["day"], skip=ev)
    world.canon.sort(key=lambda e: e["order"])
    return True
