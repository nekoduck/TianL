"""
[INPUT]: 依赖 tianlong.world 全部基础设施（不接入 LLM）
[OUTPUT]: unittest 用例——历法、剧情后果落账、器物与地理归基础设施、宽松规整、世界物理、场外在场性、消息延迟、隐情揭示、LOD 污染、存读档
[POS]: tests 的状态层验证，证明剧情能自由改变既有世界，而地理与器物只由系统掌管
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import tempfile
import unittest
from pathlib import Path

from tianlong.world import lod, rag
from tianlong.world.clock import Clock
from tianlong.world.world import World

GO = lambda dest: {"op": "set", "id": "player", "key": "location", "value": dest}


class ClockTest(unittest.TestCase):
    def test_label_and_crossing(self):
        c = Clock(724)
        self.assertEqual(c.label(), "元祐七年三月初一 辰时")
        self.assertEqual(c.advance(12 * 30), (30, 1))
        self.assertEqual(Clock(12 * 360 * 3).label(), "绍圣元年正月初一 子时")
        self.assertEqual(Clock().label(19), "元祐七年正月二十")


class PlotTest(unittest.TestCase):
    def setUp(self):
        self.w = World.from_seed("测试")

    def test_plot_consequences_become_truth(self):
        ops = [{"op": "set", "id": "段誉", "key": "status", "value": "wounded"},
               {"op": "set", "id": "左子穆", "key": "mood", "value": "恼羞成怒"},
               {"op": "link", "src": "左子穆", "dst": "player", "rel": "记恨"},
               {"op": "add", "id": "player", "key": "hp", "value": -20},
               {"op": "set", "id": "剑湖宫", "key": "state", "value": "比剑被搅散，满厅狼藉"}]
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual((len(applied), rejected), (5, []))
        pack = rag.build(self.w)
        self.assertEqual(pack["scene"]["state"], "比剑被搅散，满厅狼藉")
        self.assertIn("左子穆→你：记恨", next(p for p in pack["people"] if p["name"] == "左子穆")["toward_you"])
        self.assertEqual(self.w.player["hp"], 80)
        self.assertIn("段誉", self.w.taint)

    def test_items_and_geography_belong_to_infrastructure(self):
        ops = [{"op": "create", "id": "青衫剑客", "type": "person", "attrs": {}},           # 不能新造人物
               {"op": "create", "id": "断剑", "type": "item", "attrs": {}},                 # 不能新造器物
               GO("后山禁地"),                                                              # 世上没有此地
               {"op": "push", "id": "player", "key": "inventory", "value": "倚天剑"},       # 世上没有此物
               {"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"},  # 远在琅嬛福地
               {"op": "set", "id": "北冥神功卷轴", "key": "grants", "value": {}},            # 器物定义不可改
               {"op": "set", "id": "剑湖宫", "key": "desc", "value": "一片废墟"}]            # 地理定义不可改
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual((applied, len(rejected)), ([], 7))

    def test_loose_writing_is_understood(self):
        ops = [{"op": "set", "id": "player", "key": "姿态", "value": "跌坐"},  # 中文属性名
               GO("无量玉璧")]                                                 # 景物名 → 其所在之地
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual((len(applied), rejected), (2, []))
        self.assertEqual((self.w.player["posture"], self.w.here), ("跌坐", "无量后山"))

    def test_hidden_item_found_through_plot(self):
        self.w.apply([GO("琅嬛福地")], "director")
        self.assertEqual(rag.build(self.w)["items"], [])
        self.assertTrue(any("北冥神功卷轴" in h for h in rag.backstage(self.w)["hidden"]))
        self.w.apply([{"op": "set", "id": "北冥神功卷轴", "key": "hidden", "value": False}], "director")  # 蒲团磕破
        self.assertEqual([i["name"] for i in rag.build(self.w)["items"]], ["北冥神功卷轴"])
        applied, _ = self.w.apply([{"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"}],
                                  "director")
        self.assertEqual(len(applied), 1)
        self.assertIsNone(self.w.graph.get("北冥神功卷轴", "location"))

    def test_player_hp_floor(self):
        self.w.apply([{"op": "add", "id": "player", "key": "hp", "value": -500}], "director")
        self.assertEqual(self.w.player["hp"], 1)

    def test_physics_rejects_the_impossible(self):
        self.w.graph.set("左子穆", "status", "dead")
        ops = [{"op": "set", "id": "左子穆", "key": "status", "value": "alive"},  # 死者复生
               {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},     # 远在无锡，够不着
               {"op": "set", "id": "段誉", "key": "status", "value": "wounded"}]   # 合法
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual([op["id"] for op in applied], ["段誉"])
        self.assertEqual(len(rejected), 2)

    def test_offscreen_cannot_touch_player_but_can_hate_him(self):
        _, ring = lod.lod1_scope(self.w)
        ops = [{"op": "add", "id": "player", "key": "hp", "value": -50},
               {"op": "link", "src": "鸠摩智", "dst": "player", "rel": "起了杀心"},
               {"op": "set", "id": "段正淳", "key": "status", "value": "wounded"},
               {"op": "set", "id": "段正淳", "key": "location", "value": "雁门关"},  # 一日千里
               {"op": "set", "id": "段正淳", "key": "location", "value": "万劫谷"}]
        applied, rejected = self.w.apply(ops, "lod1", ring)
        self.assertEqual((len(applied), len(rejected)), (3, 2))
        self.assertEqual(self.w.player["hp"], 100)

    def test_garbage_rejected(self):
        _, rejected = self.w.apply([{"op": "rm"}, "x", {"op": "set", "id": "无此人", "key": "a", "value": 1},
                                    {"op": "set", "id": ["段誉"], "key": "mood", "value": 1},
                                    {"op": "set", "id": "player", "key": "location", "value": {"a": 1}}], "director")
        self.assertEqual(len(rejected), 5)


class PropagationTest(unittest.TestCase):
    def test_news_delay_follows_road_distance(self):
        w = World.from_seed()
        dist = w.graph.distances(w.here)["聚贤庄"]  # 剑湖宫→大理城→小镜湖→聚贤庄 = 21 日
        self.assertEqual(dist, 21)
        op = {"op": "set", "id": "游骥", "key": "status", "value": "dead"}
        w.apply([op], "canon")
        w.record("游骥身亡", "聚贤庄", [op], "canon", 1)
        self.assertEqual(w.knowledge.view("游骥")["status"], "alive")  # 真相已变，认知未变
        w.advance(12 * (dist - 1))
        self.assertEqual(w.sync(), [])
        w.advance(12)
        self.assertEqual([e["summary"] for e in w.sync()], ["游骥身亡"])
        self.assertEqual(w.knowledge.view("游骥")["status"], "dead")

    def test_offscreen_plot_spreads_as_news(self):
        w = World.from_seed()
        _, ring = lod.lod1_scope(w)
        lod.absorb(w, [{"where": "大理城", "event": "国师夜闯天龙寺", "result": "段正淳负伤",
                        "effects": [{"op": "set", "id": "段正淳", "key": "status", "value": "wounded"}]}], ring)
        self.assertEqual(w.knowledge.view("段正淳")["status"], "alive")
        w.advance(12 * 3)
        w.sync()
        self.assertEqual(w.knowledge.view("段正淳")["status"], "wounded")

    def test_observation_overrides_belief(self):
        w = World.from_seed()
        w.apply([{"op": "set", "id": "段正淳", "key": "location", "value": "万劫谷"}], "canon")
        w.apply([GO("大理城")], "director")
        w.sync()
        self.assertIsNone(w.knowledge.view("段正淳")["location"])  # 亲眼所见：段正淳不在城中

    def test_secrets_backstage_only_until_revealed(self):
        w = World.from_seed()
        self.assertNotIn("生父", str(rag.build(w)))
        self.assertIn("段延庆—生父—段誉", rag.backstage(w)["secrets"])
        w.apply([{"op": "reveal", "src": "段延庆", "dst": "段誉", "rel": "生父"}], "director")
        self.assertNotIn("段延庆—生父—段誉", rag.backstage(w)["secrets"])
        w.graph.set("段延庆", "location", "剑湖宫")
        self.assertIn("段延庆—生父—段誉", rag.build(w)["relations"])


class LodTest(unittest.TestCase):
    def test_clean_canon_follows_rails(self):
        w = World.from_seed()
        w.advance(12 * 120)  # 跨过杏子林之变（day 150）
        due = lod.due_canon(w, 120, 4)
        self.assertEqual([(ev["id"], r) for ev, r in due], [("杏子林之变", [])])
        lod.settle(w, due[0][0], due[0][0], "canon")
        self.assertIsNone(w.graph.get("乔峰", "faction"))

    def test_player_pollution_marks_dirty(self):
        w = World.from_seed()
        w.player.set("location", "燕子坞")
        w.apply([{"op": "link", "src": "阿朱", "dst": "player", "rel": "倾心"}], "director")
        self.assertIn("阿朱", w.taint)
        ev = next(e for e in w.canon if e["id"] == "聚贤庄之战")
        self.assertTrue(any("阿朱" in r for r in lod.dirt(w, ev, 2)))

    def test_broken_premise(self):
        w = World.from_seed()
        w.apply([{"op": "set", "id": "无崖子", "key": "status", "value": "dead"}], "canon")
        ev = next(e for e in w.canon if e["id"] == "珍珑破局")
        self.assertTrue(lod.broken(w, ev))


class PersistenceTest(unittest.TestCase):
    def test_roundtrip(self):
        w = World.from_seed("存档")
        w.apply([GO("琅嬛福地"), {"op": "reveal", "src": "玄慈", "dst": "虚竹", "rel": "生父"}], "director")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            w.save(path)
            v = World.load(path)
        self.assertEqual(v.dump(), w.dump())


if __name__ == "__main__":
    unittest.main()
