"""B1 验收：v0.2 少林寺内核（tianl.kernel + defs/）与原型逐位相同。

  python3 -m unittest tests.test_b1_kernel                 # 默认（约 25 秒）
  TIANL_SLOW=1 python3 -m unittest tests.test_b1_kernel    # 再加十年基准、六个种子、E2/E2b/E5/E6、人物与独有物测试

“日志”指 reference/logs/shaolin_run_log.txt（原型跑出来的输出）；日志逐行复现由 tools/shaolin_regress.py 产出。
"""
import ast
import contextlib
import importlib.util
import io
import json
import os
import re
import unittest
from pathlib import Path

from tests.test_b1_common import BASELINE_DAYS, REF_HASH, baseline_world
from tianl.core.calendar import SLOTS_PER_DAY, YEAR
from tianl.kernel import World, year_report

ROOT = Path(__file__).resolve().parents[1]
SLOW = os.environ.get('TIANL_SLOW') == '1'
LOG = (ROOT / 'reference' / 'logs' / 'shaolin_run_log.txt').read_text(encoding='utf-8')


def _load_tool():
    spec = importlib.util.spec_from_file_location('shaolin_regress', ROOT / 'tools' / 'shaolin_regress.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


RG = _load_tool()


def norm(text):
    return re.sub(r'用时 [0-9.]+ 秒', '用时 X 秒', text)


def captured(fn, *args):
    """跑 fn(*args)，返回 (打印出来的文字, 返回值)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = fn(*args)
    return buf.getvalue(), r


def log_section(label_prefix):
    """日志里以“===== label_prefix…”开头的那一段（到下一个“=====”标题前）。"""
    parts = re.split(r'(?m)^(?=\n?===== )', LOG)
    for p in parts:
        if p.lstrip('\n').startswith('===== ' + label_prefix):
            return p
    raise KeyError(label_prefix)


YEAR_RE = re.compile(r"第(\d+)年: 余钱 (-?\d+)->(-?\d+) 贯 \| 收 ([\d.]+) 支 ([\d.]+) \| 寺库最低 ([\d.]+) 日, 总量最低 ([\d.]+) 日 "
                     r"\| 档位日数 (\{.*?\}) \| 封路 (\d+) 日 \| 订单 (\{.*?\}) 按期 (\S+) \| 事件 (\d+) \| 僧 (\d+)")
CUM_RE = re.compile(r"累计: 断炊日 (\d+) \| 缺货日 (.*?) \| 上报 (\d+) \| 佃户借粮 (\d+) 次 赈济 (\d+) 次 \| 农户挨饿 (\d+) 户日 \| 离乡 (\d+) 户 "
                    r"\| 僧人圆寂 (\d+) 离寺 (\d+)")


class LogNumbers:
    """把日志里的数字（年度行、累计行）与世界里算出来的值逐项比对。"""

    def check_years(self, text, w):
        rows = YEAR_RE.findall(text)
        self.assertTrue(rows, '日志段里没有年度行')
        for y, c0, c1, inc, spd, cmin, tmin, tiers, closed, orders, ontime, events, head in rows:
            r = year_report(w, int(y))
            self.assertEqual((f"{r['cash_start']:.0f}", f"{r['cash_end']:.0f}"), (c0, c1), f'第{y}年 余钱')
            self.assertEqual((r['income'], r['spend']), (float(inc), float(spd)), f'第{y}年 收支')
            self.assertEqual((r['cover_min'], r['total_min']), (float(cmin), float(tmin)), f'第{y}年 库存最低')
            self.assertEqual(r['tier_days'], ast.literal_eval(tiers), f'第{y}年 档位日数')
            self.assertEqual(r['closed_days'], int(closed), f'第{y}年 封路日数')
            self.assertEqual(r['orders'], ast.literal_eval(orders), f'第{y}年 订单')
            self.assertEqual(r['ontime_rate'], None if ontime == 'None' else float(ontime), f'第{y}年 按期率')
            self.assertEqual(r['events'], int(events), f'第{y}年 事件数')
            self.assertEqual(r['head_end'], int(head), f'第{y}年 僧')
        return len(rows)

    def check_cumulative(self, text, w):
        m = CUM_RE.search(text)
        self.assertIsNotNone(m, '日志段里没有累计行')
        meal, short, esc, borrow, relief, hunger, left, deaths, away = m.groups()
        c = w.cnt
        self.assertEqual([c['meal_short'], c['escalated'], c['hh_borrow'], c['relief'], c['hunger_days'], c['hh_left'], c['deaths'], c['monks_left']],
                         [int(meal), int(esc), int(borrow), int(relief), int(hunger), int(left), int(deaths), int(away)])
        by_name = {g.name: k for k, g in w.G.items()}
        logged = {by_name[n]: int(v) for n, v in re.findall(r'(\S+?)(\d+)(?:\s|$)', short)}
        mine = {k: c['short_' + k] for k in w.G if c['short_' + k]}
        self.assertEqual(mine, logged, '缺货日')

    def check_section(self, label, w):
        text = log_section(label)
        self.check_years(text, w)
        self.check_cumulative(text, w)
        return text


class BaselineTests(unittest.TestCase, LogNumbers):
    @classmethod
    def setUpClass(cls):
        cls.w = baseline_world()                       # 进程内共享、只读
        cls.w2 = split_phase_world()[0]                # 另跑一遍（分步走法、接着空引擎），验证“重跑一致”

    def test_hash_matches_prototype(self):
        self.assertEqual(self.w.state_hash(), REF_HASH)

    def test_rerun_identical_and_no_violations(self):
        self.assertEqual(self.w2.state_hash(), self.w.state_hash())
        self.assertEqual(self.w.viol, [])

    def test_baseline_numbers_match_log(self):
        text = log_section('基准')
        self.assertIn(REF_HASH, text)
        self.assertIn('重跑一致=True', text)
        self.assertIn('不变量违规: 0', text)
        self.assertEqual(self.check_years(text, self.w), 3)
        self.check_cumulative(text, self.w)
        # 农户期末、边界与铺户余额
        hh = {k: (n, round(c / 1000, 1), round(g / 1000, 1)) for k, n, c, g, _ in self.w.x(
            f"SELECT h.kind, COUNT(*), AVG(a.balance), AVG(s.qty), AVG(h.members) FROM household h JOIN account a ON a.id=h.id "
            f"JOIN stock s ON s.owner=h.id AND s.commodity='{self.w.cm.staple}' WHERE h.status='在' GROUP BY h.kind")}
        for k, n, c, g in re.findall(r'(\w+) (\d+)户 均钱([\d.]+)贯 均粮([\d.]+)石', text):
            self.assertEqual(hh[k], (int(n), float(c), float(g)), k)
        bal = dict(self.w.x('SELECT id, balance FROM account'))
        for k, v in re.findall(r'(\w+)=(-?\d+)', text.split('边界与铺户余额(贯):')[1].splitlines()[0]):
            self.assertEqual(round(bal[k] / 1000), int(v), k)

    def test_baseline_section_text_matches_log(self):
        out, _ = captured(RG.report_baseline, self.w, 0.0, self.w.state_hash(), self.w2.state_hash())
        self.assertIn(norm(out), norm(LOG))

    def test_econ_hash_is_economy_only(self):
        w = World().run(30)
        e0, s0 = w.econ_hash(), w.state_hash()
        w.x("INSERT INTO event_log(day,type) VALUES(0,'X')")
        self.assertEqual(w.econ_hash(), e0)               # 事件表不在经济表里
        self.assertNotEqual(w.state_hash(), s0)
        w.x('UPDATE account SET balance=balance+1 WHERE id=?', (w.ac.org,))
        self.assertNotEqual(w.econ_hash(), e0)


class ExperimentTests(unittest.TestCase, LogNumbers):
    def test_e1_blockade_matches_log(self):
        out, w = captured(RG.e1)
        self.assertIn(norm(out), norm(LOG))                # 全文（年度行、累计行、窗口行、因果追溯、日报）逐字出现在日志里
        text = self.check_section('E1', w)                 # 数字与世界里算出来的逐项一致
        start = 2 * YEAR + 330
        win = [s for s in w.series if start <= s['day'] <= start + 70]
        m = re.search(r'寺库最低 ([\d.]+) 日 \| 首次缺货在封路第 (\d+) 日 \| 同时受阻订单最多 (\d+) 张 \| 复通后 (\d+) 日内全部补齐 \| 事件 (\{.*\})', text)
        reopen = start + 45
        self.assertEqual(round(min(s['cover'] for s in win), 1), float(m[1]))
        self.assertEqual(next(s['day'] - start for s in win if s['short'] > 0), int(m[2]))
        self.assertEqual(max(s['blocked'] for s in win), int(m[3]))
        self.assertEqual(next(s['day'] - reopen for s in win if s['day'] >= reopen and s['blocked'] == 0 and s['short'] == 0), int(m[4]))
        self.assertEqual(ast.literal_eval(m[5]), RG.window(w, start, start + 60, ('ORDER_BLOCKED', 'ORDER_FAILED', 'ORDER_RENEWED',
                                                                                'ORDER_ESCALATED', 'SHORTAGE', 'FORAGE', 'MEAL_SHORT')))
        # 因果追溯：缺货 <- 订单受阻 <- 封路
        chain = w.why(w.x("SELECT id FROM event_log WHERE type='SHORTAGE' AND day>=? AND cause IS NOT NULL ORDER BY id LIMIT 1", (start,)).fetchone()[0])
        self.assertEqual([c.split(' ')[1] for c in chain], ['SHORTAGE', 'ORDER_BLOCKED', 'ROAD_CLOSED'])
        for c in chain:
            self.assertIn(c, text)

    def test_e3_cook_leaves_matches_log(self):
        out, w = captured(RG.e3)
        self.assertIn(norm(out), norm(LOG))
        text = self.check_section('E3', w)
        win = RG.window(w, 2 * YEAR + 100, 2 * YEAR + 104, ('DEATH', 'ACTING', 'APPOINT', 'MEAL_SHORT'))
        self.assertEqual(win, {'ACTING': 1, 'APPOINT': 2, 'DEATH': 1})
        self.assertIn(str(win), text)

    @unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开')
    def test_slow_other_experiments_match_log(self):
        for fn, label in ((RG.e2, 'E2 '), (RG.e2b, 'E2b'), (RG.e5, 'E5'), (RG.e6, 'E6')):
            with self.subTest(label):
                out, w = captured(fn)
                self.assertIn(norm(out), norm(LOG))
                self.check_section(label, w)

    @unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开')
    def test_slow_ten_year_and_seeds_match_log(self):
        out, w = captured(RG.ten_year)
        self.assertIn(norm(out), norm(LOG))
        self.check_section('十年基准', w)
        out, _ = captured(RG.seeds)
        self.assertIn(norm(out), norm(LOG))
        self.assertEqual(w.viol, [])

    @unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开')
    def test_slow_people_and_unique_items_match_log(self):
        w = World().run(360 * 4)
        out, _ = captured(RG.people_tests, w)
        self.assertIn(norm(out), norm(LOG))


class StepTests(unittest.TestCase):
    def test_step_equals_split_phases(self):
        """未接引擎：step() 与 begin_day + 12 x run_slot + end_day 逐位相同（这里走 130 日，含第一次收录与第一场收成；整个基准的分步走法在下一条）。"""
        a = World().run(130)
        b = World()
        for _ in range(130):
            b.begin_day()
            for _ in range(SLOTS_PER_DAY): b.run_slot()
            b.end_day()
        self.assertEqual((b.day, b.slot), (130, 0))
        self.assertEqual(a.state_hash(), b.state_hash())
        self.assertEqual(a.econ_hash(), b.econ_hash())
        self.assertEqual(a.series, b.series)

    def test_split_phases_over_the_whole_baseline_equal_step(self):
        """整个基准（预热 1 年 + 3 年）用分步走法（并接着空引擎）跑一遍，与 step() 跑的基准逐位相同：哈希、经济表哈希、逐日序列。"""
        a, (b, _) = baseline_world(), split_phase_world()
        self.assertEqual((b.day, b.slot), (BASELINE_DAYS, 0))
        self.assertEqual(b.state_hash(), REF_HASH)
        self.assertEqual(a.state_hash(), b.state_hash())
        self.assertEqual(a.econ_hash(), b.econ_hash())
        self.assertEqual(a.series, b.series)

    def test_advance_equals_step_at_day_boundaries(self):
        a = World()
        b = World()
        for k in range(1, 7):
            a.run(1)
            b.advance(SLOTS_PER_DAY)
            self.assertEqual((a.day, a.slot), (b.day, b.slot))
            self.assertEqual(a.state_hash(), b.state_hash(), f'第 {k} 日末')

    def test_stop_mid_day_keeps_transaction_open_and_resumes_identically(self):
        ref = World().run(40)
        w = World()
        w.advance(SLOTS_PER_DAY * 3 + 5)                   # 第 3 日停在卯时边界
        self.assertEqual((w.day, w.slot), (3, 5))
        self.assertTrue(w.db.in_transaction, '日内停在时辰边界时事务保持打开')
        self.assertTrue(w.x("SELECT 1 FROM event_log WHERE day=3 AND type='MEALS'").fetchone(), '当日经济阶段已结算')
        w.advance(7)                                       # 走完这一日（自动 end_day）
        self.assertEqual((w.day, w.slot), (4, 0))
        self.assertFalse(w.db.in_transaction)
        w.advance(SLOTS_PER_DAY * 36)                      # 余下的日子
        self.assertEqual((w.day, w.slot), (40, 0))
        self.assertEqual(w.state_hash(), ref.state_hash())

    def test_step_finishes_a_started_day(self):
        ref = World().run(5)
        w = World()
        w.advance(SLOTS_PER_DAY * 2 + 9)
        w.step()                                           # 补完第 2 日
        self.assertEqual((w.day, w.slot), (3, 0))
        w.run(2)
        self.assertEqual(w.state_hash(), ref.state_hash())

    def test_misuse_is_rejected(self):
        w = World()
        with self.assertRaises(RuntimeError): w.run_slot()      # 没 begin_day
        with self.assertRaises(RuntimeError): w.end_day()
        w.begin_day()
        with self.assertRaises(RuntimeError): w.begin_day()
        for _ in range(SLOTS_PER_DAY): w.run_slot()
        with self.assertRaises(RuntimeError): w.run_slot()      # 十二时辰走完要先 end_day

    def test_end_day_refuses_an_unfinished_day(self):
        """日内直接 end_day 会让引擎漏掉剩下的 run_slot：必须拒绝，且拒绝之后世界毫发无损、能接着走。"""
        eng = StubEngine()
        w = World(engine=eng)
        w.begin_day()
        with self.assertRaises(RuntimeError): w.end_day()                       # 一个时辰都没走
        for _ in range(5): w.run_slot()
        h = w.state_hash()
        with self.assertRaises(RuntimeError): w.end_day()                       # 走了 5 个
        self.assertEqual((w.day, w.slot, w.state_hash()), (0, 5, h))
        self.assertNotIn(('end_day', 0), eng.calls)                             # 引擎没被叫去收盘
        w.step()                                                                # 补完这一日
        self.assertEqual((w.day, w.slot), (1, 0))
        self.assertEqual([c[2] for c in eng.calls if c[0] == 'run_slot' and c[1] == 0], list(range(SLOTS_PER_DAY)))
        self.assertEqual(w.state_hash(), World().run(1).state_hash())
        # 不接引擎也一样：不能靠“没人在乎”蒙混过去
        v = World(); v.begin_day()
        with self.assertRaises(RuntimeError): v.end_day()

    def test_unimplemented_commands_fail_loudly(self):
        w = World()
        for name in ('cmd_put', 'cmd_use', 'cmd_say'):
            with self.assertRaises(NotImplementedError, msg=name): getattr(w, name)('P0001')

    def test_hooks_fire_in_split_flow(self):
        def setup(w): w.hooks[20].append(lambda w: w.close_road(5, '扰动'))
        a = World(); setup(a); a.run(30)
        b = World(); setup(b); b.advance(SLOTS_PER_DAY * 30)
        self.assertEqual(a.state_hash(), b.state_hash())
        self.assertTrue(a.x("SELECT 1 FROM route_closure WHERE from_day=20").fetchone())


class StubEngine:
    """记录调用的空引擎：不改任何状态，where 只对 managed 里的人作答。"""

    def __init__(self, managed=None, probe=None):
        self.calls, self.managed, self.probe = [], dict(managed or {}), probe

    def attach(self, world): self.world = world; self.calls.append(('attach',))
    def begin_day(self, day):
        self.calls.append(('begin_day', day))
        if self.probe: self.probe('begin_day', self.world, day)
    def run_slot(self, day, slot): self.calls.append(('run_slot', day, slot))
    def end_day(self, day):
        self.calls.append(('end_day', day))
        if self.probe: self.probe('end_day', self.world, day)
    def on_person_added(self, pid): self.calls.append(('added', pid))
    def on_person_removed(self, pid, why): self.calls.append(('removed', pid, why))
    def where(self, pid, day, slot): return self.managed.get(pid)


_split_cache = {}


def split_phase_world():
    """(世界, 空引擎)：预热 1 年 + 3 年，接着一个什么也不做的引擎，且不用 step()，手动 begin_day + 12 x run_slot + end_day。
    进程内只算一遍、只读（基准要 2.7 秒，默认整套测试有 60 秒线）：它同时是“重跑一致”“分步与 step 逐位等价”“空引擎不改变状态”三项检查的对象，
    三项各自与 baseline_world()（step() 跑的、没接引擎）或 REF_HASH 比对，所以任何一项出了偏差都会红。"""
    if 'w' not in _split_cache:
        eng = StubEngine()
        w = World(engine=eng)
        for _ in range(BASELINE_DAYS):
            w.begin_day()
            for _ in range(SLOTS_PER_DAY): w.run_slot()
            w.end_day()
        _split_cache['w'] = (w, eng)
    return _split_cache['w']


class EngineHookTests(unittest.TestCase):
    def test_call_order_and_phase_boundaries(self):
        seen = {}

        def probe(which, w, day):
            if which == 'begin_day':       # 引擎的 begin_day 在经济阶段之后
                seen['meals_at_begin'] = bool(w.x("SELECT 1 FROM event_log WHERE day=? AND type='MEALS'", (day,)).fetchone())
                seen['roster_next_at_begin'] = w.x('SELECT COUNT(*) FROM roster WHERE day=?', (day + 1,)).fetchone()[0]
            else:                          # 引擎的 end_day 在人事阶段之前：次日班表还没排
                seen['roster_next_at_end'] = w.x('SELECT COUNT(*) FROM roster WHERE day=?', (day + 1,)).fetchone()[0]
        eng = StubEngine(probe=probe)
        w = World(engine=eng)
        w.run(3)
        expect = [('attach',)]
        for d in range(3):
            expect += [('begin_day', d)] + [('run_slot', d, s) for s in range(SLOTS_PER_DAY)] + [('end_day', d)]
        self.assertEqual([c for c in eng.calls if c[0] in ('attach', 'begin_day', 'run_slot', 'end_day')], expect)
        self.assertTrue(seen['meals_at_begin'])
        self.assertEqual(seen['roster_next_at_begin'], 0)
        self.assertEqual(seen['roster_next_at_end'], 0)
        self.assertGreater(w.x('SELECT COUNT(*) FROM roster WHERE day=3').fetchone()[0], 0)

    def test_inert_engine_changes_nothing_econ_hash_neutral(self):
        base = baseline_world()
        w, eng = split_phase_world()                               # 整个基准，接着空引擎
        self.assertEqual(w.state_hash(), REF_HASH)
        self.assertEqual(w.econ_hash(), base.econ_hash())          # 经济中立性
        removed = [c for c in eng.calls if c[0] == 'removed']
        self.assertEqual(len(removed), w.cnt['deaths'])
        self.assertTrue(all(c[2] == '圆寂' for c in removed))
        self.assertEqual(len([c for c in eng.calls if c[0] == 'added']), len(w.pids) - 300)

    def test_real_npc_engine_attaches_and_stays_econ_neutral(self):
        """协议冒烟：真正的 NpcEngine（C 段，原型场景 60 僧）经 attach 接上内核，begin_day / run_slot / end_day 的签名与次序对得上，
        经济表哈希与不接引擎的世界相同。两边的名册与场所还各管各的（KernelHost 与名册映射是集成代理的事），所以这里只验协议与经济中立性，不验 where 的内容。
        这是跨模块的契约测试：C 段改了 ProtoRun 或 Engine 协议，这里先红。"""
        from tianl.core import rnd
        from tianl.npc.scenarios import ProtoRun
        days = 60
        base = World().run(days)
        run = ProtoRun(rng=rnd)
        w = World(engine=run.engine).run(days)
        self.assertEqual(run.engine.last, (days - 1, SLOTS_PER_DAY - 1))        # 每个日每个时辰引擎都被叫到
        self.assertIs(run.engine.world, w)
        self.assertEqual(w.econ_hash(), base.econ_hash())
        self.assertEqual(w.viol, base.viol)

    def test_active_engine_driving_commands_keeps_economy_neutral(self):
        """会动手的引擎：每个时辰调 cmd_move、每日末调 set_meal_ration(次日, 1)（撤销）与 cmd_steal_food（开关关着）。
        这些调用只许写 assignment / event_log 一类非经济表，经济表哈希与不接引擎的世界逐位相同。"""
        class Busy(StubEngine):
            def run_slot(self, day, slot):
                super().run_slot(day, slot)
                w = self.world
                who = w.pids[(day * 12 + slot) % 40]
                w.cmd_move(who, w.pl.main_hall, day, slot)
            def end_day(self, day):
                super().end_day(day)
                self.world.set_meal_ration(day + 1, 1.0, '无事')
                self.stolen = getattr(self, 'stolen', 0) + self.world.cmd_steal_food(self.world.pids[0], 5000)
        eng = Busy()
        a, b = World().run(240), World(engine=eng).run(240)
        self.assertEqual(a.econ_hash(), b.econ_hash())
        self.assertNotEqual(a.state_hash(), b.state_hash())                    # assignment 表里确实多了行
        self.assertGreater(b.x('SELECT COUNT(*) FROM assignment').fetchone()[0], 0)
        self.assertEqual(eng.stolen, 0)
        self.assertFalse(b.x("SELECT 1 FROM event_log WHERE type IN ('MEAL_HALVED','GRAIN_STOLEN')").fetchone())
        self.assertEqual(b.viol, [])

    def test_where_delegates_to_engine_for_managed_people(self):
        base = World()
        pid = next(p for p in base.pids if base.person(p)['gen'] == base.S.org.recruit.gen)
        eng = StubEngine({pid: ('SH_X', '见习', '自由', '测试')})
        w = World(engine=eng)
        self.assertEqual(w.where(pid, 3, 6), ('SH_X', '见习'))
        self.assertEqual(w.where_ex(pid, 3, 6), ('SH_X', '见习', '自由', '测试'))
        other = next(p for p in w.pids if p != pid)
        self.assertEqual(w.where(other, 3, 6), base.where(other, 3, 6))       # 其余仍走作息模板
        self.assertEqual(w.where_ex(other, 3, 6)[2:], ('作息', '模板'))
        self.assertIn(pid, w.present('SH_X', 3, 6))
        self.assertIsNone(w.where(pid, -5, 6))                                 # 不在世者不问引擎


def drain_famine(w):
    """清库：寺库、庄仓、粮铺的存粮与寺里的钱一并清空（具名消耗，守恒不破），逼出“断供”档位。"""
    for owner, place in ((w.ac.org, w.pl.granary), (w.ac.org, w.pl.estate_granary), (w.ac.shop_grain, w.pl.town)):
        w.consume(owner, place, w.cm.staple, 10 ** 12, 'consume')
    w.pay(w.ac.org, w.ac.equity, w.bal(w.ac.org), '扰动:清钱')


class RecordingEngine(StubEngine):
    """在 on_person_added 回调里当场读库：引擎看到的必须是写定的一行（含 home）。"""

    def __init__(self):
        super().__init__()
        self.seen = []

    def on_person_added(self, pid):
        super().on_person_added(pid)
        row = self.world.x('SELECT id, home, hall, status, org FROM person WHERE id=?', (pid,)).fetchone()
        self.seen.append((row, self.world.person(pid)['home']))


class PersonHookTimingTests(unittest.TestCase):
    def test_on_person_added_sees_the_finished_row(self):
        eng = RecordingEngine()
        w = World(engine=eng).run(2 * YEAR)
        recruits = [r for r, _ in eng.seen if r[0] in w.pids[300:]]
        self.assertGreaterEqual(len(recruits), 4)
        for (pid, home, hall, status, org), cached_home in eng.seen:
            self.assertIsNotNone(home, f'{pid} 回调时 home 还是空')
            self.assertEqual(home, cached_home)                      # 人员缓存里的也是定稿的一行
            self.assertEqual((status, org), ('在寺', w.ac.org))
        o = w.S.org
        self.assertEqual({r[1] for r in recruits}, {f'{o.dorm.prefix}{o.dorm.recruit}'})

    def test_wandering_monks_leave_and_return_through_the_hooks(self):
        eng = StubEngine()
        w = World(engine=eng)
        w.hooks[40].append(drain_famine)
        monks = [p for p in w.pids if w.person(p)['gen'] != w.S.org.visitor_gen]
        for p in monks: w.where(p, 0, 6)                            # 先把人员缓存填满：游方者的缓存必须随状态更新
        w.run(41)
        gone = [c[1] for c in eng.calls if c[0] == 'removed' and c[2] == '游方']
        self.assertGreater(len(gone), 0)
        self.assertEqual(len(gone), w.cnt['monks_left'])
        for pid in gone:
            self.assertEqual(w.x('SELECT status FROM person WHERE id=?', (pid,)).fetchone()[0], '游方')
            self.assertIsNone(w.where(pid, w.day, 6), '游方者不在世，where 应为 None（缓存没更新就会误答）')
        n_added = len([c for c in eng.calls if c[0] == 'added'])
        w.run(150 - 41)                                              # 过了收成日，粮足，游方僧归寺
        self.assertEqual(w.x("SELECT COUNT(*) FROM person WHERE status='游方'").fetchone()[0], 0)
        back = [c for c in eng.calls if c[0] == 'added'][n_added:]
        self.assertTrue(set(gone) <= {c[1] for c in back}, '归寺者都要回调 on_person_added')
        self.assertEqual(w.viol, [])


class NameExhaustionTests(unittest.TestCase):
    def test_exhausted_single_char_names_fall_back_to_two_char_names(self):
        w = World()
        gen = w.S.org.recruit.gen
        for ch in w._pool: w.names.add(gen + ch)                    # 该辈的单字名全部占满
        nm = w._newname(gen, 'probe')
        self.assertEqual(len(nm), 3)
        self.assertTrue(nm.startswith(gen))
        self.assertNotIn(nm, w.names)
        self.assertEqual(w._newname(gen, 'probe'), nm)              # 确定性：同键同名

    def test_name_pool_truly_exhausted_raises_instead_of_hanging(self):
        w = World()
        gen, pool = w.S.org.recruit.gen, w._pool
        w.names |= {gen + a for a in pool} | {gen + a + b for a in pool for b in pool}
        with self.assertRaises(RuntimeError): w._newname(gen, 'probe')

    def test_mass_recruitment_does_not_hang_and_names_stay_unique(self):
        w = World({'monks': 420}).run(100)                         # 四月初一一次收录 ~120 人：远超池里剩下的单字名
        self.assertEqual(w.head(), 420)
        names = [r[0] for r in w.x('SELECT name FROM person')]
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(any(len(n) == 3 for n in names))
        self.assertEqual(w.viol, [])

    @unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开')
    def test_slow_thirty_year_run_completes_with_no_violations(self):
        w = World()
        for _ in range(30): w.run(YEAR)
        self.assertEqual(w.viol, [])
        names = [r[0] for r in w.x('SELECT name FROM person')]
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(any(len(n) == 3 for n in names))           # 取名池在约 20 年后耗尽，之后改取两字名


class CouplingTests(unittest.TestCase):
    """ARCHITECTURE 5.1 的两处耦合：各有开关、各发事件、缺省不触发（econ_hash 中立）。"""

    def test_defaults_are_inert(self):
        w = World()
        self.assertEqual(w.couplings, {'half_meal': True, 'food_theft': False})
        self.assertEqual(w.cmd_steal_food('P0001', 5000), 0)       # (b) 缺省关：不扣粮、不发事件
        self.assertFalse(w.x("SELECT 1 FROM event_log WHERE type='GRAIN_STOLEN'").fetchone())
        base = World().run(30)
        self.assertEqual(w.run(30).state_hash(), base.state_hash())

    def test_half_meal_reduces_that_days_ration_and_emits_event(self):
        base, w = World().run(20), World()
        w.run(9)
        self.assertTrue(w.set_meal_ration(10, 0.5, '厨下人手不足'))
        w.run(11)
        meals = lambda x, d: json.loads(x.x("SELECT payload FROM event_log WHERE type='MEALS' AND day=?", (d,)).fetchone()[0])
        full, half = meals(base, 10)['grain'], meals(w, 10)['grain']
        self.assertEqual(half, int(full * 0.5))
        self.assertLess(half, full)
        ev = w.x("SELECT payload FROM event_log WHERE type='MEAL_HALVED'").fetchall()
        self.assertEqual(len(ev), 1)
        p = json.loads(ev[0][0])
        self.assertEqual((p['full'], p['need'], p['why']), (full, half, '厨下人手不足'))
        self.assertEqual(meals(w, 9), meals(base, 9))              # 前一日不受影响
        self.assertEqual(w.viol, [])                               # 守恒不破
        self.assertIn('只备半餐', w.chronicle(10))
        self.assertEqual(w.meal_scale, {})                         # 用过即清

    def test_half_meal_switch_off_or_wrong_day(self):
        w = World()
        w.couplings['half_meal'] = False
        self.assertFalse(w.set_meal_ration(3, 0.5))
        w.run(5)
        self.assertEqual(w.state_hash(), World().run(5).state_hash())
        w = World(); w.run(2)
        with self.assertRaises(ValueError): w.set_meal_ration(1, 0.5)             # 已过去的日子
        w.begin_day()
        with self.assertRaises(ValueError): w.set_meal_ration(w.day, 0.5)         # 今日消耗阶段已跑完
        self.assertTrue(w.set_meal_ration(w.day + 1, 0.5))
        with self.assertRaises(ValueError): w.set_meal_ration(w.day + 1, 0)
        with self.assertRaises(ValueError): w.set_meal_ration(w.day + 1, 1.5)
        self.assertTrue(w.set_meal_ration(w.day + 1, 1))                          # 系数 1 = 撤销
        self.assertEqual(w.meal_scale, {})

    def test_engine_can_set_tomorrows_ration_from_end_day(self):
        class Kitchen(StubEngine):
            def end_day(self, day):
                super().end_day(day)
                if day == 6: self.world.set_meal_ration(day + 1, 0.5, '人手不足')
        w = World(engine=Kitchen()).run(10)
        self.assertEqual([r[0] for r in w.x("SELECT day FROM event_log WHERE type='MEAL_HALVED'")], [7])

    def test_food_theft_switch_on_deducts_grain_and_emits_event(self):
        w = World().run(5)
        w.couplings['food_theft'] = True
        g0 = w.qty(w.ac.org, w.pl.granary, w.cm.staple)
        e = w.ev('FOOD_THEFT', actor='P0003')
        self.assertEqual(w.cmd_steal_food('P0003', 4000, slot=7, cause=e), 4000)
        self.assertEqual(w.qty(w.ac.org, w.pl.granary, w.cm.staple), g0 - 4000)
        row = w.x("SELECT actor, slot, cause, payload FROM event_log WHERE type='GRAIN_STOLEN'").fetchone()
        self.assertEqual((row[0], row[1], row[2], json.loads(row[3])), ('P0003', 7, e, {'grain': 4000}))
        self.assertEqual(w.cmd_steal_food('P0003', 10 ** 12), g0 - 4000)       # 不够就扣到空
        w.run(3)
        self.assertEqual([v for v in w.viol if v[1].startswith('物守恒')], [])
        self.assertIn('偷食', w.chronicle(5))

    def test_inert_engine_still_econ_neutral_with_couplings_present(self):
        a, b = World().run(120), World(engine=StubEngine()).run(120)
        self.assertEqual(a.econ_hash(), b.econ_hash())
        self.assertFalse(b.x("SELECT 1 FROM event_log WHERE type IN ('MEAL_HALVED','GRAIN_STOLEN')").fetchone())


if __name__ == '__main__':
    unittest.main()
