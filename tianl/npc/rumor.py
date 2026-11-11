"""闲谈与传闻（计划 8.3，结构取自 Minecraft 的 gossip；源头取自《矮人要塞》：只有目击者能起头）。

* 闲谈配对：想闲谈的人按随机序排队，队首挑“好恶 + 噪声”最大的；落单的改散步。
* 一次闲谈：改好恶（投机/不投机）；双方各转述一条（挑对方不知道的里面最强的）；
  每条见闻有强度，转述时减弱，低于下限不再外传；对当事人本人不说。
* 见闻是指向事件的指针 [强度, 经手层数, 来源 ix]，每人最多留 keep 条，弱的先忘。
* 追踪（传闻实验）：Rumor.track(eid, heard) 追踪一条事件，每日记“仍记得的人数”“累计听说过的人数”和经手层数分布。
传闻速度由闲谈次数决定，闲谈次数又由“群”的收支决定——传闻参数要和需求一起校准（计划 8.3 末段）。
"""
from collections import Counter

from ..core import clamp
from .model import PAIR
from .spec import A_CHAT, A_STROLL, SCALE


class Rumor:
    def __init__(self, eng):
        self.eng = eng
        self.sp = eng.spec.rumor
        self.track_eid = None
        self.heard = set()
        self.hops = Counter()
        self.curve = []                     # (日, 仍记得的人数)
        self.cum = []                       # (日, 累计听说过的人数)

    def track(self, eid, heard):
        self.track_eid = eid
        self.heard.update(heard)

    # ---------- 转述 ----------
    def share(self, A, B, day, slot):
        eng, sp = self.eng, self.sp
        best = None
        for e, v in A.news.items():
            if v[0] < sp.min_strength or eng.ev_by_id[e].actor == B.ix:
                continue
            cur = B.news.get(e)
            if cur and cur[0] >= v[0] - sp.penalty:
                continue
            if best is None or v[0] > best[1]:
                best = (e, v[0], v[1])
        if not best:
            return
        e, st, hop = best
        if eng.rng(eng.seed, 'share', day, slot, A.ix, B.ix, e) < min(sp.p_cap, st / SCALE + sp.p_add) \
                * (sp.g_off + A.G / sp.g_div):
            if e == self.track_eid and B.ix not in self.heard:
                self.hops[hop + 1] += 1
                self.heard.add(B.ix)
            B.news[e] = [st - sp.penalty, hop + 1, A.ix]
            eng.stat['shared'] += 1

    # ---------- 一次闲谈 ----------
    def chat(self, a, b, day, slot, full):
        eng = self.eng
        ch = eng.spec.chat
        A, B = eng.people[a], eng.people[b]
        op, mood = eng.opinions, eng.moods
        good = eng.rng(eng.seed, 'chat', day, slot, a, b) < ch.good_base + (op.compat(a, b) - ch.good_mid) * ch.good_w
        if good:
            op.add_mod(a, b, ch.good_mod, day)
            op.add_mod(b, a, ch.good_mod, day)
            if full:
                mood.think(A, ch.good_thought, day)
                mood.think(B, ch.good_thought, day)
        else:
            op.add_mod(a, b, ch.bad_mod, day)
            op.add_mod(b, a, ch.bad_mod, day)
        if not full:
            A.need['s'] = clamp(A.need['s'] + ch.gain_when_brief)
            B.need['s'] = clamp(B.need['s'] + ch.gain_when_brief)
        eng.stat['chat'] += 1
        eng.stat['chat_good'] += good
        self.share(A, B, day, slot)
        self.share(B, A, day, slot)

    # ---------- 闲谈配对 ----------
    def pair(self, ctx, day, slot):
        eng = self.eng
        ch = eng.spec.chat
        dec, r, seed, op = ctx.dec, eng.rng, eng.seed, eng.opinions
        L = sorted((i for i, d in dec.items() if d[1] == A_CHAT), key=lambda i: r(seed, 'cq', day, slot, i))
        while len(L) >= PAIR:
            a = L.pop(0)
            b = max(L, key=lambda j: op.opinion(a, j) + ch.pair_noise * r(seed, 'pair', day, slot, a, j))
            L.remove(b)
            self.chat(a, b, day, slot, True)
        for a in L:
            dec[a] = (dec[a][0], A_STROLL, dec[a][2], ch.lone_label)

    # ---------- 每日衰减 ----------
    def decay(self, p):
        sp = self.sp
        news = p.news
        for e in list(news):
            news[e][0] -= sp.decay
            if news[e][0] <= 0:
                del news[e]
        if len(news) > sp.keep:
            for e in sorted(news, key=lambda e: news[e][0])[:len(news) - sp.keep]:
                del news[e]

    def end_day(self, day):
        if self.track_eid is not None:
            a = self.eng.ev_by_id[self.track_eid].actor
            tid = self.track_eid
            self.curve.append((day, sum(1 for p in self.eng.people if tid in p.news and p.ix != a)))
            self.cum.append((day, len(self.heard)))
