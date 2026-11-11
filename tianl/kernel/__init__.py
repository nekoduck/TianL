"""v0.2 少林寺钱粮闭环内核（reference/shaolin_spike.py 的移植）。常量全部来自 defs/，见 docs/KERNEL_DEFS.md。"""
from .spec import Spec, Good, load_spec, load_kernel_defs, DEFS_ROOT
from .world import World, ECON_TABLES
from .vocab import SHI, GUAN
from .report import year_report, summary, baseline, window
