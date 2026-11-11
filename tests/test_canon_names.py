"""提及普查与缺名检测（tools/canon_names.py = tianl/canon/names.py）：mentions / verify / candidates。

先在一本为测试自编的小书（虚构内容，3 回）和 5 个自造实体上跑通；再在真原文上做合理性核对
（有 sources/tianlong.txt 才运行；测试里不写任何原文片段，名字只来自 schema 里的 30 人召回名单）。
"""
import json
import re
import unittest

from tianl.canon import names as N
from tianl.canon import schema as S
from tianl.canon import text as T
from tests.test_canon_common import HAVE_REAL, IND, REAL_SOURCE, TmpDirCase, real_store, run_main

ENTS = [
    {'id': 'person:canon:linyuan', 'type': 'person', 'name': '林远', 'aliases': ['林少侠', '远'], 'note': '虚构'},
    {'id': 'person:canon:suxiaotang', 'type': 'person', 'name': '苏小棠', 'aliases': ['小棠'], 'note': '虚构'},
    {'id': 'person:canon:huiming', 'type': 'person', 'name': '慧明', 'aliases': ['慧明大师'], 'note': '虚构'},
    {'id': 'place:canon:baitasi', 'type': 'place', 'name': '白塔寺', 'aliases': [], 'note': '虚构'},
    {'id': 'org:canon:tiejianmen', 'type': 'org', 'name': '铁剑门', 'aliases': ['铁剑派'], 'note': '虚构'},
]


def small_book():
    """第 1 回：12 组“归云冷笑道：…林远答道：…”（归云没登记）；第 2 回：白塔寺与铁剑门各出现一次。"""
    p = [IND + '林远与苏小棠在石桥相遇。']
    for i in range(12):
        p.append(IND + f'归云冷笑道：“第{i}回合的虚构对白。”林远答道：“知道了。”')
        p.append(IND + '林少侠望了望天色。苏小棠站在桥头，慧明大师没有说话。')
    return ('一 石桥夜雨\n' + '\n'.join(p) + '\n二 白塔寺中\n'
            + IND + '白塔寺里，慧明大师与慧明在院中。铁剑门的人并没有来。\n三 云梦镇上\n' + IND + '尾声。\n')


class SmallRegistryTests(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.book = self.source(small_book())
        self.census = self.write('census/p1.jsonl', '\n'.join(json.dumps(e, ensure_ascii=False) for e in ENTS) + '\n')
        self.common = ['--source', str(self.book), '--expect', '0', '--canon-dir', str(self.tmp)]
        self.store = T.TextStore.from_file(self.book, expect_chapters=0)

    def run_names(self, *argv):
        return run_main(N.main, list(argv))

    # ---- mentions ----
    def mentions(self, **kw):
        out_dir, counts = self.tmp / 'out', self.tmp / 'mention_counts.tsv'
        rc, out = self.run_names('mentions', *self.common, '--entities', str(self.census), '--out', str(out_dir), '--counts', str(counts))
        return rc, out, out_dir / 'mentions.tsv', counts

    def test_mentions_counts_are_longest_match_and_sorted(self):
        rc, out, mtsv, counts = self.mentions()
        self.assertEqual(rc, 0, out)
        self.assertIn('登记 5 个实体', out)
        self.assertIn('单字称呼 1 个不参与匹配', out)                           # 单字别名“远”
        self.assertIn('字位取回校验错误 0', out)
        lines = counts.read_text(encoding='utf-8').splitlines()
        self.assertEqual(lines[0], 'entity\tch\tcount')
        rows = [l.split('\t') for l in lines[1:]]
        self.assertEqual(rows, sorted(rows, key=lambda r: (r[0], int(r[1]))))   # 按实体、回排序
        got = {(e, int(ch)): int(n) for e, ch, n in rows}
        self.assertEqual(got[('person:canon:linyuan', 1)], 25)                  # 13 处“林远”+ 12 处别名“林少侠”
        self.assertEqual(got[('person:canon:suxiaotang', 1)], 13)               # “小棠”被“苏小棠”吞掉，不重复计
        self.assertEqual(got[('person:canon:huiming', 1)], 12)
        self.assertEqual(got[('person:canon:huiming', 2)], 2)
        self.assertEqual(got[('place:canon:baitasi', 2)], 1)
        self.assertEqual(got[('org:canon:tiejianmen', 2)], 1)
        self.assertNotIn('归云', counts.read_text(encoding='utf-8'))            # 没登记的不计

    def test_mentions_tsv_points_back_to_the_surface_and_counts_file_has_no_text(self):
        rc, out, mtsv, counts = self.mentions()
        surfaces = {sf: e['id'] for e in ENTS for sf in [e['name']] + e['aliases'] if len(sf) > 1}
        n = 0
        for line in mtsv.read_text(encoding='utf-8').splitlines()[1:]:
            eid, ch, para, start, end = line.split('\t')
            got = self.store.get_span({'ch': int(ch), 'para': int(para), 'start': int(start), 'end': int(end),
                                       'hash': self.store.paragraph(int(ch), int(para)).hash})
            self.assertEqual(surfaces[got], eid)                               # 按字位能取回同一个称呼
            n += 1
        self.assertEqual(n, 54)
        # 入库的汇总里只有 实体编号、回号、次数：没有任何汉字
        for line in counts.read_text(encoding='utf-8').splitlines()[1:]:
            self.assertRegex(line, r'^[a-z]+:canon:[a-z0-9]+\t\d+\t\d+$')
        self.assertNotRegex(counts.read_text(encoding='utf-8'), r'[一-鿿]')

    def test_mentions_without_registry_is_usage_error(self):
        rc, out = self.run_names('mentions', '--source', str(self.book), '--expect', '0', '--canon-dir', str(self.tmp / 'void'))
        self.assertEqual(rc, 2)
        self.assertIn('没有实体登记', out)

    def test_ambiguous_surface_is_counted_as_pseudo_entity(self):
        rows = [dict(ENTS[2], aliases=['慧明大师', {'name': '大师', 'ambiguous': True}]),
                {'id': 'person:canon:huineng', 'type': 'person', 'name': '慧能', 'aliases': [{'name': '大师', 'ambiguous': True}]}]
        reg = self.write('amb/p1.jsonl', '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n')
        book = self.source(IND_BOOK_AMB, 'amb.txt')
        counts = self.tmp / 'amb.tsv'
        rc, out = self.run_names('mentions', '--source', str(book), '--expect', '0', '--canon-dir', str(self.tmp),
                                 '--entities', str(reg), '--out', str(self.tmp / 'o2'), '--counts', str(counts))
        self.assertEqual(rc, 0, out)
        text = counts.read_text(encoding='utf-8')
        self.assertIn('ambiguous:大师', text)
        self.assertIn('歧义称呼提及 1 条', out)

    # ---- verify ----
    def test_verify_reports_zero_hits_swallowed_and_single_char(self):
        rc, out = self.run_names('verify', str(self.census), *self.common)
        self.assertEqual(rc, 1, out)                                           # 铁剑派 0 命中 = 错误
        self.assertIn('别名 铁剑派：全书 0 处，首见 —', out)
        self.assertIn('0 命中', out)
        self.assertIn('别名 小棠', out)
        self.assertIn('被更长名字吞掉（主要被“苏小棠”）', out)
        self.assertIn('单字别名', out)
        self.assertIn('错误 1（0 命中的名字/别名、登记冲突），警告 2（被吞、单字） -> 有问题', out)
        self.assertIn('person:canon:linyuan 林远：全书 13 处，首见 第 1 回', out)
        self.assertIn('place:canon:baitasi 白塔寺：全书 1 处，首见 第 2 回', out)

    def test_verify_warnings_do_not_fail_unless_strict(self):
        rows = [dict(e, aliases=[a for a in e['aliases'] if a not in ('铁剑派', '远')]) for e in ENTS]      # 去掉 0 命中与单字别名
        f = self.write('warn.jsonl', '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n')
        rc, out = self.run_names('verify', str(f), *self.common, '--only')
        self.assertEqual(rc, 0, out)
        self.assertIn('错误 0（0 命中的名字/别名、登记冲突），警告 1（被吞、单字） -> 通过', out)        # 小棠被苏小棠吞：只是警告
        rc, out = self.run_names('verify', str(f), *self.common, '--only', '--strict')
        self.assertEqual(rc, 1, out)
        rows = [dict(r, aliases=[a for a in r['aliases'] if a != '小棠']) for r in rows]
        g = self.write('clean.jsonl', '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n')
        rc, out = self.run_names('verify', str(g), *self.common, '--only', '--strict')
        self.assertEqual(rc, 0, out)
        self.assertIn('错误 0（0 命中的名字/别名、登记冲突），警告 0（被吞、单字） -> 通过', out)

    def test_verify_missing_file_and_quiet(self):
        rc, out = self.run_names('verify', str(self.tmp / 'no.jsonl'), *self.common)
        self.assertEqual(rc, 2)
        rc, out = self.run_names('verify', str(self.census), *self.common, '--quiet')
        self.assertNotIn('林远：全书', out)                                    # 没问题的行不打印
        self.assertIn('铁剑派', out)

    # ---- candidates ----
    def test_candidates_find_unregistered_speaker_and_print_no_text(self):
        rc, out = self.run_names('candidates', '--type', 'person', *self.common, '--entities', str(self.census))
        self.assertEqual(rc, 0, out)
        self.assertIn('登记 5 个实体', out)
        lines = out.splitlines()
        rows = lines[2:]
        self.assertEqual(len(rows), 1, out)
        self.assertRegex(rows[0], r'^归云\s+12\s+12\s+1\s+c1p2$')              # 候选 命中 句式次数 首见回 示例段编号
        # 已登记的不再出现
        for e in ENTS:
            for sf in [e['name']] + e['aliases']:
                self.assertNotIn(sf, ''.join(rows))
        # 输出只有：说明、表头、“名字 + 整数 + 段编号”：不含任何段落文字（虚构对白里的独特词不得出现）
        self.assertNotIn('虚构对白', out)
        self.assertNotIn('望了望天色', out)
        for r in rows:
            self.assertRegex(r, r'^\S{2,4}\s+\d+\s+\d+\s+\d+\s+c\d+p\d+$')

    def test_candidates_min_and_registered_cover(self):
        rc, out = self.run_names('candidates', '--type', 'person', *self.common, '--entities', str(self.census), '--min', '13')
        self.assertEqual(out.splitlines()[2:], [])                             # 12 次 < 13
        rc, out = self.run_names('candidates', '--type', 'person', *self.common)    # 缺省登记表 = canon-dir/census（5 个自造实体）：归云仍是候选
        self.assertIn('归云', out)
        reg = self.write('reg2.jsonl', json.dumps({'id': 'person:canon:guiyun', 'type': 'person', 'name': '归云', 'aliases': []}, ensure_ascii=False) + '\n')
        rc, out = self.run_names('candidates', '--type', 'person', *self.common, '--entities', str(reg))
        self.assertNotIn('归云', out)                                          # 登记之后不再是候选

    def test_candidates_other_types_run(self):
        for typ in ('place', 'org', 'martial', 'item'):
            rc, out = self.run_names('candidates', '--type', typ, *self.common, '--entities', str(self.census))
            self.assertEqual(rc, 0, (typ, out))
            self.assertIn('示例段只给编号', out)

    def test_bad_source_is_clear_error(self):
        rc, out = self.run_names('candidates', '--type', 'person', '--source', str(self.tmp / 'missing.txt'), '--expect', '0')
        self.assertEqual(rc, 2)
        self.assertIn('错误', out)


def noise_book():
    """虚构小书：每种情形重复 12 次，左右文字都有变化（避开“右边总跟同一个字”的过滤）。
    林小河：说话归属句式里的人名，末字“河”是地点后缀；白云岭：真地点；武林：泛称；决计不会、走上几步、呼的一掌：虚词残片。"""
    verbs = ['冷笑', '答', '说', '笑', '叹', '问']
    after = '上下左右前后中里外内'
    p = []
    for i in range(12):
        p.append(IND + f'林小河{verbs[i % 6]}道：“第{i}回合。”')
        p.append(IND + f'远处，白云岭{after[i % 10]}一片苍茫。')
        p.append(IND + f'传闻，武林{"中人事风云盛衰"[i % 7]}多有变故。')
        p.append(IND + f'谁说，决计不会{after[i % 10]}去。')
        p.append(IND + f'只见，走上几步{after[(i + 3) % 10]}回头。')
        p.append(IND + f'忽然，呼的一掌{after[(i + 5) % 10]}拍出。')
    return '一 虚构\n' + '\n'.join(p) + '\n二 尾声\n' + IND + '尾声。\n'


class CandidateNoiseFilterTests(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.book = self.source(noise_book())
        self.reg = self.write('reg.jsonl', json.dumps({'id': 'person:canon:x', 'type': 'person', 'name': '某某人物', 'aliases': []},
                                                      ensure_ascii=False) + '\n')
        self.common = ['--source', str(self.book), '--expect', '0', '--canon-dir', str(self.tmp), '--entities', str(self.reg)]

    def cand(self, typ):
        rc, out = run_main(N.main, ['candidates', '--type', typ, *self.common])
        self.assertEqual(rc, 0, out)
        return [l.split()[0] for l in out.splitlines()[2:]]

    def test_person_is_a_person_candidate_and_stays_out_of_place_candidates(self):
        self.assertIn('林小河', self.cand('person'))
        place = self.cand('place')
        self.assertNotIn('林小河', place)                 # 末字“河”像地点，但在说话归属句式里站得住：是人
        self.assertIn('白云岭', place)                    # 没有说话句式的真地点照常列出
        for typ in ('org', 'martial', 'item'):
            self.assertNotIn('林小河', self.cand(typ))

    def test_generic_words_and_function_word_fragments_are_dropped(self):
        place = self.cand('place')
        self.assertNotIn('武林', place)                   # 泛称
        org = self.cand('org')
        self.assertNotIn('决计不会', org)                 # “…不会”不是“会”字组织
        martial = self.cand('martial')
        self.assertNotIn('走上几步', martial)             # 名字中间不会有“几”
        self.assertNotIn('呼的一掌', martial)             # 名字中间不会有“的”

    def test_person_like_matches_the_person_candidates(self):
        st = T.TextStore.from_file(self.book, expect_chapters=0)
        pl = N.person_like(st)
        self.assertIn('林小河', pl)
        self.assertNotIn('白云岭', pl)


IND_BOOK_AMB = ('一 石桥夜雨\n' + IND + '大师没有说话。\n' + IND + '慧明大师与慧能在院中。\n二 白塔寺中\n' + IND + '尾声。\n三 云梦镇上\n' + IND + '尾声。\n')


# ----------------------------------------------------------------------------------------------------------------------
# 真原文
# ----------------------------------------------------------------------------------------------------------------------
@unittest.skipUnless(HAVE_REAL, '没有原文 sources/tianlong.txt：跳过真文本核对')
class RealTextNamesTests(TmpDirCase):
    # 5 个自造实体：名字来自召回名单（人物）与常识（少林寺同时是组织与地点）
    REG = [
        {'id': 'person:canon:duanyu', 'type': 'person', 'name': '段誉', 'aliases': ['段公子']},
        {'id': 'person:canon:azhu', 'type': 'person', 'name': '阿朱', 'aliases': []},
        {'id': 'person:canon:qiaofeng', 'type': 'person', 'name': '乔峰', 'aliases': ['萧峰', '乔帮主']},
        {'id': 'org:canon:shaolinsi', 'type': 'org', 'name': '少林寺', 'aliases': ['少林派']},
        {'id': 'place:canon:shaolinsi', 'type': 'place', 'name': '少林寺', 'aliases': []},
    ]

    def setUp(self):
        super().setUp()
        self.census = self.write('census/p1.jsonl', '\n'.join(json.dumps(r, ensure_ascii=False) for r in self.REG) + '\n')
        self.common = ['--source', str(REAL_SOURCE), '--canon-dir', str(self.tmp)]

    def test_mentions_match_an_independent_count(self):
        counts = self.tmp / 'mc.tsv'
        rc, out = run_main(N.main, ['mentions', *self.common, '--entities', str(self.census), '--out', str(self.tmp / 'o'), '--counts', str(counts)])
        self.assertEqual(rc, 0, out)
        by, first = {}, {}
        for line in counts.read_text(encoding='utf-8').splitlines()[1:]:
            e, ch, n = line.split('\t')
            by[e] = by.get(e, 0) + int(n)
            first.setdefault(e, int(ch))
        # 独立算：最长匹配、不重叠（用正则交替式，长的在前）
        alts = {r['name']: r['id'] for r in self.REG if r['type'] == 'person'}
        for r in self.REG:
            for a in r['aliases']:
                alts[a] = r['id']
        rx = re.compile('|'.join(sorted(map(re.escape, list(alts) + ['少林寺', '少林派']), key=lambda s: (-len(s), s))))
        want, want_first = {}, {}
        for p in real_store().iter_paragraphs():
            for m in rx.finditer(p.text):
                sf = m.group(0)
                ids = ['org:canon:shaolinsi', 'place:canon:shaolinsi'] if sf in ('少林寺',) else [alts.get(sf, 'org:canon:shaolinsi')]
                for e in ids:
                    want[e] = want.get(e, 0) + 1
                    want_first.setdefault(e, p.ch)
        for e in ('person:canon:duanyu', 'person:canon:azhu', 'person:canon:qiaofeng', 'org:canon:shaolinsi', 'place:canon:shaolinsi'):
            self.assertEqual(by[e], want[e], e)
            self.assertEqual(first[e], want_first[e], e)
        # 与 CANON_SCHEMA 第 11 节：阿朱首见第 11 回、乔峰（含萧峰）首见第 9 回、段誉第 1 回
        self.assertEqual((first['person:canon:azhu'], first['person:canon:qiaofeng'], first['person:canon:duanyu']), (11, 9, 1))

    def test_verify_flags_the_seeded_defects(self):
        bad = self.REG + [{'id': 'person:canon:ghost', 'type': 'person', 'name': '并无此人', 'aliases': ['无此别名', '誉']}]
        f = self.write('bad.jsonl', '\n'.join(json.dumps(r, ensure_ascii=False) for r in bad) + '\n')
        rc, out = run_main(N.main, ['verify', str(f), *self.common, '--only'])
        self.assertEqual(rc, 1, out)
        self.assertIn('规范名 0 命中 1', out)
        self.assertIn('并无此人', out)
        self.assertIn('单字别名', out)

    def test_candidates_person_top_are_real_characters(self):
        rc, out = run_main(N.main, ['candidates', '--type', 'person', *self.common, '--entities', str(self.census), '--top', '40'])
        self.assertEqual(rc, 0, out)
        top = [l.split()[0] for l in out.splitlines()[2:]]
        self.assertEqual(len(top), 40)
        # 召回名单里没登记的人，应该大量出现在前 40 名（“萧远山”这类常以别称出现的除外）
        known = {r[0] for r in S.RECALL_30} - {'段誉', '阿朱', '乔峰'}
        got = [k for k in known if any(t == k or t in k or k in t for t in top)]
        self.assertGreaterEqual(len(got), 18, f'前 40 名里只命中召回名单 {len(got)} 人')
        # 已登记的称呼不得出现；不得出现“某某道”式的残片（候选 2–4 字、只有汉字）
        for sf in ('段誉', '段公子', '阿朱', '乔峰', '萧峰'):
            self.assertNotIn(sf, top)
        for t in top:
            self.assertRegex(t, r'^[一-鿿]{2,4}$')
        # 输出里除候选名外只有数字与段编号：不含段落文字
        for l in out.splitlines()[2:]:
            self.assertRegex(l, r'^\S{2,4}\s+\d+\s+\d+\s+\d+\s+c\d+p\d+$')


if __name__ == '__main__':
    unittest.main()
