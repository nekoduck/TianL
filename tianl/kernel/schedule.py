"""作息与位置：作息是函数，例外才是状态。

where(pid, day, slot) 的取值次序：引擎（若接了且它管这个人）> 例外（指派）> 外来香客 > 值守班表 > 作息模板。
值守班表每日结算时为次日落盘，之后不再重算（历史不可改写）。作息模板见 defs 的 rule:<scope>:timetable。
"""
from ..core.calendar import SLOTS, SLOTS_PER_DAY


class ScheduleMixin:
    def person(self, pid):
        if pid not in self.pcache:
            r = self.x('SELECT id,name,gen,hall,home,joined,died,status FROM person WHERE id=?', (pid,)).fetchone()
            self.pcache[pid] = dict(zip(('id', 'name', 'gen', 'hall', 'home', 'joined', 'died', 'status'), r)) if r else None
        return self.pcache[pid]

    def alive_at(self, p, day):
        return p['joined'] <= day and (p['died'] is None or p['died'] >= day) and p['status'] != '游方'

    def make_roster(self, day):
        """值守排班: 每日结算时落盘, 之后不再重算 (历史不可改写)。"""
        o = self.S.org
        el = lambda hall, gen: [r[0] for r in self.x("SELECT id FROM person WHERE status='在寺' AND hall=? AND gen=? ORDER BY id", (hall, gen))]
        posts = [(r.label, r.place, r.slots, r.n, el(r.hall, r.gen)) for r in self.S.roster]
        for post, place, slots, n, e in posts:
            if not e: continue
            for j, slot in enumerate(slots):
                for k in range(min(n, len(e))):
                    self.x('INSERT INTO roster VALUES(?,?,?,?,?)', (day, post, slot, e[(day * o.roster_stride + (j // o.roster_shift) * n + k) % len(e)], place))

    # ------------------------------------------------------------------ 作息模板
    def _when(self, w, ctx):
        for k, v in w.items():
            if k == 'slots':
                if ctx['s'] not in v: return False
            elif k == 'base':
                if ctx['base'] not in v: return False
            elif k == 'site':
                if bool(ctx['site']) != v: return False
            elif k == 'gen':
                if ctx['p']['gen'] not in v: return False
            elif k == 'hall_mapped':
                if (ctx['p']['hall'] in self.S.org.halls) != v: return False
            elif k == 'hall_in':
                if ctx['p']['hall'] not in v: return False
            elif k in ('shuowang', 'retreat'):
                if bool(ctx['c'][k]) != v: return False
            else:
                raise KeyError(f'作息模板：未知条件 {k}')
        return True

    def template(self, p, day, slot):
        office = self.office_of(p['id'], day)
        base = self.base_of(office) if office else None
        ctx = dict(p=p, c=self.cal(day), s=SLOTS[slot], base=base, site=self.S.site_of.get(base))
        for rule in self.S.timetable:
            if not self._when(rule.when, ctx): continue
            for out in rule.out:
                if not self._when(out.when, ctx): continue
                kind, code = out.place
                if kind == 'code': place = code
                elif kind == 'home': place = p['home']
                elif kind == 'site': place = ctx['site']
                else: place = self.S.org.halls.get(p['hall'], code)
                return (place, out.act)
        raise RuntimeError('作息模板没有缺省规则')

    def where_ex(self, pid, day, slot):
        """(场所 code, 活动, 层, 原因)；不在世或游方者返回 None。层：引擎自报，或 指派 / 值守 / 作息。"""
        p = self.person(pid)
        if p is None or not self.alive_at(p, day): return None
        if self.engine is not None:
            r = self.engine.where(pid, day, slot)
            if r is not None: return tuple(r)
        t = day * SLOTS_PER_DAY + slot
        r = self.x('SELECT place, activity FROM assignment WHERE person=? AND t_from<=? AND t_to>=? ORDER BY id DESC LIMIT 1', (pid, t, t)).fetchone()
        if r: return (r[0], r[1], '指派', '命令')
        o = self.S.org
        if p['gen'] == o.visitor_gen: return (o.visitor_place, o.visitor_act, '作息', '外来香客')
        r = self.x('SELECT place FROM roster WHERE person=? AND day=? AND slot=?', (pid, day, slot)).fetchone()
        if r: return (r[0], '值守', '值守', '班表')
        place, act = self.template(p, day, slot)
        return (place, act, '作息', '模板')

    def where(self, pid, day, slot):
        """某人某日某时辰在哪、在做什么 -> (场所 code, 活动)。先查引擎与例外(指派), 再查值守排班, 最后算作息模板。"""
        r = self.where_ex(pid, day, slot)
        return None if r is None else r[:2]

    def present(self, place, day, slot, exclude=None):
        ids = [r[0] for r in self.x('SELECT id FROM person ORDER BY id')]
        return [i for i in ids if i != exclude and (self.where(i, day, slot) or (None,))[0] == place]
