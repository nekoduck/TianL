"""第 4 阶段复核工具（tools/canon_review.py 的实现）：给复核代理看“断言 + 它引的原文”，再把判断写回文件。

复核只做判断，不改内容：这段原文是否支持这条断言？
  sup 支持 / rej 不支持 / doubt 存疑。
本模块不打印整本书：prep 只把**每条记录自己引用的那一段**（以证据字位为中心截取至多 WINDOW 字）写进 out/ 下的复核单，
复核单在 out/（被 .gitignore 忽略），不入库。
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from . import schema as S
from . import text as T

WINDOW = 360          # 复核单里每个证据只展示指针前后共约这么多字
VERDICTS = ('sup', 'rej', 'doubt')
KINDS = ('assertions', 'events', 'secrets', 'identities')


def entity_names(canon_dir=None):
    """{编号: 名字}，读普查登记（census/*.jsonl，其次 entities.jsonl）。"""
    d = Path(canon_dir) if canon_dir else S.CANON_DIR
    rows = []
    for f in sorted((d / 'census').glob('*.jsonl')) if (d / 'census').is_dir() else []:
        rows.extend(o for _, o in S.read_jsonl(f)[0])
    if not rows and (d / 'entities.jsonl').is_file():
        rows = [o for _, o in S.read_jsonl(d / 'entities.jsonl')[0]]
    return {r['id']: r.get('name', r['id']) for r in rows if isinstance(r, dict) and 'id' in r}


def _nm(names, x):
    if isinstance(x, str) and x in names:
        return f'{names[x]}〔{x}〕'
    return str(x)


def _evidence_of(raw):
    for k in ('e', 'evidence', 'ev'):
        if k in raw and isinstance(raw[k], list):
            return raw[k]
    return []


def render_assertion(raw, names):
    a = S.expand_assertion(raw)
    q = a.get('qualifiers') or {}
    qs = '；'.join(f'{k}={_nm(names, v)}' for k, v in q.items())
    s = f'{_nm(names, a["subject"])} ｜ {a["property"]} ｜ {_nm(names, a["value"])}'
    extra = f'  〔{a["mode"]}/{a["rank"]}/{a["tag"]}〕'
    if qs:
        extra += f'  限定：{qs}'
    if a.get('why'):
        extra += f'  理由：{a["why"]}'
    if a.get('note'):
        extra += f'  备注：{a["note"]}'
    return s + extra


def render_event(raw, names):
    e = S.expand_event(raw)
    parts = ', '.join(f'{_nm(names, p.get("person"))}:{p.get("role")}' for p in e.get('participants', []))
    t = e.get('time') or {}
    return (f'事件 {e.get("id")}《{e.get("name")}》 {e.get("kind")}  地点 {_nm(names, e.get("place"))}  '
            f'时间 {t.get("start")}~{t.get("end", t.get("start"))}{"(约)" if t.get("approx") else ""}\n'
            f'    参与者：{parts}\n    前提：{json.dumps(e.get("pre", []), ensure_ascii=False)}\n'
            f'    结果：{json.dumps(e.get("eff", []), ensure_ascii=False)}\n    备注：{e.get("note", "")}')


def render_secret(raw, names):
    s = S.expand_secret(raw)
    kn = '; '.join(f'{_nm(names, k.get("person"))}信{k.get("believes")}' for k in s.get('knowers_at_open', []))
    vs = ' | '.join(f'{v.get("key")}:{v.get("text")}' for v in s.get('versions', []) or [])
    return f'秘密 {s.get("id")}  真相：{s.get("truth")}\n    版本：{vs}\n    开局知情：{kn}'


def render_identity(raw, names):
    r = S.expand_identity(raw)
    return (f'身份 {_nm(names, r.get("person"))} 以「{r.get("as_name")}」出现（{r.get("kind")}）  '
            f'所扮 {_nm(names, r.get("as_person"))}  回 {r.get("ch")}  地点 {_nm(names, r.get("where"))}  '
            f'被谁当真 {r.get("believed_by")}')


RENDER = {'assertions': render_assertion, 'events': render_event, 'secrets': render_secret,
          'identities': render_identity}


def kind_of_path(path):
    parts = Path(path).parts
    for k in KINDS:
        if k in parts:
            return k
    raise ValueError(f'无法从路径判断记录类型（要求路径含 {"/".join(KINDS)} 之一）：{path}')


def excerpt(store, ptr):
    """证据指针 -> 以指针为中心的一小段（指针范围用【】括起）。"""
    ptr = S.expand_pointer(ptr)
    p = store.paragraph(ptr['ch'], ptr['para'])
    t, a, b = p.text, ptr['start'], ptr['end']
    half = max(0, (WINDOW - (b - a)) // 2)
    lo, hi = max(0, a - half), min(len(t), b + half)
    return (('…' if lo > 0 else '') + t[lo:a] + '【' + t[a:b] + '】' + t[b:hi] + ('…' if hi < len(t) else ''))


def prep(files, store, names, out_dir, kind=None, only_rows=None, header=''):
    """把若干 JSONL 里的记录写成复核单。返回 [(复核单路径, 条数)]。
    only_rows：{文件: {行号...}} 只取这些行（抽样用）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = []
    for f in files:
        f = Path(f)
        k = kind or kind_of_path(f)
        rows, errs = S.read_jsonl(f)
        lines = [header] if header else []
        lines.append(f'# 复核单：{f}（{k}）  复核点：这段原文是否支持这条记录？答 sup 支持 / rej 不支持 / doubt 存疑。行号 = JSONL 文件行号。')
        n = 0
        for ln, raw in rows:
            if only_rows is not None and ln not in only_rows.get(str(f), ()):
                continue
            n += 1
            try:
                body = RENDER[k](raw, names)
            except Exception as ex:   # 格式有错的行也要让复核员看见
                body = f'（无法渲染：{ex}）{json.dumps(raw, ensure_ascii=False)[:200]}'
            lines.append(f'\n#{ln}  {body}')
            for ptr in _evidence_of(raw):
                try:
                    lines.append(f'    〔c{S.expand_pointer(ptr)["ch"]}p{S.expand_pointer(ptr)["para"]}〕 {excerpt(store, ptr)}')
                except Exception as ex:
                    lines.append(f'    〔证据无法取回：{ex}〕')
            if not _evidence_of(raw):
                lines.append('    （无证据指针：basis=recall 的行，只核对常识与前后一致）')
        out = out_dir / f'{f.parent.name}_{f.stem}.txt'
        out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        res.append((str(out), n))
    return res


def apply_verdicts(path, verdicts, reviewer='model'):
    """verdicts: {行号: (verdict, why)}。就地改写：写 rv / rb；断言被 rej 则等级置 dep；why 追加进 n/note。
    未提到的行、注释与空行原样保留。返回统计 dict。"""
    p = Path(path)
    kind = kind_of_path(p)
    lines = p.read_text(encoding='utf-8-sig').splitlines()
    stat = {'sup': 0, 'rej': 0, 'doubt': 0, 'untouched': 0}
    out = []
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s.startswith('#') or i not in verdicts:
            if s and not s.startswith('#'):
                stat['untouched'] += 1
            out.append(line)
            continue
        raw = json.loads(s)
        v, why = verdicts[i]
        if v not in VERDICTS:
            raise ValueError(f'{p}:{i}: 复核结论须为 {VERDICTS}，得到 {v!r}')
        raw['rv'] = v
        raw['rb'] = f'model:{reviewer}'
        if why and v != 'sup':
            key = 'n' if kind == 'assertions' and 'subject' not in raw else 'note'
            old = raw.get(key, '')
            raw[key] = (f'{old}；' if old else '') + f'复核：{why}'[:100]
            raw[key] = raw[key][:120]
        if v == 'rej' and kind == 'assertions':
            if 'subject' in raw:
                raw['rank'] = 'dep'
            else:
                raw['r'] = 'dep'
        stat[v] += 1
        out.append(S.dumps_line(raw))
    p.write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')
    return stat


def read_verdicts(path):
    """判决文件 JSONL：{"n":行号,"v":"sup|rej|doubt","why":"≤60字"}；返回 {行号: (v, why)}，重复行号以后者为准。"""
    out = {}
    for ln, o in S.read_jsonl(path)[0]:
        if not isinstance(o, dict) or not isinstance(o.get('n'), int) or o.get('v') not in VERDICTS:
            raise ValueError(f'{path}:{ln}: 判决行须形如 {{"n":行号,"v":"sup|rej|doubt","why":"…"}}')
        out[o['n']] = (o['v'], str(o.get('why', ''))[:60])
    return out


def tally(files):
    """统计若干 JSONL 里的复核结论。返回 {kind: {'total','sup','rej','doubt','none'}}。"""
    t = {}
    for f in files:
        k = kind_of_path(f)
        d = t.setdefault(k, {'total': 0, 'sup': 0, 'rej': 0, 'doubt': 0, 'none': 0})
        for _, raw in S.read_jsonl(f)[0]:
            d['total'] += 1
            rv = raw.get('rv') if isinstance(raw, dict) else None
            if rv is None and isinstance(raw, dict) and isinstance(raw.get('reviewed'), dict):
                rv = raw['reviewed'].get('verdict')
            d[rv if rv in VERDICTS else 'none'] += 1
    return t


def draw_sample(files, n, seed, first_choice=True):
    """从断言文件里等概率抽 n 条（只抽首选 narrator 的 text 断言）。返回 {文件: {行号...}}。用计数器式随机，可复现。"""
    from ..core.rng import rnd
    pool = []
    for f in files:
        for ln, raw in S.read_jsonl(f)[0]:
            a = S.expand_assertion(raw)
            if first_choice and (a.get('rank') != 'pref' or a.get('basis') != 'text'):
                continue
            pool.append((str(f), ln))
    keyed = sorted(pool, key=lambda x: rnd(seed, 'canon-sample', x[0], x[1]))
    pick = keyed[:n]
    out = {}
    for f, ln in pick:
        out.setdefault(f, set()).add(ln)
    return out, len(pool)


# ----------------------------------------------------------------------------------------------------------------------
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog='canon_review', description='第 4 阶段复核：复核单生成、判决写回、统计、抽样')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('prep', help='把 JSONL 记录连同其引用的原文段写成复核单（out/canon/review/）')
    a.add_argument('files', nargs='+')
    a.add_argument('--out', default='out/canon/review')
    a.add_argument('--source', default=None)
    b = sub.add_parser('apply', help='把判决文件写回 JSONL（rv/rb；rej 的断言置 dep）')
    b.add_argument('file')
    b.add_argument('verdicts')
    b.add_argument('--by', default='reviewer')
    c = sub.add_parser('tally', help='统计复核结论')
    c.add_argument('files', nargs='+')
    d = sub.add_parser('sample', help='从断言文件里随机抽 N 条首选断言做独立精度审计，生成复核单')
    d.add_argument('files', nargs='+')
    d.add_argument('--n', type=int, default=200)
    d.add_argument('--seed', type=int, default=20261111)
    d.add_argument('--out', default='out/canon/audit')
    d.add_argument('--source', default=None)
    args = ap.parse_args(argv)

    if args.cmd == 'apply':
        stat = apply_verdicts(args.file, read_verdicts(args.verdicts), args.by)
        print(f'{args.file}: sup {stat["sup"]}  rej {stat["rej"]}  doubt {stat["doubt"]}  未复核 {stat["untouched"]}')
        return 0
    if args.cmd == 'tally':
        for k, d_ in tally(args.files).items():
            tot = d_['total']
            judged = d_['sup'] + d_['rej'] + d_['doubt']
            print(f'{k}: 共 {tot}；sup {d_["sup"]} rej {d_["rej"]} doubt {d_["doubt"]} 未复核 {d_["none"]}'
                  + (f'；已复核中 sup 占 {100 * d_["sup"] / judged:.1f}%' if judged else ''))
        return 0
    store = T.load_book(args.source)
    names = entity_names()
    if args.cmd == 'prep':
        for path, n in prep(args.files, store, names, args.out):
            print(f'{path}: {n} 条')
        return 0
    if args.cmd == 'sample':
        sel, pool = draw_sample(args.files, args.n, args.seed)
        tot = sum(len(v) for v in sel.values())
        print(f'首选 text 断言共 {pool} 条，按种子 {args.seed} 抽 {tot} 条，涉及 {len(sel)} 个文件')
        res = prep(sorted(sel), store, names, args.out, only_rows=sel,
                   header=f'# 随机审计样本：种子 {args.seed}，样本 {tot}/{pool}')
        for path, n in res:
            print(f'{path}: {n} 条')
        # 样本清单（文件:行号），供事后统计
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / 'sample.json').write_text(
            json.dumps({k: sorted(v) for k, v in sorted(sel.items())}, ensure_ascii=False, indent=1), encoding='utf-8')
        return 0
    return 2


if __name__ == '__main__':
    sys.exit(main())
