"""证据锚点：把“短锚点”解析成证据指针 [回,段,起,止,哈希]，并核对带指针的文件（tools/canon_resolve.py 的实现）。

抽取代理写证据时**不必算字位与哈希**，只写  [回,段,"锚点"]  或  [回,段,"锚点",第几次]：
  * 锚点 = 该段里的一小段原文（1–20 字），用来定位；解析后**锚点丢弃，不留存引文**，只剩指针；
  * 锚点在段内出现多次时必须给“第几次”（从 1 起，按出现顺序，重叠的算不同次），否则报错并列出各位置；
  * 解析出的指针恰好覆盖锚点那几个字：[回,段,起,止,哈希]。
本模块只处理 JSONL 里的证据字段：紧凑断言的 e、完整断言的 evidence、事件/秘密/身份的 ev（按行里有哪个键）。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import schema as S
from . import text as T

ANCHOR_MAX = 20
EVIDENCE_KEYS = ('e', 'evidence', 'ev')


class AnchorError(ValueError):
    """锚点无法解析成唯一指针。"""


def anchor_positions(text, anchor):
    """anchor 在 text 里的所有起点（重叠的也算）。"""
    out, i = [], text.find(anchor)
    while i != -1:
        out.append(i)
        i = text.find(anchor, i + 1)
    return out


def resolve_anchor(store, ch, para, anchor, nth=None):
    """-> 紧凑指针 [回,段,起,止,哈希]；失败抛 AnchorError（消息里列出原因与各位置，不含原文）。"""
    if not isinstance(anchor, str) or not anchor:
        raise AnchorError('锚点须为非空字符串')
    if len(anchor) > ANCHOR_MAX:
        raise AnchorError(f'锚点 {len(anchor)} 字，超过上限 {ANCHOR_MAX} 字（锚点只用来定位，取最能唯一定位的一小段）')
    try:
        p = store.paragraph(ch, para)
    except KeyError as ex:
        raise AnchorError(str(ex.args[0]))
    pos = anchor_positions(p.text, anchor)
    if not pos:
        raise AnchorError(f'第 {ch} 回第 {para} 段（c{ch}p{para}）里找不到这个锚点（段长 {len(p.text)} 字）；'
                          f'可用 tools/canon_text.py find 检索，或换一小段')
    if nth is None:
        if len(pos) > 1:
            raise AnchorError(f'锚点在 c{ch}p{para} 里出现 {len(pos)} 次（起点 {", ".join(map(str, pos))}）：'
                              f'请加“第几次”参数 [回,段,"锚点",K]，或换更长的锚点')
        k = 0
    else:
        if isinstance(nth, bool) or not isinstance(nth, int) or nth < 1:
            raise AnchorError(f'“第几次”须为 >=1 的整数，得到 {nth!r}')
        if nth > len(pos):
            raise AnchorError(f'锚点在 c{ch}p{para} 里只出现 {len(pos)} 次（起点 {", ".join(map(str, pos))}），没有第 {nth} 次')
        k = nth - 1
    return [ch, para, pos[k], pos[k] + len(anchor), p.hash]


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def classify_item(item):
    """证据项 -> ('pointer', 完整指针dict) | ('anchor', (回, 段, 锚点, 第几次|None)) | ('bad', 原因)。"""
    if isinstance(item, dict):
        return ('pointer', dict(item))
    if isinstance(item, (list, tuple)):
        if len(item) == 5 and isinstance(item[4], str):
            return ('pointer', S.expand_pointer(item))
        if len(item) in (3, 4) and _is_int(item[0]) and _is_int(item[1]) and isinstance(item[2], str):
            return ('anchor', (item[0], item[1], item[2], item[3] if len(item) == 4 else None))
    return ('bad', '证据项须为指针 [回,段,起,止,哈希]，或锚点 [回,段,"锚点"] / [回,段,"锚点",第几次]')


def evidence_key(row):
    """行里证据字段的键（e / evidence / ev）；没有返回 None。"""
    for k in EVIDENCE_KEYS:
        if k in row:
            return k
    return None


def check_pointer_item(store, p):
    """完整指针 -> 原因字符串或 None（能取回、哈希相符、取回非空）。"""
    why = store.check_pointer(p)
    if why:
        return why
    q = S.expand_pointer(p)
    if q['end'] <= q['start']:
        return '指针取回的是空串（起 = 止）'
    return None


# ----------------------------------------------------------------------------------------------------------------------
# canon_resolve：原地改写
# ----------------------------------------------------------------------------------------------------------------------
@dataclass
class FileReport:
    path: str
    rows: int = 0                     # 非空非注释行
    with_evidence: int = 0            # 有证据项的行
    rewritten: int = 0                # 被改写的行
    anchors: int = 0                  # 解析出的锚点数
    pointers: int = 0                 # 原本就是指针的项数
    errors: list = field(default_factory=list)    # [(行号, 原因)]


def _with_basis(row, ekey):
    """给行补 basis = text，放在证据字段前面：完整格式的断言行（有 subject/property/evidence/basis）用 basis，其余用紧凑键 b。
    返回新 dict。"""
    long_style = any(k in row for k in ('basis', 'subject', 'property', 'evidence'))
    key = 'b' if 'b' in row else 'basis' if long_style else 'b'
    if row.get(key) == 'text':
        return row
    out = {}
    done = False
    for k, v in row.items():
        if k == key:
            out[k] = 'text'
            done = True
            continue
        if k == ekey and not done:
            out[key] = 'text'
            done = True
        out[k] = v
    if not done:
        out[key] = 'text'
    return out


def resolve_row(store, row):
    """解析一行（dict）里的证据项。返回 (新行 或 None[无需改动], 锚点数, 原指针数, 错误列表)。
    只要有一项失败，整行不改（返回 None 与错误）。"""
    ekey = evidence_key(row)
    if ekey is None:
        return None, 0, 0, []
    items = row[ekey]
    if not isinstance(items, list):
        return None, 0, 0, [f'{ekey} 须为数组']
    if not items:
        return None, 0, 0, []
    errs, new, n_anchor, n_ptr = [], [], 0, 0
    for i, it in enumerate(items):
        kind, val = classify_item(it)
        if kind == 'bad':
            errs.append(f'{ekey}[{i}]: {val}')
        elif kind == 'pointer':
            n_ptr += 1
            why = check_pointer_item(store, val)
            if why:
                errs.append(f'{ekey}[{i}]: 已有指针取不回原字：{why}')
            else:
                new.append(S.compact_pointer(S.expand_pointer(val)))
        else:
            ch, para, anchor, nth = val
            try:
                new.append(resolve_anchor(store, ch, para, anchor, nth))
                n_anchor += 1
            except AnchorError as ex:
                errs.append(f'{ekey}[{i}]: {ex}')
    if errs:
        return None, 0, 0, errs
    dedup = []
    for p in new:
        if p not in dedup:
            dedup.append(p)
    out = {k: (dedup if k == ekey else v) for k, v in row.items()}
    out = _with_basis(out, ekey)
    if out == row:
        return None, 0, n_ptr, []
    return out, n_anchor, n_ptr, []


def resolve_file(store, path, dry_run=False):
    """原地改写一个 JSONL 文件：锚点 -> 指针，补 b=text。失败的行不改。返回 FileReport。"""
    p = Path(path)
    rep = FileReport(str(p))
    data = p.read_bytes()
    bom = data.startswith(b'\xef\xbb\xbf')                  # 保留 BOM 与行尾（read_text 会把 CRLF 变成 LF，所以读字节）
    lines = data.decode('utf-8-sig').split('\n')
    changed = False
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        rep.rows += 1
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as ex:
            rep.errors.append((n, f'JSON 解析失败（{ex.msg}，列 {ex.colno}）'))
            continue
        if not isinstance(obj, dict):
            rep.errors.append((n, '行须为 JSON 对象'))
            continue
        ekey = evidence_key(obj)
        if ekey is not None and isinstance(obj[ekey], list) and obj[ekey]:
            rep.with_evidence += 1
        new, n_anchor, n_ptr, errs = resolve_row(store, obj)
        for e in errs:
            rep.errors.append((n, e))
        rep.pointers += n_ptr
        if new is not None:
            rep.anchors += n_anchor
            rep.rewritten += 1
            tail = '\r' if line.endswith('\r') else ''
            lines[n - 1] = S.dumps_line(new) + tail
            changed = True
    if changed and not dry_run:
        tmp = p.with_name(p.name + '.tmp')
        tmp.write_bytes((('\ufeff' if bom else '') + '\n'.join(lines)).encode('utf-8'))
        os.replace(tmp, p)
    return rep


def main(argv=None, out=None):
    import argparse
    from . import textcli
    out = out or sys.stdout
    ap = argparse.ArgumentParser(
        prog='canon_resolve',
        description='把紧凑 JSONL 里的证据锚点 [回,段,"锚点"] / [回,段,"锚点",第几次] 原地改写成指针 [回,段,起,止,哈希]'
                    '（锚点丢弃，不留存引文），并给有证据的行补 "b":"text"。解析失败的行列成错误清单且不改动该行。')
    ap.add_argument('files', nargs='+', metavar='FILE', help='JSONL 文件（断言、事件、秘密、身份……）；目录则取其中所有 *.jsonl')
    textcli.add_source_args(ap)
    ap.add_argument('--dry-run', action='store_true', help='只检查，不写文件')
    a = ap.parse_args(argv)
    try:
        store = textcli.open_store(a)
    except (OSError, T.TextFormatError) as ex:
        print(f'错误：{ex}', file=out)
        return 2
    files = []
    for f in a.files:
        pf = Path(f)
        if not pf.exists():
            print(f'错误：路径不存在：{f}', file=out)
            return 2
        files.extend(S.list_jsonl_files(pf))
    reps = [resolve_file(store, f, a.dry_run) for f in files]
    n_err = sum(len(r.errors) for r in reps)
    for r in reps:
        print(f'{r.path}：{r.rows} 行，有证据 {r.with_evidence}，改写 {r.rewritten}，锚点解析 {r.anchors}，'
              f'原有指针 {r.pointers}，错误 {len(r.errors)}', file=out)
        for n, e in r.errors:
            print(f'  {Path(r.path).name}:{n}: {e}', file=out)
    print(f'汇总：{len(reps)} 个文件，改写 {sum(r.rewritten for r in reps)} 行，锚点 {sum(r.anchors for r in reps)} 个'
          f'{"（dry-run，未写文件）" if a.dry_run else ""}；错误行 {n_err} -> ' + ('通过' if n_err == 0 else '有错误，见上'), file=out)
    return 0 if n_err == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
