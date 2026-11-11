"""规格与原型的一致性：由 defs 构造的 proto60_spec() 的每个常数都等于原型 npc_spike.py 里对应的常量；
并对多个种子与规模做“逐步差分”：轨迹、统计、事件序列与原型逐项相同。
原型文件只读，本测试只 import 它，不改它。（规格由 defs/*/proto60*.toml 构造：原型里的独立字段——岗位的理事时段、集体日程、功课、
需求增减……——现在分别在行为包与交互里，这里从包与交互里读出来再比。）
"""
import dataclasses
import importlib.util
import sys
import unittest
from pathlib import Path

from tianl.npc import ProtoRun, proto60_spec
from tianl.npc import events as E
from tianl.npc.scenarios import PROTO_SEED, proto60_scenario
from tests.test_npc_support import (class_acts, group_acts, handler_packages, office_posts, package, with_effects,
                                    with_interaction, with_params)

GOSSIP_SLOT = proto60_scenario().gossip.slot            # 传闻脚本发生的时辰：场景（defs）给，引擎里没有缺省

REF_PATH = Path(__file__).resolve().parent.parent / 'reference' / 'npc_spike.py'
NPC_SRC = Path(__file__).resolve().parent.parent / 'tianl' / 'npc'


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
        posts = office_posts(sp)                                     # 岗位的理事场所与时辰：第 8 层（岗位）的声明式包
        self.assertEqual({k: v[0] for k, v in posts.items()}, r.OFFICE_PLACE)
        self.assertEqual({k: v[1] for k, v in posts.items()}, r.OFFICE_SLOTS)
        self.assertEqual(set(sp.kitchen_offices), set(r.KITCHEN))
        self.assertEqual(set(sp.disc_offices), r.DISC)
        self.assertEqual(package(sp, 'duty_kitchen').when.slots, r.KIT_SLOTS)
        self.assertEqual({o.name for o in sp.offices if o.prefix == '玄'}, {'方丈', '首座'})

    def test_group_class_and_needs(self):
        r, sp = self.ref, self.sp
        self.assertEqual(group_acts(sp), r.GROUP)                    # 集体日程：第 7 层的声明式包（布萨带日子条件，单列）
        self.assertEqual(class_acts(sp), r.CLASS)                    # 清众的功课：第 9 层“身份”里有 who.track 的包
        up = package(sp, 'uposatha')                                 # 原型：if day in (1, 15) and slot == 7: return ('hall', 'chant', '集体', '布萨诵戒')
        self.assertEqual((up.when.days, up.when.slots, up.do.place, up.do.act, up.do.label, up.layer),
                         ((1, 15), (7,), 'hall', 'chant', '布萨诵戒', '集体'))
        self.assertEqual(sp.needs.base, r.BASE)
        self.assertEqual({a: i.effects for a, i in sp.interactions.items()}, r.EFF)     # 活动的需求增减：交互的 effects
        self.assertEqual({a: i.bonus for a, i in sp.interactions.items() if i.bonus}, r.BONUS)
        self.assertEqual({a: i.category for a, i in sp.interactions.items()}, r.CAT)
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
        walk(proto60_scenario())                                     # 三个要角的性格改写、实验的日子……属于场景，不在 SiteSpec 里
        missing = sorted(n for n in nums if float(n) not in seen)         # 不豁免任何数（含 0、1、100、12、60、30）
        self.assertEqual(missing, [], '原型里出现、规格里没有的数：%s' % missing)


class StepwiseDifferential(unittest.TestCase):
    """多个种子与规模：轨迹、统计、事件序列与原型逐项相同（比日志里的那几个数更严）。"""

    @classmethod
    def setUpClass(cls):
        cls.ref = load_ref()

    _both = {}                                              # 配置 -> both() 的结果（没有 patch、没改规格的运行才缓存，只读共用）

    @classmethod
    def both(cls, seed, n, days, script=None, acting=True, observer=None, spec=None, patch=None, record=False):
        """原型与移植版各跑一遍：返回 (原型 World 的结果, 移植版 ProtoRun, 原型抽签键多重集, 移植抽签键多重集)。
        patch：{原型模块级常数名: 新值}，只在内存里临时改原型模块（不碰文件），跑完恢复；spec 给对应改过的规格。
        record=True 时另记两边的每一次抽签的键（多重集，键里的每一项转成字符串；否则后两项是 None）。
        没有 patch、没改规格的配置按配置缓存：几条测试要同一个配置（比如“传闻脚本”）就只跑一次，结果只读共用。"""
        key = (seed, n, days, repr(script), acting, observer) if spec is None and not patch else None
        hit = cls._both.get(key) if key else None
        if hit is not None and (hit[2] is not None or not record):
            return hit
        from collections import Counter
        from tianl.core import rnd_b2
        from tianl.npc.host import StandaloneHost
        ref_keys, port_keys = (Counter(), Counter()) if record else (None, None)
        saved = {k: getattr(cls.ref, k) for k in list(patch or {}) + ['rnd']}
        try:
            for k, v in (patch or {}).items():
                setattr(cls.ref, k, v)
            if record:
                orig = cls.ref.rnd

                def rec_ref(*k):
                    ref_keys[tuple(map(str, k))] += 1
                    return orig(*k)
                cls.ref.rnd = rec_ref
            r = cls.ref.World(seed=seed, n=n, days=days, script=script, acting=acting, observer=observer).run()
        finally:
            for k, v in saved.items():
                setattr(cls.ref, k, v)
        host = None
        if record:
            def rec_port(*k):
                port_keys[tuple(map(str, k))] += 1
                return rnd_b2(*k)
            host = StandaloneHost(seed, rec_port)
        g = ProtoRun(seed=seed, n=n, days=days, script=script, acting=acting, observer=observer, spec=spec, host=host).run()
        out = (r, g, ref_keys, port_keys)
        if key:
            cls._both[key] = out
        return out

    def check(self, seed, n, days, script=None, acting=True, spec=None, patch=None, record=False):
        """原型与移植版逐项比对（轨迹、统计、事件序列、终态……）。返回移植版的这次运行。"""
        r, g, _, _ = self.both(seed, n, days, script, acting, None, spec, patch, record)
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
        return g

    @classmethod
    def scenario_keys(cls):
        """若干场景下，原型与移植版各自的“抽签键多重集”：{名: (原型 Counter, 移植 Counter)}；只算一次，且与下面的逐步差分共用同一次运行。
        场景要把每一种抽签用途都跑到：N1 无人代理才有举报概率（report），种子 4 的 90 日有传讯认错（confess）与
        处分阶梯，观察者在场才有细节叙述（narr）。"""
        probe = ProtoRun().engine
        kit = probe.by['典座'] + probe.by['饭头'][:3]
        scenarios = {
            '传闻脚本（监院派人代理）': dict(script={'gossip': (6, probe.common[8].ix, probe.common[9].ix), 'gossip_slot': GOSSIP_SLOT}),
            'N1 无人代理': dict(script={'ill': (10, kit, 4)}, acting=False),
            '种子 4 的 90 日': dict(seed=4, days=90),
            '观察者在廊下 12 日': dict(days=12, observer='clo'),
        }
        out = {}
        for name, kw in scenarios.items():
            _, _, ref_keys, port_keys = cls.both(kw.get('seed', PROTO_SEED), 60, kw.get('days', 30), kw.get('script'),
                                                kw.get('acting', True), kw.get('observer'), record=True)
            out[name] = (ref_keys, port_keys)
        return out

    def test_random_keys_are_the_same_multiset_as_the_prototype(self):
        """每一次抽签的键（用途、日、时辰、人……）与原型的抽签键逐一相同、次数相同：不多抽、不少抽、不换键。"""
        for name, (ref_keys, port_keys) in self.scenario_keys().items():
            self.assertEqual(ref_keys, port_keys, name)
            self.assertGreater(sum(port_keys.values()), 1000, name)

    @staticmethod
    def engine_random_purposes():
        """从引擎源码里读出所有抽签用途：对 rng(...) / r(...) 的调用，第二个参数是字符串；再加上建人用的五项性格键。"""
        import ast
        from tianl.npc.spec import TRAIT_KEYS
        found = set(TRAIT_KEYS)
        for f in sorted(NPC_SRC.glob('*.py')):
            for n in ast.walk(ast.parse(f.read_text(encoding='utf-8'))):
                if isinstance(n, ast.Call) and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant) \
                        and isinstance(n.args[1].value, str) \
                        and ((isinstance(n.func, ast.Name) and n.func.id in ('r', 'rng'))
                             or (isinstance(n.func, ast.Attribute) and n.func.attr == 'rng')):
                    found.add(n.args[1].value)
        return found

    def test_every_random_purpose_of_the_engine_is_compared_with_the_prototype(self):
        """引擎源码里的每一种抽签用途，都至少在一个场景里被抽到过，并因此经过了上面的多重集比对——
        不会有哪一支概率判定（举报、认错、传话……）从来没跑到过、却无人察觉。"""
        purposes = self.engine_random_purposes()
        self.assertGreaterEqual(len(purposes), 20)
        seen = {}
        for name, (ref_keys, port_keys) in self.scenario_keys().items():
            for k, c in port_keys.items():
                seen[k[1]] = seen.get(k[1], 0) + c
        self.assertEqual(sorted(purposes - set(seen)), [], '从未被任何对照场景抽到的用途')
        for purpose in ('report', 'confess', 'disc', 'share', 'narr', 'wchat'):
            self.assertGreater(seen[purpose], 0, purpose)
        _, port_keys = self.scenario_keys()['N1 无人代理']
        self.assertGreater(sum(c for k, c in port_keys.items() if k[1] == 'report'), 100)      # 举报概率这一支真的被走了很多遍

    def reasons(self, run):
        eng = run.engine
        return {eng.where(p.ix, d, sl)[3] for p in eng.people for d in range(1, run.days + 1) for sl in range(12)}

    def test_reaction_layer_branch_is_compared(self):
        """“反应”层（去戒律院举报）在基准、90 日、种子 1–5 里一次也不生效——举报全由当面禀告送达。
        N1 无人代理在种子 34 的 40 日里才走到它（pkg_反应 > 0），这里与原型逐项比对。"""
        from tianl.npc.engine import PKG_STAT
        from tianl.npc.spec import L_REACT
        probe = ProtoRun().engine
        kit = probe.by['典座'] + probe.by['饭头'][:3]
        g = self.check(34, 60, 40, script={'ill': (10, kit, 4)}, acting=False)
        self.assertGreater(g.engine.stat[PKG_STAT + L_REACT], 0)

    def test_court_without_a_judge_and_departed_offender_branches_are_compared(self):
        """裁断时辰戒律院没人能断案（首座与执事全病倒），以及处分时当事人已迁单：这两支基准里从不走到，与原型逐项比对。"""
        probe = ProtoRun().engine
        court = probe.by['首座'] + probe.by['执事']
        kit = probe.by['典座'] + probe.by['饭头'][:3]
        g = self.check(PROTO_SEED, 60, 30, script={'ill': (10, court, 5)})
        self.assertGreater(g.engine.stat['no_judge'], 0)
        g = self.check(PROTO_SEED, 60, 30, script={'ill': (10, court + kit, 5)}, acting=False)
        self.assertGreater(g.engine.stat['no_judge'], 0)
        closed = g.engine.spec.cases.closed                          # 当事人已迁单：案子直接结案，不再处分
        self.assertTrue(any(c.state == closed for c in g.engine.norms.cases.values()))

    def test_perturbed_constants_still_agree_with_the_prototype(self):
        """把原型的模块级常数在内存里改掉（原型文件不动），同时改规格里对应的字段，两边仍须逐项一致。
        一来证明引擎读的是规格字段、读法与原型读常数的读法相同；二来逼出基准世界从不走到的分支
        （“昏沉不支”“困乏未起”、容量吃紧后的改选、更多举报与处分……）。"""
        sp, R = proto60_spec(), dataclasses.replace
        base = dict(sp.needs.base)
        eff = {a: dict(i.effects) for a, i in sp.interactions.items()}
        eff['sleep']['e'], eff['chat']['s'], eff['bath']['c'], eff['stroll'] = 30, 10, 40, {'s': 3, 'e': 1}
        bonus = {'martial': ('武', 15, 2), 'study': ('学', 30, 5), 'zazen': ('禅', 8, 1)}
        cap = {'lib': 3, 'yard': 5, 'bath': 4, 'well': 3, 'zen': 20, 'clo': 10}
        sal = {E.FOOD_THEFT: 90, E.SANCTION: 40, E.THEFT_FOUND: 70, E.ABSENCE: 0, E.SLACK: 0, E.REPORT: 0, E.BED_EMPTY: 0}
        eff_spec = R(sp, interactions={a: R(i, effects=eff[a]) for a, i in sp.interactions.items()})
        bonus_spec = R(sp, interactions={a: R(i, bonus=bonus.get(a, i.bonus)) for a, i in sp.interactions.items()})
        cases = {
            '困得快（e 每时辰 -18）': (R(sp, needs=R(sp.needs, base={**base, 'e': -18.0})), {'BASE': {**base, 'e': -18.0}}),
            '饿得快、孤得快': (R(sp, needs=R(sp.needs, base={**base, 'h': -9.0, 's': -2.5})),
                             {'BASE': {**base, 'h': -9.0, 's': -2.5}}),
            '设施工位吃紧': (R(sp, capacity=cap), {'CAPF': dict(cap)}),
            '活动的收支效果': (eff_spec, {'EFF': {k: dict(v) for k, v in eff.items()}}),
            '功课加成': (bonus_spec, {'BONUS': dict(bonus)}),
            '传闻与见闻强度': (R(sp, rumor=R(sp.rumor, penalty=8, decay=3, min_strength=30), salience=sal),
                              {'PEN': 8, 'NEWS_DECAY': 3, 'NEWS_MIN': 30, 'SAL': {E.label(k): v for k, v in sal.items()}}),
            '夜间时辰更长': (R(sp, night=(10, 11, 0, 1)), {'NIGHT': (10, 11, 0, 1)}),
        }
        for name, (spec, patch) in cases.items():
            g = self.check(PROTO_SEED, 60, 20, spec=spec, patch=patch)
            if name.startswith('困得快'):
                why = self.reasons(g)
                self.assertIn(package(sp, 'physiology').params['faint_label'], why)      # 基准里从不走到的两个生理分支
                self.assertIn(package(sp, 'lazy').params['tired_label'], why)
            if name.startswith('饿得快'):
                self.assertGreater(g.engine.stat['sanction'], 3)     # 偷食、举报、处分阶梯整条路都更忙
            if name.startswith('设施工位'):
                self.assertGreater(g.engine.stat['full'], 1000)      # 满员改选大量发生

    def test_seeds_and_sizes(self):
        for seed in (1, 2, 3, PROTO_SEED):
            self.check(seed, 60, 30)
        self.check(7, 75, 25)
        self.check(8, 90, 15)

    def test_long_run_with_departure(self):
        self.check(PROTO_SEED, 60, 90)                       # 含惯犯迁单
        self.check(4, 60, 90, record=True)                   # 含传讯认错与举报定罪两条路（与抽签键多重集共用这次运行）

    def test_observer_changes_nothing_but_the_narration_count(self):
        for place in ('clo', 'hall', 'court'):
            r, g, _, _ = self.both(PROTO_SEED, 60, 12, observer=place, record=place == 'clo')   # 廊下那组与抽签键多重集共用
            self.assertEqual((g.hash, g.engine.narr), (r.hash, r.narr), place)
            self.assertGreater(r.narr, 0)

    def test_with_scripts(self):
        g = ProtoRun().common
        self.check(PROTO_SEED, 60, 30, script={'gossip': (6, g[8].ix, g[9].ix), 'gossip_slot': GOSSIP_SLOT}, record=True)      # 与抽签键多重集共用
        kit = ProtoRun().engine.by['典座'] + ProtoRun().engine.by['饭头'][:3]
        self.check(PROTO_SEED, 60, 30, script={'ill': (10, kit, 4)}, acting=False, record=True)
        self.check(PROTO_SEED, 60, 30, script={'ill': (10, kit, 4)}, acting=True)


if __name__ == '__main__':
    unittest.main()
