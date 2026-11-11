"""B1 验收：defs/*.toml 与原型常量逐项一致；内核代码里没有少林寺专有常量；换一个 scope 照样能跑。

  python3 -m unittest tests.test_b1_defs                   # 默认（几秒）
  TIANL_SLOW=1 python3 -m unittest tests.test_b1_defs      # 再逐类把常量换回原型的值，各复核一次基准哈希
"""
import ast
import copy
import importlib.util
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from tianl.core.calendar import Calendar
from tianl.defs import Defs
from tianl.kernel import World, load_kernel_defs, load_spec
from tianl.kernel.spec import KERNEL_CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
SLOW = os.environ.get('TIANL_SLOW') == '1'
REF_HASH = '49f6ddde04dfa7f5'


def load_reference():
    spec = importlib.util.spec_from_file_location('shaolin_spike_ref', ROOT / 'reference' / 'shaolin_spike.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


REF = load_reference()


class DefsMatchPrototype(unittest.TestCase):
    def test_kernel_defs_load_clean(self):
        d = load_kernel_defs()
        self.assertEqual(d.problems, [])
        self.assertGreater(len(d), 70)

    def test_constants_equal_prototype(self):
        v = load_spec().constants_view()
        self.assertEqual(v['P'], REF.P)
        self.assertEqual(v['GOODS'], REF.GOODS)
        self.assertEqual(list(v['GOODS']), list(REF.GOODS))               # 顺序也要一致
        self.assertEqual(v['SHOP_BANDS'], REF.SHOP_BANDS)
        self.assertEqual(list(v['SHOP_BANDS']), list(REF.SHOP_BANDS))
        self.assertEqual(v['CRITICAL'], REF.CRITICAL)                      # 次序决定检查次序
        self.assertEqual(v['SITE'], REF.SITE)
        self.assertEqual(v['HALLPLACE'], REF.HALLPLACE)
        self.assertEqual(v['PLACE_NAME'], REF.PLACE_NAME)
        self.assertEqual(list(v['PLACE_NAME']), list(REF.PLACE_NAME))      # place 表的插入次序
        self.assertEqual(v['CANON'], REF.CANON)
        self.assertEqual(v['RESERVED'], REF.RESERVED)
        self.assertEqual(v['POOL'], REF.POOL)                              # 字序不得改动
        self.assertEqual(v['TIERS'], REF.TIERS)
        self.assertEqual(v['MULT'], REF.MULT)
        self.assertEqual(v['festivals'], {(1, 1): '元日', (1, 15): '上元', (2, 15): '涅槃日', (4, 8): '佛诞', (4, 15): '结夏',
                                          (7, 15): '盂兰盆', (12, 8): '腊八'})
        self.assertEqual((v['retreat'], v['wheat_doy'], v['millet_doy']), (((4, 15), (7, 15)), 125, 245))

    def test_calendar_from_defs_equals_default(self):
        c = load_spec().cal
        d = Calendar()
        for day in range(0, 3 * 360):
            self.assertEqual(c.cal(day), d.cal(day))
            self.assertEqual(c.cal_str(day), d.cal_str(day))

    def test_accounts_and_opening_follow_prototype(self):
        S = load_spec()
        self.assertEqual([(a.code, a.boundary) for a in S.accounts if not a.virtual],
                         [('EQUITY', 1), ('PORT', 1), ('PILGRIMS', 1), ('TOWN_BG', 1), ('STATE', 1), ('NEIGHBOR', 1),
                          ('ORG_SH', 0), ('SHOP_GRAIN', 0), ('SHOP_GEN', 0)])
        self.assertEqual([(a.code, a.opening_cash) for a in S.accounts if a.opening_cash], [('ORG_SH', 600), ('SHOP_GRAIN', 800), ('SHOP_GEN', 500)])
        w = World()
        # 开局存货：与原型 _populate 的 produce 序列一致
        self.assertEqual(w.qty('ORG_SH', 'SH_GRANARY', 'grain'), 400 * REF.SHI)
        self.assertEqual(w.qty('ORG_SH', 'EST_GRANARY', 'grain'), 900 * REF.SHI)
        for c, g in REF.GOODS.items():
            if g[3]: self.assertEqual(w.qty('ORG_SH', 'SH_STORE', c), g[3] * {'firewood': 12, 'veg': 2}.get(c, 45), c)
        for c, (lo, hi) in REF.SHOP_BANDS.items(): self.assertEqual(w.qty('SHOP_GEN', 'DF', c), hi, c)

    def test_order_field_not_id_order(self):
        """Defs.by_kind 按编号排序，不等于原型的字典顺序——内核必须按 order 字段排。"""
        d = load_kernel_defs()
        by_id = [x['code'] for x in d.by_kind('place')]
        self.assertNotEqual(by_id, list(REF.PLACE_NAME))
        self.assertEqual([p[0] for p in load_spec().places], list(REF.PLACE_NAME))
        for kind in ('place', 'account', 'commodity', 'item', 'post'):
            orders = [x['order'] for x in d.by_kind(kind)]
            self.assertEqual(len(set(orders)), len(orders), f'{kind} 的 order 有重复')

    def test_new_scope_runs_identically(self):
        """把整套定义换个 scope（shaolin -> demo）照样装得起来、跑出同样的世界：内核里没有写死 scope。"""
        with tempfile.TemporaryDirectory() as tmp:
            for cat in KERNEL_CATEGORIES:
                src = ROOT / 'defs' / cat
                if not src.is_dir(): continue
                for f in src.rglob('*.toml'):
                    out = Path(tmp) / f.relative_to(ROOT / 'defs')
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(f.read_text(encoding='utf-8').replace(':shaolin:', ':demo:'), encoding='utf-8')
            spec = load_spec(scope='demo', root=tmp)
            self.assertEqual(spec.scope, 'demo')
            a, b = World().run(120), World(spec=spec).run(120)
            self.assertEqual(a.state_hash(), b.state_hash())

    def test_params_override_and_seed_matters(self):
        a, b = World().run(10), World({'seed': 7}).run(10)
        self.assertNotEqual(a.state_hash(), b.state_hash())
        self.assertEqual(World({'seed': 7}).run(10).state_hash(), b.state_hash())
        w = World({'n_tenant': 10})
        self.assertEqual(w.x("SELECT COUNT(*) FROM household WHERE kind='tenant'").fetchone()[0], 10)


class NoShaolinConstantsInCode(unittest.TestCase):
    """硬验收 (e)：少林寺专有的编号、名字、数值只能出现在 defs 与测试里，不能出现在内核代码与回归工具里。"""
    FILES = sorted((ROOT / 'tianl' / 'kernel').glob('*.py')) + [ROOT / 'tools' / 'shaolin_regress.py']

    @classmethod
    def setUpClass(cls):
        S = load_spec()
        D = load_kernel_defs()
        codes = {p[0] for p in S.places} | {a.code for a in S.accounts} | {i.code for i in S.items}
        cls.codes = codes
        cls.prefixes = {c.prefix for c in S.hh_classes} | {S.org.dorm.prefix}
        names = set(S.place_name.values()) | {p.name for p in S.posts} | set(S.org.halls) | {c.name for c in S.org.canon}
        names |= set(S.org.reserved) | {i.name for i in S.items} | {S.org.name} | set(S.K['damage_targets']) | set(S.K['tiers'])
        names |= {a.name for a in S.accounts if a.name} | {a.office for a in S.accounts if a.office}
        names |= {g.name for g in S.goods.values()} | set(S.cal.festivals.values()) | {c.label for c in S.hh_classes}
        names |= {v for v in S.labels.values() if isinstance(v, str)} | {gd.gen for gd in S.org.gens}
        for i in D.ids():
            d = D.get(i)
            if i.startswith('post:'): names.add(d['name'])
        cls.names = {n for n in names if n and len(n) >= 2}
        cls.pool = S.org.pool

    @staticmethod
    def literals(path):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                b = node.body
                if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                    docs.add(id(b[0].value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                yield node.lineno, node.value

    def test_no_codes_anywhere_in_text(self):
        """编号（SH_LIBRARY、ORG_SH、SHOP_GRAIN、HH_T、SH_DORM_ …）在代码的任何位置（含注释、文档字符串）都不许出现。"""
        pat = re.compile(r'(?<![A-Za-z0-9_])(?:' + '|'.join(re.escape(c) for c in sorted(self.codes, key=len, reverse=True)) + r')(?![A-Za-z0-9_])'
                         r'|(?<![A-Za-z0-9_])(?:' + '|'.join(re.escape(p) for p in self.prefixes) + ')')
        bad = []
        for f in self.FILES:
            for i, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
                m = pat.search(line)
                if m: bad.append(f'{f.name}:{i} {m.group(0)}')
        self.assertEqual(bad, [])

    def test_no_names_in_string_literals(self):
        """场所名、岗位名、院堂名、要角名、独有物名、品类名、账户名、节日名……不许写在代码的字符串字面量里（注释与文档字符串除外）。"""
        bad = []
        for f in self.FILES:
            for ln, s in self.literals(f):
                hit = [n for n in self.names if n in s] + [c for c in self.codes if c in s.replace('_', ' ').split() or c == s]
                if hit: bad.append(f'{f.name}:{ln} {s[:30]!r} {sorted(set(hit))}')
        self.assertEqual(bad, [])

    def test_no_name_pool_or_canon_text(self):
        for f in self.FILES:
            self.assertNotIn(self.pool[:20], f.read_text(encoding='utf-8'), f.name)

    def test_defs_do_hold_them(self):
        """反过来：这些常量确实在 defs 里。"""
        text = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'defs').rglob('*.toml'))
        for code in ('SH_LIBRARY', 'ORG_SH', 'SHOP_GRAIN', 'EST_GRANARY', 'SH_DORM_', 'HH_T', 'IT_YJJ'):
            self.assertIn(code, text)


def hybrid(spec, classes):
    """把 spec 里指定类别的常量换回原型的值（用来逐类复核：defs 与原型常量等价）。"""
    s = copy.copy(spec)
    s.org, s.K = copy.copy(spec.org), dict(spec.K)
    for c in classes:
        if c == 'P': s.P = dict(REF.P)
        elif c == 'GOODS':
            s.goods = {}
            for k, (name, unit, price, use, low, up, prio) in REF.GOODS.items():
                g = copy.copy(spec.goods[k]); g.name, g.unit, g.price, g.use, g.low, g.up, g.prio = name, unit, price, use, low, up, prio
                s.goods[k] = g
        elif c == 'SHOP_BANDS': s.bands = dict(REF.SHOP_BANDS)
        elif c == 'CRITICAL': s.critical = list(REF.CRITICAL)
        elif c == 'SITE': s.site_of = dict(REF.SITE)
        elif c == 'HALLPLACE': s.org.halls = dict(REF.HALLPLACE)
        elif c == 'PLACE_NAME':
            s.places = [(code, name, 'locked_night' if code in ('SH_LIBRARY', 'SH_GRANARY') else 'open') for code, name in REF.PLACE_NAME.items()]
            s.place_name = dict(REF.PLACE_NAME)
        elif c == 'CANON': s.org.canon = [NS(name=n, gen=g, age=a, hall=h, home='SH_ABBOT' if n == '玄慈' else None) for n, g, a, h in REF.CANON]
        elif c == 'RESERVED': s.org.reserved = list(REF.RESERVED)
        elif c == 'POOL': s.org.pool = REF.POOL
        elif c == 'TIERS': s.K['tiers'], s.K['tier_mult'] = list(REF.TIERS), [REF.MULT[t] for t in REF.TIERS]
        elif c == 'calendar': s.cal = Calendar()           # core 的默认历法就是 v0.2 原样
        else: raise KeyError(c)
    return s


CLASSES = ['P', 'GOODS', 'SHOP_BANDS', 'CRITICAL', 'SITE', 'HALLPLACE', 'PLACE_NAME', 'CANON', 'RESERVED', 'POOL', 'TIERS', 'calendar']


class MigrationStepwise(unittest.TestCase):
    def test_hybrid_helper_is_sound_for_one_short_class(self):
        """（快）把两类常量换回原型值，跑 60 日，与纯 defs 的哈希相同。"""
        a = World().run(60)
        b = World(spec=hybrid(load_spec(), ['P', 'POOL'])).run(60)
        self.assertEqual(a.state_hash(), b.state_hash())

    @unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开')
    def test_each_constant_class_keeps_baseline_hash(self):
        spec = load_spec()
        for c in CLASSES:
            with self.subTest(c):
                self.assertEqual(World(spec=hybrid(spec, [c])).run(360 * 4).state_hash(), REF_HASH)

    @unittest.skipUnless(SLOW, '慢测试：TIANL_SLOW=1 打开')
    def test_all_classes_at_once_keep_baseline_hash(self):
        self.assertEqual(World(spec=hybrid(load_spec(), CLASSES)).run(360 * 4).state_hash(), REF_HASH)


if __name__ == '__main__':
    unittest.main()
