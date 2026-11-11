"""由 defs 构造规格：SiteSpec.from_defs(defs, 'scenario:proto60:main') 的实现（ARCHITECTURE 第 4、6 节）。

一个 scope（编号的中间一段，如 proto60）下的全部定义拼成一份 SiteSpec：
  place 场所、facility 设施、interaction 交互、post 岗位、job 差事、trait 性格、package 行为包、thought 想法、modifier 好恶修正项、
  event 事件显著度、norm 规范、ladder 处分阶梯、org 组织与部门、rule 站点级规则。
单例类（rule / org / norm）按角色名取：角色名是 role 字段，没写就取编号的最后一段（与内核按角色名取东西的约定一致）。
次序敏感的定义带 order（岗位、差事、广告）；行为包的次序由 rule:stack 的 packages 列表决定。

校验是“读字段时顺手做”的：缺字段、字段类型不对、未知字段（多半是拼错）、引用不存在的定义、处理器未登记、参数不合法、
同 scope 里没被任何地方用到的定义（多半是漏了引用），都记成一条问题，最后一起抛 SpecError，每条写明哪条定义的哪个字段。
Reader 读字段时同时登记“字段表”（field_docs()），docs/NPC_ENGINE.md 第 12 节的字段表由它生成，并有测试核对文档没有漏字段。
"""
from .events import LABELS as EVENT_LABELS
from .handlers import GATES, GATE_PARAMS, PACKAGE_HANDLERS, REQUIRED
from .spec import (NEED_KEYS, OWN_BED, ROTATE_ARITY, TRAIT_KEYS, AdSpec, AnnounceSpec, CaseSpec, ChatSpec, CourtSpec, DoSpec, FreeSpec,
                   GateSpec, GossipSpec, IllSpec, InteractionSpec, InventorySpec, JobSpec, JobsSpec, KitchenSpec, LadderStep,
                   MoodLine, MoodSpec, ModSpec, N1Spec, NeedSpec, NeedTerm, OfficeSpec, OpinionSpec, PackageSpec, PatrolSpec,
                   ReportSpec, RollCallSpec, RumorSpec, ScenarioSpec, SiteSpec, SlackSpec, SpecError, ThoughtSpec,
                   TraitSpec, ViolationSpec, WhenSpec, WhoSpec)

# 任何定义都可带的元字段（加载器与排序用）；其余字段必须是本模块读过的，否则报“未知字段”
META_KEYS = frozenset({'id', 'kind', '_file', 'parent', '_abstract', 'note', 'notes', 'text', 'desc', 'doc', 'comment',
                       'order', 'kernel', 'role'})
# 引擎认识的角色名（org / norm / rule 各取其一，见 Ctx.role）；测试的“业务词不进引擎代码”据此豁免这几个结构性的名字
ROLES = ('main', 'kitchen', 'patrol', 'gate', 'court', 'theft', 'absence', 'slack', 'bed', 'stack', 'layers', 'schedule', 'needs',
         'illness', 'board', 'opinion', 'chat', 'rumor', 'mood', 'free', 'gossip', 'n1')
SCENARIO_ID_PARTS = 3                                    # 场景编号 scenario:<scope>:<名> 的段数
DEFAULT_DURATION = 1                                     # 交互的缺省时长（时辰）：引擎按时辰决定
SCOPE_KINDS = ('place', 'facility', 'interaction', 'post', 'job', 'trait', 'package', 'thought', 'modifier', 'event',
               'norm', 'ladder', 'org', 'rule')          # 本模块消费的类别：同 scope 里没被用到的定义会被报出来
_TYPE_NAMES = {'int': '整数', 'num': '数', 'str': '字符串', 'bool': '布尔'}
_NONE = object()                                         # 读字段时“没有默认值（可缺省为 None）”的占位


class _Cascade(Exception):
    """前面已经记过问题，后面的装配因此无法继续（不是新问题）。"""


class Ctx:
    """一次构造的上下文：defs、scope、问题表、已用定义、字段表。"""

    def __init__(self, defs, scope):
        self.defs, self.scope = defs, scope
        self.problems = []
        self.used = set()
        self.docs = {}                  # (类别, 字段路径) -> (类型, 必填, 默认值, 说明)

    def err(self, where, msg):
        self.problems.append('%s：%s' % (where, msg))

    def use(self, d):
        self.used.add(d['id'])
        return d

    def scoped(self, kind, mark=True):
        """本 scope 下某 kind 的全部（非抽象）定义，按 (order, 编号) 排序；mark = True 时全部标记为已用。
        想法、修正项这类“该有人引用”的定义用 mark = False 读：没被任何地方引用的由末尾的检查报出（多半是漏了引用）。"""
        rows = [d for d in self.defs.by_kind(kind) if d['id'].split(':')[1] == self.scope]
        rows.sort(key=lambda d: (d.get('order', 0), d['id']))
        if mark:
            for d in rows:
                self.use(d)
        return rows

    def role(self, kind, role, required=True):
        """本 scope 下 kind 类别里角色为 role 的那一条（role 字段，没写取编号最后一段）。"""
        rows = [d for d in self.defs.by_kind(kind) if d['id'].split(':')[1] == self.scope
                and d.get('role', d['id'].rpartition(':')[2]) == role]
        if len(rows) == 1:
            return self.use(rows[0])
        if rows:
            self.err('scope %s' % self.scope, '%s 的角色 %r 有 %d 条定义：%s' % (kind, role, len(rows), '、'.join(d['id'] for d in rows)))
        elif required:
            self.err('scope %s' % self.scope, '缺少 %s 的角色 %r（编号形如 %s:%s:%s，或写 role = "%s"）' % (kind, role, kind, self.scope, role, role))
        return None

    def resolve(self, where, ref, kind):
        """ref 是 kind 类的定义编号：返回（已展开继承的）定义，否则记问题返回 None。"""
        if not isinstance(ref, str) or ':' not in ref:
            self.err(where, '应引用一条 %s 定义的编号，得到 %r' % (kind, ref))
            return None
        if ref not in self.defs:
            self.err(where, '引用了不存在的 %s' % ref)
            return None
        if ref.partition(':')[0] != kind:
            self.err(where, '应引用 %s 类定义，得到 %s' % (kind, ref))
            return None
        return self.use(self.defs.get(ref))

    def place_code(self, where, ref):
        d = self.resolve(where, ref, 'place')
        if d is None:
            return None
        if 'code' not in d:
            self.err(where, '%s 没有 code' % ref)
            return None
        return d['code']

    def doc(self, kindname, path, typ, required, default, text):
        self.docs.setdefault((kindname, path), (typ, required, default, text))

    def guard(self, fn, *a):
        """跑一段装配：前面已经记过问题时，装配里因缺东西抛的异常不算新问题（返回 None）。"""
        n = len(self.problems)
        try:
            return fn(*a)
        except (_Cascade, KeyError, TypeError, AttributeError, IndexError, ValueError):
            if len(self.problems) == n and not self.problems:
                raise
            return None


def _kind_label(d):
    kind = d['id'].partition(':')[0]
    if kind in ('rule', 'org', 'norm'):
        return '%s:%s' % (kind, d.get('role', d['id'].rpartition(':')[2]))
    return kind


class Reader:
    """读一条定义（或其中一张子表）的字段：登记字段表、校验类型、记录问题；finish() 查未知字段。"""

    def __init__(self, ctx, d, path='', kindname=None, id_=None):
        self.ctx, self.d, self.path = ctx, d, path
        self.id = id_ or d['id']
        self.kindname = kindname or _kind_label(d)
        self.seen = set()

    def where(self, key):
        return '%s 的字段 %s%s' % (self.id, self.path, key)

    def _get(self, key, typ, doc, default):
        required = default is REQUIRED
        self.ctx.doc(self.kindname, self.path + key, typ, required, None if required else default, doc)
        self.seen.add(key)
        if key in self.d:
            return self.d[key], True
        if required:
            self.ctx.err(self.id, '缺少字段 %s%s：%s' % (self.path, key, doc))
            return None, False
        return default, False

    def _bad(self, key, typ, v):
        self.ctx.err(self.id, '字段 %s%s 应是 %s，得到 %r' % (self.path, key, _TYPE_NAMES.get(typ, typ), v))

    def int(self, key, doc, default=REQUIRED):
        v, got = self._get(key, 'int', doc, default)
        if got and (not isinstance(v, int) or isinstance(v, bool)):
            self._bad(key, 'int', v)
            return None
        return v

    def num(self, key, doc, default=REQUIRED):
        v, got = self._get(key, 'num', doc, default)
        if got and (not isinstance(v, (int, float)) or isinstance(v, bool)):
            self._bad(key, 'num', v)
            return None
        return v

    def str(self, key, doc, default=REQUIRED):
        v, got = self._get(key, 'str', doc, default)
        if got and not isinstance(v, str):
            self._bad(key, 'str', v)
            return None
        return v

    def bool(self, key, doc, default=REQUIRED):
        v, got = self._get(key, 'bool', doc, default)
        if got and not isinstance(v, bool):
            self._bad(key, 'bool', v)
            return None
        return v

    def list(self, key, item, doc, default=REQUIRED):
        """item：'int' / 'num' / 'str'。返回元组。"""
        v, got = self._get(key, '[%s]' % item, doc, default)
        if not got:
            return None if v is None else tuple(v)
        if not isinstance(v, list):
            self._bad(key, '[%s]' % item, v)
            return None
        ok = {'int': lambda x: isinstance(x, int) and not isinstance(x, bool), 'str': lambda x: isinstance(x, str),
              'num': lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)}[item]
        if not all(ok(x) for x in v):
            self._bad(key, '[%s]' % item, v)
            return None
        return tuple(v)

    def one_or_list(self, key, item, doc, default=REQUIRED):
        """一个值或一组值（如 slot = 5 或 slot = [5, 8]）：返回元组。"""
        v, got = self._get(key, '%s | [%s]' % (item, item), doc, default)
        if not got:
            return None if v is None else tuple(v)
        vals = v if isinstance(v, list) else [v]
        ok = {'int': lambda x: isinstance(x, int) and not isinstance(x, bool), 'str': lambda x: isinstance(x, str)}[item]
        if not vals or not all(ok(x) for x in vals):
            self._bad(key, '%s | [%s]' % (item, item), v)
            return None
        return tuple(vals)

    def raw(self, key, doc, default=REQUIRED, typ='表'):
        """原样取一个值（表或其他）：处理器的 params 之类，由调用者校验。"""
        v, got = self._get(key, typ, doc, default)
        return v

    def table(self, key, doc, default=REQUIRED):
        """子表：返回子 Reader；缺省且默认不是 REQUIRED 时返回 None。"""
        v, got = self._get(key, '表', doc, default)
        if not got:
            return None
        if not isinstance(v, dict):
            self._bad(key, '表', v)
            return None
        return Reader(self.ctx, v, self.path + key + '.', self.kindname, self.id)

    def tables(self, key, doc, default=REQUIRED):
        """表的列表：返回子 Reader 列表（路径里记作 key[].）。"""
        v, got = self._get(key, '[表]', doc, default)
        if not got:
            return None if v is None else []
        if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
            self._bad(key, '[表]', v)
            return None
        return [Reader(self.ctx, x, self.path + key + '[].', self.kindname, self.id) for x in v]

    def numdict(self, key, doc, default=REQUIRED, keys=None):
        """{键: 数}：返回 dict；keys 给定时键必须在其中。"""
        v, got = self._get(key, '{键: 数}', doc, default)
        if not got:
            return None if v is None else dict(v)
        if not isinstance(v, dict) or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values()):
            self._bad(key, '{键: 数}', v)
            return None
        if keys is not None:
            bad = [k for k in v if k not in keys]
            if bad:
                self.ctx.err(self.id, '字段 %s%s 的键 %s 不在 %s 里' % (self.path, key, '、'.join(map(repr, bad)), '/'.join(keys)))
                return None
        return dict(v)

    def ref(self, key, kind, doc, default=REQUIRED):
        """引用另一条定义：返回已展开继承的定义（缺省为 None 时返回 None）。"""
        v, got = self._get(key, '引用 %s' % kind, doc, default)
        if not got:
            return None
        return self.ctx.resolve(self.where(key), v, kind)

    def refs(self, key, kind, doc, default=REQUIRED):
        v, got = self._get(key, '[引用 %s]' % kind, doc, default)
        if not got:
            return None if v is None else []
        if not isinstance(v, list):
            self._bad(key, '[引用 %s]' % kind, v)
            return None
        return [self.ctx.resolve('%s[%d]' % (self.where(key), i), x, kind) for i, x in enumerate(v)]

    def finish(self):
        extra = sorted(k for k in self.d if k not in self.seen and (self.path or k not in META_KEYS))
        if extra:
            self.ctx.err(self.id, '未知字段 %s（拼错了？）' % '、'.join(self.path + k for k in extra))


def _role_of(d):
    return d.get('role', d['id'].rpartition(':')[2])


def _ok(*xs):
    """读出的值里有 None（出过问题）就抛 _Cascade，让 guard 吞掉后续装配。"""
    if any(x is None for x in xs):
        raise _Cascade()
    return xs


def _each(rows, fn):
    """对每条定义各跑一遍 fn，某条读不全（_Cascade）只丢掉那一条、继续读下一条：这样一次能报出所有定义的问题，不止第一条。"""
    out = []
    for d in rows:
        try:
            out.append(fn(d))
        except _Cascade:
            continue
    return out


# ================================================================= 装配
class Builder:
    def __init__(self, ctx):
        self.ctx = ctx
        self.places = {}                # code -> 显示名
        self.thoughts, self.mods = {}, {}
        self.events = {}                # 事件定义编号 -> code

    # ---------------------------------------------------------------- 场所、设施、岗位、差事、性格
    def build_places(self):
        out = {}
        for d in self.ctx.scoped('place'):
            r = Reader(self.ctx, d)
            code = r.str('code', '运行时钥匙；原型场景沿用原型短码（它进随机数键与基线哈希）')
            name = r.str('name', '显示名（不进哈希）')
            r.finish()
            if code in out:
                self.ctx.err(d['id'], 'code %r 重复' % code)
            out[code] = name
        self.places = out
        return out

    def build_capacity(self):
        out = {}
        for d in self.ctx.scoped('facility'):
            r = Reader(self.ctx, d)
            place = r.ref('place', 'place', '设施所在的场所')
            stations = r.int('stations', '工位数：同一时辰最多几人占用（占位即预约）；不写 = 不限', default=None)
            r.finish()
            if stations is not None and place is not None:
                out[place['code']] = stations
        return out

    def build_offices(self):
        return tuple(_each(self.ctx.scoped('post'), self._office))

    def _office(self, d):
        r = Reader(self.ctx, d)
        name = r.str('name', '岗位名')
        count = r.int('count', '编制')
        prefix = r.str('prefix', '法名前缀（建人用）')
        disc = r.bool('disc', '纪律执事：当面禀告的对象、见证必报', default=False)
        kitchen = r.bool('kitchen', '厨房职事', default=False)
        r.finish()
        return OfficeSpec(*_ok(name, count, prefix, disc, kitchen))

    def build_traits(self):
        out = {}
        for d in self.ctx.scoped('trait'):
            r = Reader(self.ctx, d)
            key = d['id'].rpartition(':')[2]
            if key not in TRAIT_KEYS:
                self.ctx.err(d['id'], '性格键必须是 %s（编号的最后一段）' % '/'.join(TRAIT_KEYS))
                continue
            r.str('name', '中文名（说明用）')
            out[key] = dict(mean=r.num('mean', '开局均值（0–100）'), sd=r.num('sd', '开局标准差'),
                            office_bonus=r.num('office_bonus', '有岗位者的均值加成', default=0), lo=r.num('lo', '取值下限'),
                            hi=r.num('hi', '取值上限'))
            r.finish()
        miss = [k for k in TRAIT_KEYS if k not in out]
        if miss:
            self.ctx.err('scope %s' % self.ctx.scope, '缺少性格定义 %s（trait:%s:<键>）' % ('、'.join(miss), self.ctx.scope))
            raise _Cascade()
        pick = lambda field: {k: out[k][field] for k in TRAIT_KEYS}
        return TraitSpec(mean=pick('mean'), sd=pick('sd'), office_bonus={k: v for k, v in pick('office_bonus').items() if v},
                         lo=pick('lo'), hi=pick('hi'))

    def build_jobs(self):
        return tuple(_each(self.ctx.scoped('job'), self._job))

    def _job(self, d):
        r = Reader(self.ctx, d)
        prio = r.int('prio', '优先级：数字小的先被认领')
        name = r.str('name', '差事名')
        place = r.ref('place', 'place', '干活的场所')
        count = r.int('count', '当日需要几人')
        outputs = r.numdict('outputs', '产出物：物 -> 每名完成者入账的量', default={})
        r.finish()
        _ok(prio, name, place, count, outputs)
        return JobSpec(prio, name, place['code'], count, outputs)

    # ---------------------------------------------------------------- 想法、修正项、事件
    def build_thoughts(self):
        out = {}
        for d in self.ctx.scoped('thought', mark=False):        # 想法该有人引用：没被引用的由末尾的检查报出
            out[d['id'].rpartition(':')[2]] = None              # 先占位：这条读不全时，引用它的地方不再重复报“不在想法表里”
            r = Reader(self.ctx, d)
            vals = (r.str('label', '标签：同标签共用叠加上限'), r.num('value', '每条的心情增减'), r.int('days', '持续几日'),
                    r.int('cap', '同标签最多同时几条'))
            r.finish()
            if None not in vals:
                out[d['id'].rpartition(':')[2]] = ThoughtSpec(*vals)
        self.thoughts = out
        return out

    def build_mods(self):
        out = {}
        for d in self.ctx.scoped('modifier', mark=False):       # 修正项同理
            out[d['id'].rpartition(':')[2]] = None
            r = Reader(self.ctx, d)
            vals = (r.str('label', '种类：同种类共用叠加上限（不叫 kind：kind 是加载器保留字）'), r.num('value', '每条的好恶增减'),
                    r.int('days', '持续几日'), r.int('cap', '同种类最多几条（满了只续期最老的一条）'),
                    r.str('cause', '起因（“情”命令向玩家说明）'))
            r.finish()
            if None not in vals:
                out[d['id'].rpartition(':')[2]] = ModSpec(*vals)
        self.mods = out
        return out

    def build_events(self):
        out, codes = {}, {}
        for d in self.ctx.scoped('event'):
            r = Reader(self.ctx, d)
            code = r.str('code', '事件类型代码（tianl/npc/events.py 登记的）')
            sal = r.num('salience', '目击者得到的见闻强度（0 = 不产生见闻）')
            r.finish()
            _ok(code, sal)
            if code not in EVENT_LABELS:
                self.ctx.err(d['id'], '事件类型代码 %r 未在 events.py 登记（已登记：%s）' % (code, '、'.join(sorted(EVENT_LABELS))))
            out[code] = sal
            codes[d['id']] = code
        self.events = codes
        return out

    def thought_key(self, d):
        """想法定义 -> 键（编号最后一段）；必须是本 scope 登记过的。"""
        if d is None:
            return None
        key = d['id'].rpartition(':')[2]
        if key not in self.thoughts:
            self.ctx.err(d['id'], '想法 %s 不在本 scope 的想法表里' % d['id'])
        return key

    def mod_key(self, d):
        if d is None:
            return None
        key = d['id'].rpartition(':')[2]
        if key not in self.mods:
            self.ctx.err(d['id'], '修正项 %s 不在本 scope 的修正项表里' % d['id'])
        return key

    # ---------------------------------------------------------------- 交互、广告、违规
    def build_interactions(self):
        ctx = self.ctx
        inter, ads, viol = {}, [], {}
        ad_rows = []
        for d in ctx.scoped('interaction'):
            r = Reader(ctx, d)
            act = r.str('act', '活动代码（轨迹与哈希里的活动名）')
            st_raw = r.raw('station', '所需工位：facility 编号；"%s" = 本人寮房床位；不写 = 不占工位' % OWN_BED, default=None, typ='引用 facility | "%s"' % OWN_BED)
            duration = r.int('duration', '时长（时辰）；目前只接受 1（见 SiteSpec.validate）', default=DEFAULT_DURATION)
            effects = r.numdict('effects', '需求增减（每时辰）：{h,e,c,s,a: 数}', keys=NEED_KEYS, default={})
            inputs = r.numdict('inputs', '所需物：每次服务耗的物', default={})
            outputs = r.numdict('outputs', '产出物：做一次得的物', default={})
            adm = r.table('admission', '准入条件：gate = "<准入门名>"，其余键是该门的参数（只对有 ad 的交互起作用）', default=None)
            norm = r.ref('norm', 'norm', '触犯的规范：谁做了这件事，就触犯它（对旁人是偷食，对饭头的“厨务”是工作——后者是另一种活动）', default=None)
            category = r.str('category', '时间分配类别（统计口径）')
            bonus = r.table('track_bonus', '本方向做此事的志增量：track 方向、own 本方向、other 其余', default=None)
            thought = r.ref('thought', 'thought', '做了这件事就得到的想法', default=None)
            refrain = r.ref('refrain_thought', 'thought', '有理由做、却克制没做时得到的想法（饿极而不偷：忍饥）', default=None)
            ad = r.table('ad', '自由时段的广告（Sims）：label、terms 需求项、scale 性格系数、pref 性格偏好', default=None)
            station = None
            if st_raw == OWN_BED:
                station = OWN_BED
            elif st_raw is not None:
                fac = ctx.resolve(r.where('station'), st_raw, 'facility')
                if fac is not None:
                    pl = ctx.resolve('%s.place' % fac['id'], fac.get('place'), 'place')
                    station = pl['code'] if pl else None
            bonus_t = None
            if bonus is not None:
                bonus_t = (bonus.str('track', '修行方向'), bonus.num('own', '本方向的志增量'), bonus.num('other', '其余的志增量'))
                bonus.finish()
            adm_name, adm_params = None, {}
            if adm is not None:
                adm_name = adm.str('gate', '准入门名（handlers.GATES 登记的）')
                if adm_name in GATES:
                    adm_params = self.norm_params(d['id'] + ' 的准入门 %s' % adm_name, GATE_PARAMS[adm_name],
                                                  {k: v for k, v in adm.d.items() if k != 'gate'}, 'gate:' + adm_name)
                    adm.seen.update(adm.d)
                elif adm_name is not None:
                    ctx.err(d['id'], '准入门 %r 未登记（已登记：%s）' % (adm_name, '、'.join(sorted(GATES))))
            if adm is not None:
                adm.finish()
            if adm is not None and ad is None:
                ctx.err(d['id'], 'admission 只对自由时段的广告起作用：没有 ad 的交互不该写 admission')
            if None in (act, duration, effects, inputs, outputs, category):      # 这条读不全：丢掉它，继续读下一条（一次报全）
                r.finish()
                continue
            viol_t = None
            if norm is not None:
                if _role_of(norm) != 'theft':
                    ctx.err(d['id'], '触犯的规范 %s 必须是 role = "theft" 的越轨类规范' % norm['id'])
                elif station is None or station == OWN_BED:
                    ctx.err(d['id'], '触犯规范的交互必须有 station（事件发生在工位所在的场所）')
                else:
                    code = self.events.get(norm.get('event'))
                    if code is None:
                        ctx.err(d['id'], '规范 %s 的 event 必须引用本 scope 的一条 event 定义' % norm['id'])
                    else:
                        viol_t = ViolationSpec(norm.get('name', _role_of(norm)), code, station)
            if act in inter:
                ctx.err(d['id'], '活动代码 %r 重复' % act)
            inter[act] = InteractionSpec(
                act=act, station=station, duration=duration, effects=effects, inputs=inputs, outputs=outputs,
                norm=viol_t.norm if viol_t else None, category=category, bonus=bonus_t,
                thought=self.thought_key(thought), refrain_thought=self.thought_key(refrain))
            if viol_t:
                viol[act] = viol_t
            if ad is not None:
                ad_rows.append((d.get('order', 0), d['id'], act, station, ad, adm_name, adm_params))
            r.finish()
        for order, id_, act, station, ad, gate_name, gate_params in sorted(ad_rows, key=lambda x: (x[0], x[1])):
            label = ad.str('label', '广告名（自由时段的原因）')
            terms = []
            for t in ad.tables('terms', '需求项：need 需求键、w 增量、by_track 按方向区分的增量'):
                need = t.str('need', '需求键 h e c s a')
                w = t.num('w', '增量')
                bt = []
                for x in t.tables('by_track', '按方向区分的增量：[{ track, w }]', default=[]):
                    bt.append((x.str('track', '修行方向'), x.num('w', '该方向的增量')))
                    x.finish()
                bt = tuple(bt)
                t.finish()
                terms.append(NeedTerm(need, w, bt))
            sc = ad.table('scale', '性格系数：把需求项之和再乘 (off + 性格/div)；trait 性格键', default=None)
            scale = None
            if sc is not None:
                scale = (sc.str('trait', '性格键'), sc.num('off', '偏移'), sc.num('div', '刻度'))
                sc.finish()
            pf = ad.table('pref', '性格偏好：kind = trait（按性格）/ track（本方向才加）/ idle（越不精进越想歇），trait、coef、track', default=None)
            pref = None
            if pf is not None:
                pref = (pf.str('kind', 'trait / track / idle'), pf.str('trait', '性格键'), pf.num('coef', '系数'),
                        pf.str('track', '方向（kind = track 时）', default=None))
                pf.finish()
            ad.finish()
            ads.append(AdSpec(act, station, _ok(label)[0], tuple(terms), scale, pref, gate_name, gate_params))
        return inter, tuple(ads), viol

    def norm_params(self, where, schema, raw, docname):
        """处理器 / 准入门的参数：按参数表补默认值、把引用换成 code / 岗位名、列表换元组；不合法的记问题。docname 是字段表里的类别名。"""
        ctx = self.ctx
        known = {p.name: p for p in schema}
        for k in raw:
            if k not in known:
                ctx.err(where, '未知参数 %s（可用：%s）' % (k, '、'.join(sorted(known)) or '无'))
        out = {}
        for p in schema:
            if p.name in raw:
                v = raw[p.name]
            elif p.required:
                ctx.err(where, '缺少参数 %s（%s）' % (p.name, p.doc))
                continue
            else:
                v = p.default
            ctx.doc(docname, p.name, p.type, p.required, None if p.required else p.default, p.doc)
            w2 = '%s 的参数 %s' % (where, p.name)
            if p.type == 'place':
                v = ctx.place_code(w2, v)
            elif p.type == 'post':
                d = ctx.resolve(w2, v, 'post')
                v = d['name'] if d else None
            elif p.type == 'posts':
                if isinstance(v, (list, tuple)):
                    ds = [ctx.resolve(w2, x, 'post') for x in v]
                    v = tuple(d['name'] for d in ds if d)
                else:
                    ctx.err(w2, '应是岗位编号的列表，得到 %r' % (v,))
                    v = None
            elif p.type in ('slots', 'strs'):
                v = tuple(v) if isinstance(v, (list, tuple)) else ((v,) if isinstance(v, (int, str)) and not isinstance(v, bool) else v)
            out[p.name] = v
        return out

    # ---------------------------------------------------------------- 行为包
    def build_packages(self, layers):
        ctx = self.ctx
        stack_def = ctx.role('rule', 'stack')
        r0 = Reader(ctx, stack_def)
        pdefs = r0.refs('packages', 'package', '行为包的判定先后：包的编号列表（自上而下第一个成立的生效）')
        r0.finish()
        _ok(pdefs)
        ctx.scoped('package')           # 同 scope 的包都标记为已用；没进栈的包由下面的检查报出
        in_stack = {d['id'] for d in pdefs if d}
        for d in ctx.defs.by_kind('package'):
            if d['id'].split(':')[1] == ctx.scope and d['id'] not in in_stack:
                ctx.err(d['id'], '这个包没有列进 %s 的 packages（不在栈里就永远不会生效；写错了？）' % stack_def['id'])
        return tuple(_each((d for d in pdefs if d is not None), self.package))

    def package(self, d):
        ctx = self.ctx
        r = Reader(ctx, d, kindname='package')
        layer = r.str('layer', '层标签（rule:layers 登记过的）')
        who = self.who(r.table('who', '谁适用：post 岗位列表 / status = common|holder / track 方向列表；不写 = 所有人', default=None))
        when = self.when(r.table('when', '何时成立：slot day day_of_month month festival weather season；不写 = 任何时候', default=None))
        do_r = r.table('do', '声明式：place act label [claim overflow]', default=None)
        handler = r.str('handler', '需要条件判断的包：登记过的处理器名（与 do 二选一）', default=None)
        raw = r.raw('params', '处理器的参数（见处理器的参数表）', default={})
        r.finish()
        do = None
        if do_r is not None:
            pl = do_r.raw('place', '场所：place 编号，或 "%s"（本人寮房）' % OWN_BED, typ='引用 place | "%s"' % OWN_BED)
            place = pl if pl in (OWN_BED, None) else ctx.place_code(do_r.where('place'), pl)
            act = do_r.str('act', '活动代码（要有对应的 interaction）')
            label = do_r.str('label', '原因')
            claim = do_r.bool('claim', '占一个工位（满员改去 overflow.place）', default=False)
            ov = do_r.table('overflow', '满员时：place 改去的场所、suffix 原因后缀', default=None)
            ov_place, ov_suffix = None, ''
            if ov is not None:
                ov_ref = ov.raw('place', '改去的场所', typ='引用 place')
                ov_place = ctx.place_code(ov.where('place'), ov_ref) if ov_ref is not None else None
                ov_suffix = ov.str('suffix', '原因后缀', default='')
                ov.finish()
            do_r.finish()
            do = DoSpec(*_ok(place, act, label, claim), ov_place, ov_suffix)
        params = {}
        if handler is not None:
            hd = PACKAGE_HANDLERS.get(handler)
            if hd is None:
                ctx.err(d['id'], '处理器 %r 未登记（已登记：%s）' % (handler, '、'.join(sorted(PACKAGE_HANDLERS))))
            elif not isinstance(raw, dict):
                ctx.err(d['id'], '字段 params 应是表')
            else:
                params = self.norm_params(d['id'] + ' 的处理器 %s' % handler, hd.params, raw, 'handler:' + handler)
        elif raw:
            ctx.err(d['id'], '没有 handler 的包不该有 params')
        return PackageSpec(d['id'], _ok(layer)[0], who, when, do, handler, params)

    def who(self, r):
        if r is None:
            return WhoSpec(None, None, None)
        posts = r.refs('post', 'post', '适用的岗位（任一）', default=None)
        status = r.str('status', 'common（无岗位的清众）| holder（有岗位者）', default=None)
        tracks = r.list('track', 'str', '适用的修行方向（任一）', default=None)
        r.finish()
        names = None if posts is None else tuple(p['name'] for p in posts if p)
        return WhoSpec(names, status, tracks)

    def when(self, r):
        if r is None:
            return WhenSpec(None, None, None, None, None, None, None, None)
        slots = r.one_or_list('slot', 'int', '时辰（子 0 … 亥 11）', default=None)
        periods = r.one_or_list('period', 'str', '时段名：night（夜间）/ meal（斋食时辰），取自 rule:schedule', default=None)
        days = r.one_or_list('day', 'int', '模拟日序号（原型口径：布萨在第 1、15 日）', default=None)
        doms = r.one_or_list('day_of_month', 'int', '历法的月内日（1–30）', default=None)
        months = r.one_or_list('month', 'int', '月（1–12）', default=None)
        fest = r.raw('festival', '节日：true = 任一节日，或节日名（一个或一组）', default=None, typ='bool | str | [str]')
        weathers = r.one_or_list('weather', 'str', '天气（由 Host 的 weather(day) 提供；没有就永不成立）', default=None)
        seasons = r.one_or_list('season', 'str', '季节（rule:schedule 的 seasons 登记的）', default=None)
        r.finish()
        if fest is True:
            fest = True
        elif isinstance(fest, str):
            fest = (fest,)
        elif isinstance(fest, list):
            fest = tuple(fest)
        elif fest is not None:
            self.ctx.err(r.id, '字段 when.festival 应是 true、节日名或节日名列表，得到 %r' % (fest,))
        return WhenSpec(slots, periods, days, doms, months, fest, weathers, seasons)

    # ---------------------------------------------------------------- 部门与规范
    def build_kitchen(self):
        d = self.ctx.role('org', 'kitchen')
        r = Reader(self.ctx, d)
        place = r.ref('place', 'place', '厨房')
        dining = r.ref('dining', 'place', '斋堂：到课（过堂）人数在此统计')
        prep = {}
        for x in r.tables('prep', '备斋时辰：[{ meal, prep }]'):
            prep[x.int('meal', '斋食时辰')] = x.int('prep', '备斋时辰')
            x.finish()
        min_staff = r.int('min_staff', '足量所需的在厨人手')
        gf, gh = r.num('gain_full', '足量斋食给的饥'), r.num('gain_half', '半餐给的饥')
        stock = r.numdict('stock_init', '开局库存：物 -> 量（水、柴）')
        r.finish()
        _ok(place, dining, min_staff, gf, gh, stock)
        return KitchenSpec(place['code'], dining['code'], prep, min_staff, gf, gh, stock)

    def build_court(self):
        ctx = self.ctx
        d = ctx.role('org', 'court')
        r = Reader(ctx, d)
        place = r.ref('place', 'place', '裁断与立案的场所（法庭所在）')
        judges = r.refs('judges', 'post', '有资格裁断的岗位（按次序，首座优先）')
        slot = r.int('judge_slot', '裁断的时辰')
        r.finish()
        _ok(place, judges, slot)
        return CourtSpec(place['code'], tuple(j['name'] for j in judges if j), slot)

    def build_gate(self):
        d = self.ctx.role('org', 'gate')
        r = Reader(self.ctx, d)
        place = r.ref('place', 'place', '门禁所在的场所')
        count = r.int('count', '每日从清众里轮值几人')
        r.finish()
        _ok(place, count)
        return GateSpec(place['code'], count)

    def build_patrol(self):
        ctx = self.ctx
        d = ctx.role('org', 'patrol')
        r = Reader(ctx, d)
        office = r.ref('office', 'post', '僧值：两人轮流，一人巡夜，一人日间巡寮')
        r.finish()
        n = ctx.role('norm', 'bed')
        nr = Reader(ctx, n)
        slots = nr.one_or_list('check_slots', 'int', '巡夜查寮的时辰')
        ex = nr.list('exempt_layers', 'str', '这些层的人不算“夜不在寮”')
        th = nr.ref('thought', 'thought', '被记空铺者的想法')
        nr.str('name', '规范名（说明用）')
        nr.finish()
        _ok(office, slots, ex, th)
        return PatrolSpec(office['name'], slots, ex, self.thought_key(th))

    def build_rollcall(self):
        ctx = self.ctx
        n = ctx.role('norm', 'absence')
        r = Reader(ctx, n)
        office = r.ref('office', 'post', '点名的岗位（维那）')
        place = r.ref('place', 'place', '点名的场所')
        slots = r.one_or_list('slots', 'int', '点名的时辰')
        ex = r.list('exempt_layers', 'str', '这些层的人不点名')
        window, limit = r.int('window', '近几日内'), r.int('limit', '缺课几次')
        kd = r.int('kneel_days', '就罚跪香几日')
        txt = r.str('kneel_txt', '统计里的名目')
        at = r.ref('absent_thought', 'thought', '缺课者的想法')
        kt = r.ref('kneel_thought', 'thought', '被罚跪香者的想法')
        r.str('name', '规范名（说明用）')
        r.finish()
        _ok(office, place, slots, ex, window, limit, kd, txt, at, kt)
        return RollCallSpec(office['name'], place['code'], slots, ex, window, limit, kd, txt,
                            self.thought_key(at), self.thought_key(kt))

    def build_slack(self):
        n = self.ctx.role('norm', 'slack')
        r = Reader(self.ctx, n)
        window, limit, kd = r.int('window', '近几日内'), r.int('limit', '被撞见几次'), r.int('kneel_days', '就罚跪香几日')
        th = r.ref('thought', 'thought', '被撞见者的想法')
        r.str('name', '规范名（说明用）')
        r.finish()
        _ok(window, limit, kd, th)
        return SlackSpec(window, limit, kd, self.thought_key(th))

    def build_ladder(self, d):
        r = Reader(self.ctx, d)
        steps = []
        for s in r.tables('steps', '阶梯：[{ txt, kneel_days, conf_days, need_hit, thought, gone }]（第 k 次受处分取第 k 级，超出取最后一级）'):
            txt = s.str('txt', '处分名')
            kd = s.int('kneel_days', '罚跪香几日', default=0)
            cd = s.int('conf_days', '禁闭几日', default=0)
            hit = s.numdict('need_hit', '需求增减', keys=NEED_KEYS, default={})
            th = s.ref('thought', 'thought', '加给受处分者的想法', default=None)
            gone = s.bool('gone', '离开本处（出寺、出帮……）', default=False)
            s.finish()
            _ok(txt, kd, cd, hit, gone)
            steps.append(LadderStep(txt, kd, cd, tuple(hit.items()), self.thought_key(th), gone))
        r.finish()
        return tuple(steps)

    def build_theft(self):
        """偷食这条规范：举报概率、案卷、处分阶梯、公告、清点。返回 (ReportSpec, CaseSpec, ladder, AnnounceSpec, InventorySpec)。"""
        ctx = self.ctx
        n = ctx.role('norm', 'theft')
        r = Reader(ctx, n)
        r.ref('event', 'event', '触犯时发的事件（目击者得见闻，强度见 event 的 salience）')
        rp = r.table('report', '见证人举报的概率 = base + r_w×刚正/100 − op_w×对当事人的好感，夹在 [lo, hi]')
        report = ReportSpec(*_ok(rp.num('base', '底数'), rp.num('r_w', '刚正的权重'), rp.num('op_w', '好感的权重'),
                                 rp.num('lo', '下限'), rp.num('hi', '上限')))
        rp.finish()
        cs = r.table('case', '案卷：四个状态名、stale_days、confess_base / confess_r、via_report / via_confess')
        case_vals = dict(open=cs.str('open', '状态：在查'), done=cs.str('done', '状态：已处分'), cold=cs.str('cold', '状态：悬案'),
                         closed=cs.str('closed', '状态：结案'), stale_days=cs.int('stale_days', '无人指认的案子几日后成悬案'),
                         confess_base=cs.num('confess_base', '被传讯者认错的概率 = confess_base + confess_r×刚正/100'),
                         confess_r=cs.num('confess_r', '刚正的权重'),
                         via_report=cs.str('via_report', '案卷里定罪依据：凭举报'), via_confess=cs.str('via_confess', '案卷里定罪依据：凭本人认错'))
        cs.finish()
        am = r.ref('accuse_mod', 'modifier', '受罚者对指认人记的好恶修正项')
        st = r.ref('sanction_thought', 'thought', '每起处分都给受处分者的想法')
        ld = r.ref('ladder', 'ladder', '处分阶梯')
        an = r.table('announce', '公告：slot 时辰在 place 表堂，在场者全部得知；守戒高于 s_line 的旁观者对受罚者记 mod')
        an_place = an.ref('place', 'place', '表堂的场所')
        announce_vals = (an.int('slot', '公告的时辰'), an_place, an.num('s_line', '守戒线'), an.ref('mod', 'modifier', '旁观者记的修正项'))
        an.finish()
        iv = r.table('inventory', '典座清点：slot 时辰清点，发现失窃的概率 p_find（发现即立案）')
        inventory = InventorySpec(*_ok(iv.int('slot', '清点的时辰'), iv.num('p_find', '发现的概率')))
        iv.finish()
        r.str('name', '规范名（说明用）')
        r.finish()
        _ok(am, st, ld, announce_vals[1], announce_vals[3], *case_vals.values())
        cases = CaseSpec(accuse_mod=self.mod_key(am), sanction_thought=self.thought_key(st), **case_vals)
        announce = AnnounceSpec(announce_vals[0], announce_vals[1]['code'], announce_vals[2], self.mod_key(announce_vals[3]))
        return report, cases, self.build_ladder(ld), announce, inventory

    # ---------------------------------------------------------------- 站点级规则
    def rule(self, role):
        return self.ctx.role('rule', role)

    def build_layers(self):
        r = Reader(self.ctx, self.rule('layers'))
        out = {}
        for x in r.tables('ranks', '层标签与计划 6.1 的层号：[{ name, rank }]（越轨与怠工不是一层包，记 0）'):
            name, rank = x.str('name', '层标签'), x.int('rank', '层号')
            x.finish()
            out[name] = rank
        r.finish()
        return out

    def build_schedule(self):
        r = Reader(self.ctx, self.rule('schedule'))
        night = r.list('night', 'int', '夜间时辰（子 0 … 亥 11）')
        rotate = r.list('rotate', 'int', '[日系数, 时辰系数]：各人决定的起点按 (日×a + 时辰×b) % 人数 轮转')
        meal = r.list('meal_slots', 'int', '斋食时辰')
        seasons = {}
        for x in r.tables('seasons', '季节与月份：[{ name, months }]（行为包 when.season 用）'):
            seasons[x.str('name', '季节名')] = x.list('months', 'int', '这个季节包括哪几个月')
            x.finish()
        r.finish()
        _ok(night, rotate, meal)
        if len(rotate) != ROTATE_ARITY:
            self.ctx.err('rule:schedule', 'rotate 必须是 [日系数, 时辰系数] 两项')
        return night, rotate, meal, seasons

    def build_needs(self):
        r = Reader(self.ctx, self.rule('needs'))
        vals = dict(
            init=r.numdict('init', '开局值：{h,e,c,s,a: 数}', keys=NEED_KEYS), base=r.numdict('base', '每时辰的基础消耗', keys=NEED_KEYS),
            names=None, category_default=r.str('category_default', '没有登记类别的活动记入的统计类别'),
            hunger_sleep=r.num('hunger_sleep', '睡时的饥消耗（代替 base.h）'),
            hunger_t_mid=r.num('hunger_t_mid', '饥消耗随“馋”微调：1 + (T − hunger_t_mid) / hunger_t_div'),
            hunger_t_div=r.num('hunger_t_div', '同上的刻度'), social_g=None,
            morning_slot=r.int('morning_slot', '晨起时辰：不睡就补 morning_c 点洁'), morning_c=r.num('morning_c', '晨起补的洁'),
            duty_layers=r.list('duty_layers', 'str', '这些层的决定每时辰补 duty_a 点志（履职）'), duty_a=r.num('duty_a', '履职补的志'),
            urgency_floor=r.num('urgency_floor', '迫切度 u(x) = ((100 − x)/100)^urgency_pow + urgency_floor'),
            urgency_pow=r.num('urgency_pow', '迫切度的指数'), hungry_line=r.num('hungry_line', '统计线：饥低于此算饿（只用于报表）'),
            tired_line=r.num('tired_line', '统计线：困低于此算乏（只用于报表）'))
        vals['names'] = r.raw('names', '需求键 -> 中文名（报表）')
        sg = r.table('social_g', '群的消耗乘 (off + G/div)')
        vals['social_g'] = (sg.num('off', '偏移'), sg.num('div', '刻度'))
        sg.finish()
        r.finish()
        _ok(*vals.values())
        return NeedSpec(**vals)

    def build_illness(self):
        r = Reader(self.ctx, self.rule('illness'))
        out = IllSpec(*_ok(r.num('p', '每人每日生病的概率'), r.int('min_days', '病几日（最少）'), r.int('span', '再加 [0, span) 日')))
        r.finish()
        return out

    def build_board(self, jobs):
        r = Reader(self.ctx, self.rule('board'))
        out = JobsSpec(jobs, _ok(r.num('work_chat_p', '同一件差事里两两搭伴的工友闲谈的概率'))[0])
        r.finish()
        return out

    def build_opinion(self):
        r = Reader(self.ctx, self.rule('opinion'))
        vals = [r.num(k, doc) for k, doc in (
            ('same_dorm', '同寮的底数加成'), ('same_track', '同方向的底数加成'), ('same_post', '同岗的底数加成（厨房职事视为同岗）'),
            ('compat_div', '相容度 = 1 − (|ΔD|+|ΔS|+|ΔG|)/compat_div'), ('compat_mid', '相容度的中点'), ('compat_w', '(相容度 − compat_mid)×compat_w 进底数'),
            ('lo', '好恶下限'), ('hi', '好恶上限'), ('friend_line', '双方都不低于此记好友'), ('foe_line', '双方都不高于此记不睦'))]
        r.finish()
        return OpinionSpec(*_ok(*vals))

    def build_chat(self):
        r = Reader(self.ctx, self.rule('chat'))
        vals = [r.num('good_base', '谈得投机的概率 = good_base + (相容度 − good_mid)×good_w'), r.num('good_mid', '相容度中点'),
                r.num('good_w', '相容度权重'), r.num('pair_noise', '配对时挑人的噪声'), r.num('gain_when_brief', '工友短谈给“群”的补益'),
                r.str('lone_label', '闲谈落单、改散步的原因')]
        gm, bm = r.ref('good_mod', 'modifier', '谈得投机给的修正项'), r.ref('bad_mod', 'modifier', '谈得不投机给的修正项')
        gt = r.ref('good_thought', 'thought', '谈得投机给的想法')
        r.finish()
        _ok(*vals, gm, bm, gt)
        return ChatSpec(*vals, self.mod_key(gm), self.mod_key(bm), self.thought_key(gt))

    def build_rumor(self):
        r = Reader(self.ctx, self.rule('rumor'))
        vals = [r.num('penalty', '转述一次强度减多少'), r.num('decay', '每日衰减'), r.num('min_strength', '低于此不再外传'),
                r.num('p_add', '转述概率 = min(p_cap, 强度/100 + p_add) × (g_off + 转述者合群/g_div)'), r.num('p_cap', '转述概率上限'),
                r.num('g_off', '合群的偏移'), r.num('g_div', '合群的刻度'), r.int('keep', '每人最多留几条见闻')]
        r.finish()
        return RumorSpec(*_ok(*vals))

    def build_mood(self):
        r = Reader(self.ctx, self.rule('mood'))
        weights = r.numdict('weights', '五项需求进心情的权重', keys=NEED_KEYS)
        lines = []
        for x in r.tables('lines', '三道线（自高到低）：[{ value, effect }]；effect = slack / avoid_group / life_event'):
            lines.append(MoodLine(x.num('value', '心情低于它就触发 effect'), x.str('effect', '后果')))
            x.finish()
        enabled = r.int('enabled', '启用几道（自上而下）；本步只能是 1：后两道留给 C7')
        r.finish()
        _ok(weights, enabled)
        return MoodSpec(weights, tuple(lines), enabled)

    def build_free(self, inter):
        ctx = self.ctx
        r = Reader(ctx, self.rule('free'))
        top_k = r.int('top_k', '在得分最高的几项里按分数加权抽一项')
        stroll = r.ref('stroll', 'interaction', '都不成时去做的交互（散步）：场所取它的工位')
        label = r.str('stroll_label', '散步的原因')
        keys = r.int('choice_key_chars', '“自由时段的选择”统计取原因的前几个字作键（只入统计）')
        r.finish()
        _ok(top_k, stroll, label, keys)
        it = inter[stroll['act']]
        if it.station is None:
            ctx.err(stroll['id'], '散步的交互必须有 station（去哪里散步）')
            raise _Cascade()
        return FreeSpec(top_k, it.station, it.act, label, keys)

    def build_main(self):
        ctx = self.ctx
        d = ctx.role('org', 'main')
        r = Reader(ctx, d)
        name = r.str('name', '名称')
        dorms = r.refs('dorms', 'place', '寮房（有序：第 i 个人住第 i % 寮数 个）；寮房是私人场所，不记容量')
        roam = r.refs('roam', 'place', '巡寮的候选场所（僧值每次从中按随机序挑几处）')
        cap_default = r.int('default_stations', '没登记工位数的场所按此数算')
        cycle = r.str('office_track_cycle', '岗位者的修行方向按序号循环')
        pool = r.str('name_pool', '取法名用的字池（岗位前缀 + 池中第 i 个字）')
        cp = r.str('common_prefix', '清众的法名前缀')
        tracks = []
        for x in r.tables('common_tracks', '清众按序分方向：[{ track, count }]（不写 count = 其余全部）'):
            tracks.append((x.str('track', '修行方向'), x.int('count', '人数', default=None)))
            x.finish()
        groups = r.list('groups', 'str', '时间分配统计的两组名称（清众，岗位者）')
        r.finish()
        _ok(name, dorms, roam, cap_default, cycle, pool, cp, groups)
        return (name, tuple(x['code'] for x in dorms), tuple(x['code'] for x in roam), cap_default, cycle, pool, cp,
                tuple(tracks), groups)


def build_site(defs, scenario_id):
    scope = _scope_of(scenario_id)
    if scenario_id not in defs:
        raise SpecError(['场景 %s 不存在' % scenario_id])
    ctx = Ctx(defs, scope)
    b = Builder(ctx)
    g = ctx.guard
    places = g(b.build_places)
    capacity = g(b.build_capacity)
    thoughts = g(b.build_thoughts)
    mods = g(b.build_mods)
    salience = g(b.build_events)
    layers = g(b.build_layers)
    offices = g(b.build_offices)
    traits = g(b.build_traits)
    jobs = g(b.build_jobs)
    inter = g(b.build_interactions)
    stack = g(b.build_packages, layers)
    sched = g(b.build_schedule)
    main = g(b.build_main)
    kitchen, court, gate, patrol = g(b.build_kitchen), g(b.build_court), g(b.build_gate), g(b.build_patrol)
    rollcall, slack, theft = g(b.build_rollcall), g(b.build_slack), g(b.build_theft)
    needs, illness, opinion = g(b.build_needs), g(b.build_illness), g(b.build_opinion)
    chat, rumor, mood = g(b.build_chat), g(b.build_rumor), g(b.build_mood)
    board = g(b.build_board, jobs) if jobs is not None else None
    free = g(b.build_free, inter[0]) if inter else None
    # 同 scope 里没被任何地方用到的定义（多半是漏了引用）
    for kind in SCOPE_KINDS:
        for d in defs.by_kind(kind):
            if d['id'].split(':')[1] == scope and d['id'] not in ctx.used:
                ctx.err(d['id'], '没有被任何地方引用或使用（漏了引用？拼错了 role？）')
    if ctx.problems:
        raise SpecError(ctx.problems)
    night, rotate, meal, seasons = sched
    name, dorms, roam, cap_default, cycle, pool, cp, ctracks, groups = main
    interactions, ads, violations = inter
    report, cases, ladder, announce, inventory = theft
    spec = SiteSpec(
        name=name, scope=scope, places=places, capacity=capacity, cap_default=cap_default, dorms=dorms, roam=roam,
        night=night, rotate=rotate, meal_slots=meal, seasons=seasons, offices=offices, office_track_cycle=cycle,
        name_pool=pool, common_prefix=cp, common_tracks=ctracks, groups=groups, traits=traits, layer_rank=layers,
        stack=stack, interactions=interactions, violations=violations, kitchen=kitchen, patrol=patrol, gate=gate,
        court=court, rollcall=rollcall, inventory=inventory, slack=slack, illness=illness, needs=needs, ads=ads,
        free=free, jobs=board, opinion=opinion, mods=mods, thoughts=thoughts, mood=mood, chat=chat, rumor=rumor,
        salience=salience, report=report, cases=cases, ladder=ladder, announce=announce)
    problems = spec.validate()
    if problems:
        raise SpecError(problems)
    return spec


def _scope_of(scenario_id):
    parts = scenario_id.split(':')
    if len(parts) != SCENARIO_ID_PARTS or parts[0] != 'scenario':
        raise SpecError(['场景编号应形如 scenario:<scope>:<名>，得到 %r' % scenario_id])
    return parts[1]


# ================================================================= 场景（种子、人口、要角、脚本与实验）
def build_scenario(defs, scenario_id, ctx=None):
    """ctx 只给 field_docs 用（让场景的字段也登记进同一张字段表）；平常不传。"""
    scope = _scope_of(scenario_id)
    ctx = ctx or Ctx(defs, scope)
    if scenario_id not in defs:
        raise SpecError(['场景 %s 不存在' % scenario_id])
    d = defs.get(scenario_id)
    r = Reader(ctx, d, kindname='scenario')
    name = r.str('name', '场景名')
    seed = r.int('seed', '随机数种子')
    pop = r.int('population', '人口（岗位者按编制排在前，其余是清众）')
    ndays = r.int('days', '默认跑几日')
    cast = []
    for x in r.tables('cast', '要角：[{ index, traits }]：清众里第 index 位的性格改写（序号从 0 起）'):
        cast.append((x.int('index', '清众序号'), x.numdict('traits', '性格改写 {D,S,G,T,R: 值}', keys=TRAIT_KEYS)))
        x.finish()
    glutton = r.int('glutton', '报表里点名的“惯犯”（清众序号）')
    lazy = r.int('lazy', '报表里点名的“懒人”（清众序号）')
    obs = r.ref('observer_place', 'place', '“观察者在廊下”那一行的观察处')
    trace_day = r.int('trace_day', '报表里“某日四人轨迹”的日子')
    trace_post = r.ref('trace_post', 'post', '轨迹里第四人的岗位')
    suffix = r.str('track_suffix', '清众的称呼 = 修行方向 + 此字')
    long_days = r.int('long_days', '“长跑”那一行的日数')
    seeds = r.list('extra_seeds', 'int', '多种子那几行')
    r.finish()
    gd, nd = ctx.role('scenario', 'gossip'), ctx.role('scenario', 'n1')
    if gd is None or nd is None:
        raise SpecError(ctx.problems)
    gr = Reader(ctx, gd, kindname='scenario:gossip')
    gvals = (gr.int('day', '第几日'), gr.int('who', '偷食者（清众序号）'), gr.int('heard', '唯一的见证人（清众序号）'),
             gr.int('slot', '发生的时辰'), gr.str('why', '事件里记的原因'))
    gr.finish()
    nr = Reader(ctx, nd, kindname='scenario:n1')
    day, days = nr.int('day', '第几日起'), nr.int('days', '病几日')
    sick = []
    for x in nr.tables('sick', '同时病倒的岗位者：[{ post, first }]（first = 只取该岗位的前几位）'):
        p = x.ref('post', 'post', '病倒者的岗位')
        first = x.int('first', '只取前几位', default=None)
        x.finish()
        sick.append((p['name'] if p else None, first))
    sick_label = nr.str('sick_label', '报表标题里对病倒者的称呼')
    window = nr.list('window', 'int', '逐日偷食累计看第 window[0]–window[1] 日')
    arms = []
    for x in nr.tables('arms', '对照组：[{ name, acting }]（监院是否派人代理）'):
        arms.append((x.str('name', '组名'), x.bool('acting', '监院是否派人代理')))
        x.finish()
    nr.finish()
    if ctx.problems:
        raise SpecError(ctx.problems)
    gossip = GossipSpec(*gvals)
    n1 = N1Spec(day, days, tuple(sick), sick_label, window, tuple(arms))
    return ScenarioSpec(id=scenario_id, name=name, seed=seed, population=pop, days=ndays, cast=tuple(cast), glutton=glutton, lazy=lazy,
                        observer_place=obs['code'], trace_day=trace_day, trace_post=trace_post['name'], track_suffix=suffix,
                        long_days=long_days, extra_seeds=seeds, gossip=gossip, n1=n1)


# ================================================================= 字段表（文档由它生成）
def field_docs(defs, scenario_id):
    """跑一遍 build_site / build_scenario，返回登记到的字段表：[(类别, 字段路径, 类型, 必填, 默认值, 说明)]，按类别、路径排序。"""
    scope = _scope_of(scenario_id)
    ctx = Ctx(defs, scope)
    b = Builder(ctx)
    for fn in (b.build_places, b.build_capacity, b.build_thoughts, b.build_mods, b.build_events, b.build_layers, b.build_offices,
               b.build_traits, b.build_jobs, b.build_interactions, b.build_schedule, b.build_main, b.build_kitchen, b.build_court,
               b.build_gate, b.build_patrol, b.build_rollcall, b.build_slack, b.build_theft, b.build_needs, b.build_illness,
               b.build_opinion, b.build_chat, b.build_rumor, b.build_mood):
        ctx.guard(fn)
    ctx.guard(b.build_packages, None)
    jobs = ctx.guard(b.build_jobs)
    ctx.guard(b.build_board, jobs)
    inter = ctx.guard(b.build_interactions)
    ctx.guard(b.build_free, inter[0])
    ctx.guard(build_scenario, defs, scenario_id, ctx)
    rows = [(k, p, *v) for (k, p), v in ctx.docs.items()]
    return sorted(rows)


def docs_markdown(defs, scenario_id, only=None):
    """字段表的 markdown：每个类别一张表（字段路径、类型、必填或默认值、说明），处理器与准入门的参数另有各自的表。
    only 给定时只输出这些类别（按给定的次序；形如 'interaction'、'norm:theft'、'handler:tempted'）。
    docs/NPC_ENGINE.md 第 12 节的表由它生成（python3 -m tianl.npc.defsload），测试核对文档里没有漏字段。"""
    rows = field_docs(defs, scenario_id)
    by = {}
    for kind, path, typ, req, default, text in rows:
        by.setdefault(kind, []).append((path, typ, req, default, text))
    kinds = sorted(by, key=lambda k: (k.startswith(('handler:', 'gate:')), k)) if only is None else list(only)
    title = {'handler': '处理器 `%s` 的参数（package 的 params）', 'gate': '准入门 `%s` 的参数（interaction 的 admission）'}
    out = []
    for kind in kinds:
        head, _, name = kind.partition(':')
        out.append('**%s**' % (title[head] % name if head in title else '`%s`' % kind))
        out.append('')
        out.append('| 字段 | 类型 | 必填 / 默认 | 说明 |')
        out.append('| --- | --- | --- | --- |')
        for path, typ, req, default, text in by[kind]:
            dflt = '必填' if req else ('缺省 `%s`' % (default,) if default not in (None, (), {}, []) else '可缺省')
            out.append('| `%s` | %s | %s | %s |' % (path, typ.replace('|', '\\|'), dflt.replace('|', '\\|'), text.replace('|', '\\|')))
        out.append('')
    return '\n'.join(out)


if __name__ == '__main__':
    import sys
    from .scenarios import PROTO60_ID, load_defs
    sys.stdout.write(docs_markdown(load_defs(), PROTO60_ID if len(sys.argv) == 1 else sys.argv[1]) + '\n')
