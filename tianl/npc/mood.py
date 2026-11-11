"""想法与心情（计划 9.3，做法取自 RimWorld）。

想法是带期限的加减分：[值, 止日, 标签]，同标签有叠加上限。心情 = 五项需求的加权和 + 当前所有想法之和。
三道线里本步只实现第一道（低于它怠工概率加成）；后两道（回避集体、人生事件）留给 C7。
"""
from ..core import clamp


class Moods:
    def __init__(self, eng):
        self.eng = eng
        self.w = eng.spec.mood.weights
        self.low = eng.spec.mood.low_line

    def mood(self, p):
        n, w = p.need, self.w
        return clamp(w['h'] * n['h'] + w['e'] * n['e'] + w['c'] * n['c'] + w['s'] * n['s'] + w['a'] * n['a']
                     + sum(t[0] for t in p.thoughts))

    def think(self, p, key, day):
        """给 p 加一个想法（键见 SiteSpec.thoughts）；同标签已满额就不加。"""
        t = self.eng.spec.thoughts[key]
        if sum(1 for x in p.thoughts if x[2] == t.label) < t.cap:
            p.thoughts.append([t.value, day + t.days, t.label])

    def expire(self, p, day):
        p.thoughts = [t for t in p.thoughts if t[1] > day]

    def is_low(self, p):
        return self.mood(p) < self.low
