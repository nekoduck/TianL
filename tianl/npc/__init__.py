"""NPC 引擎（C 段）：九层机制，不靠 LLM。设计见 docs/PLAN.md 第 5–11 节，实现说明见 docs/NPC_ENGINE.md。"""
from .engine import NpcEngine
from .host import CmdResult, Event, Host, StandaloneHost
from .model import PersonSpec, Profile, Script
from .scenarios import ProtoRun, proto60_roster, proto60_spec
from .spec import SiteSpec

__all__ = ['NpcEngine', 'Host', 'StandaloneHost', 'Event', 'CmdResult', 'PersonSpec', 'Profile', 'Script',
           'SiteSpec', 'ProtoRun', 'proto60_spec', 'proto60_roster']
