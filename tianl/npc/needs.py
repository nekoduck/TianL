"""五项需求（计划 6.3）：h 饥、e 困、c 洁、s 群、a 志。

每个时辰按“做了什么”结算一次（惰性求值：只在有决定的时辰动）。数字全在 SiteSpec.needs。
两条校准规则（计划 6.3）：每项需求按“一日收支”校准，日常供给必须盖得住日常消耗；
性格改的是门槛和权重，不是生理常数（馋只微调饥的消耗，真正让人偷食的是 TemptSpec 的起念门槛）。
"""
from ..core import clamp
from .spec import SCALE, A_MEAL, A_SLEEP


class Needs:
    def __init__(self, eng):
        self.eng = eng
        self.sp = eng.spec.needs

    def urgency(self, level):
        """迫切度 u(x) = ((100 - x) / 100)^2 + 0.05（计划 6.4）。"""
        sp = self.sp
        return ((SCALE - level) / SCALE) ** sp.urgency_pow + sp.urgency_floor

    def settle(self, p, d, slot, gain):
        """按决定 d = (场所, 活动, 层, 原因) 结算 p 这一时辰的五项需求。gain 是斋食的饥补益（非斋食时忽略）。"""
        sp = self.sp
        nd, act = p.need, d[1]
        e = sp.eff.get(act, {})
        fh = 1 + (p.T - sp.hunger_t_mid) / sp.hunger_t_div
        b_ = sp.base
        nd['h'] = clamp(nd['h'] + (sp.hunger_sleep * fh if act == A_SLEEP else b_['h'] * fh + e.get('h', 0))
                        + (gain if act == A_MEAL else 0))
        nd['e'] = clamp(nd['e'] + b_['e'] + e.get('e', 0))
        nd['c'] = clamp(nd['c'] + b_['c'] + e.get('c', 0) + (sp.morning_c if slot == sp.morning_slot and act != A_SLEEP else 0))
        nd['s'] = clamp(nd['s'] + b_['s'] * (sp.social_g[0] + p.G / sp.social_g[1]) + e.get('s', 0))
        b = sp.bonus.get(act)
        nd['a'] = clamp(nd['a'] + b_['a'] + e.get('a', 0) + ((b[1] if p.track == b[0] else b[2]) if b else 0)
                        + (sp.duty_a if d[2] in sp.duty_layers and act != A_SLEEP else 0))
