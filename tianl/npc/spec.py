"""规格数据类：NPC 引擎认的唯一“世界描述”。

引擎代码里没有魔数：场所与容量、岗位表、集体日程、各人群作息、规范与处分阶梯、概率与阈值……全是这里的字段。
本步（C 段第一步）规格用 Python 数据类表达，由 scenarios.proto60_spec() 构造出与原型 npc_spike.py 完全一致的一套；
之后的步骤再加 from_defs()（ARCHITECTURE 第 6 节）。数据类都是不可变的（frozen），字段没有默认值，
取值全部显式写在场景里，这样“改一个数”只有一个出处。

只有两类东西写在这里作为常量：
  * 结构性标识：行为包层的标签（强制、值守…）、活动代码（sleep、chat…）、需求键（h e c s a）、性格键（D S G T R）。
    它们是代码之间约定的“列名”，不是可调的数。
  * 单位量纲：需求与性格刻度的 0–100（SCALE）。
"""
from dataclasses import dataclass
from functools import cached_property
from typing import Optional

SCALE = 100.0                       # 需求与性格刻度的满值（0–100）

# ---- 需求键与性格键（ARCHITECTURE 第 3 节：h 饥 e 困 c 洁 s 群 a 志；D 精进 S 守戒 G 合群 T 馋 R 刚正）----
NEED_KEYS = ('h', 'e', 'c', 's', 'a')
TRAIT_KEYS = ('D', 'S', 'G', 'T', 'R')

# ---- 行为包层的标签（原型里 decide() 返回的第 3 项）----
L_FORCED, L_PENALTY, L_REACT, L_DUTY, L_PHYS = '强制', '处分', '反应', '值守', '生理'
L_DEVIANT, L_ROUTINE, L_GROUP, L_POST = '越轨', '作息', '集体', '岗位'
L_ERRAND, L_IDENT, L_SLACK, L_FREE = '差事', '身份', '怠工', '自由'

# ---- 活动代码 ----
A_SLEEP, A_REST, A_CHANT, A_MEAL, A_ZAZEN = 'sleep', 'rest', 'chant', 'meal', 'zazen'
A_WORK, A_MARTIAL, A_STUDY, A_BATH, A_WASH = 'work', 'martial', 'study', 'bath', 'wash'
A_CHAT, A_STROLL, A_PATROL, A_GUARD, A_REPORT = 'chat', 'stroll', 'patrol', 'guard', 'report'
A_KNEEL, A_CONFINED, A_SICK, A_STEAL = 'kneel', 'confined', 'sick', 'steal'

# 自由时段广告里“本人床位”的占位场所（该处不记容量，床位归人）
OWN_BED = '@bed'


class SpecError(ValueError):
    """规格自检不通过：problems 逐条列出引用不到的场所、岗位、想法键……"""

    def __init__(self, problems):
        super().__init__('；'.join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class OfficeSpec:
    """岗位（人岗分离：岗位是表上的一行，人是被任命的）。"""
    name: str
    count: int
    place: Optional[str]            # 理事所在场所；None 表示没有固定的理事时段
    slots: tuple                    # 理事时辰
    prefix: str                     # 法名前缀（建人用）
    disc: bool                      # 纪律执事：当面禀告的对象、见证必报、可作“公告”前的送达点
    kitchen: bool                   # 厨房职事


@dataclass(frozen=True)
class GroupAct:
    """集体日程里的一条：所有人同一时辰去同一处做同一件事。"""
    place: str
    act: str
    label: str


@dataclass(frozen=True)
class UposathaSpec:
    """布萨诵戒。by='day' 按模拟日编号（原型口径：第 1、15 日）；by='dom' 按历法的月内日（集成世界用）。"""
    days: tuple
    by: str
    slot: int
    what: GroupAct


@dataclass(frozen=True)
class CommonSpec:
    """清众（无岗位者）的身份作息：差事时辰领工作板上的差事，功课时辰做本方向功课。"""
    work_slot: int
    class_slot: int
    classes: dict                   # 方向 -> GroupAct
    overflow_place: str             # 功课场所满员时改去的地方
    overflow_suffix: str


@dataclass(frozen=True)
class KitchenSpec:
    place: str
    dining_place: str               # 斋堂：到课（过堂）人数在此统计
    slots: tuple                    # 厨务时辰
    label_staff: str
    label_proxy: str
    prep: dict                      # 斋食时辰 -> 备斋时辰（用备斋时辰的人手判断足量或半餐）
    min_staff: int
    stock_use: tuple                # ((物, 数量), …) 每顿斋耗
    gain_full: float
    gain_half: float
    acting_target: int              # 监院派人代理：在岗厨房人手不足此数就补
    stock_init: dict                # 初始库存：水、柴


@dataclass(frozen=True)
class PatrolSpec:
    office: str                     # 僧值：两人轮流，一人巡夜（补觉），一人日间巡寮
    pool: tuple                     # 每次巡视从这里挑
    pick: int
    night_slots: tuple
    day_slots: tuple
    rest_slots: tuple               # 巡夜者白天补觉的时辰
    labels: tuple                   # (巡夜, 巡寮)
    rest_label: str
    bed_check_slots: tuple          # 巡夜查寮的时辰
    bed_exempt_layers: tuple        # 这些层的人不算“夜不在寮”
    bed_thought: str                # 被记空铺者的想法键


@dataclass(frozen=True)
class GateSpec:
    place: str
    slots: tuple
    count: int                      # 每日从清众里轮值的人数
    label: str


@dataclass(frozen=True)
class CourtSpec:
    place: str
    judges: tuple                   # 有资格裁断的岗位名（按次序，首座优先）
    judge_slot: int
    report_slots: tuple             # 去戒律院举报的时辰
    report_label: str


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
class LibrarySpec:
    office: str                     # 藏主在，经阁才开
    slots: tuple


@dataclass(frozen=True)
class ForcedSpec:
    ill_place: str
    conf_place: str
    sleep_extra_slots: tuple        # 夜间之外也睡的时辰
    ill_sleep: str
    ill_meal: str
    ill_other: str
    conf_sleep: str
    conf_meal: str
    conf_other: str


@dataclass(frozen=True)
class PenaltySpec:
    kneel_slot: int
    place: str
    label: str


@dataclass(frozen=True)
class PhysSpec:
    faint_e: float                  # 困低于此，就地昏睡
    faint_label: str
    starve_h: float                 # 饥低于此：守戒低者偷食，其余忍着
    starve_s: float                 # 守戒低于此才偷
    starve_label: str
    endure_thought: str             # 忍着饥饿的想法键


@dataclass(frozen=True)
class TemptSpec:
    """越轨偷食的起念：性格改的是门槛，不是生理常数（计划 6.3）。"""
    th_base: float
    t_mid: float
    t_slope: float
    s_line: float
    k: float
    p_cap: float
    night_slot: int
    night_label: str
    after_slot: int
    after_label: str


@dataclass(frozen=True)
class LazySpec:
    wake_slots: tuple               # 晨起窗口
    roll_slot: int                  # 在这一时辰抽“今天贪睡”
    d_line: float
    d_div: float
    label: str
    tired_e: float
    tired_label: str


@dataclass(frozen=True)
class SlackSpec:
    d_line: float
    d_div: float
    low_mood_add: float             # 心情低于第一道线时加的概率
    window: int
    limit: int
    kneel_days: int
    thought: str                    # 被巡寮撞见者的想法键


@dataclass(frozen=True)
class IllSpec:
    p: float
    min_days: int
    span: int


@dataclass(frozen=True)
class NeedSpec:
    init: dict
    base: dict                      # 每时辰的基础消耗
    eff: dict                       # 活动 -> {需求: 增减}
    bonus: dict                     # 活动 -> (方向, 本方向增量, 其余增量)
    category: dict                  # 活动 -> 时间分配类别
    category_default: str
    act_thought: dict               # 活动 -> 想法键（做了这件事就得到的想法，如沐浴）
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
    office_bonus: dict              # 有岗位者的均值加成
    lo: float
    hi: float


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
    pref: Optional[tuple]           # (种类, 性格键, 系数, 方向)；种类 trait/track/slack
    gate: Optional[str]             # 准入门的名字（handlers.GATES）


@dataclass(frozen=True)
class FreeSpec:
    top_k: int
    stroll_place: str
    stroll_act: str
    stroll_label: str
    bath_every: int
    bath_phase: int
    bath_slots: tuple


@dataclass(frozen=True)
class JobSpec:
    prio: int
    name: str
    place: str
    count: int
    product: Optional[str]          # 产出：water / wood / None


@dataclass(frozen=True)
class JobsSpec:
    board: tuple                    # JobSpec，次序即认领次序
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


@dataclass(frozen=True)
class ThoughtSpec:
    label: str
    value: float
    days: int
    cap: int


@dataclass(frozen=True)
class MoodSpec:
    weights: dict
    low_line: float


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
    # 空间与时间
    places: dict
    capacity: dict
    cap_default: int
    dorms: tuple
    roam: tuple
    night: tuple
    night_label: str                # 夜间就寝的原因
    rotate: tuple
    meal_slots: tuple
    # 人群
    offices: tuple
    office_track_cycle: str
    name_pool: str
    common_prefix: str
    common_tracks: tuple            # ((方向, 人数或 None), …)：清众按序分方向，None 表示其余全部
    groups: tuple                   # (清众的名称, 执事的名称)
    traits: TraitSpec
    # 日程
    group: dict
    uposatha: UposathaSpec
    common: CommonSpec
    post_suffix: str
    library: LibrarySpec
    # 值守与规范机构
    kitchen: KitchenSpec
    patrol: PatrolSpec
    gate: GateSpec
    court: CourtSpec
    rollcall: RollCallSpec
    inventory: InventorySpec
    # 层的内部规则
    forced: ForcedSpec
    penalty: PenaltySpec
    phys: PhysSpec
    temptation: TemptSpec
    lazy: LazySpec
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
    layer_rank: dict                # 层标签 -> 计划 6.1 的层号（越轨与怠工记 0）

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
    def post_slots(self):
        """岗位名 -> (场所, 理事时辰)；没有固定理事时段的岗位不在其中。"""
        return {o.name: (o.place, o.slots) for o in self.offices if o.slots}

    @cached_property
    def private_places(self):
        return frozenset(self.dorms)

    def validate(self):
        """引用完整性自检：返回问题列表（空表示通过）。引擎构造时会调用，不通过就拒绝开跑。"""
        from .handlers import GATES
        out = []
        pl = set(self.places)

        def need_place(where, code):
            if code not in pl:
                out.append('%s：场所 %r 不在 places 里' % (where, code))

        def need_in(where, key, table, what):
            if key not in table:
                out.append('%s：%s %r 未登记' % (where, what, key))

        for code in self.capacity:
            need_place('capacity', code)
        for code in self.roam:
            need_place('roam', code)
        for code in self.dorms:
            need_place('dorms', code)
        for k, g in self.group.items():
            need_place('group[%s]' % k, g.place)
        need_place('uposatha', self.uposatha.what.place)
        if self.uposatha.by not in ('day', 'dom'):
            out.append("uposatha.by 只能是 'day' 或 'dom'")
        for k, g in self.common.classes.items():
            need_place('common.classes[%s]' % k, g.place)
        need_place('common.overflow_place', self.common.overflow_place)
        names = {o.name for o in self.offices}
        for o in self.offices:
            if o.place is not None:
                need_place('office %s' % o.name, o.place)
        for track, _ in self.common_tracks:
            need_in('common_tracks', track, self.common.classes, '修行方向')
        for where, code in (('kitchen.place', self.kitchen.place), ('kitchen.dining_place', self.kitchen.dining_place),
                            ('gate.place', self.gate.place), ('court.place', self.court.place),
                            ('rollcall.place', self.rollcall.place), ('forced.ill_place', self.forced.ill_place),
                            ('forced.conf_place', self.forced.conf_place), ('penalty.place', self.penalty.place),
                            ('free.stroll_place', self.free.stroll_place), ('announce.place', self.announce.place)):
            need_place(where, code)
        for code in self.patrol.pool:
            need_place('patrol.pool', code)
        for j in self.jobs.board:
            need_place('job %s' % j.name, j.place)
        for ad in self.ads:
            if ad.place != OWN_BED:
                need_place('ad %s' % ad.act, ad.place)
            if ad.gate is not None:
                need_in('ad %s' % ad.act, ad.gate, GATES, '准入门')
            for t in ad.terms:
                need_in('ad %s' % ad.act, t.need, NEED_KEYS, '需求键')
            for key in ((ad.scale[0],) if ad.scale else ()) + ((ad.pref[1],) if ad.pref else ()):
                need_in('ad %s' % ad.act, key, TRAIT_KEYS, '性格键')
        for where, off in (('patrol.office', self.patrol.office), ('rollcall.office', self.rollcall.office),
                           ('library.office', self.library.office)):
            need_in(where, off, names, '岗位')
        for off in self.court.judges:
            need_in('court.judges', off, names, '岗位')
        keys = [('phys.endure_thought', self.phys.endure_thought), ('patrol.bed_thought', self.patrol.bed_thought),
                ('rollcall.absent_thought', self.rollcall.absent_thought),
                ('rollcall.kneel_thought', self.rollcall.kneel_thought), ('slack.thought', self.slack.thought),
                ('chat.good_thought', self.chat.good_thought),
                ('cases.sanction_thought', self.cases.sanction_thought)]
        keys += [('needs.act_thought', v) for v in self.needs.act_thought.values()]
        keys += [('ladder', st.thought) for st in self.ladder if st.thought]
        for where, k in keys:
            need_in(where, k, self.thoughts, '想法键')
        for where, k in (('chat.good_mod', self.chat.good_mod), ('chat.bad_mod', self.chat.bad_mod),
                         ('cases.accuse_mod', self.cases.accuse_mod), ('announce.mod', self.announce.mod)):
            need_in(where, k, self.mods, '修正项键')
        if not self.ladder:
            out.append('ladder 不能为空')
        if set(self.kitchen.prep) != set(self.meal_slots):
            out.append('kitchen.prep 的键必须正是 meal_slots')
        if set(self.needs.init) != set(NEED_KEYS) or set(self.needs.base) != set(NEED_KEYS):
            out.append('needs.init / needs.base 必须正好覆盖 %s' % (NEED_KEYS,))
        if not set(TRAIT_KEYS) <= set(self.traits.mean) or not set(TRAIT_KEYS) <= set(self.traits.sd):
            out.append('traits.mean / traits.sd 必须覆盖 %s' % (TRAIT_KEYS,))
        if set(self.mood.weights) != set(NEED_KEYS):
            out.append('mood.weights 必须覆盖 %s' % (NEED_KEYS,))
        used_layers = (L_FORCED, L_PENALTY, L_REACT, L_DUTY, L_PHYS, L_DEVIANT, L_ROUTINE, L_GROUP, L_POST, L_ERRAND,
                       L_IDENT, L_SLACK, L_FREE)
        for lay in used_layers:
            need_in('layer_rank', lay, self.layer_rank, '层标签')
        if len(self.groups) != 2:
            out.append('groups 必须是 (清众, 执事) 两项')
        return out
