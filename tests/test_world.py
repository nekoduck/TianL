"""
[INPUT]: 依赖 tianlong.world 全部基础设施（不接入 LLM）
[OUTPUT]: unittest 用例——历法、创造物化、世界物理、场外在场性、消息延迟传播、认知/真相分离、隐情揭示、LOD 污染判定、存读档
[POS]: tests 的状态层验证，证明基础设施能把任意创造稳稳接住，并只拦下违背世界物理的部分
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


class CreationTest(unittest.TestCase):
    def setUp(self):
        self.w = World.from_seed("测试")

    def test_created_person_item_and_place_become_truth(self):
        ops = [{"op": "create", "id": "青衫剑客", "type": "person", "attrs": {"title": "无量剑西宗弃徒", "power": 50}},
               {"op": "create", "id": "断剑", "type": "item", "attrs": {"desc": "半截青钢剑"}},
               {"op": "push", "id": "player", "key": "inventory", "value": "断剑"},
               {"op": "create", "id": "后山崖底", "type": "location", "road": {"to": "剑湖宫", "days": 0},
                "attrs": {"region": "无量山", "desc": "深谷"}},
               {"op": "link", "src": "青衫剑客", "dst": "player", "rel": "欠你一命"}]
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual((len(applied), rejected), (5, []))
        self.w.sync()
        pack = rag.build(self.w)
        self.assertIn("青衫剑客", [p["name"] for p in pack["people"]])  # 默认落在此地，且被亲眼看见
        self.assertEqual(self.w.graph.get("青衫剑客", "status"), "alive")
        self.assertIn("断剑", self.w.player["inventory"])
        self.assertIsNone(self.w.graph.get("断剑", "location"))  # 随身即离地
        self.assertIn("后山崖底", [e["name"] for e in pack["exits"]])

    def test_infrastructure_tolerates_loose_schema(self):
        ops = [{"op": "create", "id": "后山禁地", "type": "location",
                "attrs": {"desc": "崖壁如玉", "road": {"to": "剑湖宫"}}},          # road 写进了 attrs、缺 days
               {"op": "create", "id": "崖底石洞", "type": "location", "attrs": {}},  # 没写 road：缺省连到此地
               GO("后山禁地"),
               {"op": "set", "id": "player", "key": "姿态", "value": "跌坐"},           # 中文属性名
               {"op": "create", "id": "火折", "type": "item", "attrs": {"location": "player"}},  # 造出即随身
               GO("无量玉璧")]                                                            # 景物名 → 其所在之地
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual((len(applied), rejected), (6, []))
        self.assertEqual(dict(self.w.graph.roads("后山禁地")), {"剑湖宫": 1})
        self.assertEqual((self.w.player["posture"], self.w.here), ("跌坐", "剑湖宫"))
        self.assertIn("火折", self.w.player["inventory"])

    def test_player_hp_floor(self):
        self.w.apply([{"op": "add", "id": "player", "key": "hp", "value": -500}], "director")
        self.assertEqual(self.w.player["hp"], 1)

    def test_physics_rejects_only_impossible(self):
        self.w.graph.set("左子穆", "status", "dead")
        ops = [{"op": "set", "id": "左子穆", "key": "status", "value": "alive"},       # 死者复生
               {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},          # 远在无锡，够不着
               {"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"},  # 远在琅嬛福地
               {"op": "create", "id": "孤岛", "type": "location", "road": {"to": "蓬莱"}},  # 接向不存在之地
               {"op": "set", "id": "段誉", "key": "status", "value": "wounded"}]        # 合法
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual([op["id"] for op in applied], ["段誉"])
        self.assertEqual(len(rejected), 4)

    def test_offscreen_cannot_touch_player_but_can_hate_him(self):
        _, ring = lod.lod1_scope(self.w)
        ops = [{"op": "add", "id": "player", "key": "hp", "value": -50},
               {"op": "link", "src": "钟万仇", "dst": "player", "rel": "誓杀"},
               {"op": "set", "id": "段正淳", "key": "location", "value": "雁门关"},  # 一日千里
               {"op": "set", "id": "段正淳", "key": "status", "value": "wounded"},
               {"op": "create", "id": "黑衣刺客", "type": "person", "attrs": {"location": "大理城"}}]
        applied, rejected = self.w.apply(ops, "lod1", ring)
        self.assertEqual(len(applied), 3)
        self.assertEqual(len(rejected), 2)
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

    def test_offscreen_creation_spreads_as_news(self):
        w = World.from_seed()
        op = {"op": "create", "id": "血刀客", "type": "person", "attrs": {"location": "大理城", "title": "西域狂僧"}}
        w.apply([op], "lod1", {"大理城"})
        w.record("血刀客现身大理", "大理城", [op], "lod1", 1)
        self.assertFalse(w.knowledge.knows("血刀客"))
        w.advance(12 * 3)
        w.sync()
        self.assertEqual(w.knowledge.view("血刀客")["title"], "西域狂僧")

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

    def test_hidden_things_are_backstage(self):
        w = World.from_seed()
        w.apply([GO("琅嬛福地")], "director")
        self.assertEqual(rag.build(w)["items"], [])
        self.assertTrue(any("北冥神功卷轴" in h for h in rag.backstage(w)["hidden"]))
        applied, _ = w.apply([{"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"}], "director")
        self.assertEqual(len(applied), 1)


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
