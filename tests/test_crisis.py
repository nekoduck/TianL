"""
[INPUT]: 依赖 tianlong.world 的 pacing / menu / body / situation / crowd 与 data/canon 原著世界，tianlong.story 的 choices / scene / brief，tianlong.engine 的 Game；
         复用 tests/test_adjudicate 的 cliff / judge / plan、tests/test_engine 的 StubLLM；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——v12 危局：15 回实录第 12–15 回主角被神农攻山帮众围在崖上，兜底三回都是「四下察看」，第 14 回只扣血改打算就报了合，
          第 15 回开新场主干落回「段誉的图谋」：
          P1-1 危局的单一口径(被围时没有此后、兜底由状态生成、写「将你团团围住」也算、厅上喝止别人不算、只扣血改打算的合记作转且僵持加一、
          结下拘押即可合且僵持归零、僵持满三回合场记要求结构性变化、危局里新场的主干是危局、命悬一线而无人可指时的兜底、身况分档 0.5 与命悬一线同一判定)
[POS]: tests 的危局验证——v12 P1-1(与 P1-7 僵持押走)的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import cliff
from tests.test_engine import StubLLM
from tianlong.engine import Game
from tianlong.story import brief, choices, scene
from tianlong.world import body, menu, pacing
from tianlong.world.world import World

RESOLVED = {"ask": "能否脱身", "state": "resolved", "by": None}


class DangerTest(unittest.TestCase):
    """危局只有一个口径(pacing.danger)：槽位、兜底、合场、主干、僵持提示、幕间省略都读它。"""

    def test_besieged_at_full_strength_is_still_a_crisis(self):
        w = cliff()
        w.player.set("hp", w.player["max_hp"])                                         # 满血：命悬一线之外的危局
        self.assertEqual(choices.later(w), [])                                          # 被围时没有此后
        texts = [t for t, _ in menu._fallbacks(w, [])]
        self.assertNotIn("歇息", texts)
        self.assertNotIn("四下察看", texts)                                             # 第 12–14 回兜底三次都是它
        self.assertIn("设法冲出神农帮众的包围", texts)
        self.assertIn("A 此刻·刚/奇", choices.slots(w)[0])                               # 危局的三槽

    def test_written_pressure_counts_and_others_quarrels_do_not(self):
        w = World.create("测")
        self.assertTrue(pacing.danger(w, [{"who": None, "text": "黄衫汉子们发一声喊，将你团团围住"}]))  # 没有围攻边也算
        self.assertEqual(pacing.danger(w, [{"who": "左子穆", "to": "龚光杰", "text": "左子穆喝止龚光杰"}]), [])

    def test_a_crisis_does_not_close_on_blood_and_moods(self):
        w = cliff()
        scene.begin(w)
        soft = [{"op": "add", "id": "player", "key": "hp", "value": -10}, {"op": "set", "id": "段誉", "key": "intent", "value": "护着少女退后"},
                {"op": "set", "id": "段誉", "key": "mood", "value": "惊惶"}]
        pressed = bool(pacing.danger(w, []))
        scene.close(w, RESOLVED, "挥剑", scene.settles(soft, False, pressed), pressed=pressed, shifted=pacing.structural(soft))
        self.assertEqual((w.player["scene"]["state"], w.player["scene"]["stall"]), ("转", 1))  # 第 14 回的伪合：记作转，僵持加一
        hostage = [{"op": "link", "src": "神农攻山帮众", "dst": "段誉", "rel": "扣为人质"}]
        scene.close(w, RESOLVED, "挥剑", scene.settles(hostage, False, pressed), pressed=pressed, shifted=pacing.structural(hostage))
        self.assertEqual((w.player["scene"]["state"], w.player["scene"]["stall"]), ("合", 0))  # 结下拘押：有账可依

    def test_the_engine_counts_the_stall(self):
        w = cliff()
        llm = StubLLM({"说书人与导演": {"beats": [{"who": None, "text": "刀光掠过，你手臂一凉，鲜血直流", "ops": [{"做": "伤人", "对": "player", "血": 8}]},
                                                 {"who": "段誉", "text": "段誉惊惶失措", "ops": [{"做": "打算", "谁": "段誉", "为": "劝众人罢手"}]}],
                                       "scene": {"state": "合", "ask": "能否脱身"}, "pace": "瞬息"}})
        game = Game(w, llm)
        game.act("挥剑抵挡")
        self.assertEqual((w.player["scene"]["state"], w.player["scene"]["stall"]), ("转", 1))
        game.act("挥剑抵挡")
        self.assertEqual(w.player["scene"]["stall"], 2)

    def test_the_brief_asks_for_a_structural_change(self):
        w = cliff()
        sc = scene.begin(w)
        story = brief.compose(w, None, [])
        self.assertEqual(story["spine"], "crisis")                                      # 危局里新开的场：主干不是段誉的图谋
        self.assertIn("眼前的危局（主角被神农帮众围住）", story["text"])
        w.player.set("scene", {**sc, "state": "转", "turns": 3, "stall": pacing.STALL_WARN})
        self.assertIn(f"危局已僵持{pacing.STALL_WARN}回合：本回合须有结构性的变化", brief.compose(w, None, [])["text"])

    def test_the_stall_follows_the_crisis_not_the_scene(self):
        w = cliff()
        sc = scene.begin(w)
        w.player.set("scene", {**sc, "state": "断", "stall": 2})                       # 导演报断：开新场，危局仍在
        self.assertEqual(scene.begin(w)["stall"], 2)
        w2 = World.create("测")
        sc = scene.begin(w2)
        w2.player.set("scene", {**sc, "state": "合", "stall": 2})
        self.assertEqual(scene.begin(w2)["stall"], 0)                                   # 脱离危局：归零
        old = {k: v for k, v in sc.items() if k != "stall"}
        w2.player.set("scene", old)
        scene.close(w2, RESOLVED, "看")                                                # 旧场没有 stall：按 0 读
        self.assertEqual(w2.player["scene"]["stall"], 0)

    def test_on_the_brink_with_nobody_to_turn_to(self):
        w = World.create("测")
        w.player.set("location", "无量山·谷底")
        w.player.set("hp", 10)
        self.assertEqual([t for t, _ in menu._fallbacks(w, [])], ["强撑伤势，寻隙脱身"])
        self.assertIn("强撑伤势，寻隙脱身", [t for t, _ in menu.check(w, [])])

    def test_wounds_are_graded_by_one_line(self):
        w = World.create("测")
        for hp, word in ((33, "重伤"), (55, "轻伤"), (15, "命悬一线"), (16, "重伤")):
            w.player.set("hp", hp * w.player["max_hp"] // 100)
            self.assertEqual(body.wound(w)[0], word)


if __name__ == "__main__":
    unittest.main()
