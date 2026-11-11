"""tianl/npc 的接口与性质测试：Host 边界、rng 注入、查询 API、ix/pid、观察者无关、源码规矩。
（与原型的数字、哈希比对在 test_npc_proto.py；与原型常量、逐步差分在 test_npc_spec.py。）
"""
import ast
import dataclasses
import os
import re
import unittest
from collections import Counter
from pathlib import Path

from tianl.core import cal, rnd, rnd_b2
from tianl.npc import NpcEngine, PersonSpec, ProtoRun, Script, StandaloneHost, proto60_spec
from tianl.npc import events as E
from tianl.npc.host import CmdResult, Event, Host
from tianl.npc.model import FIELD_MASK, GAP, Symbols, Trail, pack, unpack
from tianl.npc.spec import SpecError
from tianl.npc.scenarios import gossip_script

BASE_HASH = 'e8f8209eeb8ca94a'
NPC_SRC = Path(__file__).resolve().parent.parent / 'tianl' / 'npc'


def base_run(**kw):
    g = ProtoRun().common
    kw.setdefault('script', gossip_script(g))
    return ProtoRun(**kw).run()


class HostBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = StandaloneHost(20261110, rnd_b2, record_cmds=True)
        cls.world = base_run(host=cls.host)

    def test_ids_are_sequential_and_kinds_are_codes(self):
        evs = self.host.events
        self.assertEqual([e.id for e in evs], list(range(len(evs))))
        self.assertTrue({e.kind for e in evs} <= set(E.EMITTED))
        self.assertEqual(len(evs), len(self.world.engine.evs))

    def test_host_sees_external_ids_not_ix(self):
        eng = self.world.engine
        pids = set(eng.pids)
        for e in self.host.events:
            self.assertTrue(e.actor is None or e.actor in pids)
            self.assertTrue(all(isinstance(w, str) and w in pids for w in e.witnesses))
        found = [e for e in self.host.events if e.kind == E.THEFT_FOUND]
        self.assertTrue(found and all(e.actor is None for e in found))     # 失窃没有当事人

    def test_payload_has_wit(self):
        e = next(x for x in self.host.events if x.kind == E.FOOD_THEFT and x.witnesses)
        self.assertEqual(e.payload()['wit'], e.witnesses)
        self.assertEqual(e.wit, e.witnesses)
        self.assertIn('why', e.payload())

    def test_event_cause_chain(self):
        by_id = {e.id: e for e in self.host.events}
        for e in self.host.events:
            if e.kind in (E.THEFT_FOUND, E.REPORT, E.SANCTION):
                self.assertEqual(by_id[e.cause].kind, E.FOOD_THEFT)        # 因果链都指向偷食

    def test_kernel_command_stub_is_called_once_per_worker(self):
        self.assertEqual(self.host.cmd_count, 870)
        self.assertEqual(len(self.host.cmds), 870)
        name, pid, args = self.host.cmds[0]
        self.assertEqual(name, 'job')
        self.assertIn(pid, self.world.engine.pids)
        self.assertEqual({'job', 'place', 'day', 'slot'}, set(args))

    def test_refused_commands_mean_unfinished_jobs(self):
        class Refusing(StandaloneHost):
            def cmd(self, name, pid, **args):
                return CmdResult(False, '内核拒绝')
        x = ProtoRun(host=Refusing(20261110, rnd_b2)).run()
        self.assertEqual(x.engine.stat['job_done'], 0)
        self.assertEqual(x.engine.stat['job_post'], 870)
        self.assertGreater(x.engine.stat['half_meal'], 0)                 # 没人挑水打柴，库存耗尽，半餐

    def test_engine_behaviour_does_not_depend_on_how_the_host_numbers_events(self):
        """随机数键与见闻用引擎自己的流水号；Host 的事件 id（从 1000 起、每次跳 3、夹杂别处写的事件）只出现在边界。"""
        class Busy(StandaloneHost):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.next_id = 1000
                self.by_id = {}

            def ev(self, kind, actor, place, witnesses, day, slot, cause=None, **data):
                e = super().ev(kind, actor, place, witnesses, day, slot, cause, **data)
                e.id, self.next_id = self.next_id, self.next_id + 3
                self.by_id[e.id] = e
                return e
        h = Busy(20261110, rnd_b2)
        x = ProtoRun(host=h, script=gossip_script(ProtoRun().common)).run()
        eng = x.engine
        self.assertEqual(x.hash, BASE_HASH)                                  # 与 StandaloneHost 的结果逐位相同
        self.assertEqual([e.id for e in eng.evs], list(range(len(eng.evs))))    # 引擎流水号从 0 连续
        self.assertTrue(all(e.hid >= 1000 and e.hid % 3 == 1 for e in eng.evs))
        self.assertEqual([e.hid for e in eng.evs], [e.id for e in h.events])    # hid 就是 Host 给的
        for e in h.events:                                                    # 交给 Host 的 cause 是 Host 自己的 id
            if e.cause is not None:
                self.assertIn(e.cause, h.by_id)
                self.assertEqual(h.by_id[e.cause].kind, E.FOOD_THEFT)
        self.assertTrue(all(c['eid'] >= 1000 for c in eng.cases()))           # 边界出口：案卷、见闻都给 Host 的 id
        news = [n for p in eng.pids for n in eng.news_of(p)]
        self.assertTrue(news and all(n[0] in h.by_id for n in news))
        self.assertEqual(eng.event_of(news[0][0]).hid, news[0][0])
        ref = base_run().engine
        self.assertEqual(eng.stat, ref.stat)
        self.assertEqual([eng.places_of(i) for i in range(60)], [ref.places_of(i) for i in range(60)])

    def test_host_base_class_is_abstract(self):
        h = Host()
        with self.assertRaises(NotImplementedError):
            h.ev('X', None, 'p', [], 0, 0)
        with self.assertRaises(NotImplementedError):
            h.cmd('x', 'P1')


class RngInjection(unittest.TestCase):
    def test_every_random_goes_through_the_injected_rng(self):
        used = Counter()

        def counting(*keys):
            used[keys[1]] += 1
            return rnd_b2(*keys)

        g = ProtoRun().common
        x = ProtoRun(host=StandaloneHost(20261110, counting), script=gossip_script(g), observer='clo').run()
        self.assertEqual(x.hash, BASE_HASH)                      # 委托给 rnd_b2，所以哈希相同
        build = [t for t in used if t in ('D', 'S', 'G', 'T', 'R')]    # 建人阶段的 gauss（每人每项 a、b 两个键）
        self.assertEqual(sorted(build), ['D', 'G', 'R', 'S', 'T'])
        for tag in ('roam', 'tempt', 'lazy', 'slack', 'sb', 'cq', 'pair', 'chat', 'share', 'wchat', 'disc',
                    'ill', 'illd', 'narr'):
            self.assertGreater(used[tag], 0, tag)
        used2 = Counter()                                        # N1 里证人多：举报概率（report）与传讯认错（confess）也要走注入
        def counting2(*keys):
            used2[keys[1]] += 1
            return rnd_b2(*keys)
        eng = ProtoRun().engine
        ProtoRun(host=StandaloneHost(20261110, counting2), acting=False,
                 script={'ill': (10, eng.by['典座'] + eng.by['饭头'][:3], 4)}).run()
        self.assertGreater(used2['report'], 0)
        # 建人每人五项性格 × 每项两次抽签
        self.assertEqual(sum(used[t] for t in 'DSGTR'), 60 * 5 * 2)

    def test_rng_choice_changes_the_world_but_not_determinism(self):
        a = ProtoRun(rng=rnd).run()
        b = ProtoRun(rng=rnd).run()
        self.assertEqual(a.hash, b.hash)
        self.assertNotEqual(a.hash, BASE_HASH)

    def test_seed_changes_the_world(self):
        self.assertNotEqual(ProtoRun(seed=1).run().hash, ProtoRun(seed=2).run().hash)


class ObserverIndependence(unittest.TestCase):
    def test_hash_is_independent_of_where_the_observer_stands(self):
        base = ProtoRun(days=12).run().hash
        for place in ('clo', 'kit', 'hall', 'court', 'dorm1', 'zen', 'nowhere'):
            x = ProtoRun(days=12, observer=place).run()
            self.assertEqual(x.hash, base, place)
        self.assertGreater(ProtoRun(days=12, observer='hall').run().engine.narr, 0)
        self.assertEqual(ProtoRun(days=12, observer='nowhere').run().engine.narr, 0)

    def test_observer_only_reads(self):
        a = ProtoRun(days=6).run().engine
        b = ProtoRun(days=6, observer='clo').run().engine
        self.assertEqual([p.need for p in a.people], [p.need for p in b.people])
        self.assertEqual(a.stat, b.stat)
        self.assertGreater(b.narr, 0)


class Queries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = base_run()
        cls.eng = cls.world.engine

    def test_every_decision_has_layer_and_reason(self):
        eng, sp, n = self.eng, self.eng.spec, 0
        for p in eng.people:
            for day in range(1, 31):
                for slot in range(12):
                    w = eng.where(p.ix, day, slot)
                    self.assertIsNotNone(w)
                    place, act, layer, reason = w
                    self.assertTrue(place in sp.places and act and reason)
                    self.assertIn(layer, sp.layer_rank)
                    n += 1
        self.assertEqual(n, eng.stat['ps'])                       # 100% 说得清

    def test_where_accepts_pid_and_ix_and_rejects_the_unknown_time(self):
        eng = self.eng
        p = eng.people[30]
        self.assertEqual(eng.where(p.pid, 8, 5), eng.where(30, 8, 5))
        self.assertIsNone(eng.where(30, 0, 0))
        self.assertIsNone(eng.where(30, 31, 0))

    def test_where_matches_report_trace(self):
        eng = self.eng
        w = eng.where(self.world.glutton.ix, 8, 1)                  # 第 8 日丑时惯犯夜里偷食
        self.assertEqual(w, ('kit', 'steal', '越轨', '夜里偷食'))

    def test_explain(self):
        eng = self.eng
        ex = eng.explain(self.world.glutton.pid, 8, 1)
        self.assertEqual((ex['layer'], ex['reason'], ex['place'], ex['act']), ('越轨', '夜里偷食', 'kit', 'steal'))
        self.assertEqual(ex['layer_rank'], 0)
        self.assertEqual(ex['place_name'], '香积厨')
        self.assertIn('夜里偷食', ex['text'])
        self.assertNotIn('state', ex)                              # 过去的时辰没有当时的状态
        last = eng.last
        ex2 = eng.explain(self.world.glutton.ix, *last)
        self.assertIn('state', ex2)
        self.assertEqual(set(ex2['state']['need']), set('hecsa'))
        self.assertIsNone(eng.explain(0, 99, 0))
        steward = eng.by['典座'][0]
        self.assertEqual(eng.explain(steward, 8, 2)['layer'], '值守')          # 典座丑时……
        self.assertEqual(eng.explain(steward, 8, 2)['layer_rank'], 5)

    def test_present_now_and_then(self):
        eng = self.eng
        now = eng.present('hall')
        self.assertEqual(now, eng.present('hall', *eng.last))
        kit8 = eng.present('kit', 8, 1)
        self.assertIn(self.world.glutton.pid, kit8)
        self.assertEqual(eng.present('nowhere'), [])
        with self.assertRaises(ValueError):
            eng.present('hall', 8)

    def test_news_of_opinion_mood_needs_friends_cases(self):
        eng = self.eng
        a = eng.people[31]
        news = eng.news_of(a.pid)
        self.assertTrue(all(len(x) == 5 for x in news))
        self.assertEqual(news, sorted(news, key=lambda x: (-x[2], x[0])))
        o = eng.opinion(31, 32)
        self.assertTrue(-100 <= o <= 100)
        bd = eng.opinion_breakdown(31, 32)
        self.assertAlmostEqual(bd['total'], o)
        self.assertTrue(0 <= eng.mood(31) <= 100)
        self.assertEqual(set(eng.needs_of(31)), set('hecsa'))
        fr, foe = eng.friends()
        self.assertEqual((len(fr), foe), (35, 1))
        cs = eng.cases()
        self.assertEqual(Counter(c['state'] for c in cs), {'悬案': 5, '已处分': 1, '在查': 1})
        done = [c for c in cs if c['state'] == '已处分'][0]
        self.assertEqual((done['via'], done['sanction'], done['actor']), ('举报', '罚跪香三日', self.world.glutton.pid))
        self.assertEqual(len(done['accusers']), 1)

    def test_every_sanction_traces_back_to_a_report_or_a_confession(self):
        confessions = 0
        for seed in (20261110, 2, 4):                              # 种子 2、4 的 90 日里有人认错
            x = ProtoRun(seed=seed, days=90).run()
            eng = x.engine
            by_case = {c['eid']: c for c in eng.cases()}
            sanctions = [e for e in eng.evs if e.kind == E.SANCTION]
            self.assertEqual(len(sanctions), eng.stat['sanction'])
            for s in sanctions:
                c = by_case[eng.ev_by_id[s.cause].hid]
                self.assertIn(c['via'], ('举报', '认错'))
                self.assertEqual(eng.ev_by_id[s.cause].kind, E.FOOD_THEFT)
                reports = [e for e in eng.evs if e.kind == E.REPORT and e.cause == s.cause]
                if c['via'] == '举报':
                    self.assertTrue(reports)
                    self.assertEqual(sorted(eng.pids[r.actor] for r in reports), c['accusers'])
                else:
                    confessions += 1
                    self.assertEqual(c['accusers'], [])             # 认错：没有指认人，本人当夜在寮外被传讯
                    self.assertIn(c['actor'], c['suspects'])
            self.assertEqual(sum(1 for c in by_case.values() if c['via'] == '认错'), eng.stat['confess'])
        self.assertGreater(confessions, 0)

    def test_90_days_ladder_and_leaving(self):
        x = ProtoRun(days=90).run()
        eng = x.engine
        self.assertEqual([c['sanction'] for c in eng.cases() if c['sanction']],
                         ['罚跪香三日', '杖责并禁闭二日', '禁闭五日', '迁单出寺'])    # 四级阶梯各走一遍
        self.assertEqual(eng.people[x.glutton.ix].gone, 83)                     # 计划 8.5：第 83 日迁单出寺

    def test_explain_says_where_a_departed_monk_went(self):
        x = ProtoRun(days=90).run()
        eng, g = x.engine, x.glutton
        self.assertEqual((g.gone, g.gone_why), (83, '迁单出寺'))
        self.assertIsNone(eng.where(g.ix, 83, 11))                               # where 仍是契约里的 None
        ex = eng.explain(g.pid, 83, 11)
        self.assertEqual((ex['gone'], ex['reason'], ex['place'], ex['layer']), (83, '迁单出寺', None, None))
        self.assertIn('已于第83日离寺', ex['text'])
        self.assertEqual(eng.explain(g.ix, 90, 0)['gone'], 83)
        self.assertNotIn('gone', eng.explain(g.ix, 83, 5))                       # 迁单当日巳时（裁断时辰）仍有正常的决定
        self.assertEqual(eng.explain(g.ix, 83, 6)['gone'], 83)                   # 此后没有决定
        self.assertNotIn('gone', eng.explain(g.ix, 82, 11))
        self.assertIsNone(eng.explain(eng.people[0].ix, 99, 0))                  # 没离开的人：没记录就是 None

    def test_state_invariants(self):
        for p in self.eng.people:
            self.assertTrue(all(0 <= v <= 100 for v in p.need.values()))
            self.assertLessEqual(len(p.news), self.eng.spec.rumor.keep)
            self.assertTrue(all(t[1] > 30 for t in p.thoughts))


class IxAndPid(unittest.TestCase):
    def test_new_people_append_and_old_ix_are_stable(self):
        x = ProtoRun(days=3).run()
        eng = x.engine
        before = [(p.ix, p.pid) for p in eng.people]
        h_before = eng.state_hash()
        ps = PersonSpec('P9001', '新来', None, '禅', 'dorm2')
        newbie = eng.add_person(ps)
        self.assertEqual(newbie.ix, 60)
        self.assertEqual([(p.ix, p.pid) for p in eng.people[:60]], before)
        self.assertEqual(eng.ix_of('P9001'), 60)
        self.assertEqual(eng.ix_of(60), 60)
        self.assertEqual(eng.state_hash(), h_before)
        with self.assertRaises(ValueError):
            eng.add_person(ps)
        for day in (4, 5):
            eng.run_day(day)
        self.assertEqual(len(newbie.trail), 24)                    # 只记加入之后
        self.assertEqual(newbie.trail.t0, 4 * 12)
        self.assertIsNone(eng.where('P9001', 3, 0))
        self.assertIsNotNone(eng.where('P9001', 4, 0))
        self.assertIn(newbie.pid, eng.pids)
        self.assertTrue(0 <= eng.agree(0, 'P9001') <= 1)

    def test_on_person_added_and_removed(self):
        x = ProtoRun(days=2).run()
        eng = x.engine
        p = eng.on_person_added(PersonSpec('P9002', '来客', None, '武', 'dorm1'))
        self.assertEqual(eng.on_person_added('P9002'), p)
        eng.on_person_removed('P9002', '游方')
        self.assertEqual((p.gone, p.gone_why), (2, '游方'))
        eng.run_day(3)
        self.assertIsNone(eng.where('P9002', 3, 0))                # 已离开的人不再有决定
        self.assertEqual(eng.stat['left_游方'], 1)
        ex = eng.explain('P9002', 3, 0)                            # 但 explain 说得清去了哪里
        self.assertEqual((ex['gone'], ex['reason']), (2, '游方'))

    def test_on_person_added_by_pid_uses_the_integration_factory(self):
        """ARCHITECTURE 5.1 的 on_person_added(pid)：名册里没有的 pid 由集成层的 person_factory 说明它是谁。"""
        eng = ProtoRun(days=2).run().engine
        with self.assertRaises(LookupError):                       # 没有工厂：不凭空造人
            eng.on_person_added('P9100')
        asked = []

        def factory(pid):
            asked.append(pid)
            return PersonSpec(pid, '来者', None, '学', 'dorm3')
        eng.person_factory = factory
        p = eng.on_person_added('P9100')
        self.assertEqual((p.pid, p.ix, p.dorm, asked), ('P9100', 60, 'dorm3', ['P9100']))
        self.assertIs(eng.on_person_added('P9100'), p)             # 再来一次：已在名册，不再问工厂
        self.assertIs(eng.on_person_added(60), p)
        self.assertEqual(asked, ['P9100'])
        eng.person_factory = lambda pid: PersonSpec('别人', '错', None, '学', 'dorm3')
        with self.assertRaises(ValueError):                        # 工厂给错了人
            eng.on_person_added('P9101')
        self.assertEqual(len(eng.people), 61)

    def test_script_accepts_pid_or_ix(self):
        g = ProtoRun().common
        a = ProtoRun(script=Script(gossip=(6, g[8].ix, g[9].ix))).run().hash
        b = ProtoRun(script={'gossip': (6, g[8].pid, g[9].pid)}).run().hash
        self.assertEqual(a, b)
        self.assertEqual(a, BASE_HASH)

    def test_explicit_traits_override_generation(self):
        spec = proto60_spec()
        eng = NpcEngine(spec, StandaloneHost(1, rnd_b2))
        p = eng.add_person(PersonSpec('X', '甲', None, '武', 'dorm1', traits={'D': 11, 'S': 22, 'G': 33, 'T': 44, 'R': 55}))
        self.assertEqual((p.D, p.S, p.G, p.T, p.R), (11, 22, 33, 44, 55))
        eng.set_traits('X', R=99)
        self.assertEqual(p.R, 99)
        with self.assertRaises(KeyError):
            eng.set_traits('X', Z=1)

    def test_empty_engine_does_not_crash(self):
        eng = NpcEngine(proto60_spec(), StandaloneHost(1, rnd_b2))
        eng.run_slot(1, 0)
        self.assertIsNone(eng.last)


class Model(unittest.TestCase):
    def test_pack_roundtrip_and_symbols(self):
        s = Symbols()
        ids = [s.intern(x) for x in ('kit', 'steal', '越轨', '夜里偷食', 'kit')]
        self.assertEqual(ids[0], ids[4])
        v = pack(*ids[:4])
        self.assertEqual(unpack(v), tuple(ids[:4]))
        self.assertEqual([s.name(i) for i in unpack(v)], ['kit', 'steal', '越轨', '夜里偷食'])

    def test_trail(self):
        t = Trail()
        self.assertIsNone(t.get(5))
        self.assertIsNone(t.end)
        t.push(10, 7)
        t.push(11, 8)
        self.assertEqual((t.get(10), t.get(11), t.get(12), t.get(9)), (7, 8, None, None))
        self.assertEqual((len(t), t.t0, t.end), (2, 10, 12))

    def test_trail_tolerates_gaps_and_rejects_rewinds(self):
        t = Trail()
        t.push(10, 7)
        t.push(13, 9)                                               # 中间 11、12 没记（暂离再回）
        self.assertEqual([t.get(k) for k in range(9, 15)], [None, 7, None, None, 9, None])
        self.assertEqual((len(t), t.end), (4, 14))
        self.assertEqual(t.get(13), 9)                              # 对号入座，不错位
        with self.assertRaises(ValueError):
            t.push(13, 1)                                           # 重复
        with self.assertRaises(ValueError):
            t.push(12, 1)                                           # 回退
        self.assertEqual(t.get(13), 9)

    def test_gap_marker_cannot_collide_with_a_real_decision(self):
        s = Symbols()
        for i in range(FIELD_MASK - 1):                             # 符号号 0..FIELD_MASK-2 都可分配
            s.intern(i)
        self.assertEqual(s.intern('x'), FIELD_MASK - 1)
        with self.assertRaises(OverflowError):                      # FIELD_MASK 留给 GAP
            s.intern('y')
        self.assertNotEqual(pack(FIELD_MASK - 1, FIELD_MASK - 1, FIELD_MASK - 1, FIELD_MASK - 1), GAP)
        self.assertEqual(unpack(GAP), (FIELD_MASK,) * 4)

    def test_queries_survive_a_gap_in_a_trail(self):
        eng = NpcEngine(proto60_spec(), StandaloneHost(1, rnd_b2))
        a = eng.add_person(PersonSpec('A', '甲', None, '武', 'dorm1'))
        b = eng.add_person(PersonSpec('B', '乙', None, '武', 'dorm1'))
        sid = eng.sym.intern
        hall = pack(sid('hall'), sid('chant'), sid('集体'), sid('早课'))
        zen = pack(sid('zen'), sid('zazen'), sid('集体'), sid('晨坐'))
        for t, v in ((24, hall), (25, hall), (27, zen)):            # A 缺了 t=26
            a.trail.push(t, v)
        for t, v in ((24, hall), (25, zen), (26, hall), (27, zen)):
            b.trail.push(t, v)
        self.assertEqual(eng.places_of('A'), ['hall', 'hall', None, 'zen'])
        self.assertIsNone(eng.where('A', 2, 2))                      # t=26：没有记录
        self.assertEqual(eng.where('A', 2, 3)[0], 'zen')             # t=27：没有错位
        self.assertEqual(eng.where('B', 2, 2)[0], 'hall')
        self.assertEqual(eng.agree('A', 'B'), 2 / 3)                 # 只比两人都有记录的 3 个时辰：t=24、25、27

    def test_spec_is_frozen(self):
        sp = proto60_spec()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            sp.night = ()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            sp.rumor.penalty = 0

    def test_event_object(self):
        e = Event(3, 'X', 'P1', 'kit', ['P2'], 1, 2, None, {'why': '因'})
        self.assertIn('Event(#3', repr(e))
        self.assertEqual(e.payload(), {'why': '因', 'wit': ['P2']})


class SpecDriven(unittest.TestCase):
    """规格里的字段确实在起作用（不是摆设）：改一个字段，行为随之变。"""

    def test_uposatha_by_calendar_day_of_month(self):
        sp = proto60_spec()
        by_dom = dataclasses.replace(sp, uposatha=dataclasses.replace(sp.uposatha, by='dom', days=(1, 15)))
        x = ProtoRun(spec=by_dom, days=31).run().engine
        act_at = lambda day: Counter(x.where(i, day, 7)[1] for i in range(60) if x.where(i, day, 7))
        self.assertEqual(cal(14)['dom'], 15)
        self.assertGreaterEqual(act_at(14)['chant'], 40)           # 月内第 15 日布萨：未时大殿诵戒
        self.assertLess(act_at(15)['chant'], 5)                    # 原型口径的第 15 日这里不是布萨
        y = ProtoRun(days=16).run().engine                         # 原型口径：第 1、15 日
        self.assertGreaterEqual(Counter(y.where(i, 15, 7)[1] for i in range(60))['chant'], 40)

    def test_kitchen_staffing_threshold_is_a_field(self):
        sp = proto60_spec()
        harsh = dataclasses.replace(sp, kitchen=dataclasses.replace(sp.kitchen, min_staff=99))
        x = ProtoRun(spec=harsh, days=3).run().engine
        self.assertEqual(x.stat['half_meal'], x.stat['meals'])      # 永远人手不足：每顿都是半餐

    def test_ladder_is_a_field(self):
        sp = proto60_spec()
        gentle = dataclasses.replace(sp, ladder=(dataclasses.replace(sp.ladder[0], kneel_days=1),))
        x = ProtoRun(spec=gentle, days=90).run().engine
        self.assertTrue(all(c['sanction'] == '罚跪香三日' for c in x.cases() if c['sanction']))
        self.assertEqual(sum(1 for p in x.people if p.gone is not None), 0)     # 阶梯只有一级，没人迁单


class SpecValidation(unittest.TestCase):
    def test_proto60_is_valid(self):
        self.assertEqual(proto60_spec().validate(), [])

    def test_dangling_references_are_reported_and_engine_refuses_them(self):
        sp = proto60_spec()
        bad = dataclasses.replace(
            sp, kitchen=dataclasses.replace(sp.kitchen, place='nowhere'),
            court=dataclasses.replace(sp.court, judges=('首座', '无此岗')),
            ladder=(dataclasses.replace(sp.ladder[0], thought='无此想法'),),
            ads=sp.ads[:1] + (dataclasses.replace(sp.ads[1], gate='无此门'),))
        problems = bad.validate()
        for frag in ('kitchen.place', "无此岗", "无此想法", "无此门"):
            self.assertTrue(any(frag in p for p in problems), frag)
        with self.assertRaises(SpecError) as cm:
            NpcEngine(bad, StandaloneHost(1, rnd_b2))
        self.assertEqual(cm.exception.problems, problems)

    def test_new_fields_are_validated(self):
        sp = proto60_spec()
        bad = dataclasses.replace(sp, free=dataclasses.replace(sp.free, choice_key_chars=0),
                                  cases=dataclasses.replace(sp.cases, via_confess=sp.cases.via_report))
        problems = bad.validate()
        self.assertTrue(any('choice_key_chars' in p for p in problems))
        self.assertTrue(any('via_report' in p for p in problems))

    def test_via_labels_come_from_the_spec(self):
        sp = proto60_spec()
        renamed = dataclasses.replace(sp, cases=dataclasses.replace(sp.cases, via_report='据举报', via_confess='自认'))
        x = ProtoRun(spec=renamed, days=90, seed=4).run()
        vias = {c['via'] for c in x.engine.cases() if c['via']}
        self.assertEqual(vias, {'据举报', '自认'})
        y = ProtoRun(days=90, seed=4).run()                                  # 换了标签，行为不变
        self.assertEqual(x.hash, y.hash)


@unittest.skipUnless(os.environ.get('TIANL_SLOW'), '慢测试：TIANL_SLOW=1 打开')
class SlowScale(unittest.TestCase):
    def test_300_monks_one_year_deterministic_and_no_overbooking(self):
        a = ProtoRun(n=300, days=360).run()
        b = ProtoRun(n=300, days=360).run()
        self.assertEqual(a.hash, b.hash)
        self.assertEqual(len(a.engine.fac.violations), 0)             # 预约越界 0
        self.assertEqual(a.engine.stat['ps'], sum(len(p.trail) for p in a.engine.people))   # 每个决定都落了轨迹
        print('\n[慢测试] 300 僧 360 日：每次决策 %.1f 微秒，共 %d 次' % (
            a.engine.elapsed / a.engine.stat['ps'] * 1e6, a.engine.stat['ps']))


class SourceRules(unittest.TestCase):
    """ARCHITECTURE 第 0 节：禁 random、墙钟、对 str 的内置 hash()；tianl/npc 里没有魔数大表。"""

    def test_no_forbidden_apis(self):
        bad = re.compile(r'(^|\s)(import random|from random)|random\.|time\.time\(|datetime|[^_.\w]hash\(|\bid\(')
        for f in sorted(NPC_SRC.glob('*.py')):
            for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
                code = line.split('#')[0]
                self.assertIsNone(bad.search(code), '%s:%d: %s' % (f.name, n, line))

    def test_no_semantic_numbers_outside_spec_and_scenarios(self):
        """spec.py 与 scenarios.py 之外，数值字面量只能是下标/计数用的 0 1 2 3，或模块级的具名常量（UPPER_CASE = …）。
        所以引擎里没有藏着的参数：要调一个数，只能去 SiteSpec 或场景。"""
        const = re.compile(r'^_?[A-Z][A-Z0-9_]*$')
        for f in sorted(NPC_SRC.glob('*.py')):
            if f.name in ('spec.py', 'scenarios.py'):
                continue
            tree = ast.parse(f.read_text(encoding='utf-8'))
            named = set()
            for st in tree.body:
                if isinstance(st, ast.Assign) and all(isinstance(t, ast.Name) and const.match(t.id) for t in st.targets):
                    named.update(id(n) for n in ast.walk(st))
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool) \
                        and id(n) not in named:
                    self.assertIn(n.value, (0, 1, 2, 3), '%s:%d 有未命名的数值常数 %r' % (f.name, n.lineno, n.value))

    def test_wall_clock_only_for_reporting(self):
        users = [f.name for f in sorted(NPC_SRC.glob('*.py')) if 'perf_counter' in f.read_text(encoding='utf-8')]
        self.assertEqual(users, ['engine.py'])

    def test_every_module_in_the_plan_exists(self):
        for name in ('spec model stack needs facilities freechoice jobs perception rumor norms opinion mood engine '
                     'scenarios life lod controller persist').split():
            self.assertTrue((NPC_SRC / (name + '.py')).exists(), name)
        import importlib
        for name in ('life', 'lod', 'controller', 'persist'):
            mod = importlib.import_module('tianl.npc.' + name)          # 空壳必须能 import，且带 docstring
            self.assertTrue(mod.__doc__ and '空壳' in mod.__doc__, name)


if __name__ == '__main__':
    unittest.main()
