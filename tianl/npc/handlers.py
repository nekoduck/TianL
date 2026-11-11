"""登记表：按名字找处理器（ARCHITECTURE 第 6 节：包里写 handler = "<名>"，由这里解析）。

本步只有一类：准入门（gate）。设施广告（spec.AdSpec.gate）用名字引用它，返回 True 才开放。
之后 defs 驱动的步骤把越轨起念、值守轮换等也登记在这里。
"""

GATES = {}


def gate(name):
    def deco(fn):
        GATES[name] = fn
        return fn
    return deco


@gate('lib_open')
def lib_open(eng, p, day, slot):
    """经阁开放：在开阁时辰，且藏主没病。"""
    lb = eng.spec.library
    z = eng.by.get(lb.office)
    if not z:
        return False
    return slot in lb.slots and eng.people[z[0]].ill < day


@gate('bath_day')
def bath_day(eng, p, day, slot):
    """开浴日：每 bath_every 日一次，在 bath_slots 时辰。"""
    fr = eng.spec.free
    return day % fr.bath_every == fr.bath_phase and slot in fr.bath_slots
