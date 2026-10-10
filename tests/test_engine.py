"""
[INPUT]: 依赖 tianlong.engine 的 Game，tianlong.world 的 World；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——离线全回合循环、LLM 越权提案被框住、自由输入解析
[POS]: tests 的主循环验证，证明 narrative 层无论输出什么，world 层的真相都不被污染
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import unittest

from tianlong.engine import Game
from tianlong.narrative.llm import LLMError
from tianlong.world.world import World

logging.disable(logging.WARNING)  # 兜底告警在测试中属预期


class StubLLM:
    """按 system 提示词关键词返回预设 JSON；用来扮演"不守规矩"的大模型。"""

    def __init__(self, replies: dict):
        self.replies, self.tokens = replies, 0

    def json(self, system, user, max_tokens=0):
        for key, reply in self.replies.items():
            if key in system:
                return reply
        raise LLMError("无预设")

    def text(self, system, user, max_tokens=0):
        return "（正文）"


class OfflineLoopTest(unittest.TestCase):
    def test_full_loop_offline(self):
        game = Game(World.from_seed("离线"))
        turn = game.open()
        self.assertEqual(len(turn["options"]), 3)
        self.assertTrue(turn["text"])
        turn = game.act("去琅嬛福地看看")
        self.assertEqual(turn["place"], "琅嬛福地")
        game.act("翻看蒲团")
        game.act("拾取北冥神功卷轴")
        self.assertIn("北冥神功卷轴", game.world.player["inventory"])

    def test_month_passes_and_canon_news_arrives(self):
        game = Game(World.from_seed())
        w = game.world
        w.clock.tick = 180 * 12 - 3  # 五月末，杏子林之变（day 150）早已到期，但远在 LOD2 等待月级刷新
        game.act("歇息")  # 跨入六月 → LOD2 结算
        self.assertIn("杏子林之变", w.done)
        self.assertEqual(w.knowledge.view("乔峰")["faction"], "丐帮")  # 杏子林距此 30 日，weight 2 → 15 日后才知
        w.advance(12 * 14)
        self.assertEqual(w.sync(), [])
        w.advance(12)
        self.assertIn("乔峰", w.sync()[0]["summary"])
        self.assertIsNone(w.knowledge.view("乔峰")["faction"])


class GuardrailTest(unittest.TestCase):
    def test_director_cannot_invent_options(self):
        llm = StubLLM({"导演": {"beats": ["甲"], "options": [{"i": 999, "label": "飞升成仙"}, {"i": 0, "label": "下山"}]}})
        turn = Game(World.from_seed(), llm).open()
        self.assertEqual(len(turn["options"]), 3)
        self.assertEqual(turn["options"][0], "下山")
        self.assertNotIn("飞升成仙", turn["options"])

    def test_chronicler_overreach_is_filtered(self):
        w = World.from_seed()
        w.apply([{"op": "set", "id": "乔峰", "key": "status", "value": "wounded"}], "rules")  # 玩家污染乔峰
        llm = StubLLM({"史官": {"happens": True, "summary": "改写", "effects": [
            {"op": "set", "id": "乔峰", "key": "title", "value": "落魄英雄"},
            {"op": "set", "id": "段誉", "key": "status", "value": "dead"},
            {"op": "add", "id": "player", "key": "power", "value": 100}]}})
        game = Game(w, llm)
        w.clock.tick = 180 * 12 - 3  # 下一回合跨月，触发 LOD2
        game.act("歇息")
        self.assertEqual(w.graph.get("乔峰", "title"), "落魄英雄")
        self.assertEqual(w.graph.get("段誉", "status"), "alive")
        self.assertLess(w.player["power"], 100)

    def test_parser_maps_free_text_to_legal_action(self):
        llm = StubLLM({"解析器": {"i": 0, "manner": "大步流星"}})
        game = Game(World.from_seed(), llm)
        game.act("我要离开这里")
        self.assertEqual(game.world.here, "琅嬛福地")  # 序号 0 = 前往琅嬛福地


if __name__ == "__main__":
    unittest.main()
