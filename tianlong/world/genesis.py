"""
[INPUT]: 读取 data/canon/*.json（外部抽取的原著硬知识，格式见 data/EXTRACT_PROMPT.md 与 data/ACCESS_PROMPT.md；场景清单 18_scenes.json 见 data/WORLD_PROMPT.md 第十四节；19~26 世界底座为 v11 草案，尚未编译），依赖 world/clock 的 day_of / PER_DAY / PER_SHICHEN、world/graph 的 PLIGHT、world/crowd 的 GROUP / DISBAND（v9 人群）
[OUTPUT]: 对外提供 load()（编译出 World 可直接加载的创世字典：nodes/roads/gates/relations/canon/aliases/player/start_tick/seed）、GenesisError、DATA、SCENES、GRADES
[POS]: world 层的创世导入器——原著硬知识进入基础设施的唯一入口：裁剪抽取元数据、排定原著日程、
       处理开端未明的人物（休眠）、开局带伤者记下剧情上的伤(PLIGHT)、标出片区(area：下辖子地点或以自身为区域的大地名，同在片区不等于同处一室)、道路补丁(15 修伪捷径、16 补走廊)依次先删再加再改且须与原路严丝合缝、路程按骑马换算(PACE)、有向通行条件(14)编译为关口、
       按章成簇排定日程、编译别名表、保留隐情的揭示事件(revealed_by)、并入情境前提(17：某人仍受制于人)、校验全部 id 引用；任何错误都在开局前失败，绝不带病入世；
       v8 场景清单(18)：一处场景的建筑(地点，parent 落在场景之内；道路以补丁口径接在 15/16 之后)、景物(type=feature，不可携带)、
       分三等的器物(寻常只有名字、器物带属性 props、要物另有内容 text 与底细 secret，方位 spot)在创世时布齐，新 id 不得与书中之名及别名相撞——剧情只调度、不新造
       v9 物量与人群：器物另可写 qty/unit(碎银 cash 以两计；可分的写 split)、purse(钱袋里几两)、full/pages(全本几份、所存几份)、uses(书写、纸)、doc(文书的状态)，形状错即拒绝开局(_stock_errors)；
       squads 编入无名之众(type=group)：须属已登记的门派、在场景之内、人数三到二百、每人的功力与零钱是数、身上之物各有不同的名字，pool 按人头算好总数(_squad)
       v10 场景清单的顶层段落(v11 草案 data/WORLD_PROMPT.md 改归 23/22/21/22，此处仍认 v10 写法)：门下模板 kits 挂到门派节点(squad_kit)、人物零钱 money、原著器物补注 canon_items(只补 ENRICH 的字段)、不识字 illiterate；
       人群没写 kit 即用门下模板，leader/since/until 在 _validate 里核对；文书状态 doc 只取三态、残片 torn 须写全本几份
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from .clock import DAYS_PER_MONTH, PER_DAY, PER_SHICHEN, day_of
from .crowd import DISBAND, GROUP
from .graph import PLIGHT

DATA = Path(__file__).resolve().parents[2] / "data" / "canon"
START_MINUTE = 4 * PER_SHICHEN  # 开场于辰时
PACE = 60 / 100    # 原始路程按步行(日行六十里)估算；江湖人多骑马(日行百里)，入世时统一换算


def _ride(days: int) -> int:
    """步行日数 → 骑马日数；同处(0日)仍为 0，异地至少 1 日。"""
    return 0 if days == 0 else max(1, round(days * PACE))

# ============================================================
#  各类实体保留的字段——src / inferred / *_basis 等抽取元数据不进入世界
# ============================================================
SOURCES = {
    "location": ("01_locations.json", ("parent", "region", "desc", "lore", "state")),
    "faction": ("03_factions.json", ("desc", "base", "leader", "state")),
    "person": ("04_persons.json", ("gender", "age", "title", "faction", "status", "location", "hidden", "power",
                                   "skills", "persona", "appearance", "speech", "agenda", "secret_fields")),
    "item": ("05_items.json", ("kind", "desc", "location", "holder", "hidden", "hint", "grants", "grants_extra",
                               "effect", "state")),
    "skill": ("06_skills.json", ("school", "type", "tier", "desc", "requires")),
}
RENAME = {"type": "style"}  # 武学自带的 type(掌法/指法…) 与节点类型同名，入世时改称 style
GATE = ("kind", "blocked", "hidden", "how", "requires", "risk")  # 通行条件入世的字段；src/inferred 是抽取元数据
ROAD_PATCHES = ("15_roads_patch.json", "16_roads_fill.json")
SITUATION = "17_situation.json"  # 原著事件的情境前提补充（某人仍受制于人），合并进 requires  # 依次各打一次：15 修 0 日中枢的伪捷径，16 据既有数据补缺失的走廊
SCENES = "18_scenes.json"  # 场景清单(v8 布景)：建筑、景物、分级器物——世界生成时一次布齐，剧情只调度、不新造
GRADES = ("寻常", "器物", "要物")  # 器物的详略：寻常只有名字；器物带几样简单属性；要物详写(文书另有内容 text 与底细 secret)
DRESSED = ("grade", "kind", "desc", "location", "holder", "hidden", "hint", "spot", "props", "text", "secret", "effect",
           "qty", "unit", "cash", "purse", "split", "full", "pages", "uses", "doc", "torn")  # 布景器物入世的字段；v9 数量、银两、钱袋、可分、全本几份(所存哪几份)、用途、文书状态、撕开的残片
ENRICH = ("grade", "props", "text", "secret", "qty", "unit", "cash", "purse", "split", "full", "pages", "uses", "doc", "torn", "spot")  # v10 原著器物(05)可补注的字段：着落与持有归原著，不在此改
DOC_STATES = ("写成", "封缄", "拆封")  # 文书的状态(与 world/scribe 同一张表)


class GenesisError(Exception):
    pass


def _read(root: Path, name: str):
    return json.loads((root / name).read_text("utf-8"))


def _nodes(root: Path) -> dict[str, dict]:
    nodes = {}
    for kind, (name, keep) in SOURCES.items():
        for row in _read(root, name):
            node = {"type": kind, **{RENAME.get(k, k): row[k] for k in keep if k in row}}
            if row.get("initial_state_confirmed") is False:  # 开端生死去处未明：休眠，不得在江湖中活动
                node.update(hidden=True, dormant=True, agenda=None)
            if kind == "person" and node.get("status") == "wounded":  # 开局即带伤(容子矩、无崖子)：剧情上的伤，不随气血养好
                node[PLIGHT] = True
            nodes[row["id"]] = node
    return nodes


# ============================================================
#  道路与关口：02 是原路，15 修正 0 日中枢造成的伪捷径，16 补上缺失的走廊，14 是有向的通行条件
# ============================================================
def _patches(root: Path) -> list[tuple[str, dict]]:
    """依次要打的道路补丁 (名目, 补丁)：15 修伪捷径、16 补走廊，然后是场景清单(v8)里各场景给建筑连的路——同一口径。"""
    out = [(n, _read(root, n)) for n in ROAD_PATCHES]
    if (root / SCENES).exists():
        out += [(f"场景清单·{sc.get('scene')}", sc["roads"]) for sc in _read(root, SCENES)["scenes"] if sc.get("roads")]
    return out


def _roads(root: Path) -> list[tuple[str, str, int]]:
    """原路依次打上补丁（每个补丁先删、再加、再改，各只一次），返回步行日数；不依 parent 自动连路。
    补丁须与它所补的路严丝合缝：删与改的路必须存在、加的路必须不存在——对不上即补丁与原路版本错配，拒绝开局。"""
    roads, errors = {}, []
    for a, b, days in _read(root, "02_roads.json"):
        if frozenset((a, b)) in roads:
            errors.append(f"道路「{a}—{b}」重复登记")
        roads[frozenset((a, b))] = (a, b, days)
    for name, patch in _patches(root):
        for a, b in patch.get("remove", ()):
            if roads.pop(frozenset((a, b)), None) is None:
                errors.append(f"{name} 要删的「{a}—{b}」并不存在")
        for a, b, days in patch.get("add", ()):
            if frozenset((a, b)) in roads:
                errors.append(f"{name} 要加的「{a}—{b}」已经存在")
            roads[frozenset((a, b))] = (a, b, days)
        for a, b, days in patch.get("change", ()):
            if frozenset((a, b)) not in roads:
                errors.append(f"{name} 要改的「{a}—{b}」并不存在")
            roads[frozenset((a, b))] = (a, b, days)
    if errors:
        raise GenesisError(f"道路补丁有 {len(errors)} 处对不上原路，首条：{errors[0]}")
    return list(roads.values())


def _gates(root: Path) -> list[tuple[str, str, dict]]:
    """有向通行条件 (来处, 去处, 关口)：blocked/requires 由系统硬判，hidden 待剧情发现，how/risk 交导演在剧情里兑现。"""
    out = []
    for r in _read(root, "14_access.json"):
        gate = {k: r.get(k) for k in GATE}
        gate.update(blocked=bool(gate["blocked"]), hidden=bool(gate["hidden"]), requires=gate["requires"] or [])
        out.append((r["from"], r["to"], gate))
    return out


def _chapter(ev: dict) -> int:
    m = re.search(r"\d+", ev.get("src") or "")
    return int(m.group()) if m else -ev["order"]  # 无章可依者自成一簇


def _slots(events: list[dict]) -> dict[str, int]:
    """同月之内按章成簇：一章的事落在同一天，章内换一处地方多走一日，章与章在月内均匀铺开。
    原著一个下午的四件事不再被撒到三天里，主角也不必在厅中站两天等下一桩。"""
    months = defaultdict(list)
    for ev in events:
        months[day_of(ev["when"])].append(ev)
    slots = {}
    for base, evs in months.items():
        runs = []
        for ev in evs:
            if runs and _chapter(runs[-1][-1]) == _chapter(ev):
                runs[-1].append(ev)
            else:
                runs.append([ev])
        width = DAYS_PER_MONTH // len(runs)
        for i, run in enumerate(runs):
            moves, prev = 0, None
            for ev in run:
                moves += prev is not None and ev["where"] != prev
                prev = ev["where"]
                slots[ev["id"]] = base + i * width + min(moves, max(width - 1, 0))
    return slots


def _schedule(events: list[dict]) -> list[dict]:
    """按 order 排定日程：章节成簇，且日序随 order 单调不减（order 是先后的唯一权威）。"""
    events = sorted(events, key=lambda e: e["order"])
    slots = _slots(events)
    last, out = 0, []
    for ev in events:
        day = max(last, slots[ev["id"]])
        last = day
        out.append({"id": ev["id"], "order": ev["order"], "day": day, "where": ev["where"], "weight": ev["weight"],
                    "actors": ev["actors"], "requires": ev["requires"], "summary": ev["summary"],
                    "effects": ev["effects"], "public": not ev.get("reveal_scope")})
    return out


def _raw_aliases(root: Path) -> dict[str, str]:
    """索引里登记的别名 → 其正名(不论是否与某个 id 同名)。"""
    return {a: row["id"] for group, rows in _read(root, "00_index.json").items() if group != "events"
            for row in rows for a in row.get("aliases") or []}


def _aliases(root: Path, nodes: dict) -> dict[str, str]:
    """别名→id：索引里的别名（萧峰、乔帮主、保定帝…）与去掉「·」的写法；与既有 id 同名的别名让位于 id。"""
    out = {}
    for group, rows in _read(root, "00_index.json").items():
        if group == "events":
            continue
        for row in rows:
            if row["id"] in nodes:
                for alias in row.get("aliases") or []:
                    if alias not in nodes:
                        out.setdefault(alias, row["id"])
    for nid in nodes:
        flat = nid.replace("·", "")
        if flat != nid and flat not in nodes:
            out.setdefault(flat, nid)
    return out


# ============================================================
#  场景清单(v8 布景)：一处场景的建筑、景物与器物在创世时布齐——剧情只调度清单里的东西，不新造
#  建筑是地点(parent 落在场景之内)，道路以补丁口径接在 15/16 之后；景物是不可携带的陈设(type=feature，只可改现状)；
#  器物分三等：寻常只有名字，器物带几样简单属性(props)，要物详写(文书另有内容 text、底细 secret)；位置与持有者二者有一
# ============================================================
def _inside(nodes: dict, top: str) -> set[str]:
    """场景之内的地点：场景本身与它下辖的子地点(沿 parent 上溯落到它)。"""
    def under(nid, depth=0):
        return nid == top or (depth < 8 and nodes.get(nid, {}).get("type") == "location"
                              and nodes[nid].get("parent") is not None and under(nodes[nid]["parent"], depth + 1))
    return {nid for nid, n in nodes.items() if n["type"] == "location" and under(nid)}


def _dress(row: dict) -> dict:
    """一件布景器物入世：只取游戏字段；寻常之物没有描述也无妨，器物与要物须有。一部书写了全本几份(full)而没写存哪几份，即全本都在。"""
    node = {"type": "item", "kind": "杂物", "desc": None, "location": None, "holder": None, "hidden": False, "hint": None,
            "grants": None, "effect": None, "state": {"exists": True, "available": True}}
    node.update({k: row[k] for k in DRESSED if k in row})
    node["hidden"] = bool(node["hidden"])
    if node.get("full") and "pages" not in node and isinstance(node.get("qty", node["full"]), (int, float)):
        node["pages"] = list(range(int(node.get("qty", node["full"]))))
    if "pages" in node:
        node["qty"] = len(node["pages"])
    if node.get("cash"):
        node.setdefault("unit", "两")
    return node


def _stock_errors(ctx: str, nid: str, node: dict) -> list[str]:
    """数量与银两的形状(v9)：数是正数、钱是钱、全本的几份落在全本之内、用途是一列字。"""
    out, num = [], lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if "qty" in node and not (num(node["qty"]) and node["qty"] > 0):
        out.append(f"{ctx}：器物「{nid}」的数量须是正数")
    if "purse" in node and not (num(node["purse"]) and node["purse"] >= 0):
        out.append(f"{ctx}：器物「{nid}」钱袋里的银两须是数")
    if node.get("cash") and node.get("unit") != "两":
        out.append(f"{ctx}：碎银「{nid}」以两计")
    if "full" in node:
        pages = node.get("pages") or []
        if not (isinstance(node["full"], int) and node["full"] >= 1 and all(isinstance(i, int) and 0 <= i < node["full"] for i in pages)
                and len(set(pages)) == len(pages)):
            out.append(f"{ctx}：文书「{nid}」的全本份数与所存的几份对不上")
    if "uses" in node and not (isinstance(node["uses"], list) and all(isinstance(u, str) for u in node["uses"])):
        out.append(f"{ctx}：器物「{nid}」的用途须是一列字")
    if "doc" in node and not (isinstance(node["doc"], dict) and node["doc"].get("state", "写成") in DOC_STATES):
        out.append(f"{ctx}：文书「{nid}」的状态须是 {'/'.join(DOC_STATES)} 之一")
    if node.get("torn") and not node.get("full"):
        out.append(f"{ctx}：撕开的残片「{nid}」须写全本几份(full)")
    return out


def _kit_errors(ctx: str, who: str, kit, power) -> list[str]:
    """一群人每人身上一样的东西(v9/v10)：零钱是数、功力是 0~100 的整数、器物各有不同的名字。"""
    out = []
    if not isinstance(kit, dict):
        return [f"{ctx}：「{who}」的身上之物(kit)须是 {{money, items}}"]
    items, money = kit.get("items") or [], kit.get("money", 0)
    if not (isinstance(power, int) and 0 <= power <= 100) or not (isinstance(money, (int, float)) and not isinstance(money, bool) and money >= 0):
        out.append(f"{ctx}：「{who}」每人的功力与零钱须是数")
    names = [t.get("name") for t in items if isinstance(t, dict)]
    if not isinstance(items, list) or len(names) != len(items) or not all(isinstance(n, str) and n for n in names) or len(set(names)) != len(names):
        out.append(f"{ctx}：「{who}」身上的东西须各有不同的名字")
    return out


def _extras(data: dict, nodes: dict) -> list[str]:
    """场景清单的顶层段落(v10，交外部依原著抽取)：门派的无名弟子模板 kits、有名有姓之人开端时身上的零钱 money、
    原著器物(05)的补注 canon_items(等级、属性、内容、数量、全本几份、用途)、不识字的人 illiterate——错一处拒绝开局。"""
    errors, ctx = [], "场景清单"
    for faction, kit in (data.get("kits") or {}).items():
        if nodes.get(faction, {}).get("type") != "faction":
            errors.append(f"{ctx}·门下模板：「{faction}」不是已登记的门派")
            continue
        power = kit.get("power", 15) if isinstance(kit, dict) else None
        bad = _kit_errors(f"{ctx}·门下模板", faction, kit, power)
        errors += bad
        if not bad:
            nodes[faction]["squad_kit"] = {"handle": kit.get("handle") or f"{faction}弟子", "power": power, "money": kit.get("money", 0),
                                           "items": [dict(t) for t in kit.get("items") or []], "desc": kit.get("desc")}
    for row in data.get("money") or []:
        pid, money = row.get("id"), row.get("money")
        if nodes.get(pid, {}).get("type") != "person":
            errors.append(f"{ctx}·零钱：「{pid}」不是已登记的人物")
        elif not (isinstance(money, (int, float)) and not isinstance(money, bool) and money >= 0):
            errors.append(f"{ctx}·零钱：「{pid}」身上的银两须是数")
        else:
            nodes[pid]["money"] = round(float(money), 3)
    for row in data.get("canon_items") or []:
        nid = row.get("id")
        node = nodes.get(nid)
        if not node or node.get("type") != "item" or node.get("grade"):  # 只补原著(05)里的器物，场景清单新布的器物在各场景里写全
            errors.append(f"{ctx}·原著器物：「{nid}」不是原著登记的器物")
            continue
        extra = {k: row[k] for k in ENRICH if k in row}
        wrong = sorted(set(row) - set(ENRICH) - {"id", "src", "inferred", "basis"})
        if wrong:
            errors.append(f"{ctx}·原著器物：「{nid}」只可补注 {'/'.join(ENRICH)}，不改 {'、'.join(wrong)}")
        trial = {**node, **extra}
        if trial.get("full") and "pages" not in trial:
            trial["pages"] = list(range(int(trial.get("qty", trial["full"])))) if isinstance(trial.get("qty", trial["full"]), (int, float)) else []
        if "pages" in trial and isinstance(trial["pages"], list):
            trial["qty"] = len(trial["pages"])
        if trial.get("cash"):
            trial.setdefault("unit", "两")
        if trial.get("grade", "器物") not in GRADES:
            errors.append(f"{ctx}·原著器物：「{nid}」的等级须是 {'/'.join(GRADES)} 之一")
        if trial.get("text") and trial.get("grade") != "要物":
            errors.append(f"{ctx}·原著器物：只有要物才写内容(text)：「{nid}」")
        if not isinstance(trial.get("props") or {}, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in (trial.get("props") or {}).items()):
            errors.append(f"{ctx}·原著器物：「{nid}」的属性须是 {{名目: 一句话}}")
        errors += _stock_errors(f"{ctx}·原著器物", nid, trial)
        nodes[nid] = trial
    for row in data.get("illiterate") or []:
        pid = row.get("id") if isinstance(row, dict) else row
        if nodes.get(pid, {}).get("type") != "person":
            errors.append(f"{ctx}·不识字：「{pid}」不是已登记的人物")
        else:
            nodes[pid]["illiterate"] = True
    return errors


def _squad(ctx: str, row: dict, nodes: dict, inside: set) -> tuple[dict, list[str]]:
    """一群无名之众(v9)：同属一门、十五人上下一体，每人身上一样的零钱与器物——总数(pool)按人头算好。
    v10：没写 kit 即用这一门的门下模板(kits)；leader 是带队的有名之人(原著挪他，同在一处的这一群随他走)；since/until 是出没的时段(原著事件 id)。"""
    out, template = [], nodes.get(row.get("faction"), {}).get("squad_kit") or {}
    kit = row.get("kit") or ({"money": template.get("money", 0), "items": template.get("items") or []} if template else {})
    count, power, money = row.get("count"), row.get("power", template.get("power", 15)), kit.get("money", 0)
    items = kit.get("items") or []
    if nodes.get(row.get("faction"), {}).get("type") != "faction":
        out.append(f"{ctx}：人群「{row['id']}」须属于一个已登记的门派")
    if row.get("location") not in inside:
        out.append(f"{ctx}：人群「{row['id']}」不在场景之内")
    if not (isinstance(count, int) and DISBAND <= count <= 200):
        out.append(f"{ctx}：人群「{row['id']}」的人数须在{DISBAND}到二百之间")
    out += [e.replace("「", "人群「", 1) for e in _kit_errors(ctx, row["id"], kit, power)]
    names = [t.get("name") for t in items if isinstance(t, dict)]
    pool = {"银两": round((count or 0) * money, 3), **{n: count or 0 for n in names if isinstance(n, str)}}
    node = {"type": GROUP, "faction": row.get("faction"), "location": row.get("location"), "count": count, "down": 0, "dead": 0,
            "power": power, "handle": row.get("handle") or template.get("handle") or row["id"], "desc": row.get("desc") or template.get("desc"),
            "hidden": False, "status": "alive", "kit": {"money": money, "items": [dict(t) for t in items if isinstance(t, dict)]}, "pool": pool,
            **{k: row[k] for k in ("leader", "since", "until") if row.get(k)}}
    return node, out


def _stage(root: Path, nodes: dict) -> list[str]:
    """场景清单并入节点(就地)，返回错误。新 id 不得与既有之名(含别名)相撞；建筑落在场景之内；
    景物与器物所在之处须在场景之内，持有者须是此刻身在场景里的人；等级只有三等，文书内容只给要物。建筑连的路由 _roads 打上。"""
    if not (root / SCENES).exists():
        return []
    data = _read(root, SCENES)
    errors, raw = _extras(data, nodes), _raw_aliases(root)
    for sc in data.get("scenes") or []:
        top = sc.get("scene")
        if nodes.get(top, {}).get("type") != "location":
            errors.append(f"场景清单：「{top}」不是已登记的地点")
            continue
        ctx = f"场景清单·{top}"

        def fresh(nid, what) -> bool:
            if not isinstance(nid, str) or not nid.strip():
                errors.append(f"{ctx}：{what}缺 id")
                return False
            if nid in nodes or nid in raw:  # 布景之名不得盖住书中的人名、地名、器物名或它们的别名
                errors.append(f"{ctx}：{what}「{nid}」与既有之名相撞")
                return False
            return True
        for row in sc.get("places") or []:
            if fresh(row.get("id"), "建筑"):
                if row.get("parent") not in _inside(nodes, top):
                    errors.append(f"{ctx}：建筑「{row['id']}」的 parent「{row.get('parent')}」不在场景之内")
                nodes[row["id"]] = {"type": "location", "parent": row.get("parent"), "region": row.get("region") or nodes[top].get("region"),
                                    "desc": row.get("desc"), "lore": list(row.get("lore") or []), "state": row.get("state")}
        inside = _inside(nodes, top)
        for row in sc.get("features") or []:
            if fresh(row.get("id"), "景物"):
                if row.get("location") not in inside:
                    errors.append(f"{ctx}：景物「{row['id']}」不在场景之内")
                nodes[row["id"]] = {"type": "feature", "location": row.get("location"), "desc": row.get("desc"),
                                    "state": row.get("state"), "hidden": bool(row.get("hidden"))}
        for row in sc.get("items") or []:
            if not fresh(row.get("id"), "器物"):
                continue
            node, nid = _dress(row), row["id"]
            holder = node["holder"]
            if node.get("grade") not in GRADES:
                errors.append(f"{ctx}：器物「{nid}」的等级须是 {'/'.join(GRADES)} 之一")
            elif node["grade"] != "寻常" and not node["desc"]:
                errors.append(f"{ctx}：{node['grade']}「{nid}」须有描述")
            if node.get("text") and node.get("grade") != "要物":
                errors.append(f"{ctx}：只有要物才写内容(text)：「{nid}」")
            if not isinstance(node.get("props") or {}, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in (node.get("props") or {}).items()):
                errors.append(f"{ctx}：器物「{nid}」的属性须是 {{名目: 一句话}}")
            errors += _stock_errors(ctx, nid, node)
            if (node["location"] is None) == (holder is None):
                errors.append(f"{ctx}：器物「{nid}」须有且只有一处着落：location 或 holder")
            elif node["location"] is not None and node["location"] not in inside:
                errors.append(f"{ctx}：器物「{nid}」不在场景之内")
            elif holder is not None and (nodes.get(holder, {}).get("type") != "person" or nodes[holder].get("location") not in inside):
                errors.append(f"{ctx}：器物「{nid}」的持有者「{holder}」不是此刻身在场景里的人")
            nodes[nid] = node
        for row in sc.get("squads") or []:
            if fresh(row.get("id"), "人群"):
                nodes[row["id"]], bad = _squad(ctx, row, nodes, inside)
                errors += bad
    return errors


# ============================================================
#  校验：引用必须落在已登记的实体上
# ============================================================
def _validate(nodes, roads, gates, relations, canon) -> list[str]:
    errors = []
    canon_ids = {ev["id"] for ev in canon}

    def need(nid, kinds, ctx):
        if nid is not None and (nid not in nodes or nodes[nid]["type"] not in kinds):
            errors.append(f"{ctx}：「{nid}」不是已登记的{'/'.join(kinds)}")

    for nid, n in nodes.items():
        if n["type"] == "person":
            need(n.get("location"), ("location",), f"人物 {nid}.location")
            need(n.get("faction"), ("faction",), f"人物 {nid}.faction")
            for s in n.get("skills") or []:
                need(s, ("skill",), f"人物 {nid}.skills")
        elif n["type"] == "item":
            need(n.get("location"), ("location",), f"器物 {nid}.location")
            need(n.get("holder"), ("person",), f"器物 {nid}.holder")
        elif n["type"] == "location":
            need(n.get("parent"), ("location",), f"地点 {nid}.parent")
        elif n["type"] == "feature":
            need(n.get("location"), ("location",), f"景物 {nid}.location")
        elif n["type"] == GROUP:  # 人群(v10)：带队之人是登记过的人物，出没的时段是原著事件
            need(n.get("leader"), ("person",), f"人群 {nid}.leader")
            for k in ("since", "until"):
                if n.get(k) is not None and n[k] not in canon_ids:
                    errors.append(f"人群 {nid}.{k}：「{n[k]}」不是原著事件")
    for a, b, days in roads:
        need(a, ("location",), "道路")
        need(b, ("location",), "道路")
    pairs, seen = {frozenset((a, b)) for a, b, _ in roads}, set()
    for a, b, gate in gates:
        ctx = f"通行 {a}→{b}"
        if frozenset((a, b)) not in pairs:
            errors.append(f"{ctx}：两地之间没有道路")
        if (a, b) in seen:
            errors.append(f"{ctx}：重复登记")
        seen.add((a, b))
        for r in gate["requires"]:
            if not (isinstance(r, list) and len(r) == 3):
                errors.append(f"{ctx}.requires：「{r}」不是 [id, 属性, 期望值]")
            elif r[0] != "player":
                need(r[0], tuple(SOURCES), ctx + ".requires")
    for r in relations:
        need(r["src"], tuple(SOURCES), "关系")
        need(r["dst"], tuple(SOURCES), "关系")
        if r.get("revealed_by") and r["revealed_by"] not in canon_ids:
            errors.append(f"关系 {r['src']}—{r['rel']}—{r['dst']}：揭示事件「{r['revealed_by']}」不是已登记的原著事件")
    for ev in canon:
        ctx = f"事件 {ev['id']}"
        need(ev["where"], ("location",), ctx + ".where")
        for a in ev["actors"]:
            need(a, ("person",), ctx + ".actors")
        for nid, key, want in ev["requires"]:
            need(nid, tuple(SOURCES), ctx + ".requires")
            if key[:1] in ("~", "!"):  # 关系前提的另一端也须在世
                need(want, tuple(SOURCES), ctx + ".requires")
        for op in ev["effects"]:
            for nid in ([op.get("src"), op.get("dst")] if "src" in op else [op.get("id")]):
                need(nid, tuple(SOURCES), ctx + ".effects")
    return errors


def _situate(root: Path, canon: list[dict]) -> list[str]:
    """情境前提并入原著事件的 requires；事件须已登记、条目须是 [src, ~关系/!关系, dst]。"""
    if not (root / SITUATION).exists():
        return []
    by_id, errors = {ev["id"]: ev for ev in canon}, []
    for eid, conds in _read(root, SITUATION)["requires"].items():
        if eid not in by_id:
            errors.append(f"情境前提：「{eid}」不是已登记的原著事件")
            continue
        for c in conds:
            if not (isinstance(c, list) and len(c) == 3 and isinstance(c[1], str) and c[1][:1] in "~!"):
                errors.append(f"情境前提 {eid}：「{c}」不是 [src, ~关系/!关系, dst]")
            else:
                by_id[eid]["requires"] = by_id[eid]["requires"] + [c]
    return errors


def load(root: Path = DATA) -> dict:
    """每次返回独立副本：世界会被就地修改，编译结果只读缓存。"""
    return copy.deepcopy(_compile(str(root)))


def _areas(nodes: dict):
    """片区(v5)：下辖子地点的处所(无量山、少林寺、大理城)与以自身为区域的大地名(中原、西域)——那是一片地方，不是一间屋子：
    同在「中原」的四十人并不同处一室，主角走到那里，眼前只有找上门来、或被剧情带到跟前的人(situation.around)。"""
    parents = {n.get("parent") for n in nodes.values() if n["type"] == "location"}
    for nid, n in nodes.items():
        if n["type"] == "location" and (nid in parents or n.get("region") == nid):
            n["area"] = True


@lru_cache(maxsize=4)
def _compile(root: str) -> dict:
    root = Path(root)
    nodes = _nodes(root)
    staged = _stage(root, nodes)  # 场景清单(v8)：建筑、景物、分级器物先入图，片区与道路随之
    _areas(nodes)
    roads = [(a, b, _ride(days)) for a, b, days in _roads(root)]
    gates = _gates(root)
    relations = [{k: r[k] for k in ("src", "dst", "rel", "secret", "revealed_by") if k in r}
                 for r in _read(root, "07_relations.json")]
    canon = _schedule(_read(root, "08_canon.json"))
    aliases = _aliases(root, nodes)
    errors = staged + _situate(root, canon) + _validate(nodes, roads, gates, relations, canon)
    if errors:
        raise GenesisError(f"原著数据有 {len(errors)} 处引用错误，首条：{errors[0]}")
    first = canon[0]
    return {"seed": 1092, "start_tick": first["day"] * PER_DAY + START_MINUTE,
            "player": {"location": first["where"]},
            "nodes": nodes, "roads": roads, "gates": gates, "relations": relations, "canon": canon,
            "aliases": aliases}
