"""数据模型：建人用的 PersonSpec、运行档案 Profile、轨迹打包 Symbols/Trail、案卷 Case。

人的内部下标 ix（int，稳定，新人只追加）与外部编号 pid（str）分开：内部结构与随机数键全用 ix，
pid 只在 Host 边界与查询 API 的入口出现。
"""
from array import array
from collections import Counter
from dataclasses import dataclass
from typing import Optional


@dataclass
class PersonSpec:
    """建一个人所需的全部输入。traits 为 None 时由引擎按规格里的分布与种子生成（五项性格）。"""
    pid: str
    name: str
    office: Optional[str]
    track: str
    dorm: str
    traits: Optional[dict] = None


NEVER = -1_000_000                  # “从未”的日期哨兵：ill/conf/kneel/duty_day/lazy_day 的初值（世界第 0 日也不会误判）


class Profile:
    """一个被单独模拟的人的运行档案（字段含义见 docs/NPC_ENGINE.md 2.2）。"""
    __slots__ = ('ix', 'pid', 'name', 'office', 'track', 'dorm', 'D', 'S', 'G', 'T', 'R', 'need', 'ill', 'conf',
                 'kneel', 'pending', 'offences', 'absent', 'slackd', 'news', 'thoughts', 'duty_day', 'gone',
                 'lazy_day', 'trail')

    def __init__(self, ix, pid, name, office, track, dorm, need):
        self.ix, self.pid, self.name, self.office, self.track, self.dorm = ix, pid, name, office, track, dorm
        self.need = dict(need)
        self.ill = self.conf = self.kneel = NEVER
        self.pending = []
        self.offences = 0
        self.absent = []
        self.slackd = []
        self.news = {}
        self.thoughts = []
        self.duty_day = NEVER
        self.gone = None
        self.lazy_day = NEVER
        self.trail = Trail()


class Symbols:
    """字符串驻留：把场所、活动、层、原因编成小整数，轨迹打包要用。"""
    __slots__ = ('ids', 'names')

    def __init__(self):
        self.ids, self.names = {}, []

    def intern(self, s):
        i = self.ids.get(s)
        if i is None:
            i = self.ids[s] = len(self.names)
            self.names.append(s)
            if i > 0xFFFF:
                raise OverflowError('符号表超过 65536 项')
        return i

    def name(self, i):
        return self.names[i]


class Trail:
    """一个人的时辰级轨迹：每个时辰一个 64 位整数 (场所, 活动, 层, 原因)，t0 是第一条的绝对时刻。"""
    __slots__ = ('t0', 'arr')

    def __init__(self):
        self.t0 = None
        self.arr = array('Q')

    def push(self, t, packed):
        if self.t0 is None:
            self.t0 = t
        self.arr.append(packed)

    def get(self, t):
        """绝对时刻 t 的打包值；没有则 None。"""
        if self.t0 is None:
            return None
        k = t - self.t0
        if 0 <= k < len(self.arr):
            return self.arr[k]
        return None

    def __len__(self):
        return len(self.arr)


def pack(place, act, layer, reason):
    return (place << 48) | (act << 32) | (layer << 16) | reason


def unpack(v):
    return (v >> 48) & 0xFFFF, (v >> 32) & 0xFFFF, (v >> 16) & 0xFFFF, v & 0xFFFF


class Case:
    """一件案子。state 取值见 SiteSpec.cases；via 记定罪的依据（举报 / 认错），acc 是指认人的 ix。"""
    __slots__ = ('eid', 'opened', 'acc', 'sus', 'state', 'rep', 'asked', 'txt', 'day', 'via')

    def __init__(self, eid, opened, sus, state):
        self.eid, self.opened, self.acc, self.sus, self.state = eid, opened, set(), set(sus), state
        self.rep = None                 # 首次被举报的日子；None = 尚无人举报
        self.asked = False
        self.txt = None
        self.day = None
        self.via = None


class EvRec:
    """引擎自己留的事件记录（ix 版本）：引擎内部用 ix，Host 边界用 pid，所以各存一份。"""
    __slots__ = ('id', 'kind', 'actor', 'place', 'wit', 'day', 'slot', 'cause', 'data')

    def __init__(self, id, kind, actor, place, wit, day, slot, cause, data):
        self.id, self.kind, self.actor, self.place, self.wit = id, kind, actor, place, wit
        self.day, self.slot, self.cause, self.data = day, slot, cause, data


class SlotCtx:
    """一个时辰的工作区：工位占用、巡寮所到之处、各人的决定。"""
    __slots__ = ('day', 'slot', 'occ', 'seen', 'patroller', 'dec')

    def __init__(self, day, slot):
        self.day, self.slot = day, slot
        self.occ = Counter()
        self.seen = set()
        self.patroller = None
        self.dec = {}


@dataclass
class Script:
    """场景脚本（scenario 的一部分）：
    gossip = (日, 当事人, 唯一的见证人)：该日 gossip_slot 时辰发一条只有一人撞见、且不举报的偷食，用来追踪传闻；
    ill    = (日, [病倒者], 病几日)：该日起集体病倒。
    人用 ix 或 pid 都行。"""
    gossip: Optional[tuple] = None
    gossip_slot: int = 1
    gossip_why: str = '脚本：只有一人撞见且不举报'
    ill: Optional[tuple] = None

    @classmethod
    def coerce(cls, x):
        if x is None:
            return cls()
        if isinstance(x, cls):
            return x
        return cls(gossip=x.get('gossip'), ill=x.get('ill'), **{k: v for k, v in x.items()
                                                                 if k in ('gossip_slot', 'gossip_why')})
