"""综合校验（check.py）：夹具通过；按回产出时“重复”只警告；--evidence；--part 分区；合并。"""
import json
import unittest

from tianl.canon import check as C
from tianl.canon import merge as M
from tianl.canon import schema as S
from tests.test_canon_common import FIXTURES, TmpDirCase, run_main, synth_store

ENT = [
    {'id': 'person:canon:linyuan', 'type': 'person', 'name': '林远', 'aliases': ['林少侠'], 'note': '虚构'},
    {'id': 'person:canon:suxiaotang', 'type': 'person', 'name': '苏小棠', 'aliases': [], 'note': '虚构'},
    {'id': 'org:canon:tiejianmen', 'type': 'org', 'name': '铁剑门', 'aliases': [], 'note': '虚构'},
]


def jl(*rows):
    return '\n'.join(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows) + '\n'


class FixtureTests(unittest.TestCase):
    def test_fixture_suite_passes(self):
        rc, out = run_main(C.main, ['--canon-dir', str(FIXTURES), '--recall-ids', str(FIXTURES / 'recall_ids.json')])
        self.assertEqual(rc, 0, out)
        self.assertIn('通过', out.splitlines()[-1])
        self.assertIn('证据指针 evidence：跳过', out)                      # 夹具目录没有 --source：只提示、不失败

    def test_merge_fixture_census(self):
        res = M.merge_census(FIXTURES / 'census')
        self.assertEqual(res.conflicts, [])
        self.assertEqual(res.stats['entities'], 15)

    def test_bad_part_is_usage_error(self):
        rc, out = run_main(C.main, ['--canon-dir', str(FIXTURES), '--part', 'zz'])
        self.assertEqual(rc, 2)
        self.assertIn('未知分区', out)


class PerChapterTests(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.write('census/p1.jsonl', jl(*ENT))
        base = {'s': 'person:canon:linyuan', 'p': 'gender', 'v': 'male'}
        self.write('assertions/ch01.jsonl', jl(base, {'s': 'person:canon:linyuan', 'p': 'org', 'v': 'org:canon:tiejianmen'}))
        self.write('assertions/ch02.jsonl', jl(base, {'s': 'person:canon:suxiaotang', 'p': 'gender', 'v': 'female'}))
        self.write('assertions/ch20.jsonl', jl({'s': 'person:canon:suxiaotang', 'p': 'age_hint', 'v': '少女'}))

    def run_check(self, *extra):
        return run_main(C.main, ['--canon-dir', str(self.tmp), *extra])

    def test_duplicates_across_chapters_only_warn(self):
        rc, out = self.run_check('--assertions')
        self.assertEqual(rc, 0, out)
        self.assertIn('重复（只警告）1 条', out)
        self.assertIn('警告：', out)
        self.assertIn('重复（内容相同', out)
        self.assertIn('错误 0', out.splitlines()[-1])

    def test_same_id_different_content_is_error(self):
        self.write('assertions/ch03.jsonl', jl({'i': 'same', 's': 'person:canon:linyuan', 'p': 'age_hint', 'v': '少年'}))
        self.write('assertions/ch04.jsonl', jl({'i': 'same', 's': 'person:canon:linyuan', 'p': 'age_hint', 'v': '中年'}))
        rc, out = self.run_check('--assertions')
        self.assertEqual(rc, 1)
        self.assertIn('编号冲突', out)

    def test_event_and_secret_ids_are_unique_across_chapters(self):
        ev = {'id': 'event:canon:e1', 'name': '某事', 'kind': 'plot', 'time': {'start': 3},
              'participants': [{'person': 'person:canon:linyuan', 'role': 'actor'}]}
        sec = {'id': 'secret:canon:s1', 'truth': '某真相',
               'knowers_at_open': [{'person': 'person:canon:linyuan', 'believes': 'truth', 'from': 'self'}]}
        self.write('events/ch01.jsonl', jl(ev))
        self.write('events/ch02.jsonl', jl(ev))                      # 内容相同也算重复：事件、秘密的编号全库唯一
        self.write('secrets/ch01.jsonl', jl(sec))
        self.write('secrets/ch02.jsonl', jl(sec))
        rc, out = self.run_check('--events', '--secrets')
        self.assertEqual(rc, 1)
        self.assertIn('事件编号 event:canon:e1 与 ch01.jsonl:1 重复', out)
        self.assertIn('秘密编号 secret:canon:s1 与 ch01.jsonl:1 重复', out)

    def test_part_selects_chapter_files(self):
        rc, out = self.run_check('--assertions', '--part', 'p1')          # p1 = 第 0–12 回：ch01 与 ch02，不含 ch20
        self.assertEqual(rc, 0, out)
        self.assertIn('断言 4 条', out)
        rc, out = self.run_check('--assertions', '--part', 'ch20')
        self.assertIn('断言 1 条', out)
        rc, out = self.run_check('--assertions', '--part', 'p2')          # p2 = 第 13–25 回
        self.assertIn('断言 1 条', out)
        rc, out = self.run_check('--assertions', '--part', 'ch07')
        self.assertIn('跳过', out)
        rc, out = self.run_check('--census', '--part', 'p1')
        self.assertIn('实体 3', out)

    def test_census_partition_conflict_is_error(self):
        self.write('census/c5.jsonl', jl({'id': 'person:canon:linyuan', 'type': 'person', 'name': '林元', 'aliases': []}))
        rc, out = self.run_check('--census')
        self.assertEqual(rc, 1)
        self.assertIn('名字不一致', out)


class EvidenceTests(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.st = synth_store()
        self.src = self.source()
        self.write('census/p1.jsonl', jl(*ENT))
        h = self.st.paragraph(1, 1).hash
        self.good = [1, 1, 0, 3, h]
        self.bad = [1, 1, 0, 3, '0' * 16]

    def run_check(self, *extra):
        return run_main(C.main, ['--canon-dir', str(self.tmp), '--evidence', '--source', str(self.src), *extra])

    def A(self, **kw):
        row = {'s': 'person:canon:linyuan', 'p': 'gender', 'v': 'male'}
        row.update(kw)
        return row

    def test_skipped_without_source(self):
        self.write('assertions/ch01.jsonl', jl(self.A()))
        rc, out = run_main(C.main, ['--canon-dir', str(self.tmp), '--evidence'])
        self.assertEqual(rc, 0)
        self.assertIn('证据指针 evidence：跳过', out)
        self.assertIn('没有原文', out)

    def test_valid_text_rows_pass_with_rate(self):
        self.write('assertions/ch01.jsonl', jl(self.A(b='text', e=[self.good]),
                                               self.A(p='age_hint', v='少年'),
                                               {'s': 'person:canon:suxiaotang', 'p': 'gender', 'v': 'female', 'b': 'text', 'e': [self.good, self.good]}))
        self.write('events/ch01.jsonl', jl({'id': 'event:canon:e1', 'name': '渡口', 'kind': 'plot', 'time': {'start': 1},
                                            'participants': [{'person': 'person:canon:linyuan', 'role': 'actor'}], 'b': 'text', 'ev': [self.good]}))
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertIn('证据指针有效率：4/4 = 100.0%', out)
        self.assertIn('断言：3 行；basis=text 2，basis=recall 1', out)
        self.assertIn('事件：1 行；basis=text 1', out)

    def test_text_row_needs_a_valid_pointer(self):
        self.write('assertions/ch01.jsonl', jl(self.A(b='text', e=[self.bad]), self.A(p='age_hint', v='少年', b='text', e=[self.good, self.bad])))
        rc, out = self.run_check()
        self.assertEqual(rc, 1)
        self.assertIn('哈希不符', out)
        self.assertIn('必须至少有 1 条有效证据', out)             # 第一行：唯一一条指针无效
        self.assertIn('证据指针有效率：1/3 = 33.3%', out)

    def test_recall_row_must_have_empty_evidence_and_anchor_form_is_invalid(self):
        self.write('assertions/ch01.jsonl', jl(self.A(b='recall', e=[self.good]), self.A(p='age_hint', v='少年', b='text', e=[[1, 1, '锚点']])))
        rc, out = self.run_check()
        self.assertEqual(rc, 1)
        self.assertIn('basis=recall（凭记忆）的行证据必须为空', out)
        self.assertIn('指针须为', out)                            # 未解析的锚点形式
        self.assertIn('必须至少有 1 条有效证据', out)

    def test_secrets_and_identities_are_covered_too(self):
        sec = {'id': 'secret:canon:s1', 'truth': '某真相', 'knowers_at_open': [{'person': 'person:canon:linyuan', 'believes': 'truth', 'from': 'self'}]}
        ident = {'person': 'person:canon:suxiaotang', 'as_name': '黑衣客', 'kind': 'disguise'}
        self.write('secrets/ch01.jsonl', jl(dict(sec, b='text', ev=[self.good])))
        self.write('identities/ch01.jsonl', jl(dict(ident, b='text', ev=[self.good])))
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertIn('秘密：1 行；basis=text 1', out)
        self.assertIn('身份：1 行；basis=text 1', out)
        self.assertIn('证据指针有效率：2/2 = 100.0%', out)
        # 秘密：basis=text 却没有有效证据；身份：basis=recall 却带指针 -> 都报错
        self.write('secrets/ch01.jsonl', jl(dict(sec, b='text', ev=[self.bad])))
        self.write('identities/ch01.jsonl', jl(dict(ident, ev=[self.good])))
        rc, out = self.run_check()
        self.assertEqual(rc, 1)
        self.assertIn('必须至少有 1 条有效证据', out)
        self.assertIn('basis=recall（凭记忆）的行证据必须为空', out)

    def test_empty_span_is_invalid(self):
        self.write('assertions/ch01.jsonl', jl(self.A(b='text', e=[[1, 1, 3, 3, self.good[4]]])))
        rc, out = self.run_check()
        self.assertEqual(rc, 1)
        self.assertIn('空串', out)

    def test_not_applicable_when_no_text_rows(self):
        self.write('assertions/ch01.jsonl', jl(self.A()))
        rc, out = self.run_check()
        self.assertEqual(rc, 0)
        self.assertIn('不适用', out)

    def test_manifest_mismatch_is_warned(self):
        self.write('assertions/ch01.jsonl', jl(self.A(b='text', e=[self.good])))
        m = synth_store().manifest()
        m['chapters'][1]['sha16'] = '0' * 16
        self.write('text_manifest.json', json.dumps(m, ensure_ascii=False))
        rc, out = self.run_check()
        self.assertEqual(rc, 0)
        self.assertIn('文本清单', out)
        self.assertIn('不符', out)

    def test_evidence_runs_alongside_other_sections(self):
        self.write('assertions/ch01.jsonl', jl(self.A(b='text', e=[self.good])))
        rc, out = run_main(C.main, ['--canon-dir', str(self.tmp), '--assertions', '--evidence', '--source', str(self.src)])
        self.assertEqual(rc, 0, out)
        self.assertIn('== 证据指针 evidence：错误 0', out)
        self.assertIn('== 断言 assertions：错误 0', out)


if __name__ == '__main__':
    unittest.main()
