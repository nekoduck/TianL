"""
[INPUT]: 读取 data/canon/*.json（外部抽取的原著硬知识，格式见 data/EXTRACT_PROMPT.md），依赖 world/clock 的 day_of / PER_DAY
[OUTPUT]: 对外提供 load()（编译出 World 可直接加载的创世字典）、GenesisError、DATA
[POS]: world 层的创世导入器——原著硬知识进入基础设施的唯一入口：裁剪抽取元数据、排定原著日程、
       处理开端未明的人物（休眠）、校验全部 id 引用；任何引用错误都在开局前失败，绝不带病入世
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from .clock import DAYS_PER_MONTH, PER_DAY, day_of

DATA = Path(__file__).resolve().parents[2] / "data" / "canon"
START_SHICHEN = 4  # 开场于辰时

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
            nodes[row["id"]] = node
    return nodes


def _schedule(events: list[dict]) -> list[dict]:
    """按 order 排定日程：同月事件均匀铺开，且日序随 order 单调不减（order 是先后的唯一权威）。"""
    events = sorted(events, key=lambda e: e["order"])
    months = defaultdict(list)
    for ev in events:
        months[day_of(ev["when"])].append(ev)
    last, out = 0, []
    for ev in events:
        base = day_of(ev["when"])
        peers = months[base]
        day = max(last, base + peers.index(ev) * DAYS_PER_MONTH // len(peers))
        last = day
        out.append({"id": ev["id"], "order": ev["order"], "day": day, "where": ev["where"], "weight": ev["weight"],
                    "actors": ev["actors"], "requires": ev["requires"], "summary": ev["summary"],
                    "effects": ev["effects"], "public": not ev.get("reveal_scope")})
    return out


# ============================================================
#  校验：引用必须落在已登记的实体上
# ============================================================
def _validate(nodes, roads, relations, canon) -> list[str]:
    errors = []

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
    for a, b, days in roads:
        need(a, ("location",), "道路")
        need(b, ("location",), "道路")
    for r in relations:
        need(r["src"], tuple(SOURCES), "关系")
        need(r["dst"], tuple(SOURCES), "关系")
    for ev in canon:
        ctx = f"事件 {ev['id']}"
        need(ev["where"], ("location",), ctx + ".where")
        for a in ev["actors"]:
            need(a, ("person",), ctx + ".actors")
        for nid, _, _ in ev["requires"]:
            need(nid, tuple(SOURCES), ctx + ".requires")
        for op in ev["effects"]:
            for nid in ([op.get("src"), op.get("dst")] if "src" in op else [op.get("id")]):
                need(nid, tuple(SOURCES), ctx + ".effects")
    return errors


def load(root: Path = DATA) -> dict:
    """每次返回独立副本：世界会被就地修改，编译结果只读缓存。"""
    return copy.deepcopy(_compile(str(root)))


@lru_cache(maxsize=4)
def _compile(root: str) -> dict:
    root = Path(root)
    nodes = _nodes(root)
    roads = [tuple(r) for r in _read(root, "02_roads.json")]
    relations = [{k: r[k] for k in ("src", "dst", "rel", "secret") if k in r} for r in _read(root, "07_relations.json")]
    canon = _schedule(_read(root, "08_canon.json"))
    errors = _validate(nodes, roads, relations, canon)
    if errors:
        raise GenesisError(f"原著数据有 {len(errors)} 处引用错误，首条：{errors[0]}")
    first = canon[0]
    return {"seed": 1092, "start_tick": first["day"] * PER_DAY + START_SHICHEN,
            "player": {"location": first["where"]},
            "nodes": nodes, "roads": roads, "relations": relations, "canon": canon}
