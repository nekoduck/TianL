"""规格数据类：NPC 引擎认的唯一“世界描述”。

引擎代码里没有魔数：场所与容量、岗位表、行为包栈、交互的需求增减、规范与处分阶梯、概率与阈值……全是这里的字段。
规格由 defs 构造：`SiteSpec.from_defs(defs, 'scenario:proto60:main')`（实现在 defsload.py，字段说明见 docs/NPC_ENGINE.md 第 12 节）；
原型场景完全由 defs/*/proto60*.toml 描述，代码里不再有它的数。数据类都是不可变的（frozen），字段没有默认值，
取值全部来自定义，这样“改一个数”只有一个出处。

只有两类东西写在这里作为常量：
  * 结构性标识：行为包层的标签（强制、值守…）、活动代码（sleep、chat…）、需求键（h e c s a）、性格键（D S G T R）、
    私人床位的占位（OWN_BED）、行为包 who.status 的两个取值。它们是代码之间约定的“列名”，不是可调的数。
  * 单位量纲：需求与性格刻度的 0–100（SCALE）。
"""
from dataclasses import dataclass
from functools import cached_property
from itertools import pairwise
from typing import Optional

from ..core.calendar import MONTHS, YEAR, Calendar

SCALE = 100.0                       # 需求与性格刻度的满值（0–100）
MONTHS_PER_YEAR = len(MONTHS)       # 历法的一年几个月、每月几日：取自 tianl.core.calendar（月 = doy // 每月日数 + 1，见 Calendar.cal）
DAYS_PER_MONTH = YEAR // MONTHS_PER_YEAR
FIRST_MONTH = FIRST_DOM = 1         # 历法里月与月内日都从 1 数起（Calendar.cal 的 month、dom）

# ---- 需求键与性格键（ARCHITECTURE 第 3 节：h 饥 e 困 c 洁 s 群 a 志；D 精进 S 守戒 G 合群 T 馋 R 刚正）----
NEED_KEYS = ('h', 'e', 'c', 's', 'a')
TRAIT_KEYS = ('D', 'S', 'G', 'T', 'R')

# ---- 行为包层的标签（原型里 decide() 返回的第 3 项）。defs 的 rule:layers 必须登记它们，处理器只许带自己那一种（见 handlers.py）----
L_FORCED, L_PENALTY, L_REACT, L_DUTY, L_PHYS = '强制', '处分', '反应', '值守', '生理'
L_DEVIANT, L_ROUTINE, L_GROUP, L_POST = '越轨', '作息', '集体', '岗位'
L_ERRAND, L_IDENT, L_SLACK, L_FREE = '差事', '身份', '怠工', '自由'

# ---- 活动代码 ----
A_SLEEP, A_REST, A_CHANT, A_MEAL, A_ZAZEN = 'sleep', 'rest', 'chant', 'meal', 'zazen'
A_WORK, A_MARTIAL, A_STUDY, A_BATH, A_WASH = 'work', 'martial', 'study', 'bath', 'wash'
A_CHAT, A_STROLL, A_PATROL, A_GUARD, A_REPORT = 'chat', 'stroll', 'patrol', 'guard', 'report'
A_KNEEL, A_CONFINED, A_SICK, A_STEAL = 'kneel', 'confined', 'sick', 'steal'
ALL_ACTS = (A_SLEEP, A_REST, A_CHANT, A_MEAL, A_ZAZEN, A_WORK, A_MARTIAL, A_STUDY, A_BATH, A_WASH, A_CHAT, A_STROLL,
            A_PATROL, A_GUARD, A_REPORT, A_KNEEL, A_CONFINED, A_SICK, A_STEAL)

# 本人寮房床位的占位：行为包 do.place 与交互 station 都可写它；该处不记容量，床位归人
OWN_BED = '$home'

# 行为包 who.status 的两个取值：清众（无岗位者）与岗位者
STATUS_COMMON, STATUS_HOLDER = 'common', 'holder'

# 行为包 when.period 可用的“时段名”：夜间（SiteSpec.night）与斋食时辰（SiteSpec.meal_slots）——日程的单一出处在 rule:schedule，
# 包按名字引用，不抄一份时辰（改了夜间，包里的就寝跟着变）
PERIOD_NIGHT, PERIOD_MEAL = 'night', 'meal'
PERIODS = (PERIOD_NIGHT, PERIOD_MEAL)

# 数据格式里的元数（几项一组），不是可调的数
GROUPS_ARITY, BONUS_ARITY, ROTATE_ARITY = 2, 3, 2          # groups=(清众, 执事)；bonus=(方向, 本方向, 其余)；rotate=(日系数, 时辰系数)
# 本步启用几道心情线（只第一道；第二、三道由 C7 启用）；几个“至少为几”的下限
MOOD_LINES_ENABLED, AT_LEAST = 1, 1
# when 的具体程度（数小者先匹配）：具体日子 → 天气 → 季节 → 默认
SPEC_DAY, SPEC_WEATHER, SPEC_SEASON, SPEC_DEFAULT = 0, 1, 2, 3


class SiteCalendar(Calendar):
    """tianl.core.Calendar 加上“值相等”：规格（SiteSpec）逐字段比较时，两次从同一份 defs 读出来的历法要相等。
    历法本身（节日表、结夏、农事日）与内核共用同一个类，同一个 calendar 定义既喂内核也喂 NPC 引擎；这里不改它的任何行为。"""

    def _ident(self):
        return (tuple(sorted(self.festivals.items())), self.retreat, self.wheat_doy, self.millet_doy, self.year)

    def __eq__(self, other):
        return isinstance(other, SiteCalendar) and self._ident() == other._ident()

    __hash__ = None                 # 值相等的可变对象不可哈希（规格里本来也有字典，整个 SiteSpec 本来就不可哈希）


class SpecError(ValueError):
    """规格自检不通过：problems 逐条列出引用不到的场所、岗位、想法键……"""

    def __init__(self, problems):
        super().__init__('；'.join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class OfficeSpec:
    """岗位（人岗分离：岗位是表上的一行，人是被任命的）。岗位的日常时段不在这里：它是第 8 层的行为包。"""
    name: str
    count: int
    prefix: str                     # 法名前缀（建人用）
    disc: bool                      # 纪律执事：当面禀告的对象、见证必报、可作“公告”前的送达点
    kitchen: bool                   # 厨房职事


# ---------------------------------------------------------------- 行为包（计划 6.1、6.2）
@dataclass(frozen=True)
class WhoSpec:
    """谁适用；None = 不限。offices 是岗位名，status 见 STATUS_*，tracks 是修行方向。"""
    offices: Optional[tuple]
    status: Optional[str]
    tracks: Optional[tuple]


@dataclass(frozen=True)
class WhenSpec:
    """何时成立；None = 不限。slots 时辰；periods 时段名（night 夜间、meal 斋食，取自站点的日程）；days 模拟日序号；doms 历法月内日；
    months 月；festivals 节日（True = 任一节日）；weathers 天气；seasons 季节。
    匹配次序：先具体日子（days doms festivals），再天气，再季节（seasons months），最后默认（见 specificity）。"""
    slots: Optional[tuple]
    periods: Optional[tuple]
    days: Optional[tuple]
    doms: Optional[tuple]
    months: Optional[tuple]
    festivals: object               # None | True | 节日名元组
    weathers: Optional[tuple]
    seasons: Optional[tuple]

    @cached_property
    def has_calendar(self):
        return any(x is not None for x in (self.days, self.doms, self.months, self.festivals, self.weathers, self.seasons))

    @cached_property
    def specificity(self):
        """0 具体日子（日序号、月内日、节日）→ 1 天气 → 2 季节 / 月 → 3 默认（只有时辰或什么都没写）。数小者先匹配。"""
        if self.days is not None or self.doms is not None or self.festivals is not None:
            return SPEC_DAY
        if self.weathers is not None:
            return SPEC_WEATHER
        if self.seasons is not None or self.months is not None:
            return SPEC_SEASON
        return SPEC_DEFAULT


@dataclass(frozen=True)
class DoSpec:
    """声明式包的做什么。place 是场所 code 或 OWN_BED；claim = 占一个工位，满员改去 overflow_place、原因加 overflow_suffix。"""
    place: str
    act: str
    label: str
    claim: bool
    overflow_place: Optional[str]
    overflow_suffix: str


@dataclass(frozen=True)
class PackageSpec:
    """一个行为包：layer / who / when 加上 do（声明式）或 handler + params（需要条件判断的）。params 已规范化（引用换成 code / 岗位名）。"""
    id: str
    layer: str
    who: WhoSpec
    when: WhenSpec
    do: Optional[DoSpec]
    handler: Optional[str]
    params: dict


# ---------------------------------------------------------------- 交互与设施
@dataclass(frozen=True)
class InteractionSpec:
    """交互：一种活动（act）的全部固定字段（计划 4.3）。station 是工位所在场所 code（或 OWN_BED，或 None）。"""
    act: str
    station: Optional[str]
    duration: int                   # 时辰；引擎按时辰决定，目前只接受 1
    effects: dict                   # 需求键 -> 每时辰增减
    inputs: dict                    # 所需物：物 -> 每次服务的耗量
    outputs: dict                   # 产出物：物 -> 做一次的产量
    norm: Optional[str]             # 触犯的规范名（规范的 name）
    category: str                   # 时间分配类别
    bonus: Optional[tuple]          # (方向, 本方向的志增量, 其余的志增量)
    thought: Optional[str]          # 做了就得到的想法键
    refrain_thought: Optional[str]  # 有理由做、却克制没做时得到的想法键


@dataclass(frozen=True)
class ViolationSpec:
    """某活动触犯某规范时发什么事件、在哪个场所（工位所在）。"""
    norm: str
    event: str
    place: str


# ---------------------------------------------------------------- 站点级机构
@dataclass(frozen=True)
class KitchenSpec:
    place: str
    dining_place: str               # 斋堂：到课（过堂）人数在此统计
    prep: dict                      # 斋食时辰 -> 备斋时辰（用备斋时辰的人手判断足量或半餐）
    min_staff: int
    gain_full: float
    gain_half: float
    stock_init: dict                # 初始库存：水、柴（每顿斋耗什么见 meal 交互的 inputs）


@dataclass(frozen=True)
class PatrolSpec:
    office: str                     # 僧值：两人轮流，一人巡夜（补觉），一人日间巡寮（日程在行为包里）
    bed_check_slots: tuple          # 巡夜查寮的时辰
    bed_exempt_layers: tuple        # 这些层的人不算“夜不在寮”
    bed_thought: str                # 被记空铺者的想法键


@dataclass(frozen=True)
class GateSpec:
    place: str
    count: int                      # 每日从清众里轮值的人数


@dataclass(frozen=True)
class CourtSpec:
    place: str
    judges: tuple                   # 有资格裁断的岗位名（按次序，首座优先）
    judge_slot: int


@dataclass(frozen=True)
class RollCallSpec:
    office: str                     # 维那
    place: str
    slots: tuple
    exempt_layers: tuple            # 这些层的人不点名（强制、值守、反应）
    window: int                     # 近几日内
    limit: int                      # 缺课几次
    kneel_days: int                 # 就罚跪香几日
    kneel_txt: str                  # 统计里的名目
    absent_thought: str             # 缺课者的想法键
    kneel_thought: str              # 被罚跪香者的想法键


@dataclass(frozen=True)
class InventorySpec:
    slot: int
    p_find: float                   # 清点时发现失窃的概率


@dataclass(frozen=True)
class SlackSpec:
    window: int
    limit: int
    kneel_days: int
    thought: str                    # 被巡寮撞见者的想法键（起意怠工的概率在 slack 包的参数里）


@dataclass(frozen=True)
class IllSpec:
    p: float
    min_days: int
    span: int


@dataclass(frozen=True)
class NeedSpec:
    """五项需求的站点级参数；各活动的增减、类别、功课加成在 interaction 里。"""
    init: dict
    base: dict                      # 每时辰的基础消耗
    names: dict                     # 需求键 -> 中文名（报表）
    category_default: str
    hunger_sleep: float             # 睡时的饥消耗
    hunger_t_mid: float             # 饥消耗随“馋”微调：1 + (T - mid) / div
    hunger_t_div: float
    social_g: tuple                 # (偏移, 刻度)：群的消耗乘 (偏移 + G/刻度)
    morning_slot: int
    morning_c: float
    duty_layers: tuple
    duty_a: float
    urgency_floor: float
    urgency_pow: float
    hungry_line: float              # 统计线（只用于报告）
    tired_line: float


@dataclass(frozen=True)
class TraitSpec:
    mean: dict
    sd: dict
    office_bonus: dict              # 有岗位者的均值加成（没写的键为 0）
    lo: dict
    hi: dict


@dataclass(frozen=True)
class NeedTerm:
    """广告里的一项：某需求的迫切度乘以增量；增量可按方向区分。"""
    need: str
    w: float
    by_track: tuple                 # ((方向, 增量), …)


@dataclass(frozen=True)
class AdSpec:
    """设施的广告（Sims）：能满足什么、给谁加分、什么时候开放。"""
    act: str
    place: str                      # 场所；OWN_BED 表示本人床位
    label: str
    terms: tuple                    # NeedTerm…
    scale: Optional[tuple]          # (性格键, 偏移, 刻度)：把需求项之和再乘 (偏移 + 性格/刻度)
    pref: Optional[tuple]           # (种类, 性格键, 系数, 方向)；种类 trait/track/idle（见 facilities.score）
    gate: Optional[str]             # 准入门的名字（handlers.GATES）
    gate_params: dict               # 准入门的参数（已规范化）


@dataclass(frozen=True)
class FreeSpec:
    top_k: int
    stroll_place: str
    stroll_act: str
    stroll_label: str
    choice_key_chars: int           # “自由时段的选择”统计取原因的前几个字作键（只入统计，原型口径：2）


@dataclass(frozen=True)
class JobSpec:
    prio: int
    name: str
    place: str
    count: int
    outputs: dict                   # 产出物：物 -> 每名完成者入账的量


@dataclass(frozen=True)
class JobsSpec:
    board: tuple                    # JobSpec；认领次序：prio 升序，同级按这里的次序
    work_chat_p: float              # 工友闲谈概率


@dataclass(frozen=True)
class OpinionSpec:
    same_dorm: float
    same_track: float
    same_post: float
    compat_div: float
    compat_mid: float
    compat_w: float
    lo: float
    hi: float
    friend_line: float
    foe_line: float


@dataclass(frozen=True)
class ModSpec:
    kind: str
    value: float
    days: int
    cap: int
    cause: str                      # 起因（说明用；“情”命令向玩家解释这条修正项从哪来）


@dataclass(frozen=True)
class ThoughtSpec:
    label: str
    value: float
    days: int
    cap: int


@dataclass(frozen=True)
class MoodLine:
    value: float                    # 心情低于它就触发 effect
    effect: str                     # slack 怠工概率加成 / avoid_group 回避集体 / life_event 人生事件


@dataclass(frozen=True)
class MoodSpec:
    weights: dict
    lines: tuple                    # MoodLine，自高到低（三道线 35 / 20 / 5）
    enabled: int                    # 启用几道（自上而下）；本步只能是 1，其余留给 C7

    @property
    def low_line(self):
        return self.lines[0].value


@dataclass(frozen=True)
class ChatSpec:
    good_base: float
    good_mid: float
    good_w: float
    pair_noise: float
    gain_when_brief: float          # 工友间的短闲谈给“群”的补益（full=False）
    lone_label: str                 # 闲谈落单、改散步时的原因
    good_mod: str                   # 谈得投机的修正项键
    bad_mod: str
    good_thought: str               # 谈得来的想法键


@dataclass(frozen=True)
class RumorSpec:
    penalty: float
    decay: float
    min_strength: float
    p_add: float
    p_cap: float
    g_off: float
    g_div: float
    keep: int


@dataclass(frozen=True)
class ReportSpec:
    base: float
    r_w: float
    op_w: float
    lo: float
    hi: float


@dataclass(frozen=True)
class CaseSpec:
    open: str
    done: str
    cold: str
    closed: str
    stale_days: int
    confess_base: float
    confess_r: float
    accuse_mod: str                 # 受罚者对举报人的修正项键
    sanction_thought: str           # 每起处分都给受处分者的想法键
    via_report: str                 # 案卷 via：凭举报定罪
    via_confess: str                # 案卷 via：凭本人认错定罪


@dataclass(frozen=True)
class LadderStep:
    txt: str
    kneel_days: int
    conf_days: int
    need_hit: tuple                 # ((需求, 增减), …)
    thought: Optional[str]          # 想法键（SiteSpec.thoughts）
    gone: bool


@dataclass(frozen=True)
class AnnounceSpec:
    slot: int
    place: str
    s_line: float                   # 守戒高于此的旁观者对受罚者记“犯戒”
    mod: str


@dataclass(frozen=True)
class SiteSpec:
    name: str
    scope: str                      # 定义的 scope（如 proto60）
    # 空间与时间
    places: dict                    # 场所 code -> 显示名
    capacity: dict                  # 场所 code -> 工位数（设施登记的）
    cap_default: int
    dorms: tuple
    roam: tuple
    night: tuple
    rotate: tuple
    meal_slots: tuple
    seasons: dict                   # 季节名 -> 月份元组（行为包 when.season 用）
    calendar: SiteCalendar          # 这处场所的历法（rule:schedule 的 calendar 引用的 calendar 定义）：节日、月、月内日、季节的键都按它
    # 人群
    offices: tuple
    office_track_cycle: str
    name_pool: str
    common_prefix: str
    common_tracks: tuple            # ((方向, 人数或 None), …)：清众按序分方向，None 表示其余全部
    groups: tuple                   # (清众的名称, 执事的名称)
    leave_word: str                 # 人离开本处时 explain 里的说法（离寺、出帮……）
    traits: TraitSpec
    # 行为包栈与交互
    layer_rank: dict                # 层标签 -> 计划 6.1 的层号（越轨与怠工记 0）
    stack: tuple                    # PackageSpec，判定次序（自上而下第一个成立的生效）
    interactions: dict              # 活动代码 -> InteractionSpec
    violations: dict                # 活动代码 -> ViolationSpec（交互触犯的规范）
    # 站点级机构与规范
    kitchen: KitchenSpec
    patrol: PatrolSpec
    gate: GateSpec
    court: CourtSpec
    rollcall: RollCallSpec
    inventory: InventorySpec
    slack: SlackSpec
    illness: IllSpec
    needs: NeedSpec
    ads: tuple
    free: FreeSpec
    jobs: JobsSpec
    # 好恶、心情、闲谈、传闻
    opinion: OpinionSpec
    mods: dict                      # 名 -> ModSpec
    thoughts: dict                  # 名 -> ThoughtSpec
    mood: MoodSpec
    chat: ChatSpec
    rumor: RumorSpec
    salience: dict                  # 事件种类 -> 目击时的见闻强度（0 表示不产生见闻）
    # 规范
    report: ReportSpec
    cases: CaseSpec
    ladder: tuple
    announce: AnnounceSpec

    # ---- 由 defs 构造 ----
    @classmethod
    def from_defs(cls, defs, scenario_id):
        """由 defs 构造：scenario_id 是场景定义的编号（如 'scenario:proto60:main'），其 scope（中间一段）下的全部定义拼成规格。
        缺字段、引用不存在的定义、未登记的处理器或参数不合法，都抛 SpecError，problems 逐条写明哪条定义、哪个字段。"""
        from .defsload import build_site
        return build_site(defs, scenario_id)

    # ---- 派生量 ----
    @cached_property
    def office_by_name(self):
        return {o.name: o for o in self.offices}

    @cached_property
    def disc_offices(self):
        return frozenset(o.name for o in self.offices if o.disc)

    @cached_property
    def kitchen_offices(self):
        return frozenset(o.name for o in self.offices if o.kitchen)

    @cached_property
    def private_places(self):
        return frozenset(self.dorms)

    @cached_property
    def errand_slots(self):
        """差事时辰：差事包（handler = errand）的 when.slot 之并。差事结算、怠工被撞见都在这些时辰。"""
        out = set()
        for pk in self.stack:
            if pk.handler == 'errand' and pk.when.slots:
                out.update(pk.when.slots)
        return frozenset(out)

    @cached_property
    def period_slots(self):
        """时段名 -> 时辰元组（行为包 when.period 用）。"""
        return {PERIOD_NIGHT: tuple(self.night), PERIOD_MEAL: tuple(self.meal_slots)}

    @cached_property
    def meal_inputs(self):
        """每顿斋耗什么：meal 交互的 inputs，((物, 量), …)。"""
        return tuple(self.interactions[A_MEAL].inputs.items())

    def validate(self):
        """引用完整性自检：返回问题列表（空表示通过）。引擎构造时会调用，不通过就拒绝开跑。"""
        from .handlers import Known, ad_gate_problems, package_handler_problems, package_shape_problems
        out = []
        known = Known.of(self)
        pl = set(self.places)
        names = {o.name for o in self.offices}

        def need_place(where, code):
            if code not in pl:
                out.append('%s：场所 %r 不在 places 里' % (where, code))

        def need_in(where, key, table, what):
            if key not in table:
                out.append('%s：活动 %r 没有对应的交互' % (where, key) if what == '活动' else '%s：%s %r 未登记' % (where, what, key))

        if not isinstance(self.calendar, SiteCalendar):
            out.append('calendar：应是 SiteCalendar（由 rule:schedule 的 calendar 引用的定义构造）')
        elif self.calendar.year != YEAR:
            out.append('calendar：一年必须是 %d 日（tianl.core.calendar.YEAR；内核与 NPC 引擎都按它算月与节令）' % YEAR)
        for season, months in self.seasons.items():
            for m in months:
                if not FIRST_MONTH <= m <= MONTHS_PER_YEAR:
                    out.append('seasons[%s]：月份 %r 不是 1–%d' % (season, m, MONTHS_PER_YEAR))
        for code in self.capacity:
            need_place('capacity', code)
        for code in self.roam:
            need_place('roam', code)
        for code in self.dorms:
            need_place('dorms', code)
        for o in self.offices:
            if o.count < 0:
                out.append('office %s：编制不能为负' % o.name)
        for k in TRAIT_KEYS:
            for what in ('mean', 'sd', 'lo', 'hi'):
                if k not in getattr(self.traits, what):
                    out.append('traits.%s 必须覆盖 %s' % (what, TRAIT_KEYS))
                    break
        for where, code in (('kitchen.place', self.kitchen.place), ('kitchen.dining_place', self.kitchen.dining_place),
                            ('gate.place', self.gate.place), ('court.place', self.court.place),
                            ('rollcall.place', self.rollcall.place), ('free.stroll_place', self.free.stroll_place),
                            ('announce.place', self.announce.place)):
            need_place(where, code)
        for j in self.jobs.board:
            need_place('job %s' % j.name, j.place)
            for item in j.outputs:
                if item not in self.kitchen.stock_init:
                    out.append('job %s：产出物 %r 不在 kitchen.stock_init 里（库存没有这一项）' % (j.name, item))
        for where, off in (('patrol.office', self.patrol.office), ('rollcall.office', self.rollcall.office)):
            need_in(where, off, names, '岗位')
        for off in self.court.judges:
            need_in('court.judges', off, names, '岗位')
        # 交互
        for act, it in self.interactions.items():
            if it.act != act:
                out.append('interactions[%s].act 是 %r' % (act, it.act))
            if it.station is not None and it.station != OWN_BED:
                need_place('interaction %s.station' % act, it.station)
            if it.duration != 1:
                out.append('interaction %s：duration 目前只接受 1（引擎按时辰决定；多时辰的交互留给集成步骤）' % act)
            for k in tuple(it.effects):
                need_in('interaction %s.effects' % act, k, NEED_KEYS, '需求键')
            if it.bonus is not None and not (isinstance(it.bonus, tuple) and len(it.bonus) == BONUS_ARITY):
                out.append('interaction %s.bonus 必须是 (方向, 本方向增量, 其余增量)' % act)
            for k in (it.thought, it.refrain_thought):
                if k is not None:
                    need_in('interaction %s' % act, k, self.thoughts, '想法键')
            for item in list(it.inputs) + list(it.outputs):
                if not isinstance(item, str):
                    out.append('interaction %s：物的名字必须是字符串' % act)
        for act in (A_MEAL, A_WORK, A_SLEEP, A_REPORT, A_STROLL):
            need_in('interactions', act, self.interactions, '引擎要用的活动')
        if A_MEAL in self.interactions:
            for item, q in self.interactions[A_MEAL].inputs.items():
                if item not in self.kitchen.stock_init:
                    out.append('meal 交互：所需物 %r 不在 kitchen.stock_init 里（库存没有这一项）' % item)
        for act, v in self.violations.items():
            need_in('violations', act, self.interactions, '活动')
            need_place('violations[%s].place' % act, v.place)
        for act, it in self.interactions.items():
            if it.norm is not None and act not in self.violations:
                out.append('interaction %s：触犯规范 %r，但 violations 里没有它' % (act, it.norm))
        # 广告与准入门
        for ad in self.ads:
            if ad.place != OWN_BED:
                need_place('ad %s' % ad.act, ad.place)
            need_in('ad %s' % ad.act, ad.act, self.interactions, '活动')
            out.extend(ad_gate_problems(ad, known))
            for t in ad.terms:
                need_in('ad %s' % ad.act, t.need, NEED_KEYS, '需求键')
            for key in ((ad.scale[0],) if ad.scale else ()) + ((ad.pref[1],) if ad.pref else ()):
                need_in('ad %s' % ad.act, key, TRAIT_KEYS, '性格键')
        # 想法键与修正项键
        keys = [('rollcall.absent_thought', self.rollcall.absent_thought),
                ('rollcall.kneel_thought', self.rollcall.kneel_thought), ('patrol.bed_thought', self.patrol.bed_thought),
                ('slack.thought', self.slack.thought), ('chat.good_thought', self.chat.good_thought),
                ('cases.sanction_thought', self.cases.sanction_thought)]
        keys += [('ladder', st.thought) for st in self.ladder if st.thought]
        for where, k in keys:
            need_in(where, k, self.thoughts, '想法键')
        for where, k in (('chat.good_mod', self.chat.good_mod), ('chat.bad_mod', self.chat.bad_mod),
                         ('cases.accuse_mod', self.cases.accuse_mod), ('announce.mod', self.announce.mod)):
            need_in(where, k, self.mods, '修正项键')
        for st in self.ladder:
            for need, _ in st.need_hit:
                need_in('ladder.need_hit', need, NEED_KEYS, '需求键')
        if not self.ladder:
            out.append('ladder 不能为空')
        if set(self.kitchen.prep) != set(self.meal_slots):
            out.append('kitchen.prep 的键必须正是 meal_slots')
        if set(self.needs.init) != set(NEED_KEYS) or set(self.needs.base) != set(NEED_KEYS):
            out.append('needs.init / needs.base 必须正好覆盖 %s' % (NEED_KEYS,))
        if set(self.needs.names) != set(NEED_KEYS):
            out.append('needs.names 必须正好覆盖 %s' % (NEED_KEYS,))
        if set(self.mood.weights) != set(NEED_KEYS):
            out.append('mood.weights 必须覆盖 %s' % (NEED_KEYS,))
        if not self.mood.lines or self.mood.enabled != MOOD_LINES_ENABLED:
            out.append('mood.enabled 本步只能是 1（先只启用第一道线；第二、三道线由 C7 启用）')
        elif any(a.value <= b.value for a, b in pairwise(self.mood.lines)):
            out.append('mood.lines 必须自高到低严格递减')
        if len(self.groups) != GROUPS_ARITY:
            out.append('groups 必须是 (清众, 执事) 两项')
        if self.free.choice_key_chars < AT_LEAST:
            out.append('free.choice_key_chars 至少为 1')
        if not self.ads:
            out.append('ads 不能为空：自由时段没有任何设施可选')
        if self.free.top_k < AT_LEAST:
            out.append('free.top_k 至少为 1：自由时段在前几名里抽，不能一项都不看')
        if self.cases.via_report == self.cases.via_confess:
            out.append('cases.via_report 与 cases.via_confess 不能相同（案卷靠它区分定罪依据）')
        # 层与行为包栈
        used_layers = (L_FORCED, L_PENALTY, L_REACT, L_DUTY, L_PHYS, L_DEVIANT, L_ROUTINE, L_GROUP, L_POST, L_ERRAND,
                       L_IDENT, L_SLACK, L_FREE)
        for lay in used_layers:
            need_in('layer_rank', lay, self.layer_rank, '层标签（引擎认识的）')
        if not self.stack:
            out.append('stack 不能为空')
        seen_ids = set()
        duty_pos = []
        for pos, pk in enumerate(self.stack):
            if pk.id in seen_ids:
                out.append('包 %s：在栈里出现了两次' % pk.id)
            seen_ids.add(pk.id)
            if pk.layer == L_DUTY:
                duty_pos.append(pos)
            out.extend(package_shape_problems(pk, known))        # 层、谁、何时、做什么、处理器与参数：与读 defs 时同一份校验（handlers.py）
            out.extend(package_handler_problems(pk, known))
        if duty_pos and duty_pos != list(range(duty_pos[0], duty_pos[0] + len(duty_pos))):
            out.append('值守层的包必须在栈里相邻（反应包要先问“此刻有没有值守”）')
        if not any(pk.handler == 'free' for pk in self.stack):
            out.append('栈里必须有一个 free 包（兜底：自由时段）；否则有人会没有决定')
        return out


# ---------------------------------------------------------------- 场景（怎么跑：种子、人口、要角、脚本与实验、报表用词）
@dataclass(frozen=True)
class GossipSpec:
    """传闻实验：第 day 日 slot 时辰，清众第 who 位偷食、第 heard 位撞见（唯一的见证人，且不举报）。"""
    day: int
    who: int
    heard: int
    slot: int
    why: str


@dataclass(frozen=True)
class N1Spec:
    """实验 N1：第 day 日起 sick 里的岗位者同时病倒 days 日；两个对照组 arms = ((名称, 监院是否派人代理), …)；逐日偷食累计看 window。"""
    day: int
    days: int
    sick: tuple                     # ((岗位名, 只取前几位或 None), …)
    sick_label: str                 # 报表标题里对病倒者的称呼
    window: tuple
    arms: tuple


@dataclass(frozen=True)
class ScenarioSpec:
    """场景：与世界描述（SiteSpec）分开——同一份 SiteSpec 可以配不同的种子、人口与实验。"""
    id: str
    name: str
    seed: int
    population: int
    days: int                       # 默认跑几日
    cast: tuple                     # ((清众序号, {性格键: 值}), …)：手工指定的“要角”
    glutton: int                    # 报表里点名的两位（清众序号）
    lazy: int
    observer_place: str             # “观察者在廊下”那一行的观察处（场所 code）
    trace_day: int                  # 报表里“某日四人轨迹”的日子
    trace_post: str                 # 轨迹里第四人的岗位名
    track_suffix: str               # 清众的称呼 = 修行方向 + 此字
    long_days: int                  # “90 日”那一行
    extra_seeds: tuple              # 多种子那几行
    gossip: GossipSpec
    n1: N1Spec

    @classmethod
    def from_defs(cls, defs, scenario_id):
        from .defsload import build_scenario
        return build_scenario(defs, scenario_id)
