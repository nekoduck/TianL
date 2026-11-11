"""汇总与原型输出格式：tools/npc_regress.py 与 tests/test_npc_proto.py 共用。

proto_report() 逐行复现 reference/npc_spike.py main() 的输出（含 --all 的 N1、90 日与多种子），
便于与 reference/logs/npc_run_log.txt 逐行比对；其中两种“耗时”行只记录、不参与比对（见 TIMING_PATTERNS）。
"""
import re
from collections import Counter

from ..core import SLOTS, SLOTS_PER_DAY, rnd_b2
from .events import FOOD_THEFT, REPORT, SANCTION, THEFT_FOUND, label as event_label
from .engine import PKG_STAT
from .scenarios import ProtoRun, gossip_script, n1_script, proto60_scenario

# 日志里只记录、不比对的两类耗时（机器相关）：把数字换成占位再比
TIMING_PATTERNS = (re.compile(r'每次 [0-9.]+ 微秒  总耗时 [0-9.]+ 秒'), re.compile(r'每次决策 [0-9.]+ 微秒'))
PERCENT = 100                                  # 单位换算：百分数
FIRST_SLOT = 0                                  # 一日的第一个时辰（子）：轨迹按“当日第一个决定的次序”排
MICROS = 1e6                                    # 单位换算：微秒
SCALE_POPULATION, SCALE_DAYS = 300, 30          # 泛化检查（python3 -m tianl.npc.report）缺省的人口与日数
ARGS_FROM = 1                                   # sys.argv 里程序名之后才是命令行参数


def strip_timing(line):
    for pat in TIMING_PATTERNS:
        line = pat.sub('<耗时>', line)
    return line


def summary(eng):
    """原型 World.summary() 的对应物：一次运行的全部汇总数字。"""
    st = eng.stat
    fr, foe = eng.friends()
    P = eng.people
    same = sum(1 for a, b in fr if P[a].dorm == P[b].dorm or P[a].track == P[b].track
               or (P[a].office and P[a].office == P[b].office))
    cs = Counter(c.state for c in eng.norms.cases.values())
    return {'hash': eng.state_hash(), 'us': eng.elapsed / max(1, st['ps']) * MICROS,
            'attend': st['came'] / max(1, st['due']), 'hungry': st['hungry'] / st['ps'],
            'tired': st['tired'] / st['ps'], 'theft': st['theft'], 'seen': st['theft_seen'], 'wit': st['wit'],
            'wit_rep': st['wit_rep'], 'report': st['report'], 'disc': st['discovered'], 'cases': dict(cs),
            'sanction': st['sanction'], 'absence': st['absence'], 'slack': st['slack'],
            'slack_seen': st['slack_seen'], 'half': st['half_meal'], 'meals': st['meals'],
            'jobs': (st['job_done'], st['job_post']), 'chat': st['chat'], 'good': st['chat_good'] / max(1, st['chat']),
            'shared': st['shared'], 'friends': len(fr), 'friend_same': same, 'foes': foe, 'ill': st['ill'],
            'acting': st['acting'], 'full': st['full'], 'viol': len(eng.fac.violations),
            'moodlow': eng.moodlow / max(1, eng.pd), 'gone': sum(1 for p in P if p.gone is not None)}


def line(tag, m):
    return ('%-14s 到课%.3f 饥%.4f 困%.4f 偷食%d(被见%d) 举报%d 处分%d 案%s 缺课%d 怠工%d/%d 半餐%d/%d 好友%d 不睦%d 低落%.3f 迁单%d %s'
            % (tag, m['attend'], m['hungry'], m['tired'], m['theft'], m['seen'], m['report'], m['sanction'], m['cases'],
               m['absence'], m['slack_seen'], m['slack'], m['half'], m['meals'], m['friends'], m['foes'], m['moodlow'],
               m['gone'], m['hash']))


def trace_lines(run, day=None):
    """第 day 日（缺省取场景的 trace_day）四个人（惯犯、懒人、清众第一位、场景指定岗位的第一位）的十二时辰轨迹，
    次序与原型一致（按当日 0 时辰的决定次序）。"""
    eng = run.engine
    sp, scn = eng.spec, run.scenario
    day = scn.trace_day if day is None else day
    who = {run.glutton.ix, run.lazy.ix, eng.common[0].ix, eng.by[scn.trace_post][0]}
    n = len(eng.people)
    off = (day * sp.rotate[0] + FIRST_SLOT * sp.rotate[1]) % n
    out = []
    for i in sorted(who, key=lambda i: (i - off) % n):
        p = eng.people[i]
        out.append('—— 第 %d 日 %s（%s，精进%.0f 守戒%.0f 合群%.0f 馋%.0f）'
                   % (day, p.name, p.office or p.track + scn.track_suffix, p.D, p.S, p.G, p.T))
        tr = []
        for slot in range(SLOTS_PER_DAY):
            place, act, layer, reason = eng.where(i, day, slot)
            tr.append('%s %s·%s[%s]' % (SLOTS[slot], sp.places[place], reason, layer))
        out.append('   ' + ' | '.join(tr))
    return out


def chain_lines(run):
    """惯犯的因果链：他的偷食与处分，以及指向他偷食的失窃与举报。"""
    eng = run.engine
    gl = run.glutton
    out = ['—— 惯犯 %s 的因果链：' % gl.name]
    for e in eng.evs:
        if e.kind in (FOOD_THEFT, SANCTION) and e.actor == gl.ix or (
                e.kind in (REPORT, THEFT_FOUND) and e.cause is not None and eng.ev_by_id[e.cause].actor == gl.ix):
            out.append('   #%d 第%d日%s %s %s 见证%d人 %s' % (
                e.id, e.day, SLOTS[e.slot], event_label(e.kind), ('←#%d' % e.cause) if e.cause is not None else '',
                len(e.wit), e.data.get('txt', e.data.get('why', ''))))
    return out


def share_line(eng):
    """“行为包占比”一行：每层行为包占了多少个决定（统计键 pkg_<层>）。"""
    st = eng.stat
    return '行为包占比：' + '  '.join('%s %.1f%%' % (k[len(PKG_STAT):], PERCENT * v / st['ps'])
                                    for k, v in sorted(st.items()) if k.startswith(PKG_STAT))


def allocation_lines(eng):
    """各人群（清众、执事……）“每日时辰分配”各一行：一日 12 个时辰花在哪类活动上（类别取交互的 category）。"""
    out = []
    for grp in eng.spec.groups:
        tot = sum(eng.acts[grp].values())
        out.append('%s 每日时辰分配：' % grp + '  '.join('%s %.2f' % (k, SLOTS_PER_DAY * v / tot)
                                                       for k, v in eng.acts[grp].most_common()))
    return out


def scale_report(n, days, seed=None, rng=rnd_b2):
    """泛化检查：同一份 defs，只把人口改成 n，跑 days 日；返回 (行列表, 这次运行)。输出各层占比与时间分配。
    不要求与原型一致（人口变了就是另一个世界）；要看的是：不报错、预约不越界、每个决定都说得清、各层占比与时间分配仍然合理。"""
    run = ProtoRun(seed=seed, n=n, days=days, rng=rng).run()
    eng = run.engine
    st = eng.stat
    out = ['== 泛化：同一份 defs，人口 %d × %d 日 × %d 时辰 ==' % (len(eng.people), days, SLOTS_PER_DAY),
           '决策数 %d  预约越界 %d 次；设施满员改选 %d 次；闲谈 %d 次；传话 %d 次；差事 完成/发布 = %d/%d'
           % (st['ps'], len(eng.fac.violations), st['full'], st['chat'], st['shared'], st['job_done'], st['job_post']),
           '偷食 %d  举报 %d  处分 %d  缺课 %d  怠工 %d/%d  半餐 %d/%d  迁单 %d  哈希 %s'
           % (st['theft'], st['report'], st['sanction'], st['absence'], st['slack_seen'], st['slack'], st['half_meal'],
              st['meals'], sum(1 for p in eng.people if p.gone is not None), eng.state_hash()),
           share_line(eng)]
    out.extend(allocation_lines(eng))
    return out, run


def main(argv):
    """python3 -m tianl.npc.report [--scale N] [--days D]：泛化检查（缺省 300 人 30 日）。"""
    import sys
    n, days = SCALE_POPULATION, SCALE_DAYS
    for flag, name in (('--scale', 'n'), ('--days', 'days')):
        if flag in argv:
            v = int(argv[argv.index(flag) + 1])
            n, days = (v, days) if name == 'n' else (n, v)
    lines, _ = scale_report(n, days)
    sys.stdout.write('\n'.join(lines) + '\n')


def proto_report(include_all=False, seed=None, rng=rnd_b2):
    """逐行复现原型 main() 的输出；返回 (行列表, 附带数据字典)。附带数据里有各次运行与汇总，供测试断言用。
    种子、实验的日子与对照组、报表用词都取原型场景（defs/scenario/proto60.toml）。"""
    scn = proto60_scenario()
    seed = scn.seed if seed is None else seed
    out, info = [], {}
    g = ProtoRun(seed=seed, rng=rng).common
    script = gossip_script(g)
    w = ProtoRun(seed=seed, rng=rng, script=script).run()
    m = summary(w.engine)
    eng = w.engine
    st = eng.stat
    info.update(base=w, m=m)
    out.append('== 基准：60 僧 × 30 日 × 12 时辰 ==')
    out.append(line('基准', m))
    out.append('决策数 %d  每次 %.1f 微秒  总耗时 %.2f 秒' % (st['ps'], m['us'], eng.elapsed))
    out.append('预约越界 %d 次；设施满员改选 %d 次；闲谈 %d 次（投机 %.2f）；传话 %d 次'
               % (m['viol'], m['full'], m['chat'], m['good'], m['shared']))
    out.append('差事 完成/发布 = %d/%d；代理帮厨 %d 人次；生病 %d 起' % (m['jobs'][0], m['jobs'][1], m['acting'], m['ill']))
    ae, aa = sum(eng.att_exp.values()), sum(eng.att.values())
    out.append('过堂人数：实到/应到 = %d/%d（偏差 %.2f%%）' % (aa, ae, PERCENT * abs(aa - ae) / ae))
    out.append(share_line(eng))
    out.extend(allocation_lines(eng))
    w2 = ProtoRun(seed=seed, rng=rng, script=script).run()
    w3 = ProtoRun(seed=seed, rng=rng, script=script, observer=scn.observer_place).run()
    info.update(rerun=w2, observed=w3)
    out.append('确定性：重跑哈希 %s；观察者在廊下 %s（多生成 %d 条细节叙述）' % (w2.hash == w.hash, w3.hash == w.hash, w3.engine.narr))
    cm = [p.ix for p in eng.common if p.gone is None]
    P = eng.people
    same = [eng.agree(a, b) for a in cm for b in cm if a < b and P[a].track == P[b].track]
    diff = [eng.agree(a, b) for a in cm for b in cm if a < b and P[a].track != P[b].track]
    out.append('个体差异：同修行方向两人整月同处一地 %.3f；不同方向 %.3f；完全相同的月轨迹 %d 对'
               % (sum(same) / len(same), sum(diff) / len(diff), sum(1 for x in same + diff if x == 1.0)))
    fr, foe = eng.friends()
    out.append('好友 %d 对，其中同寮/同方向/同岗 %d 对；不睦 %d 对' % (len(fr), m['friend_same'], foe))
    out.append('自由时段的选择：' + '  '.join('%s %d' % kv for kv in eng.choice.most_common()))
    live = [p for p in P if p.gone is None]
    out.append('月末需求均值：' + '  '.join('%s %.0f' % (nm, sum(p.need[k] for p in live) / len(live))
                                          for k, nm in eng.spec.needs.names.items()))
    out.append('查寮空铺 %d 次；传讯 %d 人次，认错 %d 起；当面禀告 %d 次'
               % (st['empty_bed'], st['asked'], st['confess'], st['rep_face']))
    rm = eng.rumor
    out.append('传闻实验（第 %d 日%s时，一人撞见、不举报）：仍记得的人数按日 = %s'
               % (script.gossip[0], SLOTS[script.gossip_slot], [c for d, c in rm.curve]))
    out.append('  累计听说过的人数按日 = %s' % [c for d, c in rm.cum])
    out.append('  经手层数分布： %s  月末仍知情 %d 人' % (dict(sorted(rm.hops.items())), rm.curve[-1][1]))
    out.extend(trace_lines(w))
    out.extend(chain_lines(w))
    if not include_all:
        return out, info
    n1s = scn.n1
    out.append('== 实验 N1：第 %d 日起%s同时病倒 %d 日 ==' % (n1s.day, n1s.sick_label, n1s.days))
    n1 = n1_script(eng)
    for tag, act in n1s.arms:
        x = ProtoRun(seed=seed, rng=rng, script=n1, acting=act).run()
        mx = summary(x.engine)
        info['n1_' + tag] = (x, mx)
        out.append(line(tag, mx))
        lo, hi = n1s.window
        out.append('   逐日偷食累计（第%d–%d日）： %s' % (lo, hi, [t for d, t, h, hu in x.engine.daily if lo <= d <= hi]))
    out.append('== %d 日与多种子 ==' % scn.long_days)
    x = ProtoRun(seed=seed, rng=rng, days=scn.long_days).run()
    mx = summary(x.engine)
    info['d90'] = (x, mx)
    out.append(line('%d日' % scn.long_days, mx))
    out.append('   每次决策 %.1f 微秒' % mx['us'])
    for sd in scn.extra_seeds:
        x = ProtoRun(seed=sd, rng=rng).run()
        mx = summary(x.engine)
        info['seed%d' % sd] = (x, mx)
        out.append(line('种子%d' % sd, mx))
    return out, info


if __name__ == '__main__':
    import sys
    main(sys.argv[ARGS_FROM:])
