"""世界日报与因果追溯：事件类型是大写英文代码，中文由 chronicle() 渲染；why() 沿 cause 回溯。

渲染里的专有词（场所名、岗位名、账户名、品类名与单位）一律从 Spec 取，不写死。
"""
import json

from ..core.calendar import SLOTS
from .vocab import SHI, GUAN


class ChronicleMixin:
    def shi(self, q): return f'{q / SHI:.1f} 石'
    def guan(self, m): return f'{m / GUAN:.1f} 贯'

    def chronicle(self, day, scope='temple'):
        c = self.cal(day)
        S, T, K = self.S, self.S.T, self.K
        shi, guan = self.shi, self.guan
        out = [f"【{self.cal_str(day)} · {c['term']}" + (f" · {c['festival']}" if c['festival'] else ' · 朔望' if c['shuowang'] else '') + '】']
        G = lambda k: self.G[k].name
        U = lambda k, q: shi(q) if k == self.cm.staple else f'{q} {self.G[k].unit}'
        pn = S.place_name
        road, granary, fatang, gate = pn[self.pl.road], pn[self.pl.estate_granary], pn[self.pl.fatang], pn[self.pl.gate]
        lab, tn = S.labels, S.hh_label[self.hk.tenant]
        state = S.account_name[self.ac.state]
        for typ, place, actor, payload, slot in self.x('SELECT type,place,actor,payload,slot FROM event_log WHERE day=? ORDER BY id', (day,)).fetchall():
            p, a, pl = json.loads(payload), self.pname(actor), pn.get(place, place or '')
            if scope == 'temple' and (place in (self.pl.town, self.pl.port) or p.get('kind') == 'IMPORT'): continue
            if typ == 'ROAD_CLOSED': s = f"{p['reason']}，{road}不通，预计 {p['days']} 日。"
            elif typ == 'ROAD_OPEN': s = f'{road}复通。'
            elif typ == 'HARVEST': s = (f"{pn[self.pl.estate]}{p['crop']}收，年景 {p['yf']}。{tn}共收 {shi(p['gross'])}，{T.manor_head}{a}收租 {shi(p['rent'])} 入{granary}，"
                                        f"纳两税 {shi(p['tax_temple'])}。" + (f'年成大坏，寺院减租、{state}蠲免。' if p.get('remission') else ''))
            elif typ == 'MARKET_SALES': s = f"{lab['grain_market']}：{p['n']} 户农家卖出余粮 {shi(p['qty'])}，每石 {p['price']} 文。"
            elif typ == 'GRAIN_SOLD': s = f"{T.supervisor}{a}售{granary}余粮 {shi(p['q'])}，得钱 {guan(p['money'])}。"
            elif typ == 'ALMS': s = f"香客 {p['pilgrims']} 人，香火钱 {guan(p['money'])}" + (f"，留宿 {p['guests']} 人。" if p['guests'] else '。')
            elif typ == 'DONOR': s = f"有大施主布施 {guan(p['money'])}。"
            elif typ == 'RITE': s = f"{T.disciplinarian}{a}在{fatang}主持法事一场，收 {guan(p['money'])}。"
            elif typ == 'GUEST_TURNED_AWAY': s = f"客房已满，{T.guest_master}{a}婉拒 {p['n']} 人留宿。"
            elif typ == 'GUESTS_SUSPENDED': s = f"粮食{K['tiers'][K['tier_crisis']]}，{T.guest_master}{a}暂停挂单，{p['n']} 人未能留宿。"
            elif typ == 'TIER_CHANGE': s = f"{T.stock_keeper}{a}报：{lab['temple_store']}存粮可支 {p['cover']} 日，由“{p['frm']}”转“{p['to']}”。"
            elif typ == 'ORDER_OPEN':
                k = {'TRANSFER': f'从{granary}调', 'PURCHASE': '采买', 'IMPORT': '向外地进', 'REPAIR': '修缮用', 'ALMS': '外出募化',
                     'BORROW': f"向{S.account_name[self.ac.neighbor]}借"}[p['kind']]
                s = f"{a or lab['shop']}开单：{k}" + (f"{G(p['c'])} {U(p['c'], p['q'])}。" if p['kind'] != 'ALMS' else '。')
            elif typ == 'ORDER_RENEWED': s = f"{T.supervisor}续单（承前单 {p['parent']}）：{G(p['c'])} {U(p['c'], p['q'])}。"
            elif typ == 'ORDER_APPROVED': s = f"{T.supervisor}{a}批准采买{G(p['c'])} {U(p['c'], p['q'])}，计 {guan(p['cost'])}。"
            elif typ == 'ORDER_REDUCED': s = f"钱不凑手，{T.supervisor}{a}将采买数量由 {p['frm']} 减为 {p['to']}。"
            elif typ == 'ORDER_DEFERRED': s = f"账上钱不够，{T.supervisor}{a}暂缓采买{G(p['c'])}。"
            elif typ == 'ORDER_BLOCKED': s = f"{G(p['c'])}订单受阻：{p['why']}。"
            elif typ == 'ORDER_RESUMED': s = None
            elif typ == 'ORDER_EXPIRED': s = f"{G(p['c'])}采买单逾期未办（{p['why']}），上报{T.supervisor}。"
            elif typ == 'ORDER_FAILED': s = f"{G(p['c'])}订单" + (f"因{p['why']}" if p['why'] != '超期' else '') + f"超期，判为失败，上报{T.supervisor}。"
            elif typ == 'SHIP_OUT': s = f"{pl}发出{G(p['c'])} {U(p['c'], p['q'])}。" if p['c'] == self.cm.staple else None
            elif typ == 'SHIP_IN': s = f"{G(p['c'])} {U(p['c'], p['q'])} 运抵{pl}" + (f"，付 {guan(p['paid'])}。" if p['paid'] else '。')
            elif typ == 'GOODS_RETURNED': s = f"货款不足，{G(p['c'])} {U(p['c'], p['q'])} 退回。"
            elif typ == 'MEALS': s = (f"{T.cook}{a}供粥斋，僧 {p['head']} 人" + (f"、客 {p['guests']} 人" if p['guests'] else '') + f"，用粮 {shi(p['grain'])}"
                                      + ('。' if K['tiers'].index(p['tier']) <= K['tier_light'] else '（减供）。'))
            elif typ == 'MEAL_SHORT': s = f"断炊：{p['why']}，应供 {shi(p['need'])}，实供 {shi(p['got'])}。"
            elif typ == 'SHORTAGE': s = f"{T.stock_keeper}{a}报：{G(p['c'])}告罄。"
            elif typ == 'FORAGE': s = f"封路缺柴，{T.grounds_keeper}{a}领众普请，上山打柴 {p['q']} {self.G[self.cm.fuel].unit}。"
            elif typ == 'CLOTH_ISSUED': s = f"{T.stock_keeper}{a}发放僧衣用布 {p['q']} {self.G[self.cm.textile].unit}" + (f"，尚欠 {p['owed']} {self.G[self.cm.textile].unit}。" if p.get('owed') else '。')
            elif typ == 'DAMAGE': s = f"{p['what']}损坏。"
            elif typ == 'REPAIR_START': s = f"{T.grounds_keeper}{a}动工修{p['what']}，用料 {p['timber']} {self.G[self.cm.lumber].unit}，雇工 {p['labor']} 人日。"
            elif typ == 'REPAIR_DONE': s = f"{p['what']}修毕。"
            elif typ == 'DEATH': s = f"{a}圆寂" + (f"，所任{'、'.join(p['offices'])}出缺。" if p['offices'] else '。')
            elif typ == 'ACTING': s = f"副职{a}代理{p['office']}。"
            elif typ == 'APPOINT': s = f"{T.abbot}{a}任命{self.pname(p['person'])}为{p['office']}。"
            elif typ == 'RECRUIT': s = f"{T.abbot}{a}收录新僧 {p['n']} 人。"
            elif typ == 'CHARITY': s = f"{c['festival']}施粥，{T.cook}{a}于{gate}外散粥，用粮 {shi(p['grain'])}。"
            elif typ == 'MERIT_SPEND': s = f"岁末结余，{T.abbot}{a}拨 {guan(p['money'])} 修造功德。"
            elif typ == 'HH_BORROW': s = f"{tn} {p['hh']} 断粮，{T.manor_head}{a}自{granary}借出 {shi(p['q'])}。"
            elif typ == 'RELIEF': s = f"农户 {p['hh']} 断粮三日，{T.guest_master}{a}开库赈济 {shi(p['q'])}。"
            elif typ == 'TENANTS_SETTLED': s = f"{T.manor_head}{a}招得新佃 {p['n']} 户。"
            elif typ == 'MONKS_RETURN': s = f"游方僧 {p['n']} 人归寺。"
            elif typ == 'HH_LEFT': s = f"农户 {p['hh']} 无以为生，离乡而去。"
            elif typ == 'ALMS_ROUND_OUT': s = f"{T.almoner}{a}下山募化。"
            elif typ == 'ALMS_ROUND_BACK': s = f"{T.almoner}{a}募化归来，得粮 {shi(p['grain'])}、钱 {guan(p['money'])}。"
            elif typ == 'GRAIN_REPAID': s = f"{T.supervisor}{a}归还{p['to']}借粮 {shi(p['q'])}。"
            elif typ == 'ITEM_TAKEN': s = f"{SLOTS[slot]}时，{a}自{pl}取走{p['item']}（{p['norm']}，在场 {len(p['witnesses'])} 人）。"
            elif typ == 'REPORT': s = f"{a}向{p['to']}举报{self.pname(p['about'])}。"
            elif typ == 'CASE_OPENED': s = f"{T.discipline_head}{a}立案查问{self.pname(p['about'])}。"
            elif typ == 'AUDIT_MISSING': s = f"月朔点检，{a}发现{p['item']}不在{pl}。"
            elif typ == 'CMD_REJECTED': s = None
            else: s = None
            if s: out.append('  ' + s)
        return '\n'.join(out)

    def why(self, eid):
        chain = []
        while eid:
            day, typ, payload, cause = self.x('SELECT day,type,payload,cause FROM event_log WHERE id=?', (eid,)).fetchone()
            chain.append(f'{self.cal_str(day)} {typ} {payload}'); eid = cause
        return chain
