"""
[INPUT]: 依赖 tianlong.world 的 access / effects / menu 与 data/canon 原著世界，tianlong.engine 的 Game；复用 tests/test_engine 的 StubLLM / director
[OUTPUT]: unittest 用例——25 回实录里「走不出去、一走千里」的病灶逐条转成离线验收(v3 P2)：
          出路按局部方向措辞(出/进/去/往)不报节点全名、走过的那一步记作来路、一回合的光阴走满即在途中歇脚(en_route 记着去向与余程)、
          下回合续行到达即清、导演看得见「途中」、兜底选项不走回头路、途中先给续行、身处险境不给走开与歇息
[POS]: tests 的局部拓扑与途中验证——v3 方案 P2(4.5 本地拓扑与途中、4.8 看局面的兜底选项)的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_engine import StubLLM, director
from tianlong.engine import Game
from tianlong.world import access, effects, menu
from tianlong.world.world import World

FAR = "王夫人山庄"  # 剑湖宫四日路程，途经大理城
GO = lambda dest: {"op": "set", "id": "player", "key": "location", "value": dest}


class RouteTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {"minutes": 15}  # 片刻

    def test_exits_speak_in_directions_not_node_names(self):
        self.assertEqual(access.heading("剑湖宫·练武厅", "剑湖宫"), "出练武厅")
        self.assertEqual(access.heading("剑湖宫", "剑湖宫·练武厅"), "进练武厅")
        self.assertEqual(access.heading("无量山·山崖", "无量山·谷底"), "去谷底")
        self.assertEqual(access.heading("剑湖宫", "无量山·谷底"), "往谷底")
        self.assertEqual([e["way"] for e in access.exits(self.w)], ["出练武厅"])

    def test_the_step_just_taken_is_the_way_back(self):
        w = self.w
        effects.apply(w, [GO("剑湖宫")], "director")
        self.assertEqual(w.player["came_from"], "剑湖宫·练武厅")
        back = {e["name"]: e["back"] for e in access.exits(w)}
        self.assertTrue(back["剑湖宫·练武厅"])
        self.assertEqual(sum(back.values()), 1)

    def test_a_long_journey_rests_on_the_road(self):
        w = self.w
        _, rejected = effects.apply(w, [GO(FAR)], "director")
        self.assertEqual(w.here, "大理城")                                               # 片刻的光阴不够一步跨过四日路程
        self.assertEqual(w.player["en_route"], {"to": FAR, "left": 2})
        self.assertTrue(rejected[0][1].startswith(access.ON_ROAD))                     # 不是受阻：回告编剧还在路上
        for _ in range(2):                                                             # 一回合一程，千里之行分作几回合
            effects.apply(w, [GO(FAR)], "director")
        self.assertEqual(w.here, FAR)
        self.assertIsNone(w.player["en_route"])                                         # 到了即清

    def test_the_director_sees_the_journey_and_the_clock_counts_only_the_road_walked(self):
        llm = StubLLM(director(pace="片刻", effects=[GO(FAR)]))
        game = Game(World.create("测"), llm)
        tick = game.world.clock.tick
        game.act("去王夫人山庄")
        w = game.world
        self.assertEqual(w.here, "大理城")
        self.assertEqual(w.clock.tick - tick, access.distances(w, "剑湖宫·练武厅")["大理城"] * 1440)
        llm.replies["说书人与导演"] = director(pace="片刻")["说书人与导演"]
        game.act("看")
        self.assertIn(f"【途中】主角正赶往{FAR}，尚余2日路程", llm.director_prompts[-1])


class FallbackTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {"minutes": 15}

    def texts(self):
        return [t for t, _ in menu._fallbacks(self.w, [])]

    def test_fallbacks_do_not_backtrack_or_name_nodes(self):
        effects.apply(self.w, [GO("剑湖宫")], "director")
        texts = self.texts()
        self.assertFalse(any("·" in t or "练武厅" in t for t in texts))              # 刚走出来的厅不再请主角回去
        self.assertIn("歇息片刻", texts)

    def test_on_the_road_the_first_fallback_is_to_go_on(self):
        effects.apply(self.w, [GO(FAR)], "director")
        self.assertEqual(menu._fallbacks(self.w, [])[0], (f"继续赶往{FAR}", [FAR]))

    def test_offline_options_name_directions_and_still_move(self):
        game = Game(World.create("测"))                                                # 编剧失声或离线：兜底统一归 menu
        game.act("出练武厅")
        self.assertEqual(game.world.here, "剑湖宫")                                     # 离线说书人认得方向措辞
        turn = game.act("看")
        self.assertFalse(any("前往" in o or "·" in o for o in turn["options"]))       # P2 实测：编剧被截断时冒出「前往无量山·山崖」

    def test_in_peril_only_the_moment_is_offered(self):
        me = self.w.player
        me.set("hp", me["max_hp"] // 10)
        texts = self.texts()
        self.assertNotIn("歇息片刻", texts)
        self.assertNotIn("出练武厅", texts)                                               # 命悬一线：不给走开
        self.assertIn("四下察看", texts)


if __name__ == "__main__":
    unittest.main()
