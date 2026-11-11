"""报告：年度钱粮报表、运行摘要、基准运行（原型 main() 的输出口径，tools/shaolin_regress.py 用它复现日志）。"""
from ..core.calendar import YEAR
from .vocab import SHI, GUAN
from .world import World


def year_report(w, y):
    days = [s for s in w.series if s['year'] == y]
    d0, d1 = y * YEAR, y * YEAR + YEAR - 1
    org = w.ac.org
    money = dict(w.x("SELECT reason, SUM(CASE WHEN payee=? THEN amount ELSE -amount END) FROM ledger "
                     "WHERE (payer=? OR payee=?) AND day BETWEEN ? AND ? AND reason<>? GROUP BY reason", (org, org, org, d0, d1, w.R['opening'])).fetchall())
    orders = dict(w.x('SELECT state, COUNT(*) FROM work_order WHERE created BETWEEN ? AND ? GROUP BY state', (d0, d1)).fetchall())
    ontime = w.x("SELECT COUNT(*) FROM work_order WHERE created BETWEEN ? AND ? AND state='完成' AND closed<=deadline", (d0, d1)).fetchone()[0]
    closed_n = sum(v for k, v in orders.items() if k in ('完成', '失败', '过期'))
    tiers = w.K['tiers']
    return dict(
        year=y, cash_start=days[0]['cash'] / GUAN, cash_end=days[-1]['cash'] / GUAN,
        cover_min=round(min(s['cover'] for s in days), 1), total_min=round(min(s['total'] for s in days), 1),
        tier_days={t: sum(1 for s in days if s['tier'] == t) for t in tiers if any(s['tier'] == t for s in days)},
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
    G, lab, tn = w.G, w.S.labels, w.S.hh_label[w.hk.tenant]
    for y in range(1, w.year):
        r = year_report(w, y)
        print(f"第{y}年: 余钱 {r['cash_start']:.0f}->{r['cash_end']:.0f} 贯 | 收 {r['income']} 支 {r['spend']} | {lab['temple_store']}最低 {r['cover_min']} 日, 总量最低 {r['total_min']} 日 "
              f"| 档位日数 {r['tier_days']} | 封路 {r['closed_days']} 日 | 订单 {r['orders']} 按期 {r['ontime_rate']} | 事件 {r['events']} | 僧 {r['head_end']}")
    c = w.cnt
    print(f"累计: 断炊日 {c['meal_short']} | 缺货日 " + ' '.join(f"{G[k].name}{c['short_' + k]}" for k in G if c['short_' + k]) +
          f" | 上报 {c['escalated']} | {tn}借粮 {c['hh_borrow']} 次 赈济 {c['relief']} 次 | 农户挨饿 {c['hunger_days']} 户日 | 离乡 {c['hh_left']} 户 | 僧人圆寂 {c['deaths']} 离寺 {c['monks_left']}")
    hh = w.x(f"SELECT h.kind, COUNT(*), AVG(a.balance), AVG(s.qty), AVG(h.members) FROM household h JOIN account a ON a.id=h.id JOIN stock s ON s.owner=h.id "
             f"AND s.commodity='{w.cm.staple}' WHERE h.status='在' GROUP BY h.kind").fetchall()
    print('农户期末: ' + ' | '.join(f'{k} {n}户 均钱{c_ / GUAN:.1f}贯 均粮{g / SHI:.1f}石' for k, n, c_, g, m in hh))
    ids = [a.code for a in w.S.accounts if (a.boundary or a.shop) and not a.virtual]
    b = dict(w.x(f"SELECT id, balance FROM account WHERE id IN ({','.join('?' * len(ids))}) ORDER BY rowid", ids).fetchall())
    print(f"边界与{lab['shop']}余额(贯): " + ' '.join(f'{k}={v / GUAN:.0f}' for k, v in b.items()))


def baseline(years=3, params=None, setup=None, **kw):
    """预热 1 年 + years 年；setup(w) 在跑之前登记扰动（hooks 等）。"""
    w = World(params, **kw)
    if setup: setup(w)
    return w.run(YEAR * (1 + years))


def window(w, d0, d1, types=None):
    """某日期窗口内的事件类型计数。"""
    rows = w.x('SELECT type, COUNT(*) FROM event_log WHERE day BETWEEN ? AND ? GROUP BY type', (d0, d1)).fetchall()
    return {k: v for k, v in rows if types is None or k in types}
