"""人与岗位：开局造人、师承、住处、任命；岗位查询；每日的圆寂、继任、收录与岁末施舍。

开局造人的次序决定人号（P0001…），而状态哈希按 rowid 遍历，所以次序与随机键必须与 v0.2 完全一致：
  要角（按定义的列表序）-> 各辈无名僧（辈序、序号 k，取名与年龄用 'name'/'age' 键）-> 院堂配额 -> 师承（'master' 键）-> 住处 -> 任命。
"""
from ..core.calendar import YEAR
from .vocab import SHI


NAME_DRAWS = 64        # 取名：单字名先按随机键抽，每个池字平均最多抽这么多轮；仍抽不中才改为确定性扫描（见 _newname）


class PeopleMixin:
    # ------------------------------------------------------------------ 造人
    def _mk(self, gen, name, age, hall, canon=0, joined=0, home=None):
        """造一个人并落库。引擎的 on_person_added 在这一行的各字段（含 home）都写定之后才调用：
        收录者的住处由调用方经 home 一并写入，开局造人时住处在 _people 里统一排定（那时引擎尚未接上，不会回调）。"""
        pid = f'P{len(self.pids) + 1:04d}'; self.pids.append(pid); self.names.add(name)
        self.x('INSERT INTO person VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (pid, name, '要角' if canon else '普通', gen, age, self.ac.org, hall, home, None, '在寺', joined, None, canon))
        if self.engine is not None: self.engine.on_person_added(pid)
        return pid

    def _newname(self, gen, salt):
        """辈字 + 池里一个字。只要池里还有没用过的字，抽签次序与原型逐位相同（所以哈希不变）。
        池耗尽时不再死循环：先（极小概率）抽不中则按池序确定性扫描空位，单字名全被占满则改取两字名（辈字 + 池字 + 池字），
        两字名也占满才报错。"""
        pool, names = self._pool, self.names
        n = len(pool)
        free = lambda nm: nm not in names
        for i in range(n * NAME_DRAWS):
            ch = pool[int(self.u('name', gen, salt, i) * n)]
            if ch != gen and free(gen + ch): return gen + ch
        start = int(self.u('name', gen, salt, 'scan') * n)                       # 确定性扫描：随机起点、按池序
        for j in range(n):
            ch = pool[(start + j) % n]
            if ch != gen and free(gen + ch): return gen + ch
        for i in range(n * NAME_DRAWS):                                          # 单字名占满：两字名
            a, b = pool[int(self.u('name2', gen, salt, i, 'a') * n)], pool[int(self.u('name2', gen, salt, i, 'b') * n)]
            if free(gen + a + b): return gen + a + b
        for j in range(n * n):
            nm = gen + pool[(start + j // n) % n] + pool[j % n]
            if free(nm): return nm
        raise RuntimeError(f'取名池耗尽：辈字 {gen!r} 下 {n} 个单字名与 {n * n} 个两字名都已用完')

    def _people(self):
        x, o, K = self.x, self.S.org, self.K
        if len(set(o.pool)) < K['pool_min']:
            raise ValueError(f"取名池只有 {len(set(o.pool))} 个不同的字，少于规则参数 pool_min = {K['pool_min']}")
        canon = {c.name: self._mk(c.gen, c.name, c.age, c.hall, 1) for c in o.canon}
        for gd in o.gens:
            lo, hi = gd.age
            for k in range(gd.n):
                nm = self._newname(gd.gen, k)
                self._mk(gd.gen, nm, lo + int(self.u('age', nm) * (hi - lo + 1)), o.default_hall)
        by = lambda gen, hall=o.default_hall: [r[0] for r in x('SELECT id FROM person WHERE gen=? AND hall=? AND canon=0 ORDER BY id', (gen, hall))]
        for gd in o.gens:                                     # 院堂配额：各辈前若干人依次分到各院堂
            ids = by(gd.gen); i = 0
            for hall, n in gd.quota:
                for pid in ids[i:i + n]: x('UPDATE person SET hall=? WHERE id=?', (hall, pid))
                i += n
        # 师承: 下一辈 -> 上一辈（自该辈全体随机）
        allg = lambda g: [r[0] for r in x('SELECT id FROM person WHERE gen=? ORDER BY id', (g,))]
        for gd in o.gens:
            if not gd.master_gen: continue
            ms = allg(gd.master_gen)
            for pid in allg(gd.gen): x('UPDATE person SET master=? WHERE id=?', (ms[int(self.u('master', pid) * len(ms))], pid))
        for name, master in o.canon_masters: x('UPDATE person SET master=? WHERE id=?', (canon[master], canon[name]))
        # 住处
        senior = {gd.gen for gd in o.gens if gd.senior}
        canon_home = {canon[c.name]: c.home for c in o.canon if c.home}
        for i, (pid, gen, hall) in enumerate(x('SELECT id, gen, hall FROM person ORDER BY id').fetchall()):
            home = canon_home[pid] if pid in canon_home else o.halls.get(hall, o.elders_home) if gen in senior else f'{o.dorm.prefix}{i // o.dorm.per + 1}'
            x('UPDATE person SET home=? WHERE id=?', (home, pid))
        # 清规岗位与院堂首座
        free = {}
        for a in o.appointments:
            if a.canon: pid = canon[a.canon]
            elif a.pick == 'hall': pid = by(a.gen, a.hall)[a.index]
            else:
                if a.gen not in free: free[a.gen] = by(a.gen)
                pid = free[a.gen].pop(0)
            self._appoint((self.S.org.deputy_prefix if a.deputy else '') + a.post, pid)
        # 独有物
        for it in self.S.items:
            cust = self._appointee(it.keeper) if it.custodian == 'keeper' else it.custodian
            x('INSERT INTO item VALUES(?,?,?,?,?,?,0)', (it.code, it.name, it.home, it.keeper, cust, it.home))

    def _appoint(self, office, pid):
        self.x('INSERT OR IGNORE INTO office VALUES(?,?)', (office, self.S.site_of.get(self.base_of(office))))
        self.x('INSERT INTO appointment(person,office,from_day,to_day) VALUES(?,?,0,?)', (pid, office, 10 ** 9))

    # ------------------------------------------------------------------ 岗位
    def base_of(self, office):
        """去掉副职前缀，得到正职名。"""
        pre = self.S.org.deputy_prefix
        while pre and office.startswith(pre): office = office[len(pre):]
        return office

    def _appointee(self, office, day=None):
        d = self.day if day is None else day
        r = self.x('SELECT person FROM appointment WHERE office=? AND from_day<=? AND to_day>=? ORDER BY id DESC LIMIT 1',
                   (office, d, d)).fetchone()
        return r[0] if r else None

    def holder(self, office, day=None):
        """现任; 正职出缺时由副职代理。"""
        pre = self.S.org.deputy_prefix
        return self._appointee(office, day) or (None if office.startswith(pre) else self._appointee(pre + office, day))

    def office_of(self, pid, day):
        r = self.x('SELECT office FROM appointment WHERE person=? AND from_day<=? AND to_day>=? ORDER BY id DESC LIMIT 1',
                   (pid, day, day)).fetchone()
        return r[0] if r else None

    def pname(self, pid):
        if not pid: return ''
        r = self.x('SELECT name FROM person WHERE id=?', (pid,)).fetchone()
        return r[0] if r else pid

    # ------------------------------------------------------------------ 每日: 圆寂、继任、收录、施舍
    def phase_people(self):
        d, c, Pm, K, o = self.day, self.cal(self.day), self.P, self.K, self.S.org
        se = self.S.season
        if c['doy'] == se.new_year_doy and d > 0: self.x("UPDATE person SET age=age+1 WHERE status='在寺'"); self.pcache.clear()
        for pid, age in self.x("SELECT id, age FROM person WHERE status='在寺' AND canon=0 ORDER BY id").fetchall():
            hz = next((r for lim, r in K['mortality'] if age < lim), K['mortality_old'])
            if self.u('death', pid, d) < hz / YEAR: self.die(pid, d)
        self.succession()
        if c['doy'] == se.recruit_doy:                        # 四月初一: 收录新僧补足员额
            n = Pm['monks'] - self.head()
            for k in range(n):
                nm = self._newname(o.recruit.gen, f'r{d}-{k}')
                self._mk(o.recruit.gen, nm, o.recruit.age_min + int(self.u('age', nm) * o.recruit.age_span), o.default_hall, joined=d,
                         home=f'{o.dorm.prefix}{o.dorm.recruit}')        # 住处随行写入：引擎在回调里读到的就是定稿的一行
            if n > 0: self.ev('RECRUIT', place=self.pl.temple, actor=self.holder(self.T.abbot), n=n)
        if c['festival'] == se.charity_festival:
            if self.tier_i == 0:
                g = self.consume(self.ac.org, self.pl.granary, self.cm.staple, K['charity_shi'] * SHI, 'consume'); self.tg[(self.year, self.TG['charity'])] += g
                self.ev('CHARITY', place=self.pl.gate, actor=self.holder(self.T.cook), grain=g)
            extra = self.bal(self.ac.org) - Pm['treasury_target']
            if extra > 0:
                m = self.pay(self.ac.org, self.ac.town, extra * K['merit_n'] // K['merit_d'], self.R['merit'])
                self.ev('MERIT_SPEND', place=self.pl.temple, actor=self.holder(self.T.abbot), money=m)
        if c['dom'] == 1: self.audit_items()
        self.make_roster(d + 1)

    def die(self, pid, last_day):
        self.x("UPDATE person SET status='圆寂', died=? WHERE id=?", (last_day, pid)); self.pcache.pop(pid, None)
        offs = [r[0] for r in self.x('SELECT office FROM appointment WHERE person=? AND from_day<=? AND to_day>=?', (pid, last_day, last_day))]
        self.x('UPDATE appointment SET to_day=? WHERE person=? AND to_day>=?', (last_day, pid, last_day))
        e = self.ev('DEATH', place=self.pl.temple, actor=pid, offices=offs); self.cnt['deaths'] += 1
        pre = self.S.org.deputy_prefix
        for o in offs:
            self.vacant[o] = last_day + 1
            dep = None if o.startswith(pre) else self._appointee(pre + o, last_day + 1)
            if dep: self.ev('ACTING', actor=dep, cause=e, office=o)
        if self.engine is not None: self.engine.on_person_removed(pid, '圆寂')

    def succession(self):
        d, sc, pre = self.day, self.S.org.succession, self.S.org.deputy_prefix
        for office, since in sorted(self.vacant.items()):
            if d < since + 1: continue                        # 出缺次日议定, 第三日起正式任职
            dep = None if office.startswith(pre) else self._appointee(pre + office, d + 1)
            if dep:
                self.x('UPDATE appointment SET to_day=? WHERE person=? AND office=? AND to_day>=?', (d, dep, pre + office, d))
                self.vacant[pre + office] = d + 1; new = dep
            else:
                hall = self.S.post_hall.get(office)
                rank = sc.hall_rank if hall else sc.other_rank
                gens = "','".join(dict.fromkeys(sc.hall_rank + sc.other_rank))
                cand = self.x(f"SELECT p.id, p.gen, p.age, p.hall FROM person p WHERE p.status='在寺' AND p.canon=0 AND p.gen IN ('{gens}') AND p.age>=? "
                              "AND NOT EXISTS (SELECT 1 FROM appointment a WHERE a.person=p.id AND a.to_day>=?) ORDER BY p.id", (sc.min_age, d)).fetchall()
                cand = [r for r in cand if not hall or r[3] == hall]
                new = min(cand, key=lambda r: (rank.index(r[1]), -r[2], r[0]), default=(None,))[0]
            if new:
                self.x('INSERT INTO appointment(person,office,from_day,to_day) VALUES(?,?,?,?)', (new, office, d + 1, 10 ** 9))
                self.ev('APPOINT', actor=self.holder(self.T.abbot), office=office, person=new); del self.vacant[office]
