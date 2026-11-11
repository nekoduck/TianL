"""十层行为包栈（计划 6.1，做法取自《上古卷轴 V》的 Package Stack）：每人每个时辰只回答“我现在做什么”，
答案来自一摞按优先级排好的包，自上而下第一个成立的生效。返回 (场所, 活动, 层, 原因)；
巡寮者多带第五项：这一时辰巡到的场所集合（见证与查寮要用）。

实际判定次序（与计划表的层号对应见 SiteSpec.layer_rank，说明见 docs/NPC_ENGINE.md 第 5 节）：
  强制（卧病、禁闭）→ 处分（罚跪香）→ 反应（去戒律院举报）→ 值守（厨务、代理帮厨、巡夜巡寮、山门）
  → 生理（昏沉不支、饿极偷食）→ 夜间（就寝；夜里偷食是越轨）→ 晨起（贪睡是越轨；困乏未起）
  → 集体 → 岗位 → 身份（清众：差事、功课；怠工是越轨）→ 午后偷食（越轨）→ 自由。
越轨不是一层包：它是性格加需求让人跳过本该生效的包（计划 6.1 补充规则）。
所有常数在 SiteSpec；这里只有判定的先后。
"""
from ..core import cal
from .spec import (A_CONFINED, A_GUARD, A_KNEEL, A_MEAL, A_PATROL, A_REPORT, A_SICK, A_SLEEP, A_STEAL, A_WORK,
                   L_DEVIANT, L_DUTY, L_FORCED, L_FREE, L_GROUP, L_IDENT, L_PENALTY, L_PHYS, L_POST, L_REACT,
                   L_ROUTINE, L_SLACK)


class Stack:
    def __init__(self, eng):
        self.eng = eng
        self.sp = eng.spec

    # ---------- 值守（第 4/5 层：此刻轮到的要紧岗位；监院派来的代理也算）----------
    def duty(self, p, day, slot):
        eng, sp = self.eng, self.sp
        kt = sp.kitchen
        kit_post = p.office in sp.kitchen_offices
        if (kit_post or p.duty_day == day) and slot in kt.slots:
            return (kt.place, A_WORK, L_DUTY, kt.label_staff if kit_post else kt.label_proxy)
        pt = sp.patrol
        if p.office == pt.office:
            night = eng.night_patroller(day) == p.ix
            if (night and slot in pt.night_slots) or (not night and slot in pt.day_slots):
                r, seed = eng.rng, eng.seed
                ks = sorted(pt.pool, key=lambda x: r(seed, 'roam', day, slot, x))[:pt.pick]
                return (ks[0], A_PATROL, L_DUTY, pt.labels[0] if night else pt.labels[1], set(ks))
            if night and slot in pt.rest_slots:
                return (p.dorm, A_SLEEP, L_DUTY, pt.rest_label)
        g = sp.gate
        if slot in g.slots and p.ix in eng.guards(day):
            return (g.place, A_GUARD, L_DUTY, g.label)
        return None

    # ---------- 越轨起念：性格改门槛，不改生理常数 ----------
    def tempted(self, p, day, slot):
        tm = self.sp.temptation
        h = p.need['h']
        th = tm.th_base + (p.T - tm.t_mid) * tm.t_slope      # 越馋，越早起念
        if h >= th or p.S >= tm.s_line:
            return False
        pr = (tm.s_line - p.S) / tm.s_line * (th - h) / th * tm.k
        eng = self.eng
        return eng.rng(eng.seed, 'tempt', day, slot, p.ix) < min(tm.p_cap, pr)

    def decide(self, p, day, slot, ctx):
        eng, sp = self.eng, self.sp
        n = p.need
        meal = sp.meal_slots
        kit = sp.kitchen.place
        # 1 强制
        if p.ill >= day:
            fo = sp.forced
            if slot in sp.night or slot in fo.sleep_extra_slots:
                return (fo.ill_place, A_SLEEP, L_FORCED, fo.ill_sleep)
            return (fo.ill_place, A_MEAL, L_FORCED, fo.ill_meal) if slot in meal else \
                (fo.ill_place, A_SICK, L_FORCED, fo.ill_other)
        if p.conf >= day:
            fo = sp.forced
            if slot in sp.night or slot in fo.sleep_extra_slots:
                return (fo.conf_place, A_SLEEP, L_FORCED, fo.conf_sleep)
            return (fo.conf_place, A_MEAL, L_FORCED, fo.conf_meal) if slot in meal else \
                (fo.conf_place, A_CONFINED, L_FORCED, fo.conf_other)
        # 2 处分
        pe = sp.penalty
        if p.kneel >= day and slot == pe.kneel_slot:
            return (pe.place, A_KNEEL, L_PENALTY, pe.label)
        # 3 反应（值守者除僧值外没空举报，所以送达另有“当面禀告”）
        d = self.duty(p, day, slot)
        ct = sp.court
        if p.pending and slot in ct.report_slots and (d is None or p.office == sp.patrol.office) \
                and eng.court_open(day):
            return (ct.place, A_REPORT, L_REACT, ct.report_label)
        # 4/5 值守（指派并入此层）
        if d:
            return d
        # 6 生理紧急
        ph = sp.phys
        if n['e'] < ph.faint_e and slot not in meal:
            return (p.dorm, A_SLEEP, L_PHYS, ph.faint_label)
        if n['h'] < ph.starve_h and slot not in meal and slot not in sp.night:
            if p.S < ph.starve_s:
                return (kit, A_STEAL, L_PHYS, ph.starve_label)
            eng.moods.think(p, ph.endure_thought, day)
        tm = sp.temptation
        # 夜间：就寝，守戒低且馋的人起念偷食（越轨）
        if slot in sp.night:
            if slot == tm.night_slot and self.tempted(p, day, slot):
                return (kit, A_STEAL, L_DEVIANT, tm.night_label)
            return (p.dorm, A_SLEEP, L_ROUTINE, sp.night_label)
        # 晨起：精进低的人贪睡（越轨）
        lz = sp.lazy
        if slot in lz.wake_slots:
            if slot == lz.roll_slot and p.D < lz.d_line and \
                    eng.rng(eng.seed, 'lazy', day, p.ix) < (lz.d_line - p.D) / lz.d_div:
                p.lazy_day = day
            if p.lazy_day == day:
                return (p.dorm, A_SLEEP, L_DEVIANT, lz.label)
            if n['e'] < lz.tired_e:
                return (p.dorm, A_SLEEP, L_PHYS, lz.tired_label)
        # 7 集体
        up = sp.uposatha
        if slot == up.slot and (day if up.by == 'day' else cal(day)['dom']) in up.days:
            return (up.what.place, up.what.act, L_GROUP, up.what.label)
        g = sp.group.get(slot)
        if g:
            return (g.place, g.act, L_GROUP, g.label)
        # 8 岗位
        o = p.office
        ps = sp.post_slots.get(o)
        if ps and slot in ps[1]:
            return (ps[0], A_WORK, L_POST, o + sp.post_suffix)
        # 9 身份
        if o is None:
            cm = sp.common
            if slot == cm.work_slot:
                sk = sp.slack
                sl = max(0.0, (sk.d_line - p.D) / sk.d_div) + (sk.low_mood_add if eng.moods.is_low(p) else 0)
                if eng.rng(eng.seed, 'slack', day, p.ix) < sl:
                    return eng.free.choose(p, day, slot, L_SLACK, ctx)
                job = eng.jobs.claim(p.ix)
                if job:
                    return job
            if slot == cm.class_slot:
                c = cm.classes[p.track]
                if eng.fac.has_room(ctx.occ, c.place):
                    eng.fac.take(ctx.occ, c.place)
                    return (c.place, c.act, L_IDENT, c.label)
                eng.stat['full'] += 1
                return (cm.overflow_place, c.act, L_IDENT, c.label + cm.overflow_suffix)
        if slot == tm.after_slot and self.tempted(p, day, slot):
            return (kit, A_STEAL, L_DEVIANT, tm.after_label)
        # 10 自由
        return eng.free.choose(p, day, slot, L_FREE, ctx)
