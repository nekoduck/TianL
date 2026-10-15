"""
[INPUT]: 读取 data/canon/19_places.json ~ 27_lines.json(世界底座，格式见 data/WORLD_PROMPT.md 第六~十五节)，由 world/genesis 在 01~08 之后、18 场景清单之前调用；
         依赖 world/crowd 的 GROUP / DISBAND（人群）
[OUTPUT]: 对外提供 found()（就地补注节点、立新处所与场所、人群与随身之物，返回 Founding：错误、道路补丁、关口、关口补丁、新关系、静态的 atlas）、
          Founding、SIZES、CROWD_MAX、DRIVE_MAX、KNOWN_KEYS、nth()
[POS]: world 层的世界底座编译器(v11)——近大远小的底座在这里入世：
       19 处所卡补到 01 的地点上(form 形制、layer 层级、polity 所属之国、owner 主人、far 远景、vista 近景、bustle 人流、order 治安、hours 开闭、known 知者)，新处所入图，道路补丁(零日之路另带里数 li)，关口另有钥匙、时辰、关钱、把守；
       20 场所实例立为地点(01 已登记的只补注)，由所在之处按里数接路；模板按 7.6 的规则在此展开成「场所的近景」(房间、陈设、器物、伙计及其随身之物、货品价目、服务、招工、柜银)，
       id 在此定下、校验，却不入图——放进 atlas，主角走近时由 world/venue 布置(近大远小：远处的店只是一个地名，走进去一桌一椅才齐)；
       21 货品目录与各地物价、银钱，原著器物补注(层级、知者、估值、效用)；22 有名之人补注(层级、名声、零钱、识字、言语、随身之物、居所与常去之处、作息、能办的事、知道的消息、好恶软肋、产业、
       剧情推力、所求、心愿与了结条件、手段、底线、原著走向、出没时段)；23 门派补注与新势力、门下模板(一派几套)、人群(三到三百人，出没时段)；24 国法、江湖规矩与天龙世界的准则；25 消息；26 风物天时；27 原著剧情线与事件注——
       后几样是静态的表，进 atlas，不进存档。错一处即记一条错误，genesis 汇总后拒绝开局。
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .crowd import DISBAND, GROUP

FILES = ("19_places.json", "20_venues.json", "21_goods.json", "22_people.json", "23_factions.json",
         "24_laws.json", "25_lore.json", "26_nature.json", "27_lines.json")
FORMS = {"都城", "大城", "州城", "县城", "市镇", "村落", "部落", "寨堡", "军营", "驿站", "庄院", "府邸", "宫苑", "寺观", "坊市", "场所", "房间",
         "山岭", "峡谷", "洞窟", "水域", "洲岛", "渡口", "关隘", "道路", "荒野", "坟冢", "区域"}
BUSTLE = ("冷清", "寻常", "热闹", "繁华")  # 人流四等(4.7)：众目之下的判断据此
ORDER = {"官府", "门派", "豪强", "军中", "无主", "匪患"}
SIZES = {"小": 0.5, "中": 1.0, "大": 2.0}  # 场所规模：伙计人数、存货、柜银约按半倍、一倍、两倍(每职至少一人)
CROWD_MAX = 300   # 人群至多三百人(聚贤庄群雄)
DRIVE_MAX = 5     # 剧情推力 0~5
KNOWN_KEYS = ("in", "tags", "who", "faction", "item")  # 知者：满足一条即知道；不写即天下皆知
HOURS = re.compile(r"^[子丑寅卯辰巳午未申酉戌亥]-[子丑寅卯辰巳午未申酉戌亥]$")
LORE_KINDS = {"掌故", "名号", "门道", "风声", "物议", "行情", "传说"}
ROLES = ("起", "承", "转", "合", "余波")
GATE = ("kind", "blocked", "hidden", "how", "requires", "risk")
META = ("src", "inferred", "basis", "inferred_fields")
NUMERALS = "零一二三四五六七八九十"


def nth(i: int) -> str:
    """几间、几人同名时的编号：1 → 一、12 → 十二、20 → 二十。"""
    if i <= 10:
        return NUMERALS[i]
    tens, ones = divmod(i, 10)
    return (NUMERALS[tens] if tens > 1 else "") + "十" + (NUMERALS[ones] if ones else "")


@dataclass
class Founding:
    errors: list = field(default_factory=list)
    roads: dict = field(default_factory=lambda: {"remove": [], "add": [], "change": []})  # 19 的道路补丁 + 场所接路(带里数)
    gates: list = field(default_factory=list)        # (来处, 去处, 关口)
    patches: list = field(default_factory=list)      # 给 14 已有关口补的几项
    relations: list = field(default_factory=list)
    atlas: dict = field(default_factory=dict)


def _read(root: Path, name: str):
    path = root / name
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _strip(row: dict, *drop) -> dict:
    return {k: v for k, v in row.items() if k not in META and k not in drop}


class _Book:
    """编译时的登记簿：节点、别名与本次新立的 id——新 id 不得与书中之名、别名或本次别的新 id 相撞。"""

    def __init__(self, nodes: dict, raw_aliases: dict, out: Founding):
        self.nodes, self.raw, self.out, self.fresh_ids = nodes, raw_aliases, out, set()

    def err(self, msg: str):
        self.out.errors.append(msg)

    def kind(self, nid) -> str | None:
        return self.nodes.get(nid, {}).get("type") if isinstance(nid, str) else None

    def need(self, nid, kinds, ctx) -> bool:
        if nid is None:
            return True
        if self.kind(nid) not in kinds:
            self.err(f"{ctx}：「{nid}」不是已登记的{'/'.join(kinds)}")
            return False
        return True

    def claim(self, nid, ctx) -> bool:
        if not isinstance(nid, str) or not nid.strip():
            self.err(f"{ctx}：缺 id")
            return False
        if nid in self.nodes or nid in self.raw or nid in self.fresh_ids:
            self.err(f"{ctx}：「{nid}」与既有之名相撞")
            return False
        self.fresh_ids.add(nid)
        return True

    def known(self, k, ctx) -> dict | None:
        """知者 {in, tags, who, faction, item}：处所、人物、门派、文书须已登记；空的知者即天下皆知。"""
        if k is None:
            return None
        if not isinstance(k, dict) or set(k) - set(KNOWN_KEYS):
            self.err(f"{ctx}：知者须是 {{{', '.join(KNOWN_KEYS)}}}")
            return None
        for loc in k.get("in") or []:
            self.need(loc, ("location",), ctx + ".known.in")
        for who in k.get("who") or []:
            self.need(who, ("person",), ctx + ".known.who")
        for f in k.get("faction") or []:
            self.need(f, ("faction",), ctx + ".known.faction")
        if k.get("item"):
            self.need(k["item"], ("item",), ctx + ".known.item")
        out = {key: list(k[key]) if isinstance(k.get(key), list) else k[key] for key in KNOWN_KEYS if k.get(key)}
        return out or None


# ============================================================
#  19 处所：处所卡补到 01 的地点上，新处所入图，道路补丁与关口
# ============================================================
CARD = {"type": "form", "tier": "layer", "polity": "polity", "owner": "owner", "far": "far", "near": "vista",
        "bustle": "bustle", "order": "order", "hours": "hours"}


def _card(book: _Book, nid: str, row: dict, ctx: str):
    node = book.nodes[nid]
    if row.get("type") not in FORMS:
        book.err(f"{ctx}：形制「{row.get('type')}」不在第六节列出的类型之中")
    if row.get("tier") not in (1, 2, 3):
        book.err(f"{ctx}：层级须是 1/2/3")
    if row.get("bustle") not in BUSTLE or row.get("order") not in ORDER:
        book.err(f"{ctx}：人流与治安须取第六节列出的值")
    if row.get("hours") is not None and not HOURS.match(str(row["hours"])):
        book.err(f"{ctx}：开闭时辰写作「卯-酉」")
    book.need(row.get("polity"), ("faction",), ctx + ".polity")
    book.need(row.get("owner"), ("faction", "person"), ctx + ".owner")
    node.update({dst: row.get(src) for src, dst in CARD.items()})
    k = book.known(row.get("known"), ctx)
    if k:
        node["known"] = k


def _places(book: _Book, data: dict):
    out = book.out
    cards = {row.get("id"): row for row in data.get("cards") or []}
    for nid in [n for n, x in book.nodes.items() if x["type"] == "location"]:
        if nid not in cards:
            book.err(f"处所卡：01 的「{nid}」没有处所卡")
    for nid, row in cards.items():
        if book.need(nid, ("location",), "处所卡"):
            _card(book, nid, row, f"处所卡·{nid}")
    rows = [r for r in data.get("places") or [] if book.claim(r.get("id"), "新处所")]
    for row in rows:  # 先立后接：新处所的上级可以是另一个新处所
        book.nodes[row["id"]] = {"type": "location", "parent": row.get("parent"), "region": None, "desc": row.get("desc"),
                                 "lore": list(row.get("lore") or []), "state": row.get("state")}
    for row in rows:
        ctx = f"新处所·{row['id']}"
        if book.need(row.get("parent"), ("location",), ctx + ".parent"):
            book.nodes[row["id"]]["region"] = _region(book.nodes, row["parent"])
        _card(book, row["id"], row, ctx)
    roads = data.get("roads") or {}
    for key in ("remove", "add", "change"):
        out.roads[key] += [list(r) for r in roads.get(key) or []]
    for r in roads.get("add") or []:
        if not (isinstance(r, list) and len(r) in (3, 4) and _num(r[2]) and r[2] >= 0) or (len(r) == 3 and r[2] == 0):
            book.err(f"道路补丁「{r}」须写 [地点, 地点, 步行日数(, 里数)]，日数为 0 的须写里数")
    for row in data.get("gates") or []:
        out.gates.append((row.get("from"), row.get("to"), _gate(book, row, f"关口·{row.get('from')}→{row.get('to')}")))
    for row in data.get("gates_patch") or []:
        extra = {k: row[k] for k in ("key", "hours", "toll", "guard") if k in row}
        _gate_extra(book, extra, f"关口补丁·{row.get('from')}→{row.get('to')}")
        out.patches.append((row.get("from"), row.get("to"), extra))


def _region(nodes: dict, nid: str | None) -> str | None:
    """新处所的区域随上级：大理城·东街即大理城所在的区域。"""
    for _ in range(12):
        n = nodes.get(nid) or {}
        if n.get("region") or n.get("parent") is None:
            return n.get("region")
        nid = n["parent"]
    return None


def _gate_extra(book: _Book, gate: dict, ctx: str):
    """关口另可写的四项(6.4)：钥匙是器物(持有其中一件即过)、时辰写「卯-酉」、关钱是数、把守是人或人群。"""
    keys = gate.get("key") or []
    if not isinstance(keys, list):
        book.err(f"{ctx}：钥匙写成器物 id 的列表")
    else:
        for k in keys:
            book.need(k, ("item",), ctx + ".key")
    if gate.get("hours") is not None and not HOURS.match(str(gate["hours"])):
        book.err(f"{ctx}：时辰写作「卯-酉」")
    if gate.get("toll") is not None and not (_num(gate["toll"]) and gate["toll"] >= 0):
        book.err(f"{ctx}：关钱须是数")
    book.need(gate.get("guard"), ("person", GROUP), ctx + ".guard")


def _gate(book: _Book, row: dict, ctx: str) -> dict:
    gate = {k: row.get(k) for k in GATE}
    gate.update(blocked=bool(gate["blocked"]), hidden=bool(gate["hidden"]), requires=gate["requires"] or [],
                key=list(row.get("key") or []), hours=row.get("hours"), toll=row.get("toll"), guard=row.get("guard"))
    _gate_extra(book, gate, ctx)
    return gate


# ============================================================
#  21 货品、银钱、各地物价、原著器物补注
# ============================================================
GOODS = ("kind", "unit", "price", "grade", "desc", "split", "portable", "uses", "effect", "made", "rare", "tier")
GOODS_GRADES = ("下", "中", "上", "珍")
ITEM_GRADES = ("寻常", "器物", "要物")
CANON_ENRICH = ("grade", "props", "text", "secret", "qty", "unit", "cash", "purse", "split", "full", "pages", "uses", "doc", "torn", "spot",
                "price", "effect", "tier", "known")


def _goods(book: _Book, data: dict):
    atlas, table = book.out.atlas, {}
    for row in data.get("goods") or []:
        gid, ctx = row.get("id"), f"货品·{row.get('id')}"
        if not (isinstance(gid, str) and gid.startswith("货·")):
            book.err(f"{ctx}：货品 id 写作「货·名」")
            continue
        if gid in table:
            book.err(f"{ctx}：重复登记")
        if not (_num(row.get("price")) and row["price"] > 0) or row.get("grade") not in GOODS_GRADES:
            book.err(f"{ctx}：价钱须是正数、品级取 下/中/上/珍")
        if row.get("effect") is not None and not isinstance(row["effect"], dict):
            book.err(f"{ctx}：效用写成 {{名目: 数}}")
        table[gid] = {k: row.get(k) for k in GOODS}
    atlas["goods"] = table
    regions = []
    for row in data.get("regions") or []:
        ctx = f"各地物价·{row.get('at')}"
        book.need(row.get("at"), ("faction", "location"), ctx)
        factor = row.get("factor") or {}
        kinds = {g["kind"] for g in table.values()}
        for k, v in factor.items():
            if not (k in table or k in kinds) or not (_num(v) and v > 0):
                book.err(f"{ctx}：系数的键须是货类或货 id、值须是正数：「{k}」")
        regions.append({"at": row.get("at"), "factor": dict(factor)})
    atlas["regions"], atlas["money"] = regions, data.get("money") or {}
    for row in data.get("canon_items") or []:
        nid, ctx = row.get("id"), f"原著器物补注·{row.get('id')}"
        if not book.need(nid, ("item",), ctx):
            continue
        wrong = sorted(set(row) - set(CANON_ENRICH) - {"id", *META})
        if wrong:
            book.err(f"{ctx}：只可补注 {'/'.join(CANON_ENRICH)}，不改 {'、'.join(wrong)}")
        node = book.nodes[nid]
        extra = _strip(row, "id", "tier", "known", "effect")
        if row.get("grade", "器物") not in ITEM_GRADES:
            book.err(f"{ctx}：等级须是 {'/'.join(ITEM_GRADES)} 之一")
        if row.get("text") and row.get("grade") != "要物":
            book.err(f"{ctx}：只有要物才写内容(text)")
        if row.get("price") is not None and not (_num(row["price"]) and row["price"] >= 0):
            book.err(f"{ctx}：估值须是数")
        node.update(extra)
        if row.get("tier") is not None:
            node["layer"] = row["tier"]
        if isinstance(row.get("effect"), dict):
            if isinstance(node.get("effect"), str):
                node["effect_text"] = node["effect"]  # 05 的一句话说法留着，效用换成能接身体规则的数
            node["effect"] = dict(row["effect"])
        k = book.known(row.get("known"), ctx)
        if k:
            node["known"] = k
        if node.get("full") and "pages" not in node:
            node["pages"] = list(range(int(node.get("qty", node["full"])))) if _num(node.get("qty", node["full"])) else []
        if "pages" in node and isinstance(node["pages"], list):
            node["qty"] = len(node["pages"])


# ============================================================
#  20 场所：实例立为地点并接路；模板按 7.6 展开成近景(id 在此定下，主角走近时由 world/venue 布置)
# ============================================================
def _venues(book: _Book, data: dict, goods: dict, regions: list):
    out, types = book.out, data.get("types") or {}
    specs, used = {}, set()
    for v in data.get("venues") or []:
        vid, ctx = v.get("id"), f"场所·{v.get('id')}"
        tpl = types.get(v.get("type"))
        if tpl is None:
            book.err(f"{ctx}：模板「{v.get('type')}」没有登记")
            continue
        if v.get("size") not in SIZES:
            book.err(f"{ctx}：规模须是 小/中/大")
            continue
        if vid in specs:
            book.err(f"{ctx}：重复登记")
            continue
        old = book.kind(vid) == "location"
        if not old:
            if not book.claim(vid, ctx) or not book.need(v.get("in"), ("location",), ctx + ".in"):
                continue
            li = v.get("li", 0) or 0
            if not (_num(li) and li >= 0):
                book.err(f"{ctx}：里数须是数")
            book.nodes[vid] = {"type": "location", "parent": v["in"], "region": _region(book.nodes, v["in"]),
                               "desc": v.get("desc") or tpl.get("desc"), "lore": [], "state": None,
                               "form": "场所", "polity": _polity(book.nodes, v["in"]), "order": book.nodes[v["in"]].get("order")}
            out.roads["add"].append([v["in"], vid, 0, li] if li else [v["in"], vid, 0])
        node = book.nodes[vid]
        node.update(venue=v["type"], size=v["size"], sign=v.get("sign"), pricing=v.get("price", 1.0) or 1.0,
                    layer=node.get("layer") or v.get("tier") or tpl.get("tier"),
                    vista=node.get("vista") or v.get("near"), far=node.get("far") or v.get("far"),
                    bustle=v.get("bustle") or node.get("bustle") or tpl.get("bustle"),
                    hours=v.get("hours") or node.get("hours") or tpl.get("hours"))
        if v.get("owner"):
            book.need(v["owner"], ("person", "faction"), ctx + ".owner")
            node["owner"] = v["owner"]
        k = book.known(v.get("known"), ctx)
        if k:
            node["known"] = k
        specs[vid] = _expand(book, vid, v, tpl, goods, _factors(book.nodes, vid, regions), used)
    return specs


def _polity(nodes: dict, nid) -> str | None:
    for _ in range(12):
        n = nodes.get(nid) or {}
        if n.get("polity"):
            return n["polity"]
        if n.get("parent") is None:
            return None
        nid = n["parent"]
    return None


def _factors(nodes: dict, vid: str, regions: list) -> dict:
    """各地物价(8.3)：所属之国的系数，再由近处(城镇、区域)的盖过远处的。"""
    chain, nid = [], vid
    for _ in range(12):
        if nid is None:
            break
        chain.append(nid)
        nid = (nodes.get(nid) or {}).get("parent")
    chain.append(_polity(nodes, vid))
    out = {}
    for at in reversed(chain):  # 远的先铺，近的后盖
        for r in regions:
            if r["at"] == at:
                out.update(r["factor"])
    return out


def _named(items: list, key: str, drop: set) -> list:
    return [dict(x) for x in items if isinstance(x, dict) and x.get(key) not in drop]


def _expand(book: _Book, vid: str, v: dict, tpl: dict, goods: dict, factor: dict, used: set) -> dict:
    """一处场所的近景(7.6)：模板减去 drop、加上 add；房间「场所·房间名」(几间同样的编号)，景物与器物「场所·名」，伙计「场所·职名」(同职几人编号)，
    伙计身上的东西「伙计·名」，货「场所·货名」，柜银「场所·柜银」；与 01 已有的子地点同名的房间即用已有的。规模定伙计人数、存货与柜银。"""
    ctx, size = f"场所·{vid}", SIZES[v["size"]]
    add, drop = v.get("add") or {}, set(v.get("drop") or [])
    known_names = {x.get("name") for part in ("rooms", "features", "items", "services") for x in tpl.get(part) or []} \
        | {x.get("role") for x in tpl.get("staff") or []} | {x.get("goods") for x in tpl.get("goods") or []} \
        | {x.get("job") for x in tpl.get("jobs") or []}
    for d in drop:
        if d not in known_names:
            book.err(f"{ctx}：drop「{d}」在模板「{v['type']}」里查不到")

    def fresh(nid, what) -> bool:
        if nid in used or nid in book.nodes or nid in book.raw:
            book.err(f"{ctx}：{what}「{nid}」与既有之名相撞")
            return False
        used.add(nid)
        return True

    rooms, by_room = [], {}
    for r in _named(tpl.get("rooms") or [], "name", drop) + [dict(x) for x in add.get("rooms") or []]:
        n = int(r.get("count") or 1)
        names = [r["name"]] if n == 1 else [f"{r['name']}{nth(i)}" for i in range(1, n + 1)]
        for name in names:
            rid = f"{vid}·{name}"
            reuse = book.kind(rid) == "location"  # 镇南王府·书房：01 已有的子地点即用已有的
            if not reuse and not fresh(rid, "房间"):
                continue
            rooms.append({"id": rid, "name": name, "desc": r.get("desc"), "layer": r.get("tier", 3), "li": r.get("li", 0) or 0,
                          "gate": r.get("gate"), "reuse": reuse})
            by_room.setdefault(r["name"], rid)
            by_room.setdefault(name, rid)

    def room(name, what) -> str | None:
        if name is None:
            return rooms[0]["id"] if rooms else vid
        if name in by_room:
            return by_room[name]
        book.err(f"{ctx}：{what}所在的「{name}」不是这处场所的房间")
        return None

    features = []
    for f in _named(tpl.get("features") or [], "name", drop) + [dict(x) for x in add.get("features") or []]:
        fid = f"{vid}·{f['name']}"
        if fresh(fid, "景物"):
            features.append({"id": fid, "type": "feature", "location": room(f.get("in"), f"景物「{f['name']}」"), "desc": f.get("desc"),
                             "state": f.get("state"), "hidden": bool(f.get("hidden")), "layer": f.get("tier", 3)})
    items = []
    for x in _named(tpl.get("items") or [], "name", drop) + [dict(x) for x in add.get("items") or []]:
        iid = f"{vid}·{x['name']}"
        if fresh(iid, "器物"):
            items.append(_item(book, iid, x, location=room(x.get("in"), f"器物「{x['name']}」"), ctx=ctx))

    staff, roles = [], {}
    extra = [(dict(x), int(x.get("count") or 1)) for x in add.get("staff") or []]
    rows = []
    for s in _named(tpl.get("staff") or [], "role", drop):  # 规模定人数(每职至少一人)；原著写了的伙计替下模板里同职的一人
        n = max(1, round(int(s.get("count") or 1) * size))
        rows.append((s, n - min(n, sum(k for e, k in extra if e.get("role") == s.get("role")))))
    total, seen = {}, {}
    for s, n in rows + extra:
        total[s.get("role")] = total.get(s.get("role"), 0) + n
    for s, n in rows + extra:
        role = s.get("role")
        for _ in range(n):
            seen[role] = seen.get(role, 0) + 1
            pid = f"{vid}·{role}" if total[role] == 1 else f"{vid}·{role}{nth(seen[role])}"
            if not fresh(pid, "伙计"):
                continue
            node = _staff(book, pid, s, room(s.get("in"), f"伙计「{role}」"), ctx)
            node["items"] = [_item(book, f"{pid}·{x['name']}", x, holder=pid, ctx=ctx) for x in s.get("items") or []
                             if fresh(f"{pid}·{x['name']}", "伙计随身之物")]
            staff.append(node)
            roles.setdefault(role, []).append(pid)

    def key_of(name) -> list:
        """房门的钥匙(模板里写名字)：场所里的器物「场所·名」，或伙计身上的「伙计·名」。"""
        hits = [i["id"] for i in items if i["id"] == f"{vid}·{name}"] + \
               [i["id"] for s in staff for i in s["items"] if i["id"].endswith(f"·{name}")]
        if name and not hits:
            book.err(f"{ctx}：房门钥匙「{name}」不是这处场所的器物")
        return hits[:1]
    for r in rooms:
        g = r.pop("gate")
        if g and not r["reuse"]:
            guard = roles.get(g.get("guard"), [None])[0] if g.get("guard") else None
            if g.get("guard") and guard is None:
                book.err(f"{ctx}：房门把守「{g['guard']}」不是这处场所的职名")
            r["gate"] = {"kind": g.get("kind") or "门禁", "blocked": bool(g.get("blocked")), "hidden": bool(g.get("hidden")), "how": g.get("how"),
                         "requires": [], "risk": g.get("risk"), "key": key_of(g["key"]) if g.get("key") else [],
                         "hours": g.get("hours"), "toll": g.get("toll"), "guard": guard}
        else:
            r["gate"] = None

    wares = {}
    adds = {x.get("goods"): dict(x) for x in add.get("goods") or []}
    for x in _named(tpl.get("goods") or [], "goods", drop) + list(adds.values()):
        gid = x.get("goods")
        if x is not adds.get(gid) and gid in adds:
            continue
        item = goods.get(gid)
        if item is None:
            book.err(f"{ctx}：货「{gid}」不在货品目录里")
            continue
        price = x.get("price")
        price = round((price if _num(price) else item["price"] * factor.get(gid, factor.get(item["kind"], 1.0))) * v.get("price", 1.0), 4)
        stock = x.get("stock")
        stock = None if stock is None else max(1, round(stock * size))
        wares[gid] = {"id": f"{vid}·{gid[2:]}", "price": price, "stock": stock, "full": stock,
                      "restock": bool(x.get("restock")), "in": room(x.get("in"), f"货「{gid}」")}
    services = []
    for x in _named(tpl.get("services") or [], "name", drop) + [dict(x) for x in add.get("services") or []]:
        if x.get("by") not in roles:
            book.err(f"{ctx}：服务「{x.get('name')}」由「{x.get('by')}」办，这处场所没有这个职名")
            continue
        services.append({"name": x.get("name"), "by": list(roles[x["by"]]), "role": x["by"],
                         "price": round((x.get("price") or 0) * v.get("price", 1.0), 4), "per": x.get("per"), "time": x.get("time"),
                         "room": room(x["room"], f"服务「{x.get('name')}」") if x.get("room") else None,
                         "need": x.get("need"), "effect": x.get("effect")})
    jobs = [_strip(x) for x in _named(tpl.get("jobs") or [], "job", drop) + [dict(x) for x in add.get("jobs") or []]]
    till = round((tpl.get("till") or 0) * size, 3)
    counter = next((f["location"] for f in features if f["id"].endswith("·柜台")), None) or by_room.get("库房") or (rooms[0]["id"] if rooms else vid)
    cash = None
    if till > 0 and fresh(f"{vid}·柜银", "柜银"):
        cash = {"id": f"{vid}·柜银", "type": "item", "kind": "杂物", "grade": "器物", "desc": "柜上收着的碎银", "cash": True, "qty": till,
                "unit": "两", "split": True, "location": counter, "holder": None, "hidden": False, "hint": None, "grants": None, "effect": None,
                "state": {"exists": True, "available": True}, "layer": 3, "spot": "柜上"}
    return {"type": v["type"], "rooms": rooms, "features": features, "items": items, "staff": staff, "wares": wares,
            "services": services, "jobs": jobs, "till": cash}


ITEM_KEYS = ("grade", "kind", "desc", "hidden", "hint", "spot", "props", "text", "secret", "qty", "unit", "split", "uses", "doc",
             "price", "cash", "purse", "full", "pages", "torn")


def _item(book: _Book, iid: str, row: dict, location=None, holder=None, ctx="") -> dict:
    """一件器物入世(格式同 18)：寻常只有名字，器物与要物须有描述；有数的写数；层级缺省三层。"""
    node = {"id": iid, "type": "item", "kind": "杂物", "desc": None, "location": location, "holder": holder, "hidden": False, "hint": None,
            "grants": None, "effect": None, "state": {"exists": True, "available": True}}
    node.update({k: row[k] for k in ITEM_KEYS if k in row})
    node["hidden"], node["layer"] = bool(node["hidden"]), row.get("tier", 3)
    if isinstance(row.get("effect"), dict):
        node["effect"] = dict(row["effect"])
    if node.get("grade") not in ITEM_GRADES:
        book.err(f"{ctx}：器物「{iid}」的等级须是 {'/'.join(ITEM_GRADES)} 之一")
    elif node["grade"] != "寻常" and not node.get("desc"):
        book.err(f"{ctx}：{node['grade']}「{iid}」须有描述")
    if "qty" in node and not (_num(node["qty"]) and node["qty"] > 0):
        book.err(f"{ctx}：器物「{iid}」的数量须是正数")
    if node.get("full") and "pages" not in node:
        node["pages"] = list(range(int(node.get("qty", node["full"]))))
    if "pages" in node:
        node["qty"] = len(node["pages"])
    k = book.known(row.get("known"), f"{ctx}·{iid}")
    if k:
        node["known"] = k
    return node


STAFF = ("gender", "age", "power", "money", "persona", "speech", "appearance", "hours", "services", "knows")


def _staff(book: _Book, pid: str, row: dict, location, ctx: str) -> dict:
    """一名伙计(功能性人物)：只有职名与叫法，不起姓名；功力、零钱、识字、当值时辰、能办的事、知道哪类消息。"""
    if not (_num(row.get("power")) and 0 <= row["power"] <= 100) or not (_num(row.get("money", 0)) and row.get("money", 0) >= 0):
        book.err(f"{ctx}：伙计「{pid}」的功力与零钱须是数")
    if row.get("hours") is not None and not HOURS.match(str(row["hours"])):
        book.err(f"{ctx}：伙计「{pid}」的当值时辰写作「卯-酉」")
    gender = row.get("gender")
    node = {"id": pid, "type": "person", "title": row.get("role"), "role": row.get("role"), "faction": None, "status": "alive",
            "location": location, "hidden": False, "skills": [], "agenda": None, "staff": True, "layer": row.get("tier", 3),
            **{k: row.get(k) for k in STAFF}, "gender": gender if gender in ("男", "女") else None}
    node["power"], node["money"] = int(row.get("power") or 0), round(float(row.get("money") or 0), 3)
    node["tags"] = list(node.pop("knows") or [])  # 伙计知道哪类消息(消息 known.tags 的同一套标签)
    if row.get("literate") is False:
        node["illiterate"] = True
    return node


# ============================================================
#  22 有名之人：补注、随身之物、新关系
# ============================================================
PEOPLE = {"tier": "layer", "fame": "fame", "tongues": "tongues", "home": "home", "haunts": "haunts", "routine": "routine",
          "services": "services", "knows": "tells", "likes": "likes", "dislikes": "dislikes", "soft": "soft", "assets": "assets",
          "drive": "drive", "drive_basis": "drive_basis", "goal": "goal", "wishes": "wishes", "means": "means", "limits": "limits",
          "arc": "arc", "since": "since"}


def _people(book: _Book, data: dict, lore: set, canon: set):
    rows = {row.get("id"): row for row in data.get("named") or []}
    for nid in [n for n, x in book.nodes.items() if x["type"] == "person"]:
        if nid not in rows:
            book.err(f"人物补注：04 的「{nid}」没有补注")
    carried = []
    for pid, row in rows.items():
        ctx = f"人物补注·{pid}"
        if not book.need(pid, ("person",), ctx):
            continue
        node = book.nodes[pid]
        if not (_num(row.get("money")) and row["money"] >= 0):
            book.err(f"{ctx}：零钱须是数")
        else:
            node["money"] = round(float(row["money"]), 3)
        if row.get("literate") is False:
            node["illiterate"] = True
        drive = row.get("drive")
        if drive is not None and not (isinstance(drive, int) and 0 <= drive <= DRIVE_MAX):
            book.err(f"{ctx}：剧情推力须是 0~{DRIVE_MAX} 的整数")
        for loc in [row.get("home"), *(row.get("haunts") or []), *(row.get("assets") or [])]:
            book.need(loc, ("location",), ctx + ".居所/常去之处/产业")
        for t in row.get("knows") or []:
            if t not in lore:
                book.err(f"{ctx}：知道的消息「{t}」不在 25 里")
        for s in row.get("services") or []:
            if s.get("skill"):
                book.need(s["skill"], ("skill",), ctx + ".services.skill")
        wishes = row.get("wishes") or []
        if len(wishes) > 3:
            book.err(f"{ctx}：心愿至多三条")
        for w in wishes:
            book.need(w.get("target"), ("person", "item", "location", "faction"), ctx + ".wishes.target")
            for cond in w.get("done_when") or []:
                if not (isinstance(cond, list) and len(cond) == 3 and isinstance(cond[1], str)):
                    book.err(f"{ctx}：了结条件「{cond}」须是 [id, 键, 值]")
                else:
                    book.need(cond[0], ("person", "item", "location", "faction"), ctx + ".wishes.done_when")
        if row.get("since") is not None and row["since"] not in canon:
            book.err(f"{ctx}：出没时段 since「{row['since']}」不是原著事件")
        node.update({dst: row[src] for src, dst in PEOPLE.items() if src in row and row[src] is not None})
        if "wishes" in node:
            node["wishes"] = [{k: w[k] for k in ("wish", "target", "done_when", "then") if w.get(k) is not None} for w in node["wishes"]]
        for x in row.get("carry") or []:
            if book.claim(x.get("id"), ctx + "·随身之物"):
                if x.get("holder", pid) != pid or x.get("location"):
                    book.err(f"{ctx}：随身之物「{x['id']}」的着落即此人")
                carried.append(_item(book, x["id"], x, holder=pid, ctx=ctx))
    for node in carried:
        book.nodes[node.pop("id")] = node
    for r in data.get("relations") or []:
        if book.need(r.get("src"), ("person", "faction"), "新关系") and book.need(r.get("dst"), ("person", "faction"), "新关系"):
            book.out.relations.append({k: r[k] for k in ("src", "dst", "rel", "secret", "revealed_by") if k in r})


# ============================================================
#  23 门派：补注、新势力、门下模板(一派几套)、人群
# ============================================================
FACTION = ("fame", "goal", "drive", "seats", "sphere", "ranks", "rules", "tokens", "allies", "foes", "outsiders", "join", "teach",
           "livelihood", "forbidden")


def _faction_fields(book: _Book, node: dict, row: dict, ctx: str):
    if row.get("drive") is not None and not (isinstance(row["drive"], int) and 0 <= row["drive"] <= DRIVE_MAX):
        book.err(f"{ctx}：推力须是 0~{DRIVE_MAX} 的整数")
    for s in row.get("seats") or []:
        book.need(s.get("at"), ("location",), ctx + ".seats")
    for loc in [*(row.get("sphere") or []), *(row.get("forbidden") or [])]:
        book.need(loc, ("location",), ctx + ".sphere/forbidden")
    for t in row.get("tokens") or []:
        book.need(t, ("item",), ctx + ".tokens")
    for x in [*(row.get("allies") or []), *(row.get("foes") or [])]:
        book.need(x.get("id"), ("faction",), ctx + ".allies/foes")
    for t in row.get("teach") or []:
        book.need(t.get("skill"), ("skill",), ctx + ".teach")
    node.update({k: row[k] for k in FACTION if k in row})
    node["layer"] = row.get("tier", node.get("layer"))


def _kit(book: _Book, row: dict, ctx: str) -> dict | None:
    items, money, power = row.get("items") or [], row.get("money", 0), row.get("power", 15)
    names = [t.get("name") for t in items if isinstance(t, dict)]
    if not (isinstance(power, int) and 0 <= power <= 100) or not (_num(money) and money >= 0):
        book.err(f"{ctx}：每人的功力与零钱须是数")
        return None
    if len(names) != len(items) or not all(isinstance(n, str) and n for n in names) or len(set(names)) != len(names):
        book.err(f"{ctx}：身上的东西须各有不同的名字")
        return None
    return {"money": money, "items": [dict(t) for t in items]}


def _factions(book: _Book, data: dict, canon: set):
    for row in data.get("new") or []:  # 原著成群出现而 03 没登记的势力(聚贤庄游氏、泰山单家)
        if book.claim(row.get("id"), "新势力"):
            book.nodes[row["id"]] = {"type": "faction", "desc": row.get("desc"), "base": row.get("base"), "leader": row.get("leader"),
                                     "state": row.get("state") or {"leader": row.get("leader")}}
    for row in data.get("new") or []:
        if book.kind(row.get("id")) == "faction":
            ctx = f"新势力·{row['id']}"
            book.need(row.get("base"), ("location",), ctx + ".base")
            book.need(row.get("leader"), ("person",), ctx + ".leader")
            _faction_fields(book, book.nodes[row["id"]], row, ctx)
    rows = {row.get("id"): row for row in data.get("factions") or []}
    for nid in [n for n, x in book.nodes.items() if x["type"] == "faction" and n not in {r.get("id") for r in data.get("new") or []}]:
        if nid not in rows:
            book.err(f"门派补注：03 的「{nid}」没有补注")
    for fid, row in rows.items():
        if book.need(fid, ("faction",), "门派补注"):
            _faction_fields(book, book.nodes[fid], row, f"门派补注·{fid}")
    for row in data.get("kits") or []:  # 一派可有几套：写在最前的一套是缺省
        fid, ctx = row.get("faction"), f"门下模板·{row.get('faction')}·{row.get('handle')}"
        if not book.need(fid, ("faction",), ctx):
            continue
        kit = _kit(book, row, ctx)
        if kit is None:
            continue
        if row.get("at") is not None and row["at"] not in FORMS:  # 出没的处所，或处所的形制(捕快在州城县城)
            book.need(row["at"], ("location",), ctx + ".at")
        entry = {"handle": row.get("handle") or f"{fid}门人", "power": row.get("power", 15), **kit, "desc": row.get("desc"),
                 "at": row.get("at"), **({"illiterate": True} if row.get("literate") is False else {})}
        node = book.nodes[fid]
        node.setdefault("squad_kits", []).append(entry)
        node.setdefault("squad_kit", entry)


def _squads(book: _Book, data: dict, canon: set):
    for row in data.get("squads") or []:
        if book.claim(row.get("id"), "人群"):
            book.nodes[row["id"]] = _squad(book, row, canon)


def _squad(book: _Book, row: dict, canon: set) -> dict:
    """一群无名之众(10.4，v9 的形状)：没写 kit 即用这一门的缺省门下模板；人数三到三百；出没时段是原著事件。"""
    ctx = f"人群·{row['id']}"
    book.need(row.get("faction"), ("faction",), ctx + ".faction")
    book.need(row.get("location"), ("location",), ctx + ".location")
    book.need(row.get("leader"), ("person",), ctx + ".leader")
    for k in ("since", "until"):
        if row.get(k) is not None and row[k] not in canon:
            book.err(f"{ctx}.{k}：「{row[k]}」不是原著事件")
    template = book.nodes.get(row.get("faction"), {}).get("squad_kit") or {}
    kit = row.get("kit") or ({"money": template.get("money", 0), "items": template.get("items") or []} if template else {"money": 0, "items": []})
    count, power = row.get("count"), row.get("power", template.get("power", 15))
    if not (isinstance(count, int) and DISBAND <= count <= CROWD_MAX):
        book.err(f"{ctx}：人数须在{DISBAND}到{CROWD_MAX}之间")
        count = DISBAND
    kit = _kit(book, {**kit, "power": power}, ctx) or {"money": 0, "items": []}
    pool = {"银两": round(count * kit["money"], 3), **{t["name"]: count for t in kit["items"]}}
    return {"type": GROUP, "faction": row.get("faction"), "location": row.get("location"), "count": count, "down": 0, "dead": 0,
            "power": power, "handle": row.get("handle") or template.get("handle") or row["id"], "desc": row.get("desc") or template.get("desc"),
            "hidden": False, "status": "alive", "kit": kit, "pool": pool, "layer": row.get("tier", 2),
            **{k: row[k] for k in ("leader", "since", "until") if row.get(k)}}


# ============================================================
#  24~27：国法与规矩、消息、风物、剧情线——静态的表，进 atlas
# ============================================================
def _laws(book: _Book, data: dict, kits: set, canon: set):
    polities = {}
    for row in data.get("polities") or []:
        pid, ctx = row.get("id"), f"国法·{row.get('id')}"
        if not book.need(pid, ("faction",), ctx):
            continue
        for o in row.get("officers") or []:
            if o.get("kit") not in kits:
                book.err(f"{ctx}：官差「{o.get('role')}」的门下模板「{o.get('kit')}」不在 23 里")
        for b in row.get("borders") or []:
            book.need(b.get("at"), ("location",), ctx + ".borders")
        for p in row.get("prisons") or []:
            book.need(p, ("location",), ctx + ".prisons")
        book.need(row.get("capital"), ("location",), ctx + ".capital")
        book.need(row.get("ruler"), ("person",), ctx + ".ruler")
        polities[pid] = _strip(row)
    rules = {}
    for row in data.get("jianghu") or []:
        if not str(row.get("id") or "").startswith("规·"):
            book.err(f"江湖规矩：id 写作「规·简述」：「{row.get('id')}」")
        who = row.get("who")
        for f in (who if isinstance(who, list) else []):
            book.need(f, ("faction",), f"江湖规矩·{row.get('id')}.who")
        rules[row.get("id")] = _strip(row)
    precepts = {}
    for row in data.get("precepts") or []:
        if not str(row.get("id") or "").startswith("准·"):
            book.err(f"天龙准则：id 写作「准·简述」：「{row.get('id')}」")
        for e in row.get("examples") or []:
            if e not in canon:
                book.err(f"天龙准则·{row.get('id')}：例子「{e}」不是原著事件")
        precepts[row.get("id")] = _strip(row)
    book.out.atlas.update(polities=polities, rules=rules, precepts=precepts)


def _lore(book: _Book, data: dict, canon: set, types: set):
    table = {}
    for row in data.get("lore") or []:
        lid, ctx = row.get("id"), f"消息·{row.get('id')}"
        if not str(lid or "").startswith("闻·") or lid in table:
            book.err(f"{ctx}：id 写作「闻·简述」且不得重复")
            continue
        if row.get("kind") not in LORE_KINDS:
            book.err(f"{ctx}：类别须是 {'/'.join(sorted(LORE_KINDS))} 之一")
        known = row.get("known") or {}
        if not any(known.get(k) for k in KNOWN_KEYS) and known.get("in") is not None:
            book.err(f"{ctx}：知者至少写一条")
        k = book.known({**known, "in": known.get("in") or []}, ctx) or {}
        if row.get("true") is not True and not row.get("truth"):
            book.err(f"{ctx}：不真的消息须写真相 truth")
        for gt in row.get("get") or []:
            at = gt.get("at")
            if at not in types and book.kind(at) != "location":
                book.err(f"{ctx}：打听之处「{at}」既不是场所类型也不是处所")
            if gt.get("price") is not None and not (_num(gt["price"]) and gt["price"] >= 0):
                book.err(f"{ctx}：打听的价钱须是数")
        for x in row.get("about") or []:
            if x not in book.nodes and x not in canon:  # 风声关联的可以是原著事件
                book.err(f"{ctx}：关联的「{x}」不是已登记的实体或原著事件")
        for key in ("since", "until"):
            if row.get(key) is not None and row[key] not in canon:
                book.err(f"{ctx}.{key}：「{row[key]}」不是原著事件")
        entry = _strip(row, "known")
        entry["known"] = k  # 空的知者即天下皆知(in 为 null)
        table[lid] = entry
    book.out.atlas["lore"] = table


def _nature(book: _Book, data: dict, goods: dict, roads: set):
    for row in data.get("products") or []:
        ctx = f"物产·{row.get('what')}"
        if row.get("what") not in goods and book.kind(row.get("what")) != "item":
            book.err(f"{ctx}：产出须是货 id 或原著器物")
        for at in row.get("at") or []:
            book.need(at, ("location", "faction"), ctx + ".at")
    for row in data.get("hazards") or []:
        if not str(row.get("id") or "").startswith("险·"):
            book.err(f"险地：id 写作「险·简述」：「{row.get('id')}」")
        for at in row.get("at") or []:
            book.need(at, ("location",), f"险地·{row.get('id')}.at")
    for row in data.get("climate") or []:
        book.need(row.get("at"), ("location", "faction"), f"气候·{row.get('at')}")
    for row in data.get("seasonal_roads") or []:
        r = row.get("road") or []
        if not (len(r) == 2 and frozenset(r) in roads):
            book.err(f"季节路况：「{r}」不是已有的路")
    for row in data.get("festivals") or []:
        for at in row.get("at") or []:
            book.need(at, ("location",), f"节令·{row.get('name')}.at")
    for row in data.get("markets") or []:
        book.need(row.get("at"), ("location",), "集期")
    book.out.atlas["nature"] = {k: [_strip(r) for r in data.get(k) or []] for k in
                                ("products", "hazards", "climate", "seasonal_roads", "festivals", "markets")}
    book.out.atlas["nature"]["routine"] = dict(data.get("routine") or {})


def _lines(book: _Book, data: dict, canon: dict):
    lines = {}
    for row in data.get("lines") or []:
        lid, ctx = row.get("id"), f"剧情线·{row.get('id')}"
        if not str(lid or "").startswith("线·") or lid in lines:
            book.err(f"{ctx}：id 写作「线·名」且不得重复")
            continue
        for o in row.get("owners") or []:
            book.need(o, ("person", "faction"), ctx + ".owners")
        events = row.get("events") or []
        for e in events:
            if e not in canon:
                book.err(f"{ctx}：事件「{e}」不是原著事件")
        lines[lid] = {**_strip(row), "events": sorted((e for e in events if e in canon), key=lambda e: canon[e])}
    notes = {}
    for row in data.get("events") or []:
        eid, ctx = row.get("id"), f"事件注·{row.get('id')}"
        if eid not in canon:
            book.err(f"{ctx}：不是原著事件")
            continue
        if row.get("line") not in lines or row.get("role") not in ROLES:
            book.err(f"{ctx}：line 须是 27 的剧情线、role 取 {'/'.join(ROLES)}")
        notes[eid] = _strip(row, "id")
    for eid in canon:
        if eid not in notes:
            book.err(f"事件注：原著事件「{eid}」没有注")
    book.out.atlas.update(lines=lines, notes=notes)


# ============================================================
#  入口：先立处所，再展开场所，再落货品、人物、门派人群，最后是表
# ============================================================
def found(root: Path, nodes: dict, raw_aliases: dict, canon: list[dict], roads: set) -> Founding:
    """世界底座就地并入节点(01~06 已立)：错一处记一条，genesis 汇总后拒绝开局。roads 是 02 打完 15/16 补丁之后的路(季节路况要落在路上)。"""
    out = Founding()
    if not (root / FILES[0]).exists():  # 没有世界底座的数据(旧数据、测试注入)：照 v10 开局
        return out
    book = _Book(nodes, raw_aliases, out)
    data = {name: _read(root, name) or {} for name in FILES}
    events = {ev["id"]: ev["order"] for ev in canon}
    _places(book, data["19_places.json"])
    _goods(book, data["21_goods.json"])
    _factions(book, data["23_factions.json"], set(events))  # 门派先于场所：场所的主人、国法的官差要认得门派与门下模板
    lore_ids = {row.get("id") for row in data["25_lore.json"].get("lore") or []}
    out.atlas["venues"] = _venues(book, data["20_venues.json"], out.atlas["goods"], out.atlas["regions"])
    out.atlas["services"] = sorted({s["name"] for sp in out.atlas["venues"].values() for s in sp["services"]})  # 服务名即事码(住宿、打尖、诊治……)
    _people(book, data["22_people.json"], lore_ids, set(events))
    _squads(book, data["23_factions.json"], set(events))  # 人群在场所之后：人群可以守在新立的场所里
    kits = {k["handle"] for n in nodes.values() if n["type"] == "faction" for k in n.get("squad_kits") or []}
    _laws(book, data["24_laws.json"], kits, set(events))
    _lore(book, data["25_lore.json"], set(events), set((data["20_venues.json"].get("types") or {})))
    added = {frozenset(r[:2]) for r in out.roads["add"]}
    _nature(book, data["26_nature.json"], out.atlas["goods"], roads | added)
    _lines(book, data["27_lines.json"], events)
    return out
