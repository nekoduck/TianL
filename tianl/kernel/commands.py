"""命令：物理约束拒绝，规范约束放行但记违规。

cmd_move 走动（夜间上锁的场所无钥匙则物理层拒绝）；cmd_take 取独有物（人与物不在一处则拒绝；
非保管人取走照样执行，但记“违规”，在场者举报则当场立案）。月朔点检发现独有物不在应在处，记 AUDIT_MISSING。
cmd_put / cmd_use / cmd_say 之后由集成代理实现。
"""
from ..core.calendar import SLOTS, SLOTS_PER_DAY


class CommandsMixin:
    def has_key(self, actor, place, day, slot):
        o = self.office_of(actor, day)
        if o and self.S.site_of.get(self.base_of(o)) == place: return True
        return self.x('SELECT 1 FROM roster WHERE person=? AND day=? AND slot=? AND place=?', (actor, day, slot, place)).fetchone() is not None

    def cmd_move(self, actor, place, day, slot):
        acc = self.x('SELECT access FROM place WHERE id=?', (place,)).fetchone()
        if acc and acc[0] == 'locked_night' and SLOTS[slot] in self.S.org.lock_slots and not self.has_key(actor, place, day, slot):
            self.ev('CMD_REJECTED', place=place, actor=actor, slot=slot, cmd='MOVE', why='夜间上锁, 无钥匙'); return False
        self.x('INSERT INTO assignment(person,t_from,t_to,place,activity) VALUES(?,?,?,?,?)',
               (actor, day * SLOTS_PER_DAY + slot, day * SLOTS_PER_DAY + slot, place, '走动'))
        return True

    def cmd_take(self, actor, item, day, slot):
        name, home, keeper, custodian, place = self.x('SELECT name,home,keeper,custodian,place FROM item WHERE id=?', (item,)).fetchone()
        here = self.where(actor, day, slot)
        if place is None or here is None or here[0] != place:
            self.ev('CMD_REJECTED', place=place, actor=actor, slot=slot, cmd='TAKE', why='人与物不在一处'); return None
        permitted = actor == custodian or actor == self.holder(keeper, day)
        wit = self.present(place, day, slot, exclude=actor)
        self.x('UPDATE item SET custodian=?, place=NULL WHERE id=?', (actor, item))
        e = self.ev('ITEM_TAKEN', place=place, actor=actor, slot=slot, item=name, norm='合规' if permitted else '违规', witnesses=wit)
        if not permitted and wit:
            dp = self.S.org.discipline_place
            r = self.ev('REPORT', place=place, actor=wit[0], cause=e, slot=slot, to=self.S.place_name[dp], about=actor)
            self.ev('CASE_OPENED', place=dp, actor=self.holder(self.T.discipline_head, day), cause=r, about=actor)
        return e

    def audit_items(self):
        for iid, name, home, keeper, place, known in self.x('SELECT id,name,home,keeper,place,missing_known FROM item ORDER BY id').fetchall():
            if place != home and not known:
                self.x('UPDATE item SET missing_known=1 WHERE id=?', (iid,))
                self.ev('AUDIT_MISSING', place=home, actor=self.holder(keeper), slot=self.K['audit_slot'], item=name)
