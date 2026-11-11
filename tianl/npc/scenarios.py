"""场景：由 defs 构造的原型（60 僧 × 30 日，scenario:proto60:main）与实验 N1。

世界描述（SiteSpec）与场景（ScenarioSpec：种子、人口、三个“要角”、脚本与实验、报表用词）都来自 defs/*/proto60*.toml——
本文件里没有原型场景的数，只有装配：加载 defs、按岗位编制排名册、把引擎装成可跑的世界。
proto60_spec() / proto60_scenario() 是 defs 加载一次后缓存的结果（同一进程里是同一个对象，规格不可变）。
ProtoRun 把以上装配成可跑的世界（StandaloneHost + NpcEngine），默认用 rnd_b2 复现原型哈希 e8f8209eeb8ca94a。
换一座寺（比如 300 僧）：换一套 defs（scope 不同），或同一份 defs 改人口（ProtoRun(n=300)）；见 docs/NPC_ENGINE.md 第 12 节。
脚本（gossip / ill）是场景的一部分，见 model.Script。
"""
from pathlib import Path

from ..core import rnd_b2
from ..defs import Defs
from .engine import NpcEngine
from .host import StandaloneHost
from .model import PersonSpec, Script
from .spec import ScenarioSpec, SiteSpec

DEFS_ROOT = Path(__file__).resolve().parent.parent.parent / 'defs'
PROTO60_ID = 'scenario:proto60:main'
FIRST_DAY = 1                       # 模拟日从第 1 日起（第 0 日留给预热；原型口径）
_cache = {}


def load_defs(root=None):
    """加载 defs（默认仓库的 defs/，整棵树；引用完整性不通过抛 DefsError）。同一个 root 只加载一次。"""
    key = str(root or DEFS_ROOT)
    if key not in _cache:
        _cache[key] = Defs.load(key)
    return _cache[key]


def proto60_spec(defs=None, scenario_id=PROTO60_ID):
    """原型场景的世界描述：SiteSpec.from_defs(defs, 'scenario:proto60:main')；默认 defs 时缓存。"""
    if defs is not None:
        return SiteSpec.from_defs(defs, scenario_id)
    key = ('spec', scenario_id)
    if key not in _cache:
        _cache[key] = SiteSpec.from_defs(load_defs(), scenario_id)
    return _cache[key]


def proto60_scenario(defs=None, scenario_id=PROTO60_ID):
    """原型场景的场景描述（种子、人口、要角、脚本与实验、报表用词）。"""
    if defs is not None:
        return ScenarioSpec.from_defs(defs, scenario_id)
    key = ('scenario', scenario_id)
    if key not in _cache:
        _cache[key] = ScenarioSpec.from_defs(load_defs(), scenario_id)
    return _cache[key]


def __getattr__(name):
    """PROTO_SEED 之类的“场景常量”按需从 defs 读（模块属性，惰性：import tianl.npc 不加载 defs）。"""
    if name == 'PROTO_SEED':
        return proto60_scenario().seed
    raise AttributeError(name)


def pid_of(ix):
    """名册的外部编号：P0001 起。"""
    return 'P%04d' % (ix + 1)


def _common_track(spec, j):
    """清众里第 j 位（从 0 起）的修行方向：按 common_tracks 依次分段，None 表示其余全部。"""
    for track, cnt in spec.common_tracks:
        if cnt is None or j < cnt:
            return track
        j -= cnt
    return spec.common_tracks[-1][0]


def proto60_roster(spec, n=None, scenario=None):
    """名册：先按岗位表依次排岗位人员，其余为清众（姓名、修行方向、寮房都由序号决定）。n 缺省取场景的人口。"""
    n = (scenario or proto60_scenario()).population if n is None else n
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
    """一个可跑的世界。参数同原型 World：seed、n（人数）、days、acting（监院派人代理）、observer、script；
    缺省的种子、人口与日数取场景（scenario）的；spec / scenario 缺省是原型场景（由 defs 构造）。"""

    def __init__(self, seed=None, n=None, days=None, acting=True, observer=None, script=None, rng=rnd_b2,
                 spec=None, host=None, scenario=None):
        self.spec = spec or proto60_spec()
        self.scenario = scenario or proto60_scenario()
        seed = self.scenario.seed if seed is None else seed
        self.days = self.scenario.days if days is None else days
        self.host = host or StandaloneHost(seed, rng)
        self.engine = NpcEngine(self.spec, self.host, acting=acting, script=script)
        for ps in proto60_roster(self.spec, n, self.scenario):
            self.engine.add_person(ps)
        for k, tr in self.scenario.cast:
            self.engine.set_traits(self.engine.common[k].ix, **tr)
        self.engine.set_observer(observer)
        self.hash = None

    @property
    def common(self):
        return self.engine.common

    @property
    def glutton(self):
        return self.engine.common[self.scenario.glutton]

    @property
    def lazy(self):
        return self.engine.common[self.scenario.lazy]

    def run(self):
        for day in range(FIRST_DAY, self.days + 1):
            self.engine.run_day(day)
        self.hash = self.engine.state_hash()
        return self


def gossip_script(run_or_engine_common, scenario=None):
    """传闻实验脚本（场景的 gossip）：第 day 日，清众里第 who 位偷食，只有第 heard 位撞见且不举报。"""
    c, g = run_or_engine_common, (scenario or proto60_scenario()).gossip
    return Script(gossip=(g.day, c[g.who].ix, c[g.heard].ix), gossip_slot=g.slot, gossip_why=g.why)


def n1_script(engine, scenario=None):
    """实验 N1（场景的 n1）：第 day 日起 sick 里的岗位者同时病倒 days 日。"""
    n1 = (scenario or proto60_scenario()).n1
    who = []
    for post, first in n1.sick:
        who += engine.by[post] if first is None else engine.by[post][:first]
    return Script(ill=(n1.day, who, n1.days))
