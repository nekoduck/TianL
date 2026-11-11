"""第 0 阶段：规范化、切回切段切句、指针、全书检索、文本清单（合成文本，不依赖真原文）。"""
import json
import unittest

from tianl.canon import text as T
from tests.test_canon_common import IND, WM, TmpDirCase, synth_store, synth_text


class DecodeNormalizeTests(unittest.TestCase):
    def test_decode_utf8_bom_and_gb18030(self):
        s = '第一回　某某\n正文。'
        self.assertEqual(T.decode_bytes(s.encode('utf-8')), (s, 'utf-8-sig'))
        txt, enc = T.decode_bytes(b'\xef\xbb\xbf' + s.encode('utf-8'))
        self.assertEqual((txt, enc), (s, 'utf-8-sig'))              # BOM 被去掉
        txt, enc = T.decode_bytes(s.encode('gb18030'))
        self.assertEqual((txt, enc), (s, 'gb18030'))                 # UTF-8 失败回退 GB18030
        txt, enc = T.decode_bytes(s.encode('utf-16'))
        self.assertEqual((txt, enc), (s, 'utf-16'))

    def test_normalize_is_minimal(self):
        # CRLF/CR/换页 -> LF；零宽与控制字符去掉；但不做 NFKC / NFC：全角字母数字、兼容字原样
        raw = 'Ａ１\r\n甲​乙\rＤ\x0c丙\x01丁'
        self.assertEqual(T.normalize(raw), 'Ａ１\n甲乙\nＤ\n丙丁')
        self.assertEqual(T.normalize('兀'), '兀')            # NFC 会把它换成 U+5140；我们不换

    def test_clean_lines_watermarks_and_separators(self):
        lines, st = T.clean_lines(T.normalize(synth_text()))
        texts = [t for _, t, _ in lines]
        self.assertFalse(any('★' in t or '☆' in t for t in texts))
        self.assertFalse(any(set(t) <= set('-') for t in texts))
        self.assertEqual(st['watermark_tokens'], 3)                  # 两行独立 + 一处行尾
        self.assertEqual(st['watermark_lines'], 2)
        self.assertEqual(st['site_lines'], 6)
        self.assertEqual(st['separator_lines'], 4)
        # 行尾水印删去后，段落文字完整、两端无空白
        self.assertIn('当夜，苏小棠也来到石桥。她笑着说：“林少侠，你也在此？”林远点了点头。', texts)
        # 水印夹在行中：拆成两段
        mid, _ = T.clean_lines(f'甲甲。{WM}乙乙。')
        self.assertEqual([t for _, t, _ in mid], ['甲甲。', '乙乙。'])
        # 缩进信息：正文缩进、标题顶格
        ind = {t: i for _, t, i in lines}
        self.assertTrue(ind['林远追到云梦镇，在街口遇见了黑衣客。林远一怔。'])
        self.assertFalse(ind['一 石桥夜雨'])


class LayoutTests(unittest.TestCase):
    def test_sanlian_chapters(self):
        st = synth_store()
        self.assertEqual(st.meta['layout'], 'sanlian')
        self.assertEqual(sorted(st.chapters), [0, 1, 2, 3, 51, 52])
        self.assertEqual([st.chapters[n].title for n in (0, 1, 2, 3, 51, 52)],
                         ['卷首', '石桥夜雨', '白塔寺中 清晨', '云梦镇上', '后记', '附录 某某先生书函'])
        # 段 = 非空行；标题行不算段；全角空格空行与水印行不算段
        self.assertEqual([len(st.chapters[n].paragraphs) for n in (0, 1, 2, 3, 51, 52)], [4, 3, 3, 2, 2, 1])
        self.assertEqual(st.chapters[0].paragraphs[0].text, '“虚构作品集”序')   # 卷首的顶格标题行是普通段
        self.assertEqual(st.chapters[1].paragraphs[1].text, '当夜，苏小棠也来到石桥。她笑着说：“林少侠，你也在此？”林远点了点头。')
        self.assertEqual(st.meta['warnings'], [])

    def test_crlf_and_bom_give_identical_store(self):
        a = T.TextStore.from_text(synth_text())
        b = T.TextStore.from_bytes(b'\xef\xbb\xbf' + synth_text(crlf=True).encode('utf-8'))
        c = T.TextStore.from_bytes(synth_text().encode('gb18030'))
        self.assertEqual(a.text_sha256(), b.text_sha256())
        self.assertEqual(a.text_sha256(), c.text_sha256())
        self.assertEqual(c.meta['encoding'], 'gb18030')

    def test_non_consecutive_titles_raise(self):
        bad = synth_text().replace('三 云梦镇上', '四 云梦镇上')
        with self.assertRaises(T.TextFormatError) as cm:
            T.TextStore.from_text(bad)
        self.assertIn('应为 3', str(cm.exception))
        dup = synth_text().replace('三 云梦镇上', '二 云梦镇上')
        with self.assertRaises(T.TextFormatError):
            T.TextStore.from_text(dup)
        skip = synth_text().replace('二 白塔寺中 清晨', '三 白塔寺中 清晨')
        with self.assertRaises(T.TextFormatError):
            T.TextStore.from_text(skip)

    def test_expect_chapters(self):
        self.assertEqual(T.TextStore.from_text(synth_text(), expect_chapters=3).stats()['chapters'], 3)
        with self.assertRaises(T.TextFormatError) as cm:
            T.TextStore.from_text(synth_text(), expect_chapters=50)
        self.assertIn('应有 50 回', str(cm.exception))

    def test_indented_numeral_line_is_body_not_title(self):
        # 缩进的“一 二”不是回标题（回标题必须顶格）
        t = synth_text().replace(IND + '大师年过六旬', IND + '二 三四五，大师年过六旬')
        st = T.TextStore.from_text(t)
        self.assertEqual(sorted(st.chapters), [0, 1, 2, 3, 51, 52])
        self.assertTrue(st.chapters[2].paragraphs[1].text.startswith('二 三四五'))

    def test_legacy_hui_layout_still_works(self):
        txt = '前言一行。\n\n第一回　渡口夜话\n\n甲甲甲。\n\n第二回　白石寺\n乙乙乙。\n丙丙丙。\n'
        st = T.TextStore.from_text(txt)
        self.assertEqual(st.meta['layout'], 'hui')
        self.assertEqual([(n, c.title, len(c.paragraphs)) for n, c in sorted(st.chapters.items())],
                         [(0, '卷首', 1), (1, '渡口夜话', 1), (2, '白石寺', 2)])
        none = T.TextStore.from_text('只有一段。\n又一段。')
        self.assertEqual(sorted(none.chapters), [1])
        self.assertTrue(none.meta['warnings'])

    def test_cn2int(self):
        self.assertEqual([T.cn2int(x) for x in ('一', '十', '十五', '二十', '四十九', '五十', '一百零二', '１２')],
                         [1, 10, 15, 20, 49, 50, 102, 12])
        self.assertIsNone(T.cn2int('甲'))


class SentenceTests(unittest.TestCase):
    def sents(self, p):
        return [p[a:b] for a, b in T.split_sentences(p)]

    def test_terminators_and_closing_quotes(self):
        self.assertEqual(self.sents('他说：“你好。你是谁？”我答：“路人。”完了。'),
                         ['他说：“你好。', '你是谁？”', '我答：“路人。”', '完了。'])
        self.assertEqual(self.sents('什么！？真的？！好。'), ['什么！？', '真的？！', '好。'])
        self.assertEqual(self.sents('没有句末符的残余'), ['没有句末符的残余'])
        self.assertEqual(self.sents('他喊：“走！”（快）。'), ['他喊：“走！”', '（快）。'])

    def test_ellipsis(self):
        # 句中的省略号不切；其后是右引号或段末才算句末
        self.assertEqual(self.sents('他……他怎么会……我不信！'), ['他……他怎么会……我不信！'])
        self.assertEqual(self.sents('“我……”他说。'), ['“我……”', '他说。'])
        self.assertEqual(self.sents('后来……'), ['后来……'])

    def test_sentence_ids_and_pointers(self):
        st = synth_store()
        self.assertEqual(T.parse_sentence_id('c3p12s2'), (3, 12, 2))
        with self.assertRaises(ValueError):
            T.parse_sentence_id('c3p12')
        self.assertEqual(st.get_sentence('c1p1s2'), '老艄公说：“水涨了。”')
        self.assertEqual(st.get_sentence('c1p1s1'), '林远在石桥等了三日，船始终没有来。')
        ptr = st.sentence_pointer('c1p2s3')
        self.assertEqual(st.get_span(ptr), '林远点了点头。')
        self.assertEqual(st.get_sentence('c1p2s2'), '她笑着说：“林少侠，你也在此？”')
        with self.assertRaises(T.SpanError):
            st.get_sentence('c1p1s99')


class PointerTests(unittest.TestCase):
    def test_pointer_roundtrip_and_failures(self):
        st = synth_store()
        p = st.paragraph(1, 2)
        ptr = st.pointer(1, 2, 3, 8)
        self.assertEqual(ptr['hash'], T.para_hash(p.text))
        self.assertEqual(st.get_span(ptr), p.text[3:8])
        self.assertEqual(st.get_span([1, 2, 3, 8, p.hash]), p.text[3:8])
        self.assertIsNone(st.check_pointer(ptr))
        self.assertIn('哈希不符', st.check_pointer([1, 2, 3, 8, '0' * 16]))
        self.assertIn('越界', st.check_pointer([1, 2, 3, 999, p.hash]))
        self.assertIn('没有第 9 回', st.check_pointer([9, 1, 0, 1, p.hash]))
        self.assertIn('没有第 1 回第 99 段', st.check_pointer([1, 99, 0, 1, p.hash]))
        with self.assertRaises(T.SpanError):
            st.get_span([1, 2, 3, 999, p.hash])
        with self.assertRaises(T.SpanError):
            st.pointer(1, 2, 5, 999)

    def test_hash_depends_only_on_normalized_paragraph(self):
        a = T.para_hash('同一段。')
        self.assertEqual(a, T.para_hash('同一段。'))
        self.assertRegex(a, r'^[0-9a-f]{16}$')
        st1 = synth_store()
        st2 = T.TextStore.from_text(synth_text().replace('一 石桥夜雨', '一 石桥夜雨 改'))     # 改标题不改段落哈希
        self.assertEqual(st1.paragraph(1, 1).hash, st2.paragraph(1, 1).hash)
        self.assertNotEqual(st1.text_sha256(), st2.text_sha256())


class FindTests(unittest.TestCase):
    def test_flat_find_locate(self):
        st = synth_store()
        hits = st.find('林远')
        self.assertEqual(len(hits), 7)
        for ch, para, off in hits:
            self.assertEqual(st.paragraph(ch, para).text[off:off + 2], '林远')
        self.assertEqual([h[0] for h in st.find('林远', ch=3)], [3, 3, 3])
        self.assertEqual(st.find('不存在的串'), [])
        self.assertEqual(st.find('林远', ch=99), [])
        self.assertEqual(len(st.find('哈哈', overlap=True)), 1)
        self.assertEqual(len(T.TextStore.from_text(synth_text().replace('哈哈一笑', '哈哈哈一笑')).find('哈哈', overlap=True)), 2)
        with self.assertRaises(ValueError):
            st.find('甲\n乙')
        # 平铺位置与回的范围
        lo, hi = st.chapter_flat_range(2)
        flat = st.flat_index()[0]
        self.assertTrue(flat[lo:hi].startswith('次日清晨'))
        self.assertTrue(flat[lo:hi].endswith('性子急躁，爱下棋。'))
        self.assertIsNone(st.chapter_flat_range(9))


class ManifestTests(TmpDirCase):
    def test_manifest_content_has_no_text(self):
        st = synth_store()
        m = st.manifest()
        self.assertEqual(m['normalizer'], T.NORMALIZER_ID)
        self.assertEqual(m['text_sha256'], st.text_sha256())
        self.assertEqual(m['totals'], {'chapters': 3, 'paragraphs': st.stats()['paragraphs'], 'chars': st.stats()['chars']})
        self.assertEqual(m['removed'], {'watermark_tokens': 3, 'site_lines': 6, 'separator_lines': 4})
        self.assertEqual([c['ch'] for c in m['chapters']], [0, 1, 2, 3, 51, 52])
        self.assertEqual(m['chapters'][1], {'ch': 1, 'title': '石桥夜雨', 'paras': 3, 'chars': st.chapters[1].chars(),
                                            'sha16': st.chapters[1].hash16()})
        body = json.dumps(m, ensure_ascii=False)
        for p in st.iter_paragraphs():
            self.assertNotIn(p.text[:8], body)                      # 清单里没有任何段落文字
        self.assertEqual(st.check_manifest(m), [])

    def test_manifest_mismatch_messages(self):
        m = synth_store().manifest()
        other = T.TextStore.from_text(synth_text().replace('老艄公说', '老艄公笑道'))
        probs = other.check_manifest(m)
        self.assertTrue(probs)
        self.assertIn('不符', probs[0])
        self.assertTrue(any('第 1 回' in x and '哈希' in x for x in probs[1:]))
        fewer = T.TextStore.from_text(synth_text().replace('三 云梦镇上', '后记 谁'))        # 少一回
        self.assertTrue(any('第 3 回' in x for x in fewer.check_manifest(m)))
        m2 = dict(m, normalizer='old-rule')
        self.assertTrue(any('规范化规则' in x for x in synth_store().check_manifest(m2)))

    def test_from_file_applies_manifest(self):
        src = self.source()
        m = synth_store().manifest()
        mp = self.write('manifest.json', json.dumps(m, ensure_ascii=False))
        st = T.TextStore.from_file(src, manifest=mp)
        self.assertEqual(st.meta['manifest'], 'ok')
        self.assertEqual(st.meta['manifest_problems'], [])
        bad = self.source(synth_text().replace('她笑着说', '她冷冷地说'), name='other.txt')
        st2 = T.TextStore.from_file(bad, manifest=mp)
        self.assertEqual(st2.meta['manifest'], 'mismatch')
        self.assertTrue(st2.meta['warnings'])
        st3 = T.TextStore.from_file(src, manifest=self.tmp / 'nope.json')
        self.assertEqual(st3.meta['manifest'], 'missing')
        self.assertNotIn('manifest', T.TextStore.from_file(src).meta)       # 默认不核对

    def test_load_book_strict(self):
        src = self.source()
        with self.assertRaises(T.TextFormatError):
            T.load_book(src, canon_dir=self.tmp)                             # 默认要求 50 回
        st = T.load_book(src, canon_dir=self.tmp, expect_chapters=0)
        self.assertEqual(st.meta['manifest'], 'missing')
        self.assertTrue(any('还没有文本清单' in w for w in st.meta['warnings']))
        with self.assertRaises(FileNotFoundError):
            T.load_book(self.tmp / 'none.txt')

    def test_index_roundtrip(self):
        st = synth_store()
        self.assertEqual(st.check_index(st.index()), [])
        idx = st.index()
        idx['chapters'][1]['paras'][0][2] = '0' * 16
        self.assertTrue(st.check_index(idx))


class SurfaceIndexTests(unittest.TestCase):
    ROWS = [{'id': 'person:canon:linyuan', 'type': 'person', 'name': '林远', 'aliases': ['林少侠', '远']},
            {'id': 'person:canon:suxiaotang', 'type': 'person', 'name': '苏小棠', 'aliases': ['小棠']},
            {'id': 'person:canon:huiming', 'type': 'person', 'name': '慧明', 'aliases': ['慧明大师', {'name': '大师', 'ambiguous': True}]},
            {'id': 'person:canon:huineng', 'type': 'person', 'name': '慧能', 'aliases': [{'name': '大师', 'ambiguous': True}]}]

    def test_longest_match_non_overlapping(self):
        idx = T.SurfaceIndex(self.ROWS)
        self.assertEqual(idx.scan('慧明大师与林少侠，远行'), [(0, 4, '慧明大师'), (5, 8, '林少侠')])
        self.assertEqual(idx.skipped, [('person:canon:linyuan', '远')])          # 单字称呼不参与
        self.assertEqual(idx.match_at('慧明大师', 0), '慧明大师')
        self.assertIsNone(idx.match_at('苏苏', 0))
        self.assertEqual(idx.scan(''), [])

    def test_census_mentions_and_verify(self):
        st = synth_store()
        idx = T.SurfaceIndex(self.ROWS)
        ms = T.census_mentions(st, idx)
        self.assertEqual(T.verify_mentions(st, ms), [])
        by = T.mention_counts(T.resolve_mentions(st, ms, idx).mentions)
        self.assertEqual(by['person:canon:linyuan'], 8)                         # 7 处“林远” + 1 处别名“林少侠”
        self.assertEqual(by['person:canon:suxiaotang'], 3)
        amb = [m for m in ms if m.surface == '大师']
        self.assertEqual(len(amb), 1)                                           # “大师”歧义：靠上下文消歧
        self.assertEqual(amb[0].cands, ('person:canon:huiming', 'person:canon:huineng'))


if __name__ == '__main__':
    unittest.main()
