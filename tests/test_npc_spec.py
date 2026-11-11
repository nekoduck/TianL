"""规格与原型的一致性：proto60_spec() 的每个常数都等于原型 npc_spike.py 里对应的常量；
并对多个种子与规模做“逐步差分”：轨迹、统计、事件序列与原型逐项相同。
原型文件只读，本测试只 import 它，不改它。
"""
import importlib.util
import sys
import unittest
from pathlib import Path

from tianl.npc import ProtoRun, proto60_spec
from tianl.npc import events as E
from tianl.npc.scenarios import PROTO60_CAST, PROTO_SEED

REF_PATH = Path(__file__).resolve().parent.parent / 'reference' / 'npc_spike.py'


def load_ref():
    """只读地加载原型模块；不写字节码，免得在 reference/ 下留下文件。"""
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location('npc_spike_ref', REF_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


class ConstantsMatchPrototype(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = load_ref()
        cls.sp = proto60_spec()

    def test_places_capacities_roam_night(self):
        r, sp = self.ref, self.sp
        self.assertEqual(sp.places, r.PLACE)
        self.assertEqual(sp.capacity, r.CAPF)
        self.assertEqual(sp.roam, tuple(r.ROAM))
        self.assertEqual(sp.night, r.NIGHT)
        self.assertEqual(set(sp.private_places), {'dorm1', 'dorm2', 'dorm3'})
        self.assertEqual(sp.cap_default, 999)

    def test_offices(self):
        r, sp = self.ref, self.sp
        self.assertEqual([(o.name, o.count) for o in sp.offices], r.OFFICES)
        self.assertEqual({o.name: o.place for o in sp.offices if o.place}, r.OFFICE_PLACE)
        self.assertEqual({o.name: o.slots for o in sp.offices if o.slots}, r.OFFICE_SLOTS)
        self.assertEqual(set(sp.kitchen_offices), set(r.KITCHEN))
        self.assertEqual(set(sp.disc_offices), r.DISC)
        self.assertEqual(sp.kitchen.slots, r.KIT_SLOTS)
        self.assertEqual({o.name for o in sp.offices if o.prefix == '玄'}, {'方丈', '首座'})

    def test_group_class_and_needs(self):
        r, sp = self.ref, self.sp
        self.assertEqual({k: (g.place, g.act, g.label) for k, g in sp.group.items()}, r.GROUP)
        self.assertEqual({k: (g.place, g.act, g.label) for k, g in sp.common.classes.items()}, r.CLASS)
        self.assertEqual(sp.needs.base, r.BASE)
        self.assertEqual(sp.needs.eff, r.EFF)
        self.assertEqual(sp.needs.bonus, r.BONUS)
        self.assertEqual(sp.needs.category, r.CAT)
        self.assertEqual(sp.needs.init, {'h': 70.0, 'e': 80.0, 'c': 70.0, 's': 60.0, 'a': 60.0})

    def test_rumor_and_salience(self):
        r, sp = self.ref, self.sp
        self.assertEqual((sp.rumor.penalty, sp.rumor.decay, sp.rumor.min_strength), (r.PEN, r.NEWS_DECAY, r.NEWS_MIN))
        by_label = {E.label(k): v for k, v in sp.salience.items()}
        for k, v in r.SAL.items():
            self.assertEqual(by_label[k], v, k)

    def test_ladder_and_cases(self):
        sp = self.sp
        self.assertEqual([s.txt for s in sp.ladder], ['罚跪香三日', '杖责并禁闭二日', '禁闭五日', '迁单出寺'])
        self.assertEqual([(s.kneel_days, s.conf_days, s.gone) for s in sp.ladder],
                         [(3, 0, False), (0, 2, False), (0, 5, False), (0, 0, True)])
        self.assertEqual((sp.cases.open, sp.cases.done, sp.cases.cold), ('在查', '已处分', '悬案'))

    def test_every_numeric_constant_of_the_prototype_source_is_in_the_spec(self):
        """原型代码里出现过的每个“不平凡”的数，都应在规格里出现（防止漏抄：魔数必须成为字段）。"""
        import dataclasses
        import re
        src = REF_PATH.read_text(encoding='utf-8')
        body = src[src.index('class P:'):src.index('def line(')]
        body = re.sub(r"'[^']*'", "''", body)                       # 去掉字符串里的数字
        body = re.sub(r'#.*', '', body)
        nums = set(re.findall(r'(?<![\w.])(\d+\.\d+|\d+)(?![\w.])', body))
        seen = set()

        def walk(o):
            if dataclasses.is_dataclass(o) and not isinstance(o, type):
                for f in dataclasses.fields(o):
                    walk(getattr(o, f.name))
            elif isinstance(o, dict):
                for k, v in o.items():
                    walk(k)
                    walk(v)
            elif isinstance(o, (list, tuple, set, frozenset)):
                for v in o:
                    walk(v)
            elif isinstance(o, (int, float)) and not isinstance(o, bool):
                seen.add(float(o))
        walk(self.sp)
        walk(PROTO60_CAST)                                           # 三个要角的性格改写属于场景，不在 SiteSpec 里
        missing = sorted(n for n in nums if float(n) not in seen)         # 不豁免任何数（含 0、1、100、12、60、30）
        self.assertEqual(missing, [], '原型里出现、规格里没有的数：%s' % missing)


class StepwiseDifferential(unittest.TestCase):
    """多个种子与规模：轨迹、统计、事件序列与原型逐项相同（比日志里的那几个数更严）。"""

    @classmethod
    def setUpClass(cls):
        cls.ref = load_ref()

    def check(self, seed, n, days, script=None, acting=True):
        r = self.ref.World(seed=seed, n=n, days=days, script=script, acting=acting).run()
        g = ProtoRun(seed=seed, n=n, days=days, script=script, acting=acting).run()
        eng = g.engine
        self.assertEqual(g.hash, r.hash, (seed, n, days))
        for i in range(n):
            self.assertEqual(eng.places_of(i), r.places[i], (seed, n, days, i))
        self.assertEqual({k: v for k, v in eng.stat.items() if v}, {k: v for k, v in r.stat.items() if v})
        self.assertEqual([(E.label(e.kind), e.actor, e.day, e.slot, e.cause, len(e.wit)) for e in eng.evs],
                         [(e['kind'], e['actor'], e['day'], e['slot'], e['cause'], len(e['wit'])) for e in r.events])
        self.assertEqual(eng.choice, r.choice)
        self.assertEqual(eng.acts, r.acts)
        self.assertEqual((eng.moodlow, eng.pd), (r.moodlow, r.pd))
        self.assertEqual(eng.daily, r.daily)
        norm = lambda v: max(v, 0)                          # 引擎用很小的负数表示“从未”，原型用 0；跑过之后只比有没有发生过
        for a, b in zip(r.people, eng.people):
            self.assertEqual((a.need, a.thoughts, a.news, a.pending, a.absent, a.slackd, a.offences, a.gone, a.office,
                              a.dorm, a.track, (a.D, a.S, a.G, a.T, a.R)),
                             (b.need, b.thoughts, b.news, b.pending, b.absent, b.slackd, b.offences, b.gone, b.office,
                              b.dorm, b.track, (b.D, b.S, b.G, b.T, b.R)), (seed, a.id))
            self.assertEqual([norm(a.ill), norm(a.conf), norm(a.kneel), norm(a.duty_day), norm(a.lazy_day)],
                             [norm(b.ill), norm(b.conf), norm(b.kneel), norm(b.duty_day), norm(b.lazy_day)])
        self.assertEqual(r.mods, eng.opinions.mods)
        self.assertEqual((r.water, r.wood, r.kit_staff), (eng.stock['water'], eng.stock['wood'], eng.kit_staff))

    def test_random_keys_are_the_same_multiset_as_the_prototype(self):
        """每一次抽签的键（用途、日、时辰、人……）与原型的抽签键逐一相同、次数相同：不多抽、不少抽、不换键。"""
        from collections import Counter
        from tianl.core import rnd_b2
        probe = ProtoRun().engine
        kit = probe.by['典座'] + probe.by['饭头'][:3]
        scripts = (({'gossip': (6, probe.common[8].ix, probe.common[9].ix)}, True), ({'ill': (10, kit, 4)}, False))
        for script, acting in scripts:
            ref_keys, port_keys = Counter(), Counter()
            orig = self.ref.rnd

            def rec_ref(*k):
                ref_keys[tuple(map(str, k))] += 1
                return orig(*k)

            def rec_port(*k):
                port_keys[tuple(map(str, k))] += 1
                return rnd_b2(*k)
            self.ref.rnd = rec_ref
            try:
                self.ref.World(seed=PROTO_SEED, script=script, acting=acting).run()
            finally:
                self.ref.rnd = orig
            ProtoRun(script=script, acting=acting, rng=rec_port).run()
            self.assertEqual(ref_keys, port_keys, script)
            self.assertGreater(sum(port_keys.values()), 10000)

    def test_seeds_and_sizes(self):
        for seed in (1, 2, 3, PROTO_SEED):
            self.check(seed, 60, 30)
        self.check(7, 75, 25)
        self.check(8, 90, 15)

    def test_long_run_with_departure(self):
        self.check(PROTO_SEED, 60, 90)                       # 含惯犯迁单

    def test_with_scripts(self):
        g = ProtoRun().common
        self.check(PROTO_SEED, 60, 30, script={'gossip': (6, g[8].ix, g[9].ix)})
        kit = ProtoRun().engine.by['典座'] + ProtoRun().engine.by['饭头'][:3]
        self.check(PROTO_SEED, 60, 30, script={'ill': (10, kit, 4)}, acting=False)
        self.check(PROTO_SEED, 60, 30, script={'ill': (10, kit, 4)}, acting=True)


if __name__ == '__main__':
    unittest.main()
