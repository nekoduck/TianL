#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《天龙世界》少林寺世界基座 · 验证原型 (spike)

目的: 用最少的代码把实现方案里的关键设计实际跑一遍, 校准参数, 找出设计漏洞。
覆盖: M0 (时钟/日历/事件日志/不变量/状态哈希) + M1 (钱粮闭环、订单生命周期、降级阶梯)
      + M2/M4 的最小子集 (僧众生成、师承、继任、作息函数、值守排班、独有物、物理/规范两层约束)。
没做: 命令层的完整封装(这里各阶段直接调用 pay/move/produce/consume 四个原语)、武学、戒律流程、
      人口出生婚配、全部地点与路网。这些见方案正文。
只用 Python 标准库。

用法:
  python3 shaolin_spike.py            # 基准: 预热 1 年 + 运行 3 年
  python3 shaolin_spike.py --all      # 基准 + 全部扰动实验 + 人物/独有物测试
"""
import sqlite3, hashlib, json, time, argparse, math
from collections import defaultdict

SHI, GUAN, YEAR = 1000, 1000, 360          # 1 石 = 1000 合; 1 贯 = 1000 文; 1 年 = 360 日
SLOTS = '子丑寅卯辰巳午未申酉戌亥'
TERMS = ('立春 雨水 惊蛰 春分 清明 谷雨 立夏 小满 芒种 夏至 小暑 大暑 '
         '立秋 处暑 白露 秋分 寒露 霜降 立冬 小雪 大雪 冬至 小寒 大寒').split()
MONTHS = '正二三四五六七八九十冬腊'
NUM = '一二三四五六七八九十'
TIERS = ['充足', '留意', '紧张', '告急', '断供']
MULT = {'充足': 1.0, '留意': 1.0, '紧张': 0.8, '告急': 0.6, '断供': 0.6}
LIVE = ('待接', '已接', '进行中', '受阻')
LIVE_SQL = "('待接','已接','进行中','受阻')"

P = dict(
    seed=20261110,
    monks=300, guest_cap=30, guest_rate=0.05,
    ration_monk=15, ration_folk=13,            # 合/人/日
    yield_net=1.2, rent_share=0.5, tax=0.1,    # 亩产(石/亩/年, 已扣种子)、分成租、两税(石/亩/年)
    temple_mu=4000,
    n_tenant=80, n_owner=25, n_wood=15,
    grain_price=1000,                          # 文/石 (基准)
    pilgrims=30, alms_each=30,                 # 平日香客数、人均香火钱(文)
    donor_prob=0.15, donor_gift=20 * GUAN, rite_prob=2 / 30, rite_fee=5 * GUAN,
    treasury_target=600 * GUAN,
    convoy=60 * SHI,                           # 庄仓 -> 寺库 每日车队运量
    wage=100, hh_misc=500, hh_salt=8, hh_cloth=1,          # 家用每年两次, 各为半年量
    town_bg_income=120,                        # 樵菜户每人每月卖给县城背景需求的收入(文)
    snow_prob=0.015,                           # 冬季每日大雪封山概率
)

# 品类: (名, 单位, 单价/文, 寺院日用量, 补货线/天, 补到/天, 缺钱时的审批优先级)
GOODS = {
    'grain':    ('粮', '合', None, None, None, None, 0),
    'firewood': ('柴炭', '担', 40, 8, 10, 17, 1),
    'veg':      ('蔬', '担', 30, 5, 1, 3, 2),
    'oilsalt':  ('油盐', '斤', 40, 5, 20, 50, 3),
    'medicine': ('药材', '剂', 200, 1, 20, 50, 4),
    'incense':  ('香烛', '份', 30, 4, 20, 50, 5),
    'paper':    ('纸墨', '份', 100, 1, 20, 50, 6),
    'cloth':    ('布', '匹', 1000, 0, 0, 0, 7),
    'timber':   ('木石料', '料', 500, 0, 0, 0, 8),
}
SHOP_BANDS = dict(oilsalt=(300, 900), medicine=(60, 200), incense=(120, 400),
                  paper=(50, 160), cloth=(80, 330), timber=(60, 200))
CRITICAL = ['方丈', '监院', '典座', '库头', '庄主', '知客', '藏主', '直岁', '维那']
SITE = {'方丈': 'SH_ABBOT', '首座': 'SH_ZEN', '监院': 'SH_OFFICE', '维那': 'SH_HALL', '典座': 'SH_KITCHEN',
        '直岁': 'SH_GROUNDS', '库头': 'SH_GRANARY', '知客': 'SH_GUEST', '藏主': 'SH_LIBRARY',
        '延寿堂主': 'SH_INFIRM', '庄主': 'EST', '园头': 'SH_GARDEN', '化主': 'SH_OFFICE',
        '戒律院首座': 'SH_JIELV', '达摩院首座': 'SH_DAMO', '菩提院首座': 'SH_PUTI'}
HALLPLACE = {'达摩院': 'SH_DAMO', '罗汉堂': 'SH_LUOHAN', '戒律院': 'SH_JIELV', '般若堂': 'SH_BORE',
             '菩提院': 'SH_PUTI', '证道院': 'SH_ZHENGDAO', '藏经阁': 'SH_LIBRARY'}
PLACE_NAME = {'SH': '少林寺', 'SH_GATE': '山门', 'SH_HALL': '大雄宝殿', 'SH_FATANG': '法堂', 'SH_ZEN': '禅堂',
              'SH_REFECTORY': '斋堂', 'SH_KITCHEN': '香积厨', 'SH_GRANARY': '粮库', 'SH_STORE': '杂库',
              'SH_OFFICE': '库司', 'SH_ABBOT': '方丈院', 'SH_DAMO': '达摩院', 'SH_LUOHAN': '罗汉堂',
              'SH_JIELV': '戒律院', 'SH_BORE': '般若堂', 'SH_PUTI': '菩提院', 'SH_ZHENGDAO': '证道院',
              'SH_LIBRARY': '藏经阁', 'SH_INFIRM': '延寿堂', 'SH_GUEST': '客堂', 'SH_GARDEN': '菜园',
              'SH_YARD': '练武场', 'SH_GROUNDS': '寺内各处', 'SH_ELDERS': '长老寮', 'SH_ROAD': '少室山道',
              'EST': '柏谷庄', 'EST_GRANARY': '庄仓', 'VIL': '少室山脚村', 'DF': '登封县城', 'PORT': '洛阳方向'}
# 原著要角 (凭记忆, 落正式数据前需对照原文)
CANON = [('玄慈', '玄', 62, '方丈院'), ('玄寂', '玄', 60, '戒律院'), ('玄难', '玄', 61, '达摩院'),
         ('玄苦', '玄', 63, '证道院'), ('慧轮', '慧', 48, '清众'), ('虚竹', '虚', 24, '清众'), ('缘根', '缘', 45, '清众')]
RESERVED = {'玄慈', '玄寂', '玄难', '玄苦', '玄痛', '玄渡', '玄悲', '玄生', '玄因', '玄澄', '玄石', '玄垢',
            '慧轮', '慧真', '慧观', '虚竹'}
POOL = ('净明觉悟智海定真如法云山泉松月灯镜心性德行愿忍静观照圆通达道常乐安宁广清凉光严华藏宝远深诚信义仁'
        '勇毅恒谦和顺平正方直素淡闲逸怀谷风雷雨露霜雪河岳岩峰岭林木枫柏桐梅莲苇舟桥钟磬度果尚相色受想识闻'
        '思修证彻见本元始终永寿福根尘劫刹慈能持戒施善缘了凡朗澈湛渊泓润济普贤文殊迦叶耆宿晦晓昙'
        '坚澄湖渚汀洲峦嶂霞霁晴岚溪涧潭瀑芝荃蘅芷杉槐榆楠')


def rnd(*keys):
    """按键现算的确定性随机数: 与调用顺序无关, 支持用到才算。"""
    h = hashlib.sha256('|'.join(map(str, keys)).encode()).digest()
    return int.from_bytes(h[:8], 'big') / 2 ** 64


def dom_name(d):
    if d <= 10: return '初' + NUM[d - 1]
    if d < 20: return '十' + NUM[d - 11]
    if d == 20: return '二十'
    if d < 30: return '廿' + NUM[d - 21]
    return '三十'


def cal(day):
    y, doy = divmod(day, YEAR)
    m, d = doy // 30 + 1, doy % 30 + 1
    fest = {(1, 1): '元日', (1, 15): '上元', (2, 15): '涅槃日', (4, 8): '佛诞', (4, 15): '结夏',
            (7, 15): '盂兰盆', (12, 8): '腊八'}.get((m, d))
    return dict(day=day, year=y, doy=doy, month=m, dom=d, term=TERMS[doy // 15], festival=fest,
                shuowang=d in (1, 15), retreat=(4, 15) <= (m, d) <= (7, 15),
                wheat=doy == 125, millet=doy == 245)


def cal_str(day):
    c = cal(day)
    y = '预热年' if c['year'] == 0 else f"第{c['year']}年"
    return f"{y}{MONTHS[c['month'] - 1]}月{dom_name(c['dom'])}"


def pilgrim_factor(c):
    f = 1.0
    if c['month'] in (11, 12, 1): f = 0.6
    if 120 <= c['doy'] < 135 or 240 <= c['doy'] < 255: f = 0.5      # 农忙
    if c['shuowang']: f *= 3
    return f * {'元日': 2, '上元': 1.34, '佛诞': 10, '盂兰盆': 1.67, '腊八': 6.7}.get(c['festival'], 1)


def shi(q): return f'{q / SHI:.1f} 石'
def guan(m): return f'{m / GUAN:.1f} 贯'


class World:
    def __init__(self, params=None):
        self.P = dict(P); self.P.update(params or {})
        self.db = sqlite3.connect(':memory:'); self.db.isolation_level = None
        self.x = self.db.execute
        self.day = 0
        self.net = defaultdict(int)        # 各品类累计净流入 (物守恒的对账基准)
        self.flows = defaultdict(int)      # (年, 品类, 类别) -> 数量
        self.tg = defaultdict(int)         # 寺院粮食账: (年, 类别) -> 合
        self.viol, self.series = [], []
        self.yield_override, self.pilgrim_boost = {}, {}
        self.price_factor = 1.0
        self.tier, self.guests, self.pilgrims_today = '充足', 0, 0
        self.road_ev = self.block_ev = None
        self.block_c, self.cloth_due, self.last_alms = {}, 0, -999
        self.vacant, self.vac_days = {}, defaultdict(int)
        self.cnt = defaultdict(int)
        self.hooks = defaultdict(list)
        self.pids, self.names, self.pcache = [], set(RESERVED), {}
        self._schema()
        self.x('BEGIN'); self._populate(); self._people(); self.make_roster(0); self.x('COMMIT')

    # ------------------------------------------------------------------ 基础设施
    def u(self, *k): return rnd(self.P['seed'], *k)

    @property
    def year(self): return self.day // YEAR

    def _schema(self):
        self.db.executescript('''
        CREATE TABLE place(id TEXT PRIMARY KEY, name TEXT, access TEXT);
        CREATE TABLE route_closure(route TEXT, from_day INT, to_day INT, reason TEXT);
        CREATE TABLE person(id TEXT PRIMARY KEY, name TEXT, kind TEXT, gen TEXT, age INT, org TEXT, hall TEXT,
                            home TEXT, master TEXT, status TEXT, joined INT, died INT, canon INT);
        CREATE TABLE office(id TEXT PRIMARY KEY, site TEXT);
        CREATE TABLE appointment(id INTEGER PRIMARY KEY, person TEXT, office TEXT, from_day INT, to_day INT);
        CREATE TABLE household(id TEXT PRIMARY KEY, kind TEXT, place TEXT, name TEXT, members INT, land INT,
                               need INT, status TEXT, hunger INT);
        CREATE TABLE account(id TEXT PRIMARY KEY, boundary INT, balance INT);
        CREATE TABLE ledger(id INTEGER PRIMARY KEY, day INT, payer TEXT, payee TEXT, amount INT, reason TEXT);
        CREATE TABLE stock(owner TEXT, place TEXT, commodity TEXT, qty INT, PRIMARY KEY(owner, place, commodity));
        CREATE TABLE shipment(id INTEGER PRIMARY KEY, order_id INT, commodity TEXT, qty INT, src_owner TEXT,
                              src_place TEXT, dst_owner TEXT, dst_place TEXT, depart INT, eta INT, state TEXT,
                              mountain INT, payer TEXT, payee TEXT, amount INT, origin TEXT, arrived INT);
        CREATE TABLE work_order(id INTEGER PRIMARY KEY, rule TEXT, kind TEXT, office TEXT, commodity TEXT,
                                qty INT, shipped INT, delivered INT, cost INT, state TEXT, created INT, sla INT,
                                deadline INT, closed INT, due INT, dedupe TEXT, parent INT, supplier TEXT,
                                buyer TEXT, note TEXT, block TEXT);
        CREATE TABLE arrears(debtor TEXT, creditor TEXT, qty INT, PRIMARY KEY(debtor, creditor));
        CREATE TABLE event_log(id INTEGER PRIMARY KEY, day INT, slot INT, type TEXT, place TEXT, actor TEXT,
                               payload TEXT, cause INT);
        CREATE TABLE assignment(id INTEGER PRIMARY KEY, person TEXT, t_from INT, t_to INT, place TEXT, activity TEXT);
        CREATE TABLE roster(day INT, post TEXT, slot INT, person TEXT, place TEXT);
        CREATE TABLE item(id TEXT PRIMARY KEY, name TEXT, home TEXT, keeper TEXT, custodian TEXT, place TEXT,
                          missing_known INT);
        CREATE INDEX ix_ship ON shipment(state, eta);
        CREATE INDEX ix_order ON work_order(state);
        CREATE INDEX ix_ev ON event_log(day);
        CREATE INDEX ix_roster ON roster(person, day, slot);
        CREATE INDEX ix_asg ON assignment(person, t_from, t_to);
        CREATE INDEX ix_app ON appointment(office, from_day, to_day);
        CREATE INDEX ix_app2 ON appointment(person, from_day, to_day);
        ''')

    def ev(self, typ, place=None, actor=None, cause=None, slot=None, **payload):
        cur = self.x('INSERT INTO event_log(day,slot,type,place,actor,payload,cause) VALUES(?,?,?,?,?,?,?)',
                     (self.day, slot, typ, place, actor, json.dumps(payload, ensure_ascii=False, sort_keys=True), cause))
        return cur.lastrowid

    # ------------------------------------------------------------------ 钱: 复式记账
    def bal(self, a): return self.x('SELECT balance FROM account WHERE id=?', (a,)).fetchone()[0]

    def pay(self, payer, payee, amt, reason):
        amt = int(amt)
        if amt <= 0: return 0
        b, bnd = self.x('SELECT balance, boundary FROM account WHERE id=?', (payer,)).fetchone()
        if not bnd and b < amt: amt = b                      # 非边界账户不得透支
        if amt <= 0: return 0
        self.x('UPDATE account SET balance=balance-? WHERE id=?', (amt, payer))
        self.x('UPDATE account SET balance=balance+? WHERE id=?', (amt, payee))
        self.x('INSERT INTO ledger(day,payer,payee,amount,reason) VALUES(?,?,?,?,?)', (self.day, payer, payee, amt, reason))
        return amt

    def pay_to(self, payer, payee, amt, reason):
        if payee != 'VILLAGE': return self.pay(payer, payee, amt, reason)
        hh = self.x("SELECT id, members FROM household WHERE kind='wood' AND status='在' ORDER BY id").fetchall()
        if not hh: return 0
        tot, paid = sum(m for _, m in hh), 0
        for i, (h, m) in enumerate(hh):                      # 按各户人口(劳力)分
            paid += self.pay(payer, h, amt * m // tot + (amt - sum(amt * mm // tot for _, mm in hh) if i == 0 else 0), reason)
        return paid

    # ------------------------------------------------------------------ 物: 只能转移; 产生与消灭必须具名
    def qty(self, owner, place, c):
        r = self.x('SELECT qty FROM stock WHERE owner=? AND place=? AND commodity=?', (owner, place, c)).fetchone()
        return r[0] if r else 0

    def _add(self, owner, place, c, q):
        self.x('INSERT INTO stock(owner,place,commodity,qty) VALUES(?,?,?,?) '
               'ON CONFLICT(owner,place,commodity) DO UPDATE SET qty=qty+excluded.qty', (owner, place, c, q))

    def produce(self, owner, place, c, q, kind):
        q = int(q)
        if q <= 0: return 0
        self._add(owner, place, c, q); self.net[c] += q; self.flows[(self.year, c, kind)] += q
        return q

    def consume(self, owner, place, c, q, kind):
        q = min(int(q), self.qty(owner, place, c))
        if q <= 0: return 0
        self._add(owner, place, c, -q); self.net[c] -= q; self.flows[(self.year, c, kind)] += q
        return q

    def move(self, o1, p1, o2, p2, c, q):
        q = min(int(q), self.qty(o1, p1, c))
        if q <= 0: return 0
        self._add(o1, p1, c, -q); self._add(o2, p2, c, q)
        return q

    def transit(self, owner, c):
        return self.x("SELECT COALESCE(SUM(qty),0) FROM shipment WHERE dst_owner=? AND commodity=? "
                      "AND state IN ('在途','滞留')", (owner, c)).fetchone()[0]

    # ------------------------------------------------------------------ 初始世界
    def _populate(self):
        Pm, x = self.P, self.x
        for pid, nm in PLACE_NAME.items():
            x('INSERT INTO place VALUES(?,?,?)', (pid, nm, 'locked_night' if pid in ('SH_LIBRARY', 'SH_GRANARY') else 'open'))
        for a, b in [('EQUITY', 1), ('PORT', 1), ('PILGRIMS', 1), ('TOWN_BG', 1), ('STATE', 1), ('NEIGHBOR', 1),
                     ('ORG_SH', 0), ('SHOP_GRAIN', 0), ('SHOP_GEN', 0)]:
            x('INSERT INTO account VALUES(?,?,0)', (a, b))
        for a, m in [('ORG_SH', 600), ('SHOP_GRAIN', 800), ('SHOP_GEN', 500)]:
            self.pay('EQUITY', a, m * GUAN, '期初')
        self.produce('ORG_SH', 'SH_GRANARY', 'grain', 400 * SHI, 'opening')
        self.produce('ORG_SH', 'EST_GRANARY', 'grain', 900 * SHI, 'opening')
        for c, g in GOODS.items():
            if g[3]: self.produce('ORG_SH', 'SH_STORE', c, g[3] * {'firewood': 12, 'veg': 2}.get(c, 45), 'opening')
        self.produce('ORG_SH', 'SH_STORE', 'cloth', 10, 'opening')
        self.produce('ORG_SH', 'SH_STORE', 'timber', 60, 'opening')
        self.produce('SHOP_GRAIN', 'DF', 'grain', 300 * SHI, 'opening')
        for c, (lo, hi) in SHOP_BANDS.items(): self.produce('SHOP_GEN', 'DF', c, hi, 'opening')
        for kind, n, mu, place, cash in [('tenant', Pm['n_tenant'], 10, 'EST', 2), ('owner', Pm['n_owner'], 8, 'VIL', 5),
                                         ('wood', Pm['n_wood'], 2, 'VIL', 2)]:
            for i in range(n):
                hid = f'HH_{kind[0].upper()}{i + 1:03d}'
                m = 3 + int(self.u('members', hid) * 5)
                name = None
                if hid == 'HH_O001': m, name = 2, '乔三槐家'
                x('INSERT INTO household VALUES(?,?,?,?,?,?,?,?,?)',
                  (hid, kind, place, name, m, m * mu, m * Pm['ration_folk'], '在', 0))
                x('INSERT INTO account VALUES(?,0,0)', (hid,))
                self.pay('EQUITY', hid, cash * GUAN, '期初')
                self.produce(hid, place, 'grain', m * Pm['ration_folk'] * 140, 'opening')
        self.P['temple_mu'] = self.x("SELECT SUM(land) FROM household WHERE kind='tenant'").fetchone()[0]

    def _mk(self, gen, name, age, hall, canon=0, joined=0):
        pid = f'P{len(self.pids) + 1:04d}'; self.pids.append(pid); self.names.add(name)
        self.x('INSERT INTO person VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (pid, name, '要角' if canon else '普通', gen, age, 'ORG_SH', hall, None, None, '在寺', joined, None, canon))
        return pid

    def _newname(self, gen, salt):
        pool = list(dict.fromkeys(POOL)); i = 0
        while True:
            ch = pool[int(self.u('name', gen, salt, i) * len(pool))]; i += 1
            if ch != gen and gen + ch not in self.names: return gen + ch

    def _people(self):
        x = self.x
        assert len(set(POOL)) >= 150
        canon = {n: self._mk(g, n, a, h, 1) for n, g, a, h in CANON}
        ages = {'玄': (55, 78), '慧': (38, 58), '虚': (20, 40), '空': (12, 22)}
        for gen, n in (('玄', 20), ('慧', 65), ('虚', 119), ('空', 89)):
            for k in range(n):
                nm = self._newname(gen, k); lo, hi = ages[gen]
                self._mk(gen, nm, lo + int(self.u('age', nm) * (hi - lo + 1)), '清众')
        quota = {'玄': [('达摩院', 7), ('戒律院', 1), ('证道院', 2), ('菩提院', 2), ('藏经阁', 1)],
                 '慧': [('罗汉堂', 15), ('达摩院', 6), ('般若堂', 10), ('戒律院', 6), ('藏经阁', 3), ('菩提院', 3), ('证道院', 3)],
                 '虚': [('罗汉堂', 40), ('般若堂', 15), ('戒律院', 4), ('藏经阁', 4), ('菩提院', 3)]}
        by = lambda gen, hall='清众': [r[0] for r in x('SELECT id FROM person WHERE gen=? AND hall=? AND canon=0 ORDER BY id', (gen, hall))]
        for gen, qs in quota.items():
            ids = by(gen); i = 0
            for hall, n in qs:
                for pid in ids[i:i + n]: x('UPDATE person SET hall=? WHERE id=?', (hall, pid))
                i += n
        # 师承: 慧 -> 玄, 虚 -> 慧, 空 -> 虚
        allg = lambda g: [r[0] for r in x('SELECT id FROM person WHERE gen=? ORDER BY id', (g,))]
        for g, mg in (('慧', '玄'), ('虚', '慧'), ('空', '虚')):
            ms = allg(mg)
            for pid in allg(g): x('UPDATE person SET master=? WHERE id=?', (ms[int(self.u('master', pid) * len(ms))], pid))
        x('UPDATE person SET master=? WHERE id=?', (canon['慧轮'], canon['虚竹']))
        # 住处
        for i, (pid, gen, hall) in enumerate(x('SELECT id, gen, hall FROM person ORDER BY id').fetchall()):
            home = 'SH_ABBOT' if pid == canon['玄慈'] else HALLPLACE.get(hall, 'SH_ELDERS') if gen == '玄' else f'SH_DORM_{i // 20 + 1}'
            x('UPDATE person SET home=? WHERE id=?', (home, pid))
        # 清规岗位与院堂首座
        free = {g: by(g) for g in ('玄', '慧', '虚')}
        lib = by('慧', '藏经阁'); puti = by('玄', '菩提院')
        def appoint(office, pid):
            x('INSERT OR IGNORE INTO office VALUES(?,?)', (office, SITE.get(office.lstrip('副'))))
            x('INSERT INTO appointment(person,office,from_day,to_day) VALUES(?,?,0,?)', (pid, office, 10 ** 9))
        appoint('方丈', canon['玄慈']); appoint('戒律院首座', canon['玄寂']); appoint('达摩院首座', canon['玄难'])
        appoint('菩提院首座', puti[0]); appoint('园头', canon['缘根'])
        appoint('首座', free['玄'].pop(0)); appoint('监院', free['玄'].pop(0)); appoint('藏主', lib[0]); appoint('副藏主', lib[1])
        for o in ('维那', '典座', '直岁', '库头', '知客', '延寿堂主', '庄主', '化主'): appoint(o, free['慧'].pop(0))
        for o in ('监院', '维那', '典座', '直岁', '库头', '知客', '庄主', '园头', '化主'): appoint('副' + o, free['慧'].pop(0))
        # 独有物
        x("INSERT INTO item VALUES('IT_YJJ','《易筋经》','SH_PUTI','菩提院首座',?, 'SH_PUTI', 0)", (puti[0],))
        x("INSERT INTO item VALUES('IT_BRZ','《般若掌》图谱','SH_LIBRARY','藏主',?, 'SH_LIBRARY', 0)", (lib[0],))

    # ------------------------------------------------------------------ 岗位
    def _appointee(self, office, day=None):
        d = self.day if day is None else day
        r = self.x('SELECT person FROM appointment WHERE office=? AND from_day<=? AND to_day>=? ORDER BY id DESC LIMIT 1',
                   (office, d, d)).fetchone()
        return r[0] if r else None

    def holder(self, office, day=None):
        """现任; 正职出缺时由副职代理。"""
        return self._appointee(office, day) or (None if office.startswith('副') else self._appointee('副' + office, day))

    def office_of(self, pid, day):
        r = self.x('SELECT office FROM appointment WHERE person=? AND from_day<=? AND to_day>=? ORDER BY id DESC LIMIT 1',
                   (pid, day, day)).fetchone()
        return r[0] if r else None

    def pname(self, pid):
        if not pid: return ''
        r = self.x('SELECT name FROM person WHERE id=?', (pid,)).fetchone()
        return r[0] if r else pid

    # ------------------------------------------------------------------ 价格与路况
    def closed(self, d=None):
        d = self.day if d is None else d
        return self.x('SELECT 1 FROM route_closure WHERE from_day<=? AND to_day>=?', (d, d)).fetchone() is not None

    def grain_price(self):
        doy = self.day % YEAR
        s = 0.92 if (125 <= doy < 185 or 245 <= doy < 305) else 1.10 if 60 <= doy < 125 else 1.0
        return int(self.P['grain_price'] * s * self.price_factor)

    def price(self, c):
        if c != 'grain': return GOODS[c][2]
        p = self.grain_price()
        return int(p * 1.1) if self.qty('SHOP_GRAIN', 'DF', 'grain') < 100 * SHI else p

    def cost(self, c, q): return q * self.price(c) // SHI if c == 'grain' else q * self.price(c)

    def head(self):
        return self.x("SELECT COUNT(*) FROM person WHERE org='ORG_SH' AND status='在寺'").fetchone()[0]

    def daily_grain(self): return max(1, self.head() * self.P['ration_monk'])

    # ------------------------------------------------------------------ 工作订单
    def open_order(self, rule, kind, office, c, q, sla, supplier=None, buyer=None, note='', cause=None,
                   parent=None, state='待接', shipped=0, cost=0, block=None):
        q = int(q)
        if q <= 0 and kind not in ('ALMS',): return None
        dedupe = f'{rule}:{buyer or ""}:{c}'
        if self.x(f'SELECT 1 FROM work_order WHERE dedupe=? AND state IN {LIVE_SQL}', (dedupe,)).fetchone(): return None
        cur = self.x('INSERT INTO work_order(rule,kind,office,commodity,qty,shipped,delivered,cost,state,created,sla,'
                     'deadline,dedupe,parent,supplier,buyer,note,block) VALUES(?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?)',
                     (rule, kind, office, c, q, shipped, cost, state, self.day, sla, self.day + sla, dedupe, parent,
                      supplier, buyer, note, block))
        oid = cur.lastrowid
        self.ev('ORDER_OPEN' if parent is None else 'ORDER_RENEWED', actor=self.holder(office), cause=cause,
                order=oid, kind=kind, c=c, q=q, parent=parent)
        self.cnt['orders'] += 1
        return oid

    def set_state(self, oid, state, **kw):
        sets, vals = ['state=?'], [state]
        for k, v in kw.items(): sets.append(f'{k}=?'); vals.append(v)
        self.x(f"UPDATE work_order SET {','.join(sets)} WHERE id=?", (*vals, oid))

    def block(self, oid, why):
        st, kind, c = self.x('SELECT state, kind, commodity FROM work_order WHERE id=?', (oid,)).fetchone()
        if st == '受阻' or st not in LIVE: return
        self.set_state(oid, '受阻', block=why)
        e = self.ev('ORDER_BLOCKED', cause=self.road_ev if why == '封路' else None, order=oid, why=why, c=c)
        self.block_c[c] = e
        if c == 'grain': self.block_ev = e

    def done(self, oid):
        self.set_state(oid, '完成', closed=self.day)
        self.ev('ORDER_DONE', order=oid)

    def finish_if_done(self, oid):
        if oid is None: return
        q, dl, st, kind, blk = self.x('SELECT qty, delivered, state, kind, block FROM work_order WHERE id=?', (oid,)).fetchone()
        if st not in LIVE: return
        live = self.x("SELECT COUNT(*), COALESCE(SUM(state='滞留'),0) FROM shipment WHERE order_id=? AND state IN ('在途','滞留')", (oid,)).fetchone()
        if kind in ('TRANSFER', 'PURCHASE', 'IMPORT', 'BORROW') and dl >= q and live[0] == 0:
            self.done(oid)
        elif st == '受阻' and blk == '封路' and live[1] == 0 and not self.closed():
            self.set_state(oid, '进行中', block=None); self.ev('ORDER_RESUMED', order=oid)

    def ship(self, oid, c, q, src, dst, days, mountain, pay=None, origin='stock'):
        q = int(q)
        if q <= 0: return 0
        if origin == 'stock':
            q = min(q, self.qty(src[0], src[1], c))
            if q <= 0: return 0
            self._add(src[0], src[1], c, -q)                 # 出库后计入在途
        else:                                                # 端口流入 / 产地现采
            self.net[c] += q; self.flows[(self.year, c, 'port_in' if origin == 'port' else 'produce')] += q
        payer, payee, amount = pay or (None, None, 0)
        self.x('INSERT INTO shipment(order_id,commodity,qty,src_owner,src_place,dst_owner,dst_place,depart,eta,state,'
               'mountain,payer,payee,amount,origin) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (oid, c, q, src[0], src[1], dst[0], dst[1], self.day, self.day + days, '在途', int(mountain), payer, payee,
                int(amount), origin))
        self.x('UPDATE work_order SET shipped=shipped+? WHERE id=?', (q, oid))
        self.ev('SHIP_OUT', place=src[1], order=oid, c=c, q=q, eta=self.day + days)
        return q

    # ------------------------------------------------------------------ 每日结算的各阶段
    def phase_weather(self):
        d, c = self.day, cal(self.day)
        if d > 0 and self.closed(d - 1) and not self.closed(d):
            self.road_ev = self.ev('ROAD_OPEN', place='SH_ROAD')
        if c['month'] in (11, 12, 1) and not self.closed(d) and self.u('snow', d) < self.P['snow_prob']:
            dur = 4 + int(self.u('snowdur', d) * 9)
            self.close_road(dur, '大雪封山')

    def close_road(self, dur, reason):
        self.x('INSERT INTO route_closure VALUES(?,?,?,?)', ('SH_ROAD', self.day, self.day + dur - 1, reason))
        self.road_ev = self.ev('ROAD_CLOSED', place='SH_ROAD', days=dur, reason=reason)

    def phase_arrivals(self):
        d, closed = self.day, self.closed()
        rows = self.x("SELECT id,order_id,commodity,qty,src_owner,src_place,dst_owner,dst_place,state,mountain,payer,"
                      "payee,amount,origin FROM shipment WHERE state IN ('在途','滞留') AND eta<=? ORDER BY id", (d,)).fetchall()
        for sid, oid, c, q, so, sp, do, dp, st, mnt, payer, payee, amt, origin in rows:
            if mnt and closed:
                if st != '滞留':
                    self.x("UPDATE shipment SET state='滞留' WHERE id=?", (sid,)); self.block(oid, '封路')
                continue
            acc, paid = q, 0
            if payee and amt > 0:
                b, bnd = self.x('SELECT balance, boundary FROM account WHERE id=?', (payer,)).fetchone()
                can = amt if bnd else min(amt, b)
                if can < amt:                                # 货款不足: 按付得起的比例收货, 其余退回
                    acc = q * can // amt; ret = q - acc
                    if origin == 'stock': self._add(so, sp, c, ret)
                    else: self.net[c] -= ret; self.flows[(self.year, c, 'returned')] += ret
                    self.x('UPDATE work_order SET qty=qty-?, shipped=shipped-? WHERE id=?', (ret, ret, oid))
                    self.ev('GOODS_RETURNED', place=dp, order=oid, c=c, q=ret, why='货款不足')
                paid = self.pay_to(payer, payee, can, '货款:' + GOODS[c][0])
            if acc > 0: self._add(do, dp, c, acc)
            self.x("UPDATE shipment SET state='已达', arrived=?, qty=? WHERE id=?", (d, acc, sid))
            self.x('UPDATE work_order SET delivered=delivered+? WHERE id=?', (acc, oid))
            self.ev('SHIP_IN', place=dp, order=oid, c=c, q=acc, paid=paid)
            if do == 'ORG_SH' and c == 'grain' and payee: self.tg[(self.year, '市购')] += acc
            self.finish_if_done(oid)

    def phase_production(self):
        d, c, Pm = self.day, cal(self.day), self.P
        if c['wheat']: self.harvest('麦')
        if c['millet']: self.harvest('粟')
        if c['doy'] in (130, 250): self.households_sell()
        if c['doy'] in (132, 252): self.households_shop()
        if c['doy'] in (135, 255): self.temple_after_harvest()
        m = c['month']
        self.produce('ORG_SH', 'SH_STORE', 'veg', 4 if m in (3, 4, 5) else 7 if m in (6, 7, 8) else 5 if m in (9, 10) else 1, 'produce')
        if c['dom'] == 1:
            for h, m in self.x("SELECT id, members FROM household WHERE kind='wood' AND status='在' ORDER BY id").fetchall():
                self.pay('TOWN_BG', h, Pm['town_bg_income'] * m, '樵菜售予县城')
        if c['doy'] == 0 and d > 0:                           # 岁首招佃: 空出的佃田由外来户补上
            gone = Pm['n_tenant'] - self.x("SELECT COUNT(*) FROM household WHERE kind='tenant' AND status='在'").fetchone()[0]
            n = 0
            for k in range(gone):
                if self.u('immig', d, k) < 0.5:
                    hid = f"HH_T{self.x("SELECT COUNT(*) FROM household WHERE kind='tenant'").fetchone()[0] + 1:03d}"
                    mm = 3 + int(self.u('members', hid) * 5)
                    self.x('INSERT INTO household VALUES(?,?,?,?,?,?,?,?,?)', (hid, 'tenant', 'EST', None, mm, mm * 10, mm * Pm['ration_folk'], '在', 0))
                    self.x('INSERT INTO account VALUES(?,0,0)', (hid,)); self.pay('PORT', hid, GUAN, '迁入携带')
                    self.produce(hid, 'EST', 'grain', mm * Pm['ration_folk'] * 140, 'port_in'); n += 1
            if n: self.ev('TENANTS_SETTLED', place='EST', actor=self.holder('庄主'), n=n)
        if c['doy'] in (140, 260) and self.tier == '充足':     # 收成后粮足: 游方僧归寺
            n = self.x("UPDATE person SET status='在寺' WHERE status='游方'").rowcount
            if n: self.pcache.clear(); self.ev('MONKS_RETURN', place='SH_GATE', n=n)
        if c['doy'] == 359:                                   # 岁末: 铺户盈余转为铺主家用与商税, 流回县城
            for s, cap in (('SHOP_GRAIN', 800), ('SHOP_GEN', 500)):
                self.pay(s, 'TOWN_BG', max(0, self.bal(s) - cap * GUAN), '铺主家用与商税')

    def harvest(self, crop):
        Pm, y = self.P, self.year
        yf = self.yield_override.get((y, crop), 0.92 + 0.16 * self.u('year', y, crop))
        self.price_factor = 1 + max(0.0, 0.95 - yf) * 1.2
        bad = yf < 0.7                                        # 灾年: 寺院减租三成收, 官府两税减半
        share, taxk = (0.3 if bad else Pm['rent_share']), (0.5 if bad else 1.0)
        gross = rent = tax_hh = repaid = 0
        for hid, kind, place, land in self.x("SELECT id,kind,place,land FROM household WHERE status='在' ORDER BY id").fetchall():
            g = self.produce(hid, place, 'grain', land / 2 * Pm['yield_net'] * yf * (0.85 + 0.3 * self.u('hhy', hid, y, crop)) * SHI, 'produce')
            gross += g
            if kind == 'tenant':
                r = self.move(hid, place, 'ORG_SH', 'EST_GRANARY', 'grain', g * share); rent += r
                owe = self.x("SELECT qty FROM arrears WHERE debtor=? AND creditor='ORG_SH'", (hid,)).fetchone()
                if owe and owe[0] > 0:
                    back = self.move(hid, place, 'ORG_SH', 'EST_GRANARY', 'grain', min(owe[0], (g - r) * 3 // 10))
                    self.x("UPDATE arrears SET qty=qty-? WHERE debtor=? AND creditor='ORG_SH'", (back, hid)); repaid += back
            else:
                tax_hh += self.consume(hid, place, 'grain', land * Pm['tax'] / 2 * SHI * taxk, 'tax_out')
        t = self.consume('ORG_SH', 'EST_GRANARY', 'grain', Pm['temple_mu'] * Pm['tax'] / 2 * SHI * taxk, 'tax_out')
        self.tg[(y, '租入')] += rent; self.tg[(y, '两税')] += t; self.tg[(y, '佃户还粮')] += repaid
        self.ev('HARVEST', place='EST', actor=self.holder('庄主'), crop=crop, yf=round(yf, 3), gross=gross, rent=rent,
                tax_temple=t, tax_hh=tax_hh, repaid=repaid, remission=bad)

    def households_sell(self):
        doy = self.day % YEAR
        nxt = (245 - doy) if doy < 245 else (YEAR - doy + 125)
        p = self.grain_price() * 9 // 10
        n = tot = 0
        for hid, place, need in self.x("SELECT id,place,need FROM household WHERE status='在' ORDER BY id").fetchall():
            sell = self.qty(hid, place, 'grain') - need * (nxt + 60)
            sell = min(sell, max(0, self.bal('SHOP_GRAIN') - 50 * GUAN) * SHI // p)
            if sell <= 0: continue
            self.move(hid, place, 'SHOP_GRAIN', 'DF', 'grain', sell)
            self.pay('SHOP_GRAIN', hid, sell * p // SHI, '卖余粮'); n += 1; tot += sell
        self.ev('MARKET_SALES', place='DF', n=n, qty=tot, price=p)

    def households_shop(self):
        Pm = self.P
        for (hid,) in self.x("SELECT id FROM household WHERE status='在' ORDER BY id").fetchall():
            for c, want, floor in (('oilsalt', Pm['hh_salt'], 0), ('cloth', Pm['hh_cloth'], 3 * GUAN)):
                q = min(want, self.qty('SHOP_GEN', 'DF', c), max(0, self.bal(hid) - floor) // GOODS[c][2])
                if q > 0:
                    self.consume('SHOP_GEN', 'DF', c, q, 'consume_hh'); self.pay(hid, 'SHOP_GEN', q * GOODS[c][2], '家用:' + GOODS[c][0])
            spare = max(0, self.bal(hid) - 3 * GUAN)             # 留三贯买粮钱, 富余的才花; 钱多的多花
            self.pay(hid, 'TOWN_BG', min(spare, Pm['hh_misc'] + max(0, spare - 2 * GUAN) * 6 // 10), '家用:杂项')

    def temple_after_harvest(self):
        y = self.year
        owe = self.x("SELECT qty FROM arrears WHERE debtor='ORG_SH' AND creditor='NEIGHBOR'").fetchone()
        if owe and owe[0] > 0:                                # 归还邻寺借粮
            back = self.consume('ORG_SH', 'EST_GRANARY', 'grain', owe[0], 'port_out')
            self.x("UPDATE arrears SET qty=qty-? WHERE debtor='ORG_SH' AND creditor='NEIGHBOR'", (back,))
            self.tg[(y, '还邻寺')] += back; self.ev('GRAIN_REPAID', actor=self.holder('监院'), q=back, to='邻寺')
        total = self.qty('ORG_SH', 'SH_GRANARY', 'grain') + self.qty('ORG_SH', 'EST_GRANARY', 'grain') + self.transit('ORG_SH', 'grain')
        excess = total - self.daily_grain() * 400             # 留足四百日之蓄, 余粮出售
        p = self.grain_price() * 9 // 10
        sell = min(excess, self.qty('ORG_SH', 'EST_GRANARY', 'grain'), max(0, self.bal('SHOP_GRAIN') - 50 * GUAN) * SHI // p)
        if sell > 0:
            self.move('ORG_SH', 'EST_GRANARY', 'SHOP_GRAIN', 'DF', 'grain', sell)
            m = self.pay('SHOP_GRAIN', 'ORG_SH', sell * p // SHI, '售余粮')
            self.tg[(y, '售出')] += sell
            self.ev('GRAIN_SOLD', place='EST', actor=self.holder('监院'), q=sell, money=m)

    def phase_visitors(self):
        d, c, Pm = self.day, cal(self.day), self.P
        closed = self.closed()
        f = pilgrim_factor(c) * self.pilgrim_boost.get(d, 1) * (0.1 if closed else 1)
        n = int(Pm['pilgrims'] * f * (0.7 + 0.6 * self.u('pilgrims', d)) + 0.5)
        money = self.pay('PILGRIMS', 'ORG_SH', n * Pm['alms_each'] / self.price_factor, '香火钱')
        g = int(n * Pm['guest_rate'] + 0.5)
        if self.tier in ('告急', '断供'):
            if g: self.ev('GUESTS_SUSPENDED', place='SH_GUEST', actor=self.holder('知客'), n=g)
            g = 0
        elif g > Pm['guest_cap']:
            self.ev('GUEST_TURNED_AWAY', place='SH_GUEST', actor=self.holder('知客'), n=g - Pm['guest_cap']); g = Pm['guest_cap']
        self.guests, self.pilgrims_today = g, n
        self.ev('ALMS', place='SH_HALL', pilgrims=n, money=money, guests=g)
        if not closed:
            big = c['festival'] in ('元日', '上元', '佛诞', '盂兰盆', '腊八')
            if (big or c['shuowang']) and self.u('donor', d) < (1.0 if big else Pm['donor_prob']):
                self.pay('PILGRIMS', 'ORG_SH', Pm['donor_gift'], '大施主布施'); self.ev('DONOR', place='SH_HALL', money=Pm['donor_gift'])
            if self.u('rite', d) < Pm['rite_prob']:
                self.pay('TOWN_BG', 'ORG_SH', Pm['rite_fee'], '法事'); self.ev('RITE', place='SH_FATANG', actor=self.holder('维那'), money=Pm['rite_fee'])

    def phase_rules(self):
        d, c, Pm = self.day, cal(self.day), self.P
        daily = self.daily_grain()
        sh, est, tr = self.qty('ORG_SH', 'SH_GRANARY', 'grain'), self.qty('ORG_SH', 'EST_GRANARY', 'grain'), self.transit('ORG_SH', 'grain')
        cover = sh / daily
        idx = lambda cv, pad: next((i for i, th in enumerate((60, 30, 10, 1)) if cv >= th + pad), 4)
        i, j, cur = idx(cover, 0), idx(cover, 5), TIERS.index(self.tier)
        tier = TIERS[i if i > cur else j if j < cur else cur]        # 变差立即生效; 变好要多出 5 日余量, 免得在线上来回跳
        if tier != self.tier:
            worse = TIERS.index(tier) > TIERS.index(self.tier)
            self.ev('TIER_CHANGE', place='SH_GRANARY', actor=self.holder('库头'), cause=self.block_ev if worse else None,
                    frm=self.tier, to=tier, cover=round(cover, 1))
            self.tier = tier
        # 库头: 寺库低于 75 日, 先从自家庄仓调粮 (档位线是 60 日, 正常运转不触线)
        if cover < 75 and est > 0:
            self.open_order('R-GRAIN-TRANSFER', 'TRANSFER', '庄主', 'grain', min(est, daily * 120 - sh - tr), 20, supplier='EST', buyer='ORG_SH')
        # 库头: 寺库加庄仓合计低于 45 日, 向粮铺市购
        if (sh + est + tr) / daily < 45:
            self.open_order('R-GRAIN-BUY', 'PURCHASE', '库头', 'grain', daily * 90 - (sh + est + tr), 12, supplier='SHOP_GRAIN', buyer='ORG_SH')
        # 降级阶梯: 紧张以下且总量不足 30 日 -> 募化; 告急 -> 向邻寺借粮
        if tier in ('紧张', '告急', '断供') and (sh + est + tr) / daily < 30 and d - self.last_alms >= 20:
            self.open_order('R-ALMS-ROUND', 'ALMS', '化主', 'grain', 0, 16, buyer='ORG_SH')
        if tier in ('告急', '断供'):
            self.open_order('R-BORROW', 'BORROW', '监院', 'grain', daily * 30, 10, supplier='NEIGHBOR', buyer='ORG_SH')
        # 库头: 杂项补货
        for cc in ('oilsalt', 'medicine', 'incense', 'paper'):
            use, st = GOODS[cc][3], self.qty('ORG_SH', 'SH_STORE', cc)
            if st < use * GOODS[cc][4]:
                self.open_order('R-RESTOCK', 'PURCHASE', '库头', cc, use * GOODS[cc][5] - st, 10, supplier='SHOP_GEN', buyer='ORG_SH')
        fw = self.firewood_use(c); st = self.qty('ORG_SH', 'SH_STORE', 'firewood')
        if st < fw * 10: self.open_order('R-RESTOCK', 'PURCHASE', '库头', 'firewood', fw * 17 - st, 10, supplier='VILLAGE', buyer='ORG_SH')
        st = self.qty('ORG_SH', 'SH_STORE', 'veg')
        if st < 10: self.open_order('R-RESTOCK', 'PURCHASE', '典座', 'veg', 15 - st, 6, supplier='VILLAGE', buyer='ORG_SH')
        if c['doy'] in (85, 235): self.cloth_due = min(150, self.cloth_due + 75)   # 立项: 本季应发僧衣(欠发不过两季)。只要还欠着, 规则就持续追
        if self.cloth_due > self.qty('ORG_SH', 'SH_STORE', 'cloth'):
            self.open_order('R-CLOTH', 'PURCHASE', '库头', 'cloth', self.cloth_due - self.qty('ORG_SH', 'SH_STORE', 'cloth'), 14, supplier='SHOP_GEN', buyer='ORG_SH')
        st = self.qty('ORG_SH', 'SH_STORE', 'timber')
        if st < 30: self.open_order('R-RESTOCK', 'PURCHASE', '直岁', 'timber', 60 - st, 14, supplier='SHOP_GEN', buyer='ORG_SH')
        # 直岁: 损坏 -> 修缮订单
        if self.u('damage', d) < 0.028 * (2 if c['month'] in (6, 7, 11, 12) else 1):
            what = ['僧寮屋瓦', '山门木栅', '库房墙垣', '斋堂梁柱', '藏经阁窗棂', '钟楼檐角'][int(self.u('damwhat', d) * 6)]
            e = self.ev('DAMAGE', place='SH', what=what)
            self.open_order(f'R-REPAIR-{d}', 'REPAIR', '直岁', 'timber', 10 + int(self.u('damt', d) * 20), 30, buyer='ORG_SH',
                            note=json.dumps(dict(what=what, labor=5 + int(self.u('daml', d) * 15)), ensure_ascii=False), cause=e)
        # 监院: 按优先级审批采购 (钱不够时先保粮柴)
        committed = self.x("SELECT COALESCE(SUM(cost*(qty-delivered)/qty),0) FROM work_order WHERE buyer='ORG_SH' AND "
                           "kind='PURCHASE' AND state IN ('已接','进行中','受阻') AND qty>0").fetchone()[0]
        avail = self.bal('ORG_SH') - int(committed)
        rows = self.x("SELECT id, commodity, qty, note FROM work_order WHERE buyer='ORG_SH' AND kind='PURCHASE' AND state='待接'").fetchall()
        for oid, cc, q, note in sorted(rows, key=lambda r: (GOODS[r[1]][6], r[0])):
            cost = self.cost(cc, q)
            room = avail - (60 * GUAN if GOODS[cc][6] >= 7 else 0)   # 布与木石料不是急用: 批它们之前先留 60 贯压库钱
            if cost > room:
                afford = int(max(0, room) * q // cost) if cost else q
                if afford >= max(1, q // 5):
                    self.ev('ORDER_REDUCED', actor=self.holder('监院'), order=oid, frm=q, to=afford, why='钱不够')
                    q, cost = afford, self.cost(cc, afford)
                else:
                    if note != '缺钱':
                        self.x("UPDATE work_order SET note='缺钱' WHERE id=?", (oid,))
                        self.ev('ORDER_DEFERRED', actor=self.holder('监院'), order=oid, c=cc, why='缺钱')
                    continue
            avail -= cost
            self.set_state(oid, '已接', cost=cost, qty=q)
            self.ev('ORDER_APPROVED', actor=self.holder('监院'), order=oid, c=cc, q=q, cost=cost)
        # 铺户: 自己的补货规则
        for cc, (lo, hi) in SHOP_BANDS.items():
            st = self.qty('SHOP_GEN', 'DF', cc) + self.transit('SHOP_GEN', cc)
            if st < lo: self.open_order('R-IMPORT', 'IMPORT', '杂货行', cc, hi - st, 12, supplier='PORT', buyer='SHOP_GEN')
        gs = self.qty('SHOP_GRAIN', 'DF', 'grain')
        if gs + self.transit('SHOP_GRAIN', 'grain') < 100 * SHI:
            self.open_order('R-IMPORT', 'IMPORT', '粮铺', 'grain', 300 * SHI - gs, 12, supplier='PORT', buyer='SHOP_GRAIN')
        elif gs > 500 * SHI:
            q = self.consume('SHOP_GRAIN', 'DF', 'grain', gs - 300 * SHI, 'port_out')
            self.pay('PORT', 'SHOP_GRAIN', q * (self.grain_price() * 95 // 100) // SHI, '粮食外销')

    def firewood_use(self, c): return GOODS['firewood'][3] + (3 if c['month'] in (11, 12, 1) else 0)

    def phase_orders(self):
        d, closed, Pm = self.day, self.closed(), self.P
        vil_cap = {'firewood': self.x("SELECT COUNT(*) FROM household WHERE kind='wood' AND status='在'").fetchone()[0] * 3 // 2, 'veg': 6}
        rows = self.x(f"SELECT id,kind,commodity,qty,shipped,delivered,state,supplier,buyer,due,note,cost,office FROM work_order "
                      f"WHERE state IN {LIVE_SQL} ORDER BY id").fetchall()
        for oid, kind, c, q, shipped, delivered, st, sup, buyer, due, note, cost, office in rows:
            rem = q - shipped
            if kind == 'TRANSFER':
                if rem <= 0: continue
                if closed: self.block(oid, '封路'); continue
                lot = min(rem, Pm['convoy'], self.qty('ORG_SH', 'EST_GRANARY', 'grain'))
                if lot <= 0:                                  # 庄仓已空: 按已发数量结单
                    self.x('UPDATE work_order SET qty=shipped WHERE id=?', (oid,)); self.finish_if_done(oid); continue
                if st == '受阻': self.ev('ORDER_RESUMED', order=oid)
                self.set_state(oid, '进行中', block=None)
                self.ship(oid, 'grain', lot, ('ORG_SH', 'EST_GRANARY'), ('ORG_SH', 'SH_GRANARY'), 2, True)
                self.tg[(self.year, '庄仓调入')] += lot
            elif kind == 'PURCHASE' and st != '待接':
                if rem <= 0: continue
                if closed: self.block(oid, '封路'); continue
                if sup == 'VILLAGE':
                    lot = min(rem, vil_cap[c]); vil_cap[c] -= lot; origin, src = 'made', ('VILLAGE', 'VIL')
                else:
                    lot = min(rem, self.qty(sup, 'DF', c)); origin, src = 'stock', (sup, 'DF')
                if lot <= 0: self.block(oid, '缺货'); continue
                if st == '受阻': self.ev('ORDER_RESUMED', order=oid)
                self.set_state(oid, '进行中', block=None)
                self.ship(oid, c, lot, src, (buyer, 'SH_GRANARY' if c == 'grain' else 'SH_STORE'), 1, True,
                          pay=(buyer, sup, cost * lot // q), origin=origin)
            elif kind == 'IMPORT' and st == '待接':
                unit = (self.grain_price() * 105 // 100) / SHI if c == 'grain' else GOODS[c][2] * 0.85
                q2 = min(q, int(max(0, self.bal(buyer) - 20 * GUAN) / unit))
                if q2 <= 0: continue
                self.set_state(oid, '进行中', qty=q2, cost=int(q2 * unit))
                self.ship(oid, c, q2, ('PORT', 'PORT'), (buyer, 'DF'), 5, False, pay=(buyer, 'PORT', int(q2 * unit)), origin='port')
            elif kind == 'REPAIR':
                info = json.loads(note)
                if st == '进行中':
                    if d >= due: self.done(oid); self.ev('REPAIR_DONE', place='SH', actor=self.holder('直岁'), what=info['what'])
                elif self.qty('ORG_SH', 'SH_STORE', 'timber') >= q:
                    self.consume('ORG_SH', 'SH_STORE', 'timber', q, 'consume')
                    hh = [r[0] for r in self.x("SELECT id FROM household WHERE kind='wood' AND status='在' ORDER BY id")]
                    if hh: self.pay('ORG_SH', hh[oid % len(hh)], info['labor'] * Pm['wage'], '修缮工钱')
                    self.set_state(oid, '进行中', block=None, due=d + math.ceil(info['labor'] / 5))
                    self.ev('REPAIR_START', place='SH', actor=self.holder('直岁'), what=info['what'], timber=q, labor=info['labor'])
                else:
                    self.block(oid, '缺料')
            elif kind == 'ALMS':
                if st in ('待接', '受阻'):
                    if closed: self.block(oid, '封路'); continue
                    self.set_state(oid, '进行中', block=None, due=d + 10)
                    self.ev('ALMS_ROUND_OUT', place='SH_GATE', actor=self.holder('化主'), order=oid)
                elif d >= due and not closed:
                    k = 1 / self.price_factor ** 2
                    g = self.produce('ORG_SH', 'SH_GRANARY', 'grain', (20 + 40 * self.u('almsg', oid)) * SHI * k, 'port_in')
                    m = self.pay('PILGRIMS', 'ORG_SH', (5 + 10 * self.u('almsm', oid)) * GUAN * k, '募化所得')
                    self.last_alms = d
                    self.tg[(self.year, '募化')] += g
                    self.done(oid); self.ev('ALMS_ROUND_BACK', place='SH_GATE', actor=self.holder('化主'), grain=g, money=m)
            elif kind == 'BORROW' and st == '待接':
                self.set_state(oid, '进行中')
                self.ship(oid, 'grain', q, ('NEIGHBOR', 'PORT'), ('ORG_SH', 'SH_GRANARY'), 3, True, origin='port')
                self.x("INSERT INTO arrears VALUES('ORG_SH','NEIGHBOR',?) ON CONFLICT(debtor,creditor) DO UPDATE SET qty=qty+excluded.qty", (q,))
                self.tg[(self.year, '借邻寺')] += q
        # 超时: 待接超期 -> 过期; 其余超期加宽限 -> 失败。两者都上报, 失败的订单由上级续单并继承在途货物。
        rows = self.x(f"SELECT id,rule,kind,office,commodity,qty,shipped,delivered,cost,state,sla,deadline,supplier,buyer,note,block "
                      f"FROM work_order WHERE state IN {LIVE_SQL} AND deadline<? ORDER BY id", (d,)).fetchall()
        for oid, rule, kind, office, c, q, shipped, delivered, cost, st, sla, deadline, sup, buyer, note, blk in rows:
            if st == '待接':
                self.set_state(oid, '过期', closed=d)
                e = self.ev('ORDER_EXPIRED', order=oid, c=c, why=note or '无人承接')
                self.ev('ORDER_ESCALATED', actor=self.holder('监院'), cause=e, order=oid); self.cnt['escalated'] += 1
            elif d > deadline + 5:
                self.set_state(oid, '失败', closed=d)
                e = self.ev('ORDER_FAILED', order=oid, c=c, why=blk or '超期')
                self.ev('ORDER_ESCALATED', actor=self.holder('监院'), cause=e, order=oid); self.cnt['escalated'] += 1
                rem = q - delivered if kind != 'REPAIR' else q
                if rem > 0 and kind in ('TRANSFER', 'PURCHASE', 'REPAIR', 'IMPORT'):
                    new = self.open_order(rule, kind, office, c, rem, min(180, sla * 2), supplier=sup, buyer=buyer, note=note, cause=e, parent=oid,
                                          state='受阻' if blk else '已接', shipped=(shipped - delivered) if kind != 'REPAIR' else 0,
                                          cost=cost * rem // q if q else 0, block=blk)
                    self.x("UPDATE shipment SET order_id=? WHERE order_id=? AND state IN ('在途','滞留')", (new, oid))

    def phase_consumption(self):
        d, c, Pm = self.day, cal(self.day), self.P
        head = self.head()
        cook = self.holder('典座')
        need = int((head + self.guests) * Pm['ration_monk'] * MULT[self.tier])
        got = self.consume('ORG_SH', 'SH_GRANARY', 'grain', need, 'consume') if cook else 0
        self.tg[(self.year, '口粮')] += got
        self.ev('MEALS', place='SH_REFECTORY', actor=cook, slot=3, head=head, guests=self.guests, grain=got, tier=self.tier)
        if got < need:
            self.cnt['meal_short'] += 1
            self.ev('MEAL_SHORT', place='SH_REFECTORY', actor=cook, need=need, got=got, why='无人主厨' if not cook else '粮尽')
        use = dict(firewood=self.firewood_use(c), veg=5, oilsalt=5, medicine=1, paper=1,
                   incense=(4 + self.pilgrims_today // 50) * (3 if c['shuowang'] or c['festival'] else 1))
        for cc, n in use.items():
            if cc == 'firewood' and self.qty('ORG_SH', 'SH_STORE', cc) < n and self.closed():
                self.produce('ORG_SH', 'SH_STORE', cc, 5, 'produce')      # 封路又缺柴: 普请打柴
                self.ev('FORAGE', place='SH_GROUNDS', actor=self.holder('直岁'), c=cc, q=5)
            g = self.consume('ORG_SH', 'SH_STORE', cc, n, 'consume')
            if g < n:
                self.cnt['short_' + cc] += 1
                if self.cnt['streak_' + cc] == 0:
                    blk = self.x("SELECT 1 FROM work_order WHERE buyer='ORG_SH' AND commodity=? AND state='受阻'", (cc,)).fetchone()
                    self.ev('SHORTAGE', place='SH_STORE', actor=self.holder('库头'), cause=self.block_c.get(cc) if blk else None, c=cc)
                self.cnt['streak_' + cc] += 1
            else:
                self.cnt['streak_' + cc] = 0
        self.consume('ORG_SH', 'SH_STORE', 'veg', self.qty('ORG_SH', 'SH_STORE', 'veg') - 15, 'spoil')   # 鲜菜存不过三日
        if self.cloth_due > 0 and not (85 <= c['doy'] < 100 or 235 <= c['doy'] < 250):
            g = self.consume('ORG_SH', 'SH_STORE', 'cloth', self.cloth_due, 'consume')
            if g:
                self.cloth_due -= g
                self.ev('CLOTH_ISSUED', place='SH_STORE', actor=self.holder('库头'), q=g, owed=self.cloth_due)
        if self.tier == '断供':
            for pid, in self.x("SELECT id FROM person WHERE status='在寺' AND canon=0 ORDER BY id").fetchall():
                if self.u('leave', pid, d) < 0.05:
                    self.x("UPDATE person SET status='游方' WHERE id=?", (pid,)); self.cnt['monks_left'] += 1
        # 农户: 够吃的批量结算, 不够的逐户处理
        ok = "h.status='在' AND s.commodity='grain' AND s.owner=h.id AND s.place=h.place"
        tot = self.x(f"SELECT COALESCE(SUM(h.need),0) FROM household h, stock s WHERE {ok} AND s.qty>=h.need").fetchone()[0]
        short = self.x(f"SELECT h.id,h.kind,h.place,h.need,s.qty,h.hunger FROM household h, stock s WHERE {ok} AND s.qty<h.need ORDER BY h.id").fetchall()
        self.x("UPDATE stock SET qty=qty-(SELECT need FROM household h WHERE h.id=stock.owner) WHERE commodity='grain' AND EXISTS "
               "(SELECT 1 FROM household h WHERE h.id=stock.owner AND h.place=stock.place AND h.status='在' AND stock.qty>=h.need)")
        self.net['grain'] -= tot; self.flows[(self.year, 'grain', 'consume_hh')] += tot
        for hid, kind, place, need, have, hunger in short:
            p = self.price('grain')
            buy = min(need * 10 - have, self.qty('SHOP_GRAIN', 'DF', 'grain'), self.bal(hid) * SHI // p)
            if buy > 0:
                self.move('SHOP_GRAIN', 'DF', hid, place, 'grain', buy); self.pay(hid, 'SHOP_GRAIN', buy * p // SHI, '买粮')
            have = self.qty(hid, place, 'grain')
            if have < need and kind == 'tenant':                      # 佃户向庄仓无息借粮, 记欠粮, 下季归还
                owe = self.x("SELECT COALESCE(SUM(qty),0) FROM arrears WHERE debtor=?", (hid,)).fetchone()[0]
                lend = self.move('ORG_SH', 'EST_GRANARY', hid, place, 'grain', min(need * 10 - have, 6 * SHI - owe))
                if lend > 0:
                    self.x("INSERT INTO arrears VALUES(?,'ORG_SH',?) ON CONFLICT(debtor,creditor) DO UPDATE SET qty=qty+excluded.qty", (hid, lend))
                    self.tg[(self.year, '借给佃户')] += lend; self.cnt['hh_borrow'] += 1
                    self.ev('HH_BORROW', place='EST', actor=self.holder('庄主'), hh=hid, q=lend)
                have = self.qty(hid, place, 'grain')
            if have >= need:
                self.consume(hid, place, 'grain', need, 'consume_hh'); self.x('UPDATE household SET hunger=0 WHERE id=?', (hid,))
            else:
                if hunger >= 2 and self.tier == '充足':            # 断粮三日: 寺院赈济十日口粮
                    g = self.move('ORG_SH', 'SH_GRANARY', hid, place, 'grain', need * 10)
                    self.tg[(self.year, '赈济')] += g; self.cnt['relief'] += 1
                    self.ev('RELIEF', place=place, actor=self.holder('知客'), hh=hid, q=g)
                    have = self.qty(hid, place, 'grain')
                self.consume(hid, place, 'grain', min(have, need), 'consume_hh'); self.cnt['hunger_days'] += have < need
                if have >= need: self.x('UPDATE household SET hunger=0 WHERE id=?', (hid,))
                elif hunger + 1 > 30:
                    self.x("UPDATE household SET status='离乡' WHERE id=?", (hid,)); self.cnt['hh_left'] += 1
                    self.ev('HH_LEFT', place=place, hh=hid)
                else:
                    self.x('UPDATE household SET hunger=hunger+1 WHERE id=?', (hid,))

    def phase_people(self):
        d, c, Pm = self.day, cal(self.day), self.P
        if c['doy'] == 0 and d > 0: self.x("UPDATE person SET age=age+1 WHERE status='在寺'"); self.pcache.clear()
        for pid, age in self.x("SELECT id, age FROM person WHERE status='在寺' AND canon=0 ORDER BY id").fetchall():
            hz = 0.003 if age < 30 else 0.008 if age < 50 else 0.02 if age < 65 else 0.06
            if self.u('death', pid, d) < hz / YEAR: self.die(pid, d)
        self.succession()
        if c['doy'] == 90:                                    # 四月初一: 收录新僧补足员额
            n = Pm['monks'] - self.head()
            for k in range(n):
                nm = self._newname('空', f'r{d}-{k}')
                pid = self._mk('空', nm, 14 + int(self.u('age', nm) * 7), '清众', joined=d)
                self.x('UPDATE person SET home=? WHERE id=?', ('SH_DORM_15', pid))
            if n > 0: self.ev('RECRUIT', place='SH', actor=self.holder('方丈'), n=n)
        if c['festival'] == '腊八':
            if self.tier == '充足':
                g = self.consume('ORG_SH', 'SH_GRANARY', 'grain', 20 * SHI, 'consume'); self.tg[(self.year, '施粥')] += g
                self.ev('CHARITY', place='SH_GATE', actor=self.holder('典座'), grain=g)
            extra = self.bal('ORG_SH') - Pm['treasury_target']
            if extra > 0:
                m = self.pay('ORG_SH', 'TOWN_BG', extra * 6 // 10, '修造功德')
                self.ev('MERIT_SPEND', place='SH', actor=self.holder('方丈'), money=m)
        if c['dom'] == 1: self.audit_items()
        self.make_roster(d + 1)

    def die(self, pid, last_day):
        self.x("UPDATE person SET status='圆寂', died=? WHERE id=?", (last_day, pid)); self.pcache.pop(pid, None)
        offs = [r[0] for r in self.x('SELECT office FROM appointment WHERE person=? AND from_day<=? AND to_day>=?', (pid, last_day, last_day))]
        self.x('UPDATE appointment SET to_day=? WHERE person=? AND to_day>=?', (last_day, pid, last_day))
        e = self.ev('DEATH', place='SH', actor=pid, offices=offs); self.cnt['deaths'] += 1
        for o in offs:
            self.vacant[o] = last_day + 1
            dep = None if o.startswith('副') else self._appointee('副' + o, last_day + 1)
            if dep: self.ev('ACTING', actor=dep, cause=e, office=o)

    def succession(self):
        d = self.day
        for office, since in sorted(self.vacant.items()):
            if d < since + 1: continue                        # 出缺次日议定, 第三日起正式任职
            dep = None if office.startswith('副') else self._appointee('副' + office, d + 1)
            if dep:
                self.x('UPDATE appointment SET to_day=? WHERE person=? AND office=? AND to_day>=?', (d, dep, '副' + office, d))
                self.vacant['副' + office] = d + 1; new = dep
            else:
                hall = office[:-2] if office.endswith('首座') and len(office) > 2 else None
                cand = self.x("SELECT p.id, p.gen, p.age, p.hall FROM person p WHERE p.status='在寺' AND p.canon=0 AND p.gen IN ('玄','慧','虚') AND p.age>=25 "
                              "AND NOT EXISTS (SELECT 1 FROM appointment a WHERE a.person=p.id AND a.to_day>=?) ORDER BY p.id", (d,)).fetchall()
                rank = '玄慧虚' if hall else '慧玄虚'
                cand = [r for r in cand if not hall or r[3] == hall]
                new = min(cand, key=lambda r: (rank.index(r[1]), -r[2], r[0]), default=(None,))[0]
            if new:
                self.x('INSERT INTO appointment(person,office,from_day,to_day) VALUES(?,?,?,?)', (new, office, d + 1, 10 ** 9))
                self.ev('APPOINT', actor=self.holder('方丈'), office=office, person=new); del self.vacant[office]

    def phase_check(self):
        d = self.day
        bad = lambda k, v: self.viol.append((d, k, v))
        s = self.x('SELECT SUM(balance) FROM account').fetchone()[0]
        if s != 0: bad('钱守恒', s)
        r = self.x('SELECT id, balance FROM account WHERE boundary=0 AND balance<0').fetchall()
        if r: bad('账户透支', r[:3])
        for c in GOODS:
            tot = self.x('SELECT COALESCE(SUM(qty),0) FROM stock WHERE commodity=?', (c,)).fetchone()[0] + \
                  self.x("SELECT COALESCE(SUM(qty),0) FROM shipment WHERE commodity=? AND state IN ('在途','滞留')", (c,)).fetchone()[0]
            if tot != self.net[c]: bad('物守恒:' + c, tot - self.net[c])
        r = self.x('SELECT owner, commodity, qty FROM stock WHERE qty<0').fetchall()
        if r: bad('负库存', r[:3])
        r = self.x(f'SELECT id FROM work_order WHERE state IN {LIVE_SQL} AND deadline+5<?', (d,)).fetchall()
        if r: bad('订单滞留', [x[0] for x in r][:5])
        r = self.x(f"SELECT s.id FROM shipment s JOIN work_order o ON o.id=s.order_id WHERE s.state IN ('在途','滞留') AND o.state NOT IN {LIVE_SQL}").fetchall()
        if r: bad('无主在途货物', [x[0] for x in r][:5])
        for o in CRITICAL:
            if self.holder(o, d + 1) is None:
                self.vac_days[o] += 1
                if self.vac_days[o] > 3: bad('关键岗位空缺', o)
            else: self.vac_days[o] = 0
        daily = self.daily_grain()
        sh = self.qty('ORG_SH', 'SH_GRANARY', 'grain'); est = self.qty('ORG_SH', 'EST_GRANARY', 'grain')
        self.series.append(dict(day=d, year=self.year, tier=self.tier, cover=sh / daily, total=(sh + est + self.transit('ORG_SH', 'grain')) / daily,
                                cash=self.bal('ORG_SH'), head=self.head(), closed=self.closed(),
                                blocked=self.x("SELECT COUNT(*) FROM work_order WHERE buyer='ORG_SH' AND state='受阻'").fetchone()[0],
                                short=sum(1 for k in GOODS if self.cnt['streak_' + k] > 0),
                                tenants=self.x("SELECT COUNT(*) FROM household WHERE kind='tenant' AND status='在'").fetchone()[0]))

    def step(self):
        self.x('BEGIN')
        for fn in self.hooks.pop(self.day, []): fn(self)
        self.phase_weather(); self.phase_arrivals(); self.phase_production(); self.phase_visitors()
        self.phase_rules(); self.phase_orders(); self.phase_consumption(); self.phase_people(); self.phase_check()
        self.x('COMMIT'); self.day += 1

    def run(self, days):
        for _ in range(days): self.step()
        return self

    def state_hash(self):
        h = hashlib.sha256()
        for (t,) in self.x("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            for row in self.x(f'SELECT * FROM {t} ORDER BY rowid'): h.update(repr(row).encode())
        return h.hexdigest()[:16]

    # ------------------------------------------------------------------ 人: 作息是函数, 例外才是状态
    def person(self, pid):
        if pid not in self.pcache:
            r = self.x('SELECT id,name,gen,hall,home,joined,died,status FROM person WHERE id=?', (pid,)).fetchone()
            self.pcache[pid] = dict(zip(('id', 'name', 'gen', 'hall', 'home', 'joined', 'died', 'status'), r)) if r else None
        return self.pcache[pid]

    def alive_at(self, p, day):
        return p['joined'] <= day and (p['died'] is None or p['died'] >= day) and p['status'] != '游方'

    def make_roster(self, day):
        """值守排班: 每日结算时落盘, 之后不再重算 (历史不可改写)。"""
        el = lambda sql: [r[0] for r in self.x("SELECT id FROM person WHERE status='在寺' AND " + sql + ' ORDER BY id')]
        posts = [('山门', 'SH_GATE', range(3, 11), 2, el("hall='罗汉堂' AND gen='虚'")),
                 ('藏经阁', 'SH_LIBRARY', range(0, 12), 1, el("hall='藏经阁' AND gen='虚'")),
                 ('夜巡', 'SH_GROUNDS', (11, 0, 1), 2, el("hall='罗汉堂' AND gen='慧'")),
                 ('粮库', 'SH_GRANARY', (10, 11, 0, 1, 2), 1, el("hall='戒律院' AND gen='虚'"))]
        for post, place, slots, n, e in posts:
            if not e: continue
            for j, slot in enumerate(slots):
                for k in range(min(n, len(e))):
                    self.x('INSERT INTO roster VALUES(?,?,?,?,?)', (day, post, slot, e[(day * 5 + (j // 2) * n + k) % len(e)], place))

    def template(self, p, day, slot):
        c, s = cal(day), SLOTS[slot]
        office = self.office_of(p['id'], day)
        base = office.lstrip('副') if office else None
        site = SITE.get(base)
        if base == '庄主': return ('EST', '庄务' if s in '辰巳未申' else '歇息')
        if s in '亥子丑': return (p['home'], '歇息')
        if s == '寅': return ('SH_KITCHEN', '执事') if base == '典座' else ('SH_HALL', '课诵')
        if s == '卯': return ('SH_KITCHEN', '执事') if base == '典座' else ('SH_REFECTORY', '斋粥')
        if s == '午': return ('SH_REFECTORY', '斋粥')
        if s == '酉': return ('SH_HALL', '课诵')
        if s == '戌': return (site, '执事') if site and base in ('监院', '库头', '知客') else ('SH_ZEN', '坐禅')
        if c['shuowang'] and s == '辰': return ('SH_FATANG', '布萨')
        if site: return (site, '执事')
        hall = p['hall']
        if p['gen'] == '玄': return (HALLPLACE.get(hall, 'SH_ZEN'), '授徒' if s in '辰申' else '禅修')
        if hall in HALLPLACE: return (HALLPLACE[hall], '练功' if s in '辰巳申' else '研武' if hall in ('达摩院', '般若堂') else '普请')
        if p['gen'] == '空': return ('SH_GROUNDS', '普请') if s in '辰未' else ('SH_ZEN', '学经') if s == '巳' else ('SH_YARD', '练功')
        if c['retreat'] and s == '未': return ('SH_ZEN', '坐禅')
        return ('SH_GROUNDS', '普请') if s in '辰未' else ('SH_YARD', '练功')

    def where(self, pid, day, slot):
        """某人某日某时辰在哪、在做什么: 先查例外(指派), 再查值守排班, 最后算作息模板。"""
        p = self.person(pid)
        if p is None or not self.alive_at(p, day): return None
        t = day * 12 + slot
        r = self.x('SELECT place, activity FROM assignment WHERE person=? AND t_from<=? AND t_to>=? ORDER BY id DESC LIMIT 1', (pid, t, t)).fetchone()
        if r: return tuple(r)
        if p['gen'] == '外': return ('SH_GUEST', '香客')
        r = self.x('SELECT place FROM roster WHERE person=? AND day=? AND slot=?', (pid, day, slot)).fetchone()
        if r: return (r[0], '值守')
        return self.template(p, day, slot)

    def present(self, place, day, slot, exclude=None):
        ids = [r[0] for r in self.x('SELECT id FROM person ORDER BY id')]
        return [i for i in ids if i != exclude and (self.where(i, day, slot) or (None,))[0] == place]

    # ------------------------------------------------------------------ 命令: 物理约束拒绝, 规范约束放行但记违规
    def has_key(self, actor, place, day, slot):
        o = self.office_of(actor, day)
        if o and SITE.get(o.lstrip('副')) == place: return True
        return self.x('SELECT 1 FROM roster WHERE person=? AND day=? AND slot=? AND place=?', (actor, day, slot, place)).fetchone() is not None

    def cmd_move(self, actor, place, day, slot):
        acc = self.x('SELECT access FROM place WHERE id=?', (place,)).fetchone()
        if acc and acc[0] == 'locked_night' and SLOTS[slot] in '亥子丑寅' and not self.has_key(actor, place, day, slot):
            self.ev('CMD_REJECTED', place=place, actor=actor, slot=slot, cmd='MOVE', why='夜间上锁, 无钥匙'); return False
        self.x('INSERT INTO assignment(person,t_from,t_to,place,activity) VALUES(?,?,?,?,?)', (actor, day * 12 + slot, day * 12 + slot, place, '走动'))
        return True

    def cmd_take(self, actor, item, day, slot):
        name, home, keeper, custodian, place = self.x('SELECT name,home,keeper,custodian,place FROM item WHERE id=?', (item,)).fetchone()
        here = self.where(actor, day, slot)
        if place is None or here is None or here[0] != place:
            self.ev('CMD_REJECTED', place=place, actor=actor, slot=slot, cmd='TAKE', why='人与物不在一处'); return None
        permitted = actor == custodian or actor == self.holder(keeper, day)
        wit = self.present(place, day, slot, exclude=actor)
        self.x('UPDATE item SET custodian=?, place=NULL WHERE id=?', (actor, item))
        e = self.ev('ITEM_TAKEN', place=place, actor=actor, slot=slot, item=name, norm='合规' if permitted else '违规', witnesses=wit)
        if not permitted and wit:
            r = self.ev('REPORT', place=place, actor=wit[0], cause=e, slot=slot, to='戒律院', about=actor)
            self.ev('CASE_OPENED', place='SH_JIELV', actor=self.holder('戒律院首座', day), cause=r, about=actor)
        return e

    def audit_items(self):
        for iid, name, home, keeper, place, known in self.x('SELECT id,name,home,keeper,place,missing_known FROM item ORDER BY id').fetchall():
            if place != home and not known:
                self.x('UPDATE item SET missing_known=1 WHERE id=?', (iid,))
                self.ev('AUDIT_MISSING', place=home, actor=self.holder(keeper), slot=4, item=name)

    # ------------------------------------------------------------------ 世界日报与因果追溯
    def chronicle(self, day, scope='temple'):
        c = cal(day)
        out = [f"【{cal_str(day)} · {c['term']}" + (f" · {c['festival']}" if c['festival'] else ' · 朔望' if c['shuowang'] else '') + '】']
        G = lambda k: GOODS[k][0]
        U = lambda k, q: shi(q) if k == 'grain' else f'{q} {GOODS[k][1]}'
        for typ, place, actor, payload, slot in self.x('SELECT type,place,actor,payload,slot FROM event_log WHERE day=? ORDER BY id', (day,)).fetchall():
            p, a, pl = json.loads(payload), self.pname(actor), PLACE_NAME.get(place, place or '')
            if scope == 'temple' and (place in ('DF', 'PORT') or p.get('kind') == 'IMPORT'): continue
            if typ == 'ROAD_CLOSED': s = f"{p['reason']}，少室山道不通，预计 {p['days']} 日。"
            elif typ == 'ROAD_OPEN': s = '少室山道复通。'
            elif typ == 'HARVEST': s = (f"柏谷庄{p['crop']}收，年景 {p['yf']}。佃户共收 {shi(p['gross'])}，庄主{a}收租 {shi(p['rent'])} 入庄仓，"
                                        f"纳两税 {shi(p['tax_temple'])}。" + ('年成大坏，寺院减租、官府蠲免。' if p.get('remission') else ''))
            elif typ == 'MARKET_SALES': s = f"登封粮市：{p['n']} 户农家卖出余粮 {shi(p['qty'])}，每石 {p['price']} 文。"
            elif typ == 'GRAIN_SOLD': s = f"监院{a}售庄仓余粮 {shi(p['q'])}，得钱 {guan(p['money'])}。"
            elif typ == 'ALMS': s = f"香客 {p['pilgrims']} 人，香火钱 {guan(p['money'])}" + (f"，留宿 {p['guests']} 人。" if p['guests'] else '。')
            elif typ == 'DONOR': s = f"有大施主布施 {guan(p['money'])}。"
            elif typ == 'RITE': s = f"维那{a}在法堂主持法事一场，收 {guan(p['money'])}。"
            elif typ == 'GUEST_TURNED_AWAY': s = f"客房已满，知客{a}婉拒 {p['n']} 人留宿。"
            elif typ == 'GUESTS_SUSPENDED': s = f"粮食告急，知客{a}暂停挂单，{p['n']} 人未能留宿。"
            elif typ == 'TIER_CHANGE': s = f"库头{a}报：寺库存粮可支 {p['cover']} 日，由“{p['frm']}”转“{p['to']}”。"
            elif typ == 'ORDER_OPEN':
                k = {'TRANSFER': '从庄仓调', 'PURCHASE': '采买', 'IMPORT': '向外地进', 'REPAIR': '修缮用', 'ALMS': '外出募化', 'BORROW': '向邻寺借'}[p['kind']]
                s = f"{a or '铺户'}开单：{k}" + (f"{G(p['c'])} {U(p['c'], p['q'])}。" if p['kind'] != 'ALMS' else '。')
            elif typ == 'ORDER_RENEWED': s = f"监院续单（承前单 {p['parent']}）：{G(p['c'])} {U(p['c'], p['q'])}。"
            elif typ == 'ORDER_APPROVED': s = f"监院{a}批准采买{G(p['c'])} {U(p['c'], p['q'])}，计 {guan(p['cost'])}。"
            elif typ == 'ORDER_REDUCED': s = f"钱不凑手，监院{a}将采买数量由 {p['frm']} 减为 {p['to']}。"
            elif typ == 'ORDER_DEFERRED': s = f"账上钱不够，监院{a}暂缓采买{G(p['c'])}。"
            elif typ == 'ORDER_BLOCKED': s = f"{G(p['c'])}订单受阻：{p['why']}。"
            elif typ == 'ORDER_RESUMED': s = None
            elif typ == 'ORDER_EXPIRED': s = f"{G(p['c'])}采买单逾期未办（{p['why']}），上报监院。"
            elif typ == 'ORDER_FAILED': s = f"{G(p['c'])}订单" + (f"因{p['why']}" if p['why'] != '超期' else '') + "超期，判为失败，上报监院。"
            elif typ == 'SHIP_OUT': s = f"{pl}发出{G(p['c'])} {U(p['c'], p['q'])}。" if p['c'] == 'grain' else None
            elif typ == 'SHIP_IN': s = f"{G(p['c'])} {U(p['c'], p['q'])} 运抵{pl}" + (f"，付 {guan(p['paid'])}。" if p['paid'] else '。')
            elif typ == 'GOODS_RETURNED': s = f"货款不足，{G(p['c'])} {U(p['c'], p['q'])} 退回。"
            elif typ == 'MEALS': s = (f"典座{a}供粥斋，僧 {p['head']} 人" + (f"、客 {p['guests']} 人" if p['guests'] else '') + f"，用粮 {shi(p['grain'])}"
                                      + ('。' if p['tier'] in ('充足', '留意') else '（减供）。'))
            elif typ == 'MEAL_SHORT': s = f"断炊：{p['why']}，应供 {shi(p['need'])}，实供 {shi(p['got'])}。"
            elif typ == 'SHORTAGE': s = f"库头{a}报：{G(p['c'])}告罄。"
            elif typ == 'FORAGE': s = f"封路缺柴，直岁{a}领众普请，上山打柴 {p['q']} 担。"
            elif typ == 'CLOTH_ISSUED': s = f"库头{a}发放僧衣用布 {p['q']} 匹" + (f"，尚欠 {p['owed']} 匹。" if p.get('owed') else '。')
            elif typ == 'DAMAGE': s = f"{p['what']}损坏。"
            elif typ == 'REPAIR_START': s = f"直岁{a}动工修{p['what']}，用料 {p['timber']} 料，雇工 {p['labor']} 人日。"
            elif typ == 'REPAIR_DONE': s = f"{p['what']}修毕。"
            elif typ == 'DEATH': s = f"{a}圆寂" + (f"，所任{'、'.join(p['offices'])}出缺。" if p['offices'] else '。')
            elif typ == 'ACTING': s = f"副职{a}代理{p['office']}。"
            elif typ == 'APPOINT': s = f"方丈{a}任命{self.pname(p['person'])}为{p['office']}。"
            elif typ == 'RECRUIT': s = f"方丈{a}收录新僧 {p['n']} 人。"
            elif typ == 'CHARITY': s = f"腊八施粥，典座{a}于山门外散粥，用粮 {shi(p['grain'])}。"
            elif typ == 'MERIT_SPEND': s = f"岁末结余，方丈{a}拨 {guan(p['money'])} 修造功德。"
            elif typ == 'HH_BORROW': s = f"佃户 {p['hh']} 断粮，庄主{a}自庄仓借出 {shi(p['q'])}。"
            elif typ == 'RELIEF': s = f"农户 {p['hh']} 断粮三日，知客{a}开库赈济 {shi(p['q'])}。"
            elif typ == 'TENANTS_SETTLED': s = f"庄主{a}招得新佃 {p['n']} 户。"
            elif typ == 'MONKS_RETURN': s = f"游方僧 {p['n']} 人归寺。"
            elif typ == 'HH_LEFT': s = f"农户 {p['hh']} 无以为生，离乡而去。"
            elif typ == 'ALMS_ROUND_OUT': s = f"化主{a}下山募化。"
            elif typ == 'ALMS_ROUND_BACK': s = f"化主{a}募化归来，得粮 {shi(p['grain'])}、钱 {guan(p['money'])}。"
            elif typ == 'GRAIN_REPAID': s = f"监院{a}归还{p['to']}借粮 {shi(p['q'])}。"
            elif typ == 'ITEM_TAKEN': s = f"{SLOTS[slot]}时，{a}自{pl}取走{p['item']}（{p['norm']}，在场 {len(p['witnesses'])} 人）。"
            elif typ == 'REPORT': s = f"{a}向{p['to']}举报{self.pname(p['about'])}。"
            elif typ == 'CASE_OPENED': s = f"戒律院首座{a}立案查问{self.pname(p['about'])}。"
            elif typ == 'AUDIT_MISSING': s = f"月朔点检，{a}发现{p['item']}不在{pl}。"
            elif typ == 'CMD_REJECTED': s = None
            else: s = None
            if s: out.append('  ' + s)
        return '\n'.join(out)

    def why(self, eid):
        chain = []
        while eid:
            day, typ, payload, cause = self.x('SELECT day,type,payload,cause FROM event_log WHERE id=?', (eid,)).fetchone()
            chain.append(f'{cal_str(day)} {typ} {payload}'); eid = cause
        return chain


# ====================================================================== 报告
def year_report(w, y):
    days = [s for s in w.series if s['year'] == y]
    d0, d1 = y * YEAR, y * YEAR + YEAR - 1
    money = dict(w.x("SELECT reason, SUM(CASE WHEN payee='ORG_SH' THEN amount ELSE -amount END) FROM ledger "
                     "WHERE (payer='ORG_SH' OR payee='ORG_SH') AND day BETWEEN ? AND ? AND reason<>'期初' GROUP BY reason", (d0, d1)).fetchall())
    orders = dict(w.x('SELECT state, COUNT(*) FROM work_order WHERE created BETWEEN ? AND ? GROUP BY state', (d0, d1)).fetchall())
    ontime = w.x("SELECT COUNT(*) FROM work_order WHERE created BETWEEN ? AND ? AND state='完成' AND closed<=deadline", (d0, d1)).fetchone()[0]
    closed_n = sum(v for k, v in orders.items() if k in ('完成', '失败', '过期'))
    return dict(
        year=y, cash_start=days[0]['cash'] / GUAN, cash_end=days[-1]['cash'] / GUAN,
        cover_min=round(min(s['cover'] for s in days), 1), total_min=round(min(s['total'] for s in days), 1),
        tier_days={t: sum(1 for s in days if s['tier'] == t) for t in TIERS if any(s['tier'] == t for s in days)},
        closed_days=sum(1 for s in days if s['closed']),
        grain={k: round(v / SHI) for (yy, k), v in sorted(w.tg.items()) if yy == y},
        money={k: round(v / GUAN, 1) for k, v in sorted(money.items(), key=lambda kv: -kv[1])},
        income=round(sum(v for v in money.values() if v > 0) / GUAN, 1), spend=round(-sum(v for v in money.values() if v < 0) / GUAN, 1),
        orders=orders, ontime_rate=round(ontime / closed_n, 3) if closed_n else None,
        events=w.x('SELECT COUNT(*) FROM event_log WHERE day BETWEEN ? AND ?', (d0, d1)).fetchone()[0],
        head_end=days[-1]['head'])


def summary(w, label):
    print(f'\n===== {label} =====')
    print(f'不变量违规: {len(w.viol)}', w.viol[:5] if w.viol else '')
    for y in range(1, w.year):
        r = year_report(w, y)
        print(f"第{y}年: 余钱 {r['cash_start']:.0f}->{r['cash_end']:.0f} 贯 | 收 {r['income']} 支 {r['spend']} | 寺库最低 {r['cover_min']} 日, 总量最低 {r['total_min']} 日 "
              f"| 档位日数 {r['tier_days']} | 封路 {r['closed_days']} 日 | 订单 {r['orders']} 按期 {r['ontime_rate']} | 事件 {r['events']} | 僧 {r['head_end']}")
    c = w.cnt
    print(f"累计: 断炊日 {c['meal_short']} | 缺货日 " + ' '.join(f"{GOODS[k][0]}{c['short_' + k]}" for k in GOODS if c['short_' + k]) +
          f" | 上报 {c['escalated']} | 佃户借粮 {c['hh_borrow']} 次 赈济 {c['relief']} 次 | 农户挨饿 {c['hunger_days']} 户日 | 离乡 {c['hh_left']} 户 | 僧人圆寂 {c['deaths']} 离寺 {c['monks_left']}")
    hh = w.x("SELECT h.kind, COUNT(*), AVG(a.balance), AVG(s.qty), AVG(h.members) FROM household h JOIN account a ON a.id=h.id JOIN stock s ON s.owner=h.id "
             "AND s.commodity='grain' WHERE h.status='在' GROUP BY h.kind").fetchall()
    print('农户期末: ' + ' | '.join(f'{k} {n}户 均钱{c_ / GUAN:.1f}贯 均粮{g / SHI:.1f}石' for k, n, c_, g, m in hh))
    b = dict(w.x('SELECT id, balance FROM account WHERE boundary=1 OR id LIKE "SHOP%"').fetchall())
    print('边界与铺户余额(贯): ' + ' '.join(f'{k}={v / GUAN:.0f}' for k, v in b.items()))


def baseline(years=3, params=None, setup=None):
    w = World(params)
    if setup: setup(w)
    return w.run(YEAR * (1 + years))


def people_tests(w):
    """M2/M4 子集: 作息函数、值守排班、历史不可改写、物理/规范两层约束。"""
    print('\n===== 人物与独有物测试 =====')
    monks = [r[0] for r in w.x("SELECT id FROM person WHERE org='ORG_SH' ORDER BY id")]
    d0 = YEAR + 97                                            # 第1年四月初八 佛诞
    use, missing = defaultdict(int), 0
    snap = {}
    for pid in monks:
        for s in range(12):
            r = w.where(pid, d0, s)
            if r is None:
                if w.alive_at(w.person(pid), d0): missing += 1
                continue
            use[r[1]] += 1; snap[(pid, s)] = r
    tot = sum(use.values())
    print('佛诞日全寺时间分配: ' + ' '.join(f'{k}{v / tot:.0%}' for k, v in sorted(use.items(), key=lambda kv: -kv[1])))
    print(f'在世而查不到位置的人次: {missing}')
    dup = w.x('SELECT COUNT(*) FROM (SELECT day,slot,person FROM roster GROUP BY 1,2,3 HAVING COUNT(*)>1)').fetchone()[0]
    print(f'同一时辰被排两处值守的人次: {dup}')
    for place, slot in (('SH_HALL', 2), ('SH_REFECTORY', 6), ('SH_LIBRARY', 0), ('SH_PUTI', 6), ('SH_PUTI', 5), ('SH_GATE', 4)):
        ps = w.present(place, d0, slot)
        print(f"  {cal_str(d0)} {SLOTS[slot]}时 {PLACE_NAME[place]}: {len(ps)} 人" + (f"（{'、'.join(w.pname(p) for p in ps[:4])}）" if 0 < len(ps) <= 4 else ''))
    xz = w.x("SELECT id FROM person WHERE name='虚竹'").fetchone()[0]
    print('  虚竹一日: ' + ' '.join(f"{SLOTS[s]}{PLACE_NAME.get(w.where(xz, d0, s)[0], '僧寮')}·{w.where(xz, d0, s)[1]}" for s in range(12)))
    m = w.x("SELECT p2.name FROM person p JOIN person p2 ON p2.id=p.master WHERE p.name='虚竹'").fetchone()[0]
    print(f'  虚竹的师父: {m}')
    # 历史不可改写: 世界又过了两年多(有人圆寂、岗位更替), 重问第1年佛诞日的位置, 必须与当时一致
    changed = sum(1 for (pid, s), r in snap.items() if w.where(pid, d0, s) != r)
    print(f'隔两年重问当日位置, 答案变了的人次: {changed} / {len(snap)}')

    # 三种取物: 物理拒绝 / 违规无人见 -> 月朔点检发现 / 违规被见 -> 当场举报
    w.x('BEGIN')
    thief = w._mk('外', '香客甲', 30, '外客', joined=w.day); w.x("UPDATE person SET kind='临时', org='外来' WHERE id=?", (thief,))
    w.x('COMMIT'); w.run(2); w.x('BEGIN')
    d = w.day
    ok = w.cmd_move(thief, 'SH_LIBRARY', d, 0)
    print(f'  子时潜入藏经阁: {"放行" if ok else "物理层拒绝（夜间上锁，无钥匙）"}')
    w.cmd_move(thief, 'SH_PUTI', d, 6)
    e1 = w.cmd_take(thief, 'IT_YJJ', d, 6)
    p1 = json.loads(w.x('SELECT payload FROM event_log WHERE id=?', (e1,)).fetchone()[0])
    print(f"  午时菩提院取《易筋经》: 已执行，{p1['norm']}，见证 {len(p1['witnesses'])} 人")
    w.cmd_move(thief, 'SH_LIBRARY', d, 5)
    e2 = w.cmd_take(thief, 'IT_BRZ', d, 5)
    p2 = json.loads(w.x('SELECT payload FROM event_log WHERE id=?', (e2,)).fetchone()[0])
    rep = w.x("SELECT COUNT(*) FROM event_log WHERE type='REPORT' AND cause=?", (e2,)).fetchone()[0]
    print(f"  巳时藏经阁取《般若掌》图谱: 已执行，{p2['norm']}，见证 {len(p2['witnesses'])} 人，当场举报 {rep} 起")
    w.x('COMMIT')
    start = w.day
    while not w.x("SELECT 1 FROM event_log WHERE type='AUDIT_MISSING' AND payload LIKE '%易筋经%'").fetchone() and w.day < start + 40: w.step()
    print(f'  《易筋经》失窃在 {w.day - start} 日后的月朔点检中被发现；这期间无人知情')
    print(w.chronicle(d))


def window(w, d0, d1, types=None):
    rows = w.x('SELECT type, COUNT(*) FROM event_log WHERE day BETWEEN ? AND ? GROUP BY type', (d0, d1)).fetchall()
    return {k: v for k, v in rows if types is None or k in types}


def experiments():
    Y2 = 2 * YEAR
    # ---- E1 封路
    start = Y2 + 330
    w = baseline(3, setup=lambda w: w.hooks[start].append(lambda w: w.close_road(45, '扰动:封路')))
    summary(w, 'E1 封路 45 日 (第2年腊月初一起)')
    win = [s for s in w.series if start <= s['day'] <= start + 70]
    reopen = start + 45
    rec = next((s['day'] - reopen for s in win if s['day'] >= reopen and s['blocked'] == 0 and s['short'] == 0), None)
    first_short = next((s['day'] - start for s in win if s['short'] > 0), None)
    print(f"  窗口内: 寺库最低 {min(s['cover'] for s in win):.1f} 日 | 首次缺货在封路第 {first_short} 日 | 同时受阻订单最多 {max(s['blocked'] for s in win)} 张 "
          f"| 复通后 {rec} 日内全部补齐 | 事件 {window(w, start, start + 60, ('ORDER_BLOCKED', 'ORDER_FAILED', 'ORDER_RENEWED', 'ORDER_ESCALATED', 'SHORTAGE', 'FORAGE', 'MEAL_SHORT'))}")
    e = w.x("SELECT id FROM event_log WHERE type='SHORTAGE' AND day>=? AND cause IS NOT NULL ORDER BY id LIMIT 1", (start,)).fetchone()
    if e: print('  因果追溯:', *w.why(e[0]), sep='\n     <- ')
    for d in (start, start + 22, reopen, reopen + 2): print(w.chronicle(d))
    # ---- E2 歉收 / E2b 大荒
    w = baseline(3, setup=lambda w: w.yield_override.update({(2, '麦'): 0.75, (2, '粟'): 0.75})); summary(w, 'E2 歉收 (第2年亩产 x0.75)')
    w = baseline(7, setup=lambda w: w.yield_override.update({(2, '麦'): 0.5, (2, '粟'): 0.5})); summary(w, 'E2b 大荒 (第2年亩产 x0.5), 连看 7 年')
    for y in range(1, 8):
        ds = [s for s in w.series if s['year'] == y]
        print(f"  第{y}年: 佃户 {ds[-1]['tenants']} 户 | 僧 {min(s['head'] for s in ds)}-{ds[-1]['head']} | 余钱 {ds[-1]['cash'] / GUAN:.0f} 贯 | 寺库最低 {min(s['cover'] for s in ds):.0f} 日 "
              f"| 非充足 {sum(1 for s in ds if s['tier'] != '充足')} 日 | {window(w, y * YEAR, y * YEAR + 359, ('ALMS_ROUND_BACK', 'HH_LEFT', 'RELIEF', 'HH_BORROW', 'TENANTS_SETTLED', 'MONKS_RETURN', 'ORDER_EXPIRED', 'MEAL_SHORT'))}")
    print(w.chronicle(Y2 + 125)); print(w.chronicle(3 * YEAR + 60))
    # ---- E3 典座离任
    def e3(w): w.hooks[Y2 + 100].append(lambda w: w.die(w._appointee('典座'), w.day - 1))
    w = baseline(3, setup=e3); summary(w, 'E3 典座离任 (第2年四月十一)')
    print('  ', window(w, Y2 + 100, Y2 + 104, ('DEATH', 'ACTING', 'APPOINT', 'MEAL_SHORT')))
    for d in (Y2 + 100, Y2 + 101): print(w.chronicle(d))
    # ---- E5 香期暴增
    w = baseline(3, setup=lambda w: w.pilgrim_boost.update({Y2 + 97: 10})); summary(w, 'E5 佛诞香客 x10 (第2年)')
    print(w.chronicle(Y2 + 97))
    # ---- E6 余钱清零
    w = baseline(3, setup=lambda w: w.hooks[Y2 + 200].append(lambda w: w.pay('ORG_SH', 'EQUITY', w.bal('ORG_SH'), '扰动:余钱清零')))
    summary(w, 'E6 余钱清零 (第2年七月廿一)')
    print('  此后 160 日:', window(w, Y2 + 200, Y2 + 359, ('ORDER_REDUCED', 'ORDER_DEFERRED', 'ORDER_EXPIRED', 'ORDER_ESCALATED', 'SHORTAGE', 'CLOTH_ISSUED', 'MERIT_SPEND', 'MEAL_SHORT')))
    print('  余钱(每 30 日):', [round(s['cash'] / GUAN) for s in w.series if s['day'] in range(Y2 + 195, 4 * YEAR, 30)])
    for d in (Y2 + 235, Y2 + 256): print(w.chronicle(d))


def long_and_seeds():
    w = baseline(10); summary(w, '十年基准')
    print('  年末余钱(贯):', [round([s for s in w.series if s['year'] == y][-1]['cash'] / GUAN) for y in range(1, 11)])
    print('  年内寺库最低(日):', [round(min(s['cover'] for s in w.series if s['year'] == y)) for y in range(1, 11)])
    print('  年末僧数:', [[s for s in w.series if s['year'] == y][-1]['head'] for y in range(1, 11)], '| 佃户:', [[s for s in w.series if s['year'] == y][-1]['tenants'] for y in range(1, 11)])
    print('  事件总数:', w.x('SELECT COUNT(*) FROM event_log').fetchone()[0], '| 排班行:', w.x('SELECT COUNT(*) FROM roster').fetchone()[0],
          '| 账目行:', w.x('SELECT COUNT(*) FROM ledger').fetchone()[0])
    print('\n===== 换 6 个种子各跑 3 年 =====')
    for seed in (1, 7, 42, 1094, 8848, 20261110):
        w = baseline(3, params=dict(seed=seed)); ds = [s for s in w.series if s['year'] >= 1]
        c = w.cnt
        ye = [round([s for s in ds if s['year'] == y][-1]['cash'] / GUAN) for y in (1, 2, 3)]
        ot = [year_report(w, y)['ontime_rate'] for y in (1, 2, 3)]
        print(f"  seed={seed:<9} 违规 {len(w.viol)} | 余钱 {min(s['cash'] for s in ds) / GUAN:.0f}-{max(s['cash'] for s in ds) / GUAN:.0f} 贯 (年末 {ye}) | 按期率 {ot} | 寺库最低 {min(s['cover'] for s in ds):.0f} 日 "
              f"| 非充足 {sum(1 for s in ds if s['tier'] != '充足')} 日 | 封路 {sum(1 for s in ds if s['closed'])} 日 | 断炊 {c['meal_short']} | 挨饿 {c['hunger_days']} 户日 | 离乡 {c['hh_left']} "
              f"| 缺货日 " + ' '.join(f"{GOODS[k][0]}{c['short_' + k]}" for k in GOODS if c['short_' + k]))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--all', action='store_true'); a = ap.parse_args()
    t0 = time.time(); w = baseline(3); t1 = time.time()
    h1 = w.state_hash(); h2 = baseline(3).state_hash()
    summary(w, f'基准: 预热1年 + 3年 (用时 {t1 - t0:.1f} 秒, 状态哈希 {h1}, 重跑一致={h1 == h2})')
    for y in (1, 2, 3):
        r = year_report(w, y)
        print(f'  第{y}年 寺院粮账(石): {r["grain"]}')
        print(f'  第{y}年 寺院钱账(贯): {r["money"]}')
    for d in (YEAR + 125, YEAR + 97, YEAR + 337): print(w.chronicle(d))
    if a.all:
        experiments()
        long_and_seeds()
        people_tests(w)


if __name__ == '__main__':
    main()
