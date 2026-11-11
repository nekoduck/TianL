"""内核规格（Spec）：把 defs 里某座寺院的定义装配成内核直接使用的只读对象。

内核代码里不出现任何少林寺专有的编号、名字与数值，一律从 Spec 取：

  S.pl / S.ac / S.cm / S.hh / S.T   场所、账户、品类、农户类别、岗位的“角色名 -> 运行时值”（定义编号的最后一段就是角色名）
  S.P / S.K                         参数 P 与规则参数 K（World(params=…) 只覆盖 P）
  S.goods / S.places / S.accounts   品类表、场所表、账户表（均按 order 排好，决定数据库插入次序，进而决定状态哈希）
  S.cal / S.season                  历法（tianl.core.Calendar）与农事香期时刻表
  S.org / S.posts / S.items / …     人事结构、岗位、独有物、值守班表、作息模板

定义里的 order 字段是原型字典的顺序。Defs.by_kind 按编号排序，不等于原型的插入顺序，所以这里一律按 (order, 编号) 排序。
新增另一座寺院：在 defs 下以另一个 scope 写同样的一组定义，再 load_spec(scope=…)；说明见 docs/KERNEL_DEFS.md。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

from ..core.calendar import Calendar
from ..defs import Defs, DefsError

DEFS_ROOT = Path(__file__).resolve().parents[2] / 'defs'
# 内核用到的定义类别目录（只加载它们，别的模块的定义文件有问题时不拖累内核）
KERNEL_CATEGORIES = ('calendar', 'space', 'economy', 'org', 'post', 'item', 'scenario')
META_KEYS = frozenset({'id', 'kind', '_file', 'parent', 'name', 'note', 'order'})


class Good:
    """一个品类。price/use/low/up 缺省为 None（如主粮：价随季节浮动、日用另算）。"""
    __slots__ = ('key', 'name', 'unit', 'price', 'use', 'low', 'up', 'prio', 'band', 'restock', 'consume_order',
                 'use_winter_extra', 'use_per_pilgrims', 'use_festival_mult', 'spoil_cap', 'role')

    def __init__(self, key, d):
        self.key, self.name, self.unit = key, d['name'], d['unit']
        self.price, self.use, self.low, self.up = d.get('price'), d.get('use'), d.get('low'), d.get('up')
        self.prio = d.get('prio', 0)
        self.band = tuple(d['band']) if 'band' in d else None
        self.restock = bool(d.get('restock', False))
        self.consume_order = d.get('consume_order', 0)
        self.use_winter_extra = d.get('use_winter_extra', 0)
        self.use_per_pilgrims = d.get('use_per_pilgrims', 0)
        self.use_festival_mult = d.get('use_festival_mult', 1)
        self.spoil_cap = d.get('spoil_cap')
        self.role = d.get('role')

    def as_tuple(self):
        return (self.name, self.unit, self.price, self.use, self.low, self.up, self.prio)


def load_kernel_defs(root=None):
    """只加载内核用到的类别目录（root 缺省为仓库的 defs/）。"""
    root = Path(root) if root else DEFS_ROOT
    d = Defs()
    for cat in KERNEL_CATEGORIES:
        sub = root / cat
        if sub.is_dir():
            for f in sorted(sub.rglob('*.toml')):
                d.add_file(f)
    d.validate()
    if d.problems:
        raise DefsError(d.problems)
    return d


def _scoped(defs, kind, scope):
    """某 scope 下某 kind 的全部定义，按 (order, 编号) 排序。"""
    rows = [d for d in defs.by_kind(kind) if d['id'].split(':')[1] == scope]
    return sorted(rows, key=lambda d: (d.get('order', 0), d['id']))


def _role(d):
    return d.get('role') or d['id'].rsplit(':', 1)[1]


class Spec:
    """由 defs 装配的内核规格。构造请用 Spec.from_defs / load_spec。"""

    @classmethod
    def from_defs(cls, defs, scope='shaolin'):
        s = cls()
        s.scope = scope
        g = lambda kind, name: defs.get(f'{kind}:{scope}:{name}')
        code_of = lambda ref: defs.get(ref)['code']
        s._code_of = code_of
        s._ref_code = {i: defs.get(i)['code'] for i in defs.ids() if 'code' in defs.get(i)}

        # ---- 历法
        cd = g('calendar', 'main')
        s.cal = Calendar.from_def(cd)
        s.season = NS(
            crops=[(c['flag'], c['name']) for c in cd['crops']],
            winter_months=tuple(cd['winter_months']), busy_windows=[tuple(w) for w in cd['busy_windows']],
            pilgrim_winter=cd['pilgrim_winter'], pilgrim_busy=cd['pilgrim_busy'], pilgrim_shuowang=cd['pilgrim_shuowang'],
            festival_mult={f['name']: f['mult'] for f in cd['pilgrim_festival']},
            donor_festivals=tuple(cd['donor_festivals']), charity_festival=cd['charity_festival'],
            grain_season=[(w['from'], w['to'], w['factor']) for w in cd['grain_season']],
            new_year_doy=cd['new_year_doy'], year_end_doy=cd['year_end_doy'],
            sell_doys=tuple(cd['sell_doys']), shop_doys=tuple(cd['shop_doys']),
            after_harvest_doys=tuple(cd['after_harvest_doys']), return_doys=tuple(cd['return_doys']),
            recruit_doy=cd['recruit_doy'], cloth_due_doys=tuple(cd['cloth_due_doys']),
            cloth_hold_windows=[tuple(w) for w in cd['cloth_hold_windows']],
            wheat_doy=cd['wheat_doy'], millet_doy=cd['millet_doy'])

        # ---- 参数
        s.P = {k: v for k, v in g('param', 'main').items() if k not in META_KEYS}
        K = {k: v for k, v in g('param', 'rules').items() if k not in META_KEYS}
        K['hh_shop'] = [dict(h, c=defs.get(h['c'])['code']) for h in K['hh_shop']]
        s.K = K
        s.labels = {k: v for k, v in g('param', 'labels').items() if k not in META_KEYS}

        # ---- 场所
        places = _scoped(defs, 'place', scope)
        s.places = [(p['code'], p['name'], p['access']) for p in places]
        s.place_name = {p['code']: p['name'] for p in places}
        s.pl = NS(**{_role(p): p['code'] for p in places})

        # ---- 账户
        accts = _scoped(defs, 'account', scope)
        s.accounts = [NS(code=a['code'], boundary=a.get('boundary', 0), name=a.get('name'), opening_cash=a.get('opening_cash'),
                         year_end_cap=a.get('year_end_cap'), shop=bool(a.get('shop')), office=a.get('office'),
                         virtual=bool(a.get('virtual')), role=_role(a)) for a in accts]
        s.ac = NS(**{a.role: a.code for a in s.accounts})
        s.account_name = {a.code: a.name for a in s.accounts}
        s.shop_accounts = [a.code for a in s.accounts if a.shop]

        # ---- 品类
        s.goods = {}
        s.cm = NS()
        for d in _scoped(defs, 'commodity', scope):
            gd = Good(d['code'], d)
            s.goods[gd.key] = gd
            if gd.role:
                setattr(s.cm, gd.role, gd.key)
        s.bands = {k: gd.band for k, gd in s.goods.items() if gd.band}
        s.restock = [k for k, gd in s.goods.items() if gd.restock]
        s.consume_order = [k for k, gd in sorted(s.goods.items(), key=lambda kv: kv[1].consume_order) if gd.consume_order > 0]
        oo = g('param', 'opening')
        s.opening_stock = []
        for e in oo['stock']:
            c = defs.get(e['c'])['code']
            if 'qty' in e:
                q = ('qty', e['qty'])
            elif 'days' in e:
                q = ('days', e['days'])
            else:
                q = ('band', e['band'])
            s.opening_stock.append(NS(owner=code_of(e['owner']), place=code_of(e['place']), c=c, kind=q[0], v=q[1]))

        # ---- 农户
        hd = g('param', 'households')
        s.hh_grain_days = hd['grain_days']
        s.hh_classes = [NS(role=c['role'], code=c['code'], label=c['label'], prefix=c['prefix'], count=c['count'], mu=c['mu'],
                           place=code_of(c['place']), cash=c['cash']) for c in hd['classes']]
        s.hh = NS(**{c.role: c.code for c in s.hh_classes})
        s.hh_label = {c.code: c.label for c in s.hh_classes}
        s.hh_special = {e['id']: (e['members'], e['name']) for e in hd['special']}

        # ---- 岗位
        posts = _scoped(defs, 'post', scope)
        org = g('org', 'main')
        s.deputy_prefix = org['deputy_prefix']
        s.posts = [NS(name=p['name'], role=_role(p), site=code_of(p['site']), critical=p.get('critical'), hall=p.get('hall')) for p in posts]
        s.T = NS(**{p.role: p.name for p in s.posts})
        s.site_of = {p.name: p.site for p in s.posts}
        s.critical = [p.name for p in sorted((p for p in s.posts if p.critical), key=lambda p: p.critical)]
        s.post_hall = {p.name: p.hall for p in s.posts if p.hall}
        name_of_post = {p['id']: p['name'] for p in posts}

        # ---- 组织与人事
        sc = org['succession']
        s.org = NS(
            name=org['name'], account=code_of(org['account']), default_hall=org['default_hall'], deputy_prefix=org['deputy_prefix'],
            visitor_gen=org['visitor_gen'], visitor_place=code_of(org['visitor_place']), visitor_act=org['visitor_act'],
            lock_slots=org['lock_slots'], elders_home=code_of(org['elders_home']), discipline_place=code_of(org['discipline_place']),
            dorm=NS(**org['dorm']), recruit=NS(**org['recruit']), roster_stride=org['roster_stride'], roster_shift=org['roster_shift'],
            canon_masters=[(m['name'], m['master']) for m in org['canon_masters']],
            gens=[NS(gen=x['gen'], n=x['n'], age=tuple(x['age']), senior=bool(x.get('senior')), master_gen=x.get('master_gen'),
                     quota=[(q['hall'], q['n']) for q in x.get('quota', [])]) for x in org['gens']],
            halls={h['name']: code_of(h['place']) for h in org['halls']},
            canon=[NS(name=c['name'], gen=c['gen'], age=c['age'], hall=c['hall'], home=code_of(c['home']) if 'home' in c else None)
                   for c in org['canon']],
            succession=NS(min_age=sc['min_age'], hall_rank=sc['hall_rank'], other_rank=sc['other_rank']),
            appointments=[NS(post=name_of_post[a['post']], deputy=bool(a.get('deputy')), canon=a.get('canon'), pick=a.get('pick'),
                             gen=a.get('gen'), hall=a.get('hall'), index=a.get('index', 0)) for a in org['appointments']],
            reserved=list(org['names']['reserved']), pool=org['names']['pool'])

        # ---- 值守班表与作息模板
        rd = g('rule', 'roster')
        s.roster = [NS(label=r['label'], place=code_of(r['place']), slots=tuple(r['slots']), n=r['n'], hall=r['hall'], gen=r['gen'])
                    for r in rd['posts']]
        s.timetable = [s._compile_rule(r, name_of_post) for r in g('rule', 'timetable')['rules']]

        # ---- 独有物
        s.items = [NS(code=i['code'], name=i['name'], home=code_of(i['home']), keeper=name_of_post[i['keeper']],
                      custodian=i['custodian']) for i in _scoped(defs, 'item', scope)]

        # ---- 回归场景（工具用）
        try:
            s.scenario = {k: v for k, v in g('scenario', 'regress').items() if k not in META_KEYS}
        except KeyError:
            s.scenario = {}
        return s

    def code(self, ref):
        """定义编号 -> 运行时钥匙（place / account / commodity / item 的 code）。"""
        return self._ref_code[ref]

    def _compile_rule(self, r, name_of_post):
        def when(w):
            w = dict(w or {})
            if 'base' in w:
                w['base'] = frozenset(name_of_post[b] for b in w['base'])
            return w

        def place(o):
            p = o['place']
            if p in ('$home', '$site'):
                return (p[1:], None)
            if p == '$hall':
                return ('hall', self._code_of(o['fallback']) if 'fallback' in o else None)
            return ('code', self._code_of(p))
        return NS(when=when(r.get('when')),
                  out=[NS(when=when(o.get('when')), place=place(o), act=o['act']) for o in r['out']])

    # ------------------------------------------------------------------ 与原型常量的对照视图（测试用）
    def constants_view(self):
        """还原成原型 shaolin_spike.py 的常量形状，用于逐项对照。"""
        K = self.K
        return dict(
            P=dict(self.P),
            GOODS={k: g.as_tuple() for k, g in self.goods.items()},
            SHOP_BANDS=dict(self.bands),
            CRITICAL=list(self.critical),
            SITE=dict(self.site_of),
            HALLPLACE=dict(self.org.halls),
            PLACE_NAME=dict(self.place_name),
            CANON=[(c.name, c.gen, c.age, c.hall) for c in self.org.canon],
            RESERVED=set(self.org.reserved),
            POOL=self.org.pool,
            TIERS=list(K['tiers']),
            MULT=dict(zip(K['tiers'], K['tier_mult'])),
            festivals=dict(self.cal.festivals),
            retreat=tuple(self.cal.retreat), wheat_doy=self.cal.wheat_doy, millet_doy=self.cal.millet_doy)


_cache: dict = {}


def load_spec(defs=None, scope='shaolin', root=None) -> Spec:
    """装配规格。defs 缺省时从 root（缺省仓库 defs/）加载内核类别目录；结果按 (root, scope) 缓存（Spec 只读）。"""
    if defs is not None:
        return Spec.from_defs(defs, scope)
    key = (str(root or DEFS_ROOT), scope)
    if key not in _cache:
        _cache[key] = Spec.from_defs(load_kernel_defs(root), scope)
    return _cache[key]
