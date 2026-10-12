"""
[INPUT]: 依赖 tianlong.world 的 perspective / adjudicate / menu / effects 与 data/canon 原著世界，tianlong.engine 的 Game；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——43 回对局(王侠墨)里「主角都没认识钟灵，开口就是钟姑娘」逐条转成离线验收：
          开局只识出身带来的人与当众主持剑会的掌门、无名之辈不在开局常识里、叫出不知其名之人(全名或姓+称谓)即违例、
          NPC 不知主角姓名却叫「王兄」即违例、自报家门与当面点名让在场者听来名字、编剧从主角视角看世界(只剩外貌叫法、不露身份)、
          交编剧之前与成文之后确定性地把漏出的名字换成叫法与泛称(编剧熟读原著，名字可能是它自己带来的)、编剧与玩家用的叫法落得回实体
[POS]: tests 的认知视角验证——v3 方案 P0-2「视角即上下文」的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tests.test_engine import StubLLM, WRITER, director
from tianlong.engine import Game
from tianlong.world import effects, perspective, rag
from tianlong.world.world import World


def kinds(r):
    return [f.kind for f in r.hard if f.kind == "name"]


class PerspectiveTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("王侠墨")

    def test_the_player_starts_knowing_only_whom_his_origin_brings(self):
        w = self.w
        self.assertTrue(perspective.knows(w, "player", "马五德") and perspective.knows(w, "马五德", "player"))
        self.assertTrue(perspective.knows(w, "player", "左子穆"))                   # 剑会主人，当众可知
        self.assertFalse(perspective.knows(w, "player", "钟灵"))
        self.assertFalse(perspective.knows(w, "段誉", "player"))
        self.assertFalse(w.knowledge.knows("木婉清"))                                # 无名之辈的下落不是江湖常识
        self.assertTrue(w.knowledge.knows("钟万仇"))                                 # 万劫谷主之名倒是听过
        self.assertEqual(perspective.handle(w, "钟灵"), "大眼圆脸的少女")

    def test_calling_a_stranger_by_name_is_a_violation(self):
        r = judge(self.w, plan(("player", "你高声唤道：「段公子、钟姑娘，且慢行！」", [])))
        self.assertEqual(sorted(f.entity for f in r.hard if f.kind == "name"), ["段誉", "钟灵"])
        r = judge(self.w, plan(("段誉", "段誉回首喜道：「王兄！快随我们走。」", [], "player")))
        self.assertEqual([f.entity for f in r.hard if f.kind == "name"], ["player"])

    def test_names_are_heard_when_given(self):
        w = self.w
        r = judge(w, plan(("钟灵", "钟灵笑道：「我叫钟灵，你呢？」", [], "player"),
                          ("player", "你拱手道：「在下王侠墨，钟姑娘好。」", [])))
        self.assertEqual(kinds(r), [])                                               # 先听她自报，再叫她钟姑娘
        self.assertTrue(perspective.knows(w, "player", "钟灵") and perspective.knows(w, "钟灵", "player"))
        w.graph.link("段誉", "左子穆", "相识")
        r = judge(w, plan(("段誉", "段誉作揖道：「左掌门息怒。」", [])))
        self.assertTrue(perspective.knows(w, "褚师弟", "左子穆"))                   # 当面叫出，在场者都听见了

    def test_the_writer_sees_the_world_through_the_players_eyes(self):
        w = self.w
        pack = perspective.veil(w, rag.build(w))
        names = [p["name"] for p in pack["people"]]
        self.assertIn("大眼圆脸的少女", names)
        self.assertNotIn("钟灵", names)
        self.assertNotIn("钟灵", " ".join(pack["relations"]))
        girl = next(p for p in pack["people"] if p["name"] == "大眼圆脸的少女")
        self.assertEqual((girl["title"], girl["faction"]), ("来历不明", "门派不明"))
        self.assertEqual(perspective.mask(w, "钟灵放出闪电貂，咬伤龚光杰"), "大眼圆脸的少女放出闪电貂，咬伤无量剑东宗的少年")
        self.assertEqual(perspective.mask(w, "段誉喜道：「王兄！钟姑娘也在。」", "段誉"), "青衫少年喜道：「兄台！姑娘也在。」")
        self.assertEqual(perspective.mask(w, "乔峰名满天下"), "乔峰名满天下")      # 久仰其名、人不在眼前：照叫
        self.assertEqual(perspective.mask(w, "得胜的东宗少年龚光杰勃然变色"), "得胜的东宗少年勃然变色")  # 已有叫法作同位语：名字直接去掉

    def test_handles_resolve_back_to_people(self):
        self.assertEqual(effects.resolve(self.w, "大眼圆脸的少女"), "钟灵")
        game = Game(self.w, StubLLM({**director(beats=["钟灵在梁上娇笑：「好不要脸的大人！」"]),
                                     "小说家": "梁上钟灵格格娇笑\n===\n梗概：梁上少女讥笑\n选项：\n1. 与梁上少女搭话｜对象：大眼圆脸的少女\n伏笔：无\n传言：无"}))
        turn = game.act("抬头张望")
        self.assertIn("与梁上少女搭话", turn["options"])
        self.assertEqual(game.menu["与梁上少女搭话"], ["钟灵"])                      # 叫法落回实体：下回合授意不失准
        self.assertNotIn("钟灵", turn["text"])                                       # 编剧熟读原著、自己写出的名字，成文也过一遍主角的视角
        prompt = game.llm.writer_prompts[-1]
        self.assertNotIn("钟灵", prompt.split("【近日传闻】")[0])                    # 编剧眼前没有她的名字


if __name__ == "__main__":
    unittest.main()
