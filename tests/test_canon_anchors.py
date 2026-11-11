"""证据锚点：resolve_anchor、canon_resolve 的改写规则、canon_text 的各子命令（合成文本）。"""
import json
import re
import unittest

from tianl.canon import anchors as A
from tianl.canon import schema as S
from tianl.canon import text as T
from tianl.canon import textcli
from tests.test_canon_common import TmpDirCase, run_main, synth_store


class ResolveAnchorTests(unittest.TestCase):
    def setUp(self):
        self.st = synth_store()

    def test_unique_anchor(self):
        p = self.st.paragraph(1, 1)
        ptr = A.resolve_anchor(self.st, 1, 1, '老艄公')
        k = p.text.index('老艄公')
        self.assertEqual(ptr, [1, 1, k, k + 3, p.hash])
        self.assertEqual(self.st.get_span(ptr), '老艄公')

    def test_ambiguous_needs_nth(self):
        text = self.st.paragraph(1, 1).text
        with self.assertRaises(A.AnchorError) as cm:
            A.resolve_anchor(self.st, 1, 1, '了')
        msg = str(cm.exception)
        self.assertIn(f'出现 {text.count("了")} 次', msg)
        self.assertIn(str(text.index('了')), msg)                       # 列出各起点
        second = [i for i, c in enumerate(text) if c == '了'][1]
        ptr = A.resolve_anchor(self.st, 1, 1, '了', 2)
        self.assertEqual(ptr[2:4], [second, second + 1])
        with self.assertRaises(A.AnchorError) as cm:
            A.resolve_anchor(self.st, 1, 1, '了', 9)
        self.assertIn('没有第 9 次', str(cm.exception))
        with self.assertRaises(A.AnchorError):
            A.resolve_anchor(self.st, 1, 1, '了', 0)

    def test_overlapping_occurrences_count_separately(self):
        st = T.TextStore.from_text(synth_text_with('哈哈哈'))
        self.assertEqual(A.anchor_positions(st.paragraph(1, 3).text, '哈哈'), [st.paragraph(1, 3).text.index('哈哈'),
                                                                               st.paragraph(1, 3).text.index('哈哈') + 1])

    def test_not_found_and_limits(self):
        for anchor, frag in (('找不到的串', '找不到'), ('', '非空'), ('甲' * 21, '超过上限 20')):
            with self.assertRaises(A.AnchorError) as cm:
                A.resolve_anchor(self.st, 1, 1, anchor)
            self.assertIn(frag, str(cm.exception))
        with self.assertRaises(A.AnchorError) as cm:
            A.resolve_anchor(self.st, 9, 1, '甲')
        self.assertIn('没有第 9 回', str(cm.exception))
        ok = '次日清晨，两人同往白塔寺借宿。慧明大师接'[:20]
        self.assertEqual(len(ok), 20)
        self.assertEqual(A.resolve_anchor(self.st, 2, 1, ok)[3] - A.resolve_anchor(self.st, 2, 1, ok)[2], 20)

    def test_classify_item(self):
        self.assertEqual(A.classify_item([1, 2, '锚', 3]), ('anchor', (1, 2, '锚', 3)))
        self.assertEqual(A.classify_item([1, 2, '锚']), ('anchor', (1, 2, '锚', None)))
        self.assertEqual(A.classify_item([1, 2, 3, 4, '0' * 16])[0], 'pointer')
        self.assertEqual(A.classify_item({'ch': 1, 'para': 2, 'start': 3, 'end': 4, 'hash': '0' * 16})[0], 'pointer')
        for bad in ([1, 2], [True, 2, '锚'], 'x', [1, 2, 3, 4, 5], None):
            self.assertEqual(A.classify_item(bad)[0], 'bad')


def synth_text_with(extra):
    from tests.test_canon_common import synth_text
    return synth_text().replace('哈哈一笑', extra + '一笑')


class ResolveFileTests(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.st = synth_store()
        self.h11 = self.st.paragraph(1, 1).hash
        self.h12 = self.st.paragraph(1, 2).hash

    def test_rewrite_rules(self):
        lines = [
            '# 注释行原样保留',
            '',
            json.dumps({'s': 'person:canon:linyuan', 'p': 'gender', 'v': 'male', 'e': [[1, 1, '老艄公'], [1, 2, '林少侠']]}, ensure_ascii=False),
            json.dumps({'s': 'person:canon:linyuan', 'p': 'org', 'v': 'none', 'e': [[1, 1, '了']]}, ensure_ascii=False),
            json.dumps({'s': 'person:canon:linyuan', 'p': 'org', 'v': 'none', 'e': [[1, 1, '了', 2]]}, ensure_ascii=False),
            json.dumps({'s': 'person:canon:linyuan', 'p': 'trait', 'v': '重义', 'e': [[1, 1, '老艄公'], [1, 2, '不存在的']]}, ensure_ascii=False),
            json.dumps({'id': 'event:canon:e1', 'name': '渡口', 'kind': 'plot', 'ev': [[1, 1, '石桥']], 'tag': 'text'}, ensure_ascii=False),
            json.dumps({'s': 'person:canon:linyuan', 'p': 'gender', 'v': 'male', 'b': 'recall'}),
            json.dumps({'s': 'person:canon:linyuan', 'p': 'age_at_open', 'v': 20, 'e': [[1, 1, '石桥'], [1, 1, '石桥']]}, ensure_ascii=False),
            'this is not json',
            '[1,2,3]',
        ]
        f = self.write('a.jsonl', '\n'.join(lines) + '\n')
        rep = A.resolve_file(self.st, f)
        out = f.read_text(encoding='utf-8').split('\n')
        # 未改动的行逐字节不变（注释、空行、失败行、无证据行）
        for i in (0, 1, 3, 5, 7, 9, 10, 11):
            self.assertEqual(out[i], lines[i] if i < len(lines) else '')
        # 成功行：锚点 -> 指针，补 b=text，b 放在 e 之前
        r2 = json.loads(out[2])
        k = self.st.paragraph(1, 1).text.index('老艄公')
        k2 = self.st.paragraph(1, 2).text.index('林少侠')
        self.assertEqual(r2['e'], [[1, 1, k, k + 3, self.h11], [1, 2, k2, k2 + 3, self.h12]])
        self.assertEqual(r2['b'], 'text')
        self.assertEqual(list(r2).index('b') + 1, list(r2).index('e'))
        # nth 成功
        r4 = json.loads(out[4])
        second = [i for i, c in enumerate(self.st.paragraph(1, 1).text) if c == '了'][1]
        self.assertEqual(r4['e'], [[1, 1, second, second + 1, self.h11]])
        # 事件也补 b=text（紧凑键；schema 接受）
        r6 = json.loads(out[6])
        self.assertEqual((r6['b'], r6['ev'][0][:2]), ('text', [1, 1]))
        self.assertEqual(S.expand_event(r6)['basis'], 'text')
        self.assertEqual(len(S.expand_event(r6)['ev']), 1)
        # 重复指针去重
        self.assertEqual(len(json.loads(out[8])['e']), 1)
        # 报告：改写 4 行，错误 4 条（不唯一、找不到、非 JSON、非对象）
        self.assertEqual((rep.rewritten, rep.anchors), (4, 6))
        self.assertEqual(sorted(n for n, _ in rep.errors), [4, 6, 10, 11])
        msgs = {n: m for n, m in rep.errors}
        self.assertIn('出现', msgs[4])
        self.assertIn('找不到', msgs[6])
        self.assertIn('JSON', msgs[10])
        self.assertIn('对象', msgs[11])

    def test_idempotent_and_verify(self):
        f = self.write('a.jsonl', json.dumps({'s': 'person:canon:linyuan', 'p': 'gender', 'v': 'male',
                                              'e': [[1, 1, '老艄公']]}, ensure_ascii=False) + '\n')
        A.resolve_file(self.st, f)
        first = f.read_bytes()
        rep = A.resolve_file(self.st, f)
        self.assertEqual((rep.rewritten, rep.errors), (0, []))
        self.assertEqual(f.read_bytes(), first)
        tot, ok, bad, badrows, nf = textcli.verify_paths(self.st, [f], out=__import__('io').StringIO())
        self.assertEqual((tot, ok, bad, badrows, nf), (1, 1, 0, 0, 1))

    def test_failed_row_is_untouched_even_if_other_anchors_resolve(self):
        row = json.dumps({'s': 'person:canon:linyuan', 'p': 'trait', 'v': '重义', 'e': [[1, 1, '老艄公'], [1, 2, '不存在的']]},
                         ensure_ascii=False)
        f = self.write('a.jsonl', row + '\n')
        before = f.read_bytes()
        rep = A.resolve_file(self.st, f)
        self.assertEqual(f.read_bytes(), before)
        self.assertEqual((rep.rewritten, len(rep.errors)), (0, 1))

    def test_existing_bad_pointer_is_an_error(self):
        row = json.dumps({'s': 'person:canon:linyuan', 'p': 'gender', 'v': 'male', 'e': [[1, 1, 0, 2, '0' * 16]]})
        f = self.write('a.jsonl', row + '\n')
        before = f.read_bytes()
        rep = A.resolve_file(self.st, f)
        self.assertEqual(f.read_bytes(), before)
        self.assertIn('哈希不符', rep.errors[0][1])

    def test_dry_run_and_crlf_and_full_format(self):
        row = {'subject': 'person:canon:linyuan', 'property': 'gender', 'value': 'male', 'evidence': [[1, 1, '老艄公']]}
        f = self.write('a.jsonl', json.dumps(row, ensure_ascii=False) + '\r\n' + json.dumps(row, ensure_ascii=False) + '\r\n')
        before = f.read_bytes()
        A.resolve_file(self.st, f, dry_run=True)
        self.assertEqual(f.read_bytes(), before)
        A.resolve_file(self.st, f)
        lines = f.read_bytes().decode('utf-8').split('\n')
        self.assertTrue(lines[0].endswith('\r'))
        r = json.loads(lines[0])
        self.assertEqual(r['basis'], 'text')                            # 完整格式用 basis
        self.assertNotIn('b', r)
        self.assertEqual(len(r['evidence'][0]), 5)
        full = S.expand_assertion(r)
        self.assertEqual(full['basis'], 'text')
        self.assertEqual(S.validate_assertion(full), [])

    def test_resolved_rows_validate_as_text_basis(self):
        f = self.write('a.jsonl', json.dumps({'s': 'person:canon:linyuan', 'p': 'gender', 'v': 'male', 'e': [[1, 1, '老艄公']]},
                                             ensure_ascii=False) + '\n')
        A.resolve_file(self.st, f)
        a = S.expand_assertion(json.loads(f.read_text(encoding='utf-8')))
        self.assertEqual(a['basis'], 'text')
        self.assertEqual(S.validate_assertion(a), [])


class CliTests(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.src = self.source()
        self.common = ['--source', str(self.src), '--expect', '0', '--canon-dir', str(self.tmp)]
        self.st = synth_store()

    def call(self, *argv):
        return run_main(textcli.main, list(argv))

    def test_info(self):
        rc, out = self.call('info', *self.common)
        self.assertEqual(rc, 0)
        self.assertIn('版面 sanlian', out)
        self.assertIn('去水印标记 3 处', out)
        self.assertRegex(out, r'  1  石桥夜雨 +3 ')
        self.assertIn('附录 某某先生书函', out)

    def test_export_line_format_and_dir_rule(self):
        rc, out = self.call('export', '--ch', '1-2', '--out', str(self.tmp / 'o'), *self.common)
        self.assertEqual(rc, 0)
        f = self.tmp / 'o' / 'chapters' / 'ch01.txt'
        self.assertTrue(f.is_file())
        self.assertTrue((self.tmp / 'o' / 'chapters' / 'ch02.txt').is_file())
        self.assertFalse((self.tmp / 'o' / 'chapters' / 'ch03.txt').exists())
        lines = f.read_text(encoding='utf-8').split('\n')
        self.assertEqual(lines[-1], '')
        lines = lines[:-1]
        self.assertEqual(len(lines), 3)
        for i, ln in enumerate(lines, 1):
            m = re.match(r'^\[c1p(\d+)\] (.+)$', ln)
            self.assertTrue(m, ln)
            self.assertEqual(int(m.group(1)), i)
            self.assertEqual(m.group(2), self.st.paragraph(1, i).text)
        # DIR 自己叫 chapters 时直接用
        self.call('export', '--ch', '3', '--out', str(self.tmp / 'x' / 'chapters'), *self.common)
        self.assertTrue((self.tmp / 'x' / 'chapters' / 'ch03.txt').is_file())
        # --all 含 0/51/52
        self.call('export', '--all', '--out', str(self.tmp / 'all'), *self.common)
        names = sorted(p.name for p in (self.tmp / 'all' / 'chapters').iterdir())
        self.assertEqual(names, ['ch00.txt', 'ch01.txt', 'ch02.txt', 'ch03.txt', 'ch51.txt', 'ch52.txt'])
        rc, out = self.call('export', '--ch', '9', '--out', str(self.tmp / 'o'), *self.common)
        self.assertEqual(rc, 1)
        self.assertIn('没有这些回', out)

    def test_show_and_find(self):
        rc, out = self.call('show', '1', '--from', '2', '--to', '3', *self.common)
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines(), [f'[c1p2] {self.st.paragraph(1, 2).text}', f'[c1p3] {self.st.paragraph(1, 3).text}'])
        self.assertEqual(self.call('show', '1', '--from', '9', *self.common)[0], 1)
        rc, out = self.call('find', '林远', *self.common)
        self.assertEqual(rc, 0)
        self.assertIn('命中 7 处', out)
        self.assertRegex(out, r'第 1 回：3 处  c1p1@0')
        self.assertNotIn('石桥', out)                                   # 不打印原文
        rc, out = self.call('find', '林远', '--ch', '3', *self.common)
        self.assertIn('第 3 回命中 3 处', out)
        self.assertEqual(self.call('find', '没有这个串', *self.common)[0], 1)

    def test_ptr(self):
        rc, out = self.call('ptr', '1', '1', '老艄公', *self.common)
        self.assertEqual(rc, 0)
        ptr = json.loads(out)
        self.assertEqual(self.st.get_span(ptr), '老艄公')
        self.assertEqual(self.call('ptr', '1', '1', '了', *self.common)[0], 1)              # 不唯一
        self.assertIn('出现', run_main.err)
        rc, out = self.call('ptr', '1', '1', '了', '--nth', '2', *self.common)
        self.assertEqual(rc, 0)
        self.assertEqual(self.st.get_span(json.loads(out)), '了')
        self.assertEqual(self.call('ptr', '1', '1', '不存在', *self.common)[0], 1)
        self.assertIn('找不到', run_main.err)

    def test_verify_evidence_cli(self):
        f = self.write('ev/a.jsonl', json.dumps({'s': 'x', 'p': 'y', 'v': 'z',
                                                  'e': [[1, 1, 3, 6, self.st.paragraph(1, 1).hash], [1, 1, 3, 6, '0' * 16],
                                                        [1, 1, '锚点未解析'], [1, 1, 4, 4, self.st.paragraph(1, 1).hash]]}) + '\n')
        rc, out = self.call('verify-evidence', str(f.parent), *self.common)
        self.assertEqual(rc, 1)
        self.assertIn('指针 4，有效 1', out)
        self.assertIn('25.0%', out)
        self.assertIn('哈希不符', out)
        self.assertIn('未解析的锚点', out)
        self.assertIn('空串', out)
        good = self.write('ev/b.jsonl', json.dumps({'s': 'x', 'p': 'y', 'v': 'z', 'e': [[1, 1, 3, 6, self.st.paragraph(1, 1).hash]]}) + '\n')
        rc, out = self.call('verify-evidence', str(good), *self.common)
        self.assertEqual(rc, 0)
        self.assertIn('100.0%', out)
        self.assertEqual(self.call('verify-evidence', str(self.tmp / 'nope'), *self.common)[0], 2)

    def test_manifest_cli(self):
        rc, out = self.call('manifest', *self.common)
        self.assertEqual(rc, 0)                                         # 没有清单：只报告
        self.assertIn('还没有清单', out)
        self.assertEqual(self.call('manifest', '--check', *self.common)[0], 1)
        rc, out = self.call('manifest', '--write', *self.common)
        self.assertEqual(rc, 0)
        mf = self.tmp / T.MANIFEST_NAME
        self.assertTrue(mf.is_file())
        m = json.loads(mf.read_text(encoding='utf-8'))
        self.assertEqual(m['text_sha256'], self.st.text_sha256())
        self.assertEqual(mf.read_text(encoding='utf-8').count('\n'), len(m['chapters']) + 11)     # 一回一行，便于 diff
        rc, out = self.call('manifest', '--check', *self.common)
        self.assertEqual(rc, 0)
        self.assertIn('相符', out)
        # 换了文本：不符
        other = self.source(T.normalize(self.src.read_text(encoding='utf-8')).replace('老艄公', '老船夫'), name='o.txt')
        rc, out = self.call('manifest', '--source', str(other), '--expect', '0', '--canon-dir', str(self.tmp))
        self.assertEqual(rc, 1)
        self.assertIn('不符', out)

    def test_missing_source_and_bad_layout(self):
        rc, out = self.call('info', '--source', str(self.tmp / 'none.txt'), '--canon-dir', str(self.tmp))
        self.assertEqual(rc, 2)
        self.assertIn('找不到原文', out)
        rc, out = self.call('info', '--source', str(self.src), '--canon-dir', str(self.tmp))      # 默认 --expect 50
        self.assertEqual(rc, 2)
        self.assertIn('应有 50 回', out)

    def test_canon_resolve_main(self):
        f = self.write('a.jsonl', json.dumps({'s': 'person:canon:linyuan', 'p': 'gender', 'v': 'male', 'e': [[1, 1, '老艄公']]},
                                             ensure_ascii=False) + '\n' +
                       json.dumps({'s': 'person:canon:linyuan', 'p': 'org', 'v': 'none', 'e': [[1, 1, '了']]}, ensure_ascii=False) + '\n')
        rc, out = run_main(A.main, [str(f), *self.common])
        self.assertEqual(rc, 1)
        self.assertIn('改写 1 行', out)
        self.assertIn('a.jsonl:2', out)
        self.assertIn('出现', out)
        rc, out = run_main(A.main, [str(f), '--dry-run', *self.common])
        self.assertEqual(rc, 1)
        self.assertEqual(run_main(A.main, [str(self.tmp / 'nope.jsonl'), *self.common])[0], 2)


if __name__ == '__main__':
    unittest.main()
