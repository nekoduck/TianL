"""综合校验（tools/canon_check.py 的实现）。

子命令（可组合）：--census --assertions --events --secrets --identities --gaps --qa --timeline --recall --evidence --all；
--part NAME 只跑某分区的文件（普查 p1–p4 c5 c6a c6b c6c；按回文件 ch00–ch52；p1–p4 也圈住范围内的按回文件）。
不给任何子命令等于 --all。输出汇总计数；退出码 0 全部通过、1 有错误。

诚实口径（docs/DECISIONS.md 第三节）：证据指针有效率只统计 basis = text 的行；没有原文时如实写“0 条有文本支撑”，
不会因此报通过。
--evidence：有原文时逐条核对指针（能取回、哈希相符），basis=text 的行须有 ≥1 条有效证据，basis=recall 的行证据须为空；
没有原文时只给出提示（该节“跳过”，不算失败）。断言的“重复”只是警告（同一事实可在多回里各出现一次，第 6 阶段合并证据）。
"""
from __future__ import annotations

import argparse
import heapq
import json
import sys
from pathlib import Path

from . import merge as M
from . import schema as S

SECTION_TITLES = {'census': '普查', 'assertions': '断言', 'events': '事件', 'secrets': '秘密', 'identities': '身份',
                  'gaps': '缺口', 'qa': '问答', 'timeline': '时间线', 'recall': '30 人召回', 'evidence': '证据指针'}
ORDER = ('census', 'assertions', 'events', 'secrets', 'identities', 'gaps', 'qa', 'timeline', 'recall', 'evidence')


class Section:
    def __init__(self, name):
        self.name = name
        self.errors, self.warnings, self.info = [], [], []
        self.skipped = None             # 跳过的原因

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def add(self, line):
        self.info.append(line)


# ----------------------------------------------------------------------------------------------------------------------
# 纯函数：时间线与召回（便于单测）
# ----------------------------------------------------------------------------------------------------------------------
def _live(a):
    """断言是否“可当事实用”：叙述者陈述、未作废。"""
    return a.get('rank') != 'dep' and a.get('mode', 'narrator') == 'narrator'


def build_parents(assertions):
    par = {}
    for _, a in assertions:
        if a.get('property') == 'parent' and _live(a) and isinstance(a.get('value'), str):
            par.setdefault(a['subject'], a['value'])
    return par


def place_chain(parents, p):
    out, seen = [p], {p}
    while p in parents and parents[p] not in seen:
        p = parents[p]
        out.append(p)
        seen.add(p)
    return out


def places_related(parents, a, b):
    return a == b or b in place_chain(parents, a) or a in place_chain(parents, b)


def build_route_graph(assertions, route_rows=()):
    """无向图 {地点: {邻居: 最少时辰数}}。来源：地点的 route 断言（须带 slots）与 routes 行 {"a","b","slots"}。
    返回 (图, 缺 slots 的 route 断言数)。"""
    g, noslots = {}, 0

    def add(a, b, n):
        for x, y in ((a, b), (b, a)):
            d = g.setdefault(x, {})
            d[y] = min(n, d.get(y, n))

    for _, a in assertions:
        if a.get('property') == 'route' and _live(a):
            n = (a.get('qualifiers') or {}).get('slots')
            if isinstance(n, int) and not isinstance(n, bool) and n >= 1 and isinstance(a.get('value'), str):
                add(a['subject'], a['value'], n)
            else:
                noslots += 1
    for r in route_rows:
        if isinstance(r, dict) and isinstance(r.get('slots'), int) and r.get('a') and r.get('b'):
            add(r['a'], r['b'], r['slots'])
    return g, noslots


def shortest_slots(graph, src, dst):
    """Dijkstra（确定性：按 (距离, 地点编号) 弹出）。不可达返回 None。"""
    if src == dst:
        return 0
    dist, heap = {src: 0}, [(0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, float('inf')):
            continue
        if u == dst:
            return d
        for v, w in sorted(graph.get(u, {}).items()):
            nd = d + w
            if nd < dist.get(v, float('inf')):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return None


def _node_of(graph, parents, place):
    for p in place_chain(parents, place):
        if p in graph:
            return p
    return None


def find_cycle(edges):
    """edges: {节点: [后继]}。有环返回其中一个环（节点列表），否则 None。迭代 DFS，顺序确定。"""
    color, stack_path = {}, []
    for root in sorted(edges):
        if color.get(root):
            continue
        stack = [(root, iter(sorted(edges.get(root, ()))))]
        color[root] = 1
        stack_path = [root]
        while stack:
            u, it = stack[-1]
            for v in it:
                c = color.get(v, 0)
                if c == 0:
                    color[v] = 1
                    stack.append((v, iter(sorted(edges.get(v, ())))))
                    stack_path.append(v)
                    break
                if c == 1:
                    i = stack_path.index(v)
                    return stack_path[i:] + [v]
            else:
                color[u] = 2
                stack.pop()
                stack_path.pop()
    return None


def check_timeline(events, assertions, secrets=(), entities=None, route_rows=()):
    """时间线综合检查。events: [(位置, 已展开事件)]；assertions: [(位置, 完整断言)]；secrets: [(位置, 秘密)]。
    返回 (错误列表, 警告列表, 信息行列表)。"""
    errs, warns, info = [], [], []
    parents = build_parents(assertions)
    graph, noslots = build_route_graph(assertions, route_rows)
    if noslots:
        warns.append(f'{noslots} 条 route 断言没有 slots（路程时辰数），无法参与路程检查')
    evs = {}
    for where, e in events:
        if isinstance(e, dict) and isinstance(e.get('id'), str):
            evs.setdefault(e['id'], (where, e))

    def times(e):
        t = e.get('time')
        if isinstance(t, dict) and isinstance(t.get('start'), int) and not isinstance(t.get('start'), bool):
            en = t.get('end', t['start'])
            if isinstance(en, int) and not isinstance(en, bool) and en >= t['start']:
                return t['start'], en
        return None

    # 1. 先后关系无环、与时间不矛盾
    edges = {}
    for eid, (where, e) in evs.items():
        for pred in e.get('after') or []:
            if pred in evs:
                edges.setdefault(pred, []).append(eid)
                tp, ts = times(evs[pred][1]), times(e)
                if tp and ts and tp[0] > ts[0]:
                    errs.append(f'{where}: {eid} 必须晚于 {pred}，但开始日 {ts[0]} 早于它的 {tp[0]}')
    cyc = find_cycle(edges)
    if cyc:
        errs.append('事件先后关系有环：' + ' -> '.join(cyc))
    # 2. 人物的时间段与地点
    ivs = {}                                    # 人物 -> [(起, 止, 地点|None, 标签, 位置)]
    for eid, (where, e) in sorted(evs.items()):
        tt = times(e)
        if tt is None:
            continue
        for p in e.get('participants') or []:
            if isinstance(p, dict) and isinstance(p.get('person'), str):
                ivs.setdefault(p['person'], []).append((tt[0], tt[1], e.get('place'), eid, where))
    alive_open, death_assert, at_open = {}, {}, {}
    for where, a in assertions:
        if not _live(a):
            continue
        s, p, v = a.get('subject'), a.get('property'), a.get('value')
        if p == 'alive_at_open' and isinstance(v, bool):
            alive_open.setdefault(s, v)
        elif p == 'death_day' and isinstance(v, int) and not isinstance(v, bool):
            death_assert.setdefault(s, v)
        elif p == 'at_open' and isinstance(v, str):
            at_open.setdefault(s, v)
    for s, pl in at_open.items():
        if alive_open.get(s, True):
            ivs.setdefault(s, []).append((0, 0, pl, 'at_open', f'at_open:{s}'))
    checked_pairs = unverifiable = same_day_warn = 0
    cache = {}

    def dist(p1, p2):
        k = (p1, p2)
        if k not in cache:
            n1, n2 = _node_of(graph, parents, p1), _node_of(graph, parents, p2)
            cache[k] = None if n1 is None or n2 is None else shortest_slots(graph, n1, n2)
        return cache[k]

    for person in sorted(ivs):
        lst = sorted(ivs[person], key=lambda x: (x[0], x[1], x[3]))
        known = [x for x in lst if x[2]]
        for i in range(len(known)):
            a = known[i]
            for j in range(i + 1, len(known)):
                b = known[j]
                if b[0] > a[1]:
                    break
                if places_related(parents, a[2], b[2]):
                    continue
                overlap = min(a[1], b[1]) - max(a[0], b[0]) + 1
                tag = f'{person} 在第 {max(a[0], b[0])}–{min(a[1], b[1])} 日同时出现在 {a[2]}（{a[3]}）与 {b[2]}（{b[3]}）'
                if overlap > 1:
                    errs.append(f'{b[4]}: {tag}')
                else:
                    d = dist(a[2], b[2])
                    if d is None:
                        same_day_warn += 1
                        warns.append(f'{b[4]}: {tag}；同日、无路线信息，无法判断')
                    elif d > 12:
                        errs.append(f'{b[4]}: {tag}；两地路程需 {d} 时辰，一日走不到')
        for i in range(len(known) - 1):
            a, b = known[i], known[i + 1]
            if b[0] <= a[1] or places_related(parents, a[2], b[2]):
                continue
            d = dist(a[2], b[2])
            if d is None:
                unverifiable += 1
                continue
            checked_pairs += 1
            avail = (b[0] - a[1] + 1) * 12
            if d > avail:
                errs.append(f'{b[4]}: {person} 从 {a[2]}（{a[3]}，止于第 {a[1]} 日）到 {b[2]}（{b[3]}，始于第 {b[0]} 日）'
                            f'需 {d} 时辰，间隔至多 {avail} 时辰，路程不够')
    # 3. 死后不再出场
    die_days = {}
    for eid, (where, e) in sorted(evs.items()):
        tt = times(e)
        for op in e.get('eff') or []:
            if isinstance(op, dict) and op.get('op') == 'die' and tt:
                die_days.setdefault(op.get('person'), []).append((tt[1], eid, where))
    for person, lst in sorted(die_days.items()):
        if len(lst) > 1:
            errs.append(f'{lst[1][2]}: {person} 死了两次：{[x[1] for x in lst]}')
        d_ev = min(x[0] for x in lst)
        if person in death_assert and death_assert[person] != d_ev:
            warns.append(f'{person} 的 death_day={death_assert[person]} 与事件 {lst[0][1]} 的死亡日 {d_ev} 不一致')
    death = {p: min(x[0] for x in lst) for p, lst in die_days.items()}
    for p, d in death_assert.items():
        death.setdefault(p, d)
    for p in sorted(set(alive_open) & set(death_assert)):
        if alive_open[p] and death_assert[p] < 0:
            errs.append(f'{p}: alive_at_open=true 但 death_day={death_assert[p]} < 0')
        if not alive_open[p] and death_assert[p] >= 0:
            errs.append(f'{p}: alive_at_open=false 但 death_day={death_assert[p]} >= 0')
    for person, lst in sorted(ivs.items()):
        for (s, e_, pl, label, where) in lst:
            if label == 'at_open':
                continue
            if person in death and s > death[person]:
                errs.append(f'{where}: {person} 已于第 {death[person]} 日死亡，却出现在 {label}（始于第 {s} 日）')
            elif alive_open.get(person) is False and s >= 0 and person not in death_assert:
                errs.append(f'{where}: {person} 开局时已不在世（alive_at_open=false），却出现在 {label}（始于第 {s} 日）')
            elif alive_open.get(person) is False and s >= 0 and death_assert.get(person, -1) < 0:
                errs.append(f'{where}: {person} 开局前已去世，却出现在 {label}（始于第 {s} 日）')
    # 4/5. 秘密与认知：知情人已登记、版本键存在
    sec = {}
    for where, s in secrets:
        if isinstance(s, dict) and isinstance(s.get('id'), str):
            sec[s['id']] = (where, s)
            for k in s.get('knowers_at_open') or []:
                if not isinstance(k, dict):
                    continue
                pid = k.get('person')
                if entities is not None and pid not in entities:
                    errs.append(f'{where}: 秘密 {s["id"]} 的知情人 {pid} 未登记')
                elif entities is not None and entities.get(pid) != 'person':
                    errs.append(f'{where}: 秘密 {s["id"]} 的知情人 {pid} 不是人物')
    for eid, (where, e) in sorted(evs.items()):
        for op in e.get('eff') or []:
            if isinstance(op, dict) and op.get('op') == 'learn':
                sid, b = op.get('secret'), op.get('belief')
                if isinstance(sid, str) and sid.startswith('secret:'):
                    if sid not in sec:
                        errs.append(f'{where}: learn 引用了未登记的秘密 {sid}')
                    elif b not in S.BELIEF_SPECIAL and b not in {v.get('key') for v in sec[sid][1].get('versions') or []}:
                        errs.append(f'{where}: learn 的 belief {b!r} 不在秘密 {sid} 的 versions 里')
    info.append(f'事件 {len(evs)} 个，出场人物 {len(ivs)} 人，先后边 {sum(len(v) for v in edges.values())} 条，'
                f'路程核验 {checked_pairs} 对（无路线可核 {unverifiable} 对），同日两地待核 {same_day_warn} 处，'
                f'路线图 {len(graph)} 个节点')
    return errs, warns, info


def check_recall(entities, assertions, ids=S.RECALL_30):
    """30 人召回。ids: [(名, 编号, 分区)]。返回 (错误列表, 行列表, 完整数)。
    每人须各有 门派(org)、师承(master，作主体)、亲属(father/mother/spouse/sibling/half_sibling/kin_other，主体或值)
    的叙述者模式、非作废断言；明确没有写 "none"。"""
    has_org, has_master, has_kin = set(), set(), set()
    for _, a in assertions:
        if not _live(a):
            continue
        s, p, v = a.get('subject'), a.get('property'), a.get('value')
        if p == 'org':
            has_org.add(s)
        elif p == 'master':
            has_master.add(s)
        elif p in S.KIN_PROPS:
            has_kin.add(s)
            if isinstance(v, str) and v != 'none':
                has_kin.add(v)
    errs, lines, full = [], [], 0
    for name, pid, part in ids:
        if entities is not None and pid not in entities:
            errs.append(f'{name}（{pid}）：未登记')
            lines.append(f'  缺  {name:<6} {pid}  未登记')
            continue
        miss = [lab for lab, got in (('门派', pid in has_org), ('师承', pid in has_master), ('亲属', pid in has_kin))
                if not got]
        if miss:
            errs.append(f'{name}（{pid}）：缺 {"、".join(miss)}')
            lines.append(f'  缺  {name:<6} {pid}  缺 {"、".join(miss)}')
        else:
            full += 1
            lines.append(f'  OK  {name:<6} {pid}')
    return errs, lines, full


# ----------------------------------------------------------------------------------------------------------------------
# 检查器：装载数据、跑各节
# ----------------------------------------------------------------------------------------------------------------------
class Checker:
    def __init__(self, canon_dir=None, part=None, paths=None, strict=False, require_core=False, source=None,
                 recall_ids=None):
        self.dir = Path(canon_dir) if canon_dir else S.CANON_DIR
        self.part = part
        self.paths = paths or {}
        self.strict = strict
        self.require_core = require_core
        self.source = source
        self.recall_ids = recall_ids
        self.parse_errors = {}
        self._cache = {}
        self._entities = None
        self.merge_result = None

    # ---- 装载 ----
    def files(self, name, scoped):
        explicit = self.paths.get(name)
        if explicit:
            return S.list_jsonl_files(explicit)
        fs = []
        base = self.dir / name
        if base.is_dir():
            fs.extend(sorted(base.glob('*.jsonl')))
        if (self.dir / f'{name}.jsonl').is_file():
            fs.append(self.dir / f'{name}.jsonl')
        if scoped and self.part:
            fs = [f for f in fs if S.stem_in_part(f.stem, self.part)]
        return fs

    def load(self, name, scoped=True):
        """-> [(位置, 原始对象)]；解析错误记入 self.parse_errors[name]。"""
        key = (name, scoped and bool(self.part))
        if key in self._cache:
            return self._cache[key]
        out = []
        for f in self.files(name, scoped):
            rows, errs = S.read_jsonl(f)
            self.parse_errors.setdefault(name, []).extend(errs if scoped else [])
            out.extend((f'{f.name}:{n}', obj) for n, obj in rows)
        self._cache[key] = out
        return out

    @property
    def entities(self):
        """{编号: 类型}。优先用普查现合并（不依赖可能过期的 entities.jsonl），其次 entities.jsonl。"""
        if self._entities is None:
            self._entities = {}
            census = self.files('census', scoped=False)
            if self.paths.get('entities'):
                recs = [(f'{Path(f).name}:{n}', o) for f, n, o in S.read_records(self.paths['entities'])[0]]
                self.merge_result = M.merge_rows(recs)
            elif census:
                recs = [(f'{f.name}:{n}', o) for f in census for n, o in S.read_jsonl(f)[0]]
                self.merge_result = M.merge_rows(recs)
            elif (self.dir / 'entities.jsonl').is_file():
                recs = [(f'{f}:{n}', o) for f, n, o in S.read_records(self.dir / 'entities.jsonl')[0]]
                self.merge_result = M.merge_rows(recs)
            if self.merge_result:
                self._entities = {r['id']: r['type'] for r in self.merge_result.entities}
        return self._entities

    def ctx(self, with_events=True):
        sec_rows = self.load('secrets', scoped=False)
        ev_rows = self.load('events', scoped=False)
        secrets = {o.get('id') for _, o in sec_rows if isinstance(o, dict)} if sec_rows else None
        events = {o.get('id') for _, o in ev_rows if isinstance(o, dict)} if (with_events and ev_rows) else None
        tw = S.load_trait_words(self.paths.get('traits'))
        return S.Ctx(entities=self.entities or None, secrets=secrets, events=events,
                     trait_words=set(tw['words']) if tw else None, strict_traits=self.strict)

    def assertions(self, scoped=True):
        return [(w, S.expand_assertion(o)) for w, o in self.load('assertions', scoped)]

    def events(self, scoped=True):
        return [(w, S.expand_event(o)) for w, o in self.load('events', scoped)]

    def secrets(self, scoped=True):
        return [(w, S.expand_secret(o)) for w, o in self.load('secrets', scoped)]

    def _need_files(self, name, sec):
        if not self.files(name, True):
            sec.skipped = '没有文件' + (f'（分区 {self.part}）' if self.part else '')
            return False
        return True

    def _pe(self, name, sec):
        for e in self.parse_errors.get(name, []):
            sec.err(e)

    # ---- 各节 ----
    def census(self):
        sec = Section('census')
        files = self.files('census', True)
        if not files and not self.paths.get('census'):
            sec.skipped = '没有文件' + (f'（分区 {self.part}）' if self.part else '')
            return sec
        recs, perr = [], []
        for f in files:
            rows, e = S.read_jsonl(f)
            perr.extend(e)
            recs.extend((f'{f.name}:{n}', o) for n, o in rows)
        for e in perr:
            sec.err(e)
        ctx = S.Ctx()
        for src, o in recs:
            for e in S.validate_entity_row(o, ctx):
                sec.err(f'{src}: {e}')
        for w in ctx.warnings:
            sec.warn(w)
        full = [(f'{f.name}:{n}', o) for f in self.files('census', False) for n, o in S.read_jsonl(f)[0]] \
            if self.part else recs
        res = M.merge_rows(full)
        mine = {src for src, _ in recs}
        for c in res.conflicts:
            if c.kind == 'bad_row':
                continue                                # 已在逐行校验里报告
            if self.part and not any(x in mine for x in c.sources):
                continue
            sec.err(c.line())
        t = '，'.join(f'{k} {v}' for k, v in sorted(res.stats['by_type'].items()))
        sec.add(f'文件 {len(files)} 个，行 {len(recs)}，实体 {res.stats["entities"]}（{t}），合并冲突 '
                f'{len([c for c in res.conflicts if c.kind != "bad_row"])}')
        return sec

    def _check_pointers(self, sec, items):
        """items: [(位置, 完整断言)]。统计 basis=text 的指针有效率（有 --source 才能核对）。"""
        text_rows = [(w, a) for w, a in items if a.get('basis') == 'text']
        sec.add(f'有文本支撑（basis=text）的断言：{len(text_rows)} 条；凭记忆（basis=recall）：{len(items) - len(text_rows)} 条')
        if not text_rows:
            sec.add('证据指针有效率：不适用（有文本支撑的断言数 = 0；不会因此报“通过”，见 DECISIONS 第三节）')
            return
        if not self.source:
            sec.add(f'证据指针有效率：未核对（{len(text_rows)} 条 basis=text 的指针需要 --source 原文才能核对）')
            return
        from . import text as T
        try:
            store = T.TextStore.from_file(self.source)
        except OSError as ex:
            sec.err(f'无法读取原文 {self.source}：{ex}')
            return
        ok = bad = 0
        for w, a in text_rows:
            for p in a.get('evidence') or []:
                why = store.check_pointer(p)
                if why:
                    bad += 1
                    sec.err(f'{w}: 证据指针取不回原字：{why}')
                else:
                    ok += 1
        tot = ok + bad
        sec.add(f'证据指针有效率：{ok}/{tot}' + (f' = {100 * ok / tot:.1f}%' if tot else ''))

    def assertions_section(self, print_ids=False):
        sec = Section('assertions')
        if not self._need_files('assertions', sec):
            return sec
        items = self.assertions(True)
        self._pe('assertions', sec)
        ctx = self.ctx()
        if ctx.entities is None:
            sec.warn('没有登记表（census / entities.jsonl），未检查主体与值是否已登记')
        valid = []
        for w, a in items:
            errs = S.validate_assertion(a, ctx, '断言')
            for e in errs:
                sec.err(f'{w}: {e}')
            valid.append((w, a))
        allitems = self.assertions(False) if self.part else items
        mine = {w for w, _ in items}
        n_before = len(ctx.warnings)
        for e in S.check_assertion_set(allitems, ctx):
            if (not self.part) or any(m in e for m in mine):
                sec.err(e)
        dups = [w for w in ctx.warnings[n_before:] if '重复' in w]
        ctx.warnings = ctx.warnings[:n_before] + [w for w in ctx.warnings[n_before:] if '重复' not in w]
        if self.part:
            dups = [w for w in dups if any(m in w for m in mine)]
        for w in ctx.warnings:
            sec.warn(w)
        n_dup = len(dups)
        for w in dups[:5]:
            sec.warn(w)
        if n_dup > 5:
            sec.warn(f'……另有 {n_dup - 5} 条重复警告（同一事实在多处出现；第 6 阶段合并证据）')
        # 统计
        def cnt(key):
            d = {}
            for _, a in items:
                k = a.get(key)
                d[k] = d.get(k, 0) + 1
            return d
        rvs = {}
        for _, a in items:
            v = (a.get('reviewed') or {}).get('verdict') or 'none'
            rvs[v] = rvs.get(v, 0) + 1
        sec.add(f'断言 {len(items)} 条；等级 {cnt("rank")}；叙述方式 {cnt("mode")}；来源标签 {cnt("tag")}；复核 {rvs}；'
                f'重复（只警告）{n_dup} 条')
        self._check_pointers(sec, items)
        # 人物必含字段覆盖
        persons = self._scope_persons()
        if persons:
            core = {k: set() for k in S.CORE_PERSON_PROPS}
            dead = set()
            for _, a in self.assertions(False):
                if a.get('property') in core and _live(a):
                    core[a['property']].add(a.get('subject'))
                    if a['property'] == 'alive_at_open' and a.get('value') is False:
                        dead.add(a.get('subject'))
            for k in S.CORE_PERSON_PROPS:
                miss = sorted(p for p in persons if p not in core[k] and not (k == 'at_open' and p in dead))
                if miss:
                    msg = f'{len(miss)}/{len(persons)} 个人物缺 {k}（必含字段），例：{", ".join(miss[:3])}'
                    (sec.err if self.require_core else sec.warn)(msg)
        if print_ids:
            for w, a in items:
                sec.add(f'{a.get("id")}\t{a.get("subject")}\t{a.get("property")}\t{a.get("value")}')
        return sec

    def _scope_persons(self):
        """登记表里的人物（分区模式下只算本分区普查登记的）。"""
        if not self.entities:
            return []
        if self.part:
            ids = set()
            for f in self.files('census', True):
                for _, o in S.read_jsonl(f)[0]:
                    if isinstance(o, dict) and o.get('type') == 'person':
                        ids.add(o.get('id'))
            return sorted(ids)
        return sorted(i for i, t in self.entities.items() if t == 'person')

    def events_section(self):
        sec = Section('events')
        if not self._need_files('events', sec):
            return sec
        items = self.events(True)
        self._pe('events', sec)
        ctx = self.ctx()
        for w, e in items:
            for er in S.validate_event(e, ctx, '事件'):
                sec.err(f'{w}: {er}')
        seen = {}
        for w, e in self.events(False):
            i = e.get('id') if isinstance(e, dict) else None
            if i in seen and (not self.part or any(w == x or seen[i] == x for x, _ in items)):
                sec.err(f'{w}: 事件编号 {i} 与 {seen[i]} 重复')
            seen.setdefault(i, w)
        for w in ctx.warnings:
            sec.warn(w)
        kinds, ops = {}, {}
        for _, e in items:
            kinds[e.get('kind')] = kinds.get(e.get('kind'), 0) + 1
            for op in (e.get('pre') or []) + (e.get('eff') or []):
                if isinstance(op, dict):
                    ops[op.get('op')] = ops.get(op.get('op'), 0) + 1
        sec.add(f'事件 {len(items)} 个；类别 {kinds}；操作词使用 {dict(sorted(ops.items(), key=lambda kv: str(kv[0])))}')
        self._check_pointers_events(sec, items)
        return sec

    def _check_pointers_events(self, sec, items):
        text_rows = [x for x in items if x[1].get('basis') == 'text']
        sec.add(f'有文本支撑（basis=text）的事件：{len(text_rows)} 个；凭记忆：{len(items) - len(text_rows)} 个')

    def secrets_section(self):
        sec = Section('secrets')
        if not self._need_files('secrets', sec):
            return sec
        items = self.secrets(True)
        self._pe('secrets', sec)
        ctx = self.ctx()
        seen = {}
        for w, s in items:
            for er in S.validate_secret(s, ctx, '秘密'):
                sec.err(f'{w}: {er}')
        for w, s in self.secrets(False):
            i = s.get('id') if isinstance(s, dict) else None
            if i in seen and (not self.part or w in {x for x, _ in items}):
                sec.err(f'{w}: 秘密编号 {i} 与 {seen[i]} 重复')
            seen.setdefault(i, w)
        for w in ctx.warnings:
            sec.warn(w)
        n_know = sum(len(s.get('knowers_at_open') or []) for _, s in items if isinstance(s, dict))
        sec.add(f'秘密 {len(items)} 条，开局知情记录 {n_know} 条')
        return sec

    def identities_section(self):
        sec = Section('identities')
        if not self._need_files('identities', sec):
            return sec
        items = [(w, S.expand_identity(o)) for w, o in self.load('identities')]
        self._pe('identities', sec)
        ctx = self.ctx()
        for w, r in items:
            for er in S.validate_identity(r, ctx, '身份'):
                sec.err(f'{w}: {er}')
        kinds = {}
        for _, r in items:
            kinds[r.get('kind')] = kinds.get(r.get('kind'), 0) + 1
        sec.add(f'“以某身份出现”{len(items)} 条；类别 {kinds}')
        return sec

    def gaps_section(self):
        sec = Section('gaps')
        if not self._need_files('gaps', sec):
            return sec
        items = [(w, S.expand_gap(o)) for w, o in self.load('gaps')]
        self._pe('gaps', sec)
        ctx = self.ctx()
        for w, g in items:
            for er in S.validate_gap(g, ctx, '缺口'):
                sec.err(f'{w}: {er}')
        fills = {}
        for _, g in items:
            for f in (g.get('fill') or []) if isinstance(g.get('fill'), list) else []:
                fills[f] = fills.get(f, 0) + 1
        sec.add(f'缺口 {len(items)} 条；填补办法 {fills}')
        return sec

    def qa_section(self):
        sec = Section('qa')
        if not self._need_files('qa', sec):
            return sec
        items = self.load('qa')
        self._pe('qa', sec)
        ids = {a.get('id') for _, a in self.assertions(False)}
        for w, r in items:
            for er in S.validate_qa(r, None, ids if ids else None, '问答'):
                sec.err(f'{w}: {er}')
        if not ids:
            sec.warn('没有断言库，未核对 support 引用')
        sec.add(f'问答 {len(items)} 条')
        return sec

    def timeline_section(self):
        sec = Section('timeline')
        evs = self.events(True)
        if not evs:
            sec.skipped = '没有事件' + (f'（分区 {self.part}）' if self.part else '')
            return sec
        self._pe('events', sec)
        routes = []
        for f in ([self.paths['routes']] if self.paths.get('routes') else [self.dir / 'routes.jsonl']):
            if Path(f).is_file():
                routes.extend(o for _, o in S.read_jsonl(f)[0])
        errs, warns, info = check_timeline(evs, self.assertions(False), self.secrets(False),
                                           self.entities or None, routes)
        sec.errors.extend(errs)
        sec.warnings.extend(warns)
        sec.info.extend(info)
        return sec

    def recall_section(self):
        sec = Section('recall')
        ids = list(self.recall_ids) if self.recall_ids else list(S.RECALL_30)
        if self.part and not self.recall_ids:
            ids = [r for r in ids if r[2] == self.part]
            if not ids:
                sec.skipped = f'分区 {self.part} 没有召回名单里的人物'
                return sec
        errs, lines, full = check_recall(self.entities, self.assertions(False), ids)
        sec.errors.extend(errs)
        sec.info.append(f'{len(ids)} 人中 {full} 人门派、师承、亲属齐全')
        sec.info.extend(lines)
        return sec

    def source_path(self):
        """原文路径：显式 --source；否则仅当数据根目录是仓库默认的 data/canon 时取 sources/tianlong.txt（有才算）。"""
        if self.source:
            return Path(self.source)
        from . import text as T
        if self.dir.resolve() == S.CANON_DIR.resolve() and T.DEFAULT_SOURCE.is_file():
            return T.DEFAULT_SOURCE
        return None

    def evidence_section(self):
        """--evidence：有原文时逐条核对指针；basis=text 的行须有 >=1 条有效证据，basis=recall 的行证据须为空。"""
        sec = Section('evidence')
        src = self.source_path()
        if src is None or not Path(src).is_file():
            sec.skipped = ('没有原文，无法核对证据指针（没找到 sources/tianlong.txt；用 --source 指定）。'
                           'basis=recall 的行证据须为空仍由各节检查；原文放好后用 --evidence 重跑')
            return sec
        from . import text as T
        try:
            store = T.TextStore.from_file(src)
        except (OSError, T.TextFormatError) as ex:
            sec.err(f'无法载入原文 {src}：{ex}')
            return sec
        mf = T.default_manifest_path(self.dir)
        if mf.is_file():
            for pr in store.apply_manifest(mf)[:1]:
                sec.warn(pr)
        groups = [('断言', self.assertions(True), 'evidence'),
                  ('事件', self.events(True), 'ev'),
                  ('秘密', self.secrets(True), 'ev'),
                  ('身份', [(w, S.expand_identity(o)) for w, o in self.load('identities')], 'ev')]
        tot_ok = tot_bad = n_text = n_recall = 0
        for label, items, key in groups:
            rows = [(w, r) for w, r in items if isinstance(r, dict)]
            if not rows:
                continue
            g_text = g_recall = g_ok = g_bad = 0
            for w, r in rows:
                ev = r.get(key)
                ev = ev if isinstance(ev, list) else []
                basis = r.get('basis')
                if basis == 'recall':
                    g_recall += 1
                    if ev:
                        sec.err(f'{w}: basis=recall（凭记忆）的行证据必须为空，却有 {len(ev)} 条；有原文指针请把 basis 改为 text')
                elif basis == 'text':
                    g_text += 1
                    ok = 0
                    for p in ev:
                        why = store.check_pointer(p)
                        if why is None:
                            q = S.expand_pointer(p)
                            if q['end'] <= q['start']:
                                why = '指针取回的是空串（起 = 止）'
                        if why:
                            g_bad += 1
                            sec.err(f'{w}: 证据指针取不回原字：{why}')
                        else:
                            ok += 1
                            g_ok += 1
                    if ok == 0:
                        sec.err(f'{w}: basis=text 必须至少有 1 条有效证据指针')
            sec.add(f'{label}：{len(rows)} 行；basis=text {g_text}，basis=recall {g_recall}；'
                    f'证据指针 {g_ok + g_bad} 条，有效 {g_ok} 条')
            tot_ok, tot_bad, n_text, n_recall = tot_ok + g_ok, tot_bad + g_bad, n_text + g_text, n_recall + g_recall
        tot = tot_ok + tot_bad
        if tot:
            sec.add(f'证据指针有效率：{tot_ok}/{tot} = {100 * tot_ok / tot:.1f}%（只统计 basis=text 的行；凭记忆的行 {n_recall} 条不计）')
        else:
            sec.add(f'证据指针有效率：不适用（basis=text 的行 {n_text} 条、指针 0 条；凭记忆 {n_recall} 条）；'
                    f'不会因此报“通过”，见 DECISIONS 第三节')
        sec.add(f'原文：{Path(src).name}，{store.stats()["chapters"]} 回，{store.stats()["paragraphs"]} 段')
        return sec


# ----------------------------------------------------------------------------------------------------------------------
# 输出与入口
# ----------------------------------------------------------------------------------------------------------------------
def emit(sec, out, max_errors=30, verbose=True):
    title = f'{SECTION_TITLES[sec.name]} {sec.name}'
    if sec.skipped:
        print(f'== {title}：跳过（{sec.skipped}）', file=out)
        return
    print(f'== {title}：错误 {len(sec.errors)}，警告 {len(sec.warnings)}', file=out)
    for l in sec.info:
        print(f'  {l}', file=out)
    for e in sec.errors[:max_errors]:
        print(f'  错误：{e}', file=out)
    if len(sec.errors) > max_errors:
        print(f'  ……另有 {len(sec.errors) - max_errors} 条错误（--max-errors 调整）', file=out)
    if verbose:
        for w in sec.warnings[:max_errors]:
            print(f'  警告：{w}', file=out)
        if len(sec.warnings) > max_errors:
            print(f'  ……另有 {len(sec.warnings) - max_errors} 条警告', file=out)


def _load_recall_ids(path):
    """--recall-ids：JSON 数组（编号字符串，或 [名,编号,分区]），或每行“编号”/“名 编号”的文本。"""
    txt = Path(path).read_text(encoding='utf-8')
    try:
        data = json.loads(txt)
        out = []
        for x in data:
            out.append((x, x, '') if isinstance(x, str) else tuple(x) + ('',) * (3 - len(x)))
        return out
    except ValueError:
        out = []
        for ln in txt.splitlines():
            parts = ln.split()
            if parts:
                out.append((parts[0], parts[-1], ''))
        return out


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='canon_check', description='原著 -> 数据 综合校验（docs/CANON_SCHEMA.md）')
    ap.add_argument('--census', nargs='?', const='', metavar='DIR_OR_FILE', help='普查登记行（含合并冲突）')
    ap.add_argument('--assertions', nargs='?', const='', metavar='FILE|DIR', help='断言')
    ap.add_argument('--events', nargs='?', const='', metavar='FILE', help='事件')
    ap.add_argument('--secrets', nargs='?', const='', metavar='FILE', help='秘密登记')
    ap.add_argument('--identities', nargs='?', const='', metavar='FILE', help='“以某身份出现”')
    ap.add_argument('--gaps', nargs='?', const='', metavar='FILE', help='缺口表')
    ap.add_argument('--qa', nargs='?', const='', metavar='FILE', help='标准问答集')
    ap.add_argument('--timeline', action='store_true', help='时间线综合检查')
    ap.add_argument('--recall', action='store_true', help='30 人召回')
    ap.add_argument('--evidence', action='store_true',
                    help='证据指针：有原文时逐条核对（basis=text 须有 >=1 条有效证据，basis=recall 须为空）；没有原文只提示')
    ap.add_argument('--all', action='store_true', help='全部（不给任何子命令时的默认）')
    ap.add_argument('--part', metavar='NAME', help=f'只跑某分区的文件：{" ".join(S.PART_NAMES)} 或 ch00–ch52；'
                                                   f'p1–p4 同时圈住范围内的按回文件')
    ap.add_argument('--canon-dir', default=str(S.CANON_DIR), help='数据根目录（默认 data/canon）')
    ap.add_argument('--entities', help='显式指定登记表（文件或目录），代替普查合并')
    ap.add_argument('--routes', help='路线表 JSONL：{"a","b","slots"}')
    ap.add_argument('--traits', help='性格词表 JSON（默认 data/canon/trait_words.json）')
    ap.add_argument('--source', help='原文文本：核对 basis=text 的证据指针')
    ap.add_argument('--recall-ids', help='覆盖 30 人名单（JSON 数组或文本行），测试用')
    ap.add_argument('--strict', action='store_true', help='未收录的性格词按错误处理')
    ap.add_argument('--require-core', action='store_true', help='人物缺 at_open / alive_at_open 按错误处理')
    ap.add_argument('--ids', action='store_true', help='列出每条断言的编号')
    ap.add_argument('--max-errors', type=int, default=30)
    ap.add_argument('--quiet', action='store_true', help='不打印警告')
    ap.add_argument('--json', action='store_true', help='以 JSON 输出汇总')
    a = ap.parse_args(argv)
    if a.part and not S.is_part_name(a.part):
        print(f'未知分区 {a.part!r}；可用：{" ".join(S.PART_NAMES)} 或 ch00–ch52', file=out)
        return 2
    sel = {k: getattr(a, k) for k in ('census', 'assertions', 'events', 'secrets', 'identities', 'gaps', 'qa')}
    run = {k for k, v in sel.items() if v is not None}
    if a.timeline:
        run.add('timeline')
    if a.recall:
        run.add('recall')
    if a.evidence:
        run.add('evidence')
    if a.all or not run:
        run = set(ORDER)
    paths = {k: v for k, v in sel.items() if v}
    for k in ('entities', 'routes', 'traits'):
        if getattr(a, k):
            paths[k] = getattr(a, k)
    for k, v in paths.items():
        if k not in ('traits',) and not Path(v).exists():
            print(f'路径不存在：--{k} {v}', file=out)
            return 2
    rids = _load_recall_ids(a.recall_ids) if a.recall_ids else None
    ck = Checker(a.canon_dir, a.part, paths, a.strict, a.require_core, a.source, rids)
    secs = []
    for name in ORDER:
        if name not in run:
            continue
        if name == 'census':
            secs.append(ck.census())
        elif name == 'assertions':
            secs.append(ck.assertions_section(a.ids))
        elif name == 'events':
            secs.append(ck.events_section())
        elif name == 'secrets':
            secs.append(ck.secrets_section())
        elif name == 'identities':
            secs.append(ck.identities_section())
        elif name == 'gaps':
            secs.append(ck.gaps_section())
        elif name == 'qa':
            secs.append(ck.qa_section())
        elif name == 'timeline':
            secs.append(ck.timeline_section())
        elif name == 'recall':
            secs.append(ck.recall_section())
        elif name == 'evidence':
            secs.append(ck.evidence_section())
    n_err = sum(len(s.errors) for s in secs)
    n_warn = sum(len(s.warnings) for s in secs)
    if a.json:
        print(json.dumps({'part': a.part, 'errors': n_err, 'warnings': n_warn,
                          'sections': {s.name: {'skipped': s.skipped, 'errors': s.errors[:a.max_errors],
                                                'n_errors': len(s.errors), 'n_warnings': len(s.warnings),
                                                'info': s.info} for s in secs}},
                         ensure_ascii=False, indent=1), file=out)
    else:
        for s in secs:
            emit(s, out, a.max_errors, not a.quiet)
        scope = f'（分区 {a.part}）' if a.part else ''
        print(f'汇总{scope}：检查 {len([s for s in secs if not s.skipped])} 节，跳过 {len([s for s in secs if s.skipped])} 节；'
              f'错误 {n_err}，警告 {n_warn} -> ' + ('通过' if n_err == 0 else '未通过'), file=out)
    return 0 if n_err == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
