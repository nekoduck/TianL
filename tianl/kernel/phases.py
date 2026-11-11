"""每日结算的各阶段（天气 -> 到货 -> 产出 -> 香客 -> 消耗），以及年内的农事结算。

阶段次序由 World.begin_day 固定：hooks -> weather -> arrivals -> production -> visitors -> rules -> orders -> consumption。
rules 与 orders 在 rules.py；people 与 check 在 people.py、invariants.py（World.end_day）。
"""
from ..core.calendar import YEAR
from .vocab import SHI, GUAN


class PhasesMixin:
    # ------------------------------------------------------------------ 天气与路况
    def phase_weather(self):
        d, c, K = self.day, self.cal(self.day), self.K
        if d > 0 and self.closed(d - 1) and not self.closed(d):
            self.road_ev = self.ev('ROAD_OPEN', place=self.pl.road)
        if c['month'] in self.S.season.winter_months and not self.closed(d) and self.u('snow', d) < self.P['snow_prob']:
            dur = K['snow_min_days'] + int(self.u('snowdur', d) * K['snow_span'])
            self.close_road(dur, '大雪封山')

    def close_road(self, dur, reason):
        self.x('INSERT INTO route_closure VALUES(?,?,?,?)', (self.pl.road, self.day, self.day + dur - 1, reason))
        self.road_ev = self.ev('ROAD_CLOSED', place=self.pl.road, days=dur, reason=reason)

    # ------------------------------------------------------------------ 到货
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
                paid = self.pay_to(payer, payee, can, '货款:' + self.G[c].name)
            if acc > 0: self._add(do, dp, c, acc)
            self.x("UPDATE shipment SET state='已达', arrived=?, qty=? WHERE id=?", (d, acc, sid))
            self.x('UPDATE work_order SET delivered=delivered+? WHERE id=?', (acc, oid))
            self.ev('SHIP_IN', place=dp, order=oid, c=c, q=acc, paid=paid)
            if do == self.ac.org and c == self.cm.staple and payee: self.tg[(self.year, self.TG['bought'])] += acc
            self.finish_if_done(oid)

    # ------------------------------------------------------------------ 产出与农事
    def phase_production(self):
        d, c, Pm, K, se = self.day, self.cal(self.day), self.P, self.K, self.S.season
        for flag, crop in se.crops:
            if c[flag]: self.harvest(crop)
        if c['doy'] in se.sell_doys: self.households_sell()
        if c['doy'] in se.shop_doys: self.households_shop()
        if c['doy'] in se.after_harvest_doys: self.temple_after_harvest()
        m = c['month']
        self.produce(self.ac.org, self.pl.store, self.cm.fresh,
                     next((v['q'] for v in K['veg_yield'] if m in v['months']), K['veg_yield_default']), 'produce')
        if c['dom'] == 1:
            for h, m in self.x("SELECT id, members FROM household WHERE kind=? AND status='在' ORDER BY id", (self.hk.wood,)).fetchall():
                self.pay(self.ac.town, h, Pm['town_bg_income'] * m, '樵菜售予县城')
        if c['doy'] == se.new_year_doy and d > 0:             # 岁首招佃: 空出的佃田由外来户补上
            ten = self.hk_class[self.hk.tenant]
            gone = Pm[ten.count] - self.x("SELECT COUNT(*) FROM household WHERE kind=? AND status='在'", (ten.code,)).fetchone()[0]
            n = 0
            for k in range(gone):
                if self.u('immig', d, k) < K['immig_prob']:
                    hid = f"{ten.prefix}{self.x('SELECT COUNT(*) FROM household WHERE kind=?', (ten.code,)).fetchone()[0] + 1:03d}"
                    mm = K['member_min'] + int(self.u('members', hid) * K['member_span'])
                    self.x('INSERT INTO household VALUES(?,?,?,?,?,?,?,?,?)',
                           (hid, ten.code, ten.place, None, mm, mm * ten.mu, mm * Pm['ration_folk'], '在', 0))
                    self.x('INSERT INTO account VALUES(?,0,0)', (hid,)); self.pay(self.ac.port, hid, K['immig_cash_guan'] * GUAN, '迁入携带')
                    self.produce(hid, ten.place, self.cm.staple, mm * Pm['ration_folk'] * self.S.hh_grain_days, 'port_in'); n += 1
            if n: self.ev('TENANTS_SETTLED', place=ten.place, actor=self.holder(self.T.manor_head), n=n)
        if c['doy'] in se.return_doys and self.tier_i == 0:     # 收成后粮足: 游方僧归寺
            ids = [r[0] for r in self.x("SELECT id FROM person WHERE status='游方' ORDER BY id")] if self.engine else ()
            n = self.x("UPDATE person SET status='在寺' WHERE status='游方'").rowcount
            if n:
                self.pcache.clear(); self.ev('MONKS_RETURN', place=self.pl.gate, n=n)
                for pid in ids: self.engine.on_person_added(pid)
        if c['doy'] == se.year_end_doy:                       # 岁末: 铺户盈余转为铺主家用与商税, 流回县城
            for a in self.S.accounts:
                if a.year_end_cap is not None:
                    self.pay(a.code, self.ac.town, max(0, self.bal(a.code) - a.year_end_cap * GUAN), '铺主家用与商税')

    def harvest(self, crop):
        Pm, K, y = self.P, self.K, self.year
        yf = self.yield_override.get((y, crop), K['yield_base'] + K['yield_var'] * self.u('year', y, crop))
        self.price_factor = 1 + max(0.0, K['price_yield_ref'] - yf) * K['price_yield_slope']
        bad = yf < K['bad_yield']                             # 灾年: 寺院减租, 官府两税减半
        share, taxk = (K['bad_rent_share'] if bad else Pm['rent_share']), (K['bad_tax_mult'] if bad else 1.0)
        per = len(self.S.season.crops)                        # 年产按收获次数均分
        gross = rent = tax_hh = repaid = 0
        grain, org, granary = self.cm.staple, self.ac.org, self.pl.estate_granary
        for hid, kind, place, land in self.x("SELECT id,kind,place,land FROM household WHERE status='在' ORDER BY id").fetchall():
            g = self.produce(hid, place, grain, land / per * Pm['yield_net'] * yf * (K['hh_yield_base'] + K['hh_yield_var'] * self.u('hhy', hid, y, crop)) * SHI, 'produce')
            gross += g
            if kind == self.hk.tenant:
                r = self.move(hid, place, org, granary, grain, g * share); rent += r
                owe = self.x("SELECT qty FROM arrears WHERE debtor=? AND creditor=?", (hid, org)).fetchone()
                if owe and owe[0] > 0:
                    back = self.move(hid, place, org, granary, grain, min(owe[0], (g - r) * K['repay_n'] // K['repay_d']))
                    self.x("UPDATE arrears SET qty=qty-? WHERE debtor=? AND creditor=?", (back, hid, org)); repaid += back
            else:
                tax_hh += self.consume(hid, place, grain, land * Pm['tax'] / per * SHI * taxk, 'tax_out')
        t = self.consume(org, granary, grain, Pm['temple_mu'] * Pm['tax'] / per * SHI * taxk, 'tax_out')
        self.tg[(y, self.TG['rent'])] += rent; self.tg[(y, self.TG['tax'])] += t; self.tg[(y, self.TG['repaid'])] += repaid
        self.ev('HARVEST', place=self.pl.estate, actor=self.holder(self.T.manor_head), crop=crop, yf=round(yf, 3), gross=gross, rent=rent,
                tax_temple=t, tax_hh=tax_hh, repaid=repaid, remission=bad)

    def households_sell(self):
        K, se = self.K, self.S.season
        doy = self.day % YEAR
        nxt = (se.millet_doy - doy) if doy < se.millet_doy else (YEAR - doy + se.wheat_doy)
        p = self.grain_price() * K['sell_n'] // K['sell_d']
        grain, shop, town = self.cm.staple, self.ac.shop_grain, self.pl.town
        n = tot = 0
        for hid, place, need in self.x("SELECT id,place,need FROM household WHERE status='在' ORDER BY id").fetchall():
            sell = self.qty(hid, place, grain) - need * (nxt + K['sell_reserve_days'])
            sell = min(sell, max(0, self.bal(shop) - K['shop_cash_floor_guan'] * GUAN) * SHI // p)
            if sell <= 0: continue
            self.move(hid, place, shop, town, grain, sell)
            self.pay(shop, hid, sell * p // SHI, '卖余粮'); n += 1; tot += sell
        self.ev('MARKET_SALES', place=town, n=n, qty=tot, price=p)

    def households_shop(self):
        Pm, K = self.P, self.K
        gen, town = self.ac.shop_gen, self.pl.town
        for (hid,) in self.x("SELECT id FROM household WHERE status='在' ORDER BY id").fetchall():
            for h in K['hh_shop']:
                c = h['c']
                q = min(Pm[h['want']], self.qty(gen, town, c), max(0, self.bal(hid) - h['floor_guan'] * GUAN) // self.G[c].price)
                if q > 0:
                    self.consume(gen, town, c, q, 'consume_hh'); self.pay(hid, gen, q * self.G[c].price, '家用:' + self.G[c].name)
            spare = max(0, self.bal(hid) - K['hh_spare_floor_guan'] * GUAN)    # 留三贯买粮钱, 富余的才花; 钱多的多花
            self.pay(hid, self.ac.town, min(spare, Pm['hh_misc'] + max(0, spare - K['hh_rich_guan'] * GUAN) * K['hh_rich_n'] // K['hh_rich_d']), '家用:杂项')

    def temple_after_harvest(self):
        y, K = self.year, self.K
        org, grain, shop, granary = self.ac.org, self.cm.staple, self.ac.shop_grain, self.pl.estate_granary
        owe = self.x("SELECT qty FROM arrears WHERE debtor=? AND creditor=?", (org, self.ac.neighbor)).fetchone()
        if owe and owe[0] > 0:                                # 归还邻寺借粮
            back = self.consume(org, granary, grain, owe[0], 'port_out')
            self.x("UPDATE arrears SET qty=qty-? WHERE debtor=? AND creditor=?", (back, org, self.ac.neighbor))
            self.tg[(y, self.TG['repay_neighbor'])] += back
            self.ev('GRAIN_REPAID', actor=self.holder(self.T.supervisor), q=back, to=self.S.account_name[self.ac.neighbor])
        total = self.qty(org, self.pl.granary, grain) + self.qty(org, granary, grain) + self.transit(org, grain)
        excess = total - self.daily_grain() * K['reserve_days']   # 留足四百日之蓄, 余粮出售
        p = self.grain_price() * K['sell_n'] // K['sell_d']
        sell = min(excess, self.qty(org, granary, grain), max(0, self.bal(shop) - K['shop_cash_floor_guan'] * GUAN) * SHI // p)
        if sell > 0:
            self.move(org, granary, shop, self.pl.town, grain, sell)
            m = self.pay(shop, org, sell * p // SHI, '售余粮')
            self.tg[(y, self.TG['sold'])] += sell
            self.ev('GRAIN_SOLD', place=self.pl.estate, actor=self.holder(self.T.supervisor), q=sell, money=m)

    # ------------------------------------------------------------------ 香客与施主
    def pilgrim_factor(self, c):
        se = self.S.season
        f = 1.0
        if c['month'] in se.winter_months: f = se.pilgrim_winter
        if any(lo <= c['doy'] < hi for lo, hi in se.busy_windows): f = se.pilgrim_busy
        if c['shuowang']: f *= se.pilgrim_shuowang
        return f * se.festival_mult.get(c['festival'], 1)

    def phase_visitors(self):
        d, c, Pm, K, se = self.day, self.cal(self.day), self.P, self.K, self.S.season
        closed = self.closed()
        f = self.pilgrim_factor(c) * self.pilgrim_boost.get(d, 1) * (K['closed_pilgrim_mult'] if closed else 1)
        a, b = K['pilgrim_noise']
        n = int(Pm['pilgrims'] * f * (a + b * self.u('pilgrims', d)) + 0.5)
        money = self.pay(self.ac.pilgrims, self.ac.org, n * Pm['alms_each'] / self.price_factor, '香火钱')
        g = int(n * Pm['guest_rate'] + 0.5)
        if self.tier_i >= K['tier_crisis']:
            if g: self.ev('GUESTS_SUSPENDED', place=self.pl.guest, actor=self.holder(self.T.guest_master), n=g)
            g = 0
        elif g > Pm['guest_cap']:
            self.ev('GUEST_TURNED_AWAY', place=self.pl.guest, actor=self.holder(self.T.guest_master), n=g - Pm['guest_cap']); g = Pm['guest_cap']
        self.guests, self.pilgrims_today = g, n
        self.ev('ALMS', place=self.pl.main_hall, pilgrims=n, money=money, guests=g)
        if not closed:
            big = c['festival'] in se.donor_festivals
            if (big or c['shuowang']) and self.u('donor', d) < (1.0 if big else Pm['donor_prob']):
                self.pay(self.ac.pilgrims, self.ac.org, Pm['donor_gift'], '大施主布施'); self.ev('DONOR', place=self.pl.main_hall, money=Pm['donor_gift'])
            if self.u('rite', d) < Pm['rite_prob']:
                self.pay(self.ac.town, self.ac.org, Pm['rite_fee'], '法事')
                self.ev('RITE', place=self.pl.fatang, actor=self.holder(self.T.disciplinarian), money=Pm['rite_fee'])

    # ------------------------------------------------------------------ 消耗
    def daily_use(self, c, key):
        """品类 key 当日的寺院用量（日用量 + 冬季加量 + 香客加量，再按朔望节日乘）。"""
        g = self.G[key]
        n = g.use + (g.use_winter_extra if c['month'] in self.S.season.winter_months else 0)
        if g.use_per_pilgrims:
            n += self.pilgrims_today // g.use_per_pilgrims
        if g.use_festival_mult != 1 and (c['shuowang'] or c['festival']):
            n *= g.use_festival_mult
        return n

    def phase_consumption(self):
        d, c, Pm, K, se = self.day, self.cal(self.day), self.P, self.K, self.S.season
        org, grain, store = self.ac.org, self.cm.staple, self.pl.store
        head = self.head()
        cook = self.holder(self.T.cook)
        need = int((head + self.guests) * Pm['ration_monk'] * K['tier_mult'][self.tier_i])
        got = self.consume(org, self.pl.granary, grain, need, 'consume') if cook else 0
        self.tg[(self.year, self.TG['meals'])] += got
        self.ev('MEALS', place=self.pl.refectory, actor=cook, slot=K['meal_slot'], head=head, guests=self.guests, grain=got, tier=self.tier)
        if got < need:
            self.cnt['meal_short'] += 1
            self.ev('MEAL_SHORT', place=self.pl.refectory, actor=cook, need=need, got=got, why='无人主厨' if not cook else '粮尽')
        for cc in self.S.consume_order:
            n = self.daily_use(c, cc)
            if cc == self.cm.fuel and self.qty(org, store, cc) < n and self.closed():
                self.produce(org, store, cc, K['forage_q'], 'produce')      # 封路又缺柴: 普请打柴
                self.ev('FORAGE', place=self.pl.grounds, actor=self.holder(self.T.grounds_keeper), c=cc, q=K['forage_q'])
            g = self.consume(org, store, cc, n, 'consume')
            if g < n:
                self.cnt['short_' + cc] += 1
                if self.cnt['streak_' + cc] == 0:
                    blk = self.x("SELECT 1 FROM work_order WHERE buyer=? AND commodity=? AND state='受阻'", (org, cc)).fetchone()
                    self.ev('SHORTAGE', place=store, actor=self.holder(self.T.stock_keeper), cause=self.block_c.get(cc) if blk else None, c=cc)
                self.cnt['streak_' + cc] += 1
            else:
                self.cnt['streak_' + cc] = 0
        fresh = self.cm.fresh
        self.consume(org, store, fresh, self.qty(org, store, fresh) - self.G[fresh].spoil_cap, 'spoil')   # 鲜菜存不过三日
        cloth = self.cm.textile
        if self.cloth_due > 0 and not any(lo <= c['doy'] < hi for lo, hi in se.cloth_hold_windows):
            g = self.consume(org, store, cloth, self.cloth_due, 'consume')
            if g:
                self.cloth_due -= g
                self.ev('CLOTH_ISSUED', place=store, actor=self.holder(self.T.stock_keeper), q=g, owed=self.cloth_due)
        if self.tier_i >= K['tier_famine']:
            for pid, in self.x("SELECT id FROM person WHERE status='在寺' AND canon=0 ORDER BY id").fetchall():
                if self.u('leave', pid, d) < K['leave_prob']:
                    self.x("UPDATE person SET status='游方' WHERE id=?", (pid,)); self.cnt['monks_left'] += 1
                    if self.engine: self.engine.on_person_removed(pid, '游方')
        # 农户: 够吃的批量结算, 不够的逐户处理
        ok = f"h.status='在' AND s.commodity='{grain}' AND s.owner=h.id AND s.place=h.place"
        tot = self.x(f"SELECT COALESCE(SUM(h.need),0) FROM household h, stock s WHERE {ok} AND s.qty>=h.need").fetchone()[0]
        short = self.x(f"SELECT h.id,h.kind,h.place,h.need,s.qty,h.hunger FROM household h, stock s WHERE {ok} AND s.qty<h.need ORDER BY h.id").fetchall()
        self.x("UPDATE stock SET qty=qty-(SELECT need FROM household h WHERE h.id=stock.owner) WHERE commodity=? AND EXISTS "
               "(SELECT 1 FROM household h WHERE h.id=stock.owner AND h.place=stock.place AND h.status='在' AND stock.qty>=h.need)", (grain,))
        self.net[grain] -= tot; self.flows[(self.year, grain, 'consume_hh')] += tot
        shop, town, granary = self.ac.shop_grain, self.pl.town, self.pl.estate_granary
        for hid, kind, place, need, have, hunger in short:
            p = self.price(grain)
            buy = min(need * K['hh_buy_days'] - have, self.qty(shop, town, grain), self.bal(hid) * SHI // p)
            if buy > 0:
                self.move(shop, town, hid, place, grain, buy); self.pay(hid, shop, buy * p // SHI, '买粮')
            have = self.qty(hid, place, grain)
            if have < need and kind == self.hk.tenant:                # 佃户向庄仓无息借粮, 记欠粮, 下季归还
                owe = self.x("SELECT COALESCE(SUM(qty),0) FROM arrears WHERE debtor=?", (hid,)).fetchone()[0]
                lend = self.move(org, granary, hid, place, grain, min(need * K['hh_buy_days'] - have, K['hh_borrow_cap_shi'] * SHI - owe))
                if lend > 0:
                    self.x("INSERT INTO arrears VALUES(?,?,?) ON CONFLICT(debtor,creditor) DO UPDATE SET qty=qty+excluded.qty", (hid, org, lend))
                    self.tg[(self.year, self.TG['lend_tenant'])] += lend; self.cnt['hh_borrow'] += 1
                    self.ev('HH_BORROW', place=self.pl.estate, actor=self.holder(self.T.manor_head), hh=hid, q=lend)
                have = self.qty(hid, place, grain)
            if have >= need:
                self.consume(hid, place, grain, need, 'consume_hh'); self.x('UPDATE household SET hunger=0 WHERE id=?', (hid,))
            else:
                if hunger >= K['hunger_relief'] and self.tier_i == 0:            # 断粮三日: 寺院赈济十日口粮
                    g = self.move(org, self.pl.granary, hid, place, grain, need * K['relief_days'])
                    self.tg[(self.year, self.TG['relief'])] += g; self.cnt['relief'] += 1
                    self.ev('RELIEF', place=place, actor=self.holder(self.T.guest_master), hh=hid, q=g)
                    have = self.qty(hid, place, grain)
                self.consume(hid, place, grain, min(have, need), 'consume_hh'); self.cnt['hunger_days'] += have < need
                if have >= need: self.x('UPDATE household SET hunger=0 WHERE id=?', (hid,))
                elif hunger + 1 > K['hunger_leave']:
                    self.x("UPDATE household SET status='离乡' WHERE id=?", (hid,)); self.cnt['hh_left'] += 1
                    self.ev('HH_LEFT', place=place, hh=hid)
                else:
                    self.x('UPDATE household SET hunger=hunger+1 WHERE id=?', (hid,))
