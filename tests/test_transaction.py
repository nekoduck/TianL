"""
[INPUT]: 依赖 tianlong.world 的 adjudicate / situation 与 data/canon 原著世界；复用 tests/test_adjudicate 的 plan / judge / GO
[OUTPUT]: unittest 用例——43 回对局(王侠墨)暴露的「拍文与账本不同生共死」逐条转成离线验收：
          拍里改变物理状态的指令落不了即整拍交返工、仍不成立即作废(第16回)、受阻不倒退、无伤扣血不入账(第5回)、
          词表不再替导演挪人(第9回「拉着二人」把在场恶人记成随行)、同伴诸拍之后才随行(第11回人质被主角带下崖)、擒者与人质同处
          (v12 B1：擒者走则人质随之由系统连带，不再交返工；擒者先了断拘押再走，人质留下)
[POS]: tests 的一拍一事务验证——v3 方案 P0-1 的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import GO, judge, plan
from tianlong.world import adjudicate, situation
from tianlong.world.world import World

FOLLOW = lambda pid: {"op": "link", "src": pid, "dst": "player", "rel": "随行"}


class TransactionTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")

    def test_a_beat_whose_move_fails_is_doomed_and_the_player_does_not_backtrack(self):
        self.w.player.set("location", "无量玉壁")
        r = judge(self.w, plan(("player", "你钻入石隙，推开石门进了一间石室", [GO("琅嬛福地")])))
        self.assertEqual(self.w.here, "无量玉壁")                                  # 近处绕回谷底仍过不去：原地不动
        self.assertIn(1, adjudicate.doomed(r))                                       # 文字写进了石室，账上却没有：返工或作废

    def test_a_wound_that_was_parried_costs_no_blood(self):
        hp = self.w.player["hp"]
        r = judge(self.w, plan(("干光豪", "干光豪横剑直刺你肩头", [{"op": "add", "id": "player", "key": "hp", "value": -18}]),
                               ("马五德", "马五德挥袖将那一剑荡了开去", [])))
        self.assertEqual(self.w.player["hp"], hp)                                   # 下一拍荡开了：那一剑没有伤到你——拍文与指令相悖，以拍文为准
        self.assertIn("parried", [f.kind for f in r.soft])                          # v13 不是悄悄丢掉：记一条软违例
        self.assertEqual(self.w.turn["hurt"], 0)

    def test_a_wound_lands_by_rule_even_when_the_beat_never_says_wound(self):
        """v13 否决即事件：导演宣告的伤不再因拍文里没有伤字眼而被悄悄丢掉；落多少归规则封顶，编剧得到连带去补写。"""
        hp = self.w.player["hp"]
        r = judge(self.w, plan(("player", "你环顾四周", [{"op": "add", "id": "player", "key": "hp", "value": -5}])))
        self.assertEqual(self.w.player["hp"], hp - 5)                               # 无人出手、不涉险地：磕碰，封顶 SCRATCH，这五点照落
        self.assertIn("unwritten", [f.kind for f in r.soft])                        # 拍文没写伤：软违例，交编剧补写
        self.assertTrue(any("你受了" in n for n in r.notes))                        # 连带：账上有伤，正文就得写
        r = judge(self.w, plan(("干光豪", "干光豪一剑刺中你肩头，鲜血直流", [{"op": "add", "id": "player", "key": "hp", "value": -10}])))
        self.assertEqual(self.w.player["hp"], hp - 5 - 10)
        self.assertNotIn("unwritten", [f.kind for f in r.soft])                     # 写了伤，不记

    def test_the_lexicon_never_moves_people(self):
        g = self.w.graph
        for p in ("云中鹤", "南海鳄神"):
            g.set(p, "location", self.w.here)
        r = judge(self.w, plan(("player", "段誉与钟灵慌忙起身。你拉着二人奔出大厅",
                                [FOLLOW("段誉"), FOLLOW("钟灵"), GO("剑湖宫")])))
        self.assertEqual(sorted(situation.party(self.w)), ["段誉", "钟灵"])         # 「二人」只指上一句的段誉与钟灵
        self.assertEqual(g.get("云中鹤", "location"), "剑湖宫·练武厅")
        self.assertEqual([f.kind for f in r.hard], [])
        r = judge(self.w, plan(("player", "你拉着马五德奔出", [GO("无量山")])))     # 漏写随行：交导演写明，不再替他挪步
        self.assertEqual(g.get("马五德", "location"), "剑湖宫·练武厅")
        self.assertIn("follow", [f.kind for f in r.hard])
        self.assertNotIn(1, adjudicate.doomed(r))                                    # 词表可能看错：只返工、不作废

    def test_a_companion_seized_in_a_later_beat_stays_with_the_captor(self):
        g = self.w.graph
        g.link("钟灵", "player", "随行")
        g.set("云中鹤", "location", self.w.here)
        r = judge(self.w, plan(("player", "你纵身跃出大厅", [GO("剑湖宫")]),
                               ("云中鹤", "云中鹤长爪抓住钟灵肩头，将她擒住",
                                [{"op": "unlink", "src": "钟灵", "dst": "player", "rel": "随行"},
                                 {"op": "link", "src": "云中鹤", "dst": "钟灵", "rel": "扣为人质"}])))
        self.assertEqual(g.get("钟灵", "location"), g.get("云中鹤", "location"))   # 人质不随主角先走一步而被带走
        self.assertEqual([f.kind for f in r.hard], [])

    def test_captor_and_hostage_share_a_place(self):
        g = self.w.graph
        g.set("云中鹤", "location", self.w.here)
        g.link("云中鹤", "钟灵", "扣为人质")
        r = judge(self.w, plan(("云中鹤", "云中鹤长啸一声，押着钟灵飞身出了大厅", [{"op": "set", "id": "云中鹤", "key": "location", "value": "剑湖宫"}])))
        self.assertEqual(g.get("钟灵", "location"), "剑湖宫")                        # v12 B1：擒者走则人质随之，由系统连带
        self.assertIn("云中鹤", situation.captors(self.w, "钟灵"))                   # 仍受制
        self.assertNotIn("custody", [f.kind for f in r.hard])                       # 不再交返工

    def test_a_captor_who_lets_go_first_leaves_the_hostage(self):
        g = self.w.graph
        g.set("云中鹤", "location", self.w.here)
        g.link("云中鹤", "钟灵", "扣为人质")
        r = judge(self.w, plan(("云中鹤", "云中鹤一把推开钟灵，飞身出了大厅",
                                [{"op": "unlink", "src": "云中鹤", "dst": "钟灵", "rel": "扣为人质"},
                                 {"op": "set", "id": "云中鹤", "key": "location", "value": "剑湖宫"}])))
        self.assertEqual(g.get("钟灵", "location"), "剑湖宫·练武厅")                 # 先了断拘押再走：人质留下
        self.assertEqual([f.kind for f in r.hard], [])


if __name__ == "__main__":
    unittest.main()
