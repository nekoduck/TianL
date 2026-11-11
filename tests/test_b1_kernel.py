"""B1 验收：v0.2 少林寺内核（tianl.kernel + defs/）与原型逐位相同。

  python3 -m unittest tests.test_b1_kernel                 # 默认（约 25 秒）
  TIANL_SLOW=1 python3 -m unittest tests.test_b1_kernel    # 再加十年基准、六个种子、E2/E2b/E5/E6、人物与独有物测试

“日志”指 reference/logs/shaolin_run_log.txt（原型跑出来的输出）；日志逐行复现由 tools/shaolin_regress.py 产出。
"""
import ast
import contextlib
import importlib.util
import io
import os
import re
import unittest
from pathlib import Path

from tianl.core.calendar import SLOTS_PER_DAY, YEAR
from tianl.kernel import World, year_report

ROOT = Path(__file__).resolve().parents[1]
SLOW = os.environ.get('TIANL_SLOW') == '1'
REF_HASH = '49f6ddde04dfa7f5'
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
        cls.w = World().run(360 * 4)
        cls.w2 = World().run(360 * 4)

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
        a = World().run(400)
        b = World()
        for _ in range(400):
            b.begin_day()
            for _ in range(SLOTS_PER_DAY): b.run_slot()
            b.end_day()
        self.assertEqual((b.day, b.slot), (400, 0))
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
        base = World().run(360 * 4)
        eng = StubEngine()
        w = World(engine=eng).run(360 * 4)
        self.assertEqual(w.state_hash(), REF_HASH)
        self.assertEqual(w.econ_hash(), base.econ_hash())          # 经济中立性
        removed = [c for c in eng.calls if c[0] == 'removed']
        self.assertEqual(len(removed), w.cnt['deaths'])
        self.assertTrue(all(c[2] == '圆寂' for c in removed))
        self.assertEqual(len([c for c in eng.calls if c[0] == 'added']), len(w.pids) - 300)

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


if __name__ == '__main__':
    unittest.main()
