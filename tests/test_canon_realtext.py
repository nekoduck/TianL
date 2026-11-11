"""真原文上的流水线核对（有 sources/tianlong.txt 才运行；没有就整体 skip）。

只核对**可复算的事实**：回数与标题、规范化清单、水印清除、导出版面、指针往返、锚点 → 指针 → 证据检查的全流程、
CANON_SCHEMA 第 11 节 30 人的首见回。测试里**不写任何原文片段**：锚点、窗口都是运行时从载入的文本里现取的。
"""
import json
import re
import unittest

from tianl.canon import anchors as A
from tianl.canon import check as C
from tianl.canon import schema as S
from tianl.canon import text as T
from tianl.canon import textcli
from tianl.core.rng import rnd
from tests.test_canon_common import HAVE_REAL, REAL_SOURCE, TmpDirCase, real_store, run_main

DOC = S.REPO_ROOT / 'docs' / 'CANON_SCHEMA.md'
MANIFEST = S.CANON_DIR / T.MANIFEST_NAME
WATERMARK = '★Ｄ★Ｏ★Ｓ★Ｐ★Ｙ★'


def part_of(ch):
    return 'p1' if ch <= 12 else 'p2' if ch <= 25 else 'p3' if ch <= 38 else 'p4'


@unittest.skipUnless(HAVE_REAL, '没有原文 sources/tianlong.txt：跳过真文本核对')
class RealBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = real_store()
        cls.raw = REAL_SOURCE.read_bytes().decode('utf-8-sig')

    def test_fifty_chapters_with_front_and_back_matter(self):
        self.assertEqual(sorted(self.st.chapters), list(range(0, 53)))
        s = self.st.stats()
        self.assertEqual((s['chapters'], s['has_front_matter']), (50, True))
        self.assertEqual(self.st.chapters[0].title, '卷首')
        self.assertEqual(self.st.chapters[51].title, '后记')
        self.assertTrue(self.st.chapters[52].title.startswith('附录'))
        self.assertEqual(self.st.meta['layout'], 'sanlian')

    def test_titles_equal_the_title_lines_of_the_source_file(self):
        """独立再抽一遍：源文件里顶格“<汉字数字> <标题>”的行，序号 1..50 依次出现，标题与载入结果一致。"""
        pat = re.compile(r'^([一二三四五六七八九十]+) (\S.*)$')
        found = []
        for line in self.raw.split('\n'):
            m = pat.match(line.rstrip('\r'))
            if m:
                found.append((T.cn2int(m.group(1)), m.group(2).strip()))
        self.assertEqual([n for n, _ in found], list(range(1, 51)))
        for n, title in found:
            self.assertEqual(self.st.chapters[n].title, title, n)

    def test_committed_manifest_matches_the_text(self):
        self.assertTrue(MANIFEST.is_file(), 'data/canon/text_manifest.json 不存在：用 tools/canon_text.py manifest --write 生成')
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(self.st.check_manifest(m), [])
        self.assertEqual(m['text_sha256'], self.st.text_sha256())
        s = self.st.stats()
        self.assertEqual(m['totals'], {'chapters': 50, 'paragraphs': s['paragraphs'], 'chars': s['chars']})
        self.assertEqual((s['paragraphs'], s['sentences'], s['chars']), (10922, 40147, 1248951))
        self.assertEqual(m['removed'], {'watermark_tokens': 178, 'site_lines': 6, 'separator_lines': 4})
        self.assertEqual(len(m['chapters']), 53)
        # 清单里只有标题、哈希与计数
        self.assertEqual(set(m['chapters'][1]), {'ch', 'title', 'paras', 'chars', 'sha16'})

    def test_watermarks_and_site_lines_are_gone(self):
        self.assertEqual(self.raw.count(WATERMARK), 178)                  # 源文件里确有 178 处
        ct = self.st.canonical_text()
        for bad in ('★', '☆', 'Ｄ★Ｏ', 'dospy', 'DOSPY', 'bbs.', '\r', '\x0c', '﻿', '​'):
            self.assertNotIn(bad, ct, bad)

    def test_paragraphs_are_clean_and_numbered_from_one(self):
        for ch, c in self.st.chapters.items():
            self.assertEqual([p.idx for p in c.paragraphs], list(range(1, len(c.paragraphs) + 1)), ch)
            for p in c.paragraphs:
                self.assertTrue(p.text and p.text == p.text.strip() and '\n' not in p.text, (ch, p.idx))
                self.assertFalse(p.text.startswith('　'), (ch, p.idx))
                self.assertEqual(p.hash, T.para_hash(p.text))

    def test_pointer_roundtrip_on_random_spans(self):
        paras = [p for p in self.st.iter_paragraphs() if len(p.text) >= 8]
        for i in range(500):
            p = paras[int(rnd('realtext', i, 'p') * len(paras))]
            a = int(rnd('realtext', i, 'a') * (len(p.text) - 1))
            b = min(len(p.text), a + 1 + int(rnd('realtext', i, 'b') * 12))
            ptr = [p.ch, p.idx, a, b, p.hash]
            self.assertEqual(self.st.check_pointer(ptr), None)
            self.assertEqual(self.st.get_span(ptr), p.text[a:b])
            self.assertEqual(S.expand_pointer(ptr)['para'], p.idx)

    def test_recall_table_first_seen_chapters_match_the_text(self):
        """CANON_SCHEMA 第 11 节：30 人的首见回、首见分区，与规范化原文里按姓名（及括号别名）检索的结果一致。"""
        rows = {}
        for ln in DOC.read_text(encoding='utf-8').splitlines():
            m = re.match(r'^\| (.+?) \| `(person:canon:\w+)` \| (p\d) \| (\d+) \|$', ln)
            if m:
                rows[m.group(2)] = (m.group(1), m.group(3), int(m.group(4)))
        self.assertEqual(len(rows), 30)
        self.assertEqual({r[1] for r in S.RECALL_30}, set(rows))
        part_count = {}
        for name, eid, part in S.RECALL_30:
            label, doc_part, doc_first = rows[eid]
            terms = [name] + re.findall(r'[（(]([^）)]+)[）)]', label)
            first = next(p.ch for p in self.st.iter_paragraphs() if p.ch >= 1 and any(t in p.text for t in terms))
            self.assertEqual(first, doc_first, name)
            self.assertEqual(part_of(first), doc_part, name)
            self.assertEqual(doc_part, part, name)
            part_count[doc_part] = part_count.get(doc_part, 0) + 1
        self.assertEqual(part_count, {'p1': 19, 'p2': 7, 'p3': 4})

    def test_find_counts_agree_with_a_direct_count(self):
        ct = self.st.canonical_text()
        for term in ('乔峰', '段誉', '少林寺'):
            rc, out = run_main(textcli.main, ['find', term, '--source', str(REAL_SOURCE)])
            self.assertEqual(rc, 0)
            n = sum(p.text.count(term) for p in self.st.iter_paragraphs())
            self.assertIn(f'全书命中 {n} 处', out)
        self.assertGreater(ct.count('乔峰'), 1000)


@unittest.skipUnless(HAVE_REAL, '没有原文 sources/tianlong.txt：跳过真文本核对')
class RealPipelineTests(TmpDirCase):
    @classmethod
    def setUpClass(cls):
        cls.st = real_store()

    def test_export_every_chapter_in_agent_readable_format(self):
        rc, out = run_main(textcli.main, ['export', '--all', '--out', str(self.tmp / 'o'), '--source', str(REAL_SOURCE)])
        self.assertEqual(rc, 0, out)
        d = self.tmp / 'o' / 'chapters'
        self.assertEqual(sorted(p.name for p in d.iterdir()), [f'ch{n:02d}.txt' for n in range(53)])
        total = 0
        for n in range(53):
            lines = (d / f'ch{n:02d}.txt').read_text(encoding='utf-8').split('\n')
            self.assertEqual(lines[-1], '')
            lines = lines[:-1]
            chap = self.st.chapters[n].paragraphs
            self.assertEqual(len(lines), len(chap), n)
            for i, (ln, p) in enumerate(zip(lines, chap), 1):
                self.assertEqual(ln, f'[c{n}p{i}] {p.text}')
            total += len(lines)
        self.assertEqual(total, 10922)

    def anchor_rows(self, n=40, anchor_len=6):
        """运行时从原文里现取 n 个锚点（唯一的用唯一写法，不唯一的写“第几次”）；返回 (行列表, [(回, 段, 锚点)])。"""
        paras = [p for p in self.st.iter_paragraphs() if len(p.text) >= 30]
        rows, picked = [], []
        for i in range(n):
            p = paras[int(rnd('realpipe', i, 'p') * len(paras))]
            a = int(rnd('realpipe', i, 'a') * (len(p.text) - anchor_len))
            anc = p.text[a:a + anchor_len]
            occ = A.anchor_positions(p.text, anc)
            item = [p.ch, p.idx, anc] if len(occ) == 1 else [p.ch, p.idx, anc, occ.index(a) + 1]
            rows.append({'s': 'person:canon:linyuan', 'p': 'trade', 'v': f'标签{i % 7}', 'e': [item]})
            picked.append((p.ch, p.idx, anc))
        return rows, picked

    def test_anchor_resolve_then_evidence_check_end_to_end(self):
        rows, picked = self.anchor_rows()
        for n in sorted({ch for ch, _, _ in picked}):                 # 按回写文件，与真实工作流一致
            self.write(f'assertions/ch{n:02d}.jsonl',
                       '\n'.join(json.dumps(r, ensure_ascii=False) for r, (ch, _, _) in zip(rows, picked) if ch == n) + '\n')
        self.write('census/p1.jsonl', json.dumps({'id': 'person:canon:linyuan', 'type': 'person', 'name': '甲某', 'aliases': [], 'note': '测试'},
                                                  ensure_ascii=False) + '\n')
        files = sorted((self.tmp / 'assertions').glob('ch*.jsonl'))
        rc, out = run_main(A.main, [*map(str, files), '--source', str(REAL_SOURCE), '--canon-dir', str(self.tmp)])
        self.assertEqual(rc, 0, out)
        self.assertIn('错误行 0', out)
        # 1) 文件里不得残留任何锚点文字；2) 每行补了 "b":"text"；3) 证据全是 5 元指针，指针取回的恰是锚点
        tot = 0
        for f in files:
            body = f.read_text(encoding='utf-8')
            for line in body.splitlines():
                r = json.loads(line)
                self.assertEqual(r['b'], 'text')
                ptr = r['e'][0]
                self.assertEqual(len(ptr), 5)
                tot += 1
                ch, para, anc = next(x for x in picked if x[0] == ptr[0] and x[1] == ptr[1] and self.st.get_span(ptr) == x[2])
                self.assertNotIn(anc, line)                          # 锚点原地丢弃
        self.assertEqual(tot, len(rows))
        # 重复运行幂等
        before = {f: f.read_bytes() for f in files}
        rc, out = run_main(A.main, [*map(str, files), '--source', str(REAL_SOURCE), '--canon-dir', str(self.tmp)])
        self.assertEqual(rc, 0, out)
        self.assertEqual(before, {f: f.read_bytes() for f in files})
        # verify-evidence 与 canon_check --evidence 都放行
        rc, out = run_main(textcli.main, ['verify-evidence', str(self.tmp / 'assertions'), '--source', str(REAL_SOURCE)])
        self.assertEqual(rc, 0, out)
        self.assertIn('100.0%', out)
        rc, out = run_main(C.main, ['--canon-dir', str(self.tmp), '--assertions', '--evidence', '--source', str(REAL_SOURCE), '--quiet'])
        self.assertEqual(rc, 0, out)
        self.assertIn(f'证据指针有效率：{len(rows)}/{len(rows)} = 100.0%', out)
        # 把其中一个指针的哈希改坏：两个检查都拦
        f0 = files[0]
        lines = f0.read_text(encoding='utf-8').splitlines()
        r = json.loads(lines[0])
        r['e'][0][4] = '0' * 16
        f0.write_text('\n'.join([json.dumps(r, ensure_ascii=False)] + lines[1:]) + '\n', encoding='utf-8')
        self.assertEqual(run_main(textcli.main, ['verify-evidence', str(self.tmp / 'assertions'), '--source', str(REAL_SOURCE)])[0], 1)
        rc, out = run_main(C.main, ['--canon-dir', str(self.tmp), '--evidence', '--source', str(REAL_SOURCE)])
        self.assertEqual(rc, 1)
        self.assertIn('哈希不符', out)

    def test_unresolved_anchor_left_in_a_final_file_is_caught(self):
        rows, picked = self.anchor_rows(n=3)
        self.write('assertions/ch01.jsonl', '\n'.join(json.dumps(dict(r, b='text'), ensure_ascii=False) for r in rows) + '\n')
        rc, out = run_main(C.main, ['--canon-dir', str(self.tmp), '--evidence', '--source', str(REAL_SOURCE)])
        self.assertEqual(rc, 1, out)
        self.assertIn('锚点', out)                                    # 提示要先运行 canon_resolve
        rc, out = run_main(textcli.main, ['verify-evidence', str(self.tmp / 'assertions'), '--source', str(REAL_SOURCE)])
        self.assertEqual(rc, 1)
        self.assertIn('未解析的锚点', out)


if __name__ == '__main__':
    unittest.main()
