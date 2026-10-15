"""
[INPUT]: 依赖 world/graph 的 ROAD、world/clock 的 PER_DAY / PER_SHICHEN / SHICHEN；World 门面(graph / atlas / here / clock / player，鸭子类型)；
         近景的 id 与形状由 world/founding 在编译时定下(atlas["venues"])
[OUTPUT]: 对外提供 venue_of()（某处属于哪一处场所）、furnish()（布置一处场所的近景）、settle()（主角所在与一步之遥的场所都布好）、
          relay()（读档重绘道路之后，接回已布置场所的房间之路与房门）、restock()（跨了日子补货）、
          door()（走进一处新立的场所即进它的前堂）、open_at()（某个开闭时辰此刻开不开）、on_duty()（伙计此刻当不当值）、spec()、wares()、services()、LI_MINUTES
[POS]: world 层的场所(v11 世界底座)——近大远小：远处的店铺只是地图上的一个地名(founding 立的地点，带招牌、形制、价目系数)，
       主角走到店里或店门口(一步之遥)，这一处的近景才布进图里：房间(「场所·房间名」，与正堂零日零里即近旁，上锁的房门是关口)、
       陈设景物、器物(柜银是一堆碎银)、伙计(功能性人物，只有职名；身上的东西「伙计·名」)、货架上的货(wares：价钱、存货、每日补回)。
       布置是确定的、幂等的：同一处场所布两次是同一副样子(试演与定稿一致)，id 不变，读档之后再接回房间之路。
       伙计有当值时辰：不当值的不在眼前(situation 据 on_duty 判)，货与服务要有人当值才办得成(事码据此判)。
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy

from .clock import PER_DAY, PER_SHICHEN, SHICHEN
from .graph import ROAD

LI_MINUTES = 6  # 城中步行一里约六分(一刻走两里半)：同城的街巷之间零日而有里数，走一趟也要光阴


def spec(world, vid: str) -> dict | None:
    return ((getattr(world, "atlas", None) or {}).get("venues") or {}).get(vid)


def venue_of(g, loc: str | None) -> str | None:
    """某处属于哪一处场所：场所自身，或它的房间(上溯几级)。"""
    for _ in range(4):
        if loc is None:
            return None
        if g.get(loc, "venue"):
            return loc
        loc = g.get(loc, "parent")
    return None


def _gate(edge_gate: dict | None) -> dict | None:
    return copy.deepcopy(edge_gate) if edge_gate else None


def _road(g, vid: str, room: dict):
    """正堂到房间的路：零日，里数缺省为零(同一座建筑之内，喊一声就听得见)；上锁的房门是进屋这一向的关口。"""
    if room.get("reuse") or g.road(vid, room["id"]):
        return
    attrs = {"days": 0, **({"li": room["li"]} if room.get("li") else {})}
    if room.get("gate"):
        attrs["gates"] = {room["id"]: _gate(room["gate"])}
    g.link(vid, room["id"], ROAD, **attrs)


def furnish(world, vid: str) -> list[str]:
    """把 atlas 里编好的近景布进图里，返回新立的节点 id。已布置的不再布(幂等)；已在图上的(有人拿走又放回、读档)照现状不动。"""
    g, sp = world.graph, spec(world, vid)
    if not sp or g.get(vid, "furnished") is not None:
        return []
    made = []

    def put(node: dict):
        nid = node["id"]
        if not g.has(nid):
            g.nodes[nid] = {k: copy.deepcopy(v) for k, v in node.items() if k not in ("id", "items")}
            made.append(nid)
    for room in sp["rooms"]:
        if not room.get("reuse") and not g.has(room["id"]):
            g.nodes[room["id"]] = {"type": "location", "parent": vid, "region": g.get(vid, "region"), "desc": room.get("desc"),
                                   "lore": [], "state": None, "form": "房间", "layer": room.get("layer", 3),
                                   "polity": g.get(vid, "polity"), "order": g.get(vid, "order")}
            made.append(room["id"])
        _road(g, vid, room)
    for node in [*sp["features"], *sp["items"]]:
        put(node)
    for person in sp["staff"]:
        put(person)
        for item in person.get("items") or []:
            put(item)
    if sp.get("till"):
        put(sp["till"])
    node = g.nodes[vid]
    node["wares"] = {gid: {k: w[k] for k in ("id", "price", "stock", "full", "restock", "in")} for gid, w in sp["wares"].items()}
    node["furnished"] = world.clock.day
    return made


def door(world, vid: str) -> str | None:
    """走进一处新立的场所，进的是它的前堂(柜台所在的那一间，没有柜台即第一间)：店铺这个地名本身只是一座房子，人与货都在屋里。
    还没布置的先布好；01 原著已登记的场所(少林寺、松鹤楼……)照原样，不改道。"""
    sp = spec(world, vid)
    if not sp or any(r.get("reuse") for r in sp["rooms"]) or not sp["rooms"] or world.graph.get(vid, "form") != "场所":
        return None
    furnish(world, vid)
    counter = next((f["location"] for f in sp["features"] if f["id"].endswith("·柜台")), None)
    front = counter or sp["rooms"][0]["id"]
    return front if world.graph.has(front) else None


def nearby(world) -> list[str]:
    """该布置的场所：主角所在之处与近旁所属的场所，连同一步之遥的(站在街上，街边的店门就在眼前)。"""
    from . import situation  # situation 引 access、access 不引本模块：用时才引，不成环
    g, spots = world.graph, situation.near(world)
    out = {venue_of(g, loc) for loc in spots}
    for loc in spots:
        out |= {venue_of(g, nxt) for nxt, _ in g.ways(loc)}
    return sorted(v for v in out if v)


def settle(world) -> list[str]:
    """主角近处的场所都布好(回合开始、主角移动之后、创世与读档时)：返回新立的节点 id。"""
    made = []
    for vid in nearby(world):
        made += furnish(world, vid)
    return made


def relay(world):
    """读档时道路随数据重绘(world.remap)：已布置的场所把房间之路与房门接回来——房间、伙计、器物本身照存档。"""
    g = world.graph
    for vid in g.of("location"):
        if g.get(vid, "furnished") is not None and spec(world, vid):
            for room in spec(world, vid)["rooms"]:
                if g.has(room["id"]):
                    _road(g, vid, room)


def restock(world, days: int):
    """跨了日子：已布置的场所把每日补货的货补回原数(现做现卖的不限量)。"""
    if days <= 0:
        return
    g = world.graph
    for vid in g.of("location"):
        for w in (g.get(vid, "wares") or {}).values():
            if w.get("restock") and w.get("full") is not None:
                w["stock"] = w["full"]


def _shichen(world) -> int:
    return (world.clock.tick % PER_DAY) // PER_SHICHEN


def open_at(hours: str | None, shichen: int) -> bool:
    """「卯-酉」：卯时开、酉时闭(卯至申开着)；「酉-卯」跨夜；None 整日不闭。"""
    if not hours or "-" not in hours:
        return True
    a, b = (SHICHEN.find(x) for x in hours.split("-", 1))
    if a < 0 or b < 0 or a == b:
        return True
    return a <= shichen < b if a < b else shichen >= a or shichen < b


def on_duty(world, pid: str) -> bool:
    """伙计此刻当不当值：不当值的不在眼前(回屋歇着了)，货与服务也没人办。有名之人与没写时辰的伙计一向都在。"""
    g = world.graph
    return not g.get(pid, "staff") or open_at(g.get(pid, "hours"), _shichen(world))


def wares(world, vid: str) -> dict:
    return world.graph.get(vid, "wares") or {}


def services(world, vid: str) -> list[dict]:
    sp = spec(world, vid)
    return list(sp["services"]) if sp else []
