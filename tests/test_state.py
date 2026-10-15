"""
[INPUT]: 依赖 tianlong.world 的 actor / body / bond / growth / lexicon / profile / rag / adjudicate 与 data/canon 原著世界，tianlong.engine 的 Game；
         复用 tests/test_adjudicate 的 plan / judge、tests/test_engine 的 StubLLM / director
[OUTPUT]: unittest 用例——v4 状态层「事件先于状态」的离线验收：
          NPC 与主角同构(气血推出负伤、写 status 气血随之对齐、内伤分级、光阴里一同养伤、吸功即负伤)；
          恩怨账(救人、赠物、夺物、伤人从 ops 推出，态度 link 不立边、按轻重记一笔，衰减不冻结)；
          进境是一等状态(习练中的功夫进身况与视锥、拍里写「身如游龙」而账上没有即违例、拍里在习练玩家所指的秘籍即追认一回研习、
          编剧写出账上没有的进境记作偏差交下回合导演)；单一投影 profile 同时喂界面、编剧与导演
          v13：研习账按武学记（练凌波微步不连带北冥）；账文分歧的措辞「这几句玩家已经读到」
[POS]: tests 的状态层验证——v4 方案第二部分(S1~S4)的离线证据；「凌波微步练到身如游龙却没有武功」那一局在这里逐条成为用例
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tests.test_engine import StubLLM, director
from tianlong.engine import Game
from tianlong.world import actor, body, bond, growth, lexicon, profile, rag
from tianlong.world.world import World

BOOK = "北冥神功卷轴"
VAULT = "琅嬛福地·玉像石室"


def stance(w, who):
    return profile.profile(w, who)["stance"]


class ActorTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_an_npcs_wound_follows_from_blood(self):
        w = self.w
        applied, _ = w.apply([{"op": "add", "id": "左子穆", "key": "hp", "value": -30}], "director")
        self.assertEqual((len(applied), w.graph.get("左子穆", "status")), (1, "wounded"))     # 气血跌破八成即负伤
        self.assertEqual(profile.profile(w, "左子穆")["wound"], "轻伤")
        w.apply([{"op": "add", "id": "左子穆", "key": "hp", "value": -200}], "director")
        self.assertEqual((actor.vitals(w, "左子穆")[0], w.graph.get("左子穆", "status")), (1, "wounded"))  # 扣血扣不死人：死须明写
        body.recover(w, body.REST * 12)
        self.assertEqual(w.graph.get("左子穆", "status"), "alive")                         # 光阴里一同将养，养回来即安好

    def test_declared_status_aligns_the_blood(self):
        w = self.w
        w.apply([{"op": "set", "id": "左子穆", "key": "status", "value": "wounded"}], "director")
        self.assertLessEqual(actor.vitals(w, "左子穆")[0], 60)
        w.graph.set("段誉", "status", "wounded")
        self.assertEqual(actor.vitals(w, "段誉"), (60, 100))                               # 原著里负伤之人，初见六成

    def test_inner_injury_is_the_same_rule_for_everyone(self):
        w = self.w
        w.apply([{"op": "push", "id": "左子穆", "key": "conditions", "value": "岔气"}], "director")
        w.apply([{"op": "push", "id": "左子穆", "key": "conditions", "value": "经脉"}], "director")
        self.assertEqual(w.graph.get("左子穆", "conditions"), ["内息紊乱"])               # 一回合至多一级
        w.apply([{"op": "set", "id": "段誉", "key": "conditions", "value": "中毒"}], "director")
        self.assertEqual(w.graph.get("段誉", "conditions"), ["中毒"])                      # 「变为中毒」即添上一样

    def test_mood_lingers_a_few_turns_then_fades(self):
        w = self.w
        judge(w, plan(("段誉", "段誉连连摇手", [], "player")))
        w.plan = None
        judge(w, {**plan(("段誉", "段誉连连摇手", [], "player")), "beats": [{"who": "段誉", "text": "段誉连连摇手", "ops": [], "mood": "惶急"}]})
        self.assertEqual(actor.mood(w, "段誉"), "惶急")
        w.player.set("turn", w.player["turn"] + actor.MOOD_TURNS)
        self.assertIsNone(actor.mood(w, "段誉"))

    def test_intent_is_a_sentence_the_plot_can_change(self):
        w = self.w
        w.apply([{"op": "set", "id": "段誉", "key": "intent", "value": "要随钟灵去万劫谷看闪电貂"}], "director")
        people = {p["name"]: p for p in rag.build(w)["people"]}
        self.assertEqual(people["段誉"]["intent"], "要随钟灵去万劫谷看闪电貂")


class BondTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")

    def test_rescue_and_injury_are_read_from_what_was_done(self):
        w = self.w
        w.graph.link("左子穆", "段誉", "扣为人质")
        judge(w, plan(("player", "你割断绳索，救下段誉", [{"op": "unlink", "src": "左子穆", "dst": "段誉", "rel": "扣为人质"}])), {"段誉"})
        self.assertEqual(stance(w, "段誉")["word"], "友善")
        self.assertEqual(stance(w, "段誉")["why"], "你救了他")
        judge(w, plan(("player", "你一掌击中左子穆胸口", [{"op": "add", "id": "左子穆", "key": "hp", "value": -20}])), {"左子穆"})
        self.assertEqual(stance(w, "左子穆")["word"], "戒备")

    def test_rewriting_an_existing_bond_is_not_another_event(self):
        w = self.w
        seize = plan(("player", "你一把扣住段誉", [{"op": "link", "src": "player", "dst": "段誉", "rel": "扣押"}]))
        judge(w, seize, {"段誉"})
        judge(w, seize, {"段誉"})                                                        # 导演每回合重写一遍拘押
        self.assertEqual(len(w.graph.nodes["段誉"]["bond"]["log"]), 1)

    def test_an_attitude_is_an_event_not_an_edge(self):
        w = self.w
        w.apply([{"op": "link", "src": "段誉", "dst": "player", "rel": "疑忌", "note": "你来路不明"}], "director")
        self.assertFalse(any(e["dst"] == "player" and e["src"] == "段誉" for e in w.graph.edges))
        self.assertIn("对你相识（你来路不明）", profile.ties(w, "段誉"))                      # 一件小事改不动立场
        w.apply([{"op": "link", "src": "段誉", "dst": "player", "rel": "结义"}], "director")
        self.assertTrue(any(e["rel"] == "结义" for e in w.graph.edges))                     # 结构性关系才是边

    def test_gifts_and_robbery(self):
        w = self.w
        w.graph.set("左子穆长剑", "holder", "player")
        w.player.push("inventory", "左子穆长剑")
        judge(w, plan(("player", "你把长剑递给段誉", [{"op": "set", "id": "左子穆长剑", "key": "holder", "value": "段誉"}])), {"段誉", "左子穆长剑"})
        self.assertEqual(stance(w, "段誉")["why"], "你赠他左子穆长剑")
        judge(w, plan(("player", "你夺过长剑", [{"op": "push", "id": "player", "key": "inventory", "value": "左子穆长剑"}])), {"左子穆长剑"})
        self.assertEqual(stance(w, "段誉")["why"], "你夺了他的左子穆长剑")


class MasteryTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        w = self.w
        w.player.set("location", VAULT)
        w.graph.set(BOOK, "hidden", False)
        w.graph.set(BOOK, "holder", "player")
        w.player.push("inventory", BOOK)

    def test_practice_in_progress_is_visible_everywhere(self):
        w = self.w
        w.turn = {}
        growth.study(w, BOOK, 20, "凌波微步")                                               # v13 账按武学记：练的是凌波微步，就只是凌波微步
        tags = [t["text"] for t in rag.condition(w)]
        self.assertIn("习练凌波微步中", tags)                                                 # 界面
        self.assertNotIn("习练北冥神功中", tags)                                              # 同一部书上的另一门功夫不连带
        arts = rag.build(w)["player"]["arts"]
        self.assertTrue(any(a.startswith("凌波微步：未入门") for a in arts), arts)            # 编剧与导演
        w.turn = {}
        growth.study(w, BOOK, 120, "凌波微步")
        self.assertIn("身负凌波微步·初窥门径", [t["text"] for t in rag.condition(w)])

    def test_claimed_mastery_without_a_stage_is_a_violation(self):
        w = self.w
        r = judge(w, plan(("player", "你踏着卦位一路走下来，身如游龙", [])))
        self.assertEqual([f.kind for f in r.hard], ["mastery"])
        self.assertEqual(lexicon.mastery("你尚未练成，只是略有所感"), [])
        w.turn = {}
        growth.study(w, BOOK, 120)
        self.assertEqual(judge(w, plan(("player", "你步法已然入门，身如游龙", []))).hard, [])  # 账上已入门：入门的措辞有账可依
        self.assertEqual([f.kind for f in judge(w, plan(("player", "你这步法已臻大成", []))).hard], ["mastery"])

    def test_study_is_the_players_choice(self):
        w = self.w
        r = judge(w, plan(("player", "你顺手翻开帛卷练了起来", [{"op": "study", "id": "player", "value": BOOK}])))
        self.assertIn(f"研习{BOOK}", r.candidates)                                       # 玩家没选：不演，留作下回合的选项
        self.assertNotIn(BOOK, w.player["study"])

    def test_a_practice_beat_is_ratified_as_study(self):
        w = self.w
        p = plan(("player", "你展开帛卷，照着图谱演练步法", []), pace="半日")
        self.assertEqual(adjudicate_imply(w, p, {BOOK}), BOOK)
        r = judge(w, p, {BOOK})
        self.assertTrue(any(op["op"] == "study" for op in r.applied))
        self.assertEqual(w.player["study"]["北冥神功"]["src"], BOOK)                      # v13 账键是武学，来源是这部书
        self.assertIsNone(adjudicate_imply(w, plan(("player", "你照着图谱演练步法", [])), set()))  # 玩家没指着它：不追认

    def test_writer_drift_reaches_the_next_director(self):
        w = self.w
        llm = StubLLM({**director(), "小说家": "你步法一展，身如游龙。\n===\n梗概：练功\n传言：无"})
        game = Game(w, llm)
        game.act("看看四周")
        self.assertTrue(w.player["drift"])
        game.act("看看四周")
        self.assertIn("账文分歧·这几句玩家已经读到", llm.director_prompts[-1])  # v6：正文是定本，进境归规则——写了账上没有的进境只能是分歧(v13 措辞：读过的不可推翻)
        self.assertIn("身如游龙", llm.director_prompts[-1])


def adjudicate_imply(w, p, aim):
    from tianlong.world import adjudicate
    return adjudicate.imply(w, p, set(aim))


if __name__ == "__main__":
    unittest.main()
