"""C 段第二步：引擎由 defs 驱动。

* 原型场景 scenario:proto60 完全由 defs/*/proto60*.toml 描述（SiteSpec.from_defs）；加载引用完整性 100%，内核照常加载；
* 行为包是数据：栈的次序、who / when / do、处理器 + 参数都来自 defs；声明式包按“先具体日子，再天气，再季节，最后默认”匹配；
  处理器登记表带参数校验，可扩展；
* 四个钩子（life.pulse / controller.decide / lod.observe / persist.flush）存在、默认空操作、后续模块不用改 engine.py；
* 泛化：同一份 defs 把人口从 60 改成 300 能跑 30 日；缺字段、引用不存在的包、未登记的处理器、参数不合法……都给出可读的报错；
* 文档（docs/NPC_ENGINE.md 第 12 节）没有漏掉任何字段、处理器、准入门。
原型哈希与全部数字的比对在 test_npc_proto.py / test_npc_spec.py，这里不重复。
"""
import ast
import contextlib
import dataclasses
import inspect
import re
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from tianl.core import cal, rnd_b2
from tianl.defs import Defs, DefsError
from tianl.npc import NpcEngine, ProtoRun, StandaloneHost, controller, life, lod, persist, proto60_spec
from tianl.npc.defsload import ROLES, docs_markdown, field_docs
from tianl.npc.handlers import GATE_PARAMS, GATES, PACKAGE_HANDLERS, Param, ParamCtx, check_params, package_handler
from tianl.npc.report import scale_report
from tianl.npc.scenarios import DEFS_ROOT, PROTO60_ID, given_name, gossip_script, load_defs, proto60_roster, proto60_scenario
from tianl.npc.spec import (L_DEVIANT, L_GROUP, DoSpec, PackageSpec, ScenarioSpec, SiteSpec, SpecError, WhenSpec,
                            WhoSpec)
from tests.test_npc_support import package, pkg_index, shared_run, with_package

BASE_HASH = 'e8f8209eeb8ca94a'      # 基准 = 60 僧 × 30 日 + 传闻脚本（gossip，第 6 日）；不带脚本的 ProtoRun() 是另一个世界（5002a67d7ebb5feb）
NPC_SRC = Path(__file__).resolve().parent.parent / 'tianl' / 'npc'
DOC = Path(__file__).resolve().parent.parent / 'docs' / 'NPC_ENGINE.md'


# ================================================================= 1 defs 驱动的规格
class DefsDrivenSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs = load_defs()
        cls.sp = proto60_spec()

    def test_the_whole_defs_tree_loads_with_full_referential_integrity(self):
        d = Defs.load(DEFS_ROOT)                                   # 严格加载：有一条悬空引用就抛 DefsError
        self.assertEqual(d.problems, [])
        refs = resolved = 0
        for i in d.ids():
            res = d.get(i)
            if res.get('_abstract'):
                continue
            for _, ref in d._refs({k: v for k, v in res.items() if k not in ('id', 'kind', '_file', 'parent')}):
                refs += 1
                resolved += ref in d
        self.assertGreater(refs, 150)
        self.assertEqual(resolved, refs)                           # 引用完整性 100%
        print('\n[defs] 整棵 defs 树 %d 条定义，%d 条引用全部可解析（%d%%）' % (len(d), refs, 100 * resolved // refs))

    def test_every_proto60_definition_is_consumed_by_the_spec(self):
        """同 scope 的每条（非抽象）定义都被规格用到：没有漏了引用的孤儿（构造时会报，见 ErrorReporting）。这里数一数。"""
        counts = Counter(x['id'].partition(':')[0] for x in (self.defs.get(i) for i in self.defs.ids())
                         if x['id'].split(':')[1] == 'proto60' and not x.get('_abstract'))
        self.assertEqual(dict(counts), {'place': 21, 'facility': 7, 'interaction': 19, 'post': 14, 'job': 8, 'trait': 5,
                                        'package': 36, 'thought': 8, 'modifier': 4, 'event': 7, 'norm': 4, 'ladder': 1,
                                        'org': 5, 'rule': 11, 'scenario': 3})
        sp = self.sp
        self.assertEqual((len(sp.places), len(sp.offices), len(sp.interactions), len(sp.ads), len(sp.jobs.board),
                          len(sp.stack)), (21, 14, 19, 7, 8, 36))

    def test_spec_validates_and_is_built_from_defs_only(self):
        self.assertEqual(self.sp.validate(), [])
        self.assertIs(proto60_spec(), self.sp)                       # 缓存：同一进程里是同一个对象
        again = SiteSpec.from_defs(self.defs, PROTO60_ID)
        self.assertEqual(again, self.sp)                             # 同一份 defs 构造两次逐字段相等
        self.assertEqual(proto60_spec(self.defs), self.sp)
        # 只有 defsload.py 构造 SiteSpec：引擎、场景代码里没有手写的规格
        for f in sorted(NPC_SRC.glob('*.py')):
            for n in ast.walk(ast.parse(f.read_text(encoding='utf-8'))):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('SiteSpec', 'ScenarioSpec'):
                    self.assertEqual(f.name, 'defsload.py', '%s:%d 手写了 %s' % (f.name, n.lineno, n.func.id))

    def test_scenario_comes_from_defs(self):
        scn = proto60_scenario()
        self.assertIsInstance(scn, ScenarioSpec)
        self.assertEqual((scn.seed, scn.population, scn.days), (20261110, 60, 30))
        self.assertEqual(scn.cast, ((5, {'T': 92, 'S': 22, 'D': 45}), (11, {'D': 18, 'S': 38}), (20, {'R': 95, 'S': 90})))
        self.assertEqual((scn.gossip.day, scn.gossip.who, scn.gossip.heard, scn.n1.day, scn.n1.days, scn.long_days,
                          scn.extra_seeds), (6, 8, 9, 10, 4, 90, (1, 2, 3, 4, 5)))
        self.assertEqual((scn.n1.sick, scn.n1.arms), ((('典座', None), ('饭头', 3)), (('无人代理', False), ('监院派人代理', True))))
        self.assertEqual((scn.observer_place, scn.trace_post, scn.trace_day), ('clo', '典座', 8))

    def test_kernel_still_loads_and_ignores_the_npc_scope(self):
        """内核加载 space / org / post / scenario 等目录：proto60 的文件在其中，必须能被它加载、且不进内核的库表。"""
        from tianl.kernel.spec import load_kernel_defs, load_spec
        k = load_kernel_defs()
        self.assertTrue(any(i.startswith('place:proto60:') for i in k.ids()))          # 内核加载得到 proto60 的文件……
        codes = {p[0] for p in load_spec().places}
        self.assertFalse({'hall', 'kit', 'dorm1'} & codes)          # ……但原型短码没有混进内核的场所表
        self.assertEqual(codes, {d['code'] for d in map(k.get, k.ids()) if d['id'].startswith('place:shaolin:')})   # 内核的场所表只有 shaolin scope

    def test_place_codes_are_the_prototype_short_codes(self):
        """原型场景的场所 code 沿用原型短码（它进随机数键与基线哈希）：defs 里改 code 就是另一个世界。"""
        self.assertEqual(set(self.sp.places), {'hall', 'zen', 'ref', 'kit', 'store', 'dorm1', 'dorm2', 'dorm3', 'lib', 'yard',
                                               'garden', 'gate', 'bath', 'court', 'inf', 'clo', 'well', 'woods', 'mill',
                                               'abbot', 'office'})
        self.assertEqual(self.defs.by_code('place', 'hall')['name'], '大雄宝殿')

    def test_no_prototype_numbers_in_engine_code_but_the_spec_is_complete(self):
        """规格里的数都来自 defs：改 defs 里的一个数，规格就跟着变（用一份临时拷贝验证）。"""
        with patched_defs() as pd:
            pd.edit('knowledge/proto60.toml', 'penalty = 12', 'penalty = 13')
            pd.edit('post/proto60_packages.toml', 'th_base = 35', 'th_base = 36')
            sp = SiteSpec.from_defs(pd.load(), PROTO60_ID)
        self.assertEqual((sp.rumor.penalty, package(sp, 'tempted_night').params['th_base']), (13, 36))
        self.assertEqual((self.sp.rumor.penalty, package(self.sp, 'tempted_night').params['th_base']), (12, 35))


# ================================================================= 2 行为包是数据
def baseline_hash():
    """原型基准的哈希：与 reference/logs/npc_run_log.txt 的“基准”一行同一个运行（场景的传闻脚本在内），rnd_b2。"""
    return shared_run(gossip=True).hash                          # 只读共用的一次运行（见 test_npc_support.shared_run）


def W(**kw):
    """WhenSpec 的简写：没写的条件都是 None。"""
    return WhenSpec(**{k: kw.get(k) for k in ('slots', 'periods', 'days', 'doms', 'months', 'festivals', 'weathers', 'seasons')})


def extra_class_package(sp, label, **when):
    """在集体层（早课所在的那一组）末尾加一个 3 时辰（卯）的声明式包：去禅堂坐禅，原因是 label。次序故意放在默认的早课之后。"""
    when.setdefault('slots', (3,))
    pk = PackageSpec('package:test:' + label, L_GROUP, WhoSpec(None, None, None), W(**when),
                     DoSpec('zen', 'zazen', label, False, None, ''), None, {})
    i = max([pkg_index(sp, 'evening_zazen')] + [j for j, x in enumerate(sp.stack) if x.id.startswith('package:test:')]) + 1
    return dataclasses.replace(sp, stack=sp.stack[:i] + (pk,) + sp.stack[i:])          # 排在已加的测试包之后：同级时先加的先列


def label_counts(run, day, slot=3):
    eng = run.engine
    return Counter(eng.where(p.ix, day, slot)[3] for p in eng.people)


class WeatherHost(StandaloneHost):
    """会报天气的 Host（weather(day) 是可选的 Host 能力；没有它，带 weather 条件的包永不成立）。"""

    def __init__(self, seed, rainy):
        super().__init__(seed, rnd_b2)
        self.rainy = set(rainy)

    def weather(self, day):
        return '雨' if day in self.rainy else '晴'


class CalendarKeys(unittest.TestCase):
    """when 的日历键与匹配次序（计划 6.2，照《星露谷物语》）：先具体日子，再天气，再季节，最后默认。"""

    @classmethod
    def setUpClass(cls):
        cls.sp = proto60_spec()

    def run_days(self, spec, days=16, host=None):
        return ProtoRun(spec=spec, days=days, host=host).run()

    def test_day_of_the_simulation(self):
        r = self.run_days(extra_class_package(self.sp, '特课', days=(3,)), 5)
        self.assertGreaterEqual(label_counts(r, 3)['特课'], 40)      # 第 3 日卯时：具体日子压过默认的早课
        self.assertLess(label_counts(r, 3)['早课'], 5)
        self.assertEqual(label_counts(r, 4)['特课'], 0)              # 其余日子照旧
        self.assertGreaterEqual(label_counts(r, 4)['早课'], 40)

    def test_day_of_month_and_festival(self):
        self.assertEqual((cal(14)['dom'], cal(14)['festival']), (15, '上元'))
        r = self.run_days(extra_class_package(self.sp, '月半', doms=(15,)))
        self.assertGreaterEqual(label_counts(r, 14)['月半'], 40)     # 月内第 15 日（模拟第 14 日）
        self.assertEqual(label_counts(r, 15)['月半'], 0)
        r = self.run_days(extra_class_package(self.sp, '节日', festivals=True))
        self.assertGreaterEqual(label_counts(r, 14)['节日'], 40)     # 任一节日（上元）
        self.assertEqual(sum(label_counts(r, d)['节日'] for d in range(1, 17) if d != 14), 0)
        r = self.run_days(extra_class_package(self.sp, '上元', festivals=('上元',)))
        self.assertGreaterEqual(label_counts(r, 14)['上元'], 40)
        r = self.run_days(extra_class_package(self.sp, '佛诞', festivals=('佛诞',)))
        self.assertEqual(sum(label_counts(r, d)['佛诞'] for d in range(1, 17)), 0)

    def test_weather_comes_from_the_host_and_never_matches_without_one(self):
        spec = extra_class_package(self.sp, '雨课', weathers=('雨',))
        r = self.run_days(spec, 8, WeatherHost(20261110, rainy=(4, 5)))
        self.assertEqual([label_counts(r, d)['雨课'] >= 40 for d in range(1, 9)],
                         [False, False, False, True, True, False, False, False])
        r = self.run_days(spec, 6)                                  # StandaloneHost 没有 weather：永不成立
        self.assertEqual(sum(label_counts(r, d)['雨课'] for d in range(1, 7)), 0)

    def test_season_comes_from_the_schedule(self):
        r = self.run_days(extra_class_package(self.sp, '春课', seasons=('春',)), 4)
        self.assertTrue(all(label_counts(r, d)['春课'] >= 40 for d in range(1, 5)))      # 第 1 年正月：春
        r = self.run_days(extra_class_package(self.sp, '冬课', seasons=('冬',)), 4)
        self.assertEqual(sum(label_counts(r, d)['冬课'] for d in range(1, 5)), 0)

    def test_specific_beats_general_whatever_the_listing_order(self):
        """先具体日子，再天气，再季节，最后默认——匹配次序是引擎的规矩，不看包在栈里的先后：这里故意把最不具体的排在最前。"""
        sp = extra_class_package(self.sp, '季课', seasons=('春',))
        sp = dataclasses.replace(sp, stack=sp.stack[:pkg_index(sp, '季课') + 1] + (
            extra_class_package(proto60_spec(), '雨课', weathers=('雨',)).stack[pkg_index(sp, '季课')],) + sp.stack[pkg_index(sp, '季课') + 1:])
        day_pkg = extra_class_package(proto60_spec(), '日课', days=(4,)).stack[pkg_index(sp, '季课')]
        sp = dataclasses.replace(sp, stack=sp.stack[:pkg_index(sp, '季课') + 2] + (day_pkg,) + sp.stack[pkg_index(sp, '季课') + 2:])
        self.assertEqual([pk.id.rpartition(':')[2] for pk in sp.stack if pk.id.startswith('package:test:')], ['季课', '雨课', '日课'])
        r = self.run_days(sp, 7, WeatherHost(20261110, rainy=(4, 5)))
        winner = lambda d: max(label_counts(r, d).items(), key=lambda kv: kv[1])[0]
        self.assertEqual([winner(d) for d in (4, 5, 6)], ['日课', '雨课', '季课'])     # 第 4 日：日子 > 天气 > 季节；第 5 日：天气 > 季节；第 6 日：季节 > 默认
        self.assertEqual(label_counts(r, 3)['季课'] >= 40, True)
        self.assertEqual(self.sp.stack[pkg_index(self.sp, 'morning_chant')].when.specificity, 3)      # 默认包的具体程度最低

    def test_same_specificity_keeps_the_listing_order(self):
        sp = extra_class_package(extra_class_package(self.sp, '甲', days=(3,)), '乙', days=(3,))
        r = self.run_days(sp, 4)
        self.assertGreaterEqual(label_counts(r, 3)['乙'] + label_counts(r, 3)['甲'], 40)
        self.assertEqual(label_counts(r, 3)['乙'], 0)               # 同级：先列的甲赢
        self.assertEqual(self.sp.stack[pkg_index(self.sp, 'uposatha')].when.specificity, 0)

    def test_the_uposatha_package_is_a_day_specific_default_override(self):
        """布萨（第 1、15 日未时）是 when.day 的具体日子包：不在布萨日，同一时辰没有它。"""
        r = ProtoRun(days=16).run()
        eng = r.engine
        chant = lambda day: sum(1 for p in eng.people if eng.where(p.ix, day, 7)[3] == '布萨诵戒')
        self.assertGreaterEqual(chant(15), 40)
        self.assertGreaterEqual(chant(1), 40)
        self.assertEqual(chant(8), 0)


class ScopeCalendar(unittest.TestCase):
    """历法是这处场所（scope）的数据，不是全局默认：行为包 when 里的 festival / month / day_of_month / season 键按 rule:schedule 的
    calendar 引用的那份历法算。第二位独立验证者指出：此前引擎读全局默认的少林历，给丐帮分舵或庄园写新 defs 时节日键仍按少林历。"""

    OTHER = ('["calendar:proto60:main"]\nname = "另一座寺的历"\nyear = 360\nfestivals = { "1-10" = "开山节", "3-3" = "踏青" }\n'
             'retreat = [[4, 15], [7, 15]]\nwheat_doy = 100\nmillet_doy = 200')

    @classmethod
    def setUpClass(cls):
        cls.sp = proto60_spec()

    @staticmethod
    def point_at_another_calendar(pd, text=None):
        pd.append('calendar/proto60.toml', text or ScopeCalendar.OTHER)
        pd.edit('post/proto60.toml', 'calendar = "calendar:shaolin:main"', 'calendar = "calendar:proto60:main"')

    def test_the_spec_carries_the_calendar_named_in_the_schedule_rule(self):
        defs = load_defs()
        self.assertEqual(defs.get('rule:proto60:schedule')['calendar'], 'calendar:shaolin:main')
        self.assertEqual(self.sp.calendar.festivals, {(1, 1): '元日', (1, 15): '上元', (2, 15): '涅槃日', (4, 8): '佛诞',
                                                       (4, 15): '结夏', (7, 15): '盂兰盆', (12, 8): '腊八'})
        eng = ProtoRun(days=1).engine
        self.assertEqual(eng.cal(14), cal(14))                      # 原型场景就是少林寺：引用的是少林历，与全局默认同值
        self.assertEqual((eng.cal(14)['dom'], eng.cal(14)['festival']), (15, '上元'))

    def test_another_calendar_moves_the_festival_keys(self):
        with patched_defs() as pd:
            self.point_at_another_calendar(pd)
            sp = SiteSpec.from_defs(pd.load(strict=True), PROTO60_ID)
        self.assertEqual(sp.calendar.festivals, {(1, 10): '开山节', (3, 3): '踏青'})
        self.assertNotEqual(sp, self.sp)
        r = ProtoRun(spec=extra_class_package(sp, '开山', festivals=('开山节',)), days=16).run()
        self.assertGreaterEqual(label_counts(r, 9)['开山'], 40)       # 月内第 10 日（模拟第 9 日）：这座寺的节日
        self.assertEqual(sum(label_counts(r, d)['开山'] for d in range(1, 17) if d != 9), 0)
        r = ProtoRun(spec=extra_class_package(sp, '节日', festivals=True), days=16).run()
        self.assertGreaterEqual(label_counts(r, 9)['节日'], 40)
        self.assertEqual(label_counts(r, 14)['节日'], 0)             # 少林历的上元（第 14 日）在这座寺里不是节日
        self.assertEqual(label_counts(r, 14)['早课'] >= 40, True)
        r = ProtoRun(spec=extra_class_package(sp, '月半', doms=(15,)), days=16).run()
        self.assertGreaterEqual(label_counts(r, 14)['月半'], 40)      # 月内日不依赖节日表，两座寺相同

    def test_the_global_default_calendar_is_not_read_by_the_engine(self):
        """换掉全局默认历法（tianl.core.set_default_calendar），引擎的结果一字不差：它读的是规格里的历法。"""
        from tianl.core import set_default_calendar
        from tianl.core.calendar import Calendar
        base = ProtoRun(spec=extra_class_package(self.sp, '上元', festivals=('上元',)), days=16).run()
        set_default_calendar(Calendar({(9, 9): '重阳'}, ((4, 15), (7, 15)), 125, 245))
        try:
            self.assertEqual(cal(14)['festival'], None)                          # 全局默认确实换了
            r = ProtoRun(spec=extra_class_package(self.sp, '上元', festivals=('上元',)), days=16).run()
            self.assertEqual(r.hash, base.hash)
            self.assertGreaterEqual(label_counts(r, 14)['上元'], 40)             # 引擎仍按自己的历法：第 14 日是上元
            self.assertEqual(r.engine.cal(14)['festival'], '上元')
            self.assertEqual(ProtoRun(script=gossip_script(ProtoRun().common)).run().hash, BASE_HASH)
        finally:
            set_default_calendar(None)                                          # 回到“第一次用到时从 defs 读”
        self.assertEqual(cal(14)['festival'], '上元')

    def test_no_npc_module_reads_the_global_default_calendar(self):
        """源码规矩：tianl/npc 里没有模块从 tianl.core 引入全局的 cal / cal_str / default_calendar（历法只经 SiteSpec.calendar 进来）。"""
        banned = {'cal', 'cal_str', 'default_calendar', 'set_default_calendar'}
        for f in sorted(NPC_SRC.glob('*.py')):
            for n in ast.walk(ast.parse(f.read_text(encoding='utf-8'))):
                if isinstance(n, ast.ImportFrom) and (n.module or '').split('.')[-1] in ('core', 'calendar'):
                    self.assertEqual(banned & {a.name for a in n.names}, set(), '%s:%d 引入了全局历法' % (f.name, n.lineno))

    def test_a_festival_the_calendar_does_not_have_is_an_error(self):
        sp = extra_class_package(self.sp, '佛诞X', festivals=('佛诞X',))
        problems = sp.validate()
        self.assertTrue(any('佛诞X' in m and '不在这处场所的历法里' in m and '上元' in m for m in problems), problems)
        with patched_defs() as pd:
            self.point_at_another_calendar(pd)
            pd.edit('post/proto60_packages.toml', '"package:proto60:free",\n]', '"package:proto60:fest", "package:proto60:free",\n]')
            pd.append('post/proto60_packages.toml', '["package:proto60:fest"]\nlayer = "集体"\nwhen = { festival = "上元", slot = 3 }\n'
                      'do = { place = "place:proto60:zen", act = "zazen", label = "上元法会" }')
            text = '\n'.join(problems_of(pd))
        self.assertIn('package:proto60:fest', text)                              # 少林历的上元，换了历法之后就是笔误
        self.assertIn("节日 '上元' 不在这处场所的历法里", text)
        self.assertIn('开山节', text)

    def test_month_and_day_of_month_are_range_checked(self):
        sp = extra_class_package(extra_class_package(self.sp, '十三月', months=(13,)), '三十一日', doms=(31,))
        text = '\n'.join(sp.validate())
        self.assertIn('when.month 里的 13 不是月（1–12）', text)
        self.assertIn('when.day_of_month 里的 31 不是月内日（1–30）', text)
        bad = dataclasses.replace(self.sp, seasons={**self.sp.seasons, '春': (0, 1, 2)})
        self.assertTrue(any('seasons[春]：月份 0 不是 1–12' in m for m in bad.validate()))

    def test_calendar_field_errors_are_readable(self):
        with patched_defs() as pd:
            pd.edit('post/proto60.toml', 'calendar = "calendar:shaolin:main"\n', '')
            self.assertIn('缺少字段 calendar', '\n'.join(problems_of(pd)))
        with patched_defs() as pd:
            pd.edit('post/proto60.toml', 'calendar = "calendar:shaolin:main"', 'calendar = "calendar:nowhere:main"')
            with self.assertRaises(DefsError) as cm:
                pd.load(strict=True)
            self.assertIn('rule:proto60:schedule', '\n'.join(cm.exception.problems))
            self.assertIn('calendar:nowhere:main', '\n'.join(cm.exception.problems))
            self.assertIn('不存在的 calendar:nowhere:main', '\n'.join(problems_of(pd)))
        with patched_defs() as pd:
            self.point_at_another_calendar(pd, ScopeCalendar.OTHER.replace('festivals = { "1-10" = "开山节", "3-3" = "踏青" }\n', ''))
            text = '\n'.join(problems_of(pd))
            self.assertIn('calendar:proto60:main', text)
            self.assertIn('festivals', text)                                     # 历法定义缺 festivals：说明哪份历法缺什么
        with patched_defs() as pd:
            self.point_at_another_calendar(pd, ScopeCalendar.OTHER.replace('year = 360', 'year = 361'))
            self.assertIn('一年必须是 360 日', '\n'.join(problems_of(pd)))
        with patched_defs() as pd:
            pd.edit('post/proto60.toml', 'calendar = "calendar:shaolin:main"', 'calendar = "place:proto60:hall"')
            self.assertIn('应引用 calendar 类定义', '\n'.join(problems_of(pd)))


# ================================================================= 3 处理器登记表与参数校验
class HandlerRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sp = proto60_spec()

    def test_every_handler_is_documented_and_every_param_has_a_known_type(self):
        types = {'int', 'float', 'str', 'bool', 'slots', 'strs', 'place', 'post', 'posts', 'act'}
        self.assertGreaterEqual(len(PACKAGE_HANDLERS), 13)
        for name, hd in PACKAGE_HANDLERS.items():
            self.assertTrue(hd.doc, name)
            self.assertTrue(hd.fn and callable(hd.fn))
            self.assertTrue(all(p.type in types for p in hd.params), name)
            self.assertEqual(len({p.name for p in hd.params}), len(hd.params), name)
        for name, fn in GATES.items():
            self.assertTrue(fn.__doc__ and all(p.type in types for p in GATE_PARAMS[name]), name)
        self.assertEqual(set(GATES), {'lib_open', 'bath_day'})

    def test_the_prototype_uses_the_handlers_the_task_names(self):
        used = {pk.handler for pk in self.sp.stack if pk.handler}
        for name in ('tempted', 'lazy', 'kitchen_duty', 'proxy_cook', 'patrol_duty', 'gate_duty', 'errand', 'slack',
                     'court_report', 'physiology', 'forced', 'penalty', 'free'):
            self.assertIn(name, used)
        self.assertEqual(used, set(PACKAGE_HANDLERS))                # 每个登记的处理器在原型里都用到了（没有死的登记）

    def test_check_params_reports_every_kind_of_mistake(self):
        ctx = ParamCtx(self.sp)
        schema = PACKAGE_HANDLERS['tempted'].params
        good = dict(package(self.sp, 'tempted_night').params)
        self.assertEqual(check_params(schema, good, ctx), [])
        bad = {**good, 'k': 'high', 'p_cap': 1.9, 'bogus': 1, 'act': 'fly'}
        del bad['th_base']
        msgs = '；'.join(check_params(schema, bad, ctx))
        for frag in ('参数 k 应是 float', '参数 p_cap = 1.9 大于上限', '未知参数 bogus', '缺少参数 th_base', "活动 'fly' 没有对应的交互"):
            self.assertIn(frag, msgs)
        forced = PACKAGE_HANDLERS['forced'].params
        fp = dict(package(self.sp, 'forced_ill').params)
        self.assertEqual(check_params(forced, {**fp, 'state': 'dead'}, ctx)[0][:24], "参数 state 只能是 'ill'/'conf'，得到 'dead'"[:24])
        self.assertTrue(check_params(forced, {**fp, 'place': 'nowhere'}, ctx))
        self.assertTrue(check_params(forced, {**fp, 'extra_sleep_slots': (12,)}, ctx))     # 时辰只有 0–11

    def test_validate_catches_unregistered_handlers_wrong_layers_and_bad_params(self):
        sp = self.sp
        bad = with_package(sp, 'lazy', handler='no_such')
        self.assertTrue(any("'no_such' 未登记" in m and 'package:proto60:lazy' in m for m in bad.validate()))
        bad = with_package(sp, 'lazy', layer='自由')
        self.assertTrue(any('只能带层 越轨' in m for m in bad.validate()), bad.validate())
        pk = package(sp, 'lazy')
        bad = with_package(sp, 'lazy', params={**pk.params, 'd_div': 'x'})
        self.assertTrue(any('参数 d_div 应是 float' in m for m in bad.validate()))
        with self.assertRaises(SpecError):
            NpcEngine(bad, StandaloneHost(1, rnd_b2))               # 引擎拒绝开跑

    def test_defaults_come_from_the_handler_table_not_from_defs(self):
        """参数的默认值（Param(default=…)）是代码里仅有的数；defs 不写就用它。forced 的 extra_sleep_slots 缺省为空。"""
        p = next(x for x in PACKAGE_HANDLERS['forced'].params if x.name == 'extra_sleep_slots')
        self.assertEqual(p.default, ())
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'params = { extra_sleep_slots = [2] }', 'params = { }')
            sp = SiteSpec.from_defs(pd.load(), PROTO60_ID)
        self.assertEqual(package(sp, 'forced_ill').params['extra_sleep_slots'], ())

    def test_a_new_handler_plugs_in_without_touching_the_stack_code(self):
        """登记一个新处理器（日课：精进高的人在卯时抄经）并写一个包引用它——不改 stack.py / engine.py。"""
        @package_handler('test_copy_sutra', layers=(L_DEVIANT,),
                         params=(Param('label', 'str'), Param('d_min', 'float', default=0, lo=0, hi=100)))
        def copy_sutra(st, pkg, p, day, slot, ctx):
            if p.D >= pkg.params['d_min']:
                return ('lib', 'study', pkg.layer, pkg.params['label'])
            return None
        try:
            pk = PackageSpec('package:test:sutra', L_DEVIANT, WhoSpec(None, None, None), W(slots=(3,)), None,
                             'test_copy_sutra', {'label': '抄经', 'd_min': 70})
            sp = dataclasses.replace(self.sp, stack=(pk,) + self.sp.stack[:-1] + self.sp.stack[-1:])
            sp = dataclasses.replace(sp, stack=self.sp.stack[:pkg_index(self.sp, 'penalty')] + (pk,) + self.sp.stack[pkg_index(self.sp, 'penalty'):])
            self.assertEqual(sp.validate(), [])
            r = ProtoRun(spec=sp, days=3).run()
            eng = r.engine
            copying = [p for p in eng.people if eng.where(p.ix, 2, 3)[3] == '抄经']
            self.assertTrue(copying and all(p.D >= 70 for p in copying))
            self.assertTrue(all(p.ill < 2 or eng.where(p.ix, 2, 3)[3] != '抄经' for p in eng.people))
        finally:
            del PACKAGE_HANDLERS['test_copy_sutra']

    def test_duty_packages_must_be_adjacent_and_a_free_package_must_close_the_stack(self):
        sp = self.sp
        i, j = pkg_index(sp, 'duty_kitchen'), pkg_index(sp, 'physiology')
        stack = list(sp.stack)
        stack[i + 1], stack[j] = stack[j], stack[i + 1]             # 把生理包塞进值守段中间
        self.assertTrue(any('相邻' in m for m in dataclasses.replace(sp, stack=tuple(stack)).validate()))
        no_free = dataclasses.replace(sp, stack=tuple(pk for pk in sp.stack if pk.handler != 'free'))
        self.assertTrue(any('free' in m for m in no_free.validate()))

    def test_the_patrol_package_must_name_the_patrol_office(self):
        bad = with_package(self.sp, 'duty_patrol', who=WhoSpec(('方丈',), None, None))
        self.assertTrue(any('必须正是' in m for m in bad.validate()), bad.validate())

    def test_stack_order_is_data(self):
        """栈的次序来自 defs：把夜里的就寝排在起念偷食之前，夜里就没人偷食了。"""
        sp = self.sp
        i, j = pkg_index(sp, 'tempted_night'), pkg_index(sp, 'night_sleep')
        stack = list(sp.stack)
        stack[i], stack[j] = stack[j], stack[i]
        swapped = dataclasses.replace(sp, stack=tuple(stack))
        self.assertEqual(swapped.validate(), [])
        base, other = ProtoRun().run(), ProtoRun(spec=swapped).run()
        night_thefts = lambda r: sum(1 for p in r.engine.people for d in range(1, 31) if r.engine.where(p.ix, d, 1)[3] == '夜里偷食')
        self.assertGreater(night_thefts(base), 0)
        self.assertEqual(night_thefts(other), 0)
        self.assertNotEqual(base.hash, other.hash)


# ================================================================= 4 报错清楚
@contextlib.contextmanager
def patched_defs():
    """defs 的一份临时拷贝，可对其中的文本做替换；load() 载入（默认不严格，好让 from_defs 自己报问题）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'defs'
        shutil.copytree(DEFS_ROOT, root)

        class Patched:
            def edit(self, rel, old, new, count=1):
                f = root / rel
                text = f.read_text(encoding='utf-8')
                assert text.count(old) >= 1, (rel, old)
                f.write_text(text.replace(old, new, count) if count else text.replace(old, new), encoding='utf-8')

            def edit_re(self, rel, pattern, repl, flags=0):
                f = root / rel
                text = f.read_text(encoding='utf-8')
                new, n = re.subn(pattern, repl, text, flags=flags)
                assert n >= 1, (rel, pattern)
                f.write_text(new, encoding='utf-8')

            def rename_scope(self, old, new):
                """把名叫 old 的 scope 整个换成 new：文件名与每条编号里的 scope 段（只改 proto60*.toml 这批文件）。"""
                for f in sorted(root.rglob('%s*.toml' % old)):
                    text = f.read_text(encoding='utf-8').replace(':%s:' % old, ':%s:' % new)
                    f.with_name(f.name.replace(old, new)).write_text(text, encoding='utf-8')
                    f.unlink()

            def append(self, rel, text):
                with (root / rel).open('a', encoding='utf-8') as fh:
                    fh.write('\n' + text + '\n')

            def load(self, strict=False):
                return Defs.load(root, strict=strict)
        yield Patched()


def problems_of(pd):
    """对改过的 defs 构造规格：返回 SpecError 的问题列表（没抛就是测试失败）。"""
    with unittest.TestCase().assertRaises(SpecError) as cm:
        SiteSpec.from_defs(pd.load(), PROTO60_ID)
    return cm.exception.problems


class ErrorReporting(unittest.TestCase):
    """缺字段、引用不存在的定义、未登记的处理器、参数不合法……每条都写明哪条定义的哪个字段。"""

    def has(self, problems, *frags):
        text = '\n'.join(problems)
        for f in frags:
            self.assertIn(f, text)

    def test_missing_required_field(self):
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'layer = "处分"\nhandler = "penalty"', 'handler = "penalty"')
            self.has(problems_of(pd), 'package:proto60:penalty', '缺少字段 layer')
        with patched_defs() as pd:
            pd.edit('post/proto60.toml', 'count = 4\nprefix = "慧"\nkitchen = true', 'prefix = "慧"\nkitchen = true')
            self.has(problems_of(pd), 'post:proto60:head_cook', '缺少字段 count', '编制')

    def test_reference_to_a_package_that_does_not_exist(self):
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', '"package:proto60:free",\n]', '"package:proto60:free", "package:proto60:nope",\n]')
            with self.assertRaises(DefsError) as cm:                # 严格加载就在 Defs.load 里拦住
                pd.load(strict=True)
            self.has(cm.exception.problems, 'rule:proto60:stack', 'package:proto60:nope', '不存在')
            self.has(problems_of(pd), 'rule:proto60:stack', 'packages[36]', 'package:proto60:nope')    # 非严格：构造规格时同样报

    def test_package_not_listed_in_the_stack(self):
        with patched_defs() as pd:
            pd.append('post/proto60_packages.toml', '["package:proto60:orphan"]\nlayer = "集体"\nwhen = { slot = 5 }\n'
                      'do = { place = "place:proto60:hall", act = "chant", label = "孤儿" }')
            self.has(problems_of(pd), 'package:proto60:orphan', '没有列进', 'rule:proto60:stack')

    def test_definition_nobody_uses(self):
        with patched_defs() as pd:
            pd.append('knowledge/proto60.toml', '["thought:proto60:unused"]\nlabel = "闲置"\nvalue = 1\ndays = 1\ncap = 1')
            self.has(problems_of(pd), 'thought:proto60:unused', '没有被任何地方引用或使用')

    def test_unregistered_handler_and_bad_params(self):
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'handler = "tempted"', 'handler = "tempt_ed"')
            self.has(problems_of(pd), 'package:proto60:tempted_night', "处理器 'tempt_ed' 未登记", '已登记：')
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'th_base = 35, ', '')
            self.has(problems_of(pd), '处理器 tempted', '缺少参数 th_base', '起念的饥门槛底数')
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'k = 1.6', 'k = "high"')
            self.has(problems_of(pd), 'package:proto60:tempted_night', '参数 k 应是 float', "'high'")
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'p_cap = 0.9', 'p_cap = 1.9')
            self.has(problems_of(pd), '参数 p_cap = 1.9 大于上限')
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'act = "steal" }\n\n# ---------------------------------------------------------------- 越轨',
                    'act = "steal", bogus = 1 }\n\n# ---------------------------------------------------------------- 越轨')
            self.has(problems_of(pd), 'package:proto60:physiology', '未知参数 bogus', '可用：')

    def test_unknown_field_is_a_typo(self):
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', '["package:proto60:penalty"]\nlayer = "处分"', '["package:proto60:penalty"]\nlyaer = "处分"\nlayer = "处分"')
            self.has(problems_of(pd), 'package:proto60:penalty', '未知字段 lyaer', '拼错')

    def test_wrong_type_and_unknown_vocabulary(self):
        with patched_defs() as pd:
            pd.edit('post/proto60.toml', 'count = 4', 'count = "four"')
            self.has(problems_of(pd), 'post:proto60:head_cook', '字段 count 应是 整数', "'four'")
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'do = { place = "place:proto60:hall", act = "chant", label = "早课" }',
                    'do = { place = "place:proto60:hall", act = "fly", label = "早课" }')
            self.has(problems_of(pd), 'package:proto60:morning_chant', "活动 'fly' 没有对应的交互")
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'layer = "集体"\nwhen = { slot = 3 }', 'layer = "空中"\nwhen = { slot = 3 }')
            self.has(problems_of(pd), 'package:proto60:morning_chant', "层标签 '空中' 未登记")
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'when = { slot = 9 }', 'when = { slot = 13 }')
            self.has(problems_of(pd), 'package:proto60:evening_chant', '不是时辰')

    def test_dangling_reference_in_facility_and_interaction(self):
        with patched_defs() as pd:
            pd.edit('facility/proto60.toml', 'station = "facility:proto60:zen"', 'station = "facility:proto60:zenn"', 1)
            with self.assertRaises(DefsError) as cm:
                pd.load(strict=True)
            self.has(cm.exception.problems, 'interaction:proto60:zazen', 'facility:proto60:zenn')
            self.has(problems_of(pd), 'interaction:proto60:zazen', 'facility:proto60:zenn')

    def test_admission_gate_problems(self):
        with patched_defs() as pd:
            pd.edit('facility/proto60.toml', 'every = 5, ', '')
            self.has(problems_of(pd), 'interaction:proto60:bath', '准入门 bath_day', '缺少参数 every')
        with patched_defs() as pd:
            pd.edit('facility/proto60.toml', 'gate = "bath_day"', 'gate = "bath_night"')
            self.has(problems_of(pd), 'interaction:proto60:bath', "准入门 'bath_night' 未登记", 'bath_day')
        with patched_defs() as pd:
            pd.edit('facility/proto60.toml', 'admission = { gate = "bath_day", every = 5, phase = 4, slots = [7, 8] }\n', '')
            pd.edit('facility/proto60.toml', 'order = 7\nad = { label = "沐浴"', 'order = 7\nadmission = { gate = "lib_open", office = "post:proto60:librarian", slots = [1] }\nad = { label = "沐浴"')
            sp = SiteSpec.from_defs(pd.load(), PROTO60_ID)          # 合法：准入门可以换成另一道，只要参数对得上——不抛错，且确实换了
            bath = next(ad for ad in sp.ads if ad.act == 'bath')
            self.assertEqual((bath.gate, bath.gate_params['slots']), ('lib_open', (1,)))
        with patched_defs() as pd:                                  # 参数的类型、取值范围在读 defs 时就查（不等规格自检）
            pd.edit('facility/proto60.toml', 'every = 5, ', 'every = "often", ')
            self.has(problems_of(pd), 'ad bath 的准入门 bath_day', '参数 every 应是 int', "'often'")
        with patched_defs() as pd:
            pd.edit('facility/proto60.toml', 'every = 5, ', 'every = 0, ')
            self.has(problems_of(pd), 'ad bath 的准入门 bath_day', '参数 every = 0 小于下限')

    def test_all_problems_are_collected_not_just_the_first(self):
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'layer = "处分"\nhandler = "penalty"', 'handler = "penalty"')
            pd.edit('post/proto60_packages.toml', 'th_base = 35, ', '')
            pd.edit('post/proto60.toml', 'count = 4', 'count = "four"')
            probs = problems_of(pd)
        self.has(probs, 'package:proto60:penalty', 'th_base', 'post:proto60:head_cook')
        self.assertGreaterEqual(len(probs), 3)

    def test_structural_and_value_mistakes_are_reported_together(self):
        """“一次报全”不分结构错与取值错：缺字段、处理器写错、参数缺失、类型不对、越界、时辰不对、活动不存在、准入门参数不合法，
        同时出现时一次全报（它们都在读 defs 时查；之前类型与越界错要等结构错修完才出现）。"""
        with patched_defs() as pd:
            pd.edit('post/proto60_packages.toml', 'k = 1.6', 'k = "high"', 0)                              # 类型错（两个起念包都错）
            pd.edit('post/proto60_packages.toml', 'p_cap = 0.9', 'p_cap = 1.9')                           # 越界
            pd.edit('post/proto60_packages.toml', 'handler = "kitchen_duty"', 'handler = "kitchen_dutyy"')  # 处理器写错
            pd.edit('post/proto60_packages.toml', 'faint_e = 10, ', '')                                    # 缺参数
            pd.edit('post/proto60_packages.toml', 'when = { slot = 9 }', 'when = { slot = 13 }')            # 时辰不对
            pd.edit('post/proto60_packages.toml', 'act = "chant", label = "早课"', 'act = "fly", label = "早课"')   # 活动不存在
            pd.edit('post/proto60_packages.toml', 'layer = "处分"\nhandler = "penalty"', 'handler = "penalty"')   # 缺字段
            pd.edit('post/proto60.toml', 'count = 4', 'count = "four"')                                    # 岗位的字段类型
            pd.edit('facility/proto60.toml', 'every = 5, ', 'every = 0, ')                                 # 准入门参数越界
            probs = problems_of(pd)
        self.has(probs, '缺少字段 layer', "处理器 'kitchen_dutyy' 未登记", '缺少参数 faint_e', '参数 k 应是 float', '参数 p_cap = 1.9 大于上限',
                 '不是时辰（0–11）', "活动 'fly' 没有对应的交互", '字段 count 应是 整数', '参数 every = 0 小于下限')
        self.assertEqual(len(probs), len(set(probs)))                  # 没有重复报同一条
        self.assertGreaterEqual(len(probs), 10)

    def test_unknown_scenario_and_missing_role(self):
        defs = load_defs()
        with self.assertRaises(SpecError) as cm:
            SiteSpec.from_defs(defs, 'scenario:proto60:nope')
        self.assertIn('scenario:proto60:nope', str(cm.exception))
        with self.assertRaises(SpecError) as cm:
            SiteSpec.from_defs(defs, 'place:proto60:hall')
        self.assertIn('scenario:<scope>:<名>', str(cm.exception))
        with self.assertRaises(SpecError) as cm:                    # 没有这个 scope 的定义
            SiteSpec.from_defs(defs, 'scenario:nowhere:main') if 'scenario:nowhere:main' in defs else \
                SiteSpec.from_defs(defs, 'scenario:nowhere:x')
        self.assertTrue(cm.exception.problems)
        with patched_defs() as pd:
            pd.edit('org/proto60.toml', '["org:proto60:gate"]', '["org:proto60:gatehouse"]')
            self.has(problems_of(pd), "缺少 org 的角色 'gate'", 'proto60')

    def test_validate_messages_are_readable_too(self):
        """SiteSpec.validate() 的问题同样写明是哪一项：改坏规格（不经 defs）也读得懂。"""
        sp = proto60_spec()
        bad = with_package(sp, 'night_sleep', do=dataclasses.replace(package(sp, 'night_sleep').do, act='fly', place='nowhere'))
        self.has(bad.validate(), 'package:proto60:night_sleep', "活动 'fly'", "场所 'nowhere'")


# ================================================================= 5 钩子
class Hooks(unittest.TestCase):
    """engine.py 里的四个钩子：默认空操作（哈希不变）；后续模块只改各自的文件，不改 engine.py。"""

    def test_defaults_are_no_ops_and_leave_the_baseline_hash(self):
        self.assertIsNone(life.pulse(None, 1))
        self.assertIsNone(persist.flush(None, 1))
        self.assertEqual(baseline_hash(), BASE_HASH)

    def test_signatures_are_the_documented_ones(self):
        sig = lambda f: list(inspect.signature(f).parameters)
        self.assertEqual(sig(life.pulse), ['engine', 'day'])
        self.assertEqual(sig(persist.flush), ['engine', 'day'])
        self.assertEqual(sig(lod.observe), ['engine', 'ctx', 'day', 'slot'])
        self.assertEqual(sig(controller.decide), ['engine', 'p', 'day', 'slot', 'ctx'])
        self.assertEqual(sig(controller.Controller.choose), ['self', 'ctx', 'candidates'])
        self.assertEqual(sig(controller.candidates), ['engine', 'p', 'day', 'slot', 'ctx'])
        self.assertEqual(sig(NpcEngine.set_controller), ['self', 'who', 'ctl'])

    def test_engine_calls_the_hooks_through_the_modules_so_replacing_them_needs_no_engine_change(self):
        src = (NPC_SRC / 'engine.py').read_text(encoding='utf-8')
        for call in ('life.pulse(self, day)', 'persist.flush(self, day)', 'lod.observe(self, ctx, day, slot)', 'controller.decide(self,'):
            self.assertIn(call, src)
        self.assertRegex(src, r'from \. import controller, life, lod, persist')

    def test_pulse_is_called_once_per_day_before_anything_else(self):
        seen = []
        with mock.patch.object(life, 'pulse', side_effect=lambda eng, day: seen.append((day, eng.stat['ill'], len(eng.evs)))):
            r = ProtoRun(days=5).run()
        self.assertEqual([d for d, _, _ in seen], [1, 2, 3, 4, 5])
        self.assertEqual(seen[0], (1, 0, 0))                          # 第一天开始时：还没有生病、没有事件——它是 begin_day 的第一步
        self.assertEqual(r.hash, ProtoRun(days=5).run().hash)         # 空操作的替身不改世界

    def test_flush_is_called_at_the_end_of_each_day_after_the_day_is_booked(self):
        seen = []
        with mock.patch.object(persist, 'flush', side_effect=lambda eng, day: seen.append((day, eng.daily[-1][0], eng.last))):
            ProtoRun(days=4).run()
        self.assertEqual(seen, [(d, d, (d, 11)) for d in (1, 2, 3, 4)])      # 流水账已记当日；最后跑完的是亥时

    def test_observe_is_called_every_slot_and_counts_only_when_someone_observes(self):
        calls = []
        real = lod.observe
        with mock.patch.object(lod, 'observe', side_effect=lambda eng, ctx, day, slot: (calls.append((day, slot)), real(eng, ctx, day, slot))):
            r = ProtoRun(days=2, observer='clo').run()
        self.assertEqual(calls, [(d, s) for d in (1, 2) for s in range(12)])
        self.assertGreater(r.engine.narr, 0)
        self.assertEqual(ProtoRun(days=2).run().engine.narr, 0)
        self.assertEqual(r.hash, ProtoRun(days=2).run().hash)         # 观察者不改哈希

    def test_default_controller_is_the_program_and_changes_nothing(self):
        run = ProtoRun(days=6)
        eng = run.engine
        self.assertEqual(eng.controllers, {})                         # 没有操纵者：run_slot 直接走栈，不经过 controller.decide
        base = ProtoRun(days=6).run().hash
        for p in eng.people:
            eng.set_controller(p.pid, controller.PROGRAM)             # 人人都配上“程序”这个操纵者
        run.run()
        self.assertEqual(run.hash, base)
        eng.set_controller(eng.people[0].pid, None)
        self.assertNotIn(0, eng.controllers)

    def test_controller_sees_candidates_and_falls_back_on_garbage(self):
        class Spy(controller.Controller):
            def __init__(self, answer):
                self.answer, self.seen = answer, []

            def choose(self, ctx, candidates):
                self.seen.append((ctx.day, ctx.slot, ctx.person.ix, list(candidates)))
                return self.answer(candidates)
        base = ProtoRun(days=3).run()
        for answer in (lambda c: ('nowhere', 'sleep', '自由', '胡来'), lambda c: (_ for _ in ()).throw(RuntimeError('LLM 超时'))):
            run = ProtoRun(days=3)
            spy = Spy(answer)
            run.engine.set_controller(5, spy)
            run.run()
            self.assertEqual(run.hash, base.hash)                     # 候选之外的答案、抛异常：都回落到程序的选择，世界照常
            self.assertEqual(len(spy.seen), 3 * 12)
            day, slot, ix, cands = spy.seen[0]
            self.assertEqual((day, slot, ix, len(cands)), (1, 0, 5, 1))
            self.assertEqual(cands[0], base.engine.where(5, day, slot))      # 第一个候选就是程序（栈）的选择（四元组：场所、活动、层、原因）

    def test_stack_decide_is_idempotent_per_person_and_slot(self):
        """decide 有副作用（占工位、记统计……），同一个人同一个时辰（同一个 ctx）只算一次；再问原样返回、不再占位——
        controller.candidates 之类多次取“程序的选择”的调用者不会重复占位（controller.py 的硬约束）。"""
        from tianl.npc.model import SlotCtx
        eng = ProtoRun(days=1).engine
        day, slot = 1, 7                                              # 申时：自由时段，会占工位
        eng.begin_day(day)
        ctx = SlotCtx(day, slot)
        p = eng.people[eng.common[0].ix]
        d1 = eng.stack.decide(p, day, slot, ctx)
        occ, stat = dict(ctx.occ), dict(eng.stat)
        d2 = eng.stack.decide(p, day, slot, ctx)
        self.assertIs(d1, d2)
        self.assertEqual((dict(ctx.occ), dict(eng.stat)), (occ, stat))     # 没有再占位、没有再记统计
        self.assertEqual(controller.candidates(eng, p, day, slot, ctx), [d1])
        self.assertEqual((dict(ctx.occ), dict(eng.stat)), (occ, stat))
        q = eng.people[eng.common[1].ix]                               # 换一个人照常算
        self.assertIsNotNone(eng.stack.decide(q, day, slot, ctx))
        self.assertEqual(eng.stack.decide(p, day, slot, ctx), d1)      # 中间插了别人，p 仍按他自己的 ctx 记忆走完（记忆只有一格：不同的人会重算）
        ctx2 = SlotCtx(day, slot)                                      # 新的 ctx（新的时辰对象）重新决定
        self.assertEqual(eng.stack.decide(p, day, slot, ctx2)[:2], d1[:2])

    def test_explain_after_leaving_uses_the_words_of_the_defs(self):
        sp = dataclasses.replace(proto60_spec(), leave_word='出帮')
        run = ProtoRun(spec=sp, days=1).run()
        run.engine.on_person_removed(run.engine.people[3].pid, '游方')
        ex = run.engine.explain(run.engine.people[3].pid, 2, 0)
        self.assertIn('已于第1日出帮（游方）', ex['text'])
        self.assertNotIn('离寺', ex['text'])

    def test_a_controller_can_choose_among_candidates(self):
        """候选不止一个时（C9 会列出合法替代）操纵者选哪个就是哪个：这里临时把候选扩成两个，验证选择生效。"""
        run = ProtoRun(days=2)
        eng = run.engine
        real = controller.candidates
        alt = ('clo', 'stroll', '自由', '操纵者改选')
        with mock.patch.object(controller, 'candidates', side_effect=lambda e, p, d, s, c: real(e, p, d, s, c) + [alt]):
            eng.set_controller(7, type('Pick', (controller.Controller,), {'choose': lambda self, ctx, cands: cands[-1]})())
            run.run()
        self.assertTrue(all(eng.where(7, d, s)[3] == '操纵者改选' for d in (1, 2) for s in range(12)))
        self.assertNotEqual(run.hash, ProtoRun(days=2).run().hash)


# ================================================================= 6 泛化：同一份 defs，人口 60 → 300
class Generalization(unittest.TestCase):
    def test_same_defs_300_monks_30_days(self):
        lines, run = scale_report(300, 30)
        eng, st = run.engine, run.engine.stat
        print('\n' + '\n'.join(lines))
        self.assertEqual(len(eng.people), 300)
        self.assertEqual(st['ps'], 300 * 12 * 30)
        self.assertEqual(eng.fac.violations, [])                        # 预约越界 0
        self.assertEqual(sum(len(p.trail) for p in eng.people), st['ps'])
        sp = eng.spec
        for p in eng.people:                                            # 每个决定都说得清：非空的层与原因，层在登记表里
            for day in (1, 8, 15, 30):
                for slot in range(12):
                    place, act, layer, reason = eng.where(p.ix, day, slot)
                    self.assertTrue(place in sp.places and act and reason and layer in sp.layer_rank)
        shares = {k[4:]: v / st['ps'] for k, v in st.items() if k.startswith('pkg_')}
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertGreater(shares['集体'], 0.4)                          # 日历上的集体活动仍占大头
        self.assertLess(shares['越轨'], 0.02)
        alloc = {g: sum(eng.acts[g].values()) for g in sp.groups}
        self.assertEqual(sum(alloc.values()), st['ps'])
        self.assertTrue(all(v > 0 for v in alloc.values()))
        self.assertEqual(baseline_hash(), BASE_HASH)                    # 泛化检查不改原型场景（规格不可变、共用的缓存没被动过）

    def test_the_same_defs_under_another_scope_reproduce_the_baseline(self):
        """引擎里没有 proto60 的任何东西：把整套 defs 的 scope 从 proto60 换成别的名字，同样的世界、同样的哈希。
        （docs/NPC_ENGINE.md 第 12 节“为另一处场所写一套 defs”的第一步就是复制并改 scope。）"""
        with patched_defs() as pd:
            pd.rename_scope('proto60', 'demo')
            defs = pd.load(strict=True)                              # 引用完整性照样 100%
            sp, scn = SiteSpec.from_defs(defs, 'scenario:demo:main'), ScenarioSpec.from_defs(defs, 'scenario:demo:main')
        self.assertEqual(sp.scope, 'demo')
        self.assertTrue(all(pk.id.startswith('package:demo:') for pk in sp.stack))
        run = ProtoRun(spec=sp, scenario=scn, script=gossip_script(ProtoRun(spec=sp, scenario=scn).common, scn)).run()
        self.assertEqual(run.hash, BASE_HASH)

    def test_editing_only_numbers_in_defs_makes_a_better_300_monk_temple(self):
        """“同一份 defs 只改人口”能跑，但差事板与工位还是 60 人的尺寸（满员改选两万多次）；再把差事数与工位数也放大 5 倍（只改 defs 里的数），
        满员改选降到几百次、差事完成数跟着涨——这就是第 12 节“把 proto60 改成 300 僧少林寺要改什么”的第一批改动，都不碰代码。"""
        with patched_defs() as pd:
            pd.edit('scenario/proto60.toml', 'population = 60', 'population = 300')
            pd.edit_re('post/proto60.toml', r'(\["job:proto60:[a-z_]+"\][^\[]*?)count = (\d+)', lambda m: '%scount = %d' % (m.group(1), 5 * int(m.group(2))), re.S)
            pd.edit_re('facility/proto60.toml', r'stations = (\d+)', lambda m: 'stations = %d' % (5 * int(m.group(1))))
            defs = pd.load(strict=True)
            sp, scn = SiteSpec.from_defs(defs, PROTO60_ID), ScenarioSpec.from_defs(defs, PROTO60_ID)
        days = 10                                                        # 十日就够看出差别（省时间）
        big = ProtoRun(spec=sp, scenario=scn, days=days).run().engine
        small = ProtoRun(n=300, days=days).run().engine                  # 只改人口
        self.assertEqual((len(big.people), big.stat['ps']), (300, 300 * 12 * days))
        self.assertEqual(big.fac.violations, [])
        posted = sum(j.count for j in sp.jobs.board) * days              # 每日板上的人手数 × 日数：全部完成
        self.assertEqual((big.stat['job_done'], big.stat['job_post']), (posted, posted))
        self.assertEqual(posted, 5 * sum(j.count for j in proto60_spec().jobs.board) * days)
        self.assertLess(big.stat['full'] * 10, small.stat['full'])       # 满员改选少了一个数量级以上
        work = lambda e: e.acts['清众']['作务'] / sum(e.acts['清众'].values())
        self.assertGreater(work(big), 3 * work(small))                   # 清众的作务时间占比明显回升

    def test_roster_scales_with_population_only(self):
        sp, scn = proto60_spec(), proto60_scenario()
        for n in (60, 300):
            r = proto60_roster(sp, n)
            self.assertEqual(len(r), n)
            self.assertEqual(sum(1 for ps in r if ps.office), sum(o.count for o in sp.offices))     # 岗位编制不随人口变
            self.assertEqual(len({ps.pid for ps in r}), n)
        self.assertEqual(len(proto60_roster(sp)), scn.population)

    def test_names_stay_unique_however_large_the_population(self):
        """字池只有 62 个字：超过一圈，名字后面多缀字（given_name），所以 300 人、数千人都不重名；第一圈与原型的取法逐字相同。"""
        sp = proto60_spec()
        pool = sp.name_pool
        for n in (60, 300, 1000, 4000):
            r = proto60_roster(sp, n)
            self.assertEqual(len({ps.name for ps in r}), n, n)
        r60, r300 = proto60_roster(sp, 60), proto60_roster(sp, 300)
        self.assertEqual([ps.name for ps in r60], [ps.name for ps in r300[:60]])         # 人口变了，前 60 位的名字不变
        for ps in r60:
            i = int(ps.pid[1:]) - 1
            self.assertEqual(ps.name, (next(o.prefix for o in sp.offices if o.name == ps.office) if ps.office else sp.common_prefix) + pool[i])
        self.assertEqual(given_name('甲', 'ab', 0), '甲a')
        self.assertEqual([given_name('甲', 'ab', i) for i in range(2, 8)], ['甲aa', '甲ba', '甲ab', '甲bb', '甲aaa', '甲baa'])

    def test_other_sizes_run(self):
        for n in (28, 90, 150):                                        # 28 = 只有岗位者；其余是不同大小的寺
            run = ProtoRun(n=n, days=6).run()
            self.assertEqual(run.engine.stat['ps'], n * 12 * 6)
            self.assertEqual(run.engine.fac.violations, [])

    def test_site_words_in_report_titles_and_explain_come_from_defs(self):
        """报表标题里的“60 僧 × 30 日”与 explain 里的“离寺”不写死在代码里：量词取场景的 track_suffix，说法取 org:main 的 leave_word。"""
        report_src = (NPC_SRC / 'report.py').read_text(encoding='utf-8')
        self.assertIsNone(re.search(r'\d+ ?僧', report_src))
        self.assertNotIn('离寺', (NPC_SRC / 'engine.py').read_text(encoding='utf-8'))
        sp, scn = proto60_spec(), proto60_scenario()
        self.assertEqual((sp.leave_word, scn.track_suffix), ('离寺', '僧'))
        with patched_defs() as pd:                                  # 换一座“帮”：只改 defs，说法与量词跟着变
            pd.edit('org/proto60.toml', 'leave_word = "离寺"', 'leave_word = "出帮"')
            pd.edit('scenario/proto60.toml', 'track_suffix = "僧"', 'track_suffix = "众"')
            defs = pd.load(strict=True)
            sp2, scn2 = SiteSpec.from_defs(defs, PROTO60_ID), ScenarioSpec.from_defs(defs, PROTO60_ID)
        self.assertEqual((sp2.leave_word, scn2.track_suffix), ('出帮', '众'))

    def test_the_scale_report_cli(self):
        import subprocess
        import sys
        r = subprocess.run([sys.executable, '-m', 'tianl.npc.report', '--scale', '100', '--days', '5'], capture_output=True,
                           text=True, check=False, cwd=str(NPC_SRC.parent.parent))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('人口 100 × 5 日', r.stdout)
        self.assertIn('行为包占比', r.stdout)


# ================================================================= 7 文档不漏字段
class DocsInSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = DOC.read_text(encoding='utf-8')
        cls.section = cls.doc[cls.doc.index('## 12 '):]

    def test_every_def_field_is_documented(self):
        rows = field_docs(load_defs(), PROTO60_ID)
        self.assertGreater(len(rows), 200)
        missing = sorted({'%s: %s' % (kind, path) for kind, path, *_ in rows if '`%s`' % path not in self.section})
        self.assertEqual(missing, [], '文档第 12 节漏了这些字段（python3 -m tianl.npc.defsload 可重新生成字段表）')

    @staticmethod
    def tables_of(text):
        """文本里“**标题**”后紧跟的表：{标题: [表行（含表头）]}。"""
        out, title, started = {}, None, False
        for line in text.splitlines():
            if re.match(r'^\*\*.+\*\*$', line):
                title, started = line, False
            elif line.startswith('|') and title:
                out.setdefault(title, []).append(line)
                started = True
            elif line.strip() and started:
                title, started = None, False
        return out

    def test_field_tables_are_exactly_the_generated_ones(self):
        """字段表逐表逐行与代码生成的一致：说明文字改了、默认值改了、类型改了而文档没跟着改，都会红；
        文档里多出来的（代码里已经没有的）字段表也会红。重新生成：python3 -m tianl.npc.defsload。"""
        gen = self.tables_of(docs_markdown(load_defs(), PROTO60_ID))
        doc = self.tables_of(self.section)
        self.assertGreaterEqual(len(gen), 40)
        field_title = re.compile(r'^\*\*(`[^`]+`|处理器 `[^`]+`|准入门 `[^`]+`)')
        self.assertEqual(sorted(t for t in doc if field_title.match(t) and t not in gen), [], '文档里有代码里已经没有的字段表')
        for title, rows in gen.items():
            self.assertIn(title, doc, '文档缺这张字段表：%s' % title)
            self.assertEqual(doc[title], rows, '字段表与代码不一致：%s' % title)

    def test_every_handler_gate_and_hook_is_documented(self):
        for name in list(PACKAGE_HANDLERS) + list(GATES):
            self.assertIn('`%s`' % name, self.section, name)
        for hook in ('life.pulse(engine, day)', 'controller.decide(engine, p, day, slot, ctx)', 'lod.observe(engine, ctx, day, slot)',
                     'persist.flush(engine, day)', 'Controller.choose(ctx, candidates)'):
            self.assertIn(hook, self.doc, hook)
        for role in ROLES:
            self.assertIn(role, self.section, role)


if __name__ == '__main__':
    unittest.main()
