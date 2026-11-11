"""操纵者接口：Controller 协议与 Program / Player / LLMStub 三个实现（计划 11.1，里程碑 C9）。

本步是空壳（只有协议与钩子），之后由 C9 接手。约定（见 PLAN 11.1）：
  * 每份档案有一个操纵者；操纵者只做一件事：在内核给出的合法候选里选一个；
  * 程序 = 行为包栈（stack.py）；玩家 = 控制台输入；LLM = 读情境、回一个候选编号和一句话；
  * LLM 只能选不能造，输出仍是一条命令并过物理与规范校验；第 1、2、5、7 层不交给操纵者；
  * 超时或输出不合法，立刻回落到程序的选择，世界不等它；运行时不调用真实 LLM。

钩子（engine.run_slot 第 1 步，每人每个时辰的“决定”入口；engine.controllers 为空时根本不经过这里，所以默认零开销、不改任何哈希）：

    decide(engine, p, day, slot, ctx) -> 决定四元组

默认实现：该档案没有操纵者就直接走栈；有就先算候选（candidates），交给 Controller.choose(choice_ctx, candidates)，
结果不在候选里（或抛异常）就回落到候选的第一个（= 程序的选择）。

    class Controller:                       # 协议
        def choose(self, ctx: ChoiceCtx, candidates: list) -> 决定四元组

    ChoiceCtx(engine, person, day, slot, slot_ctx)    情境：想读档案、需求、见闻、眼前的人，都从 engine 取

C9 只改本文件：写 Player / LLMStub，扩充 candidates（列出该层合法的替代选择，如自由时段的前几名广告），并决定哪些层锁死
（forced / penalty / duty / group：只给一个候选）。不要改 engine.py。默认的 Program 就是“取候选的第一个”。

给 C9 的一条硬约束（接手前先读）：engine.stack.decide 有副作用（占工位、记统计、改贪睡与代班的状态、认领差事），不是只读的“看一看”。
  * 同一个人同一个时辰（同一个 SlotCtx）decide 只算一次，再调用原样返回第一次的结果、不再占位（stack.py；有测试），
    所以 candidates / 预览可以放心再取“程序的选择”，但**不得为了凑候选而换着参数多次调用它**——那样只会拿到同一个结果；
  * 替代候选要自己只读地列出（例如读 engine.fac.open_ads / score 给自由时段前几名，不占位）；
  * 若操纵者选了程序的选择之外的候选，而程序的选择已经占了工位 / 认领了差事，要先放掉那份占用（在这里加放位的函数；不要改 engine.py），
    再占替代项的工位；放不了就把这一层锁死、只给一个候选。
"""
from dataclasses import dataclass


@dataclass
class ChoiceCtx:
    """给操纵者的情境。slot_ctx 是 model.SlotCtx（本时辰的工位占用与各人已有的决定）。"""
    engine: object
    person: object
    day: int
    slot: int
    slot_ctx: object


class Controller:
    """操纵者协议：在候选里选一个，返回其中的一项。"""

    def choose(self, ctx, candidates):
        raise NotImplementedError


class Program(Controller):
    """程序：行为包栈的选择（候选的第一个）。没有操纵者的档案就是它。"""

    def choose(self, ctx, candidates):
        return candidates[0]


PROGRAM = Program()


def candidates(engine, p, day, slot, ctx):
    """此刻对 p 合法的决定列表，第一个是程序（栈）的选择。现在只有它；C9 在此加上该层合法的替代选择。"""
    return [engine.stack.decide(p, day, slot, ctx)]


def decide(engine, p, day, slot, ctx):
    """决定入口（见模块说明）。操纵者出错、超时或给了候选之外的东西，都回落到程序的选择。"""
    ctl = engine.controllers.get(p.ix)
    if ctl is None:
        return engine.stack.decide(p, day, slot, ctx)
    cands = candidates(engine, p, day, slot, ctx)
    try:
        pick = ctl.choose(ChoiceCtx(engine, p, day, slot, ctx), list(cands))
    except Exception:       # noqa: BLE001 —— 操纵者的任何失败都不许拖垮世界（计划 11.1 第三条）
        return cands[0]
    return pick if pick in cands else cands[0]
