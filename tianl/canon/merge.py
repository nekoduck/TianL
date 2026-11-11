"""普查合并：data/canon/census/*.jsonl -> data/canon/entities.jsonl（tools/canon_merge.py 的实现）。

规则（docs/CANON_SCHEMA.md 3.3）：
  * 同编号：别名取并集；名字不一致 = 冲突；类型不一致 = 冲突；note 去重后用“；”连接
  * 同名（同类型）不同编号 = 冲突
  * 一个称呼同时指向多个实体 = 冲突，除非该称呼在某个实体上带 ambiguous
  * 格式错误的行也计入冲突
  * 冲突的判定范围是（类型，称呼）：不同类型同名（少林寺的组织与地点）不算冲突
退出码 = 冲突数是否为 0。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import schema as S


@dataclass
class Conflict:
    kind: str           # bad_row | name_mismatch | type_mismatch | same_name_diff_id | alias_multi
    message: str
    sources: list = field(default_factory=list)

    def line(self):
        src = f'  [{"; ".join(self.sources)}]' if self.sources else ''
        return f'[{self.kind}] {self.message}{src}'


KIND_LABEL = {'bad_row': '格式错误', 'name_mismatch': '名字不一致', 'type_mismatch': '类型不一致',
              'same_name_diff_id': '同名不同编号', 'alias_multi': '别名指向多个实体'}


@dataclass
class MergeResult:
    entities: list
    conflicts: list
    stats: dict
    warnings: list = field(default_factory=list)


def merge_rows(records):
    """records: [(来源文件名:行号, 行对象)]。返回 MergeResult（不写文件）。"""
    conflicts, warnings = [], []
    merged = {}                     # id -> {'row':…, 'amb': set, 'src': [..]}
    n_rows = 0
    ctx = S.Ctx()
    for src, obj in records:
        n_rows += 1
        errs = S.validate_entity_row(obj, ctx)
        if errs:
            conflicts.append(Conflict('bad_row', '；'.join(errs), [src]))
            continue
        row, _ = S.normalize_entity_row(obj)
        eid = row['id']
        if eid not in merged:
            merged[eid] = {'id': eid, 'type': row['type'], 'name': row['name'], 'aliases': list(row['aliases']),
                           'amb': set(row.get('amb', [])), 'notes': [row['note']] if row.get('note') else [],
                           'src': [src]}
            continue
        m = merged[eid]
        m['src'].append(src)
        if row['name'] != m['name']:
            conflicts.append(Conflict('name_mismatch', f'{eid} 的名字不一致：{m["name"]!r} vs {row["name"]!r}',
                                      list(m['src'])))
        if row['type'] != m['type']:
            conflicts.append(Conflict('type_mismatch', f'{eid} 的类型不一致：{m["type"]} vs {row["type"]}',
                                      list(m['src'])))
        for a in row['aliases']:
            if a not in m['aliases'] and a != m['name']:
                m['aliases'].append(a)
        m['amb'].update(row.get('amb', []))
        if row.get('note') and row['note'] not in m['notes']:
            m['notes'].append(row['note'])
    # 同名（同类型）不同编号
    by_name = {}
    for eid, m in merged.items():
        by_name.setdefault((m['type'], m['name']), []).append(eid)
    same_name = set()
    for (t, nm), ids in sorted(by_name.items()):
        if len(ids) > 1:
            same_name.add((t, nm))
            conflicts.append(Conflict('same_name_diff_id', f'同名“{nm}”（{t}）对应多个编号：{sorted(ids)}',
                                      [s for i in sorted(ids) for s in merged[i]['src'][:1]]))
    # 别名指向多个实体（按类型，称呼）
    surf = {}
    for eid, m in merged.items():
        for sf in [m['name']] + m['aliases']:
            surf.setdefault((m['type'], sf), set()).add(eid)
    amb_all = {(m['type'], a) for m in merged.values() for a in m['amb']}
    for (t, sf), ids in sorted(surf.items()):
        if len(ids) < 2 or (t, sf) in same_name:
            continue
        if (t, sf) in amb_all:
            continue
        conflicts.append(Conflict('alias_multi', f'称呼“{sf}”（{t}）同时指向 {sorted(ids)}；若书里本就如此，'
                                                 f'请在相应别名上标 "ambiguous": true',
                                  [s for i in sorted(ids) for s in merged[i]['src'][:1]]))
    ents = []
    for eid in sorted(merged):
        m = merged[eid]
        r = {'id': eid, 'type': m['type'], 'name': m['name'], 'aliases': m['aliases'], 'note': '；'.join(m['notes'])}
        if m['amb']:
            r['amb'] = sorted(m['amb'])
        ents.append(r)
    by_type = {}
    for r in ents:
        by_type[r['type']] = by_type.get(r['type'], 0) + 1
    stats = {'rows': n_rows, 'entities': len(ents), 'by_type': by_type, 'conflicts': len(conflicts)}
    return MergeResult(ents, conflicts, stats, warnings)


def read_census(path):
    """读文件或目录 -> ([(来源, 行对象)], 解析错误[str])。"""
    recs, errs = S.read_records(path)
    return [(f'{Path(f).name}:{n}', obj) for f, n, obj in recs], errs


def merge_census(path):
    recs, errs = read_census(path)
    res = merge_rows(recs)
    for e in errs:
        res.conflicts.append(Conflict('bad_row', e))
    res.stats['conflicts'] = len(res.conflicts)
    return res


def format_conflicts(res):
    lines = [f'普查合并冲突报告：冲突 {len(res.conflicts)} 条（行 {res.stats["rows"]}，实体 {res.stats["entities"]}）']
    if not res.conflicts:
        lines.append('无冲突。')
    for kind in KIND_LABEL:
        sel = [c for c in res.conflicts if c.kind == kind]
        if sel:
            lines.append(f'\n## {KIND_LABEL[kind]}（{len(sel)}）')
            lines.extend(c.line() for c in sel)
    return '\n'.join(lines) + '\n'


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(description='合并 data/canon/census/*.jsonl -> data/canon/entities.jsonl；退出码 = 有无冲突')
    ap.add_argument('--census', default=str(S.CANON_DIR / 'census'), help='普查目录或文件')
    ap.add_argument('--out', default=str(S.CANON_DIR / 'entities.jsonl'), help='合并产物')
    ap.add_argument('--conflicts', default=str(S.CANON_DIR / 'census_conflicts.txt'), help='冲突报告')
    ap.add_argument('--dry-run', action='store_true', help='只检查，不写文件')
    a = ap.parse_args(argv)
    files = S.list_jsonl_files(a.census)
    if not files:
        print(f'没有找到普查文件：{a.census}（无事可合并，不写任何产物）', file=out)
        return 0
    res = merge_census(a.census)
    if not a.dry_run:
        S.write_jsonl(a.out, res.entities)
        Path(a.conflicts).parent.mkdir(parents=True, exist_ok=True)
        Path(a.conflicts).write_text(format_conflicts(res), encoding='utf-8')
    t = '，'.join(f'{k} {v}' for k, v in sorted(res.stats['by_type'].items()))
    print(f'读取 {len(files)} 个文件、{res.stats["rows"]} 行 -> 实体 {res.stats["entities"]} 个（{t}）', file=out)
    print(f'冲突 {len(res.conflicts)} 条' + ('' if a.dry_run else f'，报告：{a.conflicts}'), file=out)
    for c in res.conflicts[:20]:
        print('  ' + c.line(), file=out)
    if len(res.conflicts) > 20:
        print(f'  ……另有 {len(res.conflicts) - 20} 条，见报告', file=out)
    return 0 if not res.conflicts else 1


if __name__ == '__main__':
    sys.exit(main())
