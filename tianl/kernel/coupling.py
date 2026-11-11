"""引擎 -> 经济的两处耦合（ARCHITECTURE 5.1）：各有开关，各发事件，缺省都不触发，所以接上引擎也不改变经济表（econ_hash 中立）。

  (a) 厨房人手不足 -> 半餐 -> 当日口粮减量：引擎在前一日收盘（engine.end_day）或更早时调 set_meal_ration(day, factor)，
      内核在 day 日的消耗阶段把斋粮按 factor 减量，发 MEAL_HALVED。开关 couplings['half_meal']（缺省开，但没有人调就从不触发）。
      为什么只能“告知明日”：内核的消耗阶段在 begin_day 的经济阶段里，早于 engine.begin_day；当日的备斋人手要等引擎排完人才知道，
      所以集成世界以“前一日收盘时的厨房人手”决定次日口粮。要改成当日生效，得把消耗阶段挪到 engine.begin_day 之后（改契约，不是改这里）。
  (b) 偷食扣厨房粮：引擎在判定某人偷食成功后调 cmd_steal_food(actor, q)，内核从寺库粮仓扣粮（具名消灭 'theft'），发 GRAIN_STOLEN。
      开关 couplings['food_theft']，缺省关：关着时什么都不做、不发事件（基准里 (b) 关闭）。
"""


class CouplingMixin:
    def _init_couplings(self):
        self.couplings = {'half_meal': True, 'food_theft': False}
        self.meal_scale = {}                    # 日 -> (系数, 缘由)；只在 set_meal_ration 写入，消耗阶段取走

    def set_meal_ration(self, day, factor, why=''):
        """告知内核 day 日的斋粮按 factor 减量（0 < factor <= 1；1 即不减）。返回是否登记。
        开关 couplings['half_meal'] 关着则不登记。day 必须尚未结算消耗阶段（当日 begin_day 之后即已结算）。"""
        if not self.couplings['half_meal']: return False
        if not 0 < factor <= 1: raise ValueError(f'口粮系数须在 (0, 1]：{factor!r}')
        if day < self.day or (day == self.day and self._began): raise ValueError(f'第 {day} 日的口粮已结算，只能告知明日及以后')
        if factor < 1: self.meal_scale[day] = (factor, why)
        else: self.meal_scale.pop(day, None)
        return True

    def _meal_need(self, need):
        """当日斋粮应供数：有引擎告知的减量就按系数减，并返回 (应供, 减量信息或 None)。"""
        s = self.meal_scale.pop(self.day, None)
        if s is None or not self.couplings['half_meal']: return need, None
        return int(need * s[0]), (s[0], need, s[1])

    def cmd_steal_food(self, actor, q, slot=None, cause=None):
        """(b) 偷食扣厨房粮。开关关着返回 0（不扣粮、不发事件）；开着则从寺库粮仓扣 q 合（不足则扣到空），返回实扣数。"""
        if not self.couplings['food_theft']: return 0
        g = self.consume(self.ac.org, self.pl.granary, self.cm.staple, q, 'theft')
        if g: self.ev('GRAIN_STOLEN', place=self.pl.refectory, actor=actor, cause=cause, slot=slot, grain=g)
        return g
