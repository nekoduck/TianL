"""World：v0.2 少林寺世界基座的内核（reference/shaolin_spike.py 的移植）。

由若干 mixin 组成（各管一块职责），这里放构造、库表、事件、哈希与时间指针。
所有少林寺专有的编号、名字与数值都来自 Spec（defs/*.toml），见 tianl/kernel/spec.py。

时间指针（ARCHITECTURE 第 5 节）：
  day, slot            下一个要跑的时辰（slot 0..11）；
  begin_day()          BEGIN；hooks；weather -> arrivals -> production -> visitors -> rules -> orders -> consumption；[engine.begin_day]
  run_slot()           [engine.run_slot(day, slot)]；slot += 1
  end_day()            十二时辰须已走完（否则 RuntimeError）；[engine.end_day(day)]；people（圆寂、继任、收录、次日班表）-> check -> COMMIT；day += 1
  step() = begin_day(); 12 x run_slot(); end_day()        与原型 step() 逐位相同（未接引擎时）
  advance(n) 走 n 个时辰，自动处理跨日；日内停在时辰边界时事务保持打开。
"""
import hashlib
import json
import sqlite3
from collections import defaultdict

from ..core.calendar import SLOTS_PER_DAY, YEAR
from ..core.rng import rnd
from .chronicle import ChronicleMixin
from .commands import CommandsMixin
from .coupling import CouplingMixin
from .economy import EconomyMixin
from .invariants import InvariantsMixin
from .people import PeopleMixin
from .phases import PhasesMixin
from .rules import RulesMixin
from .schedule import ScheduleMixin
from .spec import load_spec
from .vocab import GUAN

ECON_TABLES = ('account', 'ledger', 'stock', 'shipment', 'work_order', 'household', 'arrears', 'route_closure')

SCHEMA = '''
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
        '''


class World(EconomyMixin, PhasesMixin, RulesMixin, PeopleMixin, ScheduleMixin, CommandsMixin, CouplingMixin, InvariantsMixin, ChronicleMixin):
    def __init__(self, params=None, spec=None, defs=None, engine=None):
        """params 只覆盖参数 P；spec 缺省时由 defs（缺省仓库 defs/）装配；engine 见 attach()。"""
        S = self.S = spec if spec is not None else load_spec(defs)
        self.P = dict(S.P); self.P.update(params or {})
        self.K, self.G, self.pl, self.ac, self.cm, self.hk, self.T = S.K, S.goods, S.pl, S.ac, S.cm, S.hh, S.T
        self.hk_class = {c.code: c for c in S.hh_classes}
        self.TG, self.R = S.labels['grain_ledger'], S.labels['reasons']   # 粮账类别名；钱账事由（流水 reason）
        self.cal, self.cal_str = S.cal.cal, S.cal.cal_str
        self.db = sqlite3.connect(':memory:'); self.db.isolation_level = None
        self.x = self.db.execute
        self.day, self.slot, self._began = 0, 0, False
        self.net = defaultdict(int)        # 各品类累计净流入 (物守恒的对账基准)
        self.flows = defaultdict(int)      # (年, 品类, 类别) -> 数量
        self.tg = defaultdict(int)         # 寺院粮食账: (年, 类别) -> 合
        self.viol, self.series = [], []
        self.yield_override, self.pilgrim_boost = {}, {}
        self.price_factor = 1.0
        self.tier_i, self.guests, self.pilgrims_today = 0, 0, 0
        self.road_ev = self.block_ev = None
        self.block_c, self.cloth_due, self.last_alms = {}, 0, -999
        self.vacant, self.vac_days = {}, defaultdict(int)
        self.cnt = defaultdict(int)
        self.hooks = defaultdict(list)
        self.engine = None
        self._init_couplings()
        self.pids, self.names, self.pcache = [], set(S.org.reserved), {}
        self._pool = list(dict.fromkeys(S.org.pool))
        self._schema()
        self.x('BEGIN'); self._populate(); self._people(); self.make_roster(0); self.x('COMMIT')
        if engine is not None: self.attach(engine)

    # ------------------------------------------------------------------ 基础设施
    def close(self):
        """关闭内存库（未提交的日内事务随之丢弃）。"""
        try: self.db.close()
        except Exception: pass

    def __del__(self): self.close()

    def u(self, *k): return rnd(self.P['seed'], *k)

    @property
    def year(self): return self.day // YEAR

    @property
    def tier(self): return self.K['tiers'][self.tier_i]

    @tier.setter
    def tier(self, name): self.tier_i = self.K['tiers'].index(name)

    def _schema(self):
        self.db.executescript(SCHEMA)

    def ev(self, typ, place=None, actor=None, cause=None, slot=None, **payload):
        cur = self.x('INSERT INTO event_log(day,slot,type,place,actor,payload,cause) VALUES(?,?,?,?,?,?,?)',
                     (self.day, slot, typ, place, actor, json.dumps(payload, ensure_ascii=False, sort_keys=True), cause))
        return cur.lastrowid

    def attach(self, engine):
        """接上 NPC 引擎（协议见 ARCHITECTURE 5.1）。接上后 run_slot 调 engine.run_slot，where 对引擎管理的人转交 engine.where。
        开局的人已在库里；engine.attach(world) 时由引擎自己读 person 表。"""
        self.engine = engine
        engine.attach(self)

    # ------------------------------------------------------------------ 初始世界
    def _populate(self):
        Pm, K, S, x = self.P, self.K, self.S, self.x
        for code, name, access in S.places: x('INSERT INTO place VALUES(?,?,?)', (code, name, access))
        for a in S.accounts:
            if not a.virtual: x('INSERT INTO account VALUES(?,?,0)', (a.code, a.boundary))
        for a in S.accounts:
            if a.opening_cash is not None: self.pay(self.ac.equity, a.code, a.opening_cash * GUAN, self.R['opening'])
        for e in S.opening_stock:
            q = e.v if e.kind == 'qty' else self.G[e.c].use * e.v if e.kind == 'days' else self.G[e.c].band[1]
            self.produce(e.owner, e.place, e.c, q, 'opening')
        for cls in S.hh_classes:
            for i in range(Pm[cls.count]):
                hid = f'{cls.prefix}{i + 1:03d}'
                m = K['member_min'] + int(self.u('members', hid) * K['member_span'])
                name = None
                if hid in S.hh_special: m, name = S.hh_special[hid]
                x('INSERT INTO household VALUES(?,?,?,?,?,?,?,?,?)',
                  (hid, cls.code, cls.place, name, m, m * cls.mu, m * Pm['ration_folk'], '在', 0))
                x('INSERT INTO account VALUES(?,0,0)', (hid,))
                self.pay(self.ac.equity, hid, cls.cash * GUAN, self.R['opening'])
                self.produce(hid, cls.place, self.cm.staple, m * Pm['ration_folk'] * S.hh_grain_days, 'opening')
        self.P['temple_mu'] = self.x("SELECT SUM(land) FROM household WHERE kind=?", (self.hk.tenant,)).fetchone()[0]

    # ------------------------------------------------------------------ 时间指针与分步接口
    def begin_day(self):
        if self._began: raise RuntimeError('今日已 begin_day，请先 end_day')
        self.x('BEGIN'); self._began = True
        for fn in self.hooks.pop(self.day, []): fn(self)
        self.phase_weather(); self.phase_arrivals(); self.phase_production(); self.phase_visitors()
        self.phase_rules(); self.phase_orders(); self.phase_consumption()
        if self.engine is not None: self.engine.begin_day(self.day)

    def run_slot(self):
        if not self._began: raise RuntimeError('先 begin_day')
        if self.slot >= SLOTS_PER_DAY: raise RuntimeError('今日十二时辰已走完，请 end_day')
        if self.engine is not None: self.engine.run_slot(self.day, self.slot)
        self.slot += 1

    def end_day(self):
        """收盘。十二个时辰必须都走完：否则（接了引擎时）会静默漏掉剩下的 engine.run_slot；要补完这一日请用 step()。"""
        if not self._began: raise RuntimeError('先 begin_day')
        if self.slot < SLOTS_PER_DAY:
            raise RuntimeError(f'今日十二时辰才走了 {self.slot} 个，不能收盘；请继续 run_slot()，或用 step() 补完这一日')
        if self.engine is not None: self.engine.end_day(self.day)
        self.phase_people(); self.phase_check()
        self.x('COMMIT'); self._began = False
        self.day += 1; self.slot = 0

    def advance(self, n_slots):
        """走 n 个时辰。跨日时自动 end_day；下一日在要跑它的第一个时辰时才 begin_day（停在日界时不提前开新的一日）。"""
        for _ in range(n_slots):
            if not self._began: self.begin_day()
            self.run_slot()
            if self.slot >= SLOTS_PER_DAY: self.end_day()
        return self

    def step(self):
        """走完一整日 = begin_day(); 12 x run_slot(); end_day()。若日内已走了几个时辰，则补完这一日。"""
        if not self._began: self.begin_day()
        while self.slot < SLOTS_PER_DAY: self.run_slot()
        self.end_day()

    def run(self, days):
        for _ in range(days): self.step()
        return self

    # ------------------------------------------------------------------ 哈希
    def _hash(self, tables=None):
        h = hashlib.sha256()
        for (t,) in self.x("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            if tables is not None and t not in tables: continue
            for row in self.x(f'SELECT * FROM {t} ORDER BY rowid'): h.update(repr(row).encode())
        return h.hexdigest()[:16]

    def state_hash(self):
        """全库状态哈希（每张表按 rowid 顺序遍历，所以插入次序必须稳定）。"""
        return self._hash()

    def econ_hash(self):
        """只含经济表（account ledger stock shipment work_order household arrears route_closure）的哈希。"""
        return self._hash(ECON_TABLES)
