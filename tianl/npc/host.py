"""Host 接口：引擎与外界（内核或独立运行）的唯一边界。

引擎只通过 Host 做三件事：
  1. 写事件：ev(kind, actor, place, witnesses, day, slot, cause=None, **data) -> 含 id 的 Event；
  2. 要随机数：host.rng(seed, 用途, 日, 时辰, 人…)（计数器式；默认 tianl.core.rnd，复现原型用 rnd_b2），host.seed；
  3. 调内核命令：host.cmd(name, pid, **args) -> CmdResult（本步是 stub，之后由 KernelHost 接 cmd_*）。

在 Host 边界上，actor 与 witnesses 用外部 id（pid，str）；引擎内部另存 ix 版本。
"""
from dataclasses import dataclass, field
from typing import Callable

from ..core import rnd


class Event:
    """一条事件。id 由 Host 分配；payload 含 wit（架构 6.2）。"""
    __slots__ = ('id', 'kind', 'actor', 'place', 'witnesses', 'day', 'slot', 'cause', 'data')

    def __init__(self, id, kind, actor, place, witnesses, day, slot, cause, data):
        self.id, self.kind, self.actor, self.place = id, kind, actor, place
        self.witnesses, self.day, self.slot, self.cause, self.data = witnesses, day, slot, cause, data

    @property
    def wit(self):
        return self.witnesses

    def payload(self):
        d = dict(self.data)
        d['wit'] = list(self.witnesses)
        return d

    def __repr__(self):
        return 'Event(#%s %s actor=%s place=%s wit=%d day=%s slot=%s cause=%s)' % (
            self.id, self.kind, self.actor, self.place, len(self.witnesses), self.day, self.slot, self.cause)


@dataclass
class CmdResult:
    ok: bool = True
    why: str = ''
    data: dict = field(default_factory=dict)


class Host:
    """接口基类。子类必须给出 seed、rng，并实现 ev、cmd。"""
    seed: int
    rng: Callable[..., float]

    def ev(self, kind, actor, place, witnesses, day, slot, cause=None, **data) -> Event:
        raise NotImplementedError

    def cmd(self, name, pid, **args) -> CmdResult:
        raise NotImplementedError


class StandaloneHost(Host):
    """独立运行：事件存内存列表，id 从 0 起顺序编号；内核命令一律受理。

    record_cmds=True 时把命令记入 self.cmds（测试用）；默认只计数。
    """

    def __init__(self, seed, rng=rnd, record_cmds=False):
        self.seed, self.rng = seed, rng
        self.events = []
        self.record_cmds, self.cmds, self.cmd_count = record_cmds, [], 0

    def ev(self, kind, actor, place, witnesses, day, slot, cause=None, **data):
        e = Event(len(self.events), kind, actor, place, list(witnesses), day, slot, cause, data)
        self.events.append(e)
        return e

    def cmd(self, name, pid, **args):
        self.cmd_count += 1
        if self.record_cmds:
            self.cmds.append((name, pid, args))
        return CmdResult(True)
