#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用新内核（tianl.kernel + defs/）复现 reference/shaolin_spike.py 的 main() / --all 输出，便于与
reference/logs/shaolin_run_log.txt 逐行比对。

  python3 tools/shaolin_regress.py            # 基准: 预热 1 年 + 运行 3 年
  python3 tools/shaolin_regress.py --all      # 基准 + 全部扰动实验 E1–E6 + 十年基准 + 六个种子 + 人物与独有物测试
  python3 tools/shaolin_regress.py --all | diff <(sed -E 's/用时 [0-9.]+ 秒/用时 X 秒/' -) <(sed -E 's/用时 [0-9.]+ 秒/用时 X 秒/' reference/logs/shaolin_run_log.txt)

除“用时 N 秒”一行的耗时外，输出必须与日志逐字节相同。少林寺专有的编号与名字一律从 defs 取（w.S / w.T / w.ac / w.pl），不写死。
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tianl.core.calendar import SLOTS, YEAR                      # noqa: E402
from tianl.kernel import GUAN, baseline, load_spec, summary, year_report   # noqa: E402
from tianl.kernel.report import window                          # noqa: E402


Y2 = 2 * YEAR


def e1():
    """E1 封路 45 日（第2年腊月初一起）。"""
    start = Y2 + 330
    w = baseline(3, setup=lambda w: w.hooks[start].append(lambda w: w.close_road(45, '扰动:封路')))
    summary(w, 'E1 封路 45 日 (第2年腊月初一起)')
    win = [s for s in w.series if start <= s['day'] <= start + 70]
    reopen = start + 45
    rec = next((s['day'] - reopen for s in win if s['day'] >= reopen and s['blocked'] == 0 and s['short'] == 0), None)
    first_short = next((s['day'] - start for s in win if s['short'] > 0), None)
    print(f"  窗口内: {w.S.labels['temple_store']}最低 {min(s['cover'] for s in win):.1f} 日 | 首次缺货在封路第 {first_short} 日 | 同时受阻订单最多 {max(s['blocked'] for s in win)} 张 "
          f"| 复通后 {rec} 日内全部补齐 | 事件 {window(w, start, start + 60, ('ORDER_BLOCKED', 'ORDER_FAILED', 'ORDER_RENEWED', 'ORDER_ESCALATED', 'SHORTAGE', 'FORAGE', 'MEAL_SHORT'))}")
    e = w.x("SELECT id FROM event_log WHERE type='SHORTAGE' AND day>=? AND cause IS NOT NULL ORDER BY id LIMIT 1", (start,)).fetchone()
    if e: print('  因果追溯:', *w.why(e[0]), sep='\n     <- ')
    for d in (start, start + 22, reopen, reopen + 2): print(w.chronicle(d))
    return w


def e2():
    """E2 歉收：第2年亩产 x0.75。"""
    crops = [nm for _, nm in load_spec().season.crops]
    w = baseline(3, setup=lambda w: w.yield_override.update({(2, nm): 0.75 for nm in crops})); summary(w, 'E2 歉收 (第2年亩产 x0.75)')
    return w


def e2b():
    """E2b 大荒：第2年亩产 x0.5，连看 7 年。"""
    crops = [nm for _, nm in load_spec().season.crops]
    w = baseline(7, setup=lambda w: w.yield_override.update({(2, nm): 0.5 for nm in crops})); summary(w, 'E2b 大荒 (第2年亩产 x0.5), 连看 7 年')
    best, tn, ts = w.K['tiers'][0], w.S.hh_label[w.hk.tenant], w.S.labels['temple_store']
    for y in range(1, 8):
        ds = [s for s in w.series if s['year'] == y]
        print(f"  第{y}年: {tn} {ds[-1]['tenants']} 户 | 僧 {min(s['head'] for s in ds)}-{ds[-1]['head']} | 余钱 {ds[-1]['cash'] / GUAN:.0f} 贯 | {ts}最低 {min(s['cover'] for s in ds):.0f} 日 "
              f"| 非{best} {sum(1 for s in ds if s['tier'] != best)} 日 | {window(w, y * YEAR, y * YEAR + 359, ('ALMS_ROUND_BACK', 'HH_LEFT', 'RELIEF', 'HH_BORROW', 'TENANTS_SETTLED', 'MONKS_RETURN', 'ORDER_EXPIRED', 'MEAL_SHORT'))}")
    print(w.chronicle(Y2 + 125)); print(w.chronicle(3 * YEAR + 60))
    return w


def e3():
    """E3 典座离任（第2年四月十一）。"""
    def setup(w): w.hooks[Y2 + 100].append(lambda w: w.die(w._appointee(w.T.cook), w.day - 1))
    w = baseline(3, setup=setup); summary(w, f'E3 {w.T.cook}离任 (第2年四月十一)')
    print('  ', window(w, Y2 + 100, Y2 + 104, ('DEATH', 'ACTING', 'APPOINT', 'MEAL_SHORT')))
    for d in (Y2 + 100, Y2 + 101): print(w.chronicle(d))
    return w


def e5():
    """E5 佛诞香客 x10（第2年）。"""
    w = baseline(3, setup=lambda w: w.pilgrim_boost.update({Y2 + 97: 10})); summary(w, f"E5 {w.S.cal.festivals[(4, 8)]}香客 x10 (第2年)")
    print(w.chronicle(Y2 + 97))
    return w


def e6():
    """E6 余钱清零（第2年七月廿一）。"""
    w = baseline(3, setup=lambda w: w.hooks[Y2 + 200].append(lambda w: w.pay(w.ac.org, w.ac.equity, w.bal(w.ac.org), '扰动:余钱清零')))
    summary(w, 'E6 余钱清零 (第2年七月廿一)')
    print('  此后 160 日:', window(w, Y2 + 200, Y2 + 359, ('ORDER_REDUCED', 'ORDER_DEFERRED', 'ORDER_EXPIRED', 'ORDER_ESCALATED', 'SHORTAGE', 'CLOTH_ISSUED', 'MERIT_SPEND', 'MEAL_SHORT')))
    print('  余钱(每 30 日):', [round(s['cash'] / GUAN) for s in w.series if s['day'] in range(Y2 + 195, 4 * YEAR, 30)])
    for d in (Y2 + 235, Y2 + 256): print(w.chronicle(d))
    return w


def experiments():
    for f in (e1, e2, e2b, e3, e5, e6): f()


def ten_year():
    w = baseline(10); summary(w, '十年基准')
    print('  年末余钱(贯):', [round([s for s in w.series if s['year'] == y][-1]['cash'] / GUAN) for y in range(1, 11)])
    print(f"  年内{w.S.labels['temple_store']}最低(日):", [round(min(s['cover'] for s in w.series if s['year'] == y)) for y in range(1, 11)])
    print('  年末僧数:', [[s for s in w.series if s['year'] == y][-1]['head'] for y in range(1, 11)], f'| {w.S.hh_label[w.hk.tenant]}:', [[s for s in w.series if s['year'] == y][-1]['tenants'] for y in range(1, 11)])
    print('  事件总数:', w.x('SELECT COUNT(*) FROM event_log').fetchone()[0], '| 排班行:', w.x('SELECT COUNT(*) FROM roster').fetchone()[0],
          '| 账目行:', w.x('SELECT COUNT(*) FROM ledger').fetchone()[0])
    return w


def seeds():
    print('\n===== 换 6 个种子各跑 3 年 =====')
    for seed in load_spec().scenario['seeds']:
        w = baseline(3, params=dict(seed=seed)); ds = [s for s in w.series if s['year'] >= 1]
        c, best = w.cnt, w.K['tiers'][0]
        ye = [round([s for s in ds if s['year'] == y][-1]['cash'] / GUAN) for y in (1, 2, 3)]
        ot = [year_report(w, y)['ontime_rate'] for y in (1, 2, 3)]
        print(f"  seed={seed:<9} 违规 {len(w.viol)} | 余钱 {min(s['cash'] for s in ds) / GUAN:.0f}-{max(s['cash'] for s in ds) / GUAN:.0f} 贯 (年末 {ye}) | 按期率 {ot} | {w.S.labels['temple_store']}最低 {min(s['cover'] for s in ds):.0f} 日 "
              f"| 非{best} {sum(1 for s in ds if s['tier'] != best)} 日 | 封路 {sum(1 for s in ds if s['closed'])} 日 | 断炊 {c['meal_short']} | 挨饿 {c['hunger_days']} 户日 | 离乡 {c['hh_left']} "
              f"| 缺货日 " + ' '.join(f"{w.G[k].name}{c['short_' + k]}" for k in w.G if c['short_' + k]))


def people_tests(w):
    """M2/M4 子集: 作息函数、值守排班、历史不可改写、物理/规范两层约束。"""
    print('\n===== 人物与独有物测试 =====')
    sc, pn, S = w.S.scenario, w.S.place_name, w.S
    code = S.code
    monks = [r[0] for r in w.x("SELECT id FROM person WHERE org=? ORDER BY id", (w.ac.org,))]
    d0 = sc['probe_day']['year'] * YEAR + sc['probe_day']['doy']                  # 第1年四月初八 佛诞
    use, missing = {}, 0
    snap = {}
    for pid in monks:
        for s in range(12):
            r = w.where(pid, d0, s)
            if r is None:
                if w.alive_at(w.person(pid), d0): missing += 1
                continue
            use[r[1]] = use.get(r[1], 0) + 1; snap[(pid, s)] = r
    tot = sum(use.values())
    print(f'{w.S.cal.festivals[(4, 8)]}日全寺时间分配: ' + ' '.join(f'{k}{v / tot:.0%}' for k, v in sorted(use.items(), key=lambda kv: -kv[1])))
    print(f'在世而查不到位置的人次: {missing}')
    dup = w.x('SELECT COUNT(*) FROM (SELECT day,slot,person FROM roster GROUP BY 1,2,3 HAVING COUNT(*)>1)').fetchone()[0]
    print(f'同一时辰被排两处值守的人次: {dup}')
    for pr in sc['probes']:
        place, slot = code(pr['place']), pr['slot']
        ps = w.present(place, d0, slot)
        print(f"  {w.cal_str(d0)} {SLOTS[slot]}时 {pn[place]}: {len(ps)} 人" + (f"（{'、'.join(w.pname(p) for p in ps[:4])}）" if 0 < len(ps) <= 4 else ''))
    who = sc['canon_probe']
    xz = w.x("SELECT id FROM person WHERE name=?", (who,)).fetchone()[0]
    print(f'  {who}一日: ' + ' '.join(f"{SLOTS[s]}{pn.get(w.where(xz, d0, s)[0], S.labels['dorm'])}·{w.where(xz, d0, s)[1]}" for s in range(12)))
    m = w.x("SELECT p2.name FROM person p JOIN person p2 ON p2.id=p.master WHERE p.name=?", (who,)).fetchone()[0]
    print(f'  {who}的师父: {m}')
    # 历史不可改写: 世界又过了两年多(有人圆寂、岗位更替), 重问第1年佛诞日的位置, 必须与当时一致
    changed = sum(1 for (pid, s), r in snap.items() if w.where(pid, d0, s) != r)
    print(f'隔两年重问当日位置, 答案变了的人次: {changed} / {len(snap)}')

    # 三种取物: 物理拒绝 / 违规无人见 -> 月朔点检发现 / 违规被见 -> 当场举报
    v = sc['visitor']
    w.x('BEGIN')
    thief = w._mk(S.org.visitor_gen, v['name'], v['age'], v['hall'], joined=w.day); w.x("UPDATE person SET kind='临时', org=? WHERE id=?", (v['org'], thief))
    w.x('COMMIT'); w.run(2); w.x('BEGIN')
    d = w.day
    lp = sc['lock_probe']
    ok = w.cmd_move(thief, code(lp['place']), d, lp['slot'])
    print(f'  {SLOTS[lp["slot"]]}时潜入{pn[code(lp["place"])]}: {"放行" if ok else "物理层拒绝（夜间上锁，无钥匙）"}')
    evs = []
    for tk in sc['takes']:
        it = next(i for i in S.items if i.code == code(tk['item']))
        place = code(tk['place'])
        w.cmd_move(thief, place, d, tk['slot'])
        e = w.cmd_take(thief, it.code, d, tk['slot'])
        evs.append(e)
        p = json.loads(w.x('SELECT payload FROM event_log WHERE id=?', (e,)).fetchone()[0])
        line = f"  {SLOTS[tk['slot']]}时{pn[place]}取{it.name}: 已执行，{p['norm']}，见证 {len(p['witnesses'])} 人"
        if tk is sc['takes'][-1]:
            rep = w.x("SELECT COUNT(*) FROM event_log WHERE type='REPORT' AND cause=?", (e,)).fetchone()[0]
            line += f"，当场举报 {rep} 起"
        print(line)
    w.x('COMMIT')
    first = next(i for i in S.items if i.code == code(sc['takes'][0]['item']))
    start = w.day
    while not w.x("SELECT 1 FROM event_log WHERE type='AUDIT_MISSING' AND payload LIKE ?", (f'%{first.name}%',)).fetchone() and w.day < start + 40: w.step()
    print(f'  {first.name}失窃在 {w.day - start} 日后的月朔点检中被发现；这期间无人知情')
    print(w.chronicle(d))


def long_and_seeds():
    ten_year(); seeds()


def report_baseline(w, secs, h1, h2):
    """基准段：摘要、年度粮账钱账、三天日报。"""
    summary(w, f'基准: 预热1年 + 3年 (用时 {secs:.1f} 秒, 状态哈希 {h1}, 重跑一致={h1 == h2})')
    for y in (1, 2, 3):
        r = year_report(w, y)
        print(f'  第{y}年 寺院粮账(石): {r["grain"]}')
        print(f'  第{y}年 寺院钱账(贯): {r["money"]}')
    for d in (YEAR + 125, YEAR + 97, YEAR + 337): print(w.chronicle(d))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--all', action='store_true'); a = ap.parse_args()
    t0 = time.time(); w = baseline(3); t1 = time.time()
    h1 = w.state_hash(); h2 = baseline(3).state_hash()
    report_baseline(w, t1 - t0, h1, h2)
    if a.all:
        experiments()
        long_and_seeds()
        people_tests(w)


if __name__ == '__main__':
    main()
