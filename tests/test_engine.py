"""
[INPUT]: 依赖 tianlong.engine 的 Game，tianlong.world 的 World；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——离线全回合、剧情后果与自由选项跨回合延续、跋涉时日由道路结算、新造实体被驳回并回告编剧、史官改写、原著按距离延迟送达
[POS]: tests 的主循环验证，证明 LLM 编织剧情与选项、基础设施掌管地理器物并负责记住与校准
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


def director(**kw):
    return {"说书人与导演": {"beats": ["甲"], "elapsed": 1, "options": ["一", "二", "三"], "memory": "记", **kw}}


class OfflineLoopTest(unittest.TestCase):
    def test_full_loop_offline(self):
        game = Game(World.from_seed("离线"))
        turn = game.open()
        self.assertEqual(len(turn["options"]), 3)
        self.assertTrue(turn["text"])
        turn = game.act("去大理城看看")
        self.assertEqual(turn["place"], "大理城")
        self.assertEqual(turn["time"], "元祐七年三月初四 辰时")  # 3 日路程

    def test_month_passes_and_canon_news_arrives(self):
        game = Game(World.from_seed())
        w = game.world
        w.clock.tick = 180 * 12 - 1  # 五月末，杏子林之变（day 150）早已到期，但远在 LOD2 等待月级刷新
        game.act("歇息")  # 跨入六月 → LOD2 结算
        self.assertIn("杏子林之变", w.done)
        self.assertEqual(w.knowledge.view("乔峰")["faction"], "丐帮")  # 杏子林距此 30 日，weight 2 → 15 日后才知
        w.advance(12 * 14)
        self.assertEqual(w.sync(), [])
        w.advance(12)
        self.assertIn("乔峰", w.sync()[0]["summary"])
        self.assertIsNone(w.knowledge.view("乔峰")["faction"])


class DirectorTest(unittest.TestCase):
    def test_plot_and_free_options_persist_across_turns(self):
        llm = StubLLM(director(effects=[
            {"op": "link", "src": "段誉", "dst": "player", "rel": "结为知交"},
            {"op": "set", "id": "左子穆", "key": "mood", "value": "疑心大起"}],
            options=["替段誉挡下一剑", "偷看钟灵的布囊", "向左子穆讨教剑法"],
            event={"summary": "无量剑比剑被一名外客搅乱", "weight": 1}))
        game = Game(World.from_seed(), llm)
        turn = game.act("替段誉解围")
        self.assertEqual(turn["options"], ["替段誉挡下一剑", "偷看钟灵的布囊", "向左子穆讨教剑法"])  # 选项由 LLM 自由拟定
        llm.replies = director()
        game.act("1")  # 选项即原话，交回导演
        self.assertIn("【主角此刻】替段誉挡下一剑", llm.writer_prompts[-1])
        self.assertIn("段誉→你：结为知交", llm.writer_prompts[-1])  # 上一回合的剧情后果，依然在
        self.assertEqual(game.world.graph.get("左子穆", "mood"), "疑心大起")
        self.assertEqual(game.world.truth.events[0]["summary"], "无量剑比剑被一名外客搅乱")

    def test_journey_time_from_roads_not_llm(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "少林寺"}],
                               elapsed=1))
        game = Game(World.from_seed(), llm)
        turn = game.act("直奔少林寺")
        self.assertEqual(turn["place"], "少林寺")
        self.assertEqual(game.world.clock.day, 60 + 23)  # 剑湖宫→大理城→小镜湖→聚贤庄→少林寺

    def test_invented_entities_rejected_and_told_to_writer(self):
        llm = StubLLM(director(effects=[
            {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},
            {"op": "create", "id": "神秘剑客", "type": "person", "attrs": {}},
            {"op": "set", "id": "player", "key": "location", "value": "后山禁地"}]))
        game = Game(World.from_seed(), llm)
        turn = game.act("隔空一掌打死乔峰")
        self.assertEqual(game.world.graph.get("乔峰", "status"), "alive")
        self.assertFalse(game.world.graph.has("神秘剑客"))
        self.assertEqual(game.world.here, "剑湖宫")
        self.assertEqual(len(turn["void"]), 3)
        self.assertIn("未能成立", llm.writer_prompts[-1])

    def test_chronicler_rewrites_within_reach(self):
        w = World.from_seed()
        w.apply([{"op": "set", "id": "乔峰", "key": "status", "value": "wounded"}], "canon")
        w.taint.add("乔峰")
        llm = StubLLM({**director(), "史官": {"happens": True, "summary": "改写", "effects": [
            {"op": "set", "id": "乔峰", "key": "title", "value": "落魄英雄"},
            {"op": "link", "src": "乔峰", "dst": "player", "rel": "迁怒"},
            {"op": "set", "id": "段誉", "key": "status", "value": "dead"},
            {"op": "add", "id": "player", "key": "power", "value": 100}]}})
        game = Game(w, llm)
        w.clock.tick = 180 * 12 - 1  # 下一回合跨月，触发 LOD2
        game.act("歇息")
        self.assertEqual(w.graph.get("乔峰", "title"), "落魄英雄")
        self.assertTrue(any(e["rel"] == "迁怒" for e in w.graph.relations("乔峰")))
        self.assertEqual(w.graph.get("段誉", "status"), "alive")
        self.assertLess(w.player["power"], 100)


if __name__ == "__main__":
    unittest.main()
