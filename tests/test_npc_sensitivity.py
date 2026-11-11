"""规格里的每个数都在起作用：改一个数，世界就要有可见的变化。

为什么要这条：哈希只管“谁在哪、发生了什么事”，一个常数抄错了、或引擎悄悄不读它了，只要没改变这两样，
哈希与逐行日志都发现不了（例如“举报概率”那一支，基准、90 日、种子 1 里一次也没走到）。这里换一个办法：
把 SiteSpec 里每个数值字段逐个改动（每个字段试三种改法：+1 或 ×1.25、×3+7 或 ×4+0.5、减半），
在若干场景里重跑，用一个比哈希细得多的指纹（需求、想法、见闻、好恶修正项、案卷、统计、传闻曲线、层号……）
比对；只要有一个场景的指纹变了，这个数就“活着”。

* 默认（快）：对一份手挑的关键数字（举报概率、认错、起念、传闻……）逐个验证它们活着；
  再对“基准世界里碰不到”的十个字段（FORMERLY_UNREACHED）各用一个专门的场景验证它们活着（一次改动、一次重跑）。
* TIANL_SLOW=1：对全部数值字段做普查（约 350 个，多进程，约 1 分钟）。普查之后仍没有可见效果的字段，必须逐个写在
  UNREACHED 里并说明为什么——这是一份诚实的清单：它们在这些场景里没有被触及（容量不吃紧、保护线从不越过……），
  不是“已验证无误”。清单变短或变长都要改这里，不许悄悄放过。（现有 13 个，见 UNREACHED：12 个季节表项与刚正的下限。）

规格由 defs 构造（proto60_spec()），行为包与交互也是规格里的数据（字段路径形如 stack.9.params.k、interactions.sick.effects.e、
ads.5.gate_params.slots.2）：包里的每个参数、每个时辰、每个日子条件，交互里的每个需求增减，都在普查之列。

场景（SCENARIOS）分两类。前五个是原型世界（N1 无人代理、传闻脚本、90 日、种子 4 的 90 日、种子 34 的 N1），规格就是 proto60_spec()。
后四个是为“基准世界里碰不到的字段”专门造的：先把规格改成一个更挤、更累、更记仇的世界（TRANSFORMS），再在这个世界上逐个改字段：
tight（工位稀缺、未登记容量的场所按默认值、功课挪到未时让申时空出来、夜里更容易起念）、weary（困与饿的消耗加重）、
grudge（好恶放大数倍、处分阶梯里连着杖责）、emit（不跑世界，直接发一遍每种事件看见闻强度）。它们不改引擎，只改规格——
所以“改一个数、世界就变”在这里仍然只说明引擎读了这个数。
"""
import dataclasses
import hashlib
import multiprocessing
import os
import time
import unittest

from tianl.core import rnd_b2
from tianl.npc import NpcEngine, ProtoRun, StandaloneHost, proto60_spec
from tianl.npc import events as E
from tianl.npc.scenarios import PROTO_SEED, gossip_script, n1_script, proto60_roster
from tianl.npc.spec import SpecError
from tests.test_npc_support import pkg_index, with_params, with_when

R = dataclasses.replace
PROTOTYPE_SCENARIOS = ('n1', 'base', 'd90', 'd90s4', 's34')       # 由便宜到贵；N1 无人代理里举报、传讯、处分最密
STRESS_SCENARIOS = ('tight', 'weary', 'grudge', 'emit')            # 专为基准世界碰不到的字段造的世界（见模块说明）
SCENARIOS = PROTOTYPE_SCENARIOS + STRESS_SCENARIOS


def tight(sp):
    """工位稀缺：功课挪到未时（申时空出来，藏经阁的第三个开阁时辰才有人用）、禅堂只有 3 个座、
    浴室与井台没登记容量（按默认值 4 算）、夜里更容易起念偷食（巡夜才会记下空铺）。"""
    sp = R(sp, capacity={'lib': 3, 'yard': 5, 'zen': 3, 'clo': 10}, cap_default=4)
    for name in ('tempted_night', 'tempted_afternoon'):                     # 夜里与午后的起念共用一套门槛
        sp = with_params(sp, name, th_base=70, s_line=70)
    for name in ('class_martial', 'class_study', 'class_zazen'):            # 功课挪到未时（7）
        sp = with_when(sp, name, slots=(7,))
    return sp


def weary(sp):
    """困、饿、孤都消耗得更快：卧病一时辰补的“困”才不会被封顶盖住。"""
    base = dict(sp.needs.base)
    return R(sp, needs=R(sp.needs, base={**base, 'e': -18.0, 'h': -9.0, 's': -2.5}))


def grudge(sp):
    """记仇的世界：好恶的底数放大（碰得到上下限）；处分阶梯连着杖责，“受杖”想法才会叠到上限。"""
    o, st = sp.opinion, sp.ladder[1]
    sp = R(sp, opinion=R(o, same_dorm=o.same_dorm * 6, same_track=o.same_track * 6, same_post=o.same_post * 6,
                         compat_w=o.compat_w * 8))
    return R(sp, ladder=(R(sp.ladder[0], thought='flogged'), R(st, kneel_days=0, conf_days=1), R(st, conf_days=1)))


TRANSFORMS = {'tight': tight, 'weary': weary, 'grudge': grudge}     # 其余场景的规格就是原规格


def leaves(o, path=()):
    """SiteSpec 里所有数值叶子：(路径, 值)。路径元素：('f', 字段名) | ('k', 字典键) | ('i', 序号)。"""
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        for f in dataclasses.fields(o):
            yield from leaves(getattr(o, f.name), path + (('f', f.name),))
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from leaves(v, path + (('k', k),))
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o):
            yield from leaves(v, path + (('i', i),))
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield path, o


def dotted(path):
    return '.'.join(str(key) for _, key in path)


def setpath(o, path, new):
    """返回 o 的副本，路径上的那个叶子换成 new（SiteSpec 是冻结的，所以逐层 replace）。"""
    if not path:
        return new
    kind, key = path[0]
    if kind == 'f':
        return dataclasses.replace(o, **{key: setpath(getattr(o, key), path[1:], new)})
    if kind == 'k':
        d = dict(o)
        d[key] = setpath(o[key], path[1:], new)
        return d
    lst = list(o)
    lst[key] = setpath(o[key], path[1:], new)
    return tuple(lst)


def variants(v):
    """三种改法：小幅加、大幅放大、减半（概率会翻过去，容量会收紧）。"""
    if isinstance(v, int):
        out = [v + 1, v * 3 + 7]
        if v // 2 != v:
            out.append(v // 2)
    else:
        out = [v * 1.25 + 0.01, v * 4 + 0.5]
        if v:
            out.append(v * 0.5)
    return out


def fingerprint(run):
    """比哈希细得多的指纹：哈希、统计、每人的需求/想法/见闻/案底、好恶修正项、案卷、库存、传闻、层号加权和、好友。"""
    e = run.engine
    h = hashlib.sha256()

    def put(x):
        h.update(repr(x).encode())
    put(run.hash)
    put(sorted(e.stat.items()))
    for p in e.people:
        put((p.need, p.thoughts, sorted(p.news.items()), p.offences, p.kneel, p.conf, p.ill, p.absent, p.slackd,
             p.pending, p.gone, p.duty_day, p.lazy_day))
    put(sorted(e.opinions.mods.items()))
    put((e.stock, sorted(e.kit_staff.items()), e.daily, e.rumor.curve, e.rumor.cum, sorted(e.rumor.hops.items()),
         e.moodlow, e.pd, sorted(e.choice.items()), {k: sorted(v.items()) for k, v in e.acts.items()},
         sorted(e.att.items()), sorted(e.att_exp.items())))
    put([(c['eid'], c['state'], c['via'], c['sanction']) for c in e.cases()])
    put(sum(e.spec.layer_rank[lay] * e.stat['pkg_' + lay] for lay in e.spec.layer_rank))     # 层号只有这里读
    put(e.friends())
    put([round(e.opinion(a.ix, b.ix), 9) for a in e.people for b in e.people if a is not b])      # 好恶的实际值（好友线之外的变化也看得见）
    return h.hexdigest()[:16]


def emit_fingerprint(spec):
    """不跑世界：对每种事件各发一条（两个见证人），看见闻强度。事件显著度只在 NpcEngine.emit 里读，
    而举报事件没有见证人、夜不在寮只有巡夜者且当日就衰减掉，所以这两个数只能这样直接看。"""
    eng = NpcEngine(spec, StandaloneHost(PROTO_SEED, rnd_b2))
    for ps in proto60_roster(spec, 5):
        eng.add_person(ps)
    for kind in E.EMITTED:
        eng.emit(kind, 0, spec.kitchen.place, [1, 2], 1, 0)
    return repr([sorted(p.news.items()) for p in eng.people])


def run_scenario(spec, kind):
    r0 = ProtoRun()
    if kind == 'base':
        return fingerprint(ProtoRun(spec=spec, script=gossip_script(r0.engine.common)).run())
    if kind == 'n1':
        return fingerprint(ProtoRun(spec=spec, script=n1_script(r0.engine), acting=False).run())
    if kind == 'd90':
        return fingerprint(ProtoRun(spec=spec, days=90).run())
    if kind == 'd90s4':
        return fingerprint(ProtoRun(spec=spec, days=90, seed=4).run())
    if kind == 's34':                                      # 种子 34 的 N1 无人代理：“反应”层（去戒律院举报）只在这里生效
        return fingerprint(ProtoRun(spec=spec, seed=34, days=40, script=n1_script(r0.engine), acting=False).run())
    if kind in ('tight', 'weary'):
        return fingerprint(ProtoRun(spec=spec, days=20, script=n1_script(r0.engine), acting=False).run())
    if kind == 'grudge':
        return fingerprint(ProtoRun(spec=spec, days=40, script=n1_script(r0.engine), acting=False).run())
    if kind == 'emit':
        return emit_fingerprint(spec)
    raise KeyError(kind)


SPEC = proto60_spec()
LEAF = {dotted(p): (p, v) for p, v in leaves(SPEC)}        # 点分路径 -> (路径, 原值)
BASE_SPEC = {k: TRANSFORMS.get(k, lambda sp: sp)(SPEC) for k in SCENARIOS}      # 场景名 -> 这个场景里“改之前”的规格
_BASE = {}                                                 # 场景名 -> 原规格的指纹（fork 之前在父进程算好）


def baseline(kinds=SCENARIOS):
    for k in kinds:
        if k not in _BASE:
            _BASE[k] = run_scenario(BASE_SPEC[k], k)
    return _BASE


def probe(item, kinds=SCENARIOS):
    """item = (路径, 原值)。返回 (点分路径, 值, 状态, 第一个看到变化的场景)：
    live：某种改法在某个场景里指纹变了；checked：没有可见变化，但有改法被 SiteSpec.validate() 拒绝（字段受校验）；
    dead：三种改法在所有场景里都没有可见变化；crash：改动让引擎抛了别的异常（不应该发生）。"""
    path, v = item
    base = baseline(kinds)
    rejected = False
    for var in variants(v):
        for k in kinds:
            try:
                changed = setpath(BASE_SPEC[k], path, var)
            except (KeyError, IndexError):                # 这个场景的规格里没有这个字段（例如 tight 没登记浴室容量）
                continue
            try:
                h = run_scenario(changed, k)
            except SpecError:
                rejected = True
                break
            except Exception as ex:                       # noqa: BLE001 —— 任何别的异常都算“崩了”，由测试报出来
                return dotted(path), v, 'crash', '%s: %s' % (type(ex).__name__, ex)
            if h != base[k]:
                return dotted(path), v, 'live', k
    return dotted(path), v, 'checked' if rejected else 'dead', None


def _probe_all(item):
    return probe(item)


def _probe_prototype_worlds(item):
    return probe(item, PROTOTYPE_SCENARIOS)


def _probe_critical(item):
    return probe(item, CRITICAL_SCENARIOS)


def _changed_fingerprint(item):
    """(字段, 场景, 改成的值) -> 改动之后该场景的指纹。"""
    name, kind, var = item
    path, _ = LEAF[name]
    return run_scenario(setpath(BASE_SPEC[kind], path, var), kind)


def pool_map(fn, items):
    """多进程（fork：父进程里算好的基线各子进程共享）；没有 fork 的平台退回串行。"""
    if 'fork' in multiprocessing.get_all_start_methods():
        with multiprocessing.get_context('fork').Pool(min(4, os.cpu_count() or 1)) as pool:
            return pool.map(fn, items, chunksize=1)
    return [fn(it) for it in items]


# 手挑的关键数字：基准哈希对它们不敏感或只在个别场景里敏感（举报概率、认错、起念、传闻……）。默认就验证它们活着。
def _pkg(name, tail):
    """行为包某个字段的点分路径：包在栈里的下标由名字查。"""
    return 'stack.%d.%s' % (pkg_index(SPEC, name), tail)


CRITICAL = ('report.base', 'report.r_w', 'report.lo', 'cases.confess_r', 'cases.stale_days', _pkg('tempted_night', 'params.k'),
            'rumor.p_add', 'inventory.p_find', _pkg('slack', 'params.low_mood_add'), 'jobs.work_chat_p')
CRITICAL_SCENARIOS = ('n1',)                               # 它们在 N1 无人代理里都看得出来；普查才用全部场景

# 只用原型世界（PROTOTYPE_SCENARIOS）时看不出变化的十个字段：逐个说明为什么碰不到。它们要在 STRESS_SCENARIOS 里才显出差别
# （FORMERLY_UNREACHED 给出每个字段用哪个场景、改成什么）。慢测试断言这份清单：在原型世界里它们确实是死的，在加上专门场景后确实活。
AD_OF = {a.act: i for i, a in enumerate(SPEC.ads)}                     # 广告在 ads 里的下标
LIB_SLOT_2 = 'ads.%d.gate_params.slots.2' % AD_OF['study']              # 经阁的第三个开阁时辰（交互 admission 的参数）
PROTOTYPE_DEAD = {
    'capacity.zen': '禅堂 70 个工位：自由时段同时坐禅的人不到 35，容量不吃紧（改成 10 以下才显出差别）',
    'cap_default': '未登记容量的场所按 999 算：自由时段与功课只会查登记过容量的场所（改成 1 也没有差别）',
    LIB_SLOT_2: '藏经阁第三个开阁时辰（申）：申时几乎没人处于自由时段（30 日里 30 次，没有一次选读经），'
                       '清众的读经走“身份”层，不看这道门',
    'interactions.sick.effects.e': '卧病一时辰的“困”增量：病人夜里睡满，“困”早已封顶 100（降到 0 以下才显出差别）',
    'opinion.lo': '好恶下限：好恶实际落在约 -40 到 43 之间，碰不到 -50（改到 -10 才显出差别）',
    'opinion.hi': '好恶上限：同上，碰不到 50（改到 30 才显出差别）',
    'thoughts.flogged.cap': '“受杖”想法同时最多几条：每人一生只被杖责一次（阶梯只有一级杖责），上限碰不到',
    'thoughts.warned_bed.cap': '“受训诫（夜不在寮）”想法同时最多几条：三日内没人被记两次以上空铺（改成 0 才显出差别）',
    'salience.REPORT': '举报事件没有见证人，见闻强度无处可记（改成 100 也没有差别）',
    'salience.BED_EMPTY': '夜不在寮的见证人是巡夜者：强度 1、7 都低于外传下限 25，当日就衰减没了（改成 50 才显出差别）',
}
# 这十个字段各在哪个专门场景里、改成什么值时显出差别（默认就验证：一次改动、一次重跑）。
FORMERLY_UNREACHED = {
    'capacity.zen': ('tight', 71),
    'cap_default': ('tight', 1000),
    LIB_SLOT_2: ('tight', 9),
    'interactions.sick.effects.e': ('weary', 17),
    'opinion.lo': ('grudge', -99),
    'opinion.hi': ('grudge', 101),
    'thoughts.flogged.cap': ('grudge', 1),
    'thoughts.warned_bed.cap': ('tight', 1),
    'salience.REPORT': ('emit', 1),
    'salience.BED_EMPTY': ('emit', 1),
}
# 加上专门场景之后，普查仍看不出变化的字段：逐个说明（共 13 个）。它们在这些场景里没有被触及，不是“已验证”。
SEASON_WHY = ('季节表（行为包 when.season 的词表）：原型场景里没有包用季节，且 20–40 日的场景只走到正月（春），'
              '夏秋冬与春的后两个月从没被日历走到——when.season 本身的行为由 tests/test_npc_defs.py 的 CalendarKeys 验证')
UNREACHED = {'seasons.%s.%d' % (name, i): SEASON_WHY for name in '春夏秋冬' for i in range(3)}
UNREACHED['traits.lo.R'] = ('刚正的下限 5：原型这 60 人（种子 20261110 的开局）里没有人的刚正低到被夹到 5'
                            '（精进、守戒、合群、馋的下限与四项的上限都有人碰到；性格按 (种子, 键, ix) 抽，换种子或加人就可能碰到）')


class CriticalNumbersMatter(unittest.TestCase):
    """默认就跑：手挑的关键数字，改动后世界必须有可见变化。"""

    @classmethod
    def setUpClass(cls):
        cls.leaf = LEAF

    def test_leaf_enumeration_sees_the_whole_spec(self):
        self.assertGreater(len(self.leaf), 300)
        for name in CRITICAL + tuple(UNREACHED) + tuple(PROTOTYPE_DEAD) + tuple(FORMERLY_UNREACHED):
            self.assertIn(name, self.leaf, '清单里的 %s 不是规格里的数值字段' % name)
        self.assertEqual(set(PROTOTYPE_DEAD), set(FORMERLY_UNREACHED))
        self.assertTrue(set(FORMERLY_UNREACHED.values()) and all(k in STRESS_SCENARIOS for k, _ in FORMERLY_UNREACHED.values()))

    def test_fingerprint_is_deterministic_and_finer_than_the_hash(self):
        self.assertEqual(run_scenario(SPEC, 'n1'), run_scenario(SPEC, 'n1'))
        # 好恶/想法的数值变了而哈希（决定与事件）没变：指纹抓得到，哈希抓不到
        spec = dataclasses.replace(SPEC, thoughts={**SPEC.thoughts, 'sanction': dataclasses.replace(
            SPEC.thoughts['sanction'], value=SPEC.thoughts['sanction'].value - 1)})
        a, b = ProtoRun(script=n1_script(ProtoRun().engine), acting=False).run(), \
            ProtoRun(spec=spec, script=n1_script(ProtoRun().engine), acting=False).run()
        self.assertEqual(a.hash, b.hash)
        self.assertNotEqual(fingerprint(a), fingerprint(b))

    def test_critical_numbers_are_live(self):
        t0 = time.perf_counter()
        baseline(CRITICAL_SCENARIOS)                       # 父进程先算好，再 fork
        for got in pool_map(_probe_critical, [self.leaf[name] for name in CRITICAL]):
            name, v, status, where = got
            self.assertEqual(status, 'live', '%s = %r 改动后任何场景都没有可见变化（%s）' % (name, v, status))
        print('\n[关键数字] %d 个全部活着，%.1f 秒' % (len(CRITICAL), time.perf_counter() - t0))


class FormerlyUnreachedNumbersMatter(unittest.TestCase):
    """默认就跑：基准世界里碰不到的十个字段，在各自的专门场景里改一次、重跑一次，指纹必须变。"""

    def test_each_has_a_world_where_it_matters(self):
        t0 = time.perf_counter()
        items = [(name, kind, var) for name, (kind, var) in FORMERLY_UNREACHED.items()]
        base = baseline(sorted({kind for _, kind, _ in items}))      # 每个专门场景算一次“改之前”（父进程里，再 fork）
        for (name, kind, var), got in zip(items, pool_map(_changed_fingerprint, items)):
            self.assertNotEqual(var, LEAF[name][1])
            self.assertNotEqual(got, base[kind], '%s 改成 %r 之后场景 %s 的指纹没有变' % (name, var, kind))
        print('\n[原先碰不到的字段] %d 个都在专门场景里活着，%.1f 秒' % (len(items), time.perf_counter() - t0))

    def test_the_stress_worlds_are_only_spec_changes(self):
        """专门场景只是换了规格（不改引擎），并且换完仍通过 validate()；它们各自与原规格确有不同。"""
        for kind in STRESS_SCENARIOS:
            self.assertEqual(BASE_SPEC[kind].validate(), [], kind)
        for kind in TRANSFORMS:
            self.assertNotEqual(BASE_SPEC[kind], SPEC, kind)
        for kind in PROTOTYPE_SCENARIOS:
            self.assertIs(BASE_SPEC[kind], SPEC, kind)

    def test_emit_scenario_reads_exactly_the_salience_table(self):
        """emit 场景：每种事件各发一条，见闻强度就是规格里的显著度；显著度为 0 的事件不记见闻。"""
        eng = NpcEngine(SPEC, StandaloneHost(PROTO_SEED, rnd_b2))
        for ps in proto60_roster(SPEC, 5):
            eng.add_person(ps)
        for kind in E.EMITTED:
            eng.emit(kind, 0, SPEC.kitchen.place, [1, 2], 1, 0)
        for i in (1, 2):
            got = {eng.evs[e].kind: v[0] for e, v in eng.people[i].news.items()}
            self.assertEqual(got, {k: v for k, v in SPEC.salience.items() if v > 0})
        self.assertEqual(eng.people[0].news, {})                 # 当事人自己不因此得见闻


@unittest.skipUnless(os.environ.get('TIANL_SLOW'), '慢测试：TIANL_SLOW=1 打开')
class PrototypeWorldsAloneLeaveTenFieldsDead(unittest.TestCase):
    def test_every_scenario_is_deterministic(self):
        """“改动后指纹变了”才说明引擎读了这个数，前提是同一规格重跑指纹不变：九个场景各重跑一次核对。"""
        base = baseline()
        for kind in SCENARIOS:
            self.assertEqual(run_scenario(BASE_SPEC[kind], kind), base[kind], '场景 %s 不确定' % kind)

    def test_the_ten_fields_are_dead_in_the_prototype_worlds(self):
        """诚实记录的可执行版：只用五个原型世界，这十个字段确实看不出变化；专门场景才让它们显形。"""
        baseline(PROTOTYPE_SCENARIOS)
        for got in pool_map(_probe_prototype_worlds, [LEAF[name] for name in PROTOTYPE_DEAD]):
            # 'checked'（有的改法被 validate() 拒绝，其余改法看不出变化）同样是“没有可见效果”；只有 live 才说明它在原型世界里已经显形
            self.assertNotEqual(got[2], 'live', '%s 在原型世界里已经有可见效果了：%r' % (got[0], got))


@unittest.skipUnless(os.environ.get('TIANL_SLOW'), '慢测试：TIANL_SLOW=1 打开')
class EverySpecNumberMatters(unittest.TestCase):
    def test_audit_of_every_numeric_field(self):
        items = list(leaves(SPEC))
        baseline()                                         # 在父进程算好，fork 之后各子进程共享
        t0 = time.perf_counter()
        res = pool_map(_probe_all, items)
        by = {}
        for name, v, status, where in res:
            by.setdefault(status, []).append((name, v, where))
        print('\n[普查] %d 个数值字段，%.0f 秒：活 %d、受校验 %d、无可见效果 %d、崩 %d' % (
            len(res), time.perf_counter() - t0, len(by.get('live', ())), len(by.get('checked', ())),
            len(by.get('dead', ())), len(by.get('crash', ()))))
        self.assertEqual(by.get('crash', []), [], '改动规格让引擎抛了别的异常')
        dead = {name for name, v, where in by.get('dead', [])}
        self.assertEqual(sorted(dead - set(UNREACHED)), [], '新出现的“无可见效果”字段：要么修，要么写进 UNREACHED 并说明')
        self.assertEqual(sorted(set(UNREACHED) - dead), [], 'UNREACHED 里的字段现在有可见效果了：请从清单里删掉')
        self.assertEqual(sorted(set(PROTOTYPE_DEAD) & dead), [], '专门场景加上之后，这些字段应当已经显形')
        self.assertGreater(len(by.get('live', ())), 300)
        for name, v, where in by.get('dead', []):
            print('  无可见效果 %-28s = %-8r %s' % (name, v, UNREACHED.get(name, '')))


if __name__ == '__main__':
    unittest.main()
