"""防泄漏：原著原文永不入库（计划 3.1 第 2 条；ARCHITECTURE 第 0 节第 8 条；DECISIONS 第三节）。

做法：固定种子（计数器式 rnd）从**规范化原文**随机取 400 个 16 字窗口（每个窗口都落在一个段落之内，且以汉字为主），
断言它们不出现在仓库内任何入库文本文件里。扫描范围 = 仓库全部文件，去掉 .gitignore 已忽略的那些
（.git/、out/、sources/ 除 README.md 外、__pycache__、.scratch/、*.pyc *.sqlite *.db）。
比对三种形态：原样、JSON 的 \\uXXXX 转义还原后、去掉全部空白后（防止原文被折行或拆开存放）。

没有原文（sources/tianlong.txt 不存在）时，真文本部分 skip；扫描器本身的灵敏度用合成文本照常测试
（合成文本是为测试自编的虚构内容）。失败信息只报文件与指针（回、段、起），**不打印原文**。
"""
import bisect
import json
import os
import re
import unittest
from pathlib import Path

from tianl.canon import schema as S
from tianl.core.rng import rnd
from tests.test_canon_common import HAVE_REAL, TmpDirCase, real_store, synth_store

SEED = 'tianl-no-text-leak-v1'
N_WINDOWS = 400
WINDOW = 16
MIN_IDEOGRAPHS = 10                      # 窗口里至少这么多个汉字，避免取到标点或西文占多数的片段
SLOW = bool(os.environ.get('TIANL_SLOW'))

SKIP_DIRS = {'.git', '__pycache__', '.scratch'}
SKIP_TOP_DIRS = {'out'}                  # /out/ 被 .gitignore 忽略（只在仓库根）
SKIP_SUFFIXES = ('.pyc', '.sqlite', '.sqlite-journal', '.db')
KEEP_IN_SOURCES = {'README.md', '.gitkeep'}   # sources/* 被忽略，但这两个入库
MAX_FILE_BYTES = 64 * 1024 * 1024

_WS = re.compile(r'\s+')
_UESC = re.compile(r'\\u([0-9a-fA-F]{4})')


def is_ideograph(c):
    return '一' <= c <= '鿿' or '㐀' <= c <= '䶿'


def tracked_text_files(root):
    """仓库里会入库的全部文件（与 .gitignore 的口径一致；不执行 git）。"""
    root = Path(root)
    out = []
    for dp, dn, fn in os.walk(root):
        rel = Path(dp).relative_to(root)
        top = rel.parts[0] if rel.parts else ''
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS and not (not rel.parts and d in SKIP_TOP_DIRS))
        in_sources = top == 'sources'
        for f in sorted(fn):
            if f.endswith(SKIP_SUFFIXES) or f == '.DS_Store':
                continue
            if in_sources and not (len(rel.parts) == 1 and f in KEEP_IN_SOURCES):
                continue
            out.append(Path(dp) / f)
    return out


def read_text(path):
    b = Path(path).read_bytes()
    if len(b) > MAX_FILE_BYTES:
        return ''
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return b.decode('gb18030', errors='ignore')


def unescape_json(t):
    return _UESC.sub(lambda m: chr(int(m.group(1), 16)), t)


def squeeze(t):
    return _WS.sub('', t)


def load_haystacks(root):
    """[(相对路径, 原样文本, 还原转义并去空白后的文本)]"""
    root = Path(root)
    out = []
    for p in tracked_text_files(root):
        t = read_text(p)
        out.append((p.relative_to(root).as_posix(), t, squeeze(unescape_json(t))))
    return out


def sample_windows(store, n=N_WINDOWS, size=WINDOW, seed=SEED, min_ideographs=MIN_IDEOGRAPHS):
    """确定性抽样：[(回, 段, 起, 窗口文字)]。位置由 rnd(seed, 序号, 重试次数, …) 决定，与调用次序无关。"""
    paras = [(p.ch, p.idx, p.text) for p in store.iter_paragraphs() if len(p.text) >= size]
    cum, total = [], 0
    for _, _, t in paras:
        cum.append(total)
        total += len(t)
    out = []
    for i in range(n):
        for k in range(1000):
            pos = int(rnd(seed, i, k, 'pos') * total)
            j = bisect.bisect_right(cum, pos) - 1
            ch, idx, t = paras[j]
            start = min(pos - cum[j], len(t) - size)
            w = t[start:start + size]
            if sum(map(is_ideograph, w)) >= min_ideographs:
                out.append((ch, idx, start, w))
                break
        else:                                              # pragma: no cover（1000 次都抽不到汉字窗口：不可能）
            raise AssertionError(f'抽样失败：序号 {i}')
    return out


def find_leaks(root, windows):
    """窗口出现在哪些文件里：[(文件相对路径, 回, 段, 起)]。"""
    hay = load_haystacks(root)
    hits = []
    for ch, idx, start, w in windows:
        sw = squeeze(w)
        for rel, raw, sq in hay:
            if w in raw or sw in sq:
                hits.append((rel, ch, idx, start))
    return hits


def shingle_scan(store, root, size=12, mod=4):
    """全书 size 字片段的比对（内容定位的抽样，确定性、与进程无关）：只取“首字的码位 % mod == 0”的片段，
    mod = 1 即全量。泄漏的一段原文含 L - size + 1 个片段，每个约以 1/mod 的概率入选；对真文本实测（mod = 4，随机取 1000 段原文各自单独放进一个文件）：
    16 字的泄漏检出 85%，20 字 95.6%，30 字及以上 100%。两边都先去空白再比，与窗口抽样口径一致。返回 [(文件, 回, 段, 起)]。"""
    book = {}
    for p in store.iter_paragraphs():
        t = squeeze(p.text)
        for i in range(len(t) - size + 1):
            if ord(t[i]) % mod == 0:
                book.setdefault(t[i:i + size], (p.ch, p.idx, i))
    hits = []
    for rel, _, sq in load_haystacks(root):
        for i in range(len(sq) - size + 1):
            if ord(sq[i]) % mod == 0:
                g = sq[i:i + size]
                if g in book:
                    hits.append((rel, *book[g]))
                    break                                          # 每个文件报一处就够
    return hits


def fmt(hits):
    return '；'.join(f'{rel} ← c{ch}p{idx}@{st}' for rel, ch, idx, st in hits[:20])


# ----------------------------------------------------------------------------------------------------------------------
# 扫描器自身（合成文本，永远运行）
# ----------------------------------------------------------------------------------------------------------------------
class ScannerTests(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.store = synth_store()
        # 合成文本里最长的段落里取一个窗口；其余窗口由抽样器给
        self.wins = sample_windows(self.store, n=8, size=12, seed='scanner-test', min_ideographs=8)
        self.w = self.wins[0][3]

    def test_sampling_is_deterministic_in_paragraph_and_ideograph_heavy(self):
        a = sample_windows(self.store, n=20, size=12, seed='s1', min_ideographs=8)
        b = sample_windows(self.store, n=20, size=12, seed='s1', min_ideographs=8)
        c = sample_windows(self.store, n=20, size=12, seed='s2', min_ideographs=8)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(len(a), 20)
        for ch, idx, start, w in a:
            para = self.store.paragraph(ch, idx).text
            self.assertEqual(para[start:start + 12], w)                # 窗口整个落在一个段落里
            self.assertGreaterEqual(sum(map(is_ideograph, w)), 8)

    def test_detects_plain_escaped_and_wrapped_copies_and_ignores_clean_files(self):
        w = self.w
        self.write('docs/plain.md', f'说明：{w} 之类\n')
        self.write('data/escaped.json', json.dumps({'x': w}, ensure_ascii=True))      # \uXXXX 形态
        self.write('data/wrapped.txt', w[:5] + '\n  ' + w[5:] + '\n')                 # 折行
        self.write('docs/clean.md', '这里没有任何原文，只有自编的说明文字。\n')
        hits = {rel for rel, *_ in find_leaks(self.tmp, [self.wins[0]])}
        self.assertEqual(hits, {'docs/plain.md', 'data/escaped.json', 'data/wrapped.txt'})

    def test_excluded_locations_are_not_scanned(self):
        w = self.w
        for rel in ('sources/tianlong.txt', 'sources/notes.txt', 'out/canon/chapters/ch01.txt', '.git/COMMIT_EDITMSG',
                    '.scratch/x.txt', 'tianl/__pycache__/x.txt', 'data/world.sqlite', 'data/x.pyc'):
            self.write(rel, w)
        self.assertEqual(find_leaks(self.tmp, [self.wins[0]]), [])
        files = {p.relative_to(self.tmp).as_posix() for p in tracked_text_files(self.tmp)}
        self.assertEqual(files, set())
        # 但入库的 sources/README.md、以及非顶层的 out/ 目录（比如 data/out/）要扫
        self.write('sources/README.md', w)
        self.write('data/out/x.txt', w)
        hits = {rel for rel, *_ in find_leaks(self.tmp, [self.wins[0]])}
        self.assertEqual(hits, {'sources/README.md', 'data/out/x.txt'})

    def test_shingle_scan_finds_passages_and_ignores_short_or_clean_files(self):
        paras = [p.text for p in self.store.iter_paragraphs()]
        longest = max(paras, key=len)
        self.assertGreaterEqual(len(longest), 30)
        self.write('docs/quote.md', '前言\n' + longest[:14] + '\n' + longest[14:] + '\n')        # 折行的引文
        self.write('docs/many.md', '\n'.join(paras))                                                # 整章整章地抄
        self.write('docs/short.md', f'只抄了一小段：{longest[:11]}\n')                               # 不足 12 字：不算
        self.write('docs/clean.md', '这里没有任何原文，只有自编的说明文字。\n')
        full = {rel for rel, *_ in shingle_scan(self.store, self.tmp, size=12, mod=1)}
        self.assertEqual(full, {'docs/quote.md', 'docs/many.md'})
        quarter = {rel for rel, *_ in shingle_scan(self.store, self.tmp, size=12, mod=4)}
        self.assertIn('docs/many.md', quarter)                                                      # 大段抄写必现
        self.assertNotIn('docs/clean.md', quarter)
        self.assertNotIn('docs/short.md', quarter)
        for rel, ch, idx, st in shingle_scan(self.store, self.tmp, size=12, mod=1):
            self.assertRegex(fmt([(rel, ch, idx, st)]), r'\.md ← c\d+p\d+@\d+$')                  # 只报指针

    def test_report_does_not_echo_text(self):
        self.write('docs/plain.md', self.w)
        hits = find_leaks(self.tmp, [self.wins[0]])
        self.assertEqual(len(hits), 1)
        self.assertNotIn(self.w, fmt(hits))
        self.assertRegex(fmt(hits), r'docs/plain\.md ← c\d+p\d+@\d+')

    def test_gitignore_keeps_sources_and_out_out_of_the_repo(self):
        gi = (S.REPO_ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
        rules = {l.strip() for l in gi if l.strip() and not l.startswith('#')}
        self.assertIn('sources/*', rules)
        self.assertIn('!sources/README.md', rules)
        self.assertIn('/out/', rules)
        self.assertNotIn('!sources/tianlong.txt', rules)
        # 扫描器的排除表与 .gitignore 一致：只放行 README.md 与 .gitkeep
        self.assertEqual(KEEP_IN_SOURCES, {'README.md', '.gitkeep'})


# ----------------------------------------------------------------------------------------------------------------------
# 真原文（有 sources/tianlong.txt 才运行）
# ----------------------------------------------------------------------------------------------------------------------
@unittest.skipUnless(HAVE_REAL, '没有原文 sources/tianlong.txt：跳过防泄漏抽样')
class RealTextLeakTests(unittest.TestCase):
    def test_sample_is_well_formed(self):
        st = real_store()
        wins = sample_windows(st)
        self.assertEqual(len(wins), N_WINDOWS)
        self.assertTrue(all(len(w) == WINDOW for *_, w in wins))
        self.assertEqual(wins, sample_windows(st))                       # 固定种子：每次同一批
        self.assertGreater(len({(ch, idx) for ch, idx, *_ in wins}), 300)   # 散布在大量不同的段落里
        self.assertGreaterEqual(len({ch for ch, *_ in wins}), 40)        # 覆盖大部分回

    def test_no_window_of_the_book_in_any_tracked_file(self):
        wins = sample_windows(real_store())
        files = tracked_text_files(S.REPO_ROOT)
        self.assertGreater(len(files), 20)                                # 确实扫到了仓库
        hits = find_leaks(S.REPO_ROOT, wins)
        self.assertEqual(hits, [], f'原著原文泄漏进仓库（{len(hits)} 处窗口命中）：{fmt(hits)}')

    def test_quarter_of_all_12_char_shingles(self):
        """随机窗口只能抓大段泄漏；这里把全书约四分之一的 12 字片段（确定性选取）与全部入库文件逐一比对：30 字及以上的泄漏实测必现。"""
        hits = shingle_scan(real_store(), S.REPO_ROOT, size=12, mod=4)
        self.assertEqual(hits, [], f'原著原文泄漏进仓库：{fmt(hits)}')

    @unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开（全书全部 12 字片段，约 2 秒、约 230MB 内存）')
    def test_exhaustive_12_char_shingles(self):
        hits = shingle_scan(real_store(), S.REPO_ROOT, size=12, mod=1)
        self.assertEqual(hits, [], f'原著原文泄漏进仓库：{fmt(hits)}')


if __name__ == '__main__':
    unittest.main()
