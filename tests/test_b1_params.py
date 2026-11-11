"""B1 验收：规则参数 K 的每一项都“有人用、有人验”。

基准 `World().run(360*4)` 的 state_hash 是 49f6ddde04dfa7f5，所以基准里走得到的参数，值错一点哈希就变；
但有些参数只在基准走不到的分支里起作用（档位与赈济、灾年、深度欠粮、募化与借粮、钱紧、封路、点检、空缺……）。
对这些，哈希本身没有约束力。下面把它们逐个挑出来，各配一个场景（tests/test_b1_branches.py 的 SCENARIOS，
那里每个场景都与原型逐位对照过）：把参数扰动一点（数值叶子一起 +1 或 -1），场景的结果必须变——
即这个参数在那个已与原型对过账的场景里确实起作用，值错了就会和原型分道。

三种检查：
  默认（毫秒级）    清单完备：K 里的每个键恰好落在 LIVE_IN（基准里没反应、靠场景验证）或 BASELINE_LOUD（基准里有反应、靠哈希验证）之一；
                    取名池太小会拒绝装配（pool_min）。
  TIANL_SLOW=1      LIVE_IN（45 个键）里每个键在它的场景里确实让结果改变。
  TIANL_KSCAN=1     （慢，约 2 分钟，用进程池）对 K 的每个键扰动后各跑一遍基准 1440 日：BASELINE_LOUD 里的每个键必须让基准哈希变，
                    LIVE_IN 里的每个键必须不让它变——即上面的分类是实测出来的，不是手写的。
"""
import copy
import os
import unittest
from concurrent.futures import ProcessPoolExecutor

from tests.test_b1_branches import SCENARIOS, run_scenario
from tests.test_b1_common import REF_HASH, BASELINE_DAYS
from tianl.kernel import World, load_spec

SLOW = os.environ.get('TIANL_SLOW') == '1'
KSCAN = os.environ.get('TIANL_KSCAN') == '1'

# 基准里没有反应的键 -> 让它起作用的场景
LIVE_IN = {
    # 粮档位：基准里寺库一直“充足”，档位线从未触线
    'tier_cover': 'famine', 'tier_pad': 'squeeze', 'tier_light': 'famine', 'tier_alms': 'famine', 'tier_crisis': 'famine',
    'tier_famine': 'famine', 'leave_prob': 'famine',
    # 灾年：基准里年景从未低于灾年线
    'bad_yield': 'bad_harvest', 'bad_rent_share': 'bad_harvest', 'bad_tax_mult': 'bad_harvest',
    # 佃户：借粮上限与还粮比例（基准里佃户从不断粮）、离乡、岁首招佃、赈济
    'hh_borrow_cap_shi': 'debt', 'repay_n': 'debt', 'repay_d': 'debt', 'hunger_relief': 'relief', 'relief_days': 'relief',
    'hunger_leave': 'squeeze', 'immig_prob': 'squeeze', 'immig_cash_guan': 'squeeze',
    # 粮铺：缺钱、存粮偏薄、进货线、外销线
    'shop_cash_floor_guan': 'poor_shop', 'shop_grain_low_shi': 'poor_shop', 'shop_grain_high_shi': 'surplus_shop',
    'thin_shop_stock_shi': 'thin_shop', 'thin_markup': 'thin_shop', 'import_floor_guan': 'import_poor', 'import_markup_pct': 'squeeze',
    # 寺库规则：市购、募化、借粮、审批
    'buy_below': 'famine', 'buy_to': 'famine', 'buy_sla': 'famine', 'alms_below': 'squeeze', 'alms_gap': 'famine', 'alms_sla': 'famine',
    'alms_days': 'famine', 'alms_grain': 'famine', 'alms_money': 'famine', 'borrow_days': 'famine', 'borrow_sla': 'famine',
    'borrow_ship_days': 'famine', 'prio_reserve_from': 'famine', 'afford_min_div': 'famine', 'reserve_guan': 'cash_crunch',
    'cloth_due_cap': 'cloth_backlog', 'renew_cap': 'long_blockade',
    # 人
    'mortality_old': 'old_monks', 'audit_slot': 'item', 'vac_limit': 'kill',
}
# 取名池下限只是装配时的闸门，不参与任何日常结算：单独测（见 PoolGuard）
GUARD_ONLY = ('pool_min',)
# 基准里有反应的键（TIANL_KSCAN=1 实测：扰动后基准哈希变）。其值由基准哈希 49f6ddde04dfa7f5 直接约束
BASELINE_LOUD = (
    'charity_shi', 'closed_pilgrim_mult', 'cloth_due_step', 'cloth_sla', 'convoy_days', 'damage_month_mult', 'damage_months',
    'damage_prob', 'damage_targets', 'export_pct', 'forage_q', 'grace_days', 'hh_buy_days', 'hh_rich_d', 'hh_rich_guan',
    'hh_rich_n', 'hh_shop', 'hh_spare_floor_guan', 'hh_yield_base', 'hh_yield_var', 'import_days', 'import_discount',
    'import_sla', 'labor_per_day', 'meal_slot', 'member_min', 'member_span', 'merit_d', 'merit_n', 'mortality', 'pilgrim_noise',
    'price_yield_ref', 'price_yield_slope', 'purchase_days', 'renew_mult', 'repair_labor', 'repair_sla', 'repair_timber',
    'reserve_days', 'restock_sla', 'sell_d', 'sell_n', 'sell_reserve_days', 'shop_grain_target_shi', 'snow_min_days',
    'snow_span', 'tier_mult', 'tiers', 'timber_reorder', 'timber_sla', 'timber_upto', 'transfer_below', 'transfer_sla',
    'transfer_to', 'veg_cap', 'veg_reorder', 'veg_sla', 'veg_upto', 'veg_yield', 'veg_yield_default', 'wood_cap_d', 'wood_cap_n',
    'yield_base', 'yield_var',
)


def perturb(v, up, top=True):
    """数值叶子一起 +1 / -1（浮点按 ±10% 再偏一点）；只有顶层的字符串列表（档位名、损坏对象）才改字，别处的字符串是编号，不碰。"""
    if isinstance(v, bool): return v
    if isinstance(v, int): return v + 1 if up else v - 1
    if isinstance(v, float): return v * 1.1 + 0.01 if up else v * 0.9 - 0.01
    if isinstance(v, str): return v + '·' if top else v
    if isinstance(v, list): return [perturb(x, up, top and isinstance(x, str)) for x in v]
    if isinstance(v, dict): return {k: perturb(x, up, False) for k, x in v.items()}
    return v


def perturbed_spec(key, up):
    S = load_spec()
    S.K[key] = perturb(S.K[key], up)
    return S


def signature(w):
    """场景跑完后的“指纹”：状态哈希、几天的日报（有的参数只改日报的措辞，如 tier_light）、违规表。"""
    days = [d for d in (41, 42, 60, 100, 101, 125, 131, 136, 150) if d < w.day]
    return w.state_hash(), tuple(w.chronicle(d) for d in days), repr(w.viol)


def scenario_signature(name, spec=None):
    w = run_scenario(World, name, spec=spec)
    try:
        return signature(w)
    finally:
        w.close()


def baseline_hash(key_up):
    """（进程池里跑）扰动某个键后的基准哈希；装配或运行抛异常也算“有反应”，返回 'ERR'。"""
    key, up = key_up
    try:
        w = World(spec=perturbed_spec(key, up)).run(BASELINE_DAYS)
        try: return key_up, w.state_hash()
        finally: w.close()
    except Exception as e:
        return key_up, 'ERR ' + type(e).__name__


class Inventory(unittest.TestCase):
    def test_every_rule_parameter_is_classified_exactly_once(self):
        keys = set(load_spec().K)
        live, loud, guard = set(LIVE_IN), set(BASELINE_LOUD), set(GUARD_ONLY)
        self.assertEqual(sorted(live - keys), [], 'LIVE_IN 里有 K 没有的键')
        self.assertEqual(sorted(loud - keys), [], 'BASELINE_LOUD 里有 K 没有的键')
        self.assertEqual(sorted(live & loud | live & guard | loud & guard), [], '一个键只能归一类')
        self.assertEqual(sorted(keys - live - loud - guard), [], 'K 里有键没归类：新参数请先跑 TIANL_KSCAN=1，再登记到 LIVE_IN / BASELINE_LOUD')
        self.assertTrue(set(LIVE_IN.values()) <= set(SCENARIOS))

    def test_perturb_changes_numbers_but_leaves_codes_alone(self):
        K = load_spec().K
        up, dn = perturb(K['hh_shop'], True), perturb(K['hh_shop'], False)
        self.assertEqual([h['c'] for h in up], [h['c'] for h in K['hh_shop']])             # 品类编号原样
        self.assertEqual(up[1]['floor_guan'], K['hh_shop'][1]['floor_guan'] + 1)
        self.assertEqual(dn[1]['floor_guan'], K['hh_shop'][1]['floor_guan'] - 1)
        self.assertEqual(perturb(K['mortality'], True)[0], [K['mortality'][0][0] + 1, K['mortality'][0][1] * 1.1 + 0.01])
        self.assertEqual(perturb(K['tiers'], True)[0], K['tiers'][0] + '·')
        self.assertEqual(K, load_spec().K)                                                  # 扰动的是副本


class PoolGuard(unittest.TestCase):
    def test_name_pool_smaller_than_pool_min_refuses_to_build(self):
        S = load_spec()
        S.K['pool_min'] = len(set(S.org.pool)) + 1
        with self.assertRaises(ValueError) as cm: World(spec=S)
        self.assertIn('pool_min', str(cm.exception))
        S.K['pool_min'] = len(set(S.org.pool))                                              # 恰好够：照常装配
        self.assertEqual(len(World(spec=S).pids), len(World().pids))


@unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开')
class LiveInScenarios(unittest.TestCase):
    """LIVE_IN 里的每个键，在它的场景里确实起作用（扰动 +1 或 -1，场景结果必须变）。"""
    base = {}

    @classmethod
    def base_sig(cls, name):
        if name not in cls.base: cls.base[name] = scenario_signature(name)
        return cls.base[name]

    def test_each_key_changes_its_scenario(self):
        dead = []
        for key, name in LIVE_IN.items():
            with self.subTest(key):
                for up in (True, False):
                    try:
                        moved = scenario_signature(name, perturbed_spec(key, up)) != self.base_sig(name)
                    except Exception:
                        moved = True                                                        # 扰动到装配或运行报错，也说明它在起作用
                    if moved: break
                else:
                    dead.append((key, name))
                    self.fail(f'{key} 在场景 {name} 里没有反应')
        self.assertEqual(dead, [])


@unittest.skipUnless(KSCAN, '很慢：TIANL_KSCAN=1 打开（进程池，约 2 分钟）')
class BaselineSensitivity(unittest.TestCase):
    def test_classification_matches_measurement(self):
        keys = list(load_spec().K)
        jobs = [(k, up) for k in keys for up in (True, False)]
        with ProcessPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as ex:
            got = dict(ex.map(baseline_hash, jobs, chunksize=1))
        moved = {k: any(got[(k, up)] != REF_HASH for up in (True, False)) for k in keys}
        self.assertEqual(sorted(k for k in keys if moved[k] and k in LIVE_IN), [], '这些键归在 LIVE_IN，可基准里其实有反应：挪到 BASELINE_LOUD')
        self.assertEqual(sorted(k for k in keys if not moved[k] and k in BASELINE_LOUD), [], '这些键归在 BASELINE_LOUD，可基准里其实没反应：挪到 LIVE_IN 并配场景')
        self.assertEqual(sorted(k for k in keys if not moved[k] and k not in LIVE_IN and k not in GUARD_ONLY), [])
        print('\nBASELINE_LOUD =', sorted(k for k in keys if moved[k]))


if __name__ == '__main__':
    unittest.main()
