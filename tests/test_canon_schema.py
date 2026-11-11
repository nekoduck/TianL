"""格式契约：docs/CANON_SCHEMA.md 第 5 节的属性表与代码注册表一致；紧凑/完整互转；分区名；重复只警告；防引文长度。"""
import re
import unittest

from tianl.canon import schema as S
from tests.test_canon_common import FIXTURES

DOC = (S.REPO_ROOT / 'docs' / 'CANON_SCHEMA.md').read_text(encoding='utf-8')


def doc_props():
    """解析第 5 节（5.1–5.5）表格：{键: (中文, 值类型文字, 多值文字)}。"""
    a = DOC.index('## 5. 封闭属性清单')
    b = DOC.index('## 6.')
    out = {}
    for line in DOC[a:b].splitlines():
        m = re.match(r'^\| `([a-z_]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|', line)
        if m:
            out[m.group(1)] = (m.group(2).strip(), m.group(3).strip(), m.group(4).strip())
    return out


class DocRegistryTests(unittest.TestCase):
    def test_property_table_matches_registry(self):
        dp = doc_props()
        self.assertEqual(sorted(dp), sorted(S.PROPS), '文档第 5 节与 schema.PROPS 的属性集合不一致')
        for key, (label, vtype, multi) in dp.items():
            p = S.PROPS[key]
            self.assertEqual(label, p.label, key)
            self.assertEqual(vtype == '派生', p.derived, key)
            if not p.derived:
                self.assertEqual(multi == '是', p.multi, key)

    def test_doc_mentions_new_sections_and_tools(self):
        for frag in ('## 15. 文本版面与规范化', '## 16. 工具用法', 'canon_resolve', 'canon_names', 'canon_text',
                     '--evidence', 'p1 人物·第 1–12 回首见', 'c6a', 'c6b', 'c6c', 'assertions/ch00.jsonl'):
            self.assertIn(frag, DOC)

    def test_recall_table_matches_code(self):
        a = DOC.index('## 11. 30 人召回名单')
        b = DOC.index('## 12.')
        rows = re.findall(r'^\| ([^|]+?) \| `(person:canon:[a-z0-9]+)` \| (p[1-4]) \| (\d+) \|', DOC[a:b], re.M)
        self.assertEqual([(r[1], r[2]) for r in rows], [(i, part) for _, i, part in S.RECALL_30])
        self.assertEqual(len(S.RECALL_30), 30)
        self.assertEqual(sorted({part for _, _, part in S.RECALL_30}), ['p1', 'p2', 'p3'])
        # 首见回与分区一致
        for _, _, part, ch in rows:
            self.assertEqual(S.part_of_chapter(int(ch)), part)


class PartTests(unittest.TestCase):
    def test_part_names(self):
        for n in ('c1', 'c5', 'c6', 'p1', 'p4', 'c6a', 'c6b', 'c6c', 'ch00', 'ch07', 'ch52'):
            self.assertTrue(S.is_part_name(n), n)
        for n in ('ch53', 'ch7', 'p5', 'x', '', None):
            self.assertFalse(S.is_part_name(n), n)

    def test_part_of_chapter_and_stems(self):
        self.assertEqual([S.part_of_chapter(n) for n in (0, 1, 12, 13, 25, 26, 38, 39, 52)],
                         ['p1', 'p1', 'p1', 'p2', 'p2', 'p3', 'p3', 'p4', 'p4'])
        self.assertTrue(S.stem_in_part('ch12', 'p1'))
        self.assertFalse(S.stem_in_part('ch13', 'p1'))
        self.assertTrue(S.stem_in_part('ch13', 'ch13'))
        self.assertTrue(S.stem_in_part('p2', 'p2'))
        self.assertFalse(S.stem_in_part('c5', 'p2'))


class RoundTripTests(unittest.TestCase):
    def test_compact_expand_roundtrip_on_fixtures(self):
        items, errs = S.read_assertions(FIXTURES / 'assertions')
        self.assertFalse(errs)
        self.assertGreater(len(items), 30)
        for _, full in items:
            self.assertEqual(S.expand_assertion(S.compact_assertion(full)), full)

    def test_pointer_forms(self):
        d = S.expand_pointer([3, 12, 5, 9, '0f3a9c2b7d41e8a6'])
        self.assertEqual(d, {'ch': 3, 'para': 12, 'start': 5, 'end': 9, 'hash': '0f3a9c2b7d41e8a6'})
        self.assertEqual(S.compact_pointer(d), [3, 12, 5, 9, '0f3a9c2b7d41e8a6'])
        self.assertEqual(S.validate_pointer(d), [])
        self.assertTrue(S.validate_pointer({'ch': 3}))
        self.assertTrue(S.validate_pointer(dict(d, start=9, end=5)))
        self.assertTrue(S.validate_pointer(dict(d, hash='XYZ')))

    def test_provenance_aliases_b_and_e(self):
        ev = S.expand_event({'id': 'event:canon:x', 'name': 'x', 'kind': 'plot', 'time': {'start': 1}, 'b': 'text',
                             'e': [[1, 2, 3, 4, '0' * 16]]})
        self.assertEqual((ev['basis'], ev['ev']), ('text', [{'ch': 1, 'para': 2, 'start': 3, 'end': 4, 'hash': '0' * 16}]))
        self.assertNotIn('b', ev)
        self.assertEqual(S.validate_event(ev), [])


class AssertionRuleTests(unittest.TestCase):
    def row(self, **kw):
        base = {'s': 'person:canon:a', 'p': 'gender', 'v': 'male'}
        base.update(kw)
        return S.expand_assertion(base)

    def test_text_basis_needs_evidence_recall_forbids_it(self):
        ptr = [1, 1, 0, 2, '0' * 16]
        self.assertEqual(S.validate_assertion(self.row(b='text', e=[ptr])), [])
        self.assertTrue(any('至少一条' in e for e in S.validate_assertion(self.row(b='text'))))
        self.assertTrue(any('必须为空' in e for e in S.validate_assertion(self.row(b='recall', e=[ptr]))))
        self.assertEqual(S.validate_assertion(self.row()), [])                   # 默认 recall、无证据

    def test_no_long_quotes(self):
        errs = S.validate_assertion(self.row(p='access', s='place:canon:x', v='甲' * 41))
        self.assertTrue(errs)
        errs = S.validate_assertion(self.row(n='乙' * 121))
        self.assertTrue(any('120' in e for e in errs))
        self.assertTrue(S.validate_assertion(self.row(p='speech', v='他说，“好”')))        # 说话特征只许标签

    def test_duplicates_are_warnings_not_errors(self):
        a = self.row()
        b = self.row()
        c = self.row(i='manual_id')
        ctx = S.Ctx()
        errs = S.check_assertion_set([('f1:1', a), ('f2:1', b), ('f3:1', c)], ctx)
        self.assertEqual(errs, [])
        self.assertEqual(len(ctx.warnings), 2)
        self.assertTrue(all('重复' in w for w in ctx.warnings))
        # 同编号同内容 -> 警告；同编号不同内容 -> 错误
        d1, d2 = self.row(i='same'), self.row(i='same')
        ctx = S.Ctx()
        self.assertEqual(S.check_assertion_set([('f1:1', d1), ('f2:1', d2)], ctx), [])
        self.assertEqual(len(ctx.warnings), 1)
        d3 = self.row(i='same', v='female')
        errs = S.check_assertion_set([('f1:1', d1), ('f2:1', d3)], S.Ctx())
        self.assertTrue(any('编号冲突' in e for e in errs))

    def test_single_value_conflict_still_an_error(self):
        errs = S.check_assertion_set([('f1:1', self.row()), ('f2:1', self.row(v='female'))], S.Ctx())
        self.assertTrue(any('时间重叠' in e for e in errs))


if __name__ == '__main__':
    unittest.main()
