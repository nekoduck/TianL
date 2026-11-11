"""好恶（计划 9.2，结构取自 CK3）：好感 = 底数 + 所有未过期修正项之和，范围 -100 到 100。

底数由两人档案现算（同寮、同方向、同岗、性格相近），修正项是带期限的数据：[值, 止日, 种类]。
双方都不低于友线记好友，都不高于敌线记不睦。好恶影响三件事：闲谈挑谁、看见了举不举报、听来的话信不信。
"""
from ..core import clamp


class Opinions:
    def __init__(self, eng):
        self.eng = eng
        self.sp = eng.spec.opinion
        self.mods = {}                      # (a, b) -> [[值, 止日, 种类], …]；a 对 b 的好恶

    def compat(self, a, b):
        """两人性格的相容度，约 0.5–1。"""
        A, B = self.eng.people[a], self.eng.people[b]
        return 1 - (abs(A.D - B.D) + abs(A.S - B.S) + abs(A.G - B.G)) / self.sp.compat_div

    def base(self, a, b):
        """底数：档案决定、常驻。"""
        sp = self.sp
        A, B = self.eng.people[a], self.eng.people[b]
        c = self.compat(a, b)
        kit = self.eng.spec.kitchen_offices
        grp = A.office is not None and (A.office == B.office or (A.office in kit and B.office in kit))
        return (sp.same_dorm * (A.dorm == B.dorm) + sp.same_track * (A.track == B.track) + sp.same_post * grp
                + (c - sp.compat_mid) * sp.compat_w)

    def opinion(self, a, b):
        v = self.base(a, b)
        for m in self.mods.get((a, b), ()):
            v += m[0]
        return clamp(v, self.sp.lo, self.sp.hi)

    def add_mod(self, a, b, key, day):
        """a 对 b 加一条修正项（种类见 SiteSpec.mods）；同类已满额则只续期最老的一条。"""
        m = self.eng.spec.mods[key]
        L = self.mods.setdefault((a, b), [])
        same = [x for x in L if x[2] == m.kind]
        if len(same) >= m.cap:
            same[0][1] = day + m.days
        else:
            L.append([m.value, day + m.days, m.kind])

    def expire(self, day):
        for k in list(self.mods):
            L = [m for m in self.mods[k] if m[1] > day]
            if L:
                self.mods[k] = L
            else:
                del self.mods[k]

    def breakdown(self, a, b):
        """逐条列出 a 对 b 的好恶：底数与每个未过期修正项（控制台“情”用）。"""
        return {'base': self.base(a, b), 'mods': [tuple(m) for m in self.mods.get((a, b), ())],
                'total': self.opinion(a, b)}

    def friends(self):
        """好友对与不睦对数：(好友 [(a, b)…], 不睦对数)。只看未迁单的人。"""
        sp = self.sp
        fr, foe = [], 0
        ids = [p.ix for p in self.eng.people if p.gone is None]
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = ids[x], ids[y]
                o1, o2 = self.opinion(a, b), self.opinion(b, a)
                if o1 >= sp.friend_line and o2 >= sp.friend_line:
                    fr.append((a, b))
                if o1 <= sp.foe_line and o2 <= sp.foe_line:
                    foe += 1
        return fr, foe
