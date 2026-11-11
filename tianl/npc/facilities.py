"""设施运行时（计划 4.3、6.4）：工位、预约、广告、准入。

* 工位：每个有限容量的场所一个计数（SiteSpec.capacity）；占位即预约，满了就不能再占。床位归人，不记容量。
* 广告：设施说“我能满足什么”（AdSpec）；人按需求打分，打分公式见 score()。
* 准入：广告可带一道门（handlers.GATES，参数在交互的 admission 里），门不开就不进候选。
“预约越界”是硬指标：任何时辰任何有限场所的占用都不得超过容量（check_overflow 记下违例）。
"""
from .handlers import GATES
from .spec import OWN_BED, SCALE


class Facilities:
    def __init__(self, eng):
        self.eng = eng
        sp = eng.spec
        self.cap, self.cap_default = sp.capacity, sp.cap_default
        self.private = sp.private_places
        self.ads = sp.ads
        self.violations = []                # (日, 时辰, 场所, 占用数)

    def has_room(self, occ, place):
        return place in self.private or occ[place] < self.cap.get(place, self.cap_default)

    def take(self, occ, place):
        occ[place] += 1

    def check_overflow(self, occ, day, slot):
        for pl, cap in self.cap.items():
            if occ[pl] > cap:
                self.violations.append((day, slot, pl, occ[pl]))

    def open_ads(self, p, day, slot):
        """此刻对 p 开放的广告（保持规格里的次序；平分时次序决定先后）。"""
        eng = self.eng
        return [ad for ad in self.ads if ad.gate is None or GATES[ad.gate](eng, p, day, slot, ad.gate_params)]

    def score(self, ad, p):
        """p 对广告 ad 的打分：各项需求迫切度乘增量之和 → 乘性格系数 → 加性格偏好（计划 6.4 第 2 步）。"""
        U = self.eng.needs.urgency
        n = p.need
        s = 0.0
        for t in ad.terms:
            w = t.w
            for tr, ww in t.by_track:
                if tr == p.track:
                    w = ww
                    break
            s += U(n[t.need]) * w
        if ad.scale is not None:
            key, off, div = ad.scale
            s *= off + getattr(p, key) / div
        if ad.pref is not None:
            kind, key, coef, track = ad.pref
            v = getattr(p, key)
            if kind == 'trait':
                s += coef * v / SCALE
            elif kind == 'track':
                s += coef * v / SCALE if p.track == track else 0.0
            elif kind == 'idle':
                s += coef * (1 - v / SCALE)
            else:
                raise ValueError('未知的偏好种类：%r' % kind)
        return s

    def place_of(self, ad, p):
        return p.dorm if ad.place == OWN_BED else ad.place
