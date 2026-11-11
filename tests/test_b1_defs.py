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

from tests.test_b1_common import REF_HASH, baseline_world
from tianl.core.calendar import Calendar
from tianl.defs import Defs
from tianl.kernel import World, load_kernel_defs, load_spec
from tianl.kernel.spec import KERNEL_CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
SLOW = os.environ.get('TIANL_SLOW') == '1'


def load_reference():
    spec = importlib.util.spec_from_file_location('shaolin_spike_ref', ROOT / 'reference' / 'shaolin_spike.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


REF = load_reference()


REF_FLOOR = load_spec().K['hh_shop'][0]['floor_guan']      # 取一次干净值（后面的测试会改别的副本）


def copy_defs(tmp, edit=lambda text: text):
    """把内核用的各类定义目录复制到 tmp（每个文件的内容过一遍 edit），返回 tmp。"""
    for cat in KERNEL_CATEGORIES:
        src = ROOT / 'defs' / cat
        if not src.is_dir(): continue
        for f in src.rglob('*.toml'):
            out = Path(tmp) / f.relative_to(ROOT / 'defs')
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(edit(f.read_text(encoding='utf-8')), encoding='utf-8')
    return tmp


class DefsMatchPrototype(unittest.TestCase):
    def test_kernel_defs_load_clean(self):
        d = load_kernel_defs(scope='shaolin')                  # 少林寺自己的定义没有问题（别的 scope 写进同一批目录的，不归内核管）
        self.assertEqual([p for p in d.problems if re.match(r'[a-z_]+:shaolin:', p)], [])
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

    def test_calendar_from_defs_equals_prototype(self):
        """defs 里的历法与原型自己的 cal() / cal_str() 逐日相同（二十年）；core 的模块级默认历法也是从 defs 读的，同样与原型相同。"""
        from tianl.core import calendar as core_calendar
        c = load_spec().cal
        for day in range(0, 20 * 360):
            self.assertEqual(c.cal(day), REF.cal(day), day)
            self.assertEqual(c.cal_str(day), REF.cal_str(day), day)
            self.assertEqual(core_calendar.cal(day), REF.cal(day), day)
            self.assertEqual(core_calendar.cal_str(day), REF.cal_str(day), day)

    def test_core_calendar_has_no_built_in_festivals(self):
        """core 里没有任何一座寺院的节日与收成日：Calendar 的四个字段没有缺省值，从 defs 构造时漏写也报错。"""
        from tianl.core import calendar as core_calendar
        self.assertFalse(hasattr(core_calendar, 'DEFAULT_FESTIVALS'))
        with self.assertRaises(TypeError):
            Calendar()
        with self.assertRaises(ValueError) as cm:
            Calendar.from_def({'festivals': {}, 'retreat': [[1, 1], [1, 2]], 'wheat_doy': 1})
        self.assertIn('millet_doy', str(cm.exception))
        d = {'festivals': {'2-3': '甲'}, 'retreat': [[1, 1], [1, 2]], 'wheat_doy': 1, 'millet_doy': 2}
        self.assertEqual(Calendar.from_def(d).cal(32)['festival'], '甲')              # 二月初三 = 年内第 32 日（0 起）：它读的是我给的字段

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
        d = load_kernel_defs(scope='shaolin')
        mine = lambda kind: [x for x in d.by_kind(kind) if x['id'].split(':')[1] == 'shaolin' and x.get('kernel', True)]   # 别的 scope（别的模块的原型世界）不归内核管
        by_id = [x['code'] for x in mine('place')]
        self.assertNotEqual(by_id, list(REF.PLACE_NAME))
        self.assertEqual([p[0] for p in load_spec().places], list(REF.PLACE_NAME))
        for kind in ('place', 'account', 'commodity', 'item', 'post'):
            orders = [x['order'] for x in mine(kind)]
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

    def test_kernel_false_definitions_stay_out_of_kernel_tables(self):
        """别的模块往同一 scope 加的场所，标 kernel = false 就不进内核的 place 表（不改状态哈希）。"""
        with tempfile.TemporaryDirectory() as tmp:
            for cat in KERNEL_CATEGORIES:
                src = ROOT / 'defs' / cat
                if not src.is_dir(): continue
                for f in src.rglob('*.toml'):
                    out = Path(tmp) / f.relative_to(ROOT / 'defs')
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(f.read_text(encoding='utf-8'), encoding='utf-8')
            extra = Path(tmp) / 'space' / 'extra.toml'
            extra.write_text('["place:shaolin:bath"]\ncode = "SH_BATH"\nname = "浴室"\naccess = "open"\nkernel = false\norder = 99\n', encoding='utf-8')
            spec = load_spec(scope='shaolin', root=tmp)
            self.assertNotIn('SH_BATH', [p[0] for p in spec.places])
            self.assertEqual(World(spec=spec).run(30).state_hash(), World().run(30).state_hash())

    def test_other_scopes_problems_do_not_break_this_kernel(self):
        """别的 scope（别的模块的原型世界）往内核类别目录里写的定义，哪怕有悬空引用、缺 code、缺 order，也不拖累少林寺的内核；
        严格加载（不给 scope）与它们自己的负责人用的完整加载器照样报。自己的定义出问题则照样报。"""
        broken = (
            '["post:other:cook"]\nname = "厨"\nsite = "place:other:nowhere"\nfacility = "facility:other:oven"\n'
            '["place:other:yard"]\nname = "院"\naccess = "open"\n'                      # 缺 code
        )
        with tempfile.TemporaryDirectory() as tmp:
            copy_defs(tmp)
            (Path(tmp) / 'post' / 'other.toml').write_text(broken, encoding='utf-8')
            with self.assertRaises(Exception) as cm: load_kernel_defs(tmp)               # 严格：照报
            self.assertIn('place:other:nowhere', str(cm.exception))
            spec = load_spec(root=tmp)                                                   # 按 scope：只看自己的
            self.assertEqual([p[0] for p in spec.places], list(REF.PLACE_NAME))
            self.assertEqual(World(spec=spec).run(30).state_hash(), World().run(30).state_hash())
            (Path(tmp) / 'post' / 'mine.toml').write_text('["post:shaolin:ghost"]\nname = "鬼"\nsite = "place:shaolin:nowhere"\n', encoding='utf-8')
            with self.assertRaises(Exception) as cm: load_spec(root=tmp)                 # 自己的定义有问题：照报
            self.assertIn('place:shaolin:nowhere', str(cm.exception))

    def test_missing_role_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            for cat in KERNEL_CATEGORIES:
                src = ROOT / 'defs' / cat
                if not src.is_dir(): continue
                for f in src.rglob('*.toml'):
                    out = Path(tmp) / f.relative_to(ROOT / 'defs')
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(f.read_text(encoding='utf-8').replace(':shaolin:', ':demo:'), encoding='utf-8')
            # 把“典座”岗位改个角色名（cook -> chef）：内核要用 cook 这个角色
            for f in Path(tmp).rglob('*.toml'):
                f.write_text(f.read_text(encoding='utf-8').replace('post:demo:cook', 'post:demo:chef'), encoding='utf-8')
            with self.assertRaises(Exception) as cm:
                load_spec(scope='demo', root=tmp)
            self.assertIn('T.cook', str(cm.exception))

    def test_new_scope_must_spell_out_its_own_calendar(self):
        """新寺院的历法漏写任何一个必填字段（四项历法字段、农事香期时刻表）都不行，装配时就报，缺哪个报哪个：没有任何地方会悄悄补上少林寺的节日与结夏期。"""
        for field in ('festivals', 'retreat', 'wheat_doy', 'millet_doy', 'sell_doys'):
            with self.subTest(field), tempfile.TemporaryDirectory() as tmp:
                copy_defs(tmp, lambda t: re.sub(rf'(?m)^{field} = .*$', '', t))
                with self.assertRaises(Exception) as cm:
                    load_spec(root=tmp)
                self.assertIn(field, str(cm.exception))
                self.assertIn('历法', str(cm.exception))
        with tempfile.TemporaryDirectory() as tmp:                           # 年长也不许乱写：内核按 360 日算
            copy_defs(tmp, lambda t: t.replace('year = 360', 'year = 300'))
            with self.assertRaises(Exception) as cm:
                load_spec(root=tmp)
            self.assertIn('year', str(cm.exception))

    def test_load_spec_gives_independent_copies(self):
        """改某个 World 的 K、品类、场所表……不得污染后来的 World（缓存里的原件、别的 World 的副本都不能变）。"""
        a = World()
        a.K['transfer_sla'] += 100
        a.K['tiers'].append('乱入')
        a.K['hh_shop'][0]['floor_guan'] += 7
        a.G[a.cm.staple].name = '改过的名'
        a.G[a.cm.fuel].use += 1
        a.S.org.canon.pop()
        a.S.places.append(('SH_X', 'x', 'open'))
        a.S.season.sell_doys = ()
        a.S.labels['reasons']['incense'] = '改过'
        a.pl.granary = 'XX'
        a.T.cook = '厨子'
        a.P['seed'] = 99
        b = World()
        ref = load_spec()
        for w in (b, World(spec=ref)):
            self.assertEqual(w.K['transfer_sla'], 20)
            self.assertEqual(w.K['tiers'], ['充足', '留意', '紧张', '告急', '断供'])
            self.assertEqual(w.K['hh_shop'][0]['floor_guan'], REF_FLOOR)
            self.assertNotEqual(w.G[w.cm.staple].name, '改过的名')
            self.assertEqual(w.G[w.cm.fuel].use, REF.GOODS[w.cm.fuel][3])
            self.assertEqual(len(w.S.org.canon), len(REF.CANON))
            self.assertNotIn('SH_X', [p[0] for p in w.S.places])
            self.assertTrue(w.S.season.sell_doys)
            self.assertNotEqual(w.S.labels['reasons']['incense'], '改过')
            self.assertEqual(w.pl.granary, 'SH_GRANARY')
            self.assertEqual(w.T.cook, '典座')
            self.assertEqual(w.P['seed'], REF.P['seed'])
        self.assertIsNot(load_spec(), load_spec())
        self.assertEqual(b.run(5).state_hash(), World().run(5).state_hash())

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
        D = load_kernel_defs(scope='shaolin')
        codes = {p[0] for p in S.places} | {a.code for a in S.accounts} | {i.code for i in S.items}
        cls.codes = codes
        cls.prefixes = {c.prefix for c in S.hh_classes} | {S.org.dorm.prefix}
        names = set(S.place_name.values()) | {p.name for p in S.posts} | set(S.org.halls) | {c.name for c in S.org.canon}
        names |= set(S.org.reserved) | {i.name for i in S.items} | {S.org.name} | set(S.K['damage_targets']) | set(S.K['tiers'])
        names |= {a.name for a in S.accounts if a.name} | {a.office for a in S.accounts if a.office}
        names |= {g.name for g in S.goods.values()} | set(S.cal.festivals.values()) | {c.label for c in S.hh_classes}
        names |= {v for v in S.labels.values() if isinstance(v, str)} | {gd.gen for gd in S.org.gens}
        names |= {S.scenario['visitor'][k] for k in ('name', 'hall', 'kind')} | {S.scenario['canon_probe']}   # 回归场景里的人名与人员类别也只能在 defs 里（visitor.org 与 where 的层名“外来香客”撞字，不查）
        cls.labels_nested = {v for k in ('reasons', 'grain_ledger') for v in S.labels[k].values()}
        for i in D.ids():
            d = D.get(i)
            if i.startswith('post:shaolin:'): names.add(d['name'])
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

    def test_no_ledger_reason_or_grain_category_literals(self):
        """钱账事由与粮账类别名（labels.reasons / labels.grain_ledger 的值）不许原样写在代码里（日报叙述里的同形词不算：只查整串相等）。"""
        bad = []
        for f in self.FILES:
            for ln, s in self.literals(f):
                if s in self.labels_nested: bad.append(f'{f.name}:{ln} {s!r}')
        self.assertEqual(bad, [])

    def test_no_name_pool_or_canon_text(self):
        for f in self.FILES:
            self.assertNotIn(self.pool[:20], f.read_text(encoding='utf-8'), f.name)

    def test_every_rule_parameter_is_read_by_the_kernel_and_none_is_missing(self):
        """110 项规则参数 K：defs 里的每一项都被内核代码读取（没有死参数），代码里读的每一项都在 defs 里（没有缺项）。
        有的分支基准里走不到（点检时辰、还粮比例、关键岗位空缺上限、减供档线），所以不能只靠哈希；这里按源码静态核对。"""
        src = '\n'.join(f.read_text(encoding='utf-8') for f in (ROOT / 'tianl' / 'kernel').glob('*.py') if f.name != 'spec.py')
        used = set(re.findall(r"K\[\s*['\"](\w+)['\"]\s*\]", src))
        keys = set(load_spec().K)
        self.assertEqual(sorted(keys - used), [], 'defs 里有内核从不读取的规则参数')
        self.assertEqual(sorted(used - keys), [], '内核读取了 defs 里没有的规则参数')

    def test_ledger_reasons_come_from_defs(self):
        """钱账事由（流水 reason）全部取自 labels.reasons：账上出现的每个事由都能在 defs 里找到（前缀型的取前缀）。"""
        S = load_spec()
        reasons = set(S.labels['reasons'].values())
        w = baseline_world()                                  # 预热 1 年 + 3 年的共享基准（只读）
        seen = {r[0] for r in w.x('SELECT DISTINCT reason FROM ledger')}
        stray = {r for r in seen if r not in reasons and not any(r.startswith(p) for p in reasons if p.endswith(':'))}
        self.assertEqual(sorted(stray), [])
        self.assertGreaterEqual(len(seen & reasons) + sum(1 for r in seen if any(r.startswith(p) for p in reasons if p.endswith(':'))), 12)

    def test_missing_ledger_reason_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            for cat in KERNEL_CATEGORIES:
                src = ROOT / 'defs' / cat
                if not src.is_dir(): continue
                for f in src.rglob('*.toml'):
                    out = Path(tmp) / f.relative_to(ROOT / 'defs')
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(f.read_text(encoding='utf-8').replace('\nincense = "香火钱"', '\nincense_x = "香火钱"'), encoding='utf-8')
            with self.assertRaises(Exception) as cm:
                load_spec(root=tmp)
            self.assertIn('incense', str(cm.exception))

    def test_missing_label_is_reported(self):
        """labels 顶层必备键（日报与路况用词）漏写，装配时就报，缺哪个报哪个。"""
        for key in ('snow_closure', 'temple_store', 'grain_market'):
            with self.subTest(key), tempfile.TemporaryDirectory() as tmp:
                copy_defs(tmp, lambda t: re.sub(rf'(?m)^{key} = .*$', '', t))
                with self.assertRaises(Exception) as cm:
                    load_spec(root=tmp)
                self.assertIn(key, str(cm.exception))
                self.assertIn('labels', str(cm.exception))

    def test_snow_closure_reason_comes_from_labels(self):
        """冬季大雪封路的原因（写进 route_closure.reason 与 ROAD_CLOSED 事件，是状态哈希口径）取自 labels.snow_closure，代码里没有这个字面量。"""
        base = baseline_world()
        reasons = {r[0] for r in base.x('SELECT reason FROM route_closure')}
        self.assertEqual(reasons, {load_spec().labels['snow_closure']})          # 基准里有四场大雪，原因都是它
        with tempfile.TemporaryDirectory() as tmp:
            copy_defs(tmp, lambda t: t.replace('snow_closure = "大雪封山"', 'snow_closure = "雪阻山路"'))
            w = World(spec=load_spec(root=tmp)).run(700)                          # 基准里第一场大雪在第 690 日
        rows = w.x('SELECT from_day, to_day, reason FROM route_closure').fetchall()
        self.assertEqual(rows, [(r[0], r[1], '雪阻山路') for r in base.x('SELECT from_day, to_day FROM route_closure WHERE from_day<700')])
        self.assertTrue(all('雪阻山路' in r[0] for r in w.x("SELECT payload FROM event_log WHERE type='ROAD_CLOSED'").fetchall()))
        text = '\n'.join(f.read_text(encoding='utf-8') for f in (ROOT / 'tianl' / 'kernel').glob('*.py'))
        self.assertNotIn('大雪封山', text)

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
        elif c == 'calendar': s.cal = NS(cal=REF.cal, cal_str=REF.cal_str, festivals={})   # 原型自己的 cal()
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
