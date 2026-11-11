"""第 0–2 阶段（计划 3.2）：规范化、提及普查、消歧合并。原文只在本地（sources/），游戏库只存指针。

阶段 0 规范化   decode_bytes / normalize / clean_lines / TextStore.from_text：统一编码、去 BOM 与 CRLF、去水印与分隔行、
                按版面切回（0–52）、切段、切句，稳定编号 c{回}p{段}s{句}，段落哈希 = sha256(规范化段落)前 16 位；
                get_span(指针) 取回原字并校验哈希；manifest()/check_manifest() 生成与核对文本清单（只有哈希与计数）。
阶段 1 提及普查 SurfaceIndex / census_mentions：用实体表的名与别名做最长匹配，输出提及表（实体、回、段、起止字位）。
阶段 2 消歧合并 resolve_mentions：别名/称呼/“以某身份出现”归到同一实体；check_single_referent 检查
                “同一段内一个称呼只指一个实体”。

规范化规则（写死；改动要升 NORMALIZER_ID 并重生成 data/canon/text_manifest.json，见 docs/CANON_SCHEMA.md 第 15 节）：
  1. 编码：先按 UTF-8 严格解码（去 BOM），失败回退 GB18030（UTF-16 带 BOM 也认）；
  2. CRLF / CR / 换页 / 垂直制表 -> LF；去 BOM、零宽字符与其余控制字符；
  3. **不做 NFKC，也不做 NFC**（保持字数口径稳定）；全角字母数字、标点原样保留；
  4. 去水印：论坛页分隔水印“★Ｄ★Ｏ★Ｓ★Ｐ★Ｙ★”（独立成行或嵌在行尾，一律删去该标记），
     以 ☆/★ 开头并以 ☆/★ 结尾的整行（站点头尾），以及由 - 或 = 组成的分隔行（≥ 4 个）；
  5. 每行去两端空白（含全角空格）；**段 = 非空行**；空行丢弃。段内字符一律保持原样。
版面（三联版）：第 0 回 = 第一个回标题之前的卷首文字；回标题是顶格单独一行“<汉字数字> <标题>”，序号必须依次为 1、2、……
（不连续就抛 TextFormatError）；顶格单独一行“后记” = 第 51 回；顶格“附录 …”开头的行 = 第 52 回。
没有三联版标题时回退到旧的“第X回”版面；再没有则整篇当作第 1 回。
约定：
  * 段内字位 (start, end) 为左闭右开、0 起、按规范化后的字符计。
  * 文本若按固定列宽硬折行，则每一行会被当成一段（本模块不做反折行）。
"""
from __future__ import annotations

import bisect
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import schema as S

NORMALIZER_ID = 'canon-text-v2'
MANIFEST_FORMAT = 1
DEFAULT_SOURCE = S.REPO_ROOT / 'sources' / 'tianlong.txt'
MANIFEST_NAME = 'text_manifest.json'
BOOK_CHAPTERS = 50                  # 三联版正文回数
CH_POSTSCRIPT, CH_APPENDIX = 51, 52  # 后记、附录的回号


class TextFormatError(ValueError):
    """版面不符（回标题序号不连续、回数不对……）。"""


# ----------------------------------------------------------------------------------------------------------------------
# 阶段 0：规范化
# ----------------------------------------------------------------------------------------------------------------------
_CN_DIGIT = {'零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_CN_UNIT = {'十': 10, '百': 100, '千': 1000}


def cn2int(s):
    """汉字数字（一百零二、十五、二十）或阿拉伯数字（含全角）-> int。失败返回 None。"""
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
    """字节 -> (文本, 编码名)。依次试 UTF-16(有 BOM)、UTF-8(含 BOM)、GB18030。"""
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
    """字符级清理：去 BOM 与零宽字符，CRLF/CR/换页/垂直制表 -> LF，去其余控制字符。
    不做 NFC/NFKC，不改空白与标点（规则 1–3）。"""
    text = text.translate(_ZERO_WIDTH)
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\x0b', '\n').replace('\x0c', '\n')
    if any(unicodedata.category(c) == 'Cc' and c != '\n' for c in set(text)):
        text = ''.join(c for c in text if c == '\n' or unicodedata.category(c) != 'Cc')
    return text


def para_hash(text):
    """段落哈希：规范化段落文本 UTF-8 的 sha256 前 16 位。"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


# ---- 水印与分隔行 ----
_DOSPY = re.compile(r'★[ＤD]★[ＯO]★[ＳS]★[ＰP]★[ＹY]★')
_SITE = re.compile(r'^[☆★].*[☆★]$')
_SEP = re.compile(r'^[-－=＝_＿]{4,}$')


def clean_lines(text):
    """已 normalize 的全文 -> ([(原行号, 去两端空白的文本, 是否缩进)], 统计)。
    统计：blank_lines 空行 / separator_lines 分隔行 / watermark_tokens 页水印标记个数 / watermark_lines 只含标记的行 /
    site_lines 站点头尾行。缩进 = 原行以空白开头（正文段首有两个全角空格，回标题与卷首标题顶格）。"""
    st = {'blank_lines': 0, 'separator_lines': 0, 'watermark_tokens': 0, 'watermark_lines': 0, 'site_lines': 0}
    out = []
    for no, line in enumerate(text.split('\n'), 1):
        s = line.strip()
        if not s:
            st['blank_lines'] += 1
            continue
        if _SEP.match(s):
            st['separator_lines'] += 1
            continue
        if '★' in s or '☆' in s:
            parts = _DOSPY.split(line)
            st['watermark_tokens'] += len(parts) - 1
            first = True
            kept = 0
            for part in parts:
                ps = part.strip()
                if not ps:
                    first = False
                    continue
                if _SITE.match(ps):
                    st['site_lines'] += 1
                else:
                    out.append((no, ps, (part != part.lstrip()) if first else True))
                    kept += 1
                first = False
            if len(parts) > 1 and not kept:
                st['watermark_lines'] += 1
            continue
        out.append((no, s, line != line.lstrip()))
    return out, st


# ---- 句子 ----
_CLOSERS = '”’」』）)》】"\''
_SENT_RE = re.compile('(?:[。！？]+|…+(?=[' + re.escape(_CLOSERS) + ']|$))[' + re.escape(_CLOSERS) + ']*')


def split_sentences(p):
    """段落 -> [(起, 止)]。以 。！？ 为句末（连续的算一个），后随的右引号/括号并入本句；
    省略号 …… 只在其后是右引号/括号或段末时才算句末（句中停顿不切）；末尾无句末符的残余算一句。"""
    res, start = [], 0
    for m in _SENT_RE.finditer(p):
        res.append((start, m.end()))
        start = m.end()
    if start < len(p):
        res.append((start, len(p)))
    return res


# ---- 回标题 ----
_TITLE_RE = re.compile(r'^([零〇一二三四五六七八九十百]+)[ 　]+(\S.*)$')
_HEADER_RE = re.compile(r'^第\s*([0-9０-９零〇一二两三四五六七八九十百千]+)\s*[回章](?P<title>.*)$')


def parse_header(line):
    """旧版面：“第X回 标题”行。是回标题行则返回 (回号, 标题)，否则 None。标题行不超过 60 字。"""
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


class Paragraph:
    __slots__ = ('ch', 'idx', 'text', 'hash', '_sents')

    def __init__(self, ch, idx, text, hash=None, sentences=None):
        self.ch = ch
        self.idx = idx                  # 1 起
        self.text = text
        self.hash = hash or para_hash(text)
        self._sents = sentences

    @property
    def sentences(self):
        """[(起, 止)]，惰性计算。"""
        if self._sents is None:
            self._sents = split_sentences(self.text)
        return self._sents

    def __repr__(self):
        return f'Paragraph(c{self.ch}p{self.idx}, {len(self.text)}字)'


class Chapter:
    __slots__ = ('num', 'title', 'paragraphs')

    def __init__(self, num, title, paragraphs=None):
        self.num = num
        self.title = title
        self.paragraphs = paragraphs if paragraphs is not None else []

    def chars(self):
        return sum(len(p.text) for p in self.paragraphs)

    def body(self):
        """该回的规范化文本：各段以 LF 结尾连成（不含标题行）。"""
        return ''.join(p.text + '\n' for p in self.paragraphs)

    def hash16(self):
        return hashlib.sha256(self.body().encode('utf-8')).hexdigest()[:16]


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


def para_id(ch, para):
    return f'c{ch}p{para}'


def _split_sanlian(lines, expect=None):
    """三联版版面 -> [(回号, 标题, [段文本])]。严格：回标题序号必须依次为 1..k，否则抛 TextFormatError。"""
    segs = [[0, '卷首', []]]
    expected = 1
    has_post = has_app = False
    for no, t, indented in lines:
        if not indented:
            m = _TITLE_RE.match(t)
            n = cn2int(m.group(1)) if m else None
            if n is not None:
                if n != expected:
                    raise TextFormatError(f'第 {no} 行的回标题序号为 {n}，应为 {expected}（回标题必须依次出现、不得缺跳或重复）')
                segs.append([n, m.group(2).strip(), []])
                expected += 1
                continue
            if t == '后记' and expected > 1 and not has_post:
                segs.append([CH_POSTSCRIPT, '后记', []])
                has_post = True
                continue
            if t.startswith('附录') and expected > 1 and not has_app:
                segs.append([CH_APPENDIX, t, []])
                has_app = True
                continue
        segs[-1][2].append(t)
    if expected == 1:
        raise TextFormatError('没有找到三联版回标题（“一 标题”形式的顶格单独一行）')
    if expect and expected - 1 != expect:
        raise TextFormatError(f'应有 {expect} 回，实际只依次找到 {expected - 1} 回')
    return [tuple(sg) for sg in segs]


def _split_hui(lines):
    """旧版面：“第X回 标题”。同号取正文最长者；没有任何标题时整篇当作第 1 回。返回 (segs, warnings)。"""
    warnings = []
    segs = []
    cur = (0, '卷首', [])
    for _, t, _ in lines:
        h = parse_header(t)
        if h:
            segs.append(cur)
            cur = (h[0], h[1], [])
        else:
            cur[2].append(t)
    segs.append(cur)
    segs = [sg for sg in segs if sg[0] != 0 or sg[2]]
    if not any(sg[0] for sg in segs):
        warnings.append('未找到回标题：整篇当作第 1 回')
        segs = [(1, '', [t for sg in segs for t in sg[2]])]
    best = {}
    for num, title, ls in segs:
        body = sum(len(t) for t in ls)
        if num in best:
            warnings.append(f'第 {num} 回标题出现多次，保留正文最长的一处')
            if body >= best[num][0]:
                best[num] = (body, title, ls)
        else:
            best[num] = (body, title, ls)
    return [(n, best[n][1], best[n][2]) for n in sorted(best)], warnings


def default_manifest_path(canon_dir=None):
    return Path(canon_dir or S.CANON_DIR) / MANIFEST_NAME


class TextStore:
    """源文本库：回 -> 段 -> 句。由 from_text / from_bytes / from_file 构造。"""

    def __init__(self, chapters, meta=None):
        self.chapters = chapters            # {回号: Chapter}
        self.meta = meta or {}
        self.meta.setdefault('warnings', [])
        self._flat = None

    # ---- 构造 ----
    @classmethod
    def from_text(cls, text, normalized=False, layout='auto', expect_chapters=None):
        """layout：'auto'（有三联版标题则用之，否则旧的“第X回”）/ 'sanlian' / 'hui'。
        expect_chapters：只对三联版面生效，要求正好这么多回（BOOK_CHAPTERS = 50）。"""
        if not normalized:
            text = normalize(text)
        lines, clean = clean_lines(text)
        warnings = []
        if layout == 'auto':
            layout = 'sanlian' if any(not ind and (m := _TITLE_RE.match(t)) and cn2int(m.group(1)) == 1
                                      for _, t, ind in lines) else 'hui'
        if layout == 'sanlian':
            segs = _split_sanlian(lines, expect_chapters)
        elif layout == 'hui':
            segs, warnings = _split_hui(lines)
        else:
            raise ValueError(f'未知版面 {layout!r}')
        chapters = {}
        for num, title, ls in segs:
            if num == 0 and not ls:
                continue
            ch = Chapter(num, title)
            ch.paragraphs = [Paragraph(num, i, t) for i, t in enumerate(ls, 1)]
            chapters[num] = ch
        nums = [n for n in chapters if 0 < n <= BOOK_CHAPTERS]
        if nums:
            missing = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
            if missing:
                warnings.append(f'回号不连续，缺：{missing}')
        return cls(chapters, {'warnings': warnings, 'layout': layout, 'clean': clean})

    @classmethod
    def from_bytes(cls, b, **kw):
        text, enc = decode_bytes(b)
        st = cls.from_text(text, **kw)
        st.meta['encoding'] = enc
        return st

    @classmethod
    def from_file(cls, path, manifest=None, **kw):
        """manifest：None 不核对 / 'auto' 用 data/canon/text_manifest.json（有才核对）/ 清单文件路径 / 清单 dict。
        核对不符不抛错：问题写进 meta['manifest_problems']，并往 meta['warnings'] 加一条。"""
        st = cls.from_bytes(Path(path).read_bytes(), **kw)
        st.meta['path'] = str(path)
        if manifest is not None:
            st.apply_manifest(manifest)
        return st

    def apply_manifest(self, manifest):
        """核对文本清单；返回问题列表（空 = 相符或没有清单）。"""
        if manifest == 'auto':
            manifest = default_manifest_path()
        if isinstance(manifest, (str, Path)):
            p = Path(manifest)
            if not p.is_file():
                self.meta['manifest_problems'] = []
                self.meta['manifest'] = 'missing'
                return []
            manifest = json.loads(p.read_text(encoding='utf-8'))
        probs = self.check_manifest(manifest)
        self.meta['manifest'] = 'mismatch' if probs else 'ok'
        self.meta['manifest_problems'] = probs
        if probs:
            self.meta['warnings'].append(probs[0])
        return probs

    # ---- 取用 ----
    def paragraph(self, ch, para):
        c = self.chapters.get(ch)
        if c is None or not isinstance(para, int) or isinstance(para, bool) or not 1 <= para <= len(c.paragraphs):
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
        return {'chapters': len([n for n in self.chapters if 0 < n <= BOOK_CHAPTERS]),
                'has_front_matter': 0 in self.chapters,
                'paragraphs': len(paras), 'sentences': sum(len(p.sentences) for p in paras),
                'chars': sum(len(p.text) for p in paras)}

    def chapter_rows(self):
        """[(回, 标题, 段数, 字数)]，按回号。"""
        return [(n, c.title, len(c.paragraphs), c.chars()) for n, c in sorted(self.chapters.items())]

    # ---- 全书平铺索引：整本书的段以 LF 相连，便于整书子串检索 ----
    def flat_index(self):
        """-> (平铺文本, 各段起点列表, 各段(回, 段)列表)。平铺文本里段与段之间是一个 LF。"""
        if self._flat is None:
            parts, starts, keys, pos = [], [], [], 0
            for p in self.iter_paragraphs():
                starts.append(pos)
                keys.append((p.ch, p.idx))
                parts.append(p.text)
                pos += len(p.text) + 1
            self._flat = ('\n'.join(parts), starts, keys)
        return self._flat

    def locate(self, pos):
        """平铺位置 -> (回, 段, 段内偏移)。"""
        _, starts, keys = self.flat_index()
        i = bisect.bisect_right(starts, pos) - 1
        return keys[i][0], keys[i][1], pos - starts[i]

    def chapter_flat_range(self, ch):
        """某回在平铺文本里的 [lo, hi) 位置（没有这一回返回 None）。"""
        c = self.chapters.get(ch)
        if c is None or not c.paragraphs:
            return None
        flat, starts, keys = self.flat_index()
        i = bisect.bisect_left(keys, (ch, 1))
        j = bisect.bisect_right(keys, (ch, len(c.paragraphs)))
        return starts[i], starts[j - 1] + len(c.paragraphs[-1].text)

    def find(self, needle, ch=None, overlap=False):
        """全书（或某回）里 needle 的所有出现：[(回, 段, 段内偏移)]。needle 不得含换行。"""
        if not needle or '\n' in needle:
            raise ValueError('检索串须非空且不含换行')
        flat = self.flat_index()[0]
        lo, hi = 0, len(flat)
        if ch is not None:
            rng = self.chapter_flat_range(ch)
            if rng is None:
                return []
            lo, hi = rng
        out, step, i = [], (1 if overlap else len(needle)), flat.find(needle, lo, hi)
        while i != -1:
            out.append(self.locate(i))
            i = flat.find(needle, i + step, hi)
        return out

    # ---- 规范化文本的指纹与清单（不含任何原文字句以外的内容；标题是目录性质的短标签）----
    def canonical_text(self):
        """全书规范化文本：每回先一行“#回号 标题”，再各段（以 LF 结尾）。清单里的 text_sha256 就是它的 sha256。"""
        parts = []
        for n in sorted(self.chapters):
            c = self.chapters[n]
            parts.append(f'#{n} {c.title}\n')
            parts.append(c.body())
        return ''.join(parts)

    def text_sha256(self):
        return hashlib.sha256(self.canonical_text().encode('utf-8')).hexdigest()

    def manifest(self, edition='三联版'):
        st = self.stats()
        clean = self.meta.get('clean', {})
        return {
            'format': MANIFEST_FORMAT,
            'edition': edition,
            'normalizer': NORMALIZER_ID,
            'layout': self.meta.get('layout', ''),
            'text_sha256': self.text_sha256(),
            'totals': {'chapters': st['chapters'], 'paragraphs': st['paragraphs'], 'chars': st['chars']},
            'removed': {k: clean.get(k, 0) for k in ('watermark_tokens', 'site_lines', 'separator_lines')},
            'chapters': [{'ch': n, 'title': c.title, 'paras': len(c.paragraphs), 'chars': c.chars(),
                          'sha16': c.hash16()} for n, c in sorted(self.chapters.items())],
        }

    def check_manifest(self, manifest):
        """对照文本清单，返回问题列表（空 = 相符）。第一条是总括，其后逐项。"""
        probs = []
        if not isinstance(manifest, dict) or 'chapters' not in manifest:
            return ['文本清单格式不对（应含 chapters）']
        if manifest.get('normalizer') != NORMALIZER_ID:
            probs.append(f'清单的规范化规则是 {manifest.get("normalizer")!r}，当前代码是 {NORMALIZER_ID!r}：先重新生成清单')
        want = {c['ch']: c for c in manifest['chapters']}
        for n in sorted(set(want) | set(self.chapters)):
            w, c = want.get(n), self.chapters.get(n)
            if c is None:
                probs.append(f'第 {n} 回：清单有而原文没有')
            elif w is None:
                probs.append(f'第 {n} 回：原文有而清单没有')
            else:
                diffs = []
                if w.get('title') != c.title:
                    diffs.append(f'标题（清单 {w.get("title")!r}，原文 {c.title!r}）')
                if w.get('paras') != len(c.paragraphs):
                    diffs.append(f'段数（清单 {w.get("paras")}，原文 {len(c.paragraphs)}）')
                if w.get('chars') != c.chars():
                    diffs.append(f'字数（清单 {w.get("chars")}，原文 {c.chars()}）')
                if w.get('sha16') != c.hash16():
                    diffs.append('规范化文本哈希')
                if diffs:
                    probs.append(f'第 {n} 回：' + '、'.join(diffs) + ' 不符')
        if manifest.get('text_sha256') and manifest['text_sha256'] != self.text_sha256() and len(probs) == 0:
            probs.append('全书规范化文本哈希与清单不符（各回都相符，可能只是回标题或回序有变）')
        if probs:
            probs.insert(0, f'原文与文本清单 {MANIFEST_NAME} 不符（{len(probs)} 项）：这不是建清单时的那份原文，或规范化规则变了；'
                            f'已有证据指针的哈希可能失效。若确认换了版本，用 tools/canon_text.py manifest --write 重新生成')
        return probs

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


def find_source(path=None):
    """原文路径：显式给出的；否则 sources/tianlong.txt；否则 sources/ 下第一个 .txt；都没有返回 None。"""
    if path:
        return Path(path)
    if DEFAULT_SOURCE.is_file():
        return DEFAULT_SOURCE
    d = S.REPO_ROOT / 'sources'
    cands = sorted(d.glob('*.txt')) if d.is_dir() else []
    return cands[0] if cands else None


def load_book(path=None, canon_dir=None, expect_chapters=BOOK_CHAPTERS, check_manifest=True):
    """工具统一的载入入口：找原文、按三联版版面严格载入（回数 expect_chapters，0/None 不要求）、核对文本清单。
    找不到原文抛 FileNotFoundError。"""
    p = find_source(path)
    if p is None or not p.is_file():
        raise FileNotFoundError(f'找不到原文：{path or DEFAULT_SOURCE}（原文只放本地 sources/，见 sources/README.md）')
    st = TextStore.from_file(p, expect_chapters=expect_chapters or None)
    if check_manifest:
        st.apply_manifest(default_manifest_path(canon_dir))
        if st.meta.get('manifest') == 'missing':
            st.meta['warnings'].append(f'还没有文本清单 {MANIFEST_NAME}：用 tools/canon_text.py manifest --write 生成')
    return st


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
        by_first = {}
        for sf in self.cands:
            by_first.setdefault(sf[0], []).append(sf)
        self.by_first = {c: tuple(sorted(v, key=lambda s: (-len(s), s))) for c, v in by_first.items()}
        self._first_re = re.compile('[' + re.escape(''.join(sorted(self.first))) + ']') if self.first else None

    def match_at(self, text, i):
        """text[i:] 起最长匹配的称呼，没有返回 None。"""
        for sf in self.by_first.get(text[i], ()):
            if text.startswith(sf, i):
                return sf
        return None

    def scan(self, text):
        """从左到右、互不重叠的最长匹配：[(起, 止, 称呼)]。"""
        out = []
        pat = self._first_re
        if pat is None:
            return out
        pos, n = 0, len(text)
        while pos < n:
            m = pat.search(text, pos)
            if not m:
                break
            i = m.start()
            sf = self.match_at(text, i)
            if sf is None:
                pos = i + 1
                continue
            out.append((i, i + len(sf), sf))
            pos = i + len(sf)
        return out


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
        for i, j, sf in index.scan(p.text):
            c = index.cands[sf]
            m = Mention(p.ch, p.idx, i, j, sf, c)
            if len(c) == 1:
                m.entity, m.via = c[0], 'unique'
            elif _twin_group(c):
                m.twin = True
            out.append(m)
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
