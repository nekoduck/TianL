"""规则与订单阶段：库头、监院、庄主、直岁、铺户各按自己的规则开单、审批、发运、结单。

phase_rules   每日各岗位按存量规则开单；监院按优先级审批采买；铺户按补货带进货。
phase_orders  把已批准的订单落成发运、修缮、募化、借粮；超期的订单过期或判失败，由监院续单。
"""
import json
import math

from .vocab import SHI, GUAN, LIVE_SQL


class RulesMixin:
    def firewood_use(self, c): return self.daily_use(c, self.cm.fuel)

    # ------------------------------------------------------------------ 各岗位的开单规则
    def phase_rules(self):
        d, c, Pm, K = self.day, self.cal(self.day), self.P, self.K
        org, grain, store, T, G = self.ac.org, self.cm.staple, self.pl.store, self.T, self.G
        daily = self.daily_grain()
        sh, est, tr = self.qty(org, self.pl.granary, grain), self.qty(org, self.pl.estate_granary, grain), self.transit(org, grain)
        cover = sh / daily
        idx = lambda cv, pad: next((i for i, th in enumerate(K['tier_cover']) if cv >= th + pad), len(K['tier_cover']))
        i, j, cur = idx(cover, 0), idx(cover, K['tier_pad']), self.tier_i
        tier_i = i if i > cur else j if j < cur else cur        # 变差立即生效; 变好要多出若干日余量, 免得在线上来回跳
        if tier_i != cur:
            worse = tier_i > cur
            tiers = K['tiers']
            self.ev('TIER_CHANGE', place=self.pl.granary, actor=self.holder(T.stock_keeper), cause=self.block_ev if worse else None,
                    frm=tiers[cur], to=tiers[tier_i], cover=round(cover, 1))
            self.tier_i = tier_i
        tier_i = self.tier_i
        # 库头: 寺库低于若干日, 先从自家庄仓调粮 (档位线之上, 正常运转不触线)
        if cover < K['transfer_below'] and est > 0:
            self.open_order('R-GRAIN-TRANSFER', 'TRANSFER', T.manor_head, grain, min(est, daily * K['transfer_to'] - sh - tr), K['transfer_sla'],
                            supplier=self.pl.estate, buyer=org)
        # 库头: 寺库加庄仓合计过低, 向粮铺市购
        if (sh + est + tr) / daily < K['buy_below']:
            self.open_order('R-GRAIN-BUY', 'PURCHASE', T.stock_keeper, grain, daily * K['buy_to'] - (sh + est + tr), K['buy_sla'],
                            supplier=self.ac.shop_grain, buyer=org)
        # 降级阶梯: 紧张以下且总量不足 -> 募化; 告急 -> 向邻寺借粮
        if tier_i >= K['tier_alms'] and (sh + est + tr) / daily < K['alms_below'] and d - self.last_alms >= K['alms_gap']:
            self.open_order('R-ALMS-ROUND', 'ALMS', T.almoner, grain, 0, K['alms_sla'], buyer=org)
        if tier_i >= K['tier_crisis']:
            self.open_order('R-BORROW', 'BORROW', T.supervisor, grain, daily * K['borrow_days'], K['borrow_sla'], supplier=self.ac.neighbor, buyer=org)
        # 库头: 杂项补货
        for cc in self.S.restock:
            use, st = G[cc].use, self.qty(org, store, cc)
            if st < use * G[cc].low:
                self.open_order('R-RESTOCK', 'PURCHASE', T.stock_keeper, cc, use * G[cc].up - st, K['restock_sla'], supplier=self.ac.shop_gen, buyer=org)
        fuel = self.cm.fuel
        fw = self.firewood_use(c); st = self.qty(org, store, fuel)
        if st < fw * G[fuel].low: self.open_order('R-RESTOCK', 'PURCHASE', T.stock_keeper, fuel, fw * G[fuel].up - st, K['restock_sla'], supplier=self.ac.village, buyer=org)
        fresh = self.cm.fresh
        st = self.qty(org, store, fresh)
        if st < K['veg_reorder']: self.open_order('R-RESTOCK', 'PURCHASE', T.cook, fresh, K['veg_upto'] - st, K['veg_sla'], supplier=self.ac.village, buyer=org)
        cloth = self.cm.textile
        if c['doy'] in self.S.season.cloth_due_doys:           # 立项: 本季应发僧衣(欠发不过两季)。只要还欠着, 规则就持续追
            self.cloth_due = min(K['cloth_due_cap'], self.cloth_due + K['cloth_due_step'])
        if self.cloth_due > self.qty(org, store, cloth):
            self.open_order('R-CLOTH', 'PURCHASE', T.stock_keeper, cloth, self.cloth_due - self.qty(org, store, cloth), K['cloth_sla'],
                            supplier=self.ac.shop_gen, buyer=org)
        timber = self.cm.lumber
        st = self.qty(org, store, timber)
        if st < K['timber_reorder']: self.open_order('R-RESTOCK', 'PURCHASE', T.grounds_keeper, timber, K['timber_upto'] - st, K['timber_sla'],
                                                     supplier=self.ac.shop_gen, buyer=org)
        # 直岁: 损坏 -> 修缮订单
        if self.u('damage', d) < K['damage_prob'] * (K['damage_month_mult'] if c['month'] in K['damage_months'] else 1):
            what = K['damage_targets'][int(self.u('damwhat', d) * len(K['damage_targets']))]
            e = self.ev('DAMAGE', place=self.pl.temple, what=what)
            self.open_order(f'R-REPAIR-{d}', 'REPAIR', T.grounds_keeper, timber, K['repair_timber'][0] + int(self.u('damt', d) * K['repair_timber'][1]),
                            K['repair_sla'], buyer=org,
                            note=json.dumps(dict(what=what, labor=K['repair_labor'][0] + int(self.u('daml', d) * K['repair_labor'][1])), ensure_ascii=False), cause=e)
        # 监院: 按优先级审批采购 (钱不够时先保粮柴)
        committed = self.x("SELECT COALESCE(SUM(cost*(qty-delivered)/qty),0) FROM work_order WHERE buyer=? AND "
                           "kind='PURCHASE' AND state IN ('已接','进行中','受阻') AND qty>0", (org,)).fetchone()[0]
        avail = self.bal(org) - int(committed)
        rows = self.x("SELECT id, commodity, qty, note FROM work_order WHERE buyer=? AND kind='PURCHASE' AND state='待接'", (org,)).fetchall()
        for oid, cc, q, note in sorted(rows, key=lambda r: (G[r[1]].prio, r[0])):
            cost = self.cost(cc, q)
            room = avail - (K['reserve_guan'] * GUAN if G[cc].prio >= K['prio_reserve_from'] else 0)   # 布与木石料不是急用: 批它们之前先留压库钱
            if cost > room:
                afford = int(max(0, room) * q // cost) if cost else q
                if afford >= max(1, q // K['afford_min_div']):
                    self.ev('ORDER_REDUCED', actor=self.holder(T.supervisor), order=oid, frm=q, to=afford, why='钱不够')
                    q, cost = afford, self.cost(cc, afford)
                else:
                    if note != '缺钱':
                        self.x("UPDATE work_order SET note='缺钱' WHERE id=?", (oid,))
                        self.ev('ORDER_DEFERRED', actor=self.holder(T.supervisor), order=oid, c=cc, why='缺钱')
                    continue
            avail -= cost
            self.set_state(oid, '已接', cost=cost, qty=q)
            self.ev('ORDER_APPROVED', actor=self.holder(T.supervisor), order=oid, c=cc, q=q, cost=cost)
        # 铺户: 自己的补货规则
        gen, town, port = self.ac.shop_gen, self.pl.town, self.ac.port
        office_gen = next(a.office for a in self.S.accounts if a.code == gen)
        for cc, (lo, hi) in self.S.bands.items():
            st = self.qty(gen, town, cc) + self.transit(gen, cc)
            if st < lo: self.open_order('R-IMPORT', 'IMPORT', office_gen, cc, hi - st, K['import_sla'], supplier=port, buyer=gen)
        shop = self.ac.shop_grain
        office_grain = next(a.office for a in self.S.accounts if a.code == shop)
        gs = self.qty(shop, town, grain)
        if gs + self.transit(shop, grain) < K['shop_grain_low_shi'] * SHI:
            self.open_order('R-IMPORT', 'IMPORT', office_grain, grain, K['shop_grain_target_shi'] * SHI - gs, K['import_sla'], supplier=port, buyer=shop)
        elif gs > K['shop_grain_high_shi'] * SHI:
            q = self.consume(shop, town, grain, gs - K['shop_grain_target_shi'] * SHI, 'port_out')
            self.pay(port, shop, q * (self.grain_price() * K['export_pct'] // 100) // SHI, self.R['export'])

    # ------------------------------------------------------------------ 订单落地
    def phase_orders(self):
        d, closed, Pm, K = self.day, self.closed(), self.P, self.K
        org, grain, store, T, G = self.ac.org, self.cm.staple, self.pl.store, self.T, self.G
        fuel, fresh = self.cm.fuel, self.cm.fresh
        vil_cap = {fuel: self.x("SELECT COUNT(*) FROM household WHERE kind=? AND status='在'", (self.hk.wood,)).fetchone()[0] * K['wood_cap_n'] // K['wood_cap_d'],
                   fresh: K['veg_cap']}
        rows = self.x(f"SELECT id,kind,commodity,qty,shipped,delivered,state,supplier,buyer,due,note,cost,office FROM work_order "
                      f"WHERE state IN {LIVE_SQL} ORDER BY id").fetchall()
        for oid, kind, c, q, shipped, delivered, st, sup, buyer, due, note, cost, office in rows:
            rem = q - shipped
            if kind == 'TRANSFER':
                if rem <= 0: continue
                if closed: self.block(oid, '封路'); continue
                lot = min(rem, Pm['convoy'], self.qty(org, self.pl.estate_granary, grain))
                if lot <= 0:                                  # 庄仓已空: 按已发数量结单
                    self.x('UPDATE work_order SET qty=shipped WHERE id=?', (oid,)); self.finish_if_done(oid); continue
                if st == '受阻': self.ev('ORDER_RESUMED', order=oid)
                self.set_state(oid, '进行中', block=None)
                self.ship(oid, grain, lot, (org, self.pl.estate_granary), (org, self.pl.granary), K['convoy_days'], True)
                self.tg[(self.year, self.TG['transfer'])] += lot
            elif kind == 'PURCHASE' and st != '待接':
                if rem <= 0: continue
                if closed: self.block(oid, '封路'); continue
                if sup == self.ac.village:
                    lot = min(rem, vil_cap[c]); vil_cap[c] -= lot; origin, src = 'made', (self.ac.village, self.pl.village)
                else:
                    lot = min(rem, self.qty(sup, self.pl.town, c)); origin, src = 'stock', (sup, self.pl.town)
                if lot <= 0: self.block(oid, '缺货'); continue
                if st == '受阻': self.ev('ORDER_RESUMED', order=oid)
                self.set_state(oid, '进行中', block=None)
                self.ship(oid, c, lot, src, (buyer, self.pl.granary if c == grain else store), K['purchase_days'], True,
                          pay=(buyer, sup, cost * lot // q), origin=origin)
            elif kind == 'IMPORT' and st == '待接':
                unit = (self.grain_price() * K['import_markup_pct'] // 100) / SHI if c == grain else G[c].price * K['import_discount']
                q2 = min(q, int(max(0, self.bal(buyer) - K['import_floor_guan'] * GUAN) / unit))
                if q2 <= 0: continue
                self.set_state(oid, '进行中', qty=q2, cost=int(q2 * unit))
                self.ship(oid, c, q2, (self.ac.port, self.pl.port), (buyer, self.pl.town), K['import_days'], False,
                          pay=(buyer, self.ac.port, int(q2 * unit)), origin='port')
            elif kind == 'REPAIR':
                info = json.loads(note)
                if st == '进行中':
                    if d >= due: self.done(oid); self.ev('REPAIR_DONE', place=self.pl.temple, actor=self.holder(T.grounds_keeper), what=info['what'])
                elif self.qty(org, store, self.cm.lumber) >= q:
                    self.consume(org, store, self.cm.lumber, q, 'consume')
                    hh = [r[0] for r in self.x("SELECT id FROM household WHERE kind=? AND status='在' ORDER BY id", (self.hk.wood,))]
                    if hh: self.pay(org, hh[oid % len(hh)], info['labor'] * Pm['wage'], self.R['repair_wage'])
                    self.set_state(oid, '进行中', block=None, due=d + math.ceil(info['labor'] / K['labor_per_day']))
                    self.ev('REPAIR_START', place=self.pl.temple, actor=self.holder(T.grounds_keeper), what=info['what'], timber=q, labor=info['labor'])
                else:
                    self.block(oid, '缺料')
            elif kind == 'ALMS':
                if st in ('待接', '受阻'):
                    if closed: self.block(oid, '封路'); continue
                    self.set_state(oid, '进行中', block=None, due=d + K['alms_days'])
                    self.ev('ALMS_ROUND_OUT', place=self.pl.gate, actor=self.holder(T.almoner), order=oid)
                elif d >= due and not closed:
                    k = 1 / self.price_factor ** 2
                    ag, am = K['alms_grain'], K['alms_money']
                    g = self.produce(org, self.pl.granary, grain, (ag[0] + ag[1] * self.u('almsg', oid)) * SHI * k, 'port_in')
                    m = self.pay(self.ac.pilgrims, org, (am[0] + am[1] * self.u('almsm', oid)) * GUAN * k, self.R['alms'])
                    self.last_alms = d
                    self.tg[(self.year, self.TG['alms'])] += g
                    self.done(oid); self.ev('ALMS_ROUND_BACK', place=self.pl.gate, actor=self.holder(T.almoner), grain=g, money=m)
            elif kind == 'BORROW' and st == '待接':
                self.set_state(oid, '进行中')
                self.ship(oid, grain, q, (self.ac.neighbor, self.pl.port), (org, self.pl.granary), K['borrow_ship_days'], True, origin='port')
                self.x("INSERT INTO arrears VALUES(?,?,?) ON CONFLICT(debtor,creditor) DO UPDATE SET qty=qty+excluded.qty", (org, self.ac.neighbor, q))
                self.tg[(self.year, self.TG['borrow_neighbor'])] += q
        # 超时: 待接超期 -> 过期; 其余超期加宽限 -> 失败。两者都上报, 失败的订单由上级续单并继承在途货物。
        rows = self.x(f"SELECT id,rule,kind,office,commodity,qty,shipped,delivered,cost,state,sla,deadline,supplier,buyer,note,block "
                      f"FROM work_order WHERE state IN {LIVE_SQL} AND deadline<? ORDER BY id", (d,)).fetchall()
        for oid, rule, kind, office, c, q, shipped, delivered, cost, st, sla, deadline, sup, buyer, note, blk in rows:
            if st == '待接':
                self.set_state(oid, '过期', closed=d)
                e = self.ev('ORDER_EXPIRED', order=oid, c=c, why=note or '无人承接')
                self.ev('ORDER_ESCALATED', actor=self.holder(T.supervisor), cause=e, order=oid); self.cnt['escalated'] += 1
            elif d > deadline + K['grace_days']:
                self.set_state(oid, '失败', closed=d)
                e = self.ev('ORDER_FAILED', order=oid, c=c, why=blk or '超期')
                self.ev('ORDER_ESCALATED', actor=self.holder(T.supervisor), cause=e, order=oid); self.cnt['escalated'] += 1
                rem = q - delivered if kind != 'REPAIR' else q
                if rem > 0 and kind in ('TRANSFER', 'PURCHASE', 'REPAIR', 'IMPORT'):
                    new = self.open_order(rule, kind, office, c, rem, min(K['renew_cap'], sla * K['renew_mult']), supplier=sup, buyer=buyer, note=note, cause=e, parent=oid,
                                          state='受阻' if blk else '已接', shipped=(shipped - delivered) if kind != 'REPAIR' else 0,
                                          cost=cost * rem // q if q else 0, block=blk)
                    self.x("UPDATE shipment SET order_id=? WHERE order_id=? AND state IN ('在途','滞留')", (new, oid))
