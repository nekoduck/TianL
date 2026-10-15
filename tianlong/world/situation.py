"""
[INPUT]: 依赖 world/access 的 barrier / steps（同伴过关、溃退去处）、world/graph 的 holds（谓词口径），World 门面（graph / player / clock / here / aliases / turn，鸭子类型）
[OUTPUT]: 对外提供 情境层的查询与连带——
          near()（近旁：同一处所之内、零日可达、无不通之关也不隔着悬崖暗门的子地点；v11 零日而有里数(li)的路不算近旁，结果按图的戳记缓存——关口要看主角身上之物的不缓存）、APART、around()（主角身边之人：此地 + 近旁，片区里的须在名册上）、
          area() / cast() / enlist() / muster() / elsewhere() / debuted() / inhabited() / bodies() / seen()（眼前(v5)：片区不是一间屋子，名册记着被剧情带到跟前的人，走出近旁即清空；
          shortnames() 近处子地点的短名(体检与落账同一口径)；
          seen 是本回合见过的人(眼前 + 回合开始时在身边 + 本回合赶来 + 近旁的遗体 bodies)，导演够得着、编剧只叫外貌都读它；
          同在一片而不在眼前的人只交导演；原著里尚未登场的人不在任何人眼前、也赶不来）、
          party() / join() / part() / follow()（随行：主角移动，同伴一并移动，过不去的留在关前；v12 不在路上的同伴了断随行、不再瞬移，同伴带着的人一并跟来）、
          SIGHT / vista() / sightable() / sighted()（v12 望见：隔着悬崖险径水路望得见、听不见、够不着）、meet() / MET_KEEP（v12 回合末记下见过的人）、BIG_FORMS / small_area()（v12 小片区：寻人而至即遇、原著相关者在这一片即算到位）、company() / hostages() / carried() / sunder()（v12 同行与押解：NPC 之间的随行按无向连通、某人扣着的人质、某人动身时一并带走的人、回合末了断两端异地的同行）、
          captors() / captive() / free()（受制：扣为人质、囚禁之类的关系边；v9 一群人的围攻也是一种受制）、CUSTODY、imperiled()（命悬一线：兜底选项、幕间省略、导演后台共用的口径）、PERIL、
          routed() / rout()（溃退：离场且数日内不得卷土重来）、
          spawn() / sweep()（场景实体：一队人马，入账、有归属、离远即回收；v8 物件不再另立——器物由场景清单布齐，FORGE 是驳回的缘由；v10 一队人马交 crowd.muster 重组或补充，回收即并回原群）、FORGE、
          quests()：track() / touch() / settle()（未了之事：至多四条、谓词满足即自动收束、久未推进者提示）、
          entangled()（与主角故事纠缠之人：同行者、未了之事所系者——lod 与 effects 据此拦住场外对他们的改写）、MAX_QUESTS、STALE
[POS]: v11 世界底座：不当值的伙计不在眼前(venue.on_duty)；上了锁的房门隔开人(锁着的库房不是隔壁)；带时辰的关口让近旁随光阴而变(不缓存)；场所房间的短名认得最后一截。
       world 层的情境层——原著数据里没有、剧情却要依赖的状态：谁此刻在主角眼前、谁跟着谁走、谁被谁扣着、谁新败而逃、此地临时多出来的人和物、主角还欠着什么。
       「在眼前」只有一个口径(around)：裁决、选项、视锥、认知校正、见证人数、原著的分身之禁都读它。
       每一种都有写入者(导演指令或系统连带)、读者(原著前提、裁决器、视锥与后台)与自动变化(随行跟走、获救即解押、溃退期满、任务谓词满足即了结)，
       让 LLM 想做的事都有合法的落账通道——没有通道的愿望，迟早会在文字里偷偷做掉
       v12 同行与押解随调遣：导演挪动一个人，他的同行者与人质一并同去(effects 据 carried 连带落账)；原著挪人不带人，回合末两端异地的同行由 sunder 了断；离队的同伴不再瞬移回主角身边；
       P1-7 擒者是人群、两端异地的拘押(原著挪走首领，人群随之而去)回合末也由 sunder 了断
       v14 近旁认父(_home：玉壁与谷底同一处所)；dismiss 把去处说不出的人从名册划掉；登门见得着在家的主人(at_home)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import access, venue
from .graph import holds

FOLLOW = "随行"                                                     # X —随行→ player
CUSTODY = {"扣为人质", "囚禁", "拘作花匠", "扣押", "擒获", "挟持", "绑架", "押解", "软禁", "围攻"}  # 擒者 —rel→ 被擒者；围攻(v9)：一群人同仇敌忾地围住某人
ROUT_DAYS = 2                                                       # 溃退者至少隔这么多日才会卷土重来
MAX_QUESTS = 4
PERIL = 0.15                                                        # 气血不足此比例即命悬一线
STALE = 12                                                          # 这么多回合未推进的未了之事，提示导演收束
GROUP, THING = "group", "thing"
SPAWN_KINDS = {GROUP}  # v8 场景清单：器物在创世时布齐，剧情不得新造物件(thing)；场景实体只剩一队人马
FORGE = "器物由世界掌管，不得新造：此地与身边有什么，清单里都列着——用清单里的原名，清单里没有的就是此地没有"


def _root(loc: str) -> str:
    return loc.split("·")[0]


def _home(g, loc: str) -> str:
    """同根(v14)：id 不带「·」而父地点带「·」的(无量玉壁之父为无量山·谷底)，按父地点的根算——谷底里的一处石壁与谷底同是一处所。
    52 回实录：玉壁与谷底不算近旁，站在玉壁揭不开谷底的暗路，导演连驳三次后在玉壁原地编出一座石室。"""
    parent = g.get(loc, "parent") if "·" not in loc and g.has(loc) else None
    return _root(parent) if parent and "·" in parent else _root(loc)


# ============================================================
#  近旁：同一处所(名号同根)之内、零日路程、没有拦人之关的子地点——喊一声就到的距离
#  「万劫谷」与「万劫谷·药室」是近旁；「无量山·山崖」与「无量山·谷底」中间隔着悬崖，不是——路上有关口(悬崖、暗门、险径)就不算近旁
#  眼前(v5)：近旁的「片区」(area：无量山、少林寺、中原这种下辖子地点或自成区域的大地方)不是一间屋子——
#  同在片区的人要被剧情带到主角跟前(cast：赶来的、原著带上台的、随行的)才算在眼前；其余只交导演(elsewhere)
# ============================================================
APART = {"悬崖", "险径", "水路", "秘道", "机关", "阵法", "其他"}  # 隔开了人的关口：崖顶喊不到谷底，暗门后的石室不算隔壁；守卫、禁地只拦脚步不隔声


def _apart(edge: dict) -> bool:
    """隔开了人的关口：悬崖暗门之类，v11 另有上了锁的房门(锁着的库房不是隔壁——东西要开了锁才拿得着)。"""
    return any(gate.get("hidden") or gate.get("kind") in APART or gate.get("key") for gate in (edge.get("gates") or {}).values())


def _volatile(edge: dict) -> bool:
    """这条路的关口要看主角身上的东西(requires 写着 player)或时辰(v11 hours)：近旁随主角、随光阴而变，不缓存。"""
    return any(gate.get("hours") or any(r and r[0] == "player" for r in gate.get("requires") or [])
               for gate in (edge.get("gates") or {}).values())


def near(world, loc: str | None = None) -> set[str]:
    """近旁：同根(v14 另认父地点之根，见 _home)、零日、没有拦人之关、也没有隔开人的关口(v5：悬崖、险径、机关暗门、秘道)。
    v11 零日而有里数(li)的路不算近旁：同城的另一坊、街对面的客栈当日走得到，却不是喊一声就到；结果按图的戳记缓存。"""
    g, loc = world.graph, loc or world.here
    hit = g.memo.get(("near", loc))
    if hit and hit[0] == g.stamp:
        return set(hit[1])
    seen, todo, volatile = {loc}, [loc], False
    while todo:
        a = todo.pop()
        for b, e in g.ways(a):
            if b not in seen and e["days"] == 0 and not e.get("li") and (_root(b) == _root(loc) or _home(g, b) == _home(g, loc)) and not _apart(e) \
                    and access.barrier(world, a, b, e, player=False) is None:
                seen.add(b)
                todo.append(b)
                volatile = volatile or _volatile(e)
    if not volatile:
        g.memo[("near", loc)] = (g.stamp, frozenset(seen))
    return seen


def area(world, loc) -> bool:
    return bool(world.graph.get(loc, "area"))


BIG_FORMS = {"区域", "都城", "大城", "州城", "县城", "市镇", "水域", "部落", "洲岛"}  # 大地方(v12)：中原、江南、大理城——同在一片也未必碰得上


def small_area(world, loc) -> bool:
    """小片区(v12)：片区之中形制不大的(山岭、峡谷、庄院、寺观、坊市……)——在这里寻人而至即遇，原著相关者在这一片即算到位；
    中原、江南、大理城这种大地方不算。adjudicate 的寻人与 story/canon 的原著窗口共用这一个口径。"""
    return bool(loc) and area(world, loc) and world.graph.get(loc, "form") not in BIG_FORMS


def cast(world) -> set[str]:
    """被剧情带到主角跟前的人(片区之内的名册)。"""
    return set(world.player.get("cast") or [])


def enlist(world, pids):
    """这些人来到了主角跟前(赶来、原著带上台)：片区之内也算在眼前；擒者带着他的人质。"""
    g, now = world.graph, list(world.player.get("cast") or [])
    for p in pids:
        for q in [p, *(e["dst"] for e in g.edges if e["src"] == p and e["rel"] in CUSTODY)]:
            if g.kind(q) in ("person", GROUP) and q not in now:  # 一群人(v10)被带到跟前也上名册
                now.append(q)
    world.player.set("cast", now)


def dismiss(world, pids) -> list[str]:
    """这些人离开了主角跟前、去向不明(v14)：片区之内从名册上划掉，人仍在这一片、只是不在眼前了；擒者带着他的人质一并走开。
    run3 第 7 回：司空玄押着钟灵「隐入密林、不见踪影」，账房写不出去处，两人在账上便一直站在主角眼前。返回划掉的人。"""
    g, gone = world.graph, set()
    for p in pids:
        if area(world, g.get(p, "location") or "") and p in cast(world):
            gone |= {p, *(e["dst"] for e in g.edges if e["src"] == p and e["rel"] in CUSTODY)}
    world.player.set("cast", [q for q in cast_list(world) if q not in gone])
    return sorted(gone)


def cast_list(world) -> list[str]:
    return list(world.player.get("cast") or [])


def muster(world, before: set[str]):
    """主角走出了原来的近旁(before)：跟前的人留在原处，名册清空——同行者照旧随行，不靠名册。"""
    if world.here not in before:
        world.player.set("cast", [])


def _alive(g, p) -> bool:
    return g.get(p, "status") != "dead" and not g.get(p, "hidden") and not g.get(p, "dormant")


def around(world, loc: str | None = None) -> set[str]:
    """主角身边之人（此地 + 近旁，活着、未隐匿、未休眠）：片区里的人须在名册上或正随行——同在「中原」的四十人不同处一室。"""
    g, spots = world.graph, near(world, loc)
    seen = cast(world) | set(party(world)) if loc is None or loc in near(world) else set()
    return {p for s in spots for p in g.where(type="person", location=s) if _alive(g, p) and venue.on_duty(world, p)
            and (not area(world, s) or p in seen)}  # 不当值的伙计(v11)回屋歇着了，不在眼前


def shortnames(world) -> dict[str, str]:
    """近处子地点的短名(v5)：「石级隧道」「玉像石室」即琅嬛福地·石级隧道、琅嬛福地·玉像石室——体检的名表与落账的名字归一同一口径。
    只收近旁与一步之遥(含暗路)的子地点，两处同名即都不收。"""
    local = near(world) | set(access.steps(world, world.here))
    out: dict[str, str] = {}
    for loc in sorted(local):
        parts = loc.split("·")
        for k in range(1, len(parts)):  # v11 场所的房间多一截：「东街客栈·大堂」「大堂」都认得，「客房·上房一」「上房一」亦然
            short = "·".join(parts[k:])
            out[short] = None if short in out and out[short] != loc else loc
    return {k: v for k, v in out.items() if v}


def bodies(world) -> set[str]:
    """近旁的遗体(v5)：死在主角眼前、或被抬到跟前的人(片区里亦须在名册上)——看得见、搜得着、抬得走，却叫不出名字。"""
    g, spots, roster = world.graph, near(world), cast(world)
    return {p for s in spots for p in g.where(type="person", location=s) if g.get(p, "status") == "dead"
            and not g.get(p, "hidden") and (not area(world, s) or p in roster)}


def seen(world) -> set[str]:
    """本回合主角见过的人(v5)：此刻眼前的、回合开始时在身边的、本回合赶来的，连同近旁的遗体。先走一步的人导演仍够得着(这一拍他还在)，
    编剧仍只叫他的外貌——他刚从主角眼前走开(或刚死在主角眼前)，换回名字就等于替主角认出了他。"""
    turn = getattr(world, "turn", None) or {}
    return around(world) | set(turn.get("present", ())) | set(turn.get("arrived", ())) | bodies(world)


MET_KEEP = 30  # 见过的人只记三十日内的(v12)


def meet(world):
    """回合末记下本回合见过的人(v12 黑板 met：{人: 最后见到的日子})：此刻眼前与本回合见过的(seen)，连同时间轴上各时刻耳边的人；
    只留 MET_KEEP 日内的。望见(隔着关口远远看见)不算见过——seen 本就不收望见之人。"""
    g, day = world.graph, world.clock.day
    turn = getattr(world, "turn", None) or {}
    faces = seen(world) | {p for m in turn.get("moments") or () for p in m.get("ears") or ()}
    met = {p: d for p, d in (world.player.get("met") or {}).items() if day - d <= MET_KEEP}
    met.update({p: day for p in faces if p != "player" and g.kind(p) == "person"})
    world.player.set("met", met)


def inhabited(world) -> bool:
    """这一片有没有人(不论在不在跟前)：传闻要有传话的人——独处石洞，江湖上的事传不进来。"""
    g, spots = world.graph, near(world)
    return bool(party(world)) or any(_alive(g, p) for s in spots for p in g.where(type="person", location=s))  # 歇着的伙计也传得了话


SIGHT = {"悬崖", "险径", "水路"}  # 望得见、够不着的关口(v12)：崖顶望得见谷底、隔着深涧望得见对崖；暗门秘道、机关阵法、上锁的门后看不见


def _vistas(world) -> dict[str, set[str]]:
    """近旁之外一步、零日、有关口且关口全在 SIGHT 里(不暗不锁)的地点 → 隔着的关口种类。没有关口的路不算：宫门—无量山走得到，不是望得见够不着。"""
    g, close, out = world.graph, near(world), {}
    for a in close:
        for b, e in g.ways(a):
            gates = list((e.get("gates") or {}).values())
            if b not in close and e["days"] == 0 and gates \
                    and all(x.get("kind") in SIGHT and not x.get("hidden") and not x.get("key") for x in gates):
                out.setdefault(b, set()).update(x["kind"] for x in gates)
    return out


def vista(world) -> set[str]:
    """隔着关口望得见的地方(v12)：主角在澜沧江边高崖，望得见无量山；在无量山·山崖，望得见谷底。"""
    return set(_vistas(world))


def sightable(world) -> set[str]:
    """此刻望得见的人与人群(v12)：vista 里活着、已露面、当值的人；vista 里的人群，与近旁片区里未到跟前的人群(有人站着、未藏、正当出没)；
    连同同在一片而未到跟前(elsewhere)、当值的人。望得见不等于在眼前：不进 around、seen、audience，导演够不着。"""
    from . import crowd  # crowd 引本模块：用时才引，不成环
    g, spots, close = world.graph, vista(world), near(world)
    people = {p for s in spots for p in g.where(type="person", location=s) if _alive(g, p) and debuted(world, p) and venue.on_duty(world, p)}
    groups = {s for s in g.where(type=GROUP) if crowd.is_squad(g, s) and not g.get(s, "hidden") and crowd.active(world, s)
              and crowd.standing(g, s) > 0 and (g.get(s, "location") in spots or (g.get(s, "location") in close and not crowd.present(world, s)))}
    return people | groups | {p for p in elsewhere(world) if venue.on_duty(world, p)}


def sighted(world) -> list[str]:
    """本回合望见的人与人群(v12 turn["sighted"]，按先后)：望见不是见过——不上名册、不进眼前、不记进 met。"""
    return list((getattr(world, "turn", None) or {}).get("sighted") or [])


def debuted(world, pid: str) -> bool:
    """此人是否已在江湖上露面：原著里没有戏份的人一向都在；有戏份的，第一桩已到期(演了、作罢了或今天该演)才算——
    原著数据把南海鳄神开局就放在无量山，他却要到第四回才登场：在此之前，他不在任何人的眼前。"""
    done, mine = set(world.done), [ev for ev in world.canon if pid in ev["actors"]]
    return not mine or any(ev["id"] in done or ev["day"] <= world.clock.day for ev in mine)


def elsewhere(world) -> list[str]:
    """同在近旁的片区里、此刻却不在眼前、且已在江湖上露面的人：只交导演——要他们登场写 arrive(同在一片，不计路程)。"""
    g, spots, close = world.graph, near(world), around(world)
    return sorted(p for p in g.where(type="person") if g.get(p, "location") in spots and p not in close and _alive(g, p)
                  and (debuted(world, p) or at_home(g, p)))  # v14 主角登门拜访：主人在自己家里，原著戏份未到也见得着(run3 第 16~19 回进了万劫谷，谷主夫人一直不露面)


def at_home(g, p) -> bool:
    """此人正在自己的居所(home)里。"""
    home, loc = g.get(p, "home"), g.get(p, "location") or ""
    return bool(home) and (loc == home or loc.startswith(home + "·"))


# ============================================================
#  随行
# ============================================================
def entangled(world) -> set[str]:
    """与主角的故事纠缠在一起的人：正随主角同行者、主角未了之事所系之人。他们的场外原著不再照本宣科，场外剧情(v11)也挪不动他们。"""
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
    """主角走完 route 之后，同伴沿同一路线跟上；某一步对同伴不通，就留在那一步之前。返回连带说明。
    v12：只带走此刻在这条路线上任一处或其近旁的同伴，连同他一并带走的人(carried：他的同行者与人质)，到了即上名册；
    不在路上的(被导演送去了别处)了断随行、回告「X已不在你身边」——不再从大理城瞬移回主角身边。"""
    g, notes = world.graph, []
    way = set().union(*(near(world, loc) for loc in route)) if route else set()
    turn = getattr(world, "turn", None)
    movers = turn.setdefault("movers", {}) if turn is not None else {}
    for pid in party(world):
        if captors(world, pid):
            part(world, pid)
            notes.append(f"{pid}身受拘押，未能随你同行")
            continue
        at = g.get(pid, "location")
        if at not in way:
            part(world, pid)
            notes.append(f"{pid}已不在你身边")
            continue
        band = [q for q in carried(world, pid, at) if q not in party(world)]
        stop = route[-1]
        for a, b in zip(route, route[1:]):
            edge = g.road(a, b)
            if edge and access.barrier(world, a, b, edge, player=False):
                stop = a
                break
        g.set(pid, "location", stop)
        for q in band:
            g.set(q, "location", stop)
            movers[q] = "director"
        if stop != route[-1]:
            part(world, pid)
            notes.append(f"{pid}过不去，留在了{stop}" + (f"，{'、'.join(band)}也留在那里" if band else ""))
        elif band:
            enlist(world, band)
            notes.append(f"{'、'.join(band)}随{pid}一同跟来")
    return notes


# ============================================================
#  同行与押解(v12)：NPC 之间的随行、擒者与人质——一人被调遣，同行者与人质一并动身；回合末两端异地的同行了断
# ============================================================
def company(world, pid: str) -> list[str]:
    """与 pid 同行的人：以「随行」相连、两端都不是主角，按无向连通算(段誉→钟灵与钟灵→段誉同义)；只收活人。"""
    g, links = world.graph, {}
    for e in g.edges:
        if e["rel"] == FOLLOW and "player" not in (e["src"], e["dst"]):
            links.setdefault(e["src"], set()).add(e["dst"])
            links.setdefault(e["dst"], set()).add(e["src"])
    seen, todo = {pid}, [pid]
    while todo:
        for q in sorted(links.get(todo.pop(), ())):
            if q not in seen and g.kind(q) == "person" and g.get(q, "status") != "dead":
                seen.add(q)
                todo.append(q)
    return sorted(seen - {pid})


def hostages(world, pid: str) -> list[str]:
    """pid 扣着的人：pid 作擒者、关系是拘押(围攻除外——一群人围住某人，不是押着他走)。"""
    return sorted({e["dst"] for e in world.graph.edges if e["src"] == pid and e["rel"] in CUSTODY - {"围攻"}})


def carried(world, pid: str, at: str | None) -> list[str]:
    """pid 从 at 动身时一并带走的人：同行者，连同他与同行者扣着的人质——逐一筛：此刻在 at 或其近旁；活着、未隐匿、未休眠；
    本回合没被别的来源(原著、场外剧情)调遣；受制于人的，擒者须也在被带走之列(免得把人质与擒者拆开)。"""
    g = world.graph
    if not at or g.kind(pid) != "person":
        return []
    band = company(world, pid)
    want = list(dict.fromkeys(band + [h for p in [pid, *band] for h in hostages(world, p)]))
    spots = near(world, at)
    movers = (getattr(world, "turn", None) or {}).get("movers", {})
    keep = [q for q in want if q != pid and g.kind(q) == "person" and g.get(q, "location") in spots and _alive(g, q)
            and movers.get(q, "director") == "director"]
    crew = set(keep) | {pid}
    return [q for q in keep if all(c in crew for c in captors(world, q))]


def sunder(world) -> list[str]:
    """回合末了断名存实亡的同行(engine 在 sweep 之后调)：NPC 之间两端异地(不在彼此近旁)的随行了断(原著把段誉挪走，钟灵留下)；
    随行→主角的边，随行者不在主角近旁也了断；擒者是人群、两端异地的拘押也了断(v12 P1-7)。返回说明，写日志。"""
    g, out, close = world.graph, [], near(world)
    for e in [e for e in g.edges if e["rel"] == FOLLOW]:
        a, b = e["src"], e["dst"]
        if "player" in (a, b):
            other = a if b == "player" else b
            apart = g.get(other, "location") not in close
        else:
            la, lb = g.get(a, "location"), g.get(b, "location")
            apart = not la or not lb or lb not in near(world, la)
        if apart:
            g.unlink(a, b, FOLLOW)
            out.append(f"{a}与{'你' if b == 'player' else b}已不同行")
    from . import crowd  # crowd 引本模块：用时才引，不成环
    for e in [e for e in g.edges if e["rel"] in CUSTODY and crowd.is_squad(g, e["src"])]:  # 人群的拘押两端异地(原著挪走首领，人群随之而去)：了断
        a, b = e["src"], e["dst"]
        la, lb = g.get(a, "location"), (world.here if b == "player" else g.get(b, "location"))
        if not la or not lb or lb not in near(world, la):
            g.unlink(a, b, e["rel"])
            out.append(f"{'你' if b == 'player' else b}不再受{crowd.handle(g, a)}看押")
    return out


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
#  场景实体：群体(一队谷丁)——入账、有归属、离远即回收；物件不再另立(v8：器物在创世时由场景清单布齐，旧档里立过的照旧回收)
#  不得冒用原著实体之名；群体须有据可依：所属门派在附近有人或有据点，且不是原著近事里尚未到场的势力
# ============================================================
def spawn(world, spec: dict, embargo: set[str] = frozenset()) -> tuple[str | None, str | None]:
    """按 spec 立一个场景实体；返回 (id, None) 或 (None, 不成立的缘由)。embargo：原著近事里尚未到场的势力。
    物件一概不立(v8)：要的若就是现场的某件器物，裁决器先已用 effects.unearth 认回它。"""
    g = world.graph
    kind, name = spec.get("kind"), str(spec.get("name") or "").strip()[:12]
    if kind == THING:
        return None, FORGE
    if kind not in SPAWN_KINDS or not name:
        return None, "场景实体须写明 kind(group) 与 name"
    from . import crowd  # crowd 引本模块：用时才引，不成环
    if crowd.is_squad(g, world.aliases.get(name)):  # 上回整群调来、叫作这个名字的那一群
        return world.aliases[name], None
    if g.has(name) or name in world.aliases or name in ("player", "主角", world.player["name"]):
        return (name, None) if g.get(name, "ephemeral") else (None, f"「{name}」已是书中之名，不可另立")
    return crowd.muster(world, spec, name, set(embargo), _rooted)  # 一队人马(v10)是既有人群的重组，或这一门补来的无名之众


def _rooted(world, faction: str) -> bool:
    g = world.graph
    dist = g.distances(world.here)
    base = g.get(faction, "base")
    if base and dist.get(base, 99) <= 1:
        return True
    return any(g.get(p, "faction") == faction and dist.get(g.get(p, "location"), 99) <= 1
               for p in g.where(type="person"))


def sweep(world) -> list[str]:
    """主角离开一日路程以外，场景实体就地回收（主角带在身上的物件除外）：从人群里分出去的一队并回原来那一群(v10，人头与身上之物守恒)，
    补来的一队回到这一门的据点(不再记账)；随主角同行的不收。"""
    from . import crowd
    g, dist = world.graph, world.graph.distances(world.here)
    company = set(party(world))
    gone = [n for n, node in g.nodes.items() if node.get("ephemeral") and node.get("holder") != "player"
            and dist.get(node.get("location"), 99) > 1 and n not in company]
    for n in gone:
        if g.kind(n) == GROUP:
            crowd.rejoin(world, n)
        else:
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
