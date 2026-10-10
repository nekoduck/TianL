"""
[INPUT]: 依赖 tianlong.engine 的 Game，tianlong.world 的 World 与 data/canon 原著世界；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——开场原著在主角眼前上演、远方原著按距离延迟传来、剧情后果与自由选项跨回合延续、
          跋涉时日由道路结算、新造实体被驳回并回告编剧、史官改写被扰动的大事
[POS]: tests 的主循环验证，证明 LLM 编织剧情与选项、基础设施掌管原著世界并负责记住与校准
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import unittest

from tianlong.engine import Game
from tianlong.narrative.llm import LLMError
from tianlong.world.world import World

logging.disable(logging.WARNING)  # 兜底告警在测试中属预期


class StubLLM:
    """按 system 提示词关键词返回预设 JSON；记录编剧收到的提示词。"""

    def __init__(self, replies: dict):
        self.replies, self.tokens, self.writer_prompts = replies, 0, []

    def json(self, system, user, max_tokens=0):
        for key, reply in self.replies.items():
            if key in system:
                return reply
        raise LLMError("无预设")

    def text(self, system, user, max_tokens=0):
        self.writer_prompts.append(user)
        return "（正文）"


def eve_of_month_after(world, day: int):
    """把时钟拨到 day 之后那个月末的最后一个时辰：下一回合必然跨月，触发 LOD2 节拍。"""
    world.clock.tick = (day // 30 + 1) * 30 * 12 - 1


def director(**kw):
    return {"说书人与导演": {"beats": ["甲"], "elapsed": 1, "options": ["一", "二", "三"], "memory": "记", **kw}}


class CanonLoopTest(unittest.TestCase):
    def test_opening_canon_unfolds_before_the_player(self):
        game = Game(World.create("离线"))
        turn = game.open()
        w = game.world
        self.assertEqual(len(turn["options"]), 3)
        self.assertIn("无量剑第四场比剑", w.done)
        self.assertEqual(w.graph.get("褚师弟", "status"), "wounded")
        self.assertIn("龚光杰刺伤褚师弟", "".join(turn["news"]))  # 亲历即知，作为本回合见闻送达

    def test_offline_travel_follows_roads(self):
        game = Game(World.create())
        turn = game.act("去剑湖宫")
        self.assertEqual(turn["place"], "剑湖宫")

    def test_distant_canon_arrives_as_delayed_news(self):
        game = Game(World.create())
        w = game.world
        far = next(e for e in w.canon if e["id"] == "鸠摩智押段誉抵姑苏")
        eve_of_month_after(w, far["day"])
        game.act("歇息")
        self.assertIn(far["id"], w.done)
        known = lambda: {w.truth.get(i)["summary"] for i in w.knowledge.known}
        self.assertNotIn(far["summary"], known())  # 姑苏远在百日之外
        w.advance(12 * w.graph.distances(w.here)[far["where"]])
        w.sync()
        self.assertIn(far["summary"], known())


class DirectorTest(unittest.TestCase):
    def test_plot_and_free_options_persist_across_turns(self):
        llm = StubLLM(director(effects=[
            {"op": "link", "src": "段誉", "dst": "player", "rel": "结为知交"},
            {"op": "set", "id": "左子穆", "key": "mood", "value": "疑心大起"}],
            options=["替段誉挡下一掌", "偷看钟灵的布囊", "向左子穆讨教剑法"],
            event={"summary": "无量剑比剑被一名外客搅乱", "weight": 1}))
        game = Game(World.create(), llm)
        turn = game.act("替段誉解围")
        self.assertEqual(turn["options"], ["替段誉挡下一掌", "偷看钟灵的布囊", "向左子穆讨教剑法"])
        llm.replies = director()
        game.act("1")  # 选项即原话，交回导演
        self.assertIn("【主角此刻】替段誉挡下一掌", llm.writer_prompts[-1])
        self.assertIn("段誉→你：结为知交", llm.writer_prompts[-1])
        self.assertEqual(game.world.graph.get("左子穆", "mood"), "疑心大起")
        self.assertIn("无量剑比剑被一名外客搅乱", [e["summary"] for e in game.world.truth.events])

    def test_journey_time_from_roads_not_llm(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "镇南王府"}]))
        game = Game(World.create(), llm)
        w = game.world
        start, ride = w.clock.day, w.graph.distances(w.here)["镇南王府"]
        turn = game.act("直奔镇南王府")
        self.assertEqual(turn["place"], "镇南王府")
        self.assertEqual((ride, w.clock.day), (2, start + ride))  # 步行 3 日，骑马 2 日；导演只估了 1 时辰

    def test_time_always_flows_when_the_player_acts(self):
        llm = StubLLM(director(elapsed=0))
        game = Game(World.create(), llm)
        tick = game.world.clock.tick
        game.act("与段誉闲谈")
        self.assertEqual(game.world.clock.tick, tick + 1)

    def test_invented_entities_rejected_and_told_to_writer(self):
        llm = StubLLM(director(effects=[
            {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},
            {"op": "create", "id": "神秘剑客", "type": "person", "attrs": {}},
            {"op": "set", "id": "player", "key": "location", "value": "后山禁地"}]))
        game = Game(World.create(), llm)
        turn = game.act("隔空一掌打死乔峰")
        self.assertEqual(game.world.graph.get("乔峰", "status"), "alive")
        self.assertFalse(game.world.graph.has("神秘剑客"))
        self.assertEqual(len(turn["void"]), 3)
        self.assertIn("未能成立", llm.writer_prompts[-1])

    def test_chronicler_rewrites_a_disturbed_major_event(self):
        w = World.create()
        ev = next(e for e in w.canon if e["id"] == "乔峰携阿朱赴聚贤庄")
        w.done.extend(e["id"] for e in w.canon if e["order"] < ev["order"])  # 前事已了
        w.graph.set("阿朱", "status", "dead")  # 主角早先改变了阿朱的命运
        llm = StubLLM({**director(), "史官": {"happens": True, "summary": "乔峰孤身闯庄", "effects": [
            {"op": "set", "id": "乔峰", "key": "mood", "value": "万念俱灰"},
            {"op": "set", "id": "段誉", "key": "status", "value": "dead"},
            {"op": "add", "id": "player", "key": "power", "value": 100}]}})
        game = Game(w, llm)
        eve_of_month_after(w, ev["day"])  # 聚贤庄远在 LOD2，待月级节拍
        game.act("歇息")
        self.assertEqual(w.graph.get("乔峰", "mood"), "万念俱灰")
        self.assertEqual(w.graph.get("段誉", "status"), "alive")  # 越出相关者
        self.assertLess(w.player["power"], 100)                  # 场外碰不到主角
        self.assertIn("乔峰孤身闯庄", [e["summary"] for e in w.truth.events])


if __name__ == "__main__":
    unittest.main()
