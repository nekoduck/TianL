"""每日不变量（v0.2）：钱守恒、物守恒、无透支、无负库存、订单不滞留、无无主在途货物、关键岗位空缺不超限。
违规只记录（World.viol），不中断运行；每日末再记一行时间序列（World.series）供报告用。
"""
from .vocab import LIVE_SQL


class InvariantsMixin:
    def phase_check(self):
        d, K = self.day, self.K
        bad = lambda k, v: self.viol.append((d, k, v))
        s = self.x('SELECT SUM(balance) FROM account').fetchone()[0]
        if s != 0: bad('钱守恒', s)
        r = self.x('SELECT id, balance FROM account WHERE boundary=0 AND balance<0').fetchall()
        if r: bad('账户透支', r[:3])
        for c in self.G:
            tot = self.x('SELECT COALESCE(SUM(qty),0) FROM stock WHERE commodity=?', (c,)).fetchone()[0] + \
                  self.x("SELECT COALESCE(SUM(qty),0) FROM shipment WHERE commodity=? AND state IN ('在途','滞留')", (c,)).fetchone()[0]
            if tot != self.net[c]: bad('物守恒:' + c, tot - self.net[c])
        r = self.x('SELECT owner, commodity, qty FROM stock WHERE qty<0').fetchall()
        if r: bad('负库存', r[:3])
        r = self.x(f'SELECT id FROM work_order WHERE state IN {LIVE_SQL} AND deadline+?<?', (K['grace_days'], d)).fetchall()
        if r: bad('订单滞留', [x[0] for x in r][:5])
        r = self.x(f"SELECT s.id FROM shipment s JOIN work_order o ON o.id=s.order_id WHERE s.state IN ('在途','滞留') AND o.state NOT IN {LIVE_SQL}").fetchall()
        if r: bad('无主在途货物', [x[0] for x in r][:5])
        for o in self.S.critical:
            if self.holder(o, d + 1) is None:
                self.vac_days[o] += 1
                if self.vac_days[o] > K['vac_limit']: bad('关键岗位空缺', o)
            else: self.vac_days[o] = 0
        daily = self.daily_grain()
        org, grain = self.ac.org, self.cm.staple
        sh = self.qty(org, self.pl.granary, grain); est = self.qty(org, self.pl.estate_granary, grain)
        self.series.append(dict(day=d, year=self.year, tier=self.tier, cover=sh / daily, total=(sh + est + self.transit(org, grain)) / daily,
                                cash=self.bal(org), head=self.head(), closed=self.closed(),
                                blocked=self.x("SELECT COUNT(*) FROM work_order WHERE buyer=? AND state='受阻'", (org,)).fetchone()[0],
                                short=sum(1 for k in self.G if self.cnt['streak_' + k] > 0),
                                tenants=self.x("SELECT COUNT(*) FROM household WHERE kind=? AND status='在'", (self.hk.tenant,)).fetchone()[0]))
