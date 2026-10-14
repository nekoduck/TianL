"""
[INPUT]: 依赖 tianlong.world 的 pacing / effects / lod / rag / situation 与 data/canon 原著世界，tianlong.engine 的 Game；
         复用 tests/test_adjudicate 的 plan / judge 与 tests/test_engine 的 StubLLM / director
[OUTPUT]: unittest 用例——两份实录里「剧情打转」的病灶逐条转成离线验收(v3 P1)：
          同一主题近四回合有三回合即在后台写明不得再起(隔一回合又来也算)、同一个人一再对主角说同一种话即提示换个推进方式(僵持归 story/scene 的场上限)、
          某人对主角的看法由恩怨账折叠(态度不立边、恩怨并存、按光阴衰减不冻结、一件事改一级、同一件事当天重写不累加)、情绪写在拍的 mood 里只给编剧不入账、伏笔至多两条且身体不作伏笔、
          纠缠者的场外原著前提已破即作罢且场外动不了他、前提已破的原著近事在后台明标不得进台词、台词说出尚未发生的原著即违例；
          幕间省略(无人相逼才许光阴跳过——v5 悬而未决而局面平静也可、「一夜」醒在辰时、编剧写出那段空白；本幕刚被打断、拦阻追杀、受制于人则不许)、研习至少一顿饭、局面平静时后台提示可以跳
[POS]: tests 的阻尼与纠缠者验证——v3 方案 P1-1(慢变量与阻尼)、P1-2(原著与纠缠者、台词事实出处)的离线证据，及时长「回回片刻」的修正(戏内光阴与幕间省略分开)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tests.test_engine import StubLLM, director
from tianlong.engine import Game
from tianlong.world import effects, lod, pacing, rag
from tianlong.world.clock import PER_DAY
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
        self.assertNotIn("僵持", advice)                                               # 僵持归场的上限(story/scene)，不在此提示
        pacing.record(w, [beat("左子穆收剑入鞘，放你出厅")], changed=True)
        pacing.record(w, [beat("左子穆抚须而笑")], changed=True)
        self.assertEqual(pacing.advise(w), [])                                         # 此题淡出窗口，阻尼即解

    def test_feelings_toward_the_player_are_folded_from_events(self):
        w, me = self.w, self.w.player
        stance = lambda: rag.build(w)["people"][[p["name"] for p in rag.build(w)["people"]].index("段誉")]["toward_you"]
        me.set("turn", 1)
        effects.apply(w, [LINK("怨恨")], "director")
        effects.apply(w, [LINK("感激")], "director")                                   # 不覆盖：恩怨两本账并存
        self.assertEqual([e for e in w.graph.edges if e["src"] == "段誉" and e["dst"] == "player"], [])  # 态度不立边
        self.assertIn("感激中带着戒备", stance()[-1])
        w.clock.tick += 12 * PER_DAY                                                    # 十二日过去(v5 按光阴衰减)：怨比恩消得慢
        self.assertTrue(stance()[-1].startswith("对你戒备") or stance()[-1].startswith("对你相识"))
        effects.apply(w, [LINK("敬重")], "director")                                    # 一件事改一级，不冻结
        self.assertTrue(stance()[-1].startswith("对你友善"), stance())
        effects.apply(w, [LINK("敬重")], "director")                                    # 同一件事当天重写：不是又一件事
        self.assertTrue(stance()[-1].startswith("对你友善"), stance())
        for _ in range(3):
            w.clock.tick += PER_DAY
            effects.apply(w, [LINK("敬重")], "director")                                # 日复一日，恩积得够深才托付
        self.assertTrue(stance()[-1].startswith("对你托付"), stance())

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


def scene(state="resolved", cut="半日", pace="片刻", beats=None, ops=()):
    return StubLLM(director(pace=pace, cut=cut, question={"ask": "问", "state": state},
                            beats=beats or [{"who": "player", "text": "你向众人拱手作别", "ops": list(ops)}]))


class SceneCutTest(unittest.TestCase):
    """25 回实录：导演回回取「片刻」，25 回合只过了半日——戏内光阴本就是片刻，缺的是幕与幕之间的空白。"""

    def play(self, llm):
        game = Game(World.create("测"), llm)
        tick = game.world.clock.tick
        game.act("作别")
        return game, game.world.clock.tick - tick

    def test_a_settled_scene_may_skip_ahead(self):
        game, spent = self.play(scene())
        self.assertEqual(spent, 15 + 360)                                               # 片刻 + 半日
        self.assertIn("光阴跳过半日", game.llm.writer_prompts[-1])                       # 编剧写出这段空白

    def test_a_night_cut_wakes_at_dawn(self):
        game, _ = self.play(scene(cut="一夜"))
        self.assertTrue(game.world.clock.label().endswith("辰时"))

    def test_no_skip_while_the_scene_is_unsettled(self):
        for llm in (scene(state="interrupted", beats=[{"who": "左子穆", "text": "左子穆喝道：「且慢！」"}]),  # 本幕刚被打断
                    scene(beats=[{"who": "左子穆", "to": "player", "text": "左子穆横剑拦住你：「不许走！」"}])):  # 仍有人拦阻
            _, spent = self.play(llm)
            self.assertEqual(spent, 15)
        _, spent = self.play(scene(state="open"))                                     # 悬而未决而局面平静(v5)：可以隔着半日再续
        self.assertEqual(spent, 15 + 360)
        w = World.create("测")
        w.graph.link("左子穆", "player", "扣押")
        self.assertEqual(pacing.calm(w, "resolved"), "主角受制于人")

    def test_study_takes_a_sitting_whatever_the_wording(self):
        sword = [{"op": "study", "id": "player", "value": "无量剑法"}]
        game = Game(World.create("测"), scene(cut="无", ops=sword))
        tick = game.world.clock.tick
        game.act("向人讨教无量剑法")
        self.assertGreaterEqual(game.world.clock.tick - tick, 45)                     # 片刻练不成功
        _, spent = self.play(scene(cut="无", ops=sword))
        self.assertEqual(spent, 15)                                                   # 玩家只是作别：替他练的剑不演，也不主张时长(v5)

    def test_the_director_is_nudged_to_cut_when_nothing_presses(self):
        w = World.create("测")
        self.assertIn("cut", rag.backstage(w, tempo=["resolved"])["tempo"])
        self.assertNotIn("cut", rag.backstage(w, tempo=["open"])["tempo"])


class EntangledTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.graph.link("钟灵", "player", "随行")
        self.ev = next(ev for ev in self.w.canon if ev["id"] == HOSTAGE)

    def test_offstage_canon_of_a_companion_is_dropped_not_rewritten(self):
        path, _ = lod.verdict(self.w, self.ev, 1)
        self.assertEqual(path, "skip")                                                 # 不交场外编剧：同行者的行止只听导演
        _, rejected = effects.apply(self.w, [{"op": "set", "id": "钟灵", "key": "location", "value": "无量山"}], "derived")
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
