"""
[INPUT]: 依赖 tianlong.story 的 timing / canon / stakes / scene / brief / arc / choices，tianlong.world 的 World / menu / situation / body，
         tianlong.engine 的 Game；复用 tests/test_adjudicate 的 plan、tests/test_engine 的 StubLLM / director
[OUTPUT]: unittest 用例——v4 故事层「故事也有账」的离线验收：
          时间是后果(研习一回合可以入门、歇息主张半日、险境里不算歇、此后之举至少一顿饭、cut 可等到入夜或某个时限)；
          原著窗口(故事走到谷底时段誉此前的原著已了、相关者到位即拉起将至的原著、前提已破的旧事不挡路、导演演掉的原著按签名记作兑现、后台近事写「可随时上演」)；
          时限(导演立下、到期交场记一次即除)；场(跨回合保留问题与试过的路数、合场即开新场、演满上限要求收场)；
          场记(主干优先级、原著连占三场即不再拉)；主角线(秘籍到手即入局)；选项槽位(编剧标了尺度而没有此后即补一项、险境里不补、代价写全或不写)、主角的心思不归导演写(不入账也不返工)
[POS]: tests 的故事层验证——v4 方案第一部分(R1~R7)的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import plan
from tests.test_engine import StubLLM, director
from tianlong.engine import Game
from tianlong.story import arc, brief, canon, choices, scene, stakes, timing
from tianlong.world import menu
from tianlong.world.clock import PER_DAY, PER_SHICHEN
from tianlong.world.world import World

BOOK = "北冥神功卷轴"
VALLEY = "无量山·谷底"


def book_in_hand(w):
    w.graph.set(BOOK, "hidden", False)
    w.graph.set(BOOK, "holder", "player")
    w.graph.set(BOOK, "location", None)
    w.player.push("inventory", BOOK)


class TimingTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_rules_claim_their_time(self):
        w = self.w
        book_in_hand(w)
        study = plan(("player", "你展开帛卷", [{"op": "study", "id": "player", "value": BOOK}]))
        self.assertEqual(timing.claim(w, study)[0], 60)                                # 初窥一个时辰：一回合可以入门
        self.assertEqual(timing.claim(w, plan(("player", "你寻了处僻静地方歇息", [])))[0], 240)
        self.assertEqual(timing.claim(w, plan(("player", "你歇息片刻", [])))[0], 0)       # 片刻的喘息不是养伤
        self.assertEqual(timing.claim(w, plan(("player", "你上路", [])), scale="此后")[0], timing.LATER)
        w.graph.link("左子穆", "player", "扣押")
        self.assertEqual(timing.claim(w, plan(("player", "你闭目歇息", [])))[0], 0)       # 受制于人，没有歇息

    def test_a_cut_can_wait_until_a_moment(self):
        w = self.w                                                                     # 开局辰时
        self.assertEqual(timing.cut_minutes(w, {"until": "入夜"}), 5 * PER_SHICHEN)     # 辰 → 酉
        self.assertEqual(timing.cut_minutes(w, "天明"), 11 * PER_SHICHEN)               # 辰 → 次日卯
        cid = stakes.plant(w, {"what": "钟万仇夫妇启程", "in": "一日"})
        self.assertEqual(timing.cut_minutes(w, {"until": "钟万仇夫妇启程"}), PER_DAY)
        self.assertEqual(timing.cut_minutes(w, {"until": cid}), PER_DAY)
        self.assertIsNone(timing.cut_minutes(w, {"until": "不知何时"}))

    def test_a_study_turn_really_passes_time(self):
        w = World.create("测")
        w.player.set("location", "琅嬛福地·玉像石室")
        book_in_hand(w)
        llm = StubLLM(director(beats=[{"who": "player", "text": "你展开帛卷照图习练", "ops": [{"op": "study", "id": "player", "value": BOOK}]}],
                               pace="片刻"))
        t0 = w.clock.tick
        Game(w, llm).act(f"研习{BOOK}")
        self.assertGreaterEqual(w.clock.tick - t0, 60)
        self.assertIn("凌波微步", w.player["skills"])                                    # 一回合入门：不再要连练四十回


class CanonWindowTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")

    def test_canon_follows_the_story_into_the_valley(self):
        w = self.w
        w.done.extend(e["id"] for e in w.canon if e["order"] < 8)                      # 故事走到了谷底：段誉此前的原著都已了结
        w.clock.tick = 1832 * PER_DAY + 4 * PER_SHICHEN
        w.player.set("location", VALLEY)
        w.graph.set("段誉", "location", VALLEY)
        w.graph.set("段誉", "status", "wounded")
        ev = canon.pull(w)
        self.assertEqual(ev and ev["id"], "段誉坠入无量山谷")                              # 两日后的原著，相关者到位即可上演
        w.graph.set("段誉", "location", "无量后山")
        self.assertIsNone(canon.pull(w))                                               # 相关者不在身边：不拉

    def test_a_variant_played_by_the_director_is_fulfilled(self):
        w = self.w
        applied = [{"op": "link", "src": "司空玄", "dst": "钟灵", "rel": "扣为人质"}]
        done = [ev["id"] for ev in canon.consume(w, applied)]
        self.assertIn("神农帮留钟灵下毒逼援", done)                                        # 剧情里已扣下钟灵：原著不再重演
        self.assertIn("神农帮留钟灵下毒逼援", w.done)
        self.assertEqual(canon.consume(w, [{"op": "set", "id": "player", "key": "posture", "value": "坐"}]), [])

    def test_the_director_hears_that_canon_is_ready(self):
        w = self.w
        w.done.extend(e["id"] for e in w.canon if e["order"] < 8)
        w.clock.tick = 1832 * PER_DAY + 4 * PER_SHICHEN
        w.player.set("location", VALLEY)
        w.graph.set("段誉", "location", VALLEY)
        w.graph.set("段誉", "status", "wounded")
        llm = StubLLM(director())
        Game(w, llm).act("看")
        self.assertIn("原著「段誉逃离干葛追赶，失足落入崖下谷地。」在此上演", llm.director_prompts[-1])
        self.assertIn("段誉坠入无量山谷", w.done)


class StakesAndSceneTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")

    def test_a_clock_falls_due_once(self):
        w = self.w
        stakes.plant(w, {"what": "云中鹤的耐心", "in": "三个时辰"})
        self.assertEqual(stakes.urgent(w)[1], "余3个时辰")
        w.advance(3 * PER_SHICHEN)
        self.assertEqual([c["what"] for c in stakes.due(w)], ["云中鹤的耐心"])
        self.assertEqual(stakes.due(w), [])

    def test_a_scene_spans_turns_and_closes(self):
        w = self.w
        sc = scene.begin(w)
        scene.close(w, scene.question({"state": "转", "ask": "能否取信于左子穆"}), "自报来历")
        sc = scene.begin(w)
        self.assertEqual((sc["id"], sc["ask"], sc["tried"]), (1, "能否取信于左子穆", ["自报来历"]))
        for deed in ("赔罪", "送礼", "比剑", "求情"):
            scene.close(w, scene.question({"state": "转"}), deed)
        self.assertTrue(scene.over(w.player["scene"]))
        self.assertIn("必须有个结果", brief.compose(w, None, [])["text"])
        scene.close(w, scene.question({"state": "合"}), "认输")
        self.assertEqual(scene.begin(w)["id"], 2)                                        # 合场即开新场

    def test_the_brief_rotates_away_from_canon(self):
        w = self.w
        for _ in range(3):
            brief.remember(w, "canon")
        self.assertFalse(brief.allow_pull(w))
        brief.remember(w, "arc")
        self.assertTrue(brief.allow_pull(w))

    def test_the_clock_reaches_the_director_and_cut_waits_for_nightfall(self):
        w = self.w
        llm = StubLLM(director(clock={"what": "左子穆限你今夜离山", "in": "半日"}, scene={"state": "合", "ask": "去留"},
                               cut={"until": "入夜"}))
        game = Game(w, llm)
        game.act("向左子穆告辞")
        self.assertEqual(w.clock.parts()["hour"][:2], "酉时")                              # 一场合了：跳到入夜
        game.act("看")
        self.assertIn("左子穆限你今夜离山", llm.director_prompts[-1])


class ArcAndChoicesTest(unittest.TestCase):
    def test_the_book_in_hand_starts_the_arc(self):
        w = World.create("测", origin="武师")
        w.turn = {}
        self.assertIsNone(arc.track(w))
        book_in_hand(w)
        self.assertEqual(arc.track(w), "入局")
        self.assertIn("主角线：求一门真正的武学（入局）", arc.line(w))
        w.player.set("goal", "替段誉寻回钟灵")
        arc.track(w)
        self.assertEqual(w.player["arc"]["stage"], 0)                                   # 所求一变，主角线从头

    def test_options_cover_a_later_slot(self):
        w = World.create("测")
        w.player.set("location", "无量山")
        scene.begin(w)
        self.assertEqual(len(choices.slots(w)), 3)
        later = choices.later(w)
        self.assertTrue(later)
        opts = [{"text": "拔剑", "targets": [], "scale": "此刻"}, {"text": "喝问", "targets": [], "scale": "此刻"},
                {"text": "退开", "targets": [], "scale": "机缘"}]
        picked = [t for t, _ in menu.check(w, opts, later=later)]
        self.assertIn(later[0][0], picked)                                              # 没有此后之事：补一项，时间才往前走
        w.player.set("hp", 5)
        self.assertEqual(choices.later(w), [])                                          # 命悬一线：没有此后

    def test_an_option_keeps_its_price_whole_or_drops_it(self):
        from tianlong.narrative import agents
        raw = ("正文\n===\n梗概：x\n选项：\n1. 借大乱潜入后山剑湖宫搜寻剑谱底细（冒被守卫格杀之险耗去半夜）｜对象：剑湖宫｜尺度：此后\n"
               "2. 连夜赶往大理（两日路程）｜对象：大理｜尺度：此后\n3. 追问剑谱｜对象：左子穆｜代价：耗时一个时辰")
        texts = [o["text"] for o in agents._page(raw)["options"]]
        self.assertEqual(texts, ["借大乱潜入后山剑湖宫搜寻剑谱底细", "连夜赶往大理（两日路程）", "追问剑谱（耗时一个时辰）"])  # 宁缺不截半句

    def test_the_heros_mind_is_not_the_directors_to_write(self):
        w = World.create("测")
        applied, rejected = w.apply([{"op": "set", "id": "player", "key": "intent", "value": "就地研习"}], "director")
        self.assertEqual((applied, rejected), ([], []))                                 # 不入账，也不为此返工


if __name__ == "__main__":
    unittest.main()
