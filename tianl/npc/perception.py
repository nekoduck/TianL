"""感知（计划 8.1，照《哥特》的 perceptions）：事件发生时，把它交给每个见证人的处理函数。
消息只从目击者出发；规矩只对被看见、被举报的事起作用。全知的 NPC 不像人。

| 事件类 | 谁能感知 | 处理 |
| 眼前的越轨 | 同一场所、醒着的人，加上恰好巡到的人 | 记入见闻（事件的显著度）；norms 决定是否举报 |
| 缺席 | 负责点名的岗位 | 维那在早晚课点名，记缺课 |
| 空铺 | 巡夜查到的寮房 | 记“夜不在寮”，列入当夜嫌疑 |
| 少了东西 | 负责清点的岗位 | 典座晨起清点，发现失窃，立案 |
| 怠工 | 巡寮者所到之处 | 记怠工 |
见闻本身由 NpcEngine.emit 按事件的显著度（SiteSpec.salience）写进每个见证人的 news。
"""
from .events import ABSENCE, BED_EMPTY, FOOD_THEFT, SLACK, THEFT_FOUND
from .model import Case
from .spec import A_SLEEP, A_STEAL, A_WORK, L_SLACK


class Perception:
    def __init__(self, eng):
        self.eng = eng
        self.undisc = []                    # 还没被清点发现的偷食事件 id

    # ---------- 偷食 → 见证 → 是否举报 ----------
    def thefts(self, ctx, day, slot):
        eng = self.eng
        dec = ctx.dec
        kit = eng.spec.kitchen.place
        for i, d in dec.items():
            if d[1] != A_STEAL:
                continue
            wit = [j for j, x in dec.items() if x[0] == kit and j != i and x[1] != A_SLEEP]
            pt = ctx.patroller
            if pt is not None and kit in ctx.seen and pt != i and pt not in wit:
                wit.append(pt)
            e = eng.emit(FOOD_THEFT, i, kit, wit, day, slot, why=d[3])
            eng.stat['theft'] += 1
            eng.stat['theft_seen'] += bool(wit)
            self.undisc.append(e.id)
            for w in wit:
                eng.norms.witness_decides(e, w, i)

    # ---------- 巡夜查寮：空铺记名 ----------
    def bed_check(self, ctx, day, slot):
        eng = self.eng
        pt = eng.spec.patrol
        if slot not in pt.bed_check_slots or ctx.patroller is None:
            return
        for j, x in ctx.dec.items():
            q = eng.people[j]
            if q.dorm in ctx.seen and x[0] != q.dorm and x[2] not in pt.bed_exempt_layers and j not in eng.sight:
                eng.sight.add(j)
                eng.emit(BED_EMPTY, j, q.dorm, [ctx.patroller], day, slot)
                eng.stat['empty_bed'] += 1
                eng.moods.think(q, pt.bed_thought, day)

    # ---------- 典座清点：发现失窃即立案 ----------
    def inventory(self, ctx, day, slot):
        eng = self.eng
        iv = eng.spec.inventory
        if slot != iv.slot or not self.undisc:
            return
        kt = eng.spec.kitchen
        staff = [j for j, x in ctx.dec.items() if x[0] == kt.place and x[1] == A_WORK]
        for eid in self.undisc:
            if staff and eid not in eng.norms.cases and eng.rng(eng.seed, 'disc', eid) < iv.p_find:
                eng.norms.cases[eid] = Case(eid, day, eng.sight, eng.spec.cases.open)
                eng.emit(THEFT_FOUND, None, kt.place, staff, day, slot, cause=eid)
                eng.stat['discovered'] += 1
        self.undisc = []

    # ---------- 维那点名：记缺课 ----------
    def roll_call(self, ctx, day, slot):
        eng = self.eng
        rc = eng.spec.rollcall
        if slot not in rc.slots:
            return
        dec = ctx.dec
        L = eng.by.get(rc.office)
        v = L[0] if L else None                 # 点名的人（维那）；岗位空缺时今日不点名
        if v is not None and v in dec and dec[v][0] == rc.place:
            for i, d in dec.items():
                if d[0] == rc.place or d[2] in rc.exempt_layers:
                    continue
                p = eng.people[i]
                eng.emit(ABSENCE, i, d[0], [v], day, slot, why=d[3])
                eng.stat['absence'] += 1
                eng.moods.think(p, rc.absent_thought, day)
                p.absent.append(day)
                if sum(1 for x in p.absent if x > day - rc.window) >= rc.limit:
                    p.absent = []
                    p.kneel = day + rc.kneel_days
                    eng.moods.think(p, rc.kneel_thought, day)
                    eng.stat['san_' + rc.kneel_txt] += 1
        eng.stat['due'] += sum(1 for d in dec.values() if d[2] not in rc.exempt_layers)
        eng.stat['came'] += sum(1 for d in dec.values() if d[0] == rc.place)

    # ---------- 怠工被巡寮撞见 ----------
    def slackers(self, ctx, day, slot):
        eng = self.eng
        if slot != eng.spec.common.work_slot:
            return
        sk = eng.spec.slack
        for i, d in ctx.dec.items():
            if d[2] != L_SLACK:
                continue
            eng.stat['slack'] += 1
            if ctx.patroller is not None and d[0] in ctx.seen:
                p = eng.people[i]
                eng.emit(SLACK, i, d[0], [ctx.patroller], day, slot)
                eng.stat['slack_seen'] += 1
                eng.moods.think(p, sk.thought, day)
                p.slackd.append(day)
                if sum(1 for x in p.slackd if x > day - sk.window) >= sk.limit:
                    p.slackd = []
                    p.kneel = day + sk.kneel_days
