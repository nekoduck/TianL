"""自由时段怎么选（计划 6.4，做法取自《模拟人生》）：

1. 列出此刻能用的交互：设施开放、准入通过（有空工位在第 4 步才查）；
2. 给每个交互算分（facilities.score）；
3. 在最高的 top_k 项里按分数加权抽一项（计数器式随机数）——不取最高而在前几名里抽，
   是《模拟人生》避免所有人做同一件事的办法；
4. 占住工位；满了就顺次选下一项，都满了就去廊下散步。
“占位即预约”：同一时辰别人不能再占满额的场所。
"""


class FreeChoice:
    def __init__(self, eng):
        self.eng = eng
        self.sp = eng.spec.free

    def choose(self, p, day, slot, pkg, ctx):
        eng = self.eng
        fac, sp = eng.fac, self.sp
        c = [(ad.act, fac.place_of(ad, p), fac.score(ad, p), ad.label) for ad in fac.open_ads(p, day, slot)]
        c.sort(key=lambda x: -x[2])
        top = [x for x in c[:sp.top_k] if x[2] > 0]
        r = eng.rng(eng.seed, 'sb', day, slot, p.ix) * sum(x[2] for x in top)
        acc = 0.0
        first = top[0]
        for x in top:
            acc += x[2]
            if r <= acc:
                first = x
                break
        for act, place, sc, label in [first] + [x for x in c if x is not first]:
            if fac.has_room(ctx.occ, place):
                fac.take(ctx.occ, place)
                return (place, act, pkg, label)
            eng.stat['full'] += 1
        return (sp.stroll_place, sp.stroll_act, pkg, sp.stroll_label)
