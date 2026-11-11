"""tools/canon_text.py 的实现：证据锚点工具（给后续抽取代理用）。

子命令：
  info                              各回标题/段数/句数/字数，与规范化统计
  export [--ch SPEC | --all] --out DIR   把各回导出成 DIR/chapters/chNN.txt，每行 “[c12p34] 段落文字”（out/ 被忽略；Read 工具读）
  show CH [--from P --to Q]         终端打印某回（或其中几段）
  find 字符串 [--ch N]              列出命中段编号与每回计数，不打印整段
  ptr CH PARA 锚点 [--nth K]        把一个 <=20 字的锚点解析成指针 [回,段,起,止,哈希]
  verify-evidence FILE|DIR          核对断言/事件/秘密等文件里的全部证据指针：能取回、哈希相符；汇总有效率
  manifest [--write] [--check]      生成/核对 data/canon/text_manifest.json（只有哈希与计数）

原文只在本地；本工具的输出（除 export 写进 out/ 的文件与 show）不打印整段原文。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import anchors as A
from . import schema as S
from . import text as T


# ----------------------------------------------------------------------------------------------------------------------
# 公共
# ----------------------------------------------------------------------------------------------------------------------
def add_source_args(ap):
    ap.add_argument('--source', help=f'原文文本（UTF-8，三联版面）；缺省 {T.DEFAULT_SOURCE.relative_to(S.REPO_ROOT)}')
    ap.add_argument('--expect', type=int, default=T.BOOK_CHAPTERS,
                    help=f'要求正好这么多回（三联版面；默认 {T.BOOK_CHAPTERS}，0 = 不要求）')
    ap.add_argument('--canon-dir', default=str(S.CANON_DIR), help='数据根目录（取文本清单；默认 data/canon）')


def open_store(a, err=None):
    """按命令行参数载入全书（严格版面 + 核对文本清单）。载入警告写 stderr。"""
    err = err or sys.stderr
    st = T.load_book(a.source, canon_dir=a.canon_dir, expect_chapters=a.expect)
    for w in st.meta['warnings']:
        print(f'警告：{w}', file=err)
    return st


def parse_ch_spec(spec, store):
    """'3' / '1-5' / '1,3,7-9' -> 升序回号列表；回号必须存在。"""
    nums = set()
    for part in str(spec).split(','):
        part = part.strip()
        if not part:
            continue
        try:
            if '-' in part:
                a, b = part.split('-', 1)
                lo, hi = int(a), int(b)
                if lo > hi:
                    raise ValueError
                nums.update(range(lo, hi + 1))
            else:
                nums.add(int(part))
        except ValueError:
            raise ValueError(f'回号写法不对：{part!r}（例：3  1-5  1,3,7-9）')
    miss = sorted(n for n in nums if n not in store.chapters)
    if miss:
        raise ValueError(f'没有这些回：{miss}（有：{sorted(store.chapters)[0]}–{sorted(store.chapters)[-1]}）')
    return sorted(nums)


def _pad(s, width):
    """按显示宽度（汉字算 2）右补空格。"""
    return s + ' ' * max(0, width - sum(2 if ord(c) > 0x2E80 else 1 for c in s))


def para_line(p):
    return f'[c{p.ch}p{p.idx}] {p.text}'


# ----------------------------------------------------------------------------------------------------------------------
# 子命令
# ----------------------------------------------------------------------------------------------------------------------
def cmd_info(a, out):
    st = open_store(a)
    s = st.stats()
    c = st.meta.get('clean', {})
    print(f'原文：{st.meta.get("path", "?")}（编码 {st.meta.get("encoding", "?")}，版面 {st.meta.get("layout", "?")}）', file=out)
    print(f'规范化：去水印标记 {c.get("watermark_tokens", 0)} 处、站点头尾行 {c.get("site_lines", 0)} 行、'
          f'分隔行 {c.get("separator_lines", 0)} 行、空行 {c.get("blank_lines", 0)} 行；规范化规则 {T.NORMALIZER_ID}', file=out)
    print(f'正文 {s["chapters"]} 回；全书 {s["paragraphs"]} 段、{s["sentences"]} 句、{s["chars"]} 字'
          f'（含卷首 0、后记 51、附录 52；字数 = 各段字符数之和）', file=out)
    print(f'{"回":>3}  {_pad("标题", 30)}{"段":>6}{"句":>7}{"字":>9}', file=out)
    for n, title, paras, chars in st.chapter_rows():
        sents = sum(len(p.sentences) for p in st.chapters[n].paragraphs)
        print(f'{n:>3}  {_pad(title, 30)}{paras:>6}{sents:>7}{chars:>9}', file=out)
    print(f'全书规范化文本 sha256：{st.text_sha256()}', file=out)
    return 0


def export_dir(outdir):
    """导出目录：DIR/chapters（DIR 自己就叫 chapters 时直接用它）。"""
    d = Path(outdir)
    return d if d.name == 'chapters' else d / 'chapters'


def cmd_export(a, out):
    st = open_store(a)
    if a.all or a.ch is None:
        nums = sorted(st.chapters)
    else:
        nums = parse_ch_spec(a.ch, st)
    d = export_dir(a.out)
    d.mkdir(parents=True, exist_ok=True)
    n_para = 0
    for n in nums:
        path = d / f'ch{n:02d}.txt'
        c = st.chapters[n]
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            for p in c.paragraphs:
                f.write(para_line(p) + '\n')
        n_para += len(c.paragraphs)
    print(f'导出 {len(nums)} 回、{n_para} 段 -> {d}/chNN.txt（每行 “[c回p段] 段落文字”；out/ 被 .gitignore 忽略，原文不入库）', file=out)
    return 0


def cmd_show(a, out):
    st = open_store(a)
    if a.ch not in st.chapters:
        print(f'没有第 {a.ch} 回', file=out)
        return 1
    c = st.chapters[a.ch]
    lo = a.from_ if a.from_ is not None else 1
    hi = a.to if a.to is not None else len(c.paragraphs)
    if not 1 <= lo <= hi <= len(c.paragraphs):
        print(f'段范围 {lo}–{hi} 不合法（第 {a.ch} 回共 {len(c.paragraphs)} 段）', file=out)
        return 1
    for p in c.paragraphs[lo - 1:hi]:
        print(para_line(p), file=out)
    return 0


def cmd_find(a, out):
    st = open_store(a)
    if not a.needle or '\n' in a.needle:
        print('检索串须非空且不含换行', file=out)
        return 1
    hits = st.find(a.needle, ch=a.ch)
    by_ch = {}
    for ch, para, off in hits:
        by_ch.setdefault(ch, []).append((para, off))
    n_paras = len({(c, p) for c, p, _ in hits})
    where = f'第 {a.ch} 回' if a.ch is not None else '全书'
    print(f'{where}命中 {len(hits)} 处，分布在 {n_paras} 段、{len(by_ch)} 回（不打印原文；用 show 或 export 看）', file=out)
    for ch in sorted(by_ch):
        lst = by_ch[ch]
        shown = lst if a.all else lst[:a.limit]
        tags = ' '.join(f'c{ch}p{p}@{o}' for p, o in shown)
        more = f' …（另 {len(lst) - len(shown)} 处，--all 全列）' if len(shown) < len(lst) else ''
        print(f'  第 {ch} 回：{len(lst)} 处  {tags}{more}', file=out)
    return 0 if hits else 1


def cmd_ptr(a, out):
    st = open_store(a)
    try:
        ptr = A.resolve_anchor(st, a.ch, a.para, a.anchor, a.nth)
    except A.AnchorError as ex:
        print(f'错误：{ex}', file=sys.stderr)
        return 1
    print(json.dumps(ptr, ensure_ascii=False, separators=(',', ':')), file=out)
    return 0


def verify_paths(store, paths, max_errors=20, out=None):
    """核对文件/目录里的全部证据指针。返回 (总指针, 有效, 无效, 错误行数, 文件数)。"""
    out = out or sys.stdout
    files = []
    for f in paths:
        pf = Path(f)
        if not pf.exists():
            raise FileNotFoundError(f'路径不存在：{f}')
        files.extend(S.list_jsonl_files(pf))
    tot = ok = bad = badrows = 0
    for f in files:
        rows, perr = S.read_jsonl(f)
        f_tot = f_ok = f_bad = f_rows = 0
        problems = list(perr)
        for n, obj in rows:
            if not isinstance(obj, dict):
                continue
            ekey = A.evidence_key(obj)
            items = obj.get(ekey) if ekey else None
            if not isinstance(items, list) or not items:
                continue
            f_rows += 1
            for i, it in enumerate(items):
                kind, val = A.classify_item(it)
                f_tot += 1
                if kind == 'pointer':
                    why = A.check_pointer_item(store, val)
                elif kind == 'anchor':
                    why = '未解析的锚点（先运行 tools/canon_resolve.py）'
                else:
                    why = val
                if why:
                    f_bad += 1
                    problems.append(f'{Path(f).name}:{n}: {ekey}[{i}] {why}')
                else:
                    f_ok += 1
        tot, ok, bad = tot + f_tot, ok + f_ok, bad + f_bad
        badrows += len(perr)
        rate = f'{100 * f_ok / f_tot:.1f}%' if f_tot else '不适用'
        print(f'{f}：有证据的行 {f_rows}，指针 {f_tot}，有效 {f_ok}（{rate}），无效 {f_bad}'
              + (f'，解析错误 {len(perr)}' if perr else ''), file=out)
        for pr in problems[:max_errors]:
            print(f'  {pr}', file=out)
        if len(problems) > max_errors:
            print(f'  ……另有 {len(problems) - max_errors} 条', file=out)
    return tot, ok, bad, badrows, len(files)


def cmd_verify(a, out):
    st = open_store(a)
    try:
        tot, ok, bad, badrows, nf = verify_paths(st, a.paths, a.max_errors, out)
    except FileNotFoundError as ex:
        print(f'错误：{ex}', file=out)
        return 2
    rate = f'{ok}/{tot} = {100 * ok / tot:.1f}%' if tot else '不适用（没有任何证据指针）'
    print(f'汇总：{nf} 个文件；证据指针有效率 {rate}；无效 {bad}；JSON 解析错误 {badrows} -> '
          + ('通过' if bad == 0 and badrows == 0 else '有错误，见上'), file=out)
    return 0 if bad == 0 and badrows == 0 else 1


def dump_manifest(m):
    """清单的稳定文本形式：顶层一键一行，各回一回一行（便于 diff）。"""
    lines = ['{']
    keys = [k for k in m if k != 'chapters']
    for k in keys:
        lines.append(f' {json.dumps(k)}:{json.dumps(m[k], ensure_ascii=False, separators=(",", ":"))},')
    lines.append(' "chapters":[')
    rows = [json.dumps(c, ensure_ascii=False, separators=(',', ':')) for c in m['chapters']]
    lines.extend('  ' + r + (',' if i < len(rows) - 1 else '') for i, r in enumerate(rows))
    lines.append(' ]')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def cmd_manifest(a, out):
    try:
        st = T.load_book(a.source, canon_dir=a.canon_dir, expect_chapters=a.expect, check_manifest=False)
    except (OSError, T.TextFormatError) as ex:
        print(f'错误：{ex}', file=out)
        return 2
    path = Path(a.canon_dir) / T.MANIFEST_NAME
    m = st.manifest()
    t = m['totals']
    print(f'文本清单：{t["chapters"]} 回（含卷首/后记/附录共 {len(m["chapters"])} 项），{t["paragraphs"]} 段，{t["chars"]} 字；'
          f'sha256 {m["text_sha256"][:16]}…；去除 {m["removed"]}', file=out)
    rc = 0
    if path.is_file():
        probs = st.check_manifest(json.loads(path.read_text(encoding='utf-8')))
        if probs:
            print(f'与已有清单 {path} 不符：', file=out)
            for pr in probs[:10]:
                print(f'  {pr}', file=out)
            rc = 1
        else:
            print(f'与已有清单 {path} 相符。', file=out)
    else:
        print(f'还没有清单 {path}。', file=out)
        if a.check:
            rc = 1
    if a.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_manifest(m), encoding='utf-8', newline='\n')
        print(f'已写入 {path}', file=out)
        rc = 0
    return rc


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='canon_text', description='原文与证据锚点工具（docs/CANON_SCHEMA.md 第 14 节）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('info', help='各回标题/段数/句数/字数')
    add_source_args(sp)
    sp.set_defaults(fn=cmd_info)

    sp = sub.add_parser('export', help='导出成 DIR/chapters/chNN.txt，每行 “[c回p段] 段落文字”')
    add_source_args(sp)
    g = sp.add_mutually_exclusive_group()
    g.add_argument('--ch', help='回号：3 / 1-5 / 1,3,7-9')
    g.add_argument('--all', action='store_true', help='全部回（含 0 卷首、51 后记、52 附录）')
    sp.add_argument('--out', default=str(S.REPO_ROOT / 'out' / 'canon' / 'chapters'),
                    help='输出目录（默认 out/canon/chapters；给 out/canon 则写到 out/canon/chapters）')
    sp.set_defaults(fn=cmd_export)

    sp = sub.add_parser('show', help='终端打印某回')
    add_source_args(sp)
    sp.add_argument('ch', type=int)
    sp.add_argument('--from', dest='from_', type=int, metavar='P', help='起始段号（1 起）')
    sp.add_argument('--to', type=int, metavar='Q', help='结束段号（含）')
    sp.set_defaults(fn=cmd_show)

    sp = sub.add_parser('find', help='检索：列出命中段编号与每回计数（不打印整段）')
    add_source_args(sp)
    sp.add_argument('needle', metavar='字符串')
    sp.add_argument('--ch', type=int, help='只查这一回')
    sp.add_argument('--limit', type=int, default=12, help='每回最多列出的命中数')
    sp.add_argument('--all', action='store_true', help='每回命中全部列出')
    sp.set_defaults(fn=cmd_find)

    sp = sub.add_parser('ptr', help='把锚点解析成指针 [回,段,起,止,哈希]')
    add_source_args(sp)
    sp.add_argument('ch', type=int)
    sp.add_argument('para', type=int)
    sp.add_argument('anchor', metavar='锚点', help=f'该段里的一小段原文，<= {A.ANCHOR_MAX} 字')
    sp.add_argument('--nth', type=int, help='锚点在段内出现多次时，取第几次（从 1 起）')
    sp.set_defaults(fn=cmd_ptr)

    sp = sub.add_parser('verify-evidence', help='核对文件/目录里的全部证据指针')
    add_source_args(sp)
    sp.add_argument('paths', nargs='+', metavar='FILE|DIR')
    sp.add_argument('--max-errors', type=int, default=20)
    sp.set_defaults(fn=cmd_verify)

    sp = sub.add_parser('manifest', help='生成/核对 data/canon/text_manifest.json')
    add_source_args(sp)
    sp.add_argument('--write', action='store_true', help='写入清单')
    sp.add_argument('--check', action='store_true', help='只核对；没有清单或不符则退出码 1')
    sp.set_defaults(fn=cmd_manifest)

    a = ap.parse_args(argv)
    try:
        return a.fn(a, out)
    except BrokenPipeError:
        return 0
    except FileNotFoundError as ex:
        print(f'错误：{ex}', file=out)
        return 2
    except T.TextFormatError as ex:
        print(f'错误：原文版面不符：{ex}', file=out)
        return 2
    except ValueError as ex:
        print(f'错误：{ex}', file=out)
        return 1


if __name__ == '__main__':
    sys.exit(main())
