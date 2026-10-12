"""
[INPUT]: 依赖 tianlong.world 的 body / growth / effects / rag 与 data/canon 原著世界；复用 tests/test_adjudicate 的 plan / judge / GO
[OUTPUT]: unittest 用例——43 回对局(王侠墨)里「武功一练就重伤，请教段誉也无济于事」与「另立帛卷、真秘籍却一直暗藏」逐条转成离线验收：
          伤势措辞以气血与内伤共同定(五成半气血只是轻伤)、研习预裁(懂易理者解卦位、低风险武学无病不岔气、带伤强练才岔气且一回合至多一级)、
          研习之拍不扣血、无人出手一拍至多伤五点、内伤按分级升降、歇满两个时辰养伤、器物近似名认现场、另立的物件认回此地暗藏的原著秘籍
[POS]: tests 的身体规则验证——v3 方案 P0-3「身体归规则 + 实体解析认现场」的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest
from unittest import mock

from tests.test_adjudicate import judge, plan
from tianlong.world import body, effects, growth, rag
from tianlong.world.world import World

BOOK = "北冥神功卷轴"
VAULT = "琅嬛福地·玉像石室"
HURT = lambda n: {"op": "add", "id": "player", "key": "hp", "value": n}


def wound(w) -> str:
    return rag.condition(w)[0]["text"]


class BodyTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_half_blood_is_not_grave_but_a_torn_meridian_is(self):
        me = self.w.player
        me.set("hp", 55)
        self.assertEqual(wound(self.w), "轻伤")                                       # 旧阈值下五成半气血就是「重伤」
        me.set("hp", 25)
        self.assertEqual(wound(self.w), "重伤")
        me.set("hp", me["max_hp"])
        me.set("conditions", ["经脉受损"])
        self.assertEqual(wound(self.w), "重伤")

    def test_a_scholar_of_the_yijing_helps_with_the_steps(self):
        w = self.w                                                                    # 剑湖宫里段誉就在身边：他熟读易经
        luck = body.forecast(w, "凌波微步")
        self.assertIn("段誉通晓易理", luck["why"])
        self.assertGreaterEqual(luck["factor"], 1.0)                                  # 请教了不再白搭：最差也照计时长

    def test_strain_only_comes_from_forcing_it_while_hurt(self):
        w = self.w
        with mock.patch.object(body, "fate", return_value=3):
            self.assertFalse(body.forecast(w, BOOK)["strain"])                        # 逍遥派这两门初学无凶险
            w.player.set("conditions", ["内息紊乱"])
            self.assertTrue(body.forecast(w, BOOK)["strain"])                        # 带伤强练才岔气
            w.player.set("location", VAULT)
            w.graph.set(BOOK, "hidden", False)
            growth.study(w, BOOK, 60)
            growth.study(w, BOOK, 60)
        self.assertEqual(body.severity(w), 2)                                         # 一回合至多加重一级

    def test_a_study_beat_costs_no_blood(self):
        w = self.w
        w.player.set("location", VAULT)
        w.graph.set(BOOK, "hidden", False)
        hp = w.player["hp"]
        judge(w, plan(("player", "你照着帛卷修习，忽觉一阵气血翻涌，口角溢血", [{"op": "study", "id": "player", "value": BOOK}, HURT(-20)])), [BOOK])
        self.assertEqual(w.player["hp"], hp)

    def test_without_a_foe_a_beat_hurts_at_most_five(self):
        w = self.w
        hp = w.player["hp"]
        judge(w, plan(("player", "你脚下一滑摔了一跤，额头磕破流血", [HURT(-20)])))
        self.assertEqual(w.player["hp"], hp - 5)

    def test_inner_injury_rises_one_grade_a_turn_and_heals_with_rest(self):
        w = self.w
        say = lambda v, kind="push": effects.apply(w, [{"op": kind, "id": "player", "key": "conditions", "value": v}], "director")
        say("岔气走火")
        say("经脉尽断")
        self.assertEqual(w.player["conditions"], ["内息紊乱"])                         # 导演写得再重，一回合也只升一级
        w.player.set("hp", 40)
        w.turn = {}
        self.assertEqual(body.recover(w, 60), "")                                     # 一个时辰不算养伤
        body.recover(w, w.clock.minutes("一夜"))
        self.assertEqual(w.player["conditions"], [])
        self.assertGreater(w.player["hp"], 40)

    def test_a_fuzzy_name_finds_the_book_in_the_room(self):
        w = self.w
        self.assertEqual(effects.resolve(w, "北冥神功帛卷"), BOOK)
        w.player.set("location", VAULT)
        r = judge(w, plan(("player", "你撕开蒲团，摸出一卷帛卷，揣入怀中", [{"op": "push", "id": "player", "key": "inventory", "value": "蒲团里的帛卷"}]),
                          spawn=[{"kind": "thing", "name": "蒲团里的帛卷"}]), ["蒲团里的帛卷"])
        self.assertIn(BOOK, w.player["inventory"])                                    # 认回原著秘籍：不另立一卷没有武学的帛卷
        self.assertFalse(w.graph.has("蒲团里的帛卷"))
        self.assertEqual([f.kind for f in r.hard], [])


if __name__ == "__main__":
    unittest.main()
