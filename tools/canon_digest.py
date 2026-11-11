#!/usr/bin/env python3
"""原著 -> 数据：canon_digest。给抽取代理的“本回出场实体摘要”与全库登记速查表。

  python3 tools/canon_digest.py --ch 12            # 打印第 12 回出现的已登记实体：编号、名、本回次数、别名
  python3 tools/canon_digest.py --registry         # 写 out/canon/registry.tsv（全部实体：编号、名、别名）
  python3 tools/canon_digest.py --all              # 写 out/canon/digest/chNN.tsv（0–52 回）与 registry.tsv

读本地的 out/canon/mentions.tsv（canon_names mentions 的产物）与 data/canon/census/*.jsonl（其次 entities.jsonl）。
只含编号、名字与整数，不含原文。
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tianl.canon import merge as M  # noqa: E402
from tianl.canon import schema as S  # noqa: E402


def load_entities():
    recs = []
    cd = ROOT / 'data' / 'canon'
    fs = sorted((cd / 'census').glob('*.jsonl'))
    for f in fs:
        recs.extend((f'{f.name}:{n}', o) for n, o in S.read_jsonl(f)[0])
    if not recs and (cd / 'entities.jsonl').is_file():
        recs = [(f'e:{n}', o) for n, o in S.read_jsonl(cd / 'entities.jsonl')[0]]
    return {r['id']: r for r in M.merge_rows(recs).entities}


def alias_names(r):
    return [a['name'] if isinstance(a, dict) else a for a in r.get('aliases', [])]


def load_counts():
    per = defaultdict(Counter)
    p = ROOT / 'out' / 'canon' / 'mentions.tsv'
    if not p.is_file():
        raise SystemExit('缺 out/canon/mentions.tsv：先运行 python3 tools/canon_names.py mentions')
    for i, line in enumerate(p.read_text(encoding='utf-8').splitlines()):
        if i == 0 or not line:
            continue
        e, ch, *_ = line.split('\t')
        per[int(ch)][e] += 1
    return per


def digest(ch, ents, per):
    rows = []
    for e, n in per[ch].most_common():
        r = ents.get(e)
        if r is None:
            continue
        rows.append(f'{e}\t{r["name"]}\t{n}\t{"、".join(alias_names(r)[:6])}')
    return '实体编号\t名\t本回次数\t别名\n' + '\n'.join(rows) + '\n'


def registry(ents):
    rows = [f'{e}\t{r["name"]}\t{"、".join(alias_names(r))}' for e, r in sorted(ents.items())]
    return '实体编号\t名\t别名\n' + '\n'.join(rows) + '\n'


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ch', type=int)
    ap.add_argument('--registry', action='store_true')
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args(argv)
    ents = load_entities()
    out = ROOT / 'out' / 'canon'
    if a.registry or a.all:
        out.mkdir(parents=True, exist_ok=True)
        (out / 'registry.tsv').write_text(registry(ents), encoding='utf-8')
        print(f'out/canon/registry.tsv：{len(ents)} 个实体')
    if a.all:
        per = load_counts()
        (out / 'digest').mkdir(parents=True, exist_ok=True)
        for ch in range(0, 53):
            (out / 'digest' / f'ch{ch:02d}.tsv').write_text(digest(ch, ents, per), encoding='utf-8')
        print('out/canon/digest/ch00–ch52.tsv 已写')
    if a.ch is not None:
        sys.stdout.write(digest(a.ch, ents, load_counts()))
    if not (a.ch is not None or a.registry or a.all):
        ap.print_help()
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
