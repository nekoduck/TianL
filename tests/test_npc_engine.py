"""tianl/npc 的接口与性质测试：Host 边界、rng 注入、查询 API、ix/pid、观察者无关、源码规矩。
（与原型的数字、哈希比对在 test_npc_proto.py；与原型常量、逐步差分在 test_npc_spec.py。）
"""
import ast
import dataclasses
import hashlib
import os
import re
import unittest
from collections import Counter
from pathlib import Path

from tianl.core import cal, rnd, rnd_b2
from tianl.npc import NpcEngine, PersonSpec, ProtoRun, Script, StandaloneHost, proto60_spec
from tianl.npc import events as E
from tianl.npc.handlers import GATES
from tianl.npc.host import CmdResult, Event, Host
from tianl.npc.model import FIELD_MASK, GAP, Symbols, Trail, pack, unpack
from tianl.npc.model import Case
from tianl.npc.spec import A_GUARD, A_MARTIAL, A_STROLL, L_FREE, L_SLACK, AdSpec, NeedTerm, SpecError
from tianl.npc.scenarios import PROTO_SEED, gossip_script, proto60_roster
from tests.test_npc_support import with_when

BASE_HASH = 'e8f8209eeb8ca94a'
NPC_SRC = Path(__file__).resolve().parent.parent / 'tianl' / 'npc'


def base_run(**kw):
    g = ProtoRun().common
    kw.setdefault('script', gossip_script(g))
    return ProtoRun(**kw).run()


_SHARED = {}


def shared_run(seed=PROTO_SEED, days=30, gossip=False):
    """只读用的运行结果，整个模块里同样的（种子、日数、脚本）只跑一次。凡是会改引擎的测试
    （加人、设观察者、换 Host、改规格）一律不要用它，各自 ProtoRun 一份。"""
    key = (seed, days, gossip)
    if key not in _SHARED:
        kw = {'script': gossip_script(ProtoRun().common)} if gossip else {}
        _SHARED[key] = ProtoRun(seed=seed, days=days, **kw).run()
    return _SHARED[key]


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
        ref = shared_run(gossip=True).engine
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
        cls.world = shared_run(gossip=True)
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
            eng = shared_run(seed, 90).engine
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
        x = shared_run(days=90)
        eng = x.engine
        self.assertEqual([c['sanction'] for c in eng.cases() if c['sanction']],
                         ['罚跪香三日', '杖责并禁闭二日', '禁闭五日', '迁单出寺'])    # 四级阶梯各走一遍
        self.assertEqual(eng.people[x.glutton.ix].gone, 83)                     # 计划 8.5：第 83 日迁单出寺

    def test_explain_says_where_a_departed_monk_went(self):
        x = shared_run(days=90)
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

    def test_profile_id_is_a_read_only_alias_of_ix(self):
        """验收脚本里写 `common[8].id`（原型的档案叫 id）：它就是 ix，且只读，所以不会与 ix 不一致。"""
        g = ProtoRun().common
        self.assertTrue(all(p.id == p.ix for p in g))
        with self.assertRaises(AttributeError):
            g[0].id = 5
        a = ProtoRun(script={'gossip': (6, g[8].id, g[9].id)}).run().hash         # 任务书里的写法，逐字
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
        by_dom = with_when(sp, 'uposatha', days=None, doms=(1, 15))        # 布萨的日子从“模拟日序号”改成“历法的月内日”
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

    def test_job_priority_is_a_field(self):
        sp = proto60_spec()
        eng = ProtoRun().engine
        eng.jobs.publish()
        self.assertEqual([r.name for r in eng.jobs.rows][:5], ['挑水', '打柴', '舂米', '菜园帮工', '洒扫'])
        swept = tuple(dataclasses.replace(j, prio=0) if j.name == '洒扫' else j for j in sp.jobs.board)
        spec = dataclasses.replace(sp, jobs=dataclasses.replace(sp.jobs, board=swept))
        eng2 = ProtoRun(spec=spec).engine
        eng2.jobs.publish()
        self.assertEqual([r.place for r in eng2.jobs.rows][:4], ['hall', 'zen', 'clo', 'dorm1'])   # 洒扫提到最前，同级保持原次序
        self.assertEqual([r.name for r in eng2.jobs.rows][4:], ['挑水', '打柴', '舂米', '菜园帮工'])
        self.assertNotEqual(ProtoRun(days=3).run().hash, ProtoRun(spec=spec, days=3).run().hash)

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

    def test_free_time_needs_something_to_choose_from(self):
        sp = proto60_spec()
        problems = dataclasses.replace(sp, ads=()).validate()
        self.assertTrue(any('ads' in p for p in problems), problems)
        problems = dataclasses.replace(sp, free=dataclasses.replace(sp.free, top_k=0)).validate()
        self.assertTrue(any('top_k' in p for p in problems), problems)
        with self.assertRaises(SpecError):
            NpcEngine(dataclasses.replace(sp, ads=()), StandaloneHost(1, rnd_b2))

    def test_via_labels_come_from_the_spec(self):
        sp = proto60_spec()
        renamed = dataclasses.replace(sp, cases=dataclasses.replace(sp.cases, via_report='据举报', via_confess='自认'))
        x = ProtoRun(spec=renamed, days=90, seed=4).run()
        vias = {c['via'] for c in x.engine.cases() if c['via']}
        self.assertEqual(vias, {'据举报', '自认'})
        y = shared_run(4, 90)                                                # 换了标签，行为不变
        self.assertEqual(x.hash, y.hash)


class FreeChoiceFallback(unittest.TestCase):
    """自由时段没有任何得分为正的广告：原型在 top[0] 处 IndexError；移植版改为散步并记 free_none。"""

    def stroll_only(self, run):
        eng, sp = run.engine, run.engine.spec
        n = 0
        for p in eng.people:
            for day in range(1, run.days + 1):
                for slot in range(12):
                    place, act, layer, reason = eng.where(p.ix, day, slot)
                    if layer in (L_FREE, L_SLACK):
                        n += 1
                        self.assertEqual((place, act, reason), (sp.free.stroll_place, A_STROLL, sp.free.stroll_label))
        return n

    def test_every_ad_scores_nonpositive(self):
        sp = proto60_spec()
        sad = AdSpec(A_MARTIAL, 'yard', '习武', (NeedTerm('e', -3, ()),), None, None, None, {})      # 迫切度乘负增量：恒不为正
        spec = dataclasses.replace(sp, ads=(sad,))
        self.assertEqual(spec.validate(), [])
        run = ProtoRun(spec=spec, days=6).run()
        n = self.stroll_only(run)
        self.assertGreater(n, 0)
        self.assertEqual(run.engine.stat['free_none'], n)               # 每个自由时段的决定都是这一支
        self.assertEqual(run.engine.stat['full'], 0)

    def test_no_facility_open(self):
        run = ProtoRun(days=4)
        run.engine.fac.open_ads = lambda p, day, slot: []               # 设施都没开
        run.run()
        n = self.stroll_only(run)
        self.assertGreater(n, 0)
        self.assertEqual(run.engine.stat['free_none'], n)

    def test_ordinary_world_never_takes_the_fallback(self):
        eng = shared_run(gossip=True).engine
        self.assertEqual(eng.stat['free_none'], 0)
        self.assertNotIn('free_none', {k for k, v in eng.stat.items() if v})


def build(spec, keep=lambda ps: True, n=60, seed=PROTO_SEED):
    """按名册建一个引擎（不用 ProtoRun，所以名册可以缺人：只留岗位僧、只留清众、去掉藏主……）；keep 决定留谁。"""
    eng = NpcEngine(spec, StandaloneHost(seed, rnd_b2))
    for ps in proto60_roster(spec, n):
        if keep(ps):
            eng.add_person(ps)
    return eng


def run_days(eng, days):
    for day in range(1, days + 1):
        eng.run_day(day)
    return eng


def decisions(eng, days):
    for p in eng.people:
        for day in range(1, days + 1):
            for slot in range(12):
                w = eng.where(p.ix, day, slot)
                if w:
                    yield p, day, slot, w


class DefensiveBranches(unittest.TestCase):
    """基准世界与所有对照场景都走不到的三处防御性分支。原型在这几处要么 IndexError、要么根本不可达，
    所以没法与原型逐项比对；这里直接造出会走到它们的世界，断言行为合理并且不崩、不越界。"""

    def test_every_candidate_full_falls_back_to_stroll(self):
        """freechoice：能选的广告都满员 → 去廊下散步（不是 free_none：那是“没有任何正分广告”）。
        原型的“小憩”广告落在本人床位、不记容量，永远有空，所以这一支在原型世界里不可达。"""
        sp = proto60_spec()
        only = AdSpec(A_MARTIAL, 'yard', '习武', (NeedTerm('a', 6, ()),), None, None, None, {})      # 迫切度乘正增量：恒为正
        for cap in (2, 0):
            spec = dataclasses.replace(sp, ads=(only,), capacity={**sp.capacity, 'yard': cap})
            self.assertEqual(spec.validate(), [])
            eng = run_days(build(spec), 6)
            fr = spec.free
            n_free = n_yard = crowded = 0
            for day in range(1, 7):
                for slot in range(12):
                    here = {}
                    for p in eng.people:
                        w = eng.where(p.ix, day, slot)
                        if w and w[2] in (L_FREE, L_SLACK):
                            self.assertIn((w[0], w[1]), ((only.place, A_MARTIAL), (fr.stroll_place, fr.stroll_act)))
                            here[(w[0], w[1])] = here.get((w[0], w[1]), 0) + 1
                    n_free += sum(here.values())
                    n_yard += here.get(('yard', A_MARTIAL), 0)
                    crowded += here.get(('yard', A_MARTIAL), 0) == cap and here.get((fr.stroll_place, fr.stroll_act), 0) > 0
            self.assertGreater(n_free, 100)
            self.assertEqual(eng.stat['free_none'], 0)                  # 有正分广告，只是满了
            self.assertGreater(eng.stat['full'], 0)
            self.assertEqual(eng.fac.violations, [])                     # 占用从不超过容量
            if cap:
                self.assertGreater(n_yard, 0)
                self.assertGreater(crowded, 0)                           # 练武场坐满、后来的人散步：这一支走到了
            else:
                self.assertEqual(n_yard, 0)                              # 一个座位也没有：自由时段全都散步

    def test_library_gate_needs_a_keeper(self):
        """handlers.lib_open：没有藏主，藏经阁就不开（原型此处 IndexError）。"""
        sp = proto60_spec()
        ad = next(a for a in sp.ads if a.gate == 'lib_open')
        keeper, open_slots = ad.gate_params['office'], ad.gate_params['slots']       # 管阁的岗位与开阁时辰在交互的 admission 里
        control = run_days(build(sp), 15)
        empty = run_days(build(sp, lambda ps: ps.office != keeper), 15)
        self.assertEqual(empty.by.get(keeper), None)
        free_reads = lambda e: sum(1 for p, d, s, w in decisions(e, 15)
                                   if w[0] == 'lib' and w[2] in (L_FREE, L_SLACK))
        self.assertGreater(free_reads(control), 0)
        self.assertEqual(free_reads(empty), 0)
        slot = open_slots[0]
        for slot_ in range(12):
            self.assertFalse(GATES['lib_open'](empty, empty.people[0], 3, slot_, ad.gate_params))
            self.assertEqual(GATES['lib_open'](control, control.people[0], 3, slot_, ad.gate_params), slot_ in open_slots)
        zhu = control.people[control.by[keeper][0]]                      # 藏主病了：同样不开
        zhu.ill = 3
        self.assertFalse(GATES['lib_open'](control, control.people[0], 3, slot, ad.gate_params))
        self.assertTrue(GATES['lib_open'](control, control.people[0], 4, slot, ad.gate_params))

    def test_a_temple_without_common_monks_has_no_gate_guards(self):
        """engine.guards：清众为空 → 无人值守山门（不除以零）。只有岗位僧的寺照样能跑。"""
        sp = proto60_spec()
        eng = build(sp, lambda ps: ps.office is not None)
        self.assertEqual((eng.common, eng.guards(1), eng.guards(2), eng.guards(99)), ([], (), (), ()))
        run_days(eng, 8)
        self.assertGreater(eng.stat['ps'], 1000)
        self.assertFalse(any(w[1] == A_GUARD for p, d, s, w in decisions(eng, 8)))
        self.assertTrue(all(w[2] and w[3] for p, d, s, w in decisions(eng, 8)))      # 照样每个决定都说得清

    def test_a_temple_without_office_holders_runs(self):
        """只有清众：没有僧值、戒律院、维那、典座……各处按“岗位空缺”处理，不崩，也不会有人受处分。"""
        sp = proto60_spec()
        eng = build(sp, lambda ps: ps.office is None)
        self.assertEqual((eng.night_patroller(3), eng.court_staff(), eng.court_open(3)), (None, [], False))
        run_days(eng, 8)
        self.assertGreater(eng.stat['ps'], 1000)
        self.assertEqual((eng.stat['sanction'], eng.stat['absence']), (0, 0))            # 没有维那点名、没有戒律院
        self.assertTrue(all(w[2] and w[3] for p, d, s, w in decisions(eng, 8)))


class PlaceCodesAreKeys(unittest.TestCase):
    """原型的场所短码（hall、kit、dorm1……）不只是名字：它们进随机数键（巡寮抽签的键里有场所码）与基线哈希
    （每个决定一行，含场所码）。defs 驱动之后，原型场景的 place 定义的 code 就是这些短码（defs/space/proto60.toml）——
    原型回归保持原样；换成 SH_HALL 之类就是另一个世界、另一份基线（docs/NPC_ENGINE.md 第 9 节第 14 条、第 10 节）。这里把事实钉住。"""

    def test_roam_draws_are_keyed_by_the_place_code(self):
        keys = []

        def rec(*k):
            keys.append(k)
            return rnd_b2(*k)
        sp = proto60_spec()
        ProtoRun(host=StandaloneHost(PROTO_SEED, rec), days=4).run()
        roam = [k for k in keys if k[1] == 'roam']
        self.assertGreater(len(roam), 50)
        self.assertEqual({k[4] for k in roam}, set(sp.roam))                # 键 = (种子, 'roam', 日, 时辰, 场所码)
        self.assertTrue(set(sp.roam) <= set(sp.places))

    def test_baseline_hash_lines_carry_the_place_code(self):
        class Spy:
            def __init__(self):
                self.h, self.lines = hashlib.sha256(), []

            def update(self, b):
                self.lines.append(b.decode())
                self.h.update(b)

            def copy(self):
                return self.h.copy()
        run = ProtoRun(days=2)
        run.engine._h = Spy()
        run.run()
        sp = run.engine.spec
        lines = run.engine._h.lines
        self.assertEqual(len(lines), 2 * 12 * 60)
        codes = {ln.rstrip(';').split(',')[3] for ln in lines}
        self.assertTrue(codes <= set(sp.places) and {'hall', 'kit', 'dorm1'} <= codes)
        renamed = ''.join(ln.replace(',hall,', ',SH_HALL,') for ln in lines)       # 换一个场所码，摘要就不是同一个
        self.assertNotEqual(hashlib.sha256(renamed.encode()).hexdigest(), hashlib.sha256(''.join(lines).encode()).hexdigest())

    def test_display_names_are_not_part_of_the_baseline(self):
        """场所的显示名随便改：哈希不变（名字只给 explain 的 place_name 用）；动不得的是钥匙（code）。"""
        sp = proto60_spec()
        renamed = dataclasses.replace(sp, places={k: '甲' + k for k in sp.places})
        self.assertEqual(ProtoRun(spec=renamed, days=3).run().hash, ProtoRun(days=3).run().hash)


class SanctionOrder(unittest.TestCase):
    def test_accusers_are_visited_in_ix_order_not_set_order(self):
        """处分时对指认人按 ix 升序加“告发”修正项。原型遍历 set，次序是 CPython 的实现细节
        （{3, 8, 17, 42} 的遍历次序是 8, 17, 42, 3）；移植版排了序，mods 字典的键次序因此确定。"""
        eng = ProtoRun().engine
        self.assertEqual(list({3, 8, 17, 42}), [8, 17, 42, 3])           # 前提：set 次序确实不是升序
        off = 5
        e = eng.emit(E.FOOD_THEFT, off, 'kit', [], 1, 1, why='测试')
        case = Case(e.id, 1, (), eng.spec.cases.open)
        case.acc = {3, 8, 17, 42}
        case.rep = 1
        eng.norms.cases[e.id] = case
        eng.norms.sanction(e.id, case, 2, eng.spec.cases.via_report)
        self.assertEqual(list(eng.opinions.mods), [(off, 3), (off, 8), (off, 17), (off, 42)])
        for k, v in eng.opinions.mods.items():
            self.assertEqual(len(v), 1)
            self.assertEqual(v[0][2], eng.spec.mods[eng.spec.cases.accuse_mod].kind)

    def test_mods_are_ordered_the_same_way_whatever_order_the_accusers_arrived_in(self):
        orders = []
        for arrival in ((42, 3, 17, 8), (8, 17, 3, 42), (3, 8, 17, 42)):
            eng = ProtoRun().engine
            e = eng.emit(E.FOOD_THEFT, 5, 'kit', [], 1, 1, why='测试')
            case = Case(e.id, 1, (), eng.spec.cases.open)
            for a in arrival:
                case.acc.add(a)
            case.rep = 1
            eng.norms.sanction(e.id, case, 2, eng.spec.cases.via_report)
            orders.append(list(eng.opinions.mods))
        self.assertEqual(orders[0], orders[1])
        self.assertEqual(orders[1], orders[2])


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

    @staticmethod
    def _parents(tree):
        parent = {}
        for n in ast.walk(tree):
            for c in ast.iter_child_nodes(n):
                parent[c] = n
        return parent

    @staticmethod
    def _structural(n, parent):
        """数值字面量 n 是否只是结构用的：下标/元组位置、计数、初值、±1 偏移、max/min 的保底、与 0 或 1 比较。
        其余一律不放行——包括 0 1 2 3 里的 2 和 3（只能做下标）、乘除里的 0、赋给字段的 1（例如默认的时辰）。"""
        v, node, p = n.value, n, parent[n]
        if isinstance(p, ast.UnaryOp):                              # [-1] 之类
            node, p = p, parent[p]
        if isinstance(p, ast.Subscript) and p.slice is node:
            return v in (0, 1, 2, 3)
        if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == 'itemgetter':
            return v in (0, 1, 2, 3)                                # itemgetter(2)：同样是元组位置
        if v == 0:
            return not (isinstance(p, ast.BinOp) and isinstance(p.op, (ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)))
        if v == 1:
            if isinstance(p, ast.AugAssign):
                return isinstance(p.op, (ast.Add, ast.Sub))
            if isinstance(p, ast.GeneratorExp):                     # sum(1 for …)：计数
                return p.elt is node
            if isinstance(p, ast.BinOp):
                return isinstance(p.op, (ast.Add, ast.Sub))
            if isinstance(p, ast.Call):
                return isinstance(p.func, ast.Name) and p.func.id in ('max', 'min')
            if isinstance(p, ast.Compare):
                return all(isinstance(op, (ast.Eq, ast.NotEq)) for op in p.ops)
        return False

    @staticmethod
    def _const_target(t, const):
        """赋值目标是具名常量（UPPER_CASE），或一组具名常量的元组（A, B = …）。"""
        if isinstance(t, ast.Tuple):
            return all(isinstance(e, ast.Name) and const.match(e.id) for e in t.elts)
        return isinstance(t, ast.Name) and bool(const.match(t.id))

    @classmethod
    def _bad_numbers(cls, source, params_ok=False):
        """源码里不合规矩的数值字面量：[(行号, 值)]。合规 = 模块级具名常量（UPPER_CASE = …），或结构用的 0/1/2/3（见 _structural）；
        params_ok=True（handlers.py）时，登记表里 Param(…) 调用的参数（参数的默认值与取值范围）也合规——那是处理器默认参数，
        原型场景的数只许写在 defs 里，处理器的默认值是仅有的例外（任务书：“只允许在 handlers 的默认参数与 defs 里”）。"""
        const = re.compile(r'^_?[A-Z][A-Z0-9_]*$')
        tree = ast.parse(source)
        parent = cls._parents(tree)
        ok = set()
        for st in tree.body:
            if isinstance(st, ast.Assign) and all(cls._const_target(t, const) for t in st.targets):
                ok.update(id(n) for n in ast.walk(st))
        if params_ok:
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'Param':
                    ok.update(id(x) for x in ast.walk(n))
        return [(n.lineno, n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
                and id(n) not in ok and not cls._structural(n, parent)]

    def test_no_semantic_numbers_anywhere_in_the_engine(self):
        """tianl/npc 里的每个模块（现在连 spec.py、scenarios.py 也算：原型场景的数都在 defs 里，代码里一个不剩），
        数值字面量只能是模块级的具名常量（UPPER_CASE = …），或结构用的 0/1/2/3（判定见 _structural：下标、计数、初值、±1 偏移……；
        2、3 只许做下标）；handlers.py 另许 Param(…) 的参数（处理器的默认值与取值范围）。所以引擎里没有藏着的参数：
        要调一个数，只能去 defs（或处理器的默认参数）。"""
        for f in sorted(NPC_SRC.glob('*.py')):
            bad = self._bad_numbers(f.read_text(encoding='utf-8'), params_ok=f.name == 'handlers.py')
            self.assertEqual(bad, [], '%s 有未命名的数值常数（行号, 值）：%s（不是下标/计数/初值/±1 偏移）' % (f.name, bad))

    def test_the_param_default_exemption_is_narrow(self):
        """handlers 默认参数的豁免只给 Param(…) 调用：处理器函数体里的裸数字、别的调用里的数字，照旧不放行。"""
        self.assertEqual(self._bad_numbers("p = Param('k', 'float', default=0.9, lo=0, hi=1)", params_ok=True), [])
        self.assertEqual(self._bad_numbers("def f(x):\n    return x * 0.9", params_ok=True), [(2, 0.9)])
        self.assertEqual(self._bad_numbers("g(k=0.9)", params_ok=True), [(1, 0.9)])
        self.assertEqual(self._bad_numbers("p = Param('k', 'float', default=0.9)", params_ok=False), [(1, 0.9)])

    def test_the_structural_rule_has_teeth(self):
        """上面那条规则自己要能抓到违规：对一小段有毒代码逐条验证。"""
        bad = ['x = y * 2', 'x = g(2)', 'x = y / 3', 'x = 0 * y', 'x = f(y, 2)', 'class A:\n    slot: int = 1', 'x = y + 2', 'x = y > 2',
               'x = y[:2]', 'x = y ** 2', 'x = max(y, 2)', 'x = y.get(k, 1)']
        good = ['x = y[2]', 'x = itemgetter(2)', 'x = y[-1]', 'x += 1', 'x = 0', 'x = (0, 0.0)', 'x = y + 1', 'x = y - 1', 'x = 1 - y',
                'x = sum(1 for a in y)', 'x = max(1, y)', 'x = y > 0', 'x = y.get(k, 0)', 'x = y == 1.0']
        for code, want in [(c, False) for c in bad] + [(c, True) for c in good]:
            tree = ast.parse(code)
            parent = self._parents(tree)
            nums = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                    and not isinstance(n.value, bool)]
            got = all(self._structural(n, parent) for n in nums)
            self.assertEqual(got, want, code)

    def test_no_business_vocabulary_in_engine_code(self):
        """引擎代码里不出现规格里的业务词：场所（名与代码）、岗位、中文标签（活动、原因、层、案卷状态……）。
        这些只能在 defs 里写（spec.py 里的层标签 L_*、活动代码 A_*、events.py 里事件种类的中文渲染是引擎认识的结构性标识，例外）；
        引擎引用的是字段。defsload.py 与 handlers.py 是“定义格式”的一部分，字段名、角色名都是 ASCII 的英文词，难免与某个场所码同名
        （如 office、court），所以对它们只查中文的业务词。"""
        from tianl.npc.defsload import ROLES
        vocab = set()

        def walk(o):
            if dataclasses.is_dataclass(o) and not isinstance(o, type):
                for fld in dataclasses.fields(o):
                    walk(getattr(o, fld.name))
            elif isinstance(o, dict):
                for k, v in o.items():
                    walk(k)
                    walk(v)
            elif isinstance(o, (list, tuple, set, frozenset)):
                for v in o:
                    walk(v)
            elif isinstance(o, str) and re.search('[\u3400-\u9fff]', o):
                vocab.add(o)
        sp = proto60_spec()
        walk(sp)
        codes = set(sp.places) | {o.name for o in sp.offices}          # 场所代码（hall、kit……）与岗位名也算业务词
        vocab.update(codes)
        self.assertGreater(len(vocab), 120)
        schema_modules = ('defsload.py', 'handlers.py')
        for f in sorted(NPC_SRC.glob('*.py')):
            if f.name in ('spec.py', 'events.py'):
                continue
            words = {w for w in vocab if re.search('[\u3400-\u9fff]', w)} if f.name in schema_modules else vocab
            tree = ast.parse(f.read_text(encoding='utf-8'))
            slots = {id(n) for st in ast.walk(tree) if isinstance(st, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id in ('__slots__', 'ROLES') for t in st.targets) for n in ast.walk(st)}
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in slots:     # __slots__ 是字段名，ROLES 是角色名，不是业务词
                    self.assertNotIn(n.value, words, '%s:%d 把规格里的业务词 %r 写进了引擎代码' % (f.name, n.lineno, n.value))
        self.assertTrue(set(ROLES) & codes)                           # 前提：角色名里确有与场所码同名的（court、gate……），所以上面要区别对待

    def test_wall_clock_only_for_reporting(self):
        users = [f.name for f in sorted(NPC_SRC.glob('*.py')) if 'perf_counter' in f.read_text(encoding='utf-8')]
        self.assertEqual(users, ['engine.py'])

    def test_every_module_in_the_plan_exists(self):
        for name in ('spec model stack needs facilities freechoice jobs perception rumor norms opinion mood engine '
                     'scenarios life lod controller persist handlers defsload').split():
            self.assertTrue((NPC_SRC / (name + '.py')).exists(), name)
        import importlib
        for name in ('life', 'lod', 'controller', 'persist'):
            mod = importlib.import_module('tianl.npc.' + name)          # 空壳（只有钩子）必须能 import，且带 docstring
            self.assertTrue(mod.__doc__ and '空壳' in mod.__doc__, name)


if __name__ == '__main__':
    unittest.main()
