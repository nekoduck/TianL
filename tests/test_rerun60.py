"""
[INPUT]: 依赖 tools.rerun 的 load / replay / check / summary 与 tests/fixtures/replay60.json（v12 一局 60 回真模型实录里的举动与各角色原始输出，约 0.24 MB），tianlong.engine 的 Game
[OUTPUT]: unittest 用例——v13 的回归基线：把 60 回实录里真模型的写法原样交给当前引擎重演（不调模型），逐回合断言账上的不变量，并核对 P0 之后的目标：
          跑得完 60 回、没有整回合作废；第 4 回剑锋擦肩落伤、第 60 回乱刀合围气血 ≤ 70；第 7、9 回没有「主角服用断肠散」「解药」的伪分歧；第 8 回通天草交给司空玄成立；
          第 41 回只学练的那一门（凌波微步入门、北冥不动、60 分钟）；段誉的断肠散自第 7 回起一直登记在账、第 48 回账房想消它被拦下记作分歧；
          第 51 回主角被留在原处研习（石级隧道的出洞被剥掉）；账文分歧里没有技术性条目；无据丢弃里没有气血增减
[POS]: tests 的 v13 验证——世界会与原局分叉（第 8 回起通天草归了司空玄），越往后越只是「同样的模型话语落在新世界上」；它量的是新引擎能否接住真模型的写法，不是复刻原局
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest
from pathlib import Path

from tools import rerun

FIXTURE = Path(__file__).parent / "fixtures" / "replay60.json"


class Replay60Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.turns = rerun.load(FIXTURE)
        cls.game, cls.records = rerun.replay(cls.turns)

    def turn(self, n):
        return self.records[n - 1]

    def test_all_sixty_turns_run_and_the_invariants_hold(self):
        self.assertEqual(len(self.records), 60)
        self.assertEqual([r["turn"] for r in self.records if r.get("error")], [])           # 没有整回合作废
        self.assertEqual(rerun.check(self.game, self.records), [])

    def test_the_blades_that_graze_and_surround_wound(self):
        r4, r60 = self.turn(4), self.turn(60)
        self.assertEqual((r4["hp0"] - r4["hp"], r4["hurt"]), (5, 5))                      # 第 4 回「剑锋擦过肩头」：从前被悄悄丢掉，如今落伤
        self.assertLessEqual(r60["hp"], 70)                                               # 第 60 回「乱刀合围、连中数记」：从前气血纹丝不动
        self.assertGreater(r60["hurt"], 0)

    def test_no_false_drift_in_turns_7_to_9(self):
        for n in (7, 8, 9):
            self.assertEqual(self.turn(n)["drift"], [], n)                                  # 「主角服用断肠散」「从谁身上夺取」「解药」都不再是分歧

    def test_the_herb_changes_hands_in_turn_8(self):
        self.assertFalse([v for v in self.turn(8)["void"] if "通天草" in v])               # 交给没有被作废
        self.assertEqual(self.game.world.graph.get("通天草", "holder"), "司空玄")           # 账上与读者读到的一致

    def test_the_poison_is_registered_in_turn_7_and_stays(self):
        self.assertIn("断肠散", self.turn(7)["poisoned"].get("段誉", []))
        for n in range(7, 61):
            self.assertIn("断肠散", self.turn(n)["poisoned"].get("段誉", []), n)            # 第 48 回账房想消、第 51 回导演重添——毒一直在账上
        wiped = [d for n in range(47, 51) for d in self.turn(n)["drift"] if "规则登记的毒" in d]
        self.assertTrue(wiped)                                                              # 第 48 回账房据「紫胀之色退去」想消中毒：被拦下，记作分歧交导演

    def test_only_the_chosen_art_is_learned_in_turn_41(self):
        study = self.turn(41)["study"]
        self.assertEqual(sorted(study), ["凌波微步"])                                       # 北冥不动
        self.assertEqual((study["凌波微步"]["minutes"], study["凌波微步"]["stage"]), (60, 1))  # 60 分钟，一回合入门；从前两门同时入门、记了 240 分钟

    def test_the_study_in_turn_51_keeps_the_hero_where_he_chose_to_be(self):
        r = self.turn(51)
        self.assertEqual(r["here0"], r["here"])                                             # 主角没有被带出洞
        self.assertTrue([v for v in r["void"] if "离开此处前往" in v and "主角并未起意" in v])   # 出洞的拍被剥掉、明告编剧

    def test_technical_failures_never_reach_the_director(self):
        from tianlong.world.settle import TECHNICAL
        for r in self.records:
            self.assertFalse([d for d in r.get("drift", []) if TECHNICAL.search(d)], r["turn"])

    def test_the_summary_reads_like_the_targets(self):
        text = rerun.summary(self.game, self.records)
        self.assertIn("终局气血 70", text)
        self.assertIn("通天草在 司空玄", text)
        self.assertIn("研习账 ['凌波微步', '北冥神功']", text)


if __name__ == "__main__":
    unittest.main()
