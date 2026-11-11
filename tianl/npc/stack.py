"""行为包栈（计划 6.1，做法取自《上古卷轴 V》的 Package Stack）：每人每个时辰只回答“我现在做什么”，
答案来自一摞按次序排好的包，自上而下第一个成立的生效。返回 (场所, 活动, 层, 原因)；
巡寮者多带第五项：这一时辰巡到的场所集合（见证与查寮要用）。

包的次序、谁适用、何时成立、做什么，全是数据（SiteSpec.stack，来自 defs 的 package 与 rule:stack）；这里只有机制：
  * 声明式的包（只有 do）：谁（who）、何时（when）都对上，就给出 (do.place, do.act, 层, do.label)；claim 的占工位、满员改去 overflow。
    栈里相邻的、层相同的声明式包合成一组，组内按 when 的具体程度匹配（先具体日子，再天气，再季节，最后默认；同级按栈里的次序）。
  * 处理器包（handler + params）：交给 handlers.PACKAGE_HANDLERS 里登记的函数，返回决定或 None（不成立，往下判）。
  * 值守层的包（layer = 值守）相邻成一段：反应包要先问“此刻有没有值守”（duty()，带记忆：同一个人同一时辰只算一次）。
越轨不是一层包：它是性格加需求让人跳过本该生效的包（计划 6.1 补充规则）。
为了快，(岗位, 方向, 时辰) 相同的人共用一份“适用的包”清单（只留 who 与 when.slot 都对得上的），运行时再查日历条件。
"""
from ..core import cal
from .handlers import PACKAGE_HANDLERS
from .spec import L_DUTY, OWN_BED, STATUS_COMMON, STATUS_HOLDER


def applies(pk, office, track, slot, periods):
    """包 pk 对（岗位, 方向）的人在这个时辰是否可能成立（只看 who 与 when 的 slot / period；日历条件运行时再查）。
    periods 是 SiteSpec.period_slots（时段名 -> 时辰）。"""
    w = pk.who
    if w.offices is not None and office not in w.offices:
        return False
    if w.status == STATUS_COMMON and office is not None:
        return False
    if w.status == STATUS_HOLDER and office is None:
        return False
    if w.tracks is not None and track not in w.tracks:
        return False
    s = pk.when.slots
    if s is not None and slot not in s:
        return False
    per = pk.when.periods
    return per is None or any(slot in periods[name] for name in per)


def calendar_ok(w, k):
    """when 里的日历条件对不对得上当日的日历键 k（stack.calendar_keys 给）。"""
    if w.days is not None and k['day'] not in w.days:
        return False
    if w.doms is not None and k['dom'] not in w.doms:
        return False
    if w.months is not None and k['month'] not in w.months:
        return False
    if w.festivals is not None:
        f = k['festival']
        if f is None or (w.festivals is not True and f not in w.festivals):
            return False
    if w.weathers is not None and k['weather'] not in w.weathers:
        return False
    if w.seasons is not None and k['season'] not in w.seasons:
        return False
    return True


class _HandlerStep:
    __slots__ = ('pkg', 'fn', 'cal')

    def __init__(self, pkg):
        self.pkg, self.fn, self.cal = pkg, PACKAGE_HANDLERS[pkg.handler].fn, pkg.when.has_calendar

    def run(self, st, p, day, slot, ctx):
        if self.cal and not calendar_ok(self.pkg.when, st.keys(day)):
            return None
        return self.fn(st, self.pkg, p, day, slot, ctx)


class _GroupStep:
    """一组相邻、同层的声明式包：成员已按 when 的具体程度排好。"""
    __slots__ = ('members',)

    def __init__(self, members):
        self.members = tuple(members)

    def run(self, st, p, day, slot, ctx):
        k = None
        for pk in self.members:
            if pk.when.has_calendar:
                if k is None:
                    k = st.keys(day)
                if not calendar_ok(pk.when, k):
                    continue
            return _do(st, pk, p, ctx)
        return None


def _do(st, pk, p, ctx):
    do = pk.do
    place = p.dorm if do.place == OWN_BED else do.place
    if do.claim:
        fac = st.eng.fac
        if fac.has_room(ctx.occ, place):
            fac.take(ctx.occ, place)
            return (place, do.act, pk.layer, do.label)
        st.eng.stat['full'] += 1
        return (do.overflow_place, do.act, pk.layer, do.label + do.overflow_suffix)
    return (place, do.act, pk.layer, do.label)


class _DutyStep:
    """值守层的一段包：整段当一个步骤，经 Stack.duty() 求值（带记忆）。"""
    __slots__ = ()

    def run(self, st, p, day, slot, ctx):
        return st.duty(p, day, slot, ctx)


def compile_stack(spec):
    """把 spec.stack 编成步骤原型：[('handler', pkg) | ('group', [pkg…]) | ('duty', [pkg…])]（保持栈里的次序）。"""
    out = []
    for pk in spec.stack:
        if pk.handler is None:
            if out and out[-1][0] == 'group' and out[-1][1][0].layer == pk.layer:
                out[-1][1].append(pk)
            else:
                out.append(('group', [pk]))
        elif pk.layer == L_DUTY:
            if out and out[-1][0] == 'duty':
                out[-1][1].append(pk)
            else:
                out.append(('duty', [pk]))
        else:
            out.append(('handler', pk))
    return out


class Stack:
    def __init__(self, eng):
        self.eng = eng
        self.sp = eng.spec
        self.proto = compile_stack(self.sp)
        self._for = {}                          # (岗位, 方向, 时辰) -> 适用的步骤
        self._duty_for = {}                     # (岗位, 方向, 时辰) -> 适用的值守步骤
        self._dm = None                         # 值守的记忆：(ix, 日, 时辰, 结果)
        self._kday, self._k = None, None        # 日历键的缓存（按日）
        self._season = {m: name for name, months in self.sp.seasons.items() for m in months}
        self.begin_steps = [pk for pk in self.sp.stack
                            if pk.handler is not None and PACKAGE_HANDLERS[pk.handler].begin is not None]

    # ---------- 日历键 ----------
    def keys(self, day):
        """当日的日历键：day dom month festival season weather（weather 由 Host 的 weather(day) 提供，没有就是 None）。"""
        if self._kday != day:
            c = cal(day)
            wf = getattr(self.eng.host, 'weather', None)
            self._k = {'day': day, 'dom': c['dom'], 'month': c['month'], 'festival': c['festival'],
                       'season': self._season.get(c['month']), 'weather': wf(day) if wf else None}
            self._kday = day
        return self._k

    # ---------- 每日开始：处理器的 begin 钩子（监院派人代理……）----------
    def begin_day(self, day):
        for pk in self.begin_steps:
            PACKAGE_HANDLERS[pk.handler].begin(self.eng, pk, day)

    # ---------- 值守 ----------
    def _build_duty(self, office, track, slot):
        out = []
        for kind, x in self.proto:
            if kind == 'duty':
                out.extend(_HandlerStep(pk) for pk in x if applies(pk, office, track, slot, self.sp.period_slots))
        return tuple(out)

    def duty(self, p, day, slot, ctx):
        """此刻轮到的要紧岗位（值守层的包，按栈里的次序取第一个成立的）。同一个人同一时辰只算一次。"""
        m = self._dm
        if m is not None and m[0] == p.ix and m[1] == day and m[2] == slot:
            return m[3]
        key = (p.office, p.track, slot)
        steps = self._duty_for.get(key)
        if steps is None:
            steps = self._duty_for[key] = self._build_duty(*key)
        d = None
        for s in steps:
            d = s.run(self, p, day, slot, ctx)
            if d is not None:
                break
        self._dm = (p.ix, day, slot, d)
        return d

    # ---------- 判定 ----------
    def _build(self, office, track, slot):
        out = []
        for kind, x in self.proto:
            if kind == 'handler':
                if applies(x, office, track, slot, self.sp.period_slots):
                    out.append(_HandlerStep(x))
            elif kind == 'group':
                ms = [pk for pk in x if applies(pk, office, track, slot, self.sp.period_slots)]
                if ms:
                    out.append(_GroupStep(sorted(ms, key=lambda pk: pk.when.specificity)))     # 稳定排序：同级保持栈里的次序
            elif any(applies(pk, office, track, slot, self.sp.period_slots) for pk in x):
                out.append(_DutyStep())
        return tuple(out)

    def decide(self, p, day, slot, ctx):
        key = (p.office, p.track, slot)
        steps = self._for.get(key)
        if steps is None:
            steps = self._for[key] = self._build(*key)
        for s in steps:
            d = s.run(self, p, day, slot, ctx)
            if d is not None:
                return d
        raise LookupError('行为包栈没有给出决定：%s（岗位 %r，方向 %r）第 %d 日 %d 时辰；栈里缺一个兜底的包（free）？'
                          % (p.pid, p.office, p.track, day, slot))
