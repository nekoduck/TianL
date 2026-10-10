"""
[INPUT]: 依赖 tianlong.engine 的 Game，tianlong.world 的 World；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——离线全回合、导演的创造跨回合延续、跋涉时日由道路结算、不成立之事告知编剧、史官改写、原著按距离延迟送达
[POS]: tests 的主循环验证，证明 LLM 自由创造、基础设施负责记住与校准
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
    return {"主宰": {"beats": ["甲"], "elapsed": 1, "options": ["一", "二", "三"], "memory": "记", **kw}}


class OfflineLoopTest(unittest.TestCase):
    def test_full_loop_offline(self):
        game = Game(World.from_seed("离线"))
        turn = game.open()
        self.assertEqual(len(turn["options"]), 3)
        self.assertTrue(turn["text"])
        turn = game.act("去琅嬛福地看看")
        self.assertEqual(turn["place"], "琅嬛福地")
        self.assertEqual(turn["time"], "元祐七年三月初二 辰时")  # 1 日路程

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
    def test_creation_persists_across_turns(self):
        llm = StubLLM(director(effects=[
            {"op": "create", "id": "哑仆", "type": "person", "attrs": {"title": "剑湖宫哑仆", "persona": "沉默"}},
            {"op": "link", "src": "哑仆", "dst": "player", "rel": "暗中跟随"}],
            event={"summary": "剑湖宫来了个哑仆", "weight": 1}))
        game = Game(World.from_seed(), llm)
        game.act("四处打量")
        llm.replies = director()
        game.act("继续")
        self.assertIn("哑仆｜剑湖宫哑仆", llm.writer_prompts[-1])  # 下一回合的上下文里，它依然在
        self.assertIn("哑仆→你：暗中跟随", llm.writer_prompts[-1])
        self.assertEqual(game.world.truth.events[0]["summary"], "剑湖宫来了个哑仆")

    def test_journey_time_from_roads_not_llm(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "少林寺"}],
                               elapsed=1))
        game = Game(World.from_seed(), llm)
        turn = game.act("直奔少林寺")
        self.assertEqual(turn["place"], "少林寺")
        self.assertEqual(game.world.clock.day, 60 + 23)  # 剑湖宫→大理城→小镜湖→聚贤庄→少林寺

    def test_impossible_is_told_to_writer(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "乔峰", "key": "status", "value": "dead"}]))
        game = Game(World.from_seed(), llm)
        turn = game.act("隔空一掌打死乔峰")
        self.assertEqual(game.world.graph.get("乔峰", "status"), "alive")
        self.assertIn("未能成立", llm.writer_prompts[-1])
        self.assertEqual(len(turn["void"]), 1)

    def test_chronicler_rewrites_within_reach(self):
        w = World.from_seed()
        w.apply([{"op": "set", "id": "乔峰", "key": "status", "value": "wounded"}], "canon")
        w.taint.add("乔峰")
        llm = StubLLM({**director(), "史官": {"happens": True, "summary": "改写", "effects": [
            {"op": "set", "id": "乔峰", "key": "title", "value": "落魄英雄"},
            {"op": "create", "id": "全冠清", "type": "person", "attrs": {"location": "杏子林", "title": "丐帮舵主"}},
            {"op": "set", "id": "段誉", "key": "status", "value": "dead"},
            {"op": "add", "id": "player", "key": "power", "value": 100}]}})
        game = Game(w, llm)
        w.clock.tick = 180 * 12 - 1  # 下一回合跨月，触发 LOD2
        game.act("歇息")
        self.assertEqual(w.graph.get("乔峰", "title"), "落魄英雄")
        self.assertEqual(w.graph.get("全冠清", "title"), "丐帮舵主")
        self.assertEqual(w.graph.get("段誉", "status"), "alive")
        self.assertLess(w.player["power"], 100)


if __name__ == "__main__":
    unittest.main()
