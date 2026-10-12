"""
[INPUT]: 依赖 tianlong.world 的 pacing / effects / lod / rag / situation 与 data/canon 原著世界，tianlong.engine 的 Game；
         复用 tests/test_adjudicate 的 plan / judge 与 tests/test_engine 的 StubLLM / director
[OUTPUT]: unittest 用例——两份实录里「剧情打转」的病灶逐条转成离线验收(v3 P1)：
          同一主题近四回合有三回合即在后台写明不得再起(隔一回合又来也算)、同一个人一再对主角说同一种话即提示换个推进方式、在一处僵持而局面不动即逼导演推进、
          某人对主角的看法五回合内不改写(同回合以后写为准)、情绪写在拍的 mood 里只给编剧不入账、伏笔至多两条且身体不作伏笔、
          纠缠者的场外原著前提已破即作罢且场外动不了他、前提已破的原著近事在后台明标不得进台词、台词说出尚未发生的原著即违例
[POS]: tests 的阻尼与纠缠者验证——v3 方案 P1-1(慢变量与阻尼)、P1-2(原著与纠缠者、台词事实出处)的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tests.test_engine import StubLLM, director
from tianlong.engine import Game
from tianlong.world import effects, lod, pacing, rag
from tianlong.world.world import World

HOSTAGE = "神农帮留钟灵下毒逼援"
LINK = lambda rel: {"op": "link", "src": "段誉", "dst": "player", "rel": rel}


def beat(text, who="左子穆", to="player"):
    return {"who": who, "to": to, "text": text}


class PacingTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_a_theme_three_turns_running_is_damped(self):
        w = self.w
        for _ in range(2):
            pacing.record(w, [beat("左子穆横剑拦住你：「谁也不准离开！」")], changed=False)
        self.assertEqual(pacing.advise(w), [])                                         # 两回合还不算打转
        pacing.record(w, [beat("左子穆喝止道：「不许走！」")], changed=False)
        advice = "\n".join(pacing.advise(w))
        self.assertIn("「拦阻」近4回合里已有3回合", advice)
        self.assertIn("左子穆近来一再对主角拦阻", advice)
        self.assertIn("僵持3回合", advice)                                              # 25 回实录：困在练武厅
        pacing.record(w, [beat("左子穆收剑入鞘，放你出厅")], changed=True)
        self.assertNotIn("僵持", "".join(pacing.advise(w)))                            # 局面一动，僵持即解
        pacing.record(w, [beat("左子穆抚须而笑")], changed=True)
        self.assertEqual(pacing.advise(w), [])                                         # 此题淡出窗口，阻尼即解

    def test_feelings_toward_the_player_settle_slowly(self):
        w, me = self.w, self.w.player
        me.set("turn", 1)
        effects.apply(w, [LINK("怨恨")], "director")
        effects.apply(w, [LINK("感激")], "director")                                   # 同一回合里改口：以后写为准
        me.set("turn", 3)
        _, rejected = effects.apply(w, [LINK("信任")], "director")
        self.assertIn("五回合内不改", rejected[0][1].replace("5", "五"))
        me.set("turn", 6)
        effects.apply(w, [LINK("信任")], "director")
        self.assertEqual([e["rel"] for e in w.graph.edges if e["src"] == "段誉" and e["dst"] == "player"], ["信任"])

    def test_mood_reaches_the_writer_but_not_the_ledger(self):
        r = judge(self.w, plan(("段誉", "段誉连连摇手", [], "player")))
        self.assertEqual(r.applied, [])
        game = Game(World.create("测"), StubLLM(director(beats=[{"who": "段誉", "text": "段誉连连摇手", "mood": "惶急"}])))
        game.act("看")
        self.assertIn("连连摇手〔惶急〕", game.llm.writer_prompts[-1])

    def test_hooks_are_scarce_and_never_about_the_body(self):
        w = World.create("测")
        hook = lambda text: "正文\n===\n梗概：记\n伏笔：" + text + "｜期限：3\n传言：无"
        game = Game(w, StubLLM({**director(), "小说家": hook("你肩头的伤口隐隐作痛")}))
        game.act("看")
        self.assertEqual(w.player["hooks"], [])                                       # 身体归规则，不作悬念
        for text in ("梁上有人窥伺", "门外马蹄声近", "袖中书信未拆"):
            game.llm.replies["小说家"] = hook(text)
            game.act("看")
        self.assertEqual([h["text"] for h in w.player["hooks"]], ["门外马蹄声近", "袖中书信未拆"])


class EntangledTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.graph.link("钟灵", "player", "随行")
        self.ev = next(ev for ev in self.w.canon if ev["id"] == HOSTAGE)

    def test_offstage_canon_of_a_companion_is_dropped_not_rewritten(self):
        path, _ = lod.verdict(self.w, self.ev, 1)
        self.assertEqual(path, "skip")                                                 # 不交史官：同行者的行止只听导演
        _, rejected = effects.apply(self.w, [{"op": "set", "id": "钟灵", "key": "location", "value": "无量山"}], "chronicle")
        self.assertIn("场外动不了", rejected[0][1])

    def test_broken_canon_is_background_only(self):
        gm = rag.backstage(self.w, upcoming=[(self.ev, 1)])
        self.assertIn("本局已不成立", gm["upcoming"][0])
        self.assertIn("不得写进任何人的台词", gm["upcoming"][0])

    def test_dialogue_may_not_foretell_the_canon(self):
        w = World.create("测")
        r = judge(w, plan(("马五德", "马五德低声道：「听说司空玄要扣下钟灵做人质。」", [], "player")))
        self.assertIn("foretold", [f.kind for f in r.hard])
        r = judge(w, plan(("马五德", "马五德低声道：「神农帮来者不善。」", [], "player")))
        self.assertNotIn("foretold", [f.kind for f in r.hard])                         # 风声预兆可以


if __name__ == "__main__":
    unittest.main()
