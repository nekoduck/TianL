"""
[INPUT]: 依赖 tianlong.world 全部基础设施（不接入 LLM）
[OUTPUT]: unittest 用例——历法、效果 DSL 权限、规则裁决、消息延迟传播、认知/真相分离、LOD 污染判定、存读档
[POS]: tests 的状态层验证，证明"系统代码管状态"在没有大模型时独立成立
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import tempfile
import unittest
from pathlib import Path

from tianlong.world import lod, rag, rules
from tianlong.world.clock import Clock
from tianlong.world.world import World


def act(world, verb, target=None):
    out = rules.resolve(world, {"verb": verb, "target": target})
    applied, rejected = world.apply(out["effects"], "rules")
    assert not rejected, rejected
    if out["event"]:
        world.record(out["event"]["summary"], world.here, applied, "rules", out["event"]["weight"])
    span = world.advance(out["cost"])
    world.sync()
    return out, span


class ClockTest(unittest.TestCase):
    def test_label_and_crossing(self):
        c = Clock(724)
        self.assertEqual(c.label(), "元祐七年三月初一 辰时")
        self.assertEqual(c.advance(12 * 30), (30, 1))
        self.assertEqual(Clock(12 * 360 * 3).label(), "绍圣元年正月初一 子时")
        self.assertEqual(Clock().label(19), "元祐七年正月二十")


class EffectsTest(unittest.TestCase):
    def setUp(self):
        self.w = World.from_seed("测试")

    def test_player_channel_routes_to_blackboard(self):
        self.w.apply([{"op": "add", "id": "player", "key": "hp", "value": -500}], "rules")
        self.assertEqual(self.w.player["hp"], 1)  # 主角在规则层不死

    def test_lod1_cannot_kill_or_teleport(self):
        _, ring = lod.lod1_scope(self.w)
        ops = [{"op": "set", "id": "段正淳", "key": "status", "value": "dead"},
               {"op": "set", "id": "段正淳", "key": "location", "value": "雁门关"},
               {"op": "set", "id": "段正淳", "key": "location", "value": "万劫谷"}]
        applied, rejected = self.w.apply(ops, "lod1", ring)
        self.assertEqual(len(rejected), 2)
        self.assertEqual(self.w.graph.get("段正淳", "location"), "万劫谷")

    def test_chronicle_scoped_and_no_player(self):
        ops = [{"op": "set", "id": "玄慈", "key": "status", "value": "dead"},
               {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},
               {"op": "add", "id": "player", "key": "power", "value": 99}]
        applied, rejected = self.w.apply(ops, "chronicle", {"乔峰", "杏子林"})
        self.assertEqual([op["id"] for op in applied], ["乔峰"])
        self.assertEqual(len(rejected), 2)

    def test_garbage_rejected(self):
        _, rejected = self.w.apply([{"op": "rm"}, "x", {"op": "set", "id": "无此人", "key": "a", "value": 1}], "canon")
        self.assertEqual(len(rejected), 3)


class RulesTest(unittest.TestCase):
    def test_langhuan_questline(self):
        w = World.from_seed()
        act(w, "go", "琅嬛福地")
        self.assertEqual(w.here, "琅嬛福地")
        self.assertNotIn("北冥神功卷轴", rules.scene(w)["items"])
        act(w, "examine", "蒲团")
        self.assertIn("北冥神功卷轴", rules.scene(w)["items"])
        act(w, "take", "北冥神功卷轴")
        act(w, "study", "北冥神功卷轴")
        self.assertIn("北冥神功", w.player["skills"])
        self.assertEqual(w.player["power"], 40)
        self.assertNotIn("study", {a["verb"] for a in rules.legal_actions(w)})

    def test_illegal_intent_changes_nothing(self):
        w = World.from_seed()
        out = rules.resolve(w, {"verb": "fight", "target": "乔峰"})  # 乔峰远在无锡
        self.assertEqual((out["effects"], out["cost"]), ([], 0))

    def test_fight_is_reproducible(self):
        a, b = World.from_seed(), World.from_seed()
        self.assertEqual(rules.resolve(a, {"verb": "fight", "target": "左子穆"}),
                         rules.resolve(b, {"verb": "fight", "target": "左子穆"}))


class PropagationTest(unittest.TestCase):
    def test_news_delay_follows_road_distance(self):
        w = World.from_seed()
        dist = w.graph.distances(w.here)["聚贤庄"]  # 剑湖宫→大理城→小镜湖→聚贤庄 = 21 日
        self.assertEqual(dist, 21)
        w.apply([{"op": "set", "id": "游骥", "key": "status", "value": "dead"}], "canon")
        w.record("游骥身亡", "聚贤庄", [{"op": "set", "id": "游骥", "key": "status", "value": "dead"}], "canon", 1)
        self.assertEqual(w.knowledge.view("游骥")["status"], "alive")  # 真相已变，认知未变
        w.advance(12 * (dist - 1))
        self.assertEqual(w.sync(), [])
        w.advance(12)
        self.assertEqual([e["summary"] for e in w.sync()], ["游骥身亡"])
        self.assertEqual(w.knowledge.view("游骥")["status"], "dead")

    def test_weight_speeds_news_and_observation_overrides(self):
        w = World.from_seed()
        w.apply([{"op": "set", "id": "段正淳", "key": "location", "value": "万劫谷"}], "canon")
        w.record("段正淳出城", "大理城", [], "canon", 2)
        w.advance(12)  # 一日 × 分量 2 → 覆盖 2 日路程以内；大理城距此 3 日
        self.assertEqual(w.sync(), [])
        self.assertEqual(w.knowledge.view("段正淳")["location"], "大理城")
        act(w, "go", "大理城")  # 亲眼所见：段正淳不在城中
        self.assertIsNone(w.knowledge.view("段正淳")["location"])

    def test_secrets_never_reach_rag(self):
        w = World.from_seed()
        pack = rag.build(w)
        text = str(pack)
        self.assertIn("段誉", text)
        self.assertNotIn("生父", text)  # 段延庆—段誉 生父 为 secret 边


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
        w.graph.set("阿朱", "power", 0)  # 保证击伤
        act(w, "fight", "阿朱")
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
        act(w, "go", "琅嬛福地")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            w.save(path)
            v = World.load(path)
        self.assertEqual(v.dump(), w.dump())


if __name__ == "__main__":
    unittest.main()
