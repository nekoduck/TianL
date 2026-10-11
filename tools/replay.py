"""
[INPUT]: 依赖 tests/fixtures/replay80.json（从 80 回实录抽出的逐回合样本：举动/在场/随身/导演节拍与后果/选项/正文），
         world/world 的 World（实体名与别名表）、world/lexicon 的 scan / find / table
[OUTPUT]: 命令行工具：python -m tools.replay [样本.json] [--show 种类]——按违例种类统计旧对局的节拍与正文，并列出例子；
          亦可 import：audit(turns) → {kind: [(回合, Finding)]}
[POS]: 量尺——不调用模型、不改世界，用真实对局校准变化词表的误报与漏报；每一批重构都拿它对比基线
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from tianlong.world import lexicon
from tianlong.world.world import World

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "replay80.json"


def _names(world) -> tuple[list, dict]:
    g = world.graph
    names = {nid: nid for nid, n in g.nodes.items() if n["type"] in ("person", "item")}
    names.update({a: nid for a, nid in world.aliases.items() if g.kind(nid) in ("person", "item")})
    return lexicon.table(names), {nid: g.kind(nid) for nid in g.nodes}


def _view(turn: dict) -> lexicon.View:
    """旧对局没有回合末切面：由回合初的在场/随身与导演后果推出一个近似的末切面。"""
    here, inv, moved_to, dead, drained, away = set(turn["present"]), set(turn["inventory"]), None, set(), set(), set()
    arrived = set()
    for op in turn["effects"]:
        if not isinstance(op, dict):
            continue
        nid, key, v = op.get("id"), op.get("key"), op.get("value")
        if nid == "player" and key == "location":
            moved_to = v
        elif nid == "player" and key == "inventory":
            (inv.add if op.get("op") == "push" else inv.discard)(v)
        elif key == "location" and nid in here:
            away.add(nid)
        elif key == "location":
            arrived.add(nid)
        elif key == "status" and v == "dead":
            dead.add(nid)
        elif key == "power" and op.get("op") == "add" and isinstance(v, (int, float)) and v < 0:
            drained.add(nid)
        elif key == "holder" and v == "player":
            inv.add(nid)
    end = (here - away) if moved_to is None else {n for n in arrived}
    return lexicon.View(here_start=here, here_end=end, arrived=arrived, inventory_start=set(turn["inventory"]),
                        inventory_end=inv, dead=dead, drained=drained, moved=moved_to is not None)


def audit(turns: list[dict], prose: bool = False) -> dict[str, list]:
    tab, kinds = _names(World.create())
    out = defaultdict(list)
    for t in turns:
        beats = [{"who": None, "text": b} for b in t["beats"]] if not prose else \
                [{"who": None, "text": p} for p in t["text"].split("\n") if p.strip()]
        for f in lexicon.scan(beats, _view(t), tab, kinds):
            out[f.kind].append((t["n"], f))
    return out


def main(argv):
    path = Path(argv[0]) if argv and not argv[0].startswith("--") else FIXTURE
    show = argv[argv.index("--show") + 1] if "--show" in argv else None
    turns = json.loads(path.read_text("utf-8"))
    for label, prose in (("导演节拍", False), ("编剧正文", True)):
        found = audit(turns, prose)
        total = sum(len(v) for v in found.values())
        print(f"== {label}：{len(turns)} 回合，违例 {total} 条")
        for kind, items in sorted(found.items(), key=lambda kv: -len(kv[1])):
            print(f"  {kind:9s} {len(items):3d}  回合 {sorted({n for n, _ in items})[:12]}")
            if show in (kind, "all"):
                for n, f in items:
                    print(f"      第{n}回 {f.message}")


if __name__ == "__main__":
    main(sys.argv[1:])
