"""规矩与案件（计划 8.5）：越轨 → 见证 → 是否举报 → 送达 → 立案 → 传讯/认错 → 裁断 → 处分阶梯 → 公告 → 余波。

1. 越轨：需求加性格让某人做了触犯规范的交互（stack/perception）。物理上做得成，规范层打上标记。
2. 见证：同处醒着的人和恰好巡到的人（perception.thefts）。
3. 是否举报：纪律岗位必报；其余人的概率 = base + r_w×刚正 − op_w×对当事人的好感，折到 [lo, hi]（witness_decides）。
4. 送达：见到任何一位纪律执事就当面禀告；见不到，就在巳时或申时去戒律院（deliver）。
5. 无人指认时：典座清点发现失窃即立案（perception.inventory）；巡夜当夜记下的空铺者被传讯，认不认看本人的“刚正”。
6. 裁断：首座（不在则执事）在裁断时辰裁；有人指认或本人认错才定罪，否则过期成悬案（adjudicate）。
7. 处分阶梯：SiteSpec.ladder，第 k 次受处分取第 k 级，超出取最后一级（sanction）。
8. 公告：午斋后表堂，在场者全部得知（announce）。
9. 余波：受罚者对举报人好感大跌；守戒高的旁观者对受罚者记“犯戒”。
每起处分的案卷记 via（举报 / 认错）与指认人，事件 cause 指向原偷食事件：每起处分都能回溯。
"""
from ..core import clamp
from .events import REPORT, SANCTION
from .model import Case
from .spec import A_REPORT, A_SLEEP, A_WORK, L_FORCED, SCALE


class Norms:
    def __init__(self, eng):
        self.eng = eng
        self.cases = {}                     # eid -> Case（插入次序即立案次序）
        self.announce_q = []                # [(eid, 受处分者 ix, 处分文)]

    # ---------- 3 是否举报 ----------
    def witness_decides(self, e, w, i):
        """见证人 w 目睹了 i 的越轨 e：决定要不要报；要报就记入待报（送达时才真正举报）。"""
        eng = self.eng
        rp = eng.spec.report
        W = eng.people[w]
        rep = W.office in eng.spec.disc_offices or eng.rng(eng.seed, 'report', e.id, w) < clamp(
            rp.base + rp.r_w * W.R / SCALE - rp.op_w * eng.opinions.opinion(w, i), rp.lo, rp.hi)
        eng.stat['wit'] += 1
        eng.stat['wit_rep'] += rep
        if rep:
            W.pending.append(e.id)

    # ---------- 4 送达：当面禀告任何一位纪律执事，或到戒律院 ----------
    def deliver(self, ctx, day, slot):
        eng = self.eng
        sp = eng.spec
        dec, disc = ctx.dec, sp.disc_offices
        offs = {}
        for j, x in dec.items():
            if eng.people[j].office in disc and x[1] != A_SLEEP and x[2] != L_FORCED:
                offs.setdefault(x[0], j)
        for i, d in dec.items():
            p = eng.people[i]
            if not p.pending:
                continue
            if d[1] != A_REPORT and not (d[0] in offs and offs[d[0]] != i and d[1] != A_SLEEP) \
                    and p.office not in disc:
                continue
            eng.stat['rep_face'] += d[1] != A_REPORT
            for eid in p.pending:
                c = self.cases.get(eid)
                if c is None:
                    c = self.cases[eid] = Case(eid, day, (), sp.cases.open)
                c.acc.add(i)
                if c.rep is None:
                    c.rep = day
                eng.emit(REPORT, i, sp.court.place, [], day, slot, cause=eid)
                eng.stat['report'] += 1
            p.pending = []

    # ---------- 6 裁断 ----------
    def adjudicate(self, ctx, day, slot):
        eng = self.eng
        sp = eng.spec
        ct, cs = sp.court, sp.cases
        if slot != ct.judge_slot:
            return
        dec = ctx.dec
        judge = next((j for j in eng.court_staff() if j in dec and dec[j][0] == ct.place and dec[j][1] == A_WORK),
                     None)
        if judge is None:
            eng.stat['no_judge'] += 1
            return
        for eid, c in self.cases.items():
            if c.state != cs.open:
                continue
            if c.acc and c.rep < day:
                self.sanction(eid, c, day, cs.via_report)
            elif not c.acc and c.sus and not c.asked:                     # 传讯当夜不在寮的人
                c.asked = True
                o = eng.people[eng.ev_by_id[eid].actor]
                eng.stat['asked'] += len(c.sus)
                if o.ix in c.sus and o.gone is None and \
                        eng.rng(eng.seed, 'confess', eid) < cs.confess_base + cs.confess_r * o.R / SCALE:
                    eng.stat['confess'] += 1
                    self.sanction(eid, c, day, cs.via_confess)
            elif not c.acc and day - c.opened > cs.stale_days:
                c.state = cs.cold

    # ---------- 7 处分阶梯 ----------
    def sanction(self, eid, c, day, via):
        eng = self.eng
        sp = eng.spec
        off = eng.people[eng.ev_by_id[eid].actor]
        if off.gone is not None:
            c.state = sp.cases.closed
            return
        k = off.offences
        off.offences += 1
        st = sp.ladder[min(k, len(sp.ladder) - 1)]
        if st.kneel_days:
            off.kneel = day + st.kneel_days
        if st.conf_days:
            off.conf = day + st.conf_days
        for need, delta in st.need_hit:
            off.need[need] = clamp(off.need[need] + delta)
        if st.thought:
            eng.moods.think(off, st.thought, day)
        if st.gone:
            off.gone, off.gone_why = day, st.txt
        eng.moods.think(off, sp.cases.sanction_thought, day)
        for a in sorted(c.acc):             # 指认人按 ix 升序：原型遍历 set，次序是 CPython 的实现细节（NPC_ENGINE.md 第 9 节第 11 条）
            eng.opinions.add_mod(off.ix, a, sp.cases.accuse_mod, day)
        c.state = sp.cases.done
        c.txt, c.day, c.via = st.txt, day, via
        self.announce_q.append((eid, off.ix, st.txt))
        eng.stat['sanction'] += 1
        eng.stat['san_' + st.txt] += 1

    # ---------- 8/9 公告与余波 ----------
    def announce(self, ctx, day, slot):
        eng = self.eng
        an = eng.spec.announce
        if slot != an.slot or not self.announce_q:
            return
        wit = [j for j, x in ctx.dec.items() if x[0] == an.place]
        for eid, offid, txt in self.announce_q:
            eng.emit(SANCTION, offid, an.place, wit, day, slot, cause=eid, txt=txt)
            for w in wit:
                if w != offid and eng.people[w].S > an.s_line:
                    eng.opinions.add_mod(w, offid, an.mod, day)
        self.announce_q = []
