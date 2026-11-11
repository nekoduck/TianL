"""tools/canon_run.py 的实现：有原文时跑第 0–2 阶段并补证据指针；没有原文时给出清晰提示，退出码 0。

流程：
  0 规范化 -> 源文本库（段落哈希索引写 out/canon/text_index.json，不含原文）
  1 提及普查 -> out/canon/mentions.jsonl（实体、回、段、起止字位），并核对“按字位取回同样的字”
  2 消歧合并 -> out/canon/resolve_report.txt（含“同一段内一个称呼只指一个实体”的校验、30 人是否都找到）
  证据 -> 已有 basis=text 的断言：核对指针；basis=recall 的断言：找“主体与值同段出现”的候选段，写
          out/canon/evidence_candidates.jsonl。**同段出现不等于原文支持**；只有给了复核器（--review anthropic，或测试里
          注入 reviewer）且判“支持”，并加 --write，才会把断言升为 basis=text 并写回断言文件。
          没有 --write 一律不改动 data/ 下任何文件。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import llm as L
from . import merge as M
from . import schema as S
from . import text as T

HINT = ('没有找到原著文本，第 0–2 阶段无事可做（退出码 0）。\n'
        '  把《天龙八部》文本（UTF-8 纯文本，按“第X回”分章；版本以你提供的为准，默认三联版）放在 sources/ 下，\n'
        '  例如 sources/tianlong.txt，然后运行：python3 tools/canon_run.py --source sources/tianlong.txt\n'
        '  没有原文时世界照常运行，所有断言保持 basis=recall、evidence=[]（见 docs/DECISIONS.md 第三节）。\n'
        '  注意：原文只放本地，仓库不收（sources/ 已被 .gitignore 忽略）。')


def _registry(canon_dir, explicit):
    if explicit:
        recs, _ = M.read_census(explicit)
        return M.merge_rows(recs).entities
    census = S.CANON_DIR / 'census' if canon_dir is None else Path(canon_dir) / 'census'
    if S.list_jsonl_files(census):
        return M.merge_census(census).entities
    f = Path(canon_dir or S.CANON_DIR) / 'entities.jsonl'
    return [o for _, o in S.read_jsonl(f)[0]] if f.is_file() else []


def _find_source(arg):
    if arg:
        return Path(arg)
    d = S.REPO_ROOT / 'sources'
    cands = sorted(d.glob('*.txt')) if d.is_dir() else []
    return cands[0] if cands else None


def candidate_evidence(store, a, by_para, limit=3):
    """断言 a 的候选证据段：主体与（实体型的）值同段出现。返回 (指针列表, 强度)。"""
    s, v = a.get('subject'), a.get('value')
    need_v = isinstance(v, str) and S.is_entity_id(v)
    both, only_s = [], []
    for (ch, para), ids in sorted(by_para.items()):
        if s in ids:
            (both if (not need_v or v in ids) else only_s).append((ch, para))
    if need_v:
        pick, strength = both[:limit], 'both'
    else:
        pick, strength = (both or only_s)[:limit], 'subject_only'
    return [store.pointer(ch, p) for ch, p in pick], strength


def _apply(updates):
    """updates: {文件: {行号: 完整断言}}；逐行替换为紧凑 JSON，保留其余行（含注释）。"""
    for f, rows in updates.items():
        lines = Path(f).read_text(encoding='utf-8').split('\n')
        for n, a in rows.items():
            lines[n - 1] = S.dumps_line(S.compact_assertion(a))
        Path(f).write_text('\n'.join(lines), encoding='utf-8')


def main(argv=None, out=None, reviewer=None, extractor=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='canon_run', description='原著 -> 数据：第 0–2 阶段与证据指针')
    ap.add_argument('--source', help='原著文本（UTF-8，按回分章）；缺省取 sources/ 下第一个 .txt')
    ap.add_argument('--canon-dir', default=str(S.CANON_DIR))
    ap.add_argument('--entities', help='显式指定登记表（普查文件或目录）')
    ap.add_argument('--out', default=str(S.REPO_ROOT / 'out' / 'canon'), help='中间产物目录（被 .gitignore 忽略）')
    ap.add_argument('--review', choices=['none', 'anthropic'], default='none', help='复核候选证据的后端')
    ap.add_argument('--extract', choices=['none', 'anthropic'], default='none', help='第 3 阶段：滑动窗口抽取（写 out/extracted.jsonl）')
    ap.add_argument('--window', type=int, default=4)
    ap.add_argument('--limit', type=int, default=3, help='每条断言最多试几个候选段')
    ap.add_argument('--write', action='store_true', help='把复核通过的断言升为 basis=text 并写回 data/canon/assertions')
    a = ap.parse_args(argv)
    src = _find_source(a.source)
    if src is None or not src.is_file():
        print(HINT, file=out)
        if src is not None:
            print(f'  （指定的文件不存在：{src}）', file=out)
        return 0
    canon = Path(a.canon_dir)
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    rc = 0
    # 阶段 0
    store = T.TextStore.from_file(src)
    st = store.stats()
    (outdir / 'text_index.json').write_text(json.dumps(store.index(), ensure_ascii=False, separators=(',', ':')),
                                            encoding='utf-8')
    print(f'阶段 0 规范化：{st["chapters"]} 回，{st["paragraphs"]} 段，{st["sentences"]} 句，{st["chars"]} 字'
          f'（编码 {store.meta.get("encoding", "?")}）', file=out)
    for w in store.meta['warnings']:
        print(f'  警告：{w}', file=out)
    # 阶段 1
    rows = _registry(canon, a.entities)
    if not rows:
        print('没有登记表（data/canon/census 或 entities.jsonl），阶段 1–2 跳过。', file=out)
        return rc
    ident = []
    for _, o in [(f'{f}:{n}', o) for f, n, o in S.read_records(canon / 'identities')[0]]:
        ident.append(o)
    index = T.SurfaceIndex(rows, ident)
    mentions = T.census_mentions(store, index)
    merrs = T.verify_mentions(store, mentions)
    print(f'阶段 1 提及普查：称呼 {len(index.cands)} 个，提及 {len(mentions)} 条；字位取回校验错误 {len(merrs)}', file=out)
    for e in merrs[:10]:
        print(f'  错误：{e}', file=out)
    if merrs:
        rc = 1
    # 阶段 2
    res = T.resolve_mentions(store, mentions, index)
    T.write_mentions(outdir / 'mentions.jsonl', res.mentions)
    counts = T.mention_counts(res.mentions)
    lines = [f'提及 {res.report["mentions"]}：唯一候选 {res.report["unique"]}，上下文消歧 {res.report["context"]}，'
             f'身份表 {res.report["identity"]}，同名孪生 {res.report["twin"]}，未消歧 {res.report["unresolved"]}']
    lines.append(f'同段单一所指违规 {len(res.violations)} 条')
    lines.extend('  ' + v for v in res.violations[:20])
    unres = {}
    for m in res.unresolved:
        unres[m.surface] = unres.get(m.surface, 0) + 1
    lines.append('未消歧称呼（前 20）：' + '；'.join(f'{k}×{v}' for k, v in sorted(unres.items(), key=lambda kv: -kv[1])[:20]))
    found = [(n, i, counts.get(i, 0)) for n, i, _ in S.RECALL_30]
    miss = [f'{n}({i})' for n, i, c in found if c == 0]
    lines.append(f'30 人召回（提及）：{30 - len(miss)}/30 找到' + (f'；未找到：{", ".join(miss)}' if miss else ''))
    (outdir / 'resolve_report.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('阶段 2 消歧合并：', file=out)
    for ln in lines:
        print('  ' + ln, file=out)
    if res.violations:
        rc = 1
    # 证据
    by_para = T.paragraph_entities(res.mentions)
    recs = S.read_records(canon / 'assertions')[0]
    n_text = n_bad = n_cand = n_upgrade = n_rej = 0
    cands, updates = [], {}
    if a.review == 'anthropic' and reviewer is None:
        try:
            reviewer = L.AnthropicReviewer(L.AnthropicClient())
        except L.LLMUnavailable as ex:
            print(f'无法复核：{ex}', file=out)
            return 2
    for f, n, obj in recs:
        full = S.expand_assertion(obj)
        if not isinstance(full, dict) or full.get('rank') == 'dep':
            continue
        if full.get('basis') == 'text':
            n_text += 1
            for p in full.get('evidence') or []:
                why = store.check_pointer(p)
                if why:
                    n_bad += 1
                    print(f'  错误：{Path(f).name}:{n} 指针取不回原字：{why}', file=out)
            continue
        ptrs, strength = candidate_evidence(store, full, by_para, a.limit)
        if not ptrs:
            continue
        n_cand += 1
        cands.append({'id': full['id'], 'where': f'{Path(f).name}:{n}', 's': full.get('subject'),
                      'p': full.get('property'), 'v': full.get('value'), 'strength': strength,
                      'ptrs': [S.compact_pointer(p) for p in ptrs]})
        if reviewer is None or strength != 'both':
            continue
        for p in ptrs:
            r = reviewer.review(full, store.get_span(p))
            if r.get('verdict') == 'sup':
                new = dict(full, basis='text', evidence=[p],
                           reviewed={'verdict': 'sup', 'by': f'model:{getattr(reviewer, "name", "reviewer")}'})
                if not S.validate_assertion(new):
                    updates.setdefault(f, {})[n] = new
                    n_upgrade += 1
                break
        else:
            n_rej += 1
    S.write_jsonl(outdir / 'evidence_candidates.jsonl', cands)
    pct = f'{100 * (n_text - n_bad) / n_text:.1f}%' if n_text else '不适用'
    print(f'证据：已有 basis=text {n_text} 条，指针有效率 {pct}（无效 {n_bad}）；'
          f'凭记忆断言里有候选段的 {n_cand} 条（写入 evidence_candidates.jsonl，同段出现不等于原文支持）', file=out)
    if reviewer is not None:
        print(f'复核：判“支持”可升为 text 的 {n_upgrade} 条，候选段均未获支持的 {n_rej} 条'
              + ('；已写回' if a.write and updates else '；未写回（加 --write）'), file=out)
        if a.write and updates:
            _apply(updates)
    if n_bad:
        rc = 1
    # 阶段 3（可选）
    if a.extract != 'none' or extractor is not None:
        if extractor is None:
            try:
                extractor = L.AnthropicExtractor(L.AnthropicClient())
            except L.LLMUnavailable as ex:
                print(f'无法抽取：{ex}', file=out)
                return 2
        got, rej, stats = L.run_extraction(store, rows, extractor, window=a.window)
        S.write_assertions(outdir / 'extracted.jsonl', got)
        print(f'阶段 3 抽取：窗口 {stats["windows"]}，原始 {stats["raw"]}，收下 {stats["kept"]}，被拒 {stats["rejected"]}'
              f' -> {outdir / "extracted.jsonl"}', file=out)
    return rc


if __name__ == '__main__':
    sys.exit(main())
