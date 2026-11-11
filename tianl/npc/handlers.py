"""登记表：行为包与准入门里“需要条件判断”的部分，按名字引用（ARCHITECTURE 第 6 节：包里写 handler = "<名>" + params）。

两张表：
  PACKAGE_HANDLERS  行为包处理器。包定义写 handler = "<名>"、params = {…}；声明式的包（只有 do）不需要处理器。
                    处理器是一个函数 fn(stack, pkg, p, day, slot, ctx) -> 决定四元组 | None（None = 不成立，交给栈里的下一个包）；
                    巡寮者的决定多带第五项“所巡之处”（见 patrol_duty）。可选的 begin 钩子 fn(eng, pkg, day) 在每日开始（begin_day）时调用。
  GATES             准入门。交互的 admission = { gate = "<名>", … } 里其余的键是它的参数；fn(eng, p, day, slot, params) -> bool。

每个处理器 / 准入门都登记一张参数表（Param：名字、类型、必填或默认值、取值范围）：defs 构造规格时按表校验与规范化，
SiteSpec.validate() 再按同一张表查一遍。登记表还写明处理器只能带哪些层（layers）、用到哪些活动（acts）——规格自检据此核对。
参数的默认值（Param(default=…)）是这里唯一允许出现的数字；原型场景的每个数都写在 defs 里，不靠默认值。
"""
from dataclasses import dataclass
from typing import Callable, Optional

from ..core import SLOTS_PER_DAY
from .spec import (A_GUARD, A_MEAL, A_PATROL, A_SLEEP, A_WORK, L_DEVIANT, L_DUTY, L_ERRAND, L_FORCED, L_FREE, L_PENALTY,
                   L_PHYS, L_REACT, L_SLACK)

REQUIRED = object()                 # Param 的“必填”哨兵


@dataclass(frozen=True)
class Param:
    """处理器 / 准入门的一个参数。type：int float str bool slots（时辰列表）strs place post posts act。"""
    name: str
    type: str
    default: object = REQUIRED
    choices: tuple = ()
    lo: Optional[float] = None
    hi: Optional[float] = None
    doc: str = ''

    @property
    def required(self):
        return self.default is REQUIRED


@dataclass(frozen=True)
class HandlerDef:
    name: str
    fn: Callable
    params: tuple
    layers: tuple                   # 这个处理器只能带的层标签
    acts: tuple                     # 它会产出的活动（规格自检要求交互里有它们）
    begin: Optional[Callable]       # 每日开始的钩子 fn(eng, pkg, day)，没有就是 None
    who_office: bool                # True：包的 who 必须正是 org:patrol 的岗位（巡寮）
    doc: str


PACKAGE_HANDLERS = {}
GATES = {}
GATE_PARAMS = {}


def package_handler(name, params=(), layers=(), acts=(), begin=None, who_office=False):
    def deco(fn):
        PACKAGE_HANDLERS[name] = HandlerDef(name, fn, tuple(params), tuple(layers), tuple(acts), begin, who_office,
                                            (fn.__doc__ or '').strip())
        return fn
    return deco


def gate(name, params=()):
    def deco(fn):
        GATES[name] = fn
        GATE_PARAMS[name] = tuple(params)
        return fn
    return deco


# ---------------------------------------------------------------- 参数校验
class ParamCtx:
    """参数里的引用要对得上的那些表：场所、岗位、活动（取自一份 SiteSpec）。"""

    def __init__(self, spec):
        self.places = spec.places
        self.offices = {o.name for o in spec.offices}
        self.acts = spec.interactions


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_value(p, v, ctx):
    """一个参数值合不合 Param 的要求；返回问题文字或 None。"""
    t = p.type
    if t == 'int':
        ok = isinstance(v, int) and not isinstance(v, bool)
    elif t == 'float':
        ok = _num(v)
    elif t == 'str':
        ok = isinstance(v, str)
    elif t == 'bool':
        ok = isinstance(v, bool)
    elif t == 'slots':
        ok = isinstance(v, tuple) and all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x < SLOTS_PER_DAY for x in v)
        if not ok:
            return '参数 %s 应是时辰（0–%d）的列表，得到 %r' % (p.name, SLOTS_PER_DAY - 1, v)
    elif t == 'strs':
        ok = isinstance(v, tuple) and all(isinstance(x, str) for x in v)
    elif t == 'place':
        if v not in ctx.places:
            return '参数 %s：场所 %r 不在 places 里' % (p.name, v)
        ok = True
    elif t == 'post':
        if v not in ctx.offices:
            return '参数 %s：岗位 %r 未登记' % (p.name, v)
        ok = True
    elif t == 'posts':
        bad = [x for x in v if x not in ctx.offices] if isinstance(v, tuple) else None
        if bad is None:
            return '参数 %s 应是岗位列表，得到 %r' % (p.name, v)
        if bad:
            return '参数 %s：岗位 %s 未登记' % (p.name, '、'.join(map(repr, bad)))
        ok = True
    elif t == 'act':
        if v not in ctx.acts:
            return '参数 %s：活动 %r 没有对应的交互' % (p.name, v)
        ok = True
    else:
        return '登记表里的参数 %s 有未知类型 %r' % (p.name, t)
    if not ok:
        return '参数 %s 应是 %s，得到 %r' % (p.name, t, v)
    if p.choices and v not in p.choices:
        return '参数 %s 只能是 %s，得到 %r' % (p.name, '/'.join(map(repr, p.choices)), v)
    if p.lo is not None and _num(v) and v < p.lo:
        return '参数 %s = %r 小于下限 %r' % (p.name, v, p.lo)
    if p.hi is not None and _num(v) and v > p.hi:
        return '参数 %s = %r 大于上限 %r' % (p.name, v, p.hi)
    return None


def check_params(schema, params, ctx):
    """已规范化的 params（引用已换成 code / 岗位名，列表已是元组，默认值已补齐）对照参数表：返回问题列表。"""
    out = []
    names = {p.name for p in schema}
    for k in params:
        if k not in names:
            out.append('未知参数 %s（可用：%s）' % (k, '、'.join(sorted(names)) or '无'))
    for p in schema:
        if p.name not in params:
            out.append('缺少参数 %s' % p.name)
            continue
        msg = check_value(p, params[p.name], ctx)
        if msg:
            out.append(msg)
    return out


# ---------------------------------------------------------------- 准入门（交互的 admission）
@gate('lib_open', params=(Param('office', 'post', doc='管阁的岗位：它在，经阁才开'),
                          Param('slots', 'slots', doc='开阁时辰')))
def lib_open(eng, p, day, slot, params):
    """经阁开放：在开阁时辰，且管阁的岗位有人在任、没病。"""
    z = eng.by.get(params['office'])
    if not z:
        return False
    return slot in params['slots'] and eng.people[z[0]].ill < day


@gate('bath_day', params=(Param('every', 'int', lo=1, doc='每几日开浴一次'), Param('phase', 'int', lo=0, doc='日序号除以 every 的余数'),
                          Param('slots', 'slots', doc='开浴时辰')))
def bath_day(eng, p, day, slot, params):
    """开浴日：每 every 日一次（日序号 % every == phase），在 slots 时辰。"""
    return day % params['every'] == params['phase'] and slot in params['slots']


# ---------------------------------------------------------------- 行为包处理器（按栈里的先后顺序介绍）
@package_handler('forced', layers=(L_FORCED,), acts=(A_SLEEP, A_MEAL),
                 params=(Param('state', 'str', choices=('ill', 'conf'), doc='档案上的哪个状态：ill 卧病 / conf 禁闭（到哪一日，含）'),
                         Param('place', 'place', doc='卧病在哪、禁闭在哪'),
                         Param('sleep', 'str', doc='夜间（与 extra_sleep_slots）的原因'),
                         Param('meal', 'str', doc='斋食时辰的原因'),
                         Param('other', 'str', doc='其余时辰的原因'),
                         Param('other_act', 'act', doc='其余时辰的活动（sick / confined）'),
                         Param('extra_sleep_slots', 'slots', default=(), doc='夜间之外也睡的时辰')))
def forced(st, pkg, p, day, slot, ctx):
    """强制：卧病、禁闭（别的包都让位）。夜间与 extra_sleep_slots 睡，斋食时辰用斋，其余时辰做 other_act。"""
    pm = pkg.params
    if getattr(p, pm['state']) < day:
        return None
    sp = st.sp
    if slot in sp.night or slot in pm['extra_sleep_slots']:
        return (pm['place'], A_SLEEP, pkg.layer, pm['sleep'])
    if slot in sp.meal_slots:
        return (pm['place'], A_MEAL, pkg.layer, pm['meal'])
    return (pm['place'], pm['other_act'], pkg.layer, pm['other'])


@package_handler('penalty', layers=(L_PENALTY,),
                 params=(Param('place', 'place', doc='受罚的场所'), Param('act', 'act', doc='受罚的活动'),
                         Param('label', 'str', doc='原因')))
def penalty(st, pkg, p, day, slot, ctx):
    """处分：档案上还有未执行完的罚跪（kneel 到哪一日，含）。时辰由包的 when.slot 给。"""
    if p.kneel < day:
        return None
    pm = pkg.params
    return (pm['place'], pm['act'], pkg.layer, pm['label'])


@package_handler('court_report', layers=(L_REACT,),
                 params=(Param('place', 'place', doc='举报去哪（戒律院）'), Param('act', 'act', doc='活动'), Param('label', 'str', doc='原因'),
                         Param('free_posts', 'posts', default=(), doc='当值也去得了的岗位（僧值）；其余值守者没空去')))
def court_report(st, pkg, p, day, slot, ctx):
    """反应：有待报的举报，且戒律院开门（首座或执事有人在、没病没禁闭）：去举报。值守者没空，free_posts 的岗位除外。
    先问“此刻有没有值守”（栈里值守层的包，带记忆，不重复抽签）。"""
    if not p.pending:
        return None
    d = st.duty(p, day, slot, ctx)
    if (d is None or p.office in pkg.params['free_posts']) and st.eng.court_open(day):
        pm = pkg.params
        return (pm['place'], pm['act'], pkg.layer, pm['label'])
    return None


@package_handler('kitchen_duty', layers=(L_DUTY,), acts=(A_WORK,), params=(Param('label', 'str', doc='原因'),))
def kitchen_duty(st, pkg, p, day, slot, ctx):
    """值守：厨房职事（岗位表里 kitchen = true 的岗位）在厨务时辰（包的 when.slot）去香积厨干活。"""
    sp = st.sp
    if p.office in sp.kitchen_offices:
        return (sp.kitchen.place, A_WORK, pkg.layer, pkg.params['label'])
    return None


def _proxy_assign(eng, pkg, day):
    """每日开始：厨房在岗人手（未病未禁闭的厨房职事）不足 target，监院从清众里派人代理，补足 target。
    候选：未病未禁闭、没被派去山门者，按精进降序、编号升序；仅当引擎的 acting 开着。"""
    sp, target = eng.spec, pkg.params['target']
    live = [p for p in eng.people if p.gone is None]
    kit = [p for p in live if p.office in sp.kitchen_offices and p.ill < day and p.conf < day]
    if eng.acting and len(kit) < target:
        gs = eng.guards(day)
        cand = sorted((p for p in live if p.office is None and p.ill < day and p.conf < day and p.ix not in gs),
                      key=lambda p: (-p.D, p.ix))
        for p in cand[:target - len(kit)]:
            p.duty_day = day
            eng.stat['acting'] += 1


@package_handler('proxy_cook', layers=(L_DUTY,), acts=(A_WORK,), begin=_proxy_assign,
                 params=(Param('label', 'str', doc='原因'), Param('target', 'int', lo=1, doc='厨房在岗人手不足此数就补')))
def proxy_cook(st, pkg, p, day, slot, ctx):
    """值守：当日被监院派来代理帮厨的人（档案 duty_day == 今日；派人见 _proxy_assign）在厨务时辰去香积厨。"""
    if p.duty_day == day:
        return (st.sp.kitchen.place, A_WORK, pkg.layer, pkg.params['label'])
    return None


@package_handler('patrol_duty', layers=(L_DUTY,), acts=(A_PATROL, A_SLEEP), who_office=True,
                 params=(Param('pick', 'int', lo=1, doc='每次从 roam 里按随机序挑几处'),
                         Param('night_slots', 'slots', doc='巡夜者巡夜的时辰'), Param('day_slots', 'slots', doc='另一位日间巡寮的时辰'),
                         Param('rest_slots', 'slots', doc='巡夜者白天补觉的时辰'),
                         Param('label_night', 'str', doc='巡夜的原因'), Param('label_day', 'str', doc='巡寮的原因'),
                         Param('label_rest', 'str', doc='补觉的原因')))
def patrol_duty(st, pkg, p, day, slot, ctx):
    """值守：僧值两人轮流（逐日轮换，见 engine.night_patroller），一人巡夜（夜里巡、白天补觉），另一人日间巡寮。
    每次从 roam 里按 rng('roam', 日, 时辰, 场所) 排序，取前 pick 处；决定落在第一处，第五项是所巡之处的集合（见证与查寮要用）。
    包的 who 必须正是 org 里 patrol 的岗位。"""
    pm = pkg.params
    eng = st.eng
    night = eng.night_patroller(day) == p.ix
    if (night and slot in pm['night_slots']) or (not night and slot in pm['day_slots']):
        r, seed = eng.rng, eng.seed
        ks = sorted(st.sp.roam, key=lambda x: r(seed, 'roam', day, slot, x))[:pm['pick']]
        return (ks[0], A_PATROL, pkg.layer, pm['label_night'] if night else pm['label_day'], set(ks))
    if night and slot in pm['rest_slots']:
        return (p.dorm, A_SLEEP, pkg.layer, pm['label_rest'])
    return None


@package_handler('gate_duty', layers=(L_DUTY,), acts=(A_GUARD,), params=(Param('label', 'str', doc='原因'),))
def gate_duty(st, pkg, p, day, slot, ctx):
    """值守：山门。每日从清众里轮值 gate.count 人（见 engine.guards），在包的 when.slot 时辰守山门。"""
    if p.ix in st.eng.guards(day):
        return (st.sp.gate.place, A_GUARD, pkg.layer, pkg.params['label'])
    return None


@package_handler('physiology', layers=(L_PHYS,), acts=(A_SLEEP,),
                 params=(Param('faint_e', 'float', doc='困低于此，非斋食时辰就地昏睡'), Param('faint_label', 'str', doc='昏睡的原因'),
                         Param('starve_h', 'float', doc='饥低于此（非斋食、非夜间）：守戒低者偷食，其余忍着'),
                         Param('starve_s', 'float', doc='守戒低于此才偷'), Param('starve_label', 'str', doc='偷食的原因'),
                         Param('act', 'act', doc='饿极时做的活动（steal）：场所取该交互的工位，克制时的想法取它的 refrain_thought')))
def physiology(st, pkg, p, day, slot, ctx):
    """生理紧急：困到不支就地昏睡；饿极了守戒低的人去厨房偷吃（生理层，不算越轨），其余忍着（得“忍饥”想法，继续往下判）。"""
    pm, sp, n = pkg.params, st.sp, p.need
    if n['e'] < pm['faint_e'] and slot not in sp.meal_slots:
        return (p.dorm, A_SLEEP, pkg.layer, pm['faint_label'])
    if n['h'] < pm['starve_h'] and slot not in sp.meal_slots and slot not in sp.night:
        it = sp.interactions[pm['act']]
        if p.S < pm['starve_s']:
            return (it.station, pm['act'], pkg.layer, pm['starve_label'])
        if it.refrain_thought:
            st.eng.moods.think(p, it.refrain_thought, day)
    return None


@package_handler('tempted', layers=(L_DEVIANT,),
                 params=(Param('act', 'act', doc='起念去做的活动（steal）；场所取该交互的工位'), Param('label', 'str', doc='原因'),
                         Param('th_base', 'float', doc='起念的饥门槛底数'), Param('t_mid', 'float', doc='馋的中点'),
                         Param('t_slope', 'float', doc='馋每高一点，门槛抬高多少'), Param('s_line', 'float', doc='守戒达到此线的人不起念'),
                         Param('k', 'float', doc='起念概率的系数'), Param('p_cap', 'float', lo=0, hi=1, doc='起念概率的上限')))
def tempted(st, pkg, p, day, slot, ctx):
    """越轨起念：性格改的是门槛，不是生理常数（计划 6.3）。门槛 th = th_base + (馋 − t_mid)×t_slope；饥低于 th 且守戒低于 s_line 才有可能；
    概率 = min(p_cap, (s_line − 守戒)/s_line × (th − 饥)/th × k)，按 rng('tempt', 日, 时辰, 人) 抽。时辰由包的 when.slot 给。"""
    pm = pkg.params
    h = p.need['h']
    th = pm['th_base'] + (p.T - pm['t_mid']) * pm['t_slope']      # 越馋，越早起念
    if h >= th or p.S >= pm['s_line']:
        return None
    pr = (pm['s_line'] - p.S) / pm['s_line'] * (th - h) / th * pm['k']
    eng = st.eng
    if eng.rng(eng.seed, 'tempt', day, slot, p.ix) < min(pm['p_cap'], pr):
        return (st.sp.interactions[pm['act']].station, pm['act'], pkg.layer, pm['label'])
    return None


@package_handler('lazy', layers=(L_DEVIANT,), acts=(A_SLEEP,),
                 params=(Param('roll_slot', 'int', lo=0, doc='在这一时辰抽“今天贪睡”'), Param('d_line', 'float', doc='精进低于此才可能贪睡'),
                         Param('d_div', 'float', doc='贪睡概率 = (d_line − 精进)/d_div'), Param('label', 'str', doc='贪睡的原因'),
                         Param('tired_e', 'float', doc='晨起窗口里困低于此，起不来（生理层）'), Param('tired_label', 'str', doc='困乏未起的原因')))
def lazy(st, pkg, p, day, slot, ctx):
    """晨起：精进低的人今天贪睡不起（越轨）；没贪睡但困乏也起不来（生理层）。晨起窗口由包的 when.slot 给，抽签在 roll_slot。"""
    pm = pkg.params
    if slot == pm['roll_slot'] and p.D < pm['d_line'] and \
            st.eng.rng(st.eng.seed, 'lazy', day, p.ix) < (pm['d_line'] - p.D) / pm['d_div']:
        p.lazy_day = day
    if p.lazy_day == day:
        return (p.dorm, A_SLEEP, pkg.layer, pm['label'])
    if p.need['e'] < pm['tired_e']:
        return (p.dorm, A_SLEEP, L_PHYS, pm['tired_label'])
    return None


@package_handler('slack', layers=(L_SLACK,),
                 params=(Param('d_line', 'float', doc='精进低于此才可能怠工'), Param('d_div', 'float', doc='怠工概率 = (d_line − 精进)/d_div'),
                         Param('low_mood_add', 'float', doc='心情低于第一道线时加的概率')))
def slack(st, pkg, p, day, slot, ctx):
    """怠工（越轨）：差事时辰，精进低或心情低的人不去领差事，转去自由时段挑（决定的层记“怠工”）。
    被巡寮者撞见的后果见规范 slack（norms 里的 window / limit）。"""
    pm, eng = pkg.params, st.eng
    sl = max(0.0, (pm['d_line'] - p.D) / pm['d_div']) + (pm['low_mood_add'] if eng.moods.is_low(p) else 0)
    if eng.rng(eng.seed, 'slack', day, p.ix) < sl:
        return eng.free.choose(p, day, slot, pkg.layer, ctx)
    return None


@package_handler('errand', layers=(L_ERRAND,), acts=(A_WORK,))
def errand(st, pkg, p, day, slot, ctx):
    """差事：从当日工作板上按优先级认领第一件还有空额的差事（认领即预约）；没有空额就不成立。"""
    return st.eng.jobs.claim(p.ix, pkg.layer)


@package_handler('free', layers=(L_FREE,))
def free(st, pkg, p, day, slot, ctx):
    """自由：以上都不成立，按需求给设施广告打分，在前几名里加权抽一项（兜底，总有决定）。"""
    return st.eng.free.choose(p, day, slot, pkg.layer, ctx)
