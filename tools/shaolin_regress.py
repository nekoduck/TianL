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


def scenario():
    """defs/scenario 里的回归场景：全部探测点、日序号、扰动字符串与标题（工具里不写死它们）。"""
    return load_spec().scenario


def day_of(at):
    """{ year, doy } -> 绝对日序号。"""
    return at['year'] * YEAR + at['doy']


def years_of(x):
    return x.get('years', scenario()['baseline']['years'])


def e1():
    """E1 封路（第2年腊月初一起）。"""
    x = scenario()['e1']
    start = day_of(x['at'])
    w = baseline(years_of(x), setup=lambda w: w.hooks[start].append(lambda w: w.close_road(x['days'], x['reason'])))
    summary(w, x['title'])
    win = [s for s in w.series if start <= s['day'] <= start + x['window']]
    reopen = start + x['days']
    rec = next((s['day'] - reopen for s in win if s['day'] >= reopen and s['blocked'] == 0 and s['short'] == 0), None)
    first_short = next((s['day'] - start for s in win if s['short'] > 0), None)
    print(f"  窗口内: {w.S.labels['temple_store']}最低 {min(s['cover'] for s in win):.1f} 日 | 首次缺货在封路第 {first_short} 日 | 同时受阻订单最多 {max(s['blocked'] for s in win)} 张 "
          f"| 复通后 {rec} 日内全部补齐 | 事件 {window(w, start, start + x['events'], ('ORDER_BLOCKED', 'ORDER_FAILED', 'ORDER_RENEWED', 'ORDER_ESCALATED', 'SHORTAGE', 'FORAGE', 'MEAL_SHORT'))}")
    e = w.x("SELECT id FROM event_log WHERE type='SHORTAGE' AND day>=? AND cause IS NOT NULL ORDER BY id LIMIT 1", (start,)).fetchone()
    if e: print('  因果追溯:', *w.why(e[0]), sep='\n     <- ')
    for off in x['chronicle']: print(w.chronicle(start + off))
    return w


def _bad_harvest(key):
    """歉收类实验：某年各作物亩产乘 factor。"""
    x = scenario()[key]
    crops = [nm for _, nm in load_spec().season.crops]
    w = baseline(years_of(x), setup=lambda w: w.yield_override.update({(x['year'], nm): x['factor'] for nm in crops}))
    summary(w, x['title'])
    return w, x


def e2():
    """E2 歉收。"""
    return _bad_harvest('e2')[0]


def e2b():
    """E2b 大荒，连看多年。"""
    w, x = _bad_harvest('e2b')
    best, tn, ts = w.K['tiers'][0], w.S.hh_label[w.hk.tenant], w.S.labels['temple_store']
    for y in range(1, x['years'] + 1):
        ds = [s for s in w.series if s['year'] == y]
        print(f"  第{y}年: {tn} {ds[-1]['tenants']} 户 | 僧 {min(s['head'] for s in ds)}-{ds[-1]['head']} | 余钱 {ds[-1]['cash'] / GUAN:.0f} 贯 | {ts}最低 {min(s['cover'] for s in ds):.0f} 日 "
              f"| 非{best} {sum(1 for s in ds if s['tier'] != best)} 日 | {window(w, y * YEAR, y * YEAR + 359, ('ALMS_ROUND_BACK', 'HH_LEFT', 'RELIEF', 'HH_BORROW', 'TENANTS_SETTLED', 'MONKS_RETURN', 'ORDER_EXPIRED', 'MEAL_SHORT'))}")
    for at in x['chronicle']: print(w.chronicle(day_of(at)))
    return w


def e3():
    """E3 要职离任（第2年四月十一）。"""
    x = scenario()['e3']
    at, role = day_of(x['at']), x['post'].rsplit(':', 1)[1]
    def setup(w): w.hooks[at].append(lambda w: w.die(w._appointee(getattr(w.T, role)), w.day - 1))
    w = baseline(years_of(x), setup=setup); summary(w, x['title'].format(post=getattr(w.T, role)))
    print('  ', window(w, at, at + x['events'], ('DEATH', 'ACTING', 'APPOINT', 'MEAL_SHORT')))
    for off in x['chronicle']: print(w.chronicle(at + off))
    return w


def e5():
    """E5 节日香客暴增（第2年）。"""
    x = scenario()['e5']
    at = day_of(x['at'])
    w = baseline(years_of(x), setup=lambda w: w.pilgrim_boost.update({at: x['mult']}))
    summary(w, x['title'].format(festival=w.S.cal.festivals[tuple(x['festival'])]))
    for off in x['chronicle']: print(w.chronicle(at + off))
    return w


def e6():
    """E6 余钱清零（第2年七月廿一）。"""
    x = scenario()['e6']
    at = day_of(x['at'])
    w = baseline(years_of(x), setup=lambda w: w.hooks[at].append(lambda w: w.pay(w.ac.org, w.ac.equity, w.bal(w.ac.org), x['reason'])))
    summary(w, x['title'])
    print(f"  此后 {x['days']} 日:", window(w, at, at + x['days'] - 1, ('ORDER_REDUCED', 'ORDER_DEFERRED', 'ORDER_EXPIRED', 'ORDER_ESCALATED', 'SHORTAGE', 'CLOTH_ISSUED', 'MERIT_SPEND', 'MEAL_SHORT')))
    print('  余钱(每 30 日):', [round(s['cash'] / GUAN) for s in w.series if s['day'] in range(day_of(x['sample_from']), w.day, x['sample_step'])])
    for off in x['chronicle']: print(w.chronicle(at + off))
    return w


def experiments():
    for f in (e1, e2, e2b, e3, e5, e6): f()


def ten_year():
    n = scenario()['ten_year']['years']
    w = baseline(n); summary(w, '十年基准')
    print('  年末余钱(贯):', [round([s for s in w.series if s['year'] == y][-1]['cash'] / GUAN) for y in range(1, n + 1)])
    print(f"  年内{w.S.labels['temple_store']}最低(日):", [round(min(s['cover'] for s in w.series if s['year'] == y)) for y in range(1, n + 1)])
    print('  年末僧数:', [[s for s in w.series if s['year'] == y][-1]['head'] for y in range(1, n + 1)], f'| {w.S.hh_label[w.hk.tenant]}:', [[s for s in w.series if s['year'] == y][-1]['tenants'] for y in range(1, n + 1)])
    print('  事件总数:', w.x('SELECT COUNT(*) FROM event_log').fetchone()[0], '| 排班行:', w.x('SELECT COUNT(*) FROM roster').fetchone()[0],
          '| 账目行:', w.x('SELECT COUNT(*) FROM ledger').fetchone()[0])
    return w


def seeds():
    print('\n===== 换 6 个种子各跑 3 年 =====')
    for seed in scenario()['seeds']:
        w = baseline(scenario()['baseline']['years'], params=dict(seed=seed)); ds = [s for s in w.series if s['year'] >= 1]
        c, best = w.cnt, w.K['tiers'][0]
        yrs = range(1, scenario()['baseline']['years'] + 1)
        ye = [round([s for s in ds if s['year'] == y][-1]['cash'] / GUAN) for y in yrs]
        ot = [year_report(w, y)['ontime_rate'] for y in yrs]
        print(f"  seed={seed:<9} 违规 {len(w.viol)} | 余钱 {min(s['cash'] for s in ds) / GUAN:.0f}-{max(s['cash'] for s in ds) / GUAN:.0f} 贯 (年末 {ye}) | 按期率 {ot} | {w.S.labels['temple_store']}最低 {min(s['cover'] for s in ds):.0f} 日 "
              f"| 非{best} {sum(1 for s in ds if s['tier'] != best)} 日 | 封路 {sum(1 for s in ds if s['closed'])} 日 | 断炊 {c['meal_short']} | 挨饿 {c['hunger_days']} 户日 | 离乡 {c['hh_left']} "
              f"| 缺货日 " + ' '.join(f"{w.G[k].name}{c['short_' + k]}" for k in w.G if c['short_' + k]))


def people_tests(w):
    """M2/M4 子集: 作息函数、值守排班、历史不可改写、物理/规范两层约束。"""
    print('\n===== 人物与独有物测试 =====')
    sc, pn, S = scenario(), w.S.place_name, w.S
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
    print(f"{w.cal(d0)['festival']}日全寺时间分配: " + ' '.join(f'{k}{v / tot:.0%}' for k, v in sorted(use.items(), key=lambda kv: -kv[1])))
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
    thief = w._mk(S.org.visitor_gen, v['name'], v['age'], v['hall'], joined=w.day); w.x('UPDATE person SET kind=?, org=? WHERE id=?', (v['kind'], v['org'], thief))
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
        if tk.get('report'):
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
    summary(w, f"基准: 预热1年 + {scenario()['baseline']['years']}年 (用时 {secs:.1f} 秒, 状态哈希 {h1}, 重跑一致={h1 == h2})")
    sc = scenario()['baseline']
    for y in range(1, sc['years'] + 1):
        r = year_report(w, y)
        print(f'  第{y}年 寺院粮账(石): {r["grain"]}')
        print(f'  第{y}年 寺院钱账(贯): {r["money"]}')
    for at in sc['chronicle']: print(w.chronicle(day_of(at)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--all', action='store_true'); a = ap.parse_args()
    years = scenario()['baseline']['years']
    t0 = time.time(); w = baseline(years); t1 = time.time()
    h1 = w.state_hash(); h2 = baseline(years).state_hash()
    report_baseline(w, t1 - t0, h1, h2)
    if a.all:
        experiments()
        long_and_seeds()
        people_tests(w)


if __name__ == '__main__':
    main()
