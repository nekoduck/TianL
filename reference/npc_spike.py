#!/usr/bin/env python3
# npc_spike.py — NPC 生活引擎最小原型
# 行为包栈(Bethesda/Gothic) + 需求(Sims/RimWorld/DF) + 设施广告与预约(Sims/Minecraft/RimWorld)
# + 工作板(RimWorld/DF/STALKER) + 感知与传闻(Gothic/Minecraft/DF) + 规矩与案件(Oblivion/DF) + 好恶(CK3/RimWorld)
# 只用标准库；所有随机数都是 hash(seed, 用途, 日, 时辰, 人) 的计数器式随机数。
import hashlib, math, sys, time
from collections import Counter

SLOTS = '子丑寅卯辰巳午未申酉戌亥'
SEED = 20261110
NIGHT = (11, 0, 1)
PEN = 12            # 传闻每转一手损失的强度（Minecraft 的 share penalty 结构）
NEWS_DECAY = 2      # 每日衰减
NEWS_MIN = 25       # 低于此强度不再外传

def rnd(*k):
    h = hashlib.blake2b('|'.join(map(str, k)).encode(), digest_size=8).digest()
    return int.from_bytes(h, 'big') / 2 ** 64

def gauss(mean, sd, *k):
    u1 = max(rnd(*k, 'a'), 1e-12); u2 = rnd(*k, 'b')
    return mean + sd * math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)

def clamp(x, lo=0.0, hi=100.0):
    return lo if x < lo else hi if x > hi else x

PLACE = {'hall': '大雄宝殿', 'zen': '禅堂', 'ref': '斋堂', 'kit': '香积厨', 'store': '库房', 'dorm1': '东寮',
         'dorm2': '西寮', 'dorm3': '后寮', 'lib': '藏经阁', 'yard': '练武场', 'garden': '菜园', 'gate': '山门',
         'bath': '浴室', 'court': '戒律院', 'inf': '延寿堂', 'clo': '廊下', 'well': '井台', 'woods': '后山',
         'mill': '磨坊', 'abbot': '方丈室', 'office': '库院'}
CAPF = {'lib': 10, 'yard': 24, 'bath': 24, 'well': 8, 'zen': 70, 'clo': 60}   # 设施工位数
ROAM = ['clo', 'kit', 'hall', 'dorm1', 'dorm2', 'dorm3', 'gate', 'lib', 'yard', 'well', 'garden', 'zen']
OFFICES = [('方丈', 1), ('监院', 1), ('维那', 1), ('典座', 1), ('饭头', 4), ('库头', 1), ('知客', 1), ('藏主', 1),
           ('园头', 1), ('园工', 5), ('首座', 1), ('执事', 2), ('僧值', 2), ('堂主', 1)]
OFFICE_PLACE = {'方丈': 'abbot', '监院': 'office', '库头': 'store', '知客': 'gate', '藏主': 'lib', '园头': 'garden',
                '园工': 'garden', '首座': 'court', '执事': 'court', '堂主': 'inf'}
OFFICE_SLOTS = {'方丈': (5, 8), '监院': (5, 8), '库头': (5, 8), '知客': (5, 7, 8), '藏主': (5, 7, 8), '园头': (5, 8),
                '园工': (5, 8), '首座': (5, 8), '执事': (5, 8), '堂主': (5, 7, 8)}
KITCHEN = ('典座', '饭头'); KIT_SLOTS = (2, 3, 5, 8)
DISC = {'方丈', '监院', '维那', '首座', '执事', '僧值'}
GROUP = {2: ('zen', 'zazen', '晨坐'), 3: ('hall', 'chant', '早课'), 4: ('ref', 'meal', '早斋'),
         6: ('ref', 'meal', '午斋'), 9: ('hall', 'chant', '晚课'), 10: ('zen', 'zazen', '晚坐')}
CLASS = {'武': ('yard', 'martial', '习武'), '学': ('lib', 'study', '读经'), '禅': ('zen', 'zazen', '坐禅')}
BASE = {'h': -7.0, 'e': -6.0, 'c': -1.0, 's': -1.6, 'a': -3.0}
EFF = {'sleep': {'e': 36}, 'rest': {'e': 22}, 'chant': {'s': 2, 'a': 3}, 'meal': {'s': 2}, 'zazen': {'e': 3, 'a': 4},
       'work': {'e': -2, 'c': -2}, 'martial': {'e': -3, 'c': -3, 'h': -3}, 'study': {'a': 3}, 'bath': {'c': 60},
       'wash': {'c': 25}, 'chat': {'s': 16}, 'stroll': {'s': 2, 'e': 2}, 'patrol': {'e': -1}, 'guard': {},
       'report': {}, 'kneel': {'e': -3}, 'confined': {'e': 4, 's': -2}, 'sick': {'e': 16}, 'steal': {'h': 30}}
BONUS = {'martial': ('武', 23, 6), 'study': ('学', 20, 3), 'zazen': ('禅', 11, 0)}
SAL = {'偷食': 80, '处分': 60, '失窃': 50, '缺课': 0, '怠工': 0, '举报': 0, '夜不在寮': 0}
CAT = {'sleep': '睡眠', 'rest': '睡眠', 'chant': '课诵', 'zazen': '坐禅', 'meal': '斋食', 'work': '作务', 'patrol': '作务',
       'guard': '作务', 'martial': '自修', 'study': '自修', 'bath': '洗沐', 'wash': '洗沐', 'chat': '交游',
       'stroll': '交游', 'report': '其他', 'kneel': '受罚', 'confined': '受罚', 'sick': '病', 'steal': '其他'}


class P:
    __slots__ = ('id', 'name', 'office', 'track', 'dorm', 'D', 'S', 'G', 'T', 'R', 'need', 'ill', 'conf', 'kneel',
                 'pending', 'offences', 'absent', 'slackd', 'news', 'thoughts', 'duty_day', 'gone', 'lazy_day')

    def __init__(s, i, name, office, track):
        s.id, s.name, s.office, s.track = i, name, office, track
        s.dorm = 'dorm%d' % (i % 3 + 1)
        s.need = {'h': 70.0, 'e': 80.0, 'c': 70.0, 's': 60.0, 'a': 60.0}
        s.ill = s.conf = s.kneel = 0
        s.pending = []; s.offences = 0; s.absent = []; s.slackd = []
        s.news = {}; s.thoughts = []; s.duty_day = 0; s.gone = None; s.lazy_day = 0


class World:
    def __init__(s, seed=SEED, n=60, days=30, acting=True, observer=None, script=None, trace_day=8):
        s.seed, s.n, s.days, s.acting, s.observer = seed, n, days, acting, observer
        s.script = script or {}; s.trace_day = trace_day
        s.people = []; s.events = []; s.cases = {}; s.mods = {}
        s.stat = Counter(); s.acts = {'清众': Counter(), '执事': Counter()}
        s.water = 8; s.wood = 8; s.undisc = []; s.announce = []
        s.track = None; s.curve = []; s.hops = Counter(); s.traces = {}; s.places = {}
        s.kit_staff = {}; s.h = hashlib.sha256(); s.narr = 0; s.viol = []
        s.att = Counter(); s.att_exp = Counter(); s.moodlow = 0; s.pd = 0; s.daily = []
        s.choice = Counter(); s.heard = set(); s.cum = []
        s.build()

    # ---------- 建人 ----------
    def build(s):
        pool = '明净空海山石泉松竹云月风清远静定觉悟通达道德仁义礼智信诚真善忍和安宁平康福寿喜乐观照闻思修证法宝因缘果行愿力圆融正见坚勤朴厚'
        for o, k in OFFICES:
            for _ in range(k):
                i = len(s.people)
                s.people.append(P(i, ('玄' if o in ('方丈', '首座') else '慧') + pool[i], o, '禅学武'[i % 3]))
        m = s.n - len(s.people)
        for j in range(m):
            i = len(s.people)
            s.people.append(P(i, '虚' + pool[i % len(pool)], None, '武' if j < 14 else '学' if j < 24 else '禅'))
        for p in s.people:
            b = 8 if p.office else 0
            p.D = clamp(gauss(60 + b, 20, s.seed, 'D', p.id), 5, 98)
            p.S = clamp(gauss(62 + b, 20, s.seed, 'S', p.id), 5, 98)
            p.G = clamp(gauss(50, 22, s.seed, 'G', p.id), 5, 98)
            p.T = clamp(gauss(42, 22, s.seed, 'T', p.id), 5, 98)
            p.R = clamp(gauss(55, 22, s.seed, 'R', p.id), 5, 98)
        s.common = [p for p in s.people if p.office is None]
        g, l, z = s.common[5], s.common[11], s.common[20]       # 三个“要角”：馋而散漫、懒、刚正
        g.T, g.S, g.D = 92, 22, 45; l.D, l.S = 18, 38; z.R, z.S = 95, 90
        s.glutton, s.lazy = g.id, l.id
        s.by = {}
        for p in s.people:
            s.by.setdefault(p.office, []).append(p.id)
        n = s.n
        s.compat = [[0.0] * n for _ in range(n)]; s.base = [[0.0] * n for _ in range(n)]
        for a in s.people:
            for b in s.people:
                if a.id == b.id: continue
                c = 1 - (abs(a.D - b.D) + abs(a.S - b.S) + abs(a.G - b.G)) / 300
                s.compat[a.id][b.id] = c
                grp = a.office is not None and (a.office == b.office or (a.office in KITCHEN and b.office in KITCHEN))
                s.base[a.id][b.id] = 5 * (a.dorm == b.dorm) + 4 * (a.track == b.track) + 6 * grp + (c - 0.75) * 40

    # ---------- 好恶（CK3 式带期限的修正项）----------
    def opinion(s, a, b):
        v = s.base[a][b]
        for m in s.mods.get((a, b), ()): v += m[0]
        return clamp(v, -100, 100)

    def add_mod(s, a, b, val, days, kind, cap, day):
        L = s.mods.setdefault((a, b), [])
        same = [m for m in L if m[2] == kind]
        if len(same) >= cap: same[0][1] = day + days
        else: L.append([val, day + days, kind])

    def mood(s, p):
        n = p.need
        return clamp(0.28 * n['h'] + 0.22 * n['e'] + 0.10 * n['c'] + 0.15 * n['s'] + 0.25 * n['a']
                     + sum(t[0] for t in p.thoughts))

    def think(s, p, val, days, label, day, cap=3):
        if sum(1 for t in p.thoughts if t[2] == label) < cap: p.thoughts.append([val, day + days, label])

    # ---------- 事件、见证、见闻 ----------
    def ev(s, kind, actor, place, wit, day, slot, cause=None, **data):
        e = {'id': len(s.events), 'kind': kind, 'actor': actor, 'place': place, 'wit': list(wit), 'day': day,
             'slot': slot, 'cause': cause, 'data': data}
        s.events.append(e)
        if SAL.get(kind, 0) > 0:
            for w in wit:
                if w != actor: s.people[w].news[e['id']] = [SAL[kind], 0, None]
        return e

    def guards(s, day):
        m = len(s.common)
        return (s.common[(2 * day) % m].id, s.common[(2 * day + 1) % m].id)

    def night_patroller(s, day):
        return s.by['僧值'][day % 2]

    def court_open(s, day):
        return any(s.people[i].ill < day and s.people[i].conf < day for i in s.by['首座'] + s.by['执事'])

    def lib_open(s, day, slot):
        z = s.people[s.by['藏主'][0]]
        return slot in (5, 7, 8) and z.ill < day

    # ---------- 行为包栈：自上而下，第一个成立的生效 ----------
    def duty(s, p, day, slot):
        if (p.office in KITCHEN or p.duty_day == day) and slot in KIT_SLOTS:
            return ('kit', 'work', '值守', '厨务' if p.office in KITCHEN else '代理帮厨')
        if p.office == '僧值':
            night = s.night_patroller(day) == p.id
            if (night and slot in (0, 1)) or (not night and slot in (5, 7, 8)):
                ks = sorted(ROAM, key=lambda x: rnd(s.seed, 'roam', day, slot, x))[:3]
                return (ks[0], 'patrol', '值守', '巡夜' if night else '巡寮', set(ks))
            if night and slot in (7, 8): return (p.dorm, 'sleep', '值守', '巡夜后补觉')
        if slot in (5, 7, 8) and p.id in s.guards(day): return ('gate', 'guard', '值守', '山门值守')
        return None

    def tempted(s, p, day, slot):
        h = p.need['h']; th = 35 + (p.T - 40) * 0.7       # 越馋，越早起念
        if h >= th or p.S >= 45: return False
        pr = (45 - p.S) / 45 * (th - h) / th * 1.6
        return rnd(s.seed, 'tempt', day, slot, p.id) < min(0.9, pr)

    def decide(s, p, day, slot):
        n = p.need
        if p.ill >= day:                                                    # 1 强制状态
            if slot in NIGHT or slot == 2: return ('inf', 'sleep', '强制', '卧病')
            return ('inf', 'meal', '强制', '病号饭') if slot in (4, 6) else ('inf', 'sick', '强制', '卧病')
        if p.conf >= day:
            if slot in NIGHT or slot == 2: return ('court', 'sleep', '强制', '禁闭')
            return ('court', 'meal', '强制', '禁闭送饭') if slot in (4, 6) else ('court', 'confined', '强制', '禁闭')
        if p.kneel >= day and slot == 7: return ('hall', 'kneel', '处分', '罚跪香')   # 2 处分
        d = s.duty(p, day, slot)
        if p.pending and slot in (5, 8) and (d is None or p.office == '僧值') and s.court_open(day):
            return ('court', 'report', '反应', '到戒律院举报')                  # 3 反应
        if d: return d                                                      # 4 值守
        if n['e'] < 10 and slot not in (4, 6): return (p.dorm, 'sleep', '生理', '昏沉不支')   # 5 生理紧急
        if n['h'] < 12 and slot not in (4, 6) and slot not in NIGHT:
            if p.S < 55: return ('kit', 'steal', '生理', '饿极偷食')
            s.think(p, -3, 1, '忍饥', day, 2)
        if slot in NIGHT:                                                   # 6 夜间
            if slot == 1 and s.tempted(p, day, slot): return ('kit', 'steal', '越轨', '夜里偷食')
            return (p.dorm, 'sleep', '作息', '就寝')
        if slot in (2, 3):
            if slot == 2 and p.D < 35 and rnd(s.seed, 'lazy', day, p.id) < (35 - p.D) / 60: p.lazy_day = day
            if p.lazy_day == day: return (p.dorm, 'sleep', '越轨', '贪睡不起')
            if n['e'] < 25: return (p.dorm, 'sleep', '生理', '困乏未起')
        if day in (1, 15) and slot == 7: return ('hall', 'chant', '集体', '布萨诵戒')   # 7 集体
        g = GROUP.get(slot)
        if g: return (g[0], g[1], '集体', g[2])
        o = p.office                                                        # 8 岗位
        if o in OFFICE_SLOTS and slot in OFFICE_SLOTS[o]: return (OFFICE_PLACE[o], 'work', '岗位', o + '理事')
        if o is None:                                                       # 9 身份
            if slot == 5:
                sl = max(0.0, (40 - p.D) / 80) + (0.15 if s.mood(p) < 35 else 0)
                if rnd(s.seed, 'slack', day, p.id) < sl: return s.sandbox(p, day, slot, '怠工')
                for j in s.jobs:
                    if j[3] > 0:
                        j[3] -= 1; j[4].append(p.id)
                        return (j[2], 'work', '差事', j[1])
            if slot == 8:
                pl, act, lab = CLASS[p.track]
                if s.occ[pl] < CAPF.get(pl, 999):
                    s.occ[pl] += 1; return (pl, act, '身份', lab)
                s.stat['full'] += 1
                return ('hall', act, '身份', lab + '（改在讲堂）')
        if slot == 7 and s.tempted(p, day, slot): return ('kit', 'steal', '越轨', '午后偷食')
        return s.sandbox(p, day, slot, '自由')                                # 10 自由

    # ---------- 自由活动：设施打广告，人按需求打分，在前三名里抽（Sims）；占位即预约 ----------
    def sandbox(s, p, day, slot, pkg):
        n = p.need
        U = lambda l: ((100 - l) / 100) ** 2 + 0.05
        dil = 0.6 + p.D / 125
        pf = lambda t: 0.9 * p.D / 100 if p.track == t else 0.0          # 性格与志向直接给广告加分（Sims 3）
        c = [('rest', p.dorm, U(n['e']) * 22 + 0.5 * (1 - p.D / 100), '小憩'),
             ('zazen', 'zen', (U(n['a']) * (15 if p.track == '禅' else 4) + U(n['e']) * 3) * dil + pf('禅'), '坐禅'),
             ('martial', 'yard', (U(n['a']) * (23 if p.track == '武' else 6) - U(n['e']) * 3) * dil + pf('武'), '习武'),
             ('wash', 'well', U(n['c']) * 25, '浣洗'),
             ('chat', 'clo', U(n['s']) * 16 * (0.5 + p.G / 100) + 0.9 * p.G / 100, '闲谈')]
        if s.lib_open(day, slot): c.append(('study', 'lib', U(n['a']) * (23 if p.track == '学' else 6) * dil + pf('学'), '读经'))
        if day % 5 == 4 and slot in (7, 8): c.append(('bath', 'bath', U(n['c']) * 60, '沐浴'))
        c.sort(key=lambda x: -x[2])
        top = [x for x in c[:3] if x[2] > 0]
        r = rnd(s.seed, 'sb', day, slot, p.id) * sum(x[2] for x in top); acc = 0.0; first = top[0]
        for x in top:
            acc += x[2]
            if r <= acc: first = x; break
        for act, place, sc, label in [first] + [x for x in c if x is not first]:
            if place.startswith('dorm') or s.occ[place] < CAPF.get(place, 999):
                s.occ[place] += 1
                return (place, act, pkg, label)
            s.stat['full'] += 1
        return ('clo', 'stroll', pkg, '散步')

    # ---------- 闲谈：改好恶，传见闻 ----------
    def share(s, A, B, day, slot):
        best = None
        for e, v in A.news.items():
            if v[0] < NEWS_MIN or s.events[e]['actor'] == B.id: continue
            cur = B.news.get(e)
            if cur and cur[0] >= v[0] - PEN: continue
            if best is None or v[0] > best[1]: best = (e, v[0], v[1])
        if not best: return
        e, st, hop = best
        if rnd(s.seed, 'share', day, slot, A.id, B.id, e) < min(1.0, st / 100 + 0.2) * (0.5 + A.G / 100):
            if e == s.track and B.id not in s.heard: s.hops[hop + 1] += 1; s.heard.add(B.id)
            B.news[e] = [st - PEN, hop + 1, A.id]; s.stat['shared'] += 1

    def chat(s, a, b, day, slot, full):
        A, B = s.people[a], s.people[b]
        good = rnd(s.seed, 'chat', day, slot, a, b) < 0.7 + (s.compat[a][b] - 0.5) * 0.6
        if good:
            s.add_mod(a, b, 4, 30, '投机', 8, day); s.add_mod(b, a, 4, 30, '投机', 8, day)
            if full: s.think(A, 2, 1, '谈得来', day); s.think(B, 2, 1, '谈得来', day)
        else:
            s.add_mod(a, b, -4, 20, '不投机', 5, day); s.add_mod(b, a, -4, 20, '不投机', 5, day)
        if not full: A.need['s'] = clamp(A.need['s'] + 4); B.need['s'] = clamp(B.need['s'] + 4)
        s.stat['chat'] += 1; s.stat['chat_good'] += good
        s.share(A, B, day, slot); s.share(B, A, day, slot)

    # ---------- 案件（见证 → 举报 → 裁断 → 处分 → 公告）----------
    def sanction(s, eid, c, day):
        th = s.events[eid]; off = s.people[th['actor']]
        if off.gone is not None: c['state'] = '结案'; return
        k = off.offences; off.offences += 1
        if k == 0: off.kneel = day + 3; txt = '罚跪香三日'
        elif k == 1: off.conf = day + 2; off.need['e'] = clamp(off.need['e'] - 30); s.think(off, -15, 5, '受杖', day); txt = '杖责并禁闭二日'
        elif k == 2: off.conf = day + 5; txt = '禁闭五日'
        else: off.gone = day; txt = '迁单出寺'
        s.think(off, -8, 3, '受处分', day)
        for a in c['acc']: s.add_mod(off.id, a, -30, 60, '告发', 1, day)
        c['state'] = '已处分'; c['txt'] = txt; c['day'] = day
        s.announce.append((eid, off.id, txt)); s.stat['sanction'] += 1; s.stat['san_' + txt] += 1

    # ---------- 一个时辰 ----------
    def step_slot(s, day, slot):
        n = s.n; s.occ = Counter(); seen = set(); patroller = None; dec = {}
        off = (day * 7 + slot * 3) % n
        for k in range(n):
            p = s.people[(off + k) % n]
            if p.gone is not None: continue
            d = s.decide(p, day, slot)
            if len(d) == 5: seen = d[4]; patroller = p.id; d = d[:4]
            dec[p.id] = d
        # 闲谈配对：按好恶挑人（落单的改为散步）
        L = sorted((i for i, d in dec.items() if d[1] == 'chat'), key=lambda i: rnd(s.seed, 'cq', day, slot, i))
        while len(L) >= 2:
            a = L.pop(0)
            b = max(L, key=lambda j: s.opinion(a, j) + 30 * rnd(s.seed, 'pair', day, slot, a, j))
            L.remove(b); s.chat(a, b, day, slot, True)
        for a in L: dec[a] = (dec[a][0], 'stroll', dec[a][2], '无人可谈，独自散步')
        if slot == 5:
            for j in s.jobs:
                w = j[4]
                for q in range(0, len(w) - 1, 2):
                    if rnd(s.seed, 'wchat', day, w[q]) < 0.6: s.chat(w[q], w[q + 1], day, slot, False)
                if j[1] == '挑水': s.water += len(w)
                if j[1] == '打柴': s.wood += len(w)
                s.stat['job_done'] += len(w); s.stat['job_post'] += len(w) + j[3]
        if slot in (3, 5): s.kit_staff[slot] = sum(1 for d in dec.values() if d[0] == 'kit' and d[1] == 'work')
        gain = 45
        if slot in (4, 6):
            ok = s.kit_staff.get(3 if slot == 4 else 5, 0) >= 3 and s.water >= 2 and s.wood >= 2
            if ok: s.water -= 2; s.wood -= 2
            else: gain = 22; s.stat['half_meal'] += 1
            s.stat['meals'] += 1
            exp = sum(1 for p in s.people if p.gone is None and p.ill < day and p.conf < day)
            s.att_exp[slot] += exp; s.att[slot] += sum(1 for d in dec.values() if d[0] == 'ref')
        # 需求结算
        for i, d in dec.items():
            p = s.people[i]; nd = p.need; act = d[1]; e = EFF.get(act, {})
            fh = 1 + (p.T - 40) / 400
            nd['h'] = clamp(nd['h'] + (-3 * fh if act == 'sleep' else BASE['h'] * fh + e.get('h', 0))
                            + (gain if act == 'meal' else 0))
            nd['e'] = clamp(nd['e'] + BASE['e'] + e.get('e', 0))
            nd['c'] = clamp(nd['c'] + BASE['c'] + e.get('c', 0) + (6 if slot == 2 and act != 'sleep' else 0))
            nd['s'] = clamp(nd['s'] + BASE['s'] * (0.5 + p.G / 100) + e.get('s', 0))
            b = BONUS.get(act)
            nd['a'] = clamp(nd['a'] + BASE['a'] + e.get('a', 0) + ((b[1] if p.track == b[0] else b[2]) if b else 0)
                            + (6 if d[2] in ('岗位', '值守') and act != 'sleep' else 0))
            if d[2] in ('自由', '怠工'): s.choice[d[3][:2]] += 1
            if act == 'bath': s.think(p, 4, 1, '沐浴', day, 1)
            grp = '清众' if p.office is None else '执事'
            s.acts[grp][CAT.get(act, '其他')] += 1
            s.stat['ps'] += 1; s.stat['hungry'] += nd['h'] < 25; s.stat['tired'] += nd['e'] < 20
            s.stat['pkg_' + d[2]] += 1
            s.places.setdefault(i, []).append(d[0])
            if day == s.trace_day and i in (s.glutton, s.lazy, s.common[0].id, s.by['典座'][0]):
                s.traces.setdefault(i, []).append((SLOTS[slot], PLACE[d[0]], d[3], d[2]))
            s.h.update(('%d,%d,%d,%s,%s;' % (day, slot, i, d[0], d[1])).encode())
        for pl, cap in CAPF.items():
            if s.occ[pl] > cap: s.viol.append((day, slot, pl, s.occ[pl]))
        # 观察者所在场所的细节叙述：只读，不改任何状态
        if s.observer:
            here = sorted((i for i, d in dec.items() if d[0] == s.observer), key=lambda i: rnd(s.seed, 'narr', day, slot, i))
            s.narr += len(here)
        awake = lambda j: dec[j][1] != 'sleep'
        # 偷食 → 见证 → 是否举报
        for i, d in dec.items():
            if d[1] != 'steal': continue
            wit = [j for j, x in dec.items() if x[0] == 'kit' and j != i and awake(j)]
            if patroller is not None and 'kit' in seen and patroller != i and patroller not in wit: wit.append(patroller)
            e = s.ev('偷食', i, 'kit', wit, day, slot, why=d[3]); s.stat['theft'] += 1; s.stat['theft_seen'] += bool(wit)
            s.undisc.append(e['id'])
            for w in wit:
                W = s.people[w]
                rep = W.office in DISC or rnd(s.seed, 'report', e['id'], w) < clamp(
                    0.15 + 0.6 * W.R / 100 - 0.004 * s.opinion(w, i), 0.02, 0.98)
                s.stat['wit'] += 1; s.stat['wit_rep'] += rep
                if rep: W.pending.append(e['id'])
        if slot in (0, 1) and patroller is not None:                         # 巡夜查寮：空铺记名
            for j, x in dec.items():
                q = s.people[j]
                if q.dorm in seen and x[0] != q.dorm and x[2] not in ('值守', '强制') and j not in s.sight:
                    s.sight.add(j); s.ev('夜不在寮', j, q.dorm, [patroller], day, slot); s.stat['empty_bed'] += 1
                    s.think(q, -3, 3, '受训诫', day)
        g = s.script.get('gossip')
        if g and g[0] == day and slot == 1:
            e = s.ev('偷食', g[1], 'kit', [g[2]], day, slot, why='脚本：只有一人撞见且不举报'); s.track = e['id']; s.heard.add(g[2])
        if slot == 2 and s.undisc:                                           # 典座清点
            staff = [j for j, x in dec.items() if x[0] == 'kit' and x[1] == 'work']
            for eid in s.undisc:
                if staff and eid not in s.cases and rnd(s.seed, 'disc', eid) < 0.7:
                    s.cases[eid] = {'opened': day, 'acc': set(), 'sus': set(s.sight), 'state': '在查', 'rep': 0}
                    s.ev('失窃', None, 'kit', staff, day, slot, cause=eid); s.stat['discovered'] += 1
            s.undisc = []
        if slot in (3, 9):                                                   # 维那点名
            v = s.by['维那'][0]
            if v in dec and dec[v][0] == 'hall':
                for i, d in dec.items():
                    if d[0] == 'hall' or d[2] in ('强制', '值守', '反应'): continue
                    p = s.people[i]; s.ev('缺课', i, d[0], [v], day, slot, why=d[3]); s.stat['absence'] += 1
                    s.think(p, -4, 5, '受训诫', day); p.absent.append(day)
                    if sum(1 for x in p.absent if x > day - 10) >= 3:
                        p.absent = []; p.kneel = day + 2; s.think(p, -8, 3, '受处分', day); s.stat['san_缺课跪香'] += 1
            s.stat['due'] += sum(1 for d in dec.values() if d[2] not in ('强制', '值守', '反应'))
            s.stat['came'] += sum(1 for d in dec.values() if d[0] == 'hall')
        if slot == 5:                                                        # 怠工被巡寮撞见
            for i, d in dec.items():
                if d[2] != '怠工': continue
                s.stat['slack'] += 1
                if patroller is not None and d[0] in seen:
                    p = s.people[i]; s.ev('怠工', i, d[0], [patroller], day, slot); s.stat['slack_seen'] += 1
                    s.think(p, -3, 3, '受训诫', day); p.slackd.append(day)
                    if sum(1 for x in p.slackd if x > day - 10) >= 3: p.slackd = []; p.kneel = day + 1
        offs = {}
        for j, x in dec.items():
            if s.people[j].office in DISC and x[1] != 'sleep' and x[2] != '强制': offs.setdefault(x[0], j)
        for i, d in dec.items():                                             # 举报送达：到戒律院，或当面禀告任何一位纪律执事
            p = s.people[i]
            if not p.pending: continue
            if d[1] != 'report' and not (d[0] in offs and offs[d[0]] != i and d[1] != 'sleep') and p.office not in DISC: continue
            s.stat['rep_face'] += d[1] != 'report'
            for eid in p.pending:
                c = s.cases.setdefault(eid, {'opened': day, 'acc': set(), 'sus': set(), 'state': '在查', 'rep': 0})
                c['acc'].add(i); c['rep'] = c['rep'] or day
                s.ev('举报', i, 'court', [], day, slot, cause=eid); s.stat['report'] += 1
            p.pending = []
        if slot == 5:                                                        # 裁断
            judge = next((j for j in s.by['首座'] + s.by['执事'] if j in dec and dec[j][0] == 'court'
                          and dec[j][1] == 'work'), None)
            if judge is None: s.stat['no_judge'] += 1
            else:
                for eid, c in s.cases.items():
                    if c['state'] != '在查': continue
                    if c['acc'] and c['rep'] < day: s.sanction(eid, c, day)
                    elif not c['acc'] and c['sus'] and not c.get('asked'):          # 传讯当夜不在寮的人
                        c['asked'] = True; o = s.people[s.events[eid]['actor']]; s.stat['asked'] += len(c['sus'])
                        if o.id in c['sus'] and o.gone is None and rnd(s.seed, 'confess', eid) < 0.25 + 0.5 * o.R / 100:
                            s.stat['confess'] += 1; s.sanction(eid, c, day)
                    elif not c['acc'] and day - c['opened'] > 10: c['state'] = '悬案'
        if slot == 6 and s.announce:                                         # 午斋后表堂
            wit = [j for j, x in dec.items() if x[0] == 'ref']
            for eid, offid, txt in s.announce:
                s.ev('处分', offid, 'ref', wit, day, slot, cause=eid, txt=txt)
                for w in wit:
                    if w != offid and s.people[w].S > 60: s.add_mod(w, offid, -5, 30, '犯戒', 2, day)
            s.announce = []

    def step_day(s, day):
        live = [p for p in s.people if p.gone is None]
        for p in live:
            if p.ill < day and p.conf < day and rnd(s.seed, 'ill', day, p.id) < 0.004:
                p.ill = day + 1 + int(rnd(s.seed, 'illd', day, p.id) * 3); s.stat['ill'] += 1
        sc = s.script.get('ill')
        if sc and sc[0] == day:
            for i in sc[1]: s.people[i].ill = day + sc[2] - 1
        kit = [p for p in live if p.office in KITCHEN and p.ill < day and p.conf < day]
        if s.acting and len(kit) < 4:                                        # 监院派人代理（v0.2 的“指派”一级）
            gs = s.guards(day)
            cand = sorted((p for p in live if p.office is None and p.ill < day and p.conf < day and p.id not in gs),
                          key=lambda p: (-p.D, p.id))
            for p in cand[:4 - len(kit)]: p.duty_day = day; s.stat['acting'] += 1
        s.jobs = [[1, '挑水', 'well', 4, []], [2, '打柴', 'woods', 6, []], [3, '舂米', 'mill', 4, []],
                  [4, '菜园帮工', 'garden', 6, []], [5, '洒扫', 'hall', 2, []], [5, '洒扫', 'zen', 2, []],
                  [5, '洒扫', 'clo', 2, []], [5, '洒扫', 'dorm1', 3, []]]
        s.sight = set()
        for slot in range(12): s.step_slot(day, slot)
        lows = 0
        for p in s.people:
            if p.gone is not None: continue
            p.thoughts = [t for t in p.thoughts if t[1] > day]
            for e in list(p.news):
                p.news[e][0] -= NEWS_DECAY
                if p.news[e][0] <= 0: del p.news[e]
            if len(p.news) > 16:
                for e in sorted(p.news, key=lambda e: p.news[e][0])[:len(p.news) - 16]: del p.news[e]
            lows += s.mood(p) < 35; s.pd += 1
        s.moodlow += lows
        for k in list(s.mods):
            L = [m for m in s.mods[k] if m[1] > day]
            if L: s.mods[k] = L
            else: del s.mods[k]
        if s.track is not None:
            a = s.events[s.track]['actor']
            s.curve.append((day, sum(1 for p in s.people if s.track in p.news and p.id != a)))
            s.cum.append((day, len(s.heard)))
        s.daily.append((day, s.stat['theft'], s.stat['half_meal'], s.stat['hungry']))

    def run(s):
        t0 = time.perf_counter()
        for day in range(1, s.days + 1): s.step_day(day)
        s.elapsed = time.perf_counter() - t0
        for e in s.events: s.h.update(('%s,%s,%d,%d;' % (e['kind'], e['actor'], e['day'], e['slot'])).encode())
        s.hash = s.h.hexdigest()[:16]
        return s

    # ---------- 汇总 ----------
    def friends(s):
        fr = []; foe = 0
        ids = [p.id for p in s.people if p.gone is None]
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = ids[x], ids[y]; o1, o2 = s.opinion(a, b), s.opinion(b, a)
                if o1 >= 25 and o2 >= 25: fr.append((a, b))
                if o1 <= -15 and o2 <= -15: foe += 1
        return fr, foe

    def agree(s, a, b):
        A, B = s.places[a], s.places[b]; m = min(len(A), len(B))
        return sum(1 for i in range(m) if A[i] == B[i]) / m

    def summary(s):
        st = s.stat; fr, foe = s.friends()
        same = sum(1 for a, b in fr if s.people[a].dorm == s.people[b].dorm or s.people[a].track == s.people[b].track
                   or (s.people[a].office and s.people[a].office == s.people[b].office))
        cs = Counter(c['state'] for c in s.cases.values())
        return {'hash': s.hash, 'us': s.elapsed / max(1, st['ps']) * 1e6, 'attend': st['came'] / max(1, st['due']),
                'hungry': st['hungry'] / st['ps'], 'tired': st['tired'] / st['ps'], 'theft': st['theft'],
                'seen': st['theft_seen'], 'wit': st['wit'], 'wit_rep': st['wit_rep'], 'report': st['report'],
                'disc': st['discovered'], 'cases': dict(cs), 'sanction': st['sanction'], 'absence': st['absence'],
                'slack': st['slack'], 'slack_seen': st['slack_seen'], 'half': st['half_meal'], 'meals': st['meals'],
                'jobs': (st['job_done'], st['job_post']), 'chat': st['chat'], 'good': st['chat_good'] / max(1, st['chat']),
                'shared': st['shared'], 'friends': len(fr), 'friend_same': same, 'foes': foe, 'ill': st['ill'],
                'acting': st['acting'], 'full': st['full'], 'viol': len(s.viol), 'moodlow': s.moodlow / max(1, s.pd),
                'gone': sum(1 for p in s.people if p.gone is not None)}


def line(tag, m):
    print('%-14s 到课%.3f 饥%.4f 困%.4f 偷食%d(被见%d) 举报%d 处分%d 案%s 缺课%d 怠工%d/%d 半餐%d/%d 好友%d 不睦%d 低落%.3f 迁单%d %s'
          % (tag, m['attend'], m['hungry'], m['tired'], m['theft'], m['seen'], m['report'], m['sanction'], m['cases'],
             m['absence'], m['slack_seen'], m['slack'], m['half'], m['meals'], m['friends'], m['foes'], m['moodlow'],
             m['gone'], m['hash']))


def main():
    g = World().common
    script = {'gossip': (6, g[8].id, g[9].id)}
    w = World(script=script).run(); m = w.summary()
    print('== 基准：60 僧 × 30 日 × 12 时辰 =='); line('基准', m)
    print('决策数 %d  每次 %.1f 微秒  总耗时 %.2f 秒' % (w.stat['ps'], m['us'], w.elapsed))
    print('预约越界 %d 次；设施满员改选 %d 次；闲谈 %d 次（投机 %.2f）；传话 %d 次' % (m['viol'], m['full'], m['chat'], m['good'], m['shared']))
    print('差事 完成/发布 = %d/%d；代理帮厨 %d 人次；生病 %d 起' % (m['jobs'][0], m['jobs'][1], m['acting'], m['ill']))
    print('过堂人数：实到/应到 = %d/%d（偏差 %.2f%%）' % (sum(w.att.values()), sum(w.att_exp.values()),
          100 * abs(sum(w.att.values()) - sum(w.att_exp.values())) / sum(w.att_exp.values())))
    print('行为包占比：' + '  '.join('%s %.1f%%' % (k[4:], 100 * v / w.stat['ps']) for k, v in sorted(w.stat.items()) if k.startswith('pkg_')))
    for grp in ('清众', '执事'):
        tot = sum(w.acts[grp].values())
        print('%s 每日时辰分配：' % grp + '  '.join('%s %.2f' % (k, 12 * v / tot) for k, v in w.acts[grp].most_common()))
    w2 = World(script=script).run(); w3 = World(script=script, observer='clo').run()
    print('确定性：重跑哈希 %s；观察者在廊下 %s（多生成 %d 条细节叙述）' % (w2.hash == w.hash, w3.hash == w.hash, w3.narr))
    cm = [p.id for p in w.common if p.gone is None]
    same = [w.agree(a, b) for a in cm for b in cm if a < b and w.people[a].track == w.people[b].track]
    diff = [w.agree(a, b) for a in cm for b in cm if a < b and w.people[a].track != w.people[b].track]
    print('个体差异：同修行方向两人整月同处一地 %.3f；不同方向 %.3f；完全相同的月轨迹 %d 对'
          % (sum(same) / len(same), sum(diff) / len(diff), sum(1 for x in same + diff if x == 1.0)))
    fr, foe = w.friends()
    print('好友 %d 对，其中同寮/同方向/同岗 %d 对；不睦 %d 对' % (len(fr), m['friend_same'], foe))
    print('自由时段的选择：' + '  '.join('%s %d' % kv for kv in w.choice.most_common()))
    print('月末需求均值：' + '  '.join('%s %.0f' % (nm, sum(p.need[k] for p in w.people if p.gone is None) / sum(1 for p in w.people if p.gone is None)) for k, nm in zip('hecsa', ('饥', '困', '洁', '群', '志'))))
    print('查寮空铺 %d 次；传讯 %d 人次，认错 %d 起；当面禀告 %d 次' % (w.stat['empty_bed'], w.stat['asked'], w.stat['confess'], w.stat['rep_face']))
    print('传闻实验（第 6 日丑时，一人撞见、不举报）：仍记得的人数按日 =', [c for d, c in w.curve])
    print('  累计听说过的人数按日 =', [c for d, c in w.cum])
    print('  经手层数分布：', dict(sorted(w.hops.items())), ' 月末仍知情 %d 人' % w.curve[-1][1])
    for i, tr in w.traces.items():
        p = w.people[i]
        print('—— 第 %d 日 %s（%s，精进%.0f 守戒%.0f 合群%.0f 馋%.0f）' % (w.trace_day, p.name, p.office or p.track + '僧', p.D, p.S, p.G, p.T))
        print('   ' + ' | '.join('%s %s·%s[%s]' % t for t in tr))
    gl = w.people[w.glutton]
    print('—— 惯犯 %s 的因果链：' % gl.name)
    for e in w.events:
        if e['kind'] in ('偷食', '处分') and e['actor'] == gl.id or (e['kind'] in ('举报', '失窃') and e['cause'] is not None
                                                             and w.events[e['cause']]['actor'] == gl.id):
            print('   #%d 第%d日%s %s %s 见证%d人 %s' % (e['id'], e['day'], SLOTS[e['slot']], e['kind'],
                  ('←#%d' % e['cause']) if e['cause'] is not None else '', len(e['wit']), e['data'].get('txt', e['data'].get('why', ''))))
    if '--all' not in sys.argv: return
    kit = w.by['典座'] + w.by['饭头'][:3]
    print('== 实验 N1：第 10 日起典座与三名饭头同时病倒 4 日 ==')
    for tag, act in (('无人代理', False), ('监院派人代理', True)):
        x = World(script={'ill': (10, kit, 4)}, acting=act).run(); line(tag, x.summary())
        print('   逐日偷食累计（第9–16日）：', [t for d, t, h, hu in x.daily if 9 <= d <= 16])
    print('== 90 日与多种子 ==')
    x = World(days=90).run(); mx = x.summary(); line('90日', mx); print('   每次决策 %.1f 微秒' % mx['us'])
    for sd in (1, 2, 3, 4, 5):
        line('种子%d' % sd, World(seed=sd).run().summary())


if __name__ == '__main__':
    main()
