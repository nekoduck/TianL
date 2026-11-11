"""B1 验收：日志里从未触发的分支，与原型逐位对照。

reference/logs/shaolin_run_log.txt 的基准与 E1–E6 里，游方离寺与归寺、佃户借粮与收成还粮、农户离乡与岁首招佃、关键岗位空缺、
月朔点检发现失窃（之外的取物）这些分支要么没触发、要么只在个别实验里触发。下面逐个造出触发它们的扰动（hooks，具名消耗，守恒不破），
同时在原型 World 和新内核 World 上跑，比 state_hash、全部计数、粮账、物流、违规表、每日时间序列，再比几天的日报。

默认只跑最能说明问题的五个（约 4 秒）；`TIANL_SLOW=1` 再跑另外十个更窄的场景（灾年、深度欠粮、赈济、粮铺缺钱、外销、粮价上浮、
欠发僧衣封顶、钱紧、老僧圆寂、长期封路）。这些场景是 tests/test_b1_params.py 逐个规则参数找“它在哪里起作用”时用的同一批
（SCENARIOS），所以一个参数的值若与原型不同，要么基准哈希变，要么这里的某个场景与原型分道。

原型常量（场所、账户的编号）在测试里直接写，这是允许的：它们只能出现在 defs 与测试里。
"""
import importlib.util
import json
import os
import unittest
from pathlib import Path

from tianl.kernel import World

ROOT = Path(__file__).resolve().parents[1]
SLOW = os.environ.get('TIANL_SLOW') == '1'
SHI = GUAN = 1000


def _load_reference():
    spec = importlib.util.spec_from_file_location('shaolin_spike_ref_branches', ROOT / 'reference' / 'shaolin_spike.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


REF = _load_reference()


def count(w, typ):
    return w.x('SELECT COUNT(*) FROM event_log WHERE type=?', (typ,)).fetchone()[0]


# ---------------------------------------------------------------------- 扰动（只用两边都有的 API 与原型编号）
def tenants(w):
    return [r[0] for r in w.x("SELECT id FROM household WHERE kind='tenant' AND status='在' ORDER BY id").fetchall()]


def famine(w, d0):
    """d0 日清库：寺库、庄仓、粮铺存粮与寺里的钱全空 -> 断供，僧人游方；收成后粮足再归寺。"""
    def hook(w):
        for owner, place in (('ORG_SH', 'SH_GRANARY'), ('ORG_SH', 'EST_GRANARY'), ('SHOP_GRAIN', 'DF')):
            w.consume(owner, place, 'grain', 10 ** 12, 'consume')
        w.pay('ORG_SH', 'EQUITY', w.bal('ORG_SH'), '扰动:清钱')
    w.hooks[d0].append(hook)


def starve_tenants(w, d0, d1):
    """[d0, d1) 每日清空佃户的存粮：佃户向庄仓借粮，收成日按比例还粮。"""
    def hook(w):
        for hid in tenants(w): w.consume(hid, 'EST', 'grain', 10 ** 12, 'consume')
    for d in range(d0, d1): w.hooks[d].append(hook)


def squeeze(w, d0, d1):
    """[d0, d1) 每日：佃户无粮无钱、庄仓空、寺库只留三日口粮（“告急”档，不至游方，也没有赈济）-> 农户断粮超限离乡，岁首招佃。"""
    def hook(w):
        for hid in tenants(w):
            w.consume(hid, 'EST', 'grain', 10 ** 12, 'consume')
            w.pay(hid, 'EQUITY', w.bal(hid), '扰动:清钱')
        w.consume('ORG_SH', 'EST_GRANARY', 'grain', 10 ** 12, 'consume')
        w.consume('ORG_SH', 'SH_GRANARY', 'grain', 10 ** 12, 'consume')
        w.produce('ORG_SH', 'SH_GRANARY', 'grain', w.daily_grain() * 3, 'port_in')
    for d in range(d0, d1): w.hooks[d].append(hook)


def kill_everyone(w, d0):
    """d0 日全寺圆寂：岗位出缺、无人可继任 -> 关键岗位空缺超限记违规。"""
    def hook(w):
        for (pid,) in w.x("SELECT id FROM person WHERE status='在寺' ORDER BY id").fetchall(): w.die(pid, w.day - 1)
    w.hooks[d0].append(hook)


def item_taken_unseen(w):
    """第 10 日有人在藏经阁无人在场时取走独有物（非保管人，违规），此后 45 日的月朔点检发现失窃。返回 (事件号, 时辰)。"""
    w.run(10)
    d = w.day
    for s in range(12):
        ps = [x for x in w.present('SH_LIBRARY', d, s) if x != 'P0065']      # P0065 是该物的持有人
        if len(ps) >= 2: break
    w.x('BEGIN')
    e = w.cmd_take(ps[0], 'IT_BRZ', d, s)
    w.x('COMMIT')
    w.run(45)
    return e, s


# ---- 下面是更窄的场景：各自盯着一小撮规则参数
def bad_harvest(w, yf=0.65):
    """预热年两季收成都按年景 yf（低于“灾年线”0.7）：寺院减租、官府两税减半。"""
    w.yield_override.update({(0, '麦'): yf, (0, '粟'): yf})


def deep_debt(w):
    """第 100–117 日佃户每日断粮：向庄仓借粮直到触及借粮上限，收成日再按比例还粮（还不清）。"""
    starve_tenants(w, 100, 118)


def relief(w):
    """第 30–49 日佃户无粮无钱、庄仓空，但寺库充足（“充足”档）：断粮满数日，寺院赈济。"""
    def hook(w):
        for hid in tenants(w):
            w.consume(hid, 'EST', 'grain', 10 ** 12, 'consume'); w.pay(hid, 'EQUITY', w.bal(hid), '扰动:清钱')
        w.consume('ORG_SH', 'EST_GRANARY', 'grain', 10 ** 12, 'consume')
    for d in range(30, 50): w.hooks[d].append(hook)


def poor_shop(w, stock=100, cash=60, day=120):
    """day 日粮铺只剩 stock 石存粮、cash 贯现钱：农户卖粮、寺院余粮出售、粮铺进货都被它的钱与存量卡住。"""
    def hook(w):
        w.consume('SHOP_GRAIN', 'DF', 'grain', w.qty('SHOP_GRAIN', 'DF', 'grain') - stock * SHI, 'consume')
        w.pay('SHOP_GRAIN', 'EQUITY', w.bal('SHOP_GRAIN') - cash * GUAN, '扰动:清钱')
    w.hooks[day].append(hook)


def surplus_shop(w):
    """第 20 日粮铺存粮恰好比外销线（500 石）多 1 合：当日外销降到目标存量。"""
    w.hooks[20].append(lambda w: w.produce('SHOP_GRAIN', 'DF', 'grain', 500 * SHI + 1 - w.qty('SHOP_GRAIN', 'DF', 'grain'), 'port_in'))


def thin_shop(w):
    """第 30–39 日粮铺存粮压到 100 石、佃户每日断粮：佃户向粮铺买粮，粮价看粮铺存量是否“偏薄”。"""
    def hook(w):
        w.consume('SHOP_GRAIN', 'DF', 'grain', w.qty('SHOP_GRAIN', 'DF', 'grain') - 100 * SHI, 'consume')
        for hid in tenants(w): w.consume(hid, 'EST', 'grain', 10 ** 12, 'consume')
    for d in range(30, 40): w.hooks[d].append(hook)


def cloth_backlog(w):
    """第 84 日（立项前一日）欠发僧衣已累计 100 匹：立项再加一次就超过“欠发不过两季”的封顶。"""
    w.hooks[84].append(lambda w: setattr(w, 'cloth_due', 100))


def cash_crunch(w):
    """第 84 日寺里只剩 80 贯：批僧衣采买前要先留压库钱，批得起的量不足原量。"""
    w.hooks[84].append(lambda w: w.pay('ORG_SH', 'EQUITY', w.bal('ORG_SH') - 80 * GUAN, '扰动:清钱'))


def old_monks(w):
    """第 10 日全寺（要角除外）老了 45 岁：圆寂率落在最高一档。"""
    w.hooks[10].append(lambda w: (w.x("UPDATE person SET age=age+45 WHERE canon=0"), w.pcache.clear()))


def long_blockade(w):
    """第 5 日起封路 300 日：采买订单一次次超期失败、续单，时限翻倍直到触顶。"""
    w.hooks[5].append(lambda w: w.close_road(300, '扰动:封路'))


def _go(days, *setups):
    def f(w):
        for s in setups: s(w)
        w.run(days)
    return f


# 场景名 -> 在一个新造的世界上把它跑完的函数。前五个是默认测试；其余（SLOW_SCENARIOS）只在 TIANL_SLOW=1 时与原型对照。
SCENARIOS = {
    'famine': _go(150, lambda w: famine(w, 40)),
    'tenants': _go(130, lambda w: starve_tenants(w, 100, 103)),
    'squeeze': _go(365, lambda w: squeeze(w, 20, 60)),
    'kill': _go(80, lambda w: kill_everyone(w, 50)),
    'item': item_taken_unseen,
    'bad_harvest': _go(260, bad_harvest),
    'debt': _go(135, deep_debt),
    'relief': _go(70, relief),
    'poor_shop': _go(145, poor_shop),
    'import_poor': _go(130, lambda w: poor_shop(w, stock=50)),
    'surplus_shop': _go(30, surplus_shop),
    'thin_shop': _go(45, thin_shop),
    'cloth_backlog': _go(130, cloth_backlog),
    'cash_crunch': _go(100, cash_crunch),
    'old_monks': _go(400, old_monks),
    'long_blockade': _go(260, long_blockade),
}
DEFAULT_SCENARIOS = ('famine', 'tenants', 'squeeze', 'kill', 'item')
SLOW_SCENARIOS = tuple(k for k in SCENARIOS if k not in DEFAULT_SCENARIOS)


def run_scenario(cls, name, **kw):
    w = cls(**kw)
    SCENARIOS[name](w)
    return w


class Differential:
    """与原型对照的帮手（混入 TestCase）。"""

    def assertSameWorld(self, a, b, chronicle_days=()):
        self.assertEqual(a.state_hash(), b.state_hash())
        nz = lambda d: {k: v for k, v in d.items() if v}                              # defaultdict 被读过会多出零值的键
        for name in ('cnt', 'tg', 'flows', 'net'):
            self.assertEqual(nz(getattr(a, name)), nz(getattr(b, name)), name)
        self.assertEqual(a.viol, b.viol)
        self.assertEqual(a.series, b.series)
        for d in chronicle_days:
            self.assertEqual(a.chronicle(d), b.chronicle(d), f'第 {d} 日日报')
            self.assertEqual(a.chronicle(d, 'all'), b.chronicle(d, 'all'), f'第 {d} 日日报（全域）')

    def both(self, name):
        a, b = run_scenario(REF.World, name), run_scenario(World, name)
        self.addCleanup(a.db.close)                                                  # 原型的 World 不会自己关库
        self.addCleanup(b.close)
        return a, b


class BranchDifferential(Differential, unittest.TestCase):
    def test_wandering_monks_leave_and_return(self):
        a, b = self.both('famine')
        self.assertGreater(a.cnt['monks_left'], 0)                                   # 游方离寺（tier_famine、leave_prob）
        self.assertEqual(count(a, 'MONKS_RETURN'), 1)                                # 收成后归寺（return_doys）
        self.assertEqual(a.x("SELECT COUNT(*) FROM person WHERE status='游方'").fetchone()[0], 0)
        self.assertGreater(count(a, 'RECRUIT'), 0)
        self.assertGreater(a.qty('SHOP_GRAIN', 'DF', 'grain'), 0)                    # 粮铺清库后又进了粮（进货规则）
        self.assertSameWorld(a, b, (40, 41, 60, 140, 141))

    def test_tenants_borrow_and_repay_at_harvest(self):
        a, b = self.both('tenants')
        self.assertGreater(a.cnt['hh_borrow'], 0)                                    # 佃户向庄仓借粮
        self.assertGreater(sum(v for k, v in a.tg.items() if k[1] == '佃户还粮'), 0)   # 收成日还粮（repay_n / repay_d）
        self.assertGreater(a.x('SELECT COUNT(*) FROM arrears').fetchone()[0], 0)
        self.assertSameWorld(a, b, (100, 101, 125))

    def test_households_leave_and_new_tenants_settle(self):
        a, b = self.both('squeeze')
        self.assertGreater(a.cnt['hh_left'], 0)                                      # 断粮超限离乡（hunger_leave）
        self.assertEqual(a.cnt['monks_left'], 0)                                     # 寺库没到“断供”，僧人不游方
        self.assertEqual(count(a, 'TENANTS_SETTLED'), 1)                             # 岁首招佃（immig_prob、member_*）
        self.assertSameWorld(a, b, (59, 60, 360))

    def test_key_posts_left_vacant_record_violations(self):
        a, b = self.both('kill')
        self.assertTrue(any(v[1] == '关键岗位空缺' for v in a.viol))                    # vac_limit
        self.assertSameWorld(a, b, (50, 51, 53, 54))

    def test_item_taken_unseen_is_found_at_the_monthly_audit(self):
        a, b = self.both('item')
        self.assertEqual(count(a, 'AUDIT_MISSING'), 1)                               # audit_slot 写在这条事件里
        self.assertSameWorld(a, b, (10, 30, 31))


@unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开')
class NarrowBranchDifferential(Differential, unittest.TestCase):
    """更窄的场景（tests/test_b1_params.py 用它们逐个规则参数找“它在哪里起作用”）：每个都与原型逐位对照，并确认分支真的走到了。"""

    def test_bad_harvest_remits_rent_and_halves_tax(self):
        a, b = self.both('bad_harvest')
        harvests = [json.loads(r[0]) for r in a.x("SELECT payload FROM event_log WHERE type='HARVEST'")]
        self.assertEqual(len(harvests), 2)
        self.assertTrue(all(h['remission'] for h in harvests))                       # 灾年：减租、减税（bad_yield、bad_rent_share、bad_tax_mult）
        self.assertSameWorld(a, b, (125, 245))

    def test_deep_debt_is_only_partly_repaid(self):
        a, b = self.both('debt')
        self.assertGreater(a.cnt['hh_borrow'], 10)                                   # 一连借了许多次（hh_borrow_cap_shi 封顶）
        self.assertGreater(a.x('SELECT SUM(qty) FROM arrears').fetchone()[0], 0)     # 收成日按比例还（repay_n / repay_d），还不清，仍欠着
        self.assertGreater(sum(v for k, v in a.tg.items() if k[1] == '佃户还粮'), 0)
        self.assertSameWorld(a, b, (100, 118, 125))

    def test_relief_when_temple_is_comfortable(self):
        a, b = self.both('relief')
        self.assertGreater(a.cnt['relief'], 0)                                       # 赈济（hunger_relief、relief_days）
        self.assertEqual(a.cnt['monks_left'], 0)
        self.assertSameWorld(a, b, (31, 33, 40))

    def test_poor_shop_limits_sales_and_imports(self):
        for name in ('poor_shop', 'import_poor'):
            with self.subTest(name):
                a, b = self.both(name)
                imp = a.x("SELECT COUNT(*) FROM work_order WHERE kind='IMPORT' AND commodity='grain' AND created BETWEEN 120 AND 124").fetchone()[0]
                self.assertEqual(imp > 0, name == 'import_poor')                     # 存粮低于进粮线才进粮（shop_grain_low_shi）
                self.assertSameWorld(a, b, (120, 121, 130, 131))

    def test_shop_surplus_is_exported(self):
        a, b = self.both('surplus_shop')
        self.assertGreater(a.x("SELECT COUNT(*) FROM ledger WHERE day=20 AND payer='PORT'").fetchone()[0], 0)    # 外销：口岸付款
        self.assertSameWorld(a, b, (20, 21))

    def test_thin_shop_raises_the_grain_price(self):
        a, b = self.both('thin_shop')
        self.assertGreater(a.x("SELECT COUNT(*) FROM ledger WHERE payee='SHOP_GRAIN' AND payer LIKE 'HH_T%' AND day BETWEEN 30 AND 39").fetchone()[0], 0)   # 佃户向粮铺买粮
        self.assertSameWorld(a, b, (30, 31, 39))

    def test_cloth_backlog_hits_the_cap(self):
        a, b = self.both('cloth_backlog')
        self.assertSameWorld(a, b, (84, 85, 100))

    def test_cash_crunch_reduces_or_defers_orders(self):
        a, b = self.both('cash_crunch')
        self.assertGreater(count(a, 'ORDER_REDUCED') + count(a, 'ORDER_DEFERRED'), 0)
        self.assertSameWorld(a, b, (84, 85))

    def test_old_monks_die_at_the_top_rate(self):
        a, b = self.both('old_monks')
        self.assertGreater(a.cnt['deaths'], 5)
        self.assertSameWorld(a, b, (11, 12, 100))

    def test_long_blockade_renews_orders_until_the_cap(self):
        a, b = self.both('long_blockade')
        self.assertGreater(a.x("SELECT MAX(sla) FROM work_order WHERE parent IS NOT NULL").fetchone()[0], 100)   # 续单时限翻倍到很大
        self.assertSameWorld(a, b, (5, 60, 200))


if __name__ == '__main__':
    unittest.main()
