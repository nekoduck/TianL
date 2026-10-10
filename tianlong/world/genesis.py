"""
[INPUT]: 读取 data/canon/*.json（外部抽取的原著硬知识，格式见 data/EXTRACT_PROMPT.md），依赖 world/clock 的 day_of / PER_DAY / PER_SHICHEN
[OUTPUT]: 对外提供 load()（编译出 World 可直接加载的创世字典：nodes/roads/relations/canon/aliases/player/start_tick/seed）、GenesisError、DATA
[POS]: world 层的创世导入器——原著硬知识进入基础设施的唯一入口：裁剪抽取元数据、排定原著日程、
       处理开端未明的人物（休眠）、路程按骑马换算(PACE)、按章成簇排定日程、编译别名表、保留隐情的揭示事件(revealed_by)、
       校验全部 id 引用；任何引用错误都在开局前失败，绝不带病入世
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from .clock import DAYS_PER_MONTH, PER_DAY, PER_SHICHEN, day_of

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
#  校验：引用必须落在已登记的实体上
# ============================================================
def _validate(nodes, roads, relations, canon) -> list[str]:
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
    for a, b, days in roads:
        need(a, ("location",), "道路")
        need(b, ("location",), "道路")
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
    roads = [(a, b, _ride(days)) for a, b, days in _read(root, "02_roads.json")]
    relations = [{k: r[k] for k in ("src", "dst", "rel", "secret", "revealed_by") if k in r}
                 for r in _read(root, "07_relations.json")]
    canon = _schedule(_read(root, "08_canon.json"))
    errors = _validate(nodes, roads, relations, canon)
    if errors:
        raise GenesisError(f"原著数据有 {len(errors)} 处引用错误，首条：{errors[0]}")
    first = canon[0]
    return {"seed": 1092, "start_tick": first["day"] * PER_DAY + START_MINUTE,
            "player": {"location": first["where"]},
            "nodes": nodes, "roads": roads, "relations": relations, "canon": canon, "aliases": _aliases(root, nodes)}
