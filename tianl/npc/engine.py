"""NpcEngine：把九层机制串成一个时辰的 tick（固定次序见 docs/NPC_ENGINE.md 第 4 节、ARCHITECTURE 6.1）。

* 与外界只通过 Host 交互（事件、随机数、内核命令）；规格对象 SiteSpec 描述世界；
* 一切随机都是 host.rng(seed, 用途, 日, 时辰, 人…)，与调用次序无关——多生成一条叙述不会改写任何人的未来；
* 人内部用 ix（int，稳定，新人追加），外部用 pid（str）；事件同理：内部用引擎自己的流水号 id（见闻、案卷、随机数键），
  Host 给的事件 id（hid）只在边界出现——所以引擎的行为与 Host 怎么编号、别处写了多少事件无关；
* 每个决定都留“生效层与原因”（轨迹打包），where / explain 随时可答（计划 12.2 第九条“说得清”）。
"""
import hashlib
from collections import Counter
from operator import itemgetter
from time import perf_counter

from ..core import SLOTS, clamp, gauss, t_of
from .events import FOOD_THEFT, label as event_label
from .facilities import Facilities
from .freechoice import FreeChoice
from .jobs import JobBoard
from .model import (BASE_DECISION, GAP, EvRec, PersonSpec, Profile, Script, SlotCtx, Symbols, pack, place_of,
                    unpack)
from .mood import Moods
from .needs import Needs
from .norms import Norms
from .opinion import Opinions
from .perception import Perception
from .rumor import Rumor
from .spec import A_WORK, L_FREE, L_SLACK, TRAIT_KEYS, SpecError
from .stack import Stack

HASH_CHARS = 16                     # state_hash 取 sha256 十六进制的前几位（基线口径）
PKG_STAT = 'pkg_'                   # 统计键前缀：每层行为包占了多少个决定


class NpcEngine:
    def __init__(self, spec, host, acting=True, script=None, person_factory=None):
        problems = spec.validate()
        if problems:
            raise SpecError(problems)
        self.spec, self.host = spec, host
        self.seed, self.rng = host.seed, host.rng
        self.acting = acting                       # 监院是否派人代理（v0.2 的“指派”一级）
        self.script = Script.coerce(script)
        self.world = None                          # attach() 之后是内核 World
        self.person_factory = person_factory       # pid -> PersonSpec：on_person_added(pid) 遇到名册里没有的 pid 时用（集成层提供）
        # 人
        self.people, self.pids, self._ix = [], [], {}
        self.by = {}                               # 岗位名 -> [ix]（None 键是清众）
        self.common = []                           # 清众（无岗位者）的档案，建人次序
        self.sym = Symbols()
        self._packed = {}                          # 决定四元组 -> 轨迹打包值（同样的决定天天重复，驻留一次就够）
        # 世界状态
        self.stock = dict(spec.kitchen.stock_init)  # 厨房库存：水、柴（挑水打柴入账，斋食出账）
        self.kit_staff = {}                        # 备斋时辰 -> 当时在厨房干活的人数
        self.sight = set()                         # 当日查寮记下的空铺者
        self.evs, self.ev_by_id = [], {}           # 引擎自留的事件记录（ix 版本）；ev_by_id 以引擎流水号为键
        self.ev_by_hid = {}                        # Host 事件 id -> 记录
        self.dec = {}                              # 最近一个时辰各人的决定 ix -> (场所, 活动, 层, 原因)
        self.last = None                           # 最近跑完的 (日, 时辰)
        # 统计（只用于报告与验收，不进入任何决定）
        self.stat = Counter()
        self.acts = {g: Counter() for g in spec.groups}
        self.choice = Counter()
        self.att, self.att_exp = Counter(), Counter()
        self.moodlow = self.pd = 0
        self.daily = []
        self.elapsed = 0.0                         # 引擎内累计耗时（秒），只用于报告
        # 观察者
        self.observer, self.narr, self.narr_last = None, 0, []
        self._h = hashlib.sha256()
        # 各层机制
        self.opinions, self.moods, self.needs = Opinions(self), Moods(self), Needs(self)
        self.fac, self.free, self.jobs = Facilities(self), FreeChoice(self), JobBoard(self)
        self.stack, self.perc = Stack(self), Perception(self)
        self.rumor, self.norms = Rumor(self), Norms(self)

    # ================= Engine 协议（ARCHITECTURE 5.1）=================
    def attach(self, world):
        self.world = world

    def on_person_added(self, person):
        """收录、选角、迁入（ARCHITECTURE 5.1 的 on_person_added(pid)）。

        给 pid：已在名册里就什么也不做；不在则向 person_factory(pid) 要一份 PersonSpec 来建人（没有工厂就报错）。
        给 PersonSpec：直接建人（独立运行与测试用）。返回档案。
        """
        if isinstance(person, PersonSpec):
            return self.add_person(person)
        if isinstance(person, int) or person in self._ix:
            return self.people[self.ix_of(person)]
        if self.person_factory is None:
            raise LookupError('名册里没有 %r，且没有 person_factory 可以建它' % (person,))
        ps = self.person_factory(person)
        if ps.pid != person:
            raise ValueError('person_factory(%r) 给出的 PersonSpec.pid 是 %r' % (person, ps.pid))
        return self.add_person(ps)

    def on_person_removed(self, pid, why):
        p = self.people[self.ix_of(pid)]
        if p.gone is None:
            p.gone = self.last[0] if self.last else 0
            p.gone_why = why
            self.stat['left_' + why] += 1

    # ================= 建人 =================
    def ix_of(self, x):
        return x if isinstance(x, int) else self._ix[x]

    def add_person(self, ps):
        """追加一个人；返回档案。traits 缺项时按规格里的分布与种子生成（键是 (种子, 性格, ix)，与建人次序无关于他人）。"""
        if ps.pid in self._ix:
            raise ValueError('重复的 pid：%s' % ps.pid)
        sp = self.spec
        ix = len(self.people)
        p = Profile(ix, ps.pid, ps.name, ps.office, ps.track, ps.dorm, sp.needs.init)
        tr = sp.traits
        for k in TRAIT_KEYS:
            if ps.traits and k in ps.traits:
                v = ps.traits[k]
            else:
                b = tr.office_bonus.get(k, 0) if ps.office else 0
                v = clamp(gauss(tr.mean[k] + b, tr.sd[k], self.seed, k, ix, rng=self.rng), tr.lo, tr.hi)
            setattr(p, k, v)
        self.people.append(p)
        self.pids.append(ps.pid)
        self._ix[ps.pid] = ix
        self.by.setdefault(ps.office, []).append(ix)
        if ps.office is None:
            self.common.append(p)
        return p

    def set_traits(self, who, **traits):
        """改性格刻度（场景里的“要角”用；必须在开跑前调）。"""
        p = self.people[self.ix_of(who)]
        for k, v in traits.items():
            if k not in TRAIT_KEYS:
                raise KeyError(k)
            setattr(p, k, v)

    # ================= 世界事实 =================
    def guards(self, day):
        """当日山门值守（从清众里按日轮）。"""
        g, m = self.spec.gate, len(self.common)
        if not m:
            return ()
        return tuple(self.common[(g.count * day + k) % m].ix for k in range(g.count))

    def night_patroller(self, day):
        L = self.by.get(self.spec.patrol.office)
        return L[day % len(L)] if L else None

    def court_staff(self):
        return [i for o in self.spec.court.judges for i in self.by.get(o, [])]

    def court_open(self, day):
        P = self.people
        return any(P[i].ill < day and P[i].conf < day for i in self.court_staff())

    # ================= 事件 =================
    def emit(self, kind, actor, place, wit, day, slot, cause=None, **data):
        """写一条事件：经 Host 落地，引擎另留 ix 版本；按显著度给每个见证人记见闻。"""
        pids = self.pids
        hcause = None if cause is None else self.ev_by_id[cause].hid          # 对 Host 说话用它自己的 id
        he = self.host.ev(kind, None if actor is None else pids[actor], place, [pids[w] for w in wit], day, slot,
                          hcause, **data)
        rec = EvRec(len(self.evs), he.id, kind, actor, place, list(wit), day, slot, cause, data)
        self.evs.append(rec)
        self.ev_by_id[rec.id] = rec
        self.ev_by_hid[rec.hid] = rec
        sal = self.spec.salience.get(kind, 0)
        if sal > 0:
            P = self.people
            for w in wit:
                if w != actor:
                    P[w].news[rec.id] = [sal, 0, None]
        return rec

    # ================= 一日 =================
    def begin_day(self, day):
        t0 = perf_counter()
        sp, P, r, seed = self.spec, self.people, self.rng, self.seed
        live = [p for p in P if p.gone is None]
        il = sp.illness
        for p in live:
            if p.ill < day and p.conf < day and r(seed, 'ill', day, p.ix) < il.p:
                p.ill = day + il.min_days + int(r(seed, 'illd', day, p.ix) * il.span)
                self.stat['ill'] += 1
        sc = self.script.ill
        if sc and sc[0] == day:
            for i in sc[1]:
                P[self.ix_of(i)].ill = day + sc[2] - 1
        kt = sp.kitchen
        kit = [p for p in live if p.office in sp.kitchen_offices and p.ill < day and p.conf < day]
        if self.acting and len(kit) < kt.acting_target:                  # 监院派人代理
            gs = self.guards(day)
            cand = sorted((p for p in live if p.office is None and p.ill < day and p.conf < day
                           and p.ix not in gs), key=lambda p: (-p.D, p.ix))
            for p in cand[:kt.acting_target - len(kit)]:
                p.duty_day = day
                self.stat['acting'] += 1
        self.jobs.publish()
        self.sight = set()
        self.elapsed += perf_counter() - t0

    def end_day(self, day):
        t0 = perf_counter()
        lows = 0
        for p in self.people:
            if p.gone is not None:
                continue
            self.moods.expire(p, day)
            self.rumor.decay(p)
            lows += self.moods.is_low(p)
            self.pd += 1
        self.moodlow += lows
        self.opinions.expire(day)
        self.rumor.end_day(day)
        self.daily.append((day, self.stat['theft'], self.stat['half_meal'], self.stat['hungry']))
        self.elapsed += perf_counter() - t0

    # ================= 一个时辰 =================
    def run_slot(self, day, slot):
        t0 = perf_counter()
        sp, P, stat = self.spec, self.people, self.stat
        n = len(P)
        if n == 0:
            return
        ctx = SlotCtx(day, slot)
        dec = ctx.dec
        # 1 各人决定：起点轮转，保证工位预约公平且确定
        off = (day * sp.rotate[0] + slot * sp.rotate[1]) % n
        decide = self.stack.decide
        for k in range(n):
            p = P[(off + k) % n]
            if p.gone is not None:
                continue
            d = decide(p, day, slot, ctx)
            if len(d) > BASE_DECISION:                       # 巡寮者：决定里带着所巡之处
                ctx.seen, ctx.patroller = d[BASE_DECISION], p.ix
                d = d[:BASE_DECISION]
            dec[p.ix] = d
        # 2 闲谈配对与转述
        self.rumor.pair(ctx, day, slot)
        # 3 差事结算；斋食
        kt = sp.kitchen
        if slot == sp.common.work_slot:
            self.jobs.settle(day, slot)
        if slot in kt.prep.values():
            self.kit_staff[slot] = sum(1 for d in dec.values() if d[0] == kt.place and d[1] == A_WORK)
        gain = kt.gain_full
        if slot in sp.meal_slots:
            ok = self.kit_staff.get(kt.prep[slot], 0) >= kt.min_staff and \
                all(self.stock[k] >= q for k, q in kt.stock_use)
            if ok:
                for k, q in kt.stock_use:
                    self.stock[k] -= q
            else:
                gain = kt.gain_half
                stat['half_meal'] += 1
            stat['meals'] += 1
            exp = sum(1 for p in P if p.gone is None and p.ill < day and p.conf < day)
            self.att_exp[slot] += exp
            self.att[slot] += sum(1 for d in dec.values() if d[0] == kt.dining_place)
        # 4 需求结算；想法；落轨迹（统计、哈希在此累积）
        ns = sp.needs
        t = t_of(day, slot)
        sid, hup, packed = self.sym.intern, self._h.update, self._packed
        free_layers = (L_FREE, L_SLACK)
        hungry = tired = 0
        for i, d in dec.items():
            p = P[i]
            self.needs.settle(p, d, slot, gain)
            nd = p.need
            if d[2] in free_layers:
                self.choice[d[3][:sp.free.choice_key_chars]] += 1
            th = ns.act_thought.get(d[1])
            if th:
                self.moods.think(p, th, day)
            self.acts[sp.groups[0] if p.office is None else sp.groups[1]][ns.category.get(d[1], ns.category_default)] += 1
            hungry += nd['h'] < ns.hungry_line
            tired += nd['e'] < ns.tired_line
            pk = packed.get(d)
            if pk is None:
                pk = packed[d] = pack(sid(d[0]), sid(d[1]), sid(d[2]), sid(d[3]))
            p.trail.push(t, pk)
            hup(('%d,%d,%d,%s,%s;' % (day, slot, i, d[0], d[1])).encode())
        stat['ps'] += len(dec)
        stat['hungry'] += hungry
        stat['tired'] += tired
        for layer, k in Counter(map(itemgetter(2), dec.values())).items():
            stat[PKG_STAT + layer] += k
        self.fac.check_overflow(ctx.occ, day, slot)
        # 5 观察者所在场所的细节叙述：只读，只计数，不改任何状态
        if self.observer:
            here = sorted((i for i, d in dec.items() if d[0] == self.observer),
                          key=lambda i: self.rng(self.seed, 'narr', day, slot, i))
            self.narr += len(here)
            self.narr_last = here
        # 6 偷食 → 见证 → 是否举报；巡夜查寮；脚本事件
        self.perc.thefts(ctx, day, slot)
        self.perc.bed_check(ctx, day, slot)
        self._script_gossip(day, slot)
        # 7 典座清点；维那点名；怠工被撞见；举报送达；裁断；午斋后公告
        self.perc.inventory(ctx, day, slot)
        self.perc.roll_call(ctx, day, slot)
        self.perc.slackers(ctx, day, slot)
        self.norms.deliver(ctx, day, slot)
        self.norms.adjudicate(ctx, day, slot)
        self.norms.announce(ctx, day, slot)
        self.dec, self.last = dec, (day, slot)
        self.elapsed += perf_counter() - t0

    def _script_gossip(self, day, slot):
        g = self.script.gossip
        if g and g[0] == day and slot == self.script.gossip_slot:
            a, w = self.ix_of(g[1]), self.ix_of(g[2])
            e = self.emit(FOOD_THEFT, a, self.spec.kitchen.place, [w], day, slot, why=self.script.gossip_why)
            self.rumor.track(e.id, [w])

    def run_day(self, day):
        """便利：一整天（begin_day + 十二个时辰 + end_day）。"""
        self.begin_day(day)
        for slot in range(len(SLOTS)):
            self.run_slot(day, slot)
        self.end_day(day)

    # ================= 观察者 =================
    def set_observer(self, place):
        self.observer = place

    # ================= 查询 API =================
    def where(self, who, day, slot):
        """(场所 code, 活动, 层, 原因) | None。任何已跑过的时辰都能答；
        None = 没有记录：还没跑到、加入之前、离开之后（离开的缘由见 explain）、或轨迹中间缺格。"""
        p = self.people[self.ix_of(who)]
        v = p.trail.get(t_of(day, slot))
        if v is None:
            return None
        nm = self.sym.names
        a, b, c, d = unpack(v)
        return nm[a], nm[b], nm[c], nm[d]

    def present(self, place, day=None, slot=None):
        """在 place 的人（pid 列表，按 ix 升序）。不给日和时辰就是最近跑完的那个时辰。"""
        if (day is None) != (slot is None):
            raise ValueError('present() 的 day 与 slot 要么都给，要么都不给')
        if day is None:
            return [self.pids[i] for i, d in sorted(self.dec.items()) if d[0] == place]
        out = []
        for p in self.people:
            w = self.where(p.ix, day, slot)
            if w and w[0] == place:
                out.append(p.pid)
        return out

    def explain(self, who, day, slot):
        """为什么此刻做这件事：生效层、层号（计划 6.1）、原因；若正是最近跑完的时辰，附当时的状态。"""
        ix = self.ix_of(who)
        p = self.people[ix]
        w = self.where(ix, day, slot)
        if w is None:
            end = p.trail.end
            if end is None and p.gone is not None:
                end = t_of(p.gone + 1, 0)                   # 从没有过记录的人：离开当日之后都算离开
            if p.gone is not None and t_of(day, slot) >= end:      # 离开之后：说明去了哪里
                why = p.gone_why or ''
                return {'pid': p.pid, 'name': p.name, 'day': day, 'slot': slot, 'slot_name': SLOTS[slot], 'place': None,
                        'place_name': None, 'act': None, 'layer': None, 'layer_rank': None, 'reason': why,
                        'gone': p.gone, 'text': '第%d日%s时 %s已于第%d日离寺（%s）' % (day, SLOTS[slot], p.name, p.gone, why)}
            return None
        place, act, layer, reason = w
        out = {'pid': p.pid, 'name': p.name, 'day': day, 'slot': slot, 'slot_name': SLOTS[slot], 'place': place,
               'place_name': self.spec.places.get(place, place), 'act': act, 'layer': layer,
               'layer_rank': self.spec.layer_rank.get(layer), 'reason': reason}
        out['text'] = '第%d日%s时 %s在%s：%s（生效层「%s」）' % (day, SLOTS[slot], p.name, out['place_name'], reason, layer)
        if self.last == (day, slot):
            out['state'] = {'need': dict(p.need), 'mood': self.moods.mood(p), 'ill': p.ill >= day,
                            'confined': p.conf >= day, 'kneel': p.kneel >= day,
                            'pending': [self.ev_by_id[e].hid for e in p.pending],
                            'thoughts': [tuple(x) for x in p.thoughts]}
        return out

    def news_of(self, who):
        """他知道哪些事：[(Host 事件 id, 事件种类, 强度, 经手层数, 听谁说的 pid | None)]，强的在前（平手按发生先后）。"""
        p = self.people[self.ix_of(who)]
        rows = sorted(((e, v) for e, v in p.news.items()), key=lambda x: (-x[1][0], x[0]))
        return [(self.ev_by_id[e].hid, self.ev_by_id[e].kind, v[0], v[1], None if v[2] is None else self.pids[v[2]])
                for e, v in rows]

    def opinion(self, a, b):
        return self.opinions.opinion(self.ix_of(a), self.ix_of(b))

    def opinion_breakdown(self, a, b):
        return self.opinions.breakdown(self.ix_of(a), self.ix_of(b))

    def mood(self, who):
        return self.moods.mood(self.people[self.ix_of(who)])

    def needs_of(self, who):
        return dict(self.people[self.ix_of(who)].need)

    def friends(self):
        return self.opinions.friends()

    def cases(self):
        """案卷列表（立案次序）：每件案子的状态、指认人、定罪依据与处分。eid 是 Host 事件 id（偷食那条）。"""
        P = self.people
        out = []
        for eid, c in self.norms.cases.items():
            e = self.ev_by_id[eid]
            out.append({'eid': e.hid, 'actor': None if e.actor is None else self.pids[e.actor], 'day': e.day,
                        'opened': c.opened, 'state': c.state, 'accusers': [P[a].pid for a in sorted(c.acc)],
                        'suspects': [P[a].pid for a in sorted(c.sus)], 'asked': c.asked, 'via': c.via,
                        'sanction': c.txt, 'sanction_day': c.day})
        return out

    # ================= 哈希与轨迹 =================
    def state_hash(self):
        """回归哈希：每个决定一行 `日,时辰,ix,场所,活动;` 的 sha256，再并入事件日志每条 `种类中文,actor,日,时辰;`，取前 16 位。"""
        h = self._h.copy()
        for e in self.evs:
            h.update(('%s,%s,%d,%d;' % (event_label(e.kind), e.actor, e.day, e.slot)).encode())
        return h.hexdigest()[:HASH_CHARS]

    def event_of(self, hid):
        """Host 事件 id -> 引擎里的事件记录（EvRec）；不是本引擎发的事件则 KeyError。"""
        return self.ev_by_hid[hid]

    def places_of(self, who):
        """该人每个时辰所在场所的序列（按轨迹次序；轨迹中间缺格的时辰是 None）。"""
        nm = self.sym.names
        return [None if v == GAP else nm[place_of(v)] for v in self.people[self.ix_of(who)].trail.arr]

    def agree(self, a, b):
        """两人在同一绝对时刻同处一地的时辰占比（只比两人都有记录的时刻）。"""
        A, B = self.people[self.ix_of(a)].trail, self.people[self.ix_of(b)].trail
        if A.t0 is None or B.t0 is None:
            return 0.0
        lo, hi = max(A.t0, B.t0), min(A.t0 + len(A), B.t0 + len(B))
        both = same = 0
        for t in range(lo, hi):
            x, y = A.arr[t - A.t0], B.arr[t - B.t0]
            if x == GAP or y == GAP:
                continue
            both += 1
            same += place_of(x) == place_of(y)
        return same / both if both else 0.0
