"""NPC 测试共用的小工具（本文件没有测试）：在不可变的 SiteSpec 上“换一个包”“换一个交互”“换一个参数”，以及从行为包里读出
原型里原来是独立字段的那几张表（岗位的理事时段、集体日程、功课……）。规格由 defs 构造，包是数据，所以测试也按包的名字取。
"""
import dataclasses

from tianl.npc.spec import L_GROUP, L_IDENT, L_POST


def pkg_index(sp, name):
    """栈里名为 name 的包（编号最后一段）的下标。"""
    return next(i for i, pk in enumerate(sp.stack) if pk.id.rpartition(':')[2] == name)


def package(sp, name):
    return sp.stack[pkg_index(sp, name)]


def with_package(sp, name, **changes):
    """sp 的副本，栈里名为 name 的包按 changes 改（dataclasses.replace）。"""
    i = pkg_index(sp, name)
    new = dataclasses.replace(sp.stack[i], **changes)
    return dataclasses.replace(sp, stack=sp.stack[:i] + (new,) + sp.stack[i + 1:])


def with_params(sp, name, **params):
    return with_package(sp, name, params={**package(sp, name).params, **params})


def with_when(sp, name, **changes):
    return with_package(sp, name, when=dataclasses.replace(package(sp, name).when, **changes))


def with_do(sp, name, **changes):
    return with_package(sp, name, do=dataclasses.replace(package(sp, name).do, **changes))


def with_interaction(sp, act, **changes):
    """sp 的副本，活动 act 的交互按 changes 改。"""
    its = dict(sp.interactions)
    its[act] = dataclasses.replace(its[act], **changes)
    return dataclasses.replace(sp, interactions=its)


def with_effects(sp, act, **effects):
    return with_interaction(sp, act, effects={**sp.interactions[act].effects, **effects})


def handler_packages(sp, handler):
    return [pk for pk in sp.stack if pk.handler == handler]


def office_posts(sp):
    """岗位名 -> (理事场所, 理事时辰)：第 8 层（岗位）的声明式包。"""
    return {pk.who.offices[0]: (pk.do.place, pk.when.slots) for pk in sp.stack if pk.layer == L_POST and pk.do}


def group_acts(sp):
    """时辰 -> (场所, 活动, 原因)：第 7 层（集体）里只看时辰的包（带日子条件的，如布萨，不在其中）。"""
    return {pk.when.slots[0]: (pk.do.place, pk.do.act, pk.do.label) for pk in sp.stack
            if pk.layer == L_GROUP and pk.do and pk.when.days is None and pk.when.doms is None}


def class_acts(sp):
    """修行方向 -> (场所, 活动, 原因)：清众的功课（第 9 层“身份”里有 who.tracks 的声明式包）。"""
    return {pk.who.tracks[0]: (pk.do.place, pk.do.act, pk.do.label) for pk in sp.stack
            if pk.layer == L_IDENT and pk.do and pk.who.tracks}
