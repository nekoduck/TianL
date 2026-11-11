"""钱物原语与工作订单（v0.2 内核的经济底层）。

钱：复式记账，边界账户可透支，其余不得透支。物：只能转移，产生与消灭必须具名；在途货物仍算在总量里。
订单：规则开单 -> 审批 -> 发运 -> 到货 -> 完成；超期过期或失败，由上级续单并继承在途货物。
"""
from ..core.calendar import YEAR
from .vocab import SHI, GUAN, LIVE, LIVE_SQL


class EconomyMixin:
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
        if payee != self.ac.village: return self.pay(payer, payee, amt, reason)
        hh = self.x("SELECT id, members FROM household WHERE kind=? AND status='在' ORDER BY id", (self.hk.wood,)).fetchall()
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

    # ------------------------------------------------------------------ 价格与路况
    def closed(self, d=None):
        d = self.day if d is None else d
        return self.x('SELECT 1 FROM route_closure WHERE from_day<=? AND to_day>=?', (d, d)).fetchone() is not None

    def grain_price(self):
        doy = self.day % YEAR
        s = next((f for lo, hi, f in self.S.season.grain_season if lo <= doy < hi), 1.0)
        return int(self.P['grain_price'] * s * self.price_factor)

    def price(self, c):
        if c != self.cm.staple: return self.G[c].price
        p = self.grain_price()
        return int(p * self.K['thin_markup']) if self.qty(self.ac.shop_grain, self.pl.town, c) < self.K['thin_shop_stock_shi'] * SHI else p

    def cost(self, c, q): return q * self.price(c) // SHI if c == self.cm.staple else q * self.price(c)

    def head(self):
        return self.x("SELECT COUNT(*) FROM person WHERE org=? AND status='在寺'", (self.ac.org,)).fetchone()[0]

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
        if c == self.cm.staple: self.block_ev = e

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
