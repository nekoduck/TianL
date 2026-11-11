"""工作板（计划 7.1、7.2，借自 RimWorld 的工作优先级）。

每日发布一张工作板（JobsSpec.board，按 prio 从小到大、同级按规格次序）；清众每人在差事时辰按优先级从上往下扫，
认领第一件还有空额的——认领即预约，别人不能再领。差事是固定步骤：每名工人一条内核命令（host.cmd），
所以 NPC 干活和玩家操作经过同一套物理与规范校验，不留后门。本步内核命令是 stub（StandaloneHost 恒受理）。
"""
from .model import PAIR
from .spec import A_WORK


class JobRow:
    """工作板上的一行：当日的一件差事（优先级、名、场所、还剩几个空额、已认领的工人、产出什么物）。"""
    __slots__ = ('prio', 'name', 'place', 'left', 'workers', 'outputs')

    def __init__(self, job):
        self.prio, self.name, self.place, self.left, self.outputs = job.prio, job.name, job.place, job.count, tuple(job.outputs.items())
        self.workers = []


class JobBoard:
    def __init__(self, eng):
        self.eng = eng
        self.sp = eng.spec.jobs
        self.rows = []                      # [JobRow]，次序即认领次序（prio 升序，同级按规格次序）

    def publish(self):
        """发布当日的板：按优先级 prio 从小到大排（数字小的先被认领）；同级保持规格里的次序（sorted 是稳定的）。"""
        self.rows = [JobRow(j) for j in sorted(self.sp.board, key=lambda j: j.prio)]

    def claim(self, ix, layer):
        """认领第一件还有空额的差事；返回决定四元组（层是差事包的层），没有则 None。"""
        for j in self.rows:
            if j.left > 0:
                j.left -= 1
                j.workers.append(ix)
                return (j.place, A_WORK, layer, j.name)
        return None

    def settle(self, day, slot):
        """差事结算（差事时辰、需求结算之前）：工友两两闲谈；产出入账；统计完成与发布。"""
        eng, sp = self.eng, self.sp
        for j in self.rows:
            w = j.workers
            done = 0
            for ix in w:
                if eng.host.cmd('job', eng.people[ix].pid, job=j.name, place=j.place, day=day, slot=slot).ok:
                    done += 1
            for q in range(0, len(w) - 1, PAIR):
                if eng.rng(eng.seed, 'wchat', day, w[q]) < sp.work_chat_p:
                    eng.rumor.chat(w[q], w[q + 1], day, slot, False)
            for item, q in j.outputs:
                eng.stock[item] += done * q
            eng.stat['job_done'] += done
            eng.stat['job_post'] += len(w) + j.left
