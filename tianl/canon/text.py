"""第 0–2 阶段（计划 3.2）：规范化、提及普查、消歧合并。原文只在本地（sources/），游戏库只存指针。

阶段 0 规范化   decode_bytes / normalize / TextStore.from_text：统一编码、去 BOM 与 CRLF、按“第X回”切回、切段、切句，
                稳定编号 c{回}p{段}s{句}，段落哈希 = sha256(规范化段落)前 16 位；get_span(指针) 取回原字并校验哈希。
阶段 1 提及普查 SurfaceIndex / census_mentions：用实体表的名与别名做最长匹配，输出提及表（实体、回、段、起止字位）。
阶段 2 消歧合并 resolve_mentions：别名/称呼/“以某身份出现”归到同一实体；check_single_referent 检查
                “同一段内一个称呼只指一个实体”。

约定：
  * 段内字位 (start, end) 为左闭右开、0 起、按规范化后的字符计。
  * 第 0 回是第一个“第X回”之前的卷首文字；没有任何回标题时整篇当作第 1 回，并在 meta['warnings'] 里记一笔。
  * 文本若按固定列宽硬折行，则每一行会被当成一段（本模块不做反折行）。
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import schema as S

# ----------------------------------------------------------------------------------------------------------------------
# 阶段 0：规范化
# ----------------------------------------------------------------------------------------------------------------------
_CN_DIGIT = {'零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_CN_UNIT = {'十': 10, '百': 100, '千': 1000}


def cn2int(s):
    """‘第’与‘回’之间的数字：阿拉伯（含全角）或中文数字（一百零二、十五、二十）。失败返回 None。"""
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    total, cur = 0, 0
    for c in s:
        if c in _CN_DIGIT:
            cur = _CN_DIGIT[c]
        elif c in _CN_UNIT:
            total += (cur or 1) * _CN_UNIT[c]
            cur = 0
        else:
            return None
    return total + cur


def decode_bytes(b):
    """字节 -> (文本, 编码名)。依次试 UTF-8(含 BOM)、UTF-16(有 BOM)、GB18030。"""
    if b.startswith(b'\xff\xfe') or b.startswith(b'\xfe\xff'):
        return b.decode('utf-16'), 'utf-16'
    for enc in ('utf-8-sig', 'gb18030'):
        try:
            return b.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return b.decode('utf-8', errors='replace'), 'utf-8-replace'


_ZERO_WIDTH = dict.fromkeys(map(ord, '﻿​‌‍⁠­'), None)


def normalize(text):
    """统一为 NFC，去 BOM 与零宽字符，CRLF/CR/换页 -> LF，去其余控制字符，不间断空格 -> 空格。"""
    text = unicodedata.normalize('NFC', text).translate(_ZERO_WIDTH)
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\x0b', '\n').replace('\x0c', '\n')
    text = text.replace(' ', ' ')
    return ''.join(c for c in text if c in '\n\t' or unicodedata.category(c) != 'Cc')


def para_hash(text):
    """段落哈希：规范化段落文本 UTF-8 的 sha256 前 16 位。"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


_TERM = frozenset('。！？!?')
_CLOSERS = frozenset('”’」』）)》】"\'')


def split_sentences(p):
    """段落 -> [(起, 止)]。以 。！？ 为句末（连续的算一个），后随的右引号/括号并入本句；
    省略号 …… 只在其后是右引号或段末时才算句末。"""
    res, n, start, i = [], len(p), 0, 0
    while i < n:
        c = p[i]
        if c in _TERM:
            j = i + 1
            while j < n and p[j] in _TERM:
                j += 1
        elif c == '…':
            j = i
            while j < n and p[j] == '…':
                j += 1
            if j < n and p[j] not in _CLOSERS:
                i = j
                continue
        else:
            i += 1
            continue
        while j < n and p[j] in _CLOSERS:
            j += 1
        res.append((start, j))
        start = i = j
    if start < n:
        res.append((start, n))
    return res


_HEADER_RE = re.compile(r'^第\s*([0-9０-９零〇一二两三四五六七八九十百千]+)\s*[回章](?P<title>.*)$')


def parse_header(line):
    """是回标题行则返回 (回号, 标题)，否则 None。标题行不超过 60 字。"""
    s = line.strip()
    if not s or len(s) > 60:
        return None
    m = _HEADER_RE.match(s)
    if not m:
        return None
    n = cn2int(m.group(1))
    if n is None:
        return None
    return n, m.group('title').strip(' 　:：、.．-—')


@dataclass
class Paragraph:
    ch: int
    idx: int                # 1 起
    text: str
    hash: str
    sentences: list         # [(起, 止)]


@dataclass
class Chapter:
    num: int
    title: str
    paragraphs: list = field(default_factory=list)


class SpanError(ValueError):
    """指针取不回原字（回/段不存在、字位越界、哈希不符）。"""


_SID_RE = re.compile(r'^c(\d+)p(\d+)s(\d+)$')


def sentence_id(ch, para, k):
    return f'c{ch}p{para}s{k}'


def parse_sentence_id(sid):
    m = _SID_RE.match(sid) if isinstance(sid, str) else None
    if not m:
        raise ValueError(f'不是句子编号（c回p段s句）：{sid!r}')
    return tuple(int(x) for x in m.groups())


class TextStore:
    """源文本库：回 -> 段 -> 句。由 from_text / from_file 构造。"""

    def __init__(self, chapters, meta=None):
        self.chapters = chapters            # {回号: Chapter}
        self.meta = meta or {}
        self.meta.setdefault('warnings', [])

    # ---- 构造 ----
    @classmethod
    def from_text(cls, text, normalized=False):
        if not normalized:
            text = normalize(text)
        warnings = []
        segs = []                           # [(num, title, [行])]
        cur = (0, '', [])
        for line in text.split('\n'):
            h = parse_header(line)
            if h:
                segs.append(cur)
                cur = (h[0], h[1], [])
            else:
                cur[2].append(line)
        segs.append(cur)
        segs = [sg for sg in segs if sg[0] != 0 or any(ln.strip() for ln in sg[2])]
        if not any(sg[0] for sg in segs):
            warnings.append('未找到“第X回”标题：整篇当作第 1 回')
            segs = [(1, '', [ln for sg in segs for ln in sg[2]])]
        best = {}
        for num, title, lines in segs:      # 同号取正文最长者（目录与正文都有标题时，目录条目正文为空）
            body = sum(len(ln.strip()) for ln in lines)
            if num in best:
                warnings.append(f'第 {num} 回标题出现多次，保留正文最长的一处')
                if body >= best[num][0]:
                    best[num] = (body, title, lines)
            else:
                best[num] = (body, title, lines)
        chapters = {}
        for num in sorted(best):
            _, title, lines = best[num]
            ch = Chapter(num, title)
            for ln in lines:
                t = ln.strip()
                if not t:
                    continue
                ch.paragraphs.append(Paragraph(num, len(ch.paragraphs) + 1, t, para_hash(t), split_sentences(t)))
            chapters[num] = ch
        nums = [n for n in chapters if n > 0]
        if nums:
            missing = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
            if missing:
                warnings.append(f'回号不连续，缺：{missing}')
        return cls(chapters, {'warnings': warnings})

    @classmethod
    def from_bytes(cls, b):
        text, enc = decode_bytes(b)
        st = cls.from_text(text)
        st.meta['encoding'] = enc
        return st

    @classmethod
    def from_file(cls, path):
        return cls.from_bytes(Path(path).read_bytes())

    # ---- 取用 ----
    def paragraph(self, ch, para):
        c = self.chapters.get(ch)
        if c is None or not isinstance(para, int) or not 1 <= para <= len(c.paragraphs):
            raise KeyError(f'没有第 {ch} 回第 {para} 段')
        return c.paragraphs[para - 1]

    def iter_paragraphs(self):
        for n in sorted(self.chapters):
            yield from self.chapters[n].paragraphs

    def pointer(self, ch, para, start=0, end=None):
        """造一个证据指针（完整格式 dict）。"""
        p = self.paragraph(ch, para)
        end = len(p.text) if end is None else end
        if not 0 <= start <= end <= len(p.text):
            raise SpanError(f'字位越界：{start}..{end}（段长 {len(p.text)}）')
        return {'ch': ch, 'para': para, 'start': start, 'end': end, 'hash': p.hash}

    def check_pointer(self, ptr):
        """能取回则返回 None，否则返回原因字符串。ptr 可为 dict 或 [回,段,起,止,哈希]。"""
        ptr = S.expand_pointer(ptr)
        errs = S.validate_pointer(ptr)
        if errs:
            return '；'.join(errs)
        try:
            p = self.paragraph(ptr['ch'], ptr['para'])
        except KeyError as ex:
            return str(ex.args[0])
        if p.hash != ptr['hash']:
            return f'哈希不符：指针 {ptr["hash"]}，原文 {p.hash}（原文版本不同或已被改动）'
        if ptr['end'] > len(p.text):
            return f'字位越界：end={ptr["end"]} > 段长 {len(p.text)}'
        return None

    def get_span(self, ptr):
        """按指针取回原字；失败抛 SpanError。"""
        why = self.check_pointer(ptr)
        if why:
            raise SpanError(why)
        ptr = S.expand_pointer(ptr)
        return self.paragraph(ptr['ch'], ptr['para']).text[ptr['start']:ptr['end']]

    def get_sentence(self, sid):
        ch, para, k = parse_sentence_id(sid)
        p = self.paragraph(ch, para)
        if not 1 <= k <= len(p.sentences):
            raise SpanError(f'没有句子 {sid}（该段共 {len(p.sentences)} 句）')
        a, b = p.sentences[k - 1]
        return p.text[a:b]

    def sentence_pointer(self, sid):
        ch, para, k = parse_sentence_id(sid)
        p = self.paragraph(ch, para)
        if not 1 <= k <= len(p.sentences):
            raise SpanError(f'没有句子 {sid}')
        a, b = p.sentences[k - 1]
        return self.pointer(ch, para, a, b)

    def stats(self):
        paras = list(self.iter_paragraphs())
        return {'chapters': len([n for n in self.chapters if n > 0]), 'has_front_matter': 0 in self.chapters,
                'paragraphs': len(paras), 'sentences': sum(len(p.sentences) for p in paras),
                'chars': sum(len(p.text) for p in paras)}

    # ---- 哈希索引（不含原文，可入库/比对）----
    def index(self):
        return {'version': 1, 'chapters': [
            {'ch': n, 'title': c.title, 'paras': [[p.idx, len(p.text), p.hash, len(p.sentences)] for p in c.paragraphs]}
            for n, c in sorted(self.chapters.items())]}

    def check_index(self, index):
        """用已存的索引复核本库：段落哈希可复算。返回错误列表。"""
        errs = []
        have = {n: c for n, c in self.chapters.items()}
        for ch in index.get('chapters', []):
            c = have.get(ch['ch'])
            if c is None:
                errs.append(f'索引里的第 {ch["ch"]} 回在文本里不存在')
                continue
            if len(c.paragraphs) != len(ch['paras']):
                errs.append(f'第 {ch["ch"]} 回段数不符：索引 {len(ch["paras"])}，文本 {len(c.paragraphs)}')
                continue
            for (idx, ln, h, ns), p in zip(ch['paras'], c.paragraphs):
                if (ln, h) != (len(p.text), p.hash):
                    errs.append(f'第 {ch["ch"]} 回第 {idx} 段哈希或长度不符')
        return errs


# ----------------------------------------------------------------------------------------------------------------------
# 阶段 1：提及普查
# ----------------------------------------------------------------------------------------------------------------------
class SurfaceIndex:
    """称呼 -> 候选实体。名与别名都算称呼；短于 min_len 的称呼不入索引（见 skipped）。
    identities（“以某身份出现”表的行）里登记表没有的 as_name 也作为称呼加入，指向真身。"""

    def __init__(self, entities, identities=None, min_len=2):
        self.min_len = min_len
        self.cands = {}                 # 称呼 -> 编号元组（已排序）
        self.ambiguous = set()          # 登记行里标了 ambiguous 的称呼
        self.names = {}                 # 编号 -> 规范名
        self.types = {}
        self.skipped = []               # 因太短被忽略的称呼
        self.identities = [S.expand_identity(r) for r in (identities or [])]
        tmp = {}
        for row in entities:
            row, _ = S.normalize_entity_row(row)
            eid = row['id']
            self.names[eid] = row['name']
            self.types[eid] = row['type']
            for sf in [row['name']] + list(row.get('aliases', [])):
                if len(sf) < min_len:
                    self.skipped.append((eid, sf))
                    continue
                tmp.setdefault(sf, set()).add(eid)
            for sf in row.get('amb', []):
                self.ambiguous.add(sf)
        self.ident_only = set()
        for r in self.identities:
            nm = r.get('as_name')
            if isinstance(nm, str) and len(nm) >= min_len and nm not in tmp and r.get('person'):
                tmp.setdefault(nm, set()).add(r['person'])
                self.ident_only.add(nm)
        self.cands = {k: tuple(sorted(v)) for k, v in tmp.items()}
        self.maxlen = max((len(k) for k in self.cands), default=0)
        self.first = {k[0] for k in self.cands}

    def match_at(self, text, i):
        """text[i:] 起最长匹配的称呼，没有返回 None。"""
        if text[i] not in self.first:
            return None
        for ln in range(min(self.maxlen, len(text) - i), self.min_len - 1, -1):
            sf = text[i:i + ln]
            if sf in self.cands:
                return sf
        return None


@dataclass
class Mention:
    ch: int
    para: int
    start: int
    end: int
    surface: str
    cands: tuple
    entity: str | None = None       # 消歧后的真身
    seen_as: str | None = None      # 见闻里看见的身份（易容/化名时与 entity 不同）
    via: str = ''                   # unique 唯一候选 / context 上下文 / identity 身份表 / ''未消歧
    twin: bool = False              # 候选只是同名的不同类型（如 少林寺 的组织与地点），整组视为同一所指

    def entities(self):
        if self.entity:
            return [self.entity]
        return list(self.cands) if self.twin else []

    def to_row(self):
        r = {'ch': self.ch, 'para': self.para, 'start': self.start, 'end': self.end, 'surface': self.surface,
             'entity': self.entity}
        if len(self.cands) > 1:
            r['cands'] = list(self.cands)
        if self.twin:
            r['twin'] = True
        if self.seen_as:
            r['seen_as'] = self.seen_as
        if self.via:
            r['via'] = self.via
        return r


def _twin_group(cands):
    """候选编号的名字部分（canon: 之后）全相同、只是类型不同，则视为同名孪生组。"""
    return len(cands) > 1 and len({c.split(':', 2)[2] for c in cands}) == 1


def census_mentions(store, index):
    """阶段 1：逐段做最长匹配（从左到右、互不重叠），返回提及列表（尚未消歧：唯一候选的已填 entity）。"""
    out = []
    for p in store.iter_paragraphs():
        t, n, i = p.text, len(p.text), 0
        while i < n:
            sf = index.match_at(t, i)
            if sf is None:
                i += 1
                continue
            c = index.cands[sf]
            m = Mention(p.ch, p.idx, i, i + len(sf), sf, c)
            if len(c) == 1:
                m.entity, m.via = c[0], 'unique'
            elif _twin_group(c):
                m.twin = True
            out.append(m)
            i += len(sf)
    return out


def verify_mentions(store, mentions):
    """阶段 1 的机器校验：按字位能在原文取回同样的字。返回错误列表。"""
    errs = []
    for m in mentions:
        try:
            got = store.paragraph(m.ch, m.para).text[m.start:m.end]
        except KeyError as ex:
            errs.append(f'提及 {m.surface}@{m.ch}/{m.para}: {ex.args[0]}')
            continue
        if got != m.surface:
            errs.append(f'提及 {m.surface}@{m.ch}/{m.para}[{m.start}:{m.end}] 取回的是 {got!r}')
    return errs


# ----------------------------------------------------------------------------------------------------------------------
# 阶段 2：消歧合并
# ----------------------------------------------------------------------------------------------------------------------
@dataclass
class ResolveResult:
    mentions: list
    unresolved: list
    violations: list
    report: dict


def _in_range(rng, ch):
    return rng is None or rng[0] <= ch <= rng[1]


def resolve_mentions(store, mentions, index, window=1):
    """阶段 2：
      1. 身份表：称呼是某条“以某身份出现”的 as_name 且（有 ch 范围时）回数落在范围内 -> 归到真身 person，
         seen_as 记所扮的人（as_person）或 as_name 本身；
      2. 唯一候选 -> 直接确定；
      3. 多候选 -> 看前后 window 段里各候选的“无歧义提及”条数，最多者胜（须严格多于第二名），否则留作未消歧；
      4. 同一（回，段，称呼）只解析一次，保证同段内一个称呼只指一个实体。
    返回 ResolveResult（mentions 为就地更新后的同一批对象）。"""
    # 1. 身份表（只处理带 ch 范围、或 as_name 不在登记表里的行，避免全书劫持已登记称呼）
    by_surface = {}
    for r in index.identities:
        nm = r.get('as_name')
        if not isinstance(nm, str) or not r.get('person'):
            continue
        if r.get('ch') is None and nm not in index.ident_only:
            continue
        by_surface.setdefault(nm, []).append(r)
    for m in mentions:
        for r in by_surface.get(m.surface, []):
            if _in_range(r.get('ch'), m.ch):
                m.entity = r['person']
                m.seen_as = r.get('as_person') or m.surface     # 看见的身份：所扮之人的编号，或这个称呼本身
                m.via, m.twin = 'identity', False
                break
    # 2/3. 上下文消歧：先统计各段“无歧义”提及
    solid = {}                                      # (回, 段) -> {编号: 条数}
    for m in mentions:
        if m.entity:
            d = solid.setdefault((m.ch, m.para), {})
            d[m.entity] = d.get(m.entity, 0) + 1
    decided = {}                                    # (回, 段, 称呼) -> (实体|None)
    for m in mentions:
        if m.entity or m.twin:
            continue
        key = (m.ch, m.para, m.surface)
        if key not in decided:
            score = {c: 0 for c in m.cands}
            for q in range(m.para - window, m.para + window + 1):
                for e, n in solid.get((m.ch, q), {}).items():
                    if e in score:
                        score[e] += n
            ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
            decided[key] = ranked[0][0] if ranked[0][1] > 0 and (len(ranked) < 2 or ranked[0][1] > ranked[1][1]) \
                else None
        if decided[key]:
            m.entity, m.via = decided[key], 'context'
    unresolved = [m for m in mentions if not m.entity and not m.twin]
    violations = check_single_referent(mentions)
    counts = {'mentions': len(mentions), 'unique': 0, 'context': 0, 'identity': 0, 'twin': 0,
              'unresolved': len(unresolved)}
    for m in mentions:
        if m.via in counts:
            counts[m.via] += 1
        if m.twin:
            counts['twin'] += 1
    return ResolveResult(mentions, unresolved, violations, counts)


def check_single_referent(mentions):
    """阶段 2 的机器校验：同一段内一个称呼只指一个实体。返回违规列表（字符串）。
    未消歧（entity 为空）的不算违规，由 unresolved 另行报告。"""
    seen, errs = {}, []
    for m in mentions:
        if not m.entity:
            continue
        k = (m.ch, m.para, m.surface)
        if k in seen and seen[k] != m.entity:
            errs.append(f'第 {m.ch} 回第 {m.para} 段：称呼“{m.surface}”同时指 {seen[k]} 与 {m.entity}')
        seen.setdefault(k, m.entity)
    return errs


def build_alias_table(entities):
    """别名表：称呼 -> {'ids': [...], 'ambiguous': bool}（按类型不分，供人看与消歧用）。"""
    tab = {}
    for row in entities:
        row, _ = S.normalize_entity_row(row)
        for sf in [row['name']] + list(row.get('aliases', [])):
            d = tab.setdefault(sf, {'ids': [], 'ambiguous': False})
            if row['id'] not in d['ids']:
                d['ids'].append(row['id'])
            if sf in row.get('amb', []):
                d['ambiguous'] = True
    for d in tab.values():
        d['ids'].sort()
    return tab


def mention_counts(mentions):
    """{实体编号: 提及条数}（孪生组计入每个成员）。"""
    c = {}
    for m in mentions:
        for e in m.entities():
            c[e] = c.get(e, 0) + 1
    return c


def paragraph_entities(mentions):
    """{(回, 段): {实体编号}}：用于给断言找“主体与值同段出现”的候选证据段。"""
    d = {}
    for m in mentions:
        for e in m.entities():
            d.setdefault((m.ch, m.para), set()).add(e)
    return d


def write_mentions(path, mentions):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        for m in mentions:
            f.write(json.dumps(m.to_row(), ensure_ascii=False, separators=(',', ':')) + '\n')
