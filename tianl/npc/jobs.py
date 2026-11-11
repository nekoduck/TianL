"""工作板（计划 7.1、7.2，借自 RimWorld 的工作优先级）。

每日发布一张工作板（JobsSpec.board，次序即认领次序）；清众每人在差事时辰按优先级从上往下扫，
认领第一件还有空额的——认领即预约，别人不能再领。差事是固定步骤：每名工人一条内核命令（host.cmd），
所以 NPC 干活和玩家操作经过同一套物理与规范校验，不留后门。本步内核命令是 stub（StandaloneHost 恒受理）。
"""
from .spec import A_WORK, L_ERRAND


class JobBoard:
    def __init__(self, eng):
        self.eng = eng
        self.sp = eng.spec.jobs
        self.rows = []                      # [优先级, 名, 场所, 余额, [工人 ix…], 产出]

    def publish(self):
        self.rows = [[j.prio, j.name, j.place, j.count, [], j.product] for j in self.sp.board]

    def claim(self, ix):
        """认领第一件还有空额的差事；返回决定四元组，没有则 None。"""
        for j in self.rows:
            if j[3] > 0:
                j[3] -= 1
                j[4].append(ix)
                return (j[2], A_WORK, L_ERRAND, j[1])
        return None

    def settle(self, day, slot):
        """差事结算（差事时辰、需求结算之前）：工友两两闲谈；产出入账；统计完成与发布。"""
        eng, sp = self.eng, self.sp
        for j in self.rows:
            w = j[4]
            done = 0
            for ix in w:
                if eng.host.cmd('job', eng.people[ix].pid, job=j[1], place=j[2], day=day, slot=slot).ok:
                    done += 1
            for q in range(0, len(w) - 1, 2):
                if eng.rng(eng.seed, 'wchat', day, w[q]) < sp.work_chat_p:
                    eng.rumor.chat(w[q], w[q + 1], day, slot, False)
            if j[5] is not None:
                eng.stock[j[5]] += done
            eng.stat['job_done'] += done
            eng.stat['job_post'] += len(w) + j[3]
