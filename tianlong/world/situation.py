"""
[INPUT]: 依赖 world/access 的 barrier / steps（同伴过关、溃退去处）、world/graph 的 holds（谓词口径），World 门面（graph / player / clock / here / aliases / turn，鸭子类型）
[OUTPUT]: 对外提供 情境层的查询与连带——
          near()（近旁：同一处所之内、零日可达、无不通之关的子地点）、around()（主角身边之人：此地 + 近旁）、
          party() / join() / part() / follow()（随行：主角移动，同伴一并移动，过不去的留在关前）、
          captors() / captive() / free()（受制：扣为人质、囚禁之类的关系边）、CUSTODY、imperiled()（命悬一线：兜底选项、幕间省略、导演后台共用的口径）、PERIL、
          routed() / rout()（溃退：离场且数日内不得卷土重来）、
          spawn() / sweep()（场景实体：群体与寻常物件，入账、有归属、离远即回收）、
          quests()：track() / touch() / settle()（未了之事：至多四条、谓词满足即自动收束、久未推进者提示）、
          entangled()（与主角故事纠缠之人：同行者、未了之事所系者——lod 与 effects 据此拦住场外对他们的改写）、MAX_QUESTS、STALE
[POS]: world 层的情境层——原著数据里没有、剧情却要依赖的状态：谁跟着谁走、谁被谁扣着、谁新败而逃、此地临时多出来的人和物、主角还欠着什么。
       每一种都有写入者(导演指令或系统连带)、读者(原著前提、裁决器、视锥与后台)与自动变化(随行跟走、获救即解押、溃退期满、任务谓词满足即了结)，
       让 LLM 想做的事都有合法的落账通道——没有通道的愿望，迟早会在文字里偷偷做掉
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import access
from .graph import holds

FOLLOW = "随行"                                                     # X —随行→ player
CUSTODY = {"扣为人质", "囚禁", "拘作花匠", "扣押", "擒获", "挟持", "绑架", "押解", "软禁"}  # 擒者 —rel→ 被擒者
ROUT_DAYS = 2                                                       # 溃退者至少隔这么多日才会卷土重来
MAX_QUESTS = 4
PERIL = 0.15                                                        # 气血不足此比例即命悬一线
STALE = 12                                                          # 这么多回合未推进的未了之事，提示导演收束
GROUP, THING = "group", "thing"
SPAWN_KINDS = {GROUP, THING}


def _root(loc: str) -> str:
    return loc.split("·")[0]


# ============================================================
#  近旁：同一处所(名号同根)之内、零日路程、没有拦人之关的子地点——喊一声就到的距离
#  「万劫谷」与「万劫谷·药室」是近旁；「无量山」与「无量山·谷底」中间隔着悬崖，不是
# ============================================================
def near(world, loc: str | None = None) -> set[str]:
    g, loc = world.graph, loc or world.here
    seen, todo = {loc}, [loc]
    while todo:
        a = todo.pop()
        for b, e in g.ways(a):
            if b not in seen and e["days"] == 0 and _root(b) == _root(loc) \
                    and access.barrier(world, a, b, e, player=False) is None:
                seen.add(b)
                todo.append(b)
    return seen


def around(world, loc: str | None = None) -> set[str]:
    """主角身边之人（此地 + 近旁，活着、未隐匿、未休眠）。"""
    g, spots = world.graph, near(world, loc)
    return {p for p in g.where(type="person") if g.get(p, "location") in spots and g.get(p, "status") != "dead"
            and not g.get(p, "hidden") and not g.get(p, "dormant")}


# ============================================================
#  随行
# ============================================================
def entangled(world) -> set[str]:
    """与主角的故事纠缠在一起的人：正随主角同行者、主角未了之事所系之人。他们的场外原著不再照本宣科，场外推演与史官也挪不动他们。"""
    about = {a for meta in quests(world).values() for a in meta.get("about", [])}
    return set(party(world)) | {a for a in about if world.graph.kind(a) == "person"}


def party(world) -> list[str]:
    g = world.graph
    return [e["src"] for e in g.edges if e["rel"] == FOLLOW and e["dst"] == "player"
            and g.get(e["src"], "status") != "dead"]


def join(world, pid: str) -> list[str]:
    """pid 随主角同行：受制于人者随之获救（擒者若在身边，那是一场抢人，应由导演写明）。返回连带说明。"""
    notes = []
    if pid in party(world):
        return notes
    world.graph.link(pid, "player", FOLLOW)
    freed = free(world, pid)
    if freed:
        notes.append(f"{pid}脱离了{'、'.join(freed)}的拘押")
    return notes


def part(world, pid: str):
    world.graph.unlink(pid, "player", FOLLOW)


def follow(world, route: list[str]) -> list[str]:
    """主角走完 route 之后，同伴沿同一路线跟上；某一步对同伴不通，就留在那一步之前。返回连带说明。"""
    g, notes = world.graph, []
    for pid in party(world):
        if captors(world, pid):
            part(world, pid)
            notes.append(f"{pid}身受拘押，未能随你同行")
            continue
        stop = route[-1]
        for a, b in zip(route, route[1:]):
            edge = g.road(a, b)
            if edge and access.barrier(world, a, b, edge, player=False):
                stop = a
                break
        g.set(pid, "location", stop)
        if stop != route[-1]:
            part(world, pid)
            notes.append(f"{pid}过不去，留在了{stop}")
    return notes


# ============================================================
#  受制
# ============================================================
def captors(world, pid: str) -> list[str]:
    return [e["src"] for e in world.graph.edges if e["rel"] in CUSTODY and e["dst"] == pid]


def imperiled(world) -> bool:
    """命悬一线：气血不足 PERIL——兜底选项、幕间省略、导演后台共用这一个口径。"""
    return world.player["hp"] <= world.player["max_hp"] * PERIL


def captive(world) -> set[str]:
    return {e["dst"] for e in world.graph.edges if e["rel"] in CUSTODY}


def free(world, pid: str) -> list[str]:
    who = captors(world, pid)
    world.graph.edges = [e for e in world.graph.edges if not (e["rel"] in CUSTODY and e["dst"] == pid)]
    return who


# ============================================================
#  溃退：败走者离场，ROUT_DAYS 日内不会再来；离场之处由系统挑一个相邻之地
# ============================================================
def routed(world, pid: str) -> bool:
    return world.graph.get(pid, "routed_until", -1) > world.clock.day


def rout(world, pid: str) -> str | None:
    """让 pid 败走：挑一处相邻、且不在主角近旁的地方；无处可去返回 None（交导演写明去向）。"""
    g, close = world.graph, near(world)
    here = g.get(pid, "location")
    away = sorted((b for b in access.steps(world, here) if b not in close),
                  key=lambda b: (_root(b) == _root(world.here), b))
    if not away:
        return None
    g.set(pid, "location", away[0])
    g.set(pid, "routed_until", world.clock.day + ROUT_DAYS)
    part(world, pid)
    return away[0]


# ============================================================
#  场景实体：群体(一队谷丁)与寻常物件(碎银、火折、两颗明珠)——入账、有归属、离远即回收
#  不得冒用原著实体之名；群体须有据可依：所属门派在附近有人或有据点，且不是原著近事里尚未到场的势力
# ============================================================
def _similar(a: str, b: str) -> bool:
    return len(a) >= 2 and len(b) >= 2 and (a in b or b in a)


def spawn(world, spec: dict, embargo: set[str] = frozenset()) -> tuple[str | None, str | None]:
    """按 spec 立一个场景实体；返回 (id, None) 或 (None, 不成立的缘由)。embargo：原著近事里尚未到场的势力。"""
    g = world.graph
    kind, name = spec.get("kind"), str(spec.get("name") or "").strip()[:12]
    if kind not in SPAWN_KINDS or not name:
        return None, "场景实体须写明 kind(group/thing) 与 name"
    if g.has(name) or name in world.aliases or name in ("player", "主角", world.player["name"]):
        return (name, None) if g.get(name, "ephemeral") else (None, f"「{name}」已是书中之名，不可另立")
    canon = [n for n, node in g.nodes.items() if node["type"] in ("person", "item") and not node.get("ephemeral")]
    clash = next((n for n in canon if _similar(name, n)), None)
    if clash and kind == THING:
        return None, f"「{name}」与原著之物「{clash}」相混，请直接用「{clash}」或换个寻常之名"
    node = {"type": "item" if kind == THING else GROUP, "ephemeral": True, "born": world.clock.day,
            "desc": str(spec.get("desc") or "")[:40], "location": world.here, "hidden": False}
    if kind == THING:
        node.update(kind="物件", holder=None, grants=None, effect=None, state={"exists": True, "available": True})
    else:
        faction = spec.get("faction")
        faction = world.aliases.get(faction, faction)
        if g.kind(faction) != "faction":
            return None, f"群体「{name}」须属于一个已登记的门派"
        if faction in embargo:
            return None, f"{faction}的人马此时尚未到此（原著近事），不得先行登场"
        if not _rooted(world, faction):
            return None, f"{faction}在此地附近既无据点也无人手，凭空来不了一队人"
        count = spec.get("count")
        node.update(faction=faction, status="alive", count=count if isinstance(count, int) and 0 < count <= 200 else 10)
    g.nodes[name] = node
    return name, None


def _rooted(world, faction: str) -> bool:
    g = world.graph
    dist = g.distances(world.here)
    base = g.get(faction, "base")
    if base and dist.get(base, 99) <= 1:
        return True
    return any(g.get(p, "faction") == faction and dist.get(g.get(p, "location"), 99) <= 1
               for p in g.where(type="person"))


def sweep(world) -> list[str]:
    """主角离开一日路程以外，场景实体就地回收（主角带在身上的物件除外）。"""
    g, dist = world.graph, world.graph.distances(world.here)
    gone = [n for n, node in g.nodes.items() if node.get("ephemeral") and node.get("holder") != "player"
            and dist.get(node.get("location"), 99) > 1]
    for n in gone:
        del g.nodes[n]
    if gone:
        g.edges = [e for e in g.edges if e["src"] not in gone and e["dst"] not in gone]
    return gone


# ============================================================
#  未了之事：threads 是给人读的一列文字；quests 记着每一条的对象、了结谓词与最近一次推进
#  谓词：[id, 属性, 期望] 属性相符；[src, "~关系", dst] 有此关系；[src, "!关系", dst] 无此关系
# ============================================================
def quests(world) -> dict:
    return world.player.data.setdefault("quests", {})


def track(world, goal: str, about: list[str], done_when=None) -> list[str]:
    """登记一条未了之事；满四条时挤掉最久未推进的一条。返回连带说明。"""
    q, me, notes = quests(world), world.player, []
    turn = me.get("turn", 0)
    q[goal] = {"about": about, "done_when": done_when if _valid(done_when) else None, "since": turn, "touched": turn}
    while len(me["threads"]) > MAX_QUESTS:
        oldest = min((t for t in me["threads"] if t != goal), key=lambda t: q.get(t, {}).get("touched", -1))
        me.pull("threads", oldest)
        q.pop(oldest, None)
        notes.append(f"放下了旧事「{oldest}」")
    return notes


def touch(world, ids: set[str]):
    """本回合动到了哪些实体：以它们为对象的未了之事算作推进过。"""
    q, turn = quests(world), world.player.get("turn", 0)
    for goal in world.player["threads"]:
        meta = q.get(goal)
        if meta and set(meta["about"]) & ids:
            meta["touched"] = turn


def settle(world) -> list[str]:
    """谓词满足、或所系之人已死尽的未了之事，自动了结。返回了结的条目。"""
    q, g, done = quests(world), world.graph, []
    for goal in list(world.player["threads"]):
        meta = q.get(goal) or {}
        about = [a for a in meta.get("about", []) if g.kind(a) == "person"]
        if (meta.get("done_when") and all(_holds(world, c) for c in meta["done_when"])) or \
                (about and all(g.get(a, "status") == "dead" for a in about)):
            world.player.pull("threads", goal)
            q.pop(goal, None)
            done.append(goal)
    for goal in list(q):  # 被导演直接 pull 掉的条目，元数据随之清走
        if goal not in world.player["threads"]:
            q.pop(goal)
    return done


def stale(world) -> list[str]:
    q, turn = quests(world), world.player.get("turn", 0)
    return [t for t in world.player["threads"] if turn - q.get(t, {}).get("touched", turn) >= STALE]


def _valid(cond) -> bool:
    return isinstance(cond, list) and bool(cond) and all(isinstance(c, list) and len(c) == 3 for c in cond)


def _holds(world, cond: list) -> bool:
    a, key, b = cond
    return holds(world.graph, a, key, b, cur=world.player.get(key) if a == "player" and key[:1] not in "~!" else None)
