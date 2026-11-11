"""场景：原型 npc_spike.py 的 60 僧 30 日，以及实验 N1。

proto60_spec() 构造出与原型逐项一致的一套 SiteSpec（原型里的硬编码常量全部在这里，一个数一个出处）；
proto60_roster() 给出 60 人名册；PROTO60_CAST 是三个手工指定的“要角”（馋而散漫、懒、刚正）；
ProtoRun 把以上装配成可跑的世界（StandaloneHost + NpcEngine），默认用 rnd_b2 复现原型哈希。
脚本（gossip / ill）是场景的一部分，见 model.Script。
"""
from ..core import rnd_b2
from .events import (ABSENCE, BED_EMPTY, FOOD_THEFT, REPORT, SANCTION, SLACK, THEFT_FOUND)
from .engine import NpcEngine
from .host import StandaloneHost
from .model import PersonSpec, Script
from .spec import (A_BATH, A_CHANT, A_CHAT, A_MARTIAL, A_MEAL, A_REST, A_STROLL, A_STUDY, A_WASH, A_ZAZEN, OWN_BED,
                   AdSpec, AnnounceSpec, CaseSpec, ChatSpec, CommonSpec, CourtSpec, ForcedSpec, FreeSpec, GateSpec,
                   GroupAct, IllSpec, InventorySpec, JobSpec, JobsSpec, KitchenSpec, LadderStep, LazySpec, LibrarySpec,
                   ModSpec, MoodSpec, NeedSpec, NeedTerm, OfficeSpec, OpinionSpec, PatrolSpec, PenaltySpec, PhysSpec,
                   ReportSpec, RollCallSpec, RumorSpec, SiteSpec, SlackSpec, TemptSpec, ThoughtSpec, TraitSpec,
                   UposathaSpec)

PROTO_SEED = 20261110

# ---- 原型 main() 的实验参数（场景的一部分，report.py 只引用这里）----
GOSSIP_DAY, GOSSIP_WHO, GOSSIP_HEARD = 6, 8, 9     # 传闻实验：第 6 日，清众第 9 位偷食、第 10 位撞见（清众序号从 0 起）
N1_DAY, N1_DAYS, N1_COOKS = 10, 4, 3               # 实验 N1：第 10 日起典座与前 3 名饭头同时病倒 4 日
N1_WINDOW = (9, 16)                                # N1 的逐日偷食累计看第 9–16 日
LONG_DAYS = 90                                     # “90 日”那一行
EXTRA_SEEDS = (1, 2, 3, 4, 5)                      # 多种子那几行

# 原型的三个“要角”：(清众里的第几位, 性格改写)。第 6 位馋而散漫（惯犯），第 12 位懒，第 21 位刚正。
PROTO60_CAST = ((5, {'T': 92, 'S': 22, 'D': 45}), (11, {'D': 18, 'S': 38}), (20, {'R': 95, 'S': 90}))
PROTO60_GLUTTON, PROTO60_LAZY = 5, 11            # 清众序号


def proto60_spec():
    places = {'hall': '大雄宝殿', 'zen': '禅堂', 'ref': '斋堂', 'kit': '香积厨', 'store': '库房', 'dorm1': '东寮',
              'dorm2': '西寮', 'dorm3': '后寮', 'lib': '藏经阁', 'yard': '练武场', 'garden': '菜园', 'gate': '山门',
              'bath': '浴室', 'court': '戒律院', 'inf': '延寿堂', 'clo': '廊下', 'well': '井台', 'woods': '后山',
              'mill': '磨坊', 'abbot': '方丈室', 'office': '库院'}
    roam = ('clo', 'kit', 'hall', 'dorm1', 'dorm2', 'dorm3', 'gate', 'lib', 'yard', 'well', 'garden', 'zen')
    O = OfficeSpec
    offices = (
        O('方丈', 1, 'abbot', (5, 8), '玄', True, False), O('监院', 1, 'office', (5, 8), '慧', True, False),
        O('维那', 1, None, (), '慧', True, False), O('典座', 1, None, (), '慧', False, True),
        O('饭头', 4, None, (), '慧', False, True), O('库头', 1, 'store', (5, 8), '慧', False, False),
        O('知客', 1, 'gate', (5, 7, 8), '慧', False, False), O('藏主', 1, 'lib', (5, 7, 8), '慧', False, False),
        O('园头', 1, 'garden', (5, 8), '慧', False, False), O('园工', 5, 'garden', (5, 8), '慧', False, False),
        O('首座', 1, 'court', (5, 8), '玄', True, False), O('执事', 2, 'court', (5, 8), '慧', True, False),
        O('僧值', 2, None, (), '慧', True, False), O('堂主', 1, 'inf', (5, 7, 8), '慧', False, False))
    eff = {'sleep': {'e': 36}, 'rest': {'e': 22}, 'chant': {'s': 2, 'a': 3}, 'meal': {'s': 2},
           'zazen': {'e': 3, 'a': 4}, 'work': {'e': -2, 'c': -2}, 'martial': {'e': -3, 'c': -3, 'h': -3},
           'study': {'a': 3}, 'bath': {'c': 60}, 'wash': {'c': 25}, 'chat': {'s': 16}, 'stroll': {'s': 2, 'e': 2},
           'patrol': {'e': -1}, 'guard': {}, 'report': {}, 'kneel': {'e': -3}, 'confined': {'e': 4, 's': -2},
           'sick': {'e': 16}, 'steal': {'h': 30}}
    cat = {'sleep': '睡眠', 'rest': '睡眠', 'chant': '课诵', 'zazen': '坐禅', 'meal': '斋食', 'work': '作务',
           'patrol': '作务', 'guard': '作务', 'martial': '自修', 'study': '自修', 'bath': '洗沐', 'wash': '洗沐',
           'chat': '交游', 'stroll': '交游', 'report': '其他', 'kneel': '受罚', 'confined': '受罚', 'sick': '病',
           'steal': '其他'}
    N = NeedTerm
    ads = (
        AdSpec(A_REST, OWN_BED, '小憩', (N('e', 22, ()),), None, ('idle', 'D', 0.5, None), None),
        AdSpec(A_ZAZEN, 'zen', '坐禅', (N('a', 4, (('禅', 15),)), N('e', 3, ())), ('D', 0.6, 125),
               ('track', 'D', 0.9, '禅'), None),
        AdSpec(A_MARTIAL, 'yard', '习武', (N('a', 6, (('武', 23),)), N('e', -3, ())), ('D', 0.6, 125),
               ('track', 'D', 0.9, '武'), None),
        AdSpec(A_WASH, 'well', '浣洗', (N('c', 25, ()),), None, None, None),
        AdSpec(A_CHAT, 'clo', '闲谈', (N('s', 16, ()),), ('G', 0.5, 100), ('trait', 'G', 0.9, None), None),
        AdSpec(A_STUDY, 'lib', '读经', (N('a', 6, (('学', 23),)),), ('D', 0.6, 125), ('track', 'D', 0.9, '学'),
               'lib_open'),
        AdSpec(A_BATH, 'bath', '沐浴', (N('c', 60, ()),), None, None, 'bath_day'))
    J = JobSpec
    board = (J(1, '挑水', 'well', 4, 'water'), J(2, '打柴', 'woods', 6, 'wood'), J(3, '舂米', 'mill', 4, None),
             J(4, '菜园帮工', 'garden', 6, None), J(5, '洒扫', 'hall', 2, None), J(5, '洒扫', 'zen', 2, None),
             J(5, '洒扫', 'clo', 2, None), J(5, '洒扫', 'dorm1', 3, None))
    G = GroupAct
    return SiteSpec(
        name='少林寺·原型六十僧',
        places=places,
        capacity={'lib': 10, 'yard': 24, 'bath': 24, 'well': 8, 'zen': 70, 'clo': 60},
        cap_default=999,
        dorms=('dorm1', 'dorm2', 'dorm3'),
        roam=roam,
        night=(11, 0, 1),
        night_label='就寝',
        rotate=(7, 3),
        meal_slots=(4, 6),
        offices=offices,
        office_track_cycle='禅学武',
        name_pool='明净空海山石泉松竹云月风清远静定觉悟通达道德仁义礼智信诚真善忍和安宁平康福寿喜乐观照闻思修证法宝因缘果行愿力圆融正见坚勤朴厚',
        common_prefix='虚',
        common_tracks=(('武', 14), ('学', 10), ('禅', None)),
        groups=('清众', '执事'),
        traits=TraitSpec(mean={'D': 60, 'S': 62, 'G': 50, 'T': 42, 'R': 55}, sd={'D': 20, 'S': 20, 'G': 22, 'T': 22, 'R': 22},
                         office_bonus={'D': 8, 'S': 8}, lo=5, hi=98),
        group={2: G('zen', A_ZAZEN, '晨坐'), 3: G('hall', A_CHANT, '早课'), 4: G('ref', A_MEAL, '早斋'),
               6: G('ref', A_MEAL, '午斋'), 9: G('hall', A_CHANT, '晚课'), 10: G('zen', A_ZAZEN, '晚坐')},
        uposatha=UposathaSpec(days=(1, 15), by='day', slot=7, what=G('hall', A_CHANT, '布萨诵戒')),
        common=CommonSpec(work_slot=5, class_slot=8,
                          classes={'武': G('yard', A_MARTIAL, '习武'), '学': G('lib', A_STUDY, '读经'),
                                   '禅': G('zen', A_ZAZEN, '坐禅')},
                          overflow_place='hall', overflow_suffix='（改在讲堂）'),
        post_suffix='理事',
        library=LibrarySpec(office='藏主', slots=(5, 7, 8)),
        kitchen=KitchenSpec(place='kit', dining_place='ref', slots=(2, 3, 5, 8), label_staff='厨务',
                            label_proxy='代理帮厨', prep={4: 3, 6: 5}, min_staff=3,
                            stock_use=(('water', 2), ('wood', 2)), gain_full=45, gain_half=22, acting_target=4,
                            stock_init={'water': 8, 'wood': 8}),
        patrol=PatrolSpec(office='僧值', pool=roam, pick=3, night_slots=(0, 1), day_slots=(5, 7, 8),
                          rest_slots=(7, 8), labels=('巡夜', '巡寮'), rest_label='巡夜后补觉',
                          bed_check_slots=(0, 1), bed_exempt_layers=('值守', '强制'), bed_thought='warned_bed'),
        gate=GateSpec(place='gate', slots=(5, 7, 8), count=2, label='山门值守'),
        court=CourtSpec(place='court', judges=('首座', '执事'), judge_slot=5, report_slots=(5, 8),
                        report_label='到戒律院举报'),
        rollcall=RollCallSpec(office='维那', place='hall', slots=(3, 9), exempt_layers=('强制', '值守', '反应'),
                              window=10, limit=3, kneel_days=2, kneel_txt='缺课跪香', absent_thought='warned_absent',
                              kneel_thought='sanction'),
        inventory=InventorySpec(slot=2, p_find=0.7),
        forced=ForcedSpec(ill_place='inf', conf_place='court', sleep_extra_slots=(2,), ill_sleep='卧病',
                          ill_meal='病号饭', ill_other='卧病', conf_sleep='禁闭', conf_meal='禁闭送饭', conf_other='禁闭'),
        penalty=PenaltySpec(kneel_slot=7, place='hall', label='罚跪香'),
        phys=PhysSpec(faint_e=10, faint_label='昏沉不支', starve_h=12, starve_s=55, starve_label='饿极偷食',
                      endure_thought='endure'),
        temptation=TemptSpec(th_base=35, t_mid=40, t_slope=0.7, s_line=45, k=1.6, p_cap=0.9, night_slot=1,
                             night_label='夜里偷食', after_slot=7, after_label='午后偷食'),
        lazy=LazySpec(wake_slots=(2, 3), roll_slot=2, d_line=35, d_div=60, label='贪睡不起', tired_e=25,
                      tired_label='困乏未起'),
        slack=SlackSpec(d_line=40, d_div=80, low_mood_add=0.15, window=10, limit=3, kneel_days=1,
                        thought='warned_slack'),
        illness=IllSpec(p=0.004, min_days=1, span=3),
        needs=NeedSpec(init={'h': 70.0, 'e': 80.0, 'c': 70.0, 's': 60.0, 'a': 60.0},
                       base={'h': -7.0, 'e': -6.0, 'c': -1.0, 's': -1.6, 'a': -3.0}, eff=eff,
                       bonus={'martial': ('武', 23, 6), 'study': ('学', 20, 3), 'zazen': ('禅', 11, 0)},
                       category=cat, category_default='其他', act_thought={A_BATH: 'bath'}, hunger_sleep=-3,
                       hunger_t_mid=40, hunger_t_div=400, social_g=(0.5, 100), morning_slot=2, morning_c=6,
                       duty_layers=('岗位', '值守'), duty_a=6, urgency_floor=0.05, urgency_pow=2, hungry_line=25,
                       tired_line=20),
        ads=ads,
        free=FreeSpec(top_k=3, stroll_place='clo', stroll_act=A_STROLL, stroll_label='散步', bath_every=5,
                      bath_phase=4, bath_slots=(7, 8),
                      choice_key_chars=2),
        jobs=JobsSpec(board=board, work_chat_p=0.6),
        opinion=OpinionSpec(same_dorm=5, same_track=4, same_post=6, compat_div=300, compat_mid=0.75, compat_w=40,
                            lo=-100, hi=100, friend_line=25, foe_line=-15),
        mods={'good': ModSpec('投机', 4, 30, 8), 'bad': ModSpec('不投机', -4, 20, 5),
              'accuse': ModSpec('告发', -30, 60, 1), 'sin': ModSpec('犯戒', -5, 30, 2)},
        thoughts={'endure': ThoughtSpec('忍饥', -3, 1, 2), 'chat_good': ThoughtSpec('谈得来', 2, 1, 3),
                  'sanction': ThoughtSpec('受处分', -8, 3, 3), 'flogged': ThoughtSpec('受杖', -15, 5, 3),
                  'bath': ThoughtSpec('沐浴', 4, 1, 1), 'warned_bed': ThoughtSpec('受训诫', -3, 3, 3),
                  'warned_absent': ThoughtSpec('受训诫', -4, 5, 3), 'warned_slack': ThoughtSpec('受训诫', -3, 3, 3)},
        mood=MoodSpec(weights={'h': 0.28, 'e': 0.22, 'c': 0.10, 's': 0.15, 'a': 0.25}, low_line=35),
        chat=ChatSpec(good_base=0.7, good_mid=0.5, good_w=0.6, pair_noise=30, gain_when_brief=4,
                      lone_label='无人可谈，独自散步', good_mod='good', bad_mod='bad', good_thought='chat_good'),
        rumor=RumorSpec(penalty=12, decay=2, min_strength=25, p_add=0.2, p_cap=1.0, g_off=0.5, g_div=100, keep=16),
        salience={FOOD_THEFT: 80, SANCTION: 60, THEFT_FOUND: 50, ABSENCE: 0, SLACK: 0, REPORT: 0, BED_EMPTY: 0},
        report=ReportSpec(base=0.15, r_w=0.6, op_w=0.004, lo=0.02, hi=0.98),
        cases=CaseSpec(open='在查', done='已处分', cold='悬案', closed='结案', stale_days=10, confess_base=0.25,
                       confess_r=0.5, accuse_mod='accuse', sanction_thought='sanction',
                       via_report='举报', via_confess='认错'),
        ladder=(LadderStep('罚跪香三日', 3, 0, (), None, False),
                LadderStep('杖责并禁闭二日', 0, 2, (('e', -30),), 'flogged', False),
                LadderStep('禁闭五日', 0, 5, (), None, False),
                LadderStep('迁单出寺', 0, 0, (), None, True)),
        announce=AnnounceSpec(slot=6, place='ref', s_line=60, mod='sin'),
        layer_rank={'强制': 1, '处分': 2, '反应': 3, '值守': 5, '生理': 6, '集体': 7, '岗位': 8, '身份': 9,
                    '差事': 9, '作息': 9, '自由': 10, '越轨': 0, '怠工': 0},
    )


def pid_of(ix):
    """原型名册的外部编号：P0001 起。"""
    return 'P%04d' % (ix + 1)


def _common_track(spec, j):
    """清众里第 j 位（从 0 起）的修行方向：按 common_tracks 依次分段，None 表示其余全部。"""
    for track, cnt in spec.common_tracks:
        if cnt is None or j < cnt:
            return track
        j -= cnt
    return spec.common_tracks[-1][0]


def proto60_roster(spec, n=60):
    """名册：先按岗位表依次排岗位人员，其余为清众（姓名、修行方向、寮房都由序号决定）。"""
    pool, cyc, dorms = spec.name_pool, spec.office_track_cycle, spec.dorms
    out = []
    for o in spec.offices:
        for _ in range(o.count):
            i = len(out)
            out.append(PersonSpec(pid_of(i), o.prefix + pool[i], o.name, cyc[i % len(cyc)], dorms[i % len(dorms)]))
    for j in range(n - len(out)):
        i = len(out)
        out.append(PersonSpec(pid_of(i), spec.common_prefix + pool[i % len(pool)], None, _common_track(spec, j),
                              dorms[i % len(dorms)]))
    return out


class ProtoRun:
    """一个可跑的原型世界。参数同原型 World：seed、n（人数）、days、acting（监院派人代理）、observer、script。"""

    def __init__(self, seed=PROTO_SEED, n=60, days=30, acting=True, observer=None, script=None, rng=rnd_b2,
                 spec=None, host=None):
        self.spec = spec or proto60_spec()
        self.days = days
        self.host = host or StandaloneHost(seed, rng)
        self.engine = NpcEngine(self.spec, self.host, acting=acting, script=script)
        for ps in proto60_roster(self.spec, n):
            self.engine.add_person(ps)
        for k, tr in PROTO60_CAST:
            self.engine.set_traits(self.engine.common[k].ix, **tr)
        self.engine.set_observer(observer)
        self.hash = None

    @property
    def common(self):
        return self.engine.common

    @property
    def glutton(self):
        return self.engine.common[PROTO60_GLUTTON]

    @property
    def lazy(self):
        return self.engine.common[PROTO60_LAZY]

    def run(self):
        for day in range(1, self.days + 1):
            self.engine.run_day(day)
        self.hash = self.engine.state_hash()
        return self


def gossip_script(run_or_engine_common):
    """原型 main() 的传闻实验脚本：第 6 日，清众里第 9 位偷食，只有第 10 位撞见且不举报。"""
    c = run_or_engine_common
    return Script(gossip=(GOSSIP_DAY, c[GOSSIP_WHO].ix, c[GOSSIP_HEARD].ix))


def n1_script(engine):
    """实验 N1：第 10 日起典座与三名饭头同时病倒 4 日。"""
    kit = engine.by['典座'] + engine.by['饭头'][:N1_COOKS]
    return Script(ill=(N1_DAY, kit, N1_DAYS))
