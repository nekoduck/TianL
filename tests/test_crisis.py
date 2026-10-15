"""
[INPUT]: 依赖 tianlong.world 的 pacing / menu / body / situation / crowd / effects / adjudicate / rag 与 data/canon 原著世界，tianlong.story 的 choices / scene / brief，tianlong.engine 的 Game；
         复用 tests/test_adjudicate 的 cliff / judge / plan、tests/test_engine 的 StubLLM；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——v12 危局：15 回实录第 12–15 回主角被神农攻山帮众围在崖上，兜底三回都是「四下察看」，第 14 回只扣血改打算就报了合，
          第 15 回开新场主干落回「段誉的图谋」：
          P1-1 危局的单一口径(被围时没有此后、兜底由状态生成、写「将你团团围住」也算、厅上喝止别人不算、只扣血改打算的合记作转且僵持加一、
          结下拘押即可合且僵持归零、僵持满三回合场记要求结构性变化、危局里新场的主干是危局、命悬一线而无人可指时的兜底、身况分档 0.5 与命悬一线同一判定)；
          P1-7 僵持到期押走(帮众四回只会合围砍杀、段誉把「小生愿随你们去」再说一遍)：僵持满四回合而本回合仍无结构性变化，围困的人群照它写下的打算擒人押走——
          押去首领跟前(连带、名册、时间轴)、首领不算被擒者、去处取打算里写着的地方、满三回合只在场记里预告、擒拿字眼的两种否定、冲得出的不押、
          导演自己写了结构性变化不押、擒段誉而主角留下、就地扣下、另一群也围着即整桩不做、押着走不脱而功力够即脱身、导演一拍押走成立、
          原著挪走首领人群随之而去即回合末了断押解、引擎把场的僵持计数交裁决、试演与定稿同一结果
[POS]: tests 的危局验证——v12 P1-1(与 P1-7 僵持押走)的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import unittest

from tests.test_adjudicate import cliff, judge, plan
from tests.test_engine import StubLLM
from tianlong.engine import Game
from tianlong.story import brief, choices, scene
from tianlong.world import body, crowd, effects, menu, pacing, rag, situation
from tianlong.world.world import World

RESOLVED = {"ask": "能否脱身", "state": "resolved", "by": None}


class DangerTest(unittest.TestCase):
    """危局只有一个口径(pacing.danger)：槽位、兜底、合场、主干、僵持提示、幕间省略都读它。"""

    def test_besieged_at_full_strength_is_still_a_crisis(self):
        w = cliff()
        w.player.set("hp", w.player["max_hp"])                                         # 满血：命悬一线之外的危局
        self.assertEqual(choices.later(w), [])                                          # 被围时没有此后
        texts = [t for t, _ in menu._fallbacks(w, [])]
        self.assertNotIn("歇息", texts)
        self.assertNotIn("四下察看", texts)                                             # 第 12–14 回兜底三次都是它
        self.assertIn("设法冲出神农帮众的包围", texts)
        self.assertIn("A 此刻·刚/奇", choices.slots(w)[0])                               # 危局的三槽

    def test_written_pressure_counts_and_others_quarrels_do_not(self):
        w = World.create("测")
        self.assertTrue(pacing.danger(w, [{"who": None, "text": "黄衫汉子们发一声喊，将你团团围住"}]))  # 没有围攻边也算
        self.assertEqual(pacing.danger(w, [{"who": "左子穆", "to": "龚光杰", "text": "左子穆喝止龚光杰"}]), [])

    def test_a_crisis_does_not_close_on_blood_and_moods(self):
        w = cliff()
        scene.begin(w)
        soft = [{"op": "add", "id": "player", "key": "hp", "value": -10}, {"op": "set", "id": "段誉", "key": "intent", "value": "护着少女退后"},
                {"op": "set", "id": "段誉", "key": "mood", "value": "惊惶"}]
        pressed = bool(pacing.danger(w, []))
        scene.close(w, RESOLVED, "挥剑", scene.settles(soft, False, pressed), pressed=pressed, shifted=pacing.structural(soft))
        self.assertEqual((w.player["scene"]["state"], w.player["scene"]["stall"]), ("转", 1))  # 第 14 回的伪合：记作转，僵持加一
        hostage = [{"op": "link", "src": "神农攻山帮众", "dst": "段誉", "rel": "扣为人质"}]
        scene.close(w, RESOLVED, "挥剑", scene.settles(hostage, False, pressed), pressed=pressed, shifted=pacing.structural(hostage))
        self.assertEqual((w.player["scene"]["state"], w.player["scene"]["stall"]), ("合", 0))  # 结下拘押：有账可依

    def test_the_engine_counts_the_stall(self):
        w = cliff()
        llm = StubLLM({"说书人与导演": {"beats": [{"who": None, "text": "刀光掠过，你手臂一凉，鲜血直流", "ops": [{"做": "伤人", "对": "player", "血": 8}]},
                                                 {"who": "段誉", "text": "段誉惊惶失措", "ops": [{"做": "打算", "谁": "段誉", "为": "劝众人罢手"}]}],
                                       "scene": {"state": "合", "ask": "能否脱身"}, "pace": "瞬息"}})
        game = Game(w, llm)
        game.act("挥剑抵挡")
        self.assertEqual((w.player["scene"]["state"], w.player["scene"]["stall"]), ("转", 1))
        game.act("挥剑抵挡")
        self.assertEqual(w.player["scene"]["stall"], 2)

    def test_the_brief_asks_for_a_structural_change(self):
        w = cliff()
        sc = scene.begin(w)
        story = brief.compose(w, None, [])
        self.assertEqual(story["spine"], "crisis")                                      # 危局里新开的场：主干不是段誉的图谋
        self.assertIn("眼前的危局（主角被神农帮众围住）", story["text"])
        w.player.set("scene", {**sc, "state": "转", "turns": 3, "stall": pacing.STALL_WARN})
        self.assertIn(f"危局已僵持{pacing.STALL_WARN}回合：本回合须有结构性的变化", brief.compose(w, None, [])["text"])

    def test_the_stall_follows_the_crisis_not_the_scene(self):
        w = cliff()
        sc = scene.begin(w)
        w.player.set("scene", {**sc, "state": "断", "stall": 2})                       # 导演报断：开新场，危局仍在
        self.assertEqual(scene.begin(w)["stall"], 2)
        w2 = World.create("测")
        sc = scene.begin(w2)
        w2.player.set("scene", {**sc, "state": "合", "stall": 2})
        self.assertEqual(scene.begin(w2)["stall"], 0)                                   # 脱离危局：归零
        old = {k: v for k, v in sc.items() if k != "stall"}
        w2.player.set("scene", old)
        scene.close(w2, RESOLVED, "看")                                                # 旧场没有 stall：按 0 读
        self.assertEqual(w2.player["scene"]["stall"], 0)

    def test_on_the_brink_with_nobody_to_turn_to(self):
        w = World.create("测")
        w.player.set("location", "无量山·谷底")
        w.player.set("hp", 10)
        self.assertEqual([t for t, _ in menu._fallbacks(w, [])], ["强撑伤势，寻隙脱身"])
        self.assertIn("强撑伤势，寻隙脱身", [t for t, _ in menu.check(w, [])])

    def test_wounds_are_graded_by_one_line(self):
        w = World.create("测")
        for hp, word in ((33, "重伤"), (55, "轻伤"), (15, "命悬一线"), (16, "重伤")):
            w.player.set("hp", hp * w.player["max_hp"] // 100)
            self.assertEqual(body.wound(w)[0], word)


GANG = "神农攻山帮众"
CURSE = (GANG, "帮众纷纷叫骂：「臭小子，看你往哪里逃！」", [])                       # 导演的拍只有叫骂与神色
PALE = ("段誉", "段誉面色惨白，连连摇手", [{"做": "神色", "谁": "段誉", "为": "惊惶"}])


class SeizeTest(unittest.TestCase):
    """P1-7 僵持到期：第 12–15 回帮众四回只会合围砍杀——僵持满四回合、本回合仍无结构性变化，规则照围困人群写下的打算擒人押走。
    共同布置：主角在澜沧江边高崖被神农攻山帮众围住(cliff)，司空玄在无量山。"""

    def seize(self, intent, w=None, stall=pacing.STALL_SEIZE, beats=(CURSE, PALE)):
        w = w or cliff()
        if intent:
            w.graph.set(GANG, "intent", intent)
        return w, judge(w, plan(*beats), stall=stall)

    def test_taken_to_the_chief(self):
        w, r = self.seize("擒下这闯山的小子，押回去见帮主")
        g = w.graph
        self.assertEqual(w.here, "无量山")
        self.assertEqual(crowd.holders(w), [(GANG, "押解")])                            # 押着，不再围着
        self.assertEqual(crowd.besiegers(w), [])
        self.assertEqual(g.get(GANG, "location"), "无量山")
        self.assertTrue(crowd.present(w, GANG))                                           # 押着你的人就在你身边
        self.assertIn("司空玄", situation.around(w))                                     # 押到首领跟前
        self.assertIn("神农帮众照其所图，将你擒下，押往无量山", r.notes)
        for op in ({"op": "unlink", "src": GANG, "dst": "player", "rel": "围攻"}, {"op": "link", "src": GANG, "dst": "player", "rel": "押解"},
                   {"op": "set", "id": GANG, "key": "location", "value": "无量山"}, {"op": "set", "id": "player", "key": "location", "value": "无量山"}):
            self.assertIn(op, r.applied)
        self.assertEqual(w.turn["moments"][-1]["here"], "无量山")                       # 正文在那里听到的名字才落得到人
        self.assertEqual(w.turn["seized"], {"by": GANG, "who": "player", "to": "无量山"})
        self.assertTrue(pacing.danger(w))                                                 # 押着：仍是危局，只有脱身
        self.assertIn("被神农帮众押着", [t["text"] for t in rag.condition(w)])
        self.assertTrue(crowd.card(w, GANG)["holding"])

    def test_the_chief_is_not_the_captive_and_a_named_place_wins(self):
        w, _ = self.seize("擒下此人，押去见帮主司空玄")
        self.assertEqual(w.turn["seized"], {"by": GANG, "who": "player", "to": "无量山"})  # 首领不算被擒者
        w, _ = self.seize("将他绑了押往剑湖宫")
        self.assertEqual((w.turn["seized"]["to"], w.here), ("剑湖宫", "剑湖宫"))         # 打算里写着的去处在先，不取首领所在

    def test_three_turns_only_warn(self):
        w, r = self.seize("擒下这闯山的小子，押回去见帮主", stall=pacing.STALL_WARN)
        self.assertNotIn("seized", w.turn)
        self.assertEqual((w.here, crowd.besiegers(w)), ("澜沧江边高崖", [GANG]))
        sc = scene.begin(w)
        w.player.set("scene", {**sc, "state": "转", "stall": pacing.STALL_WARN})
        text = brief.compose(w, None, [])["text"]
        self.assertIn("再无结构性变化，神农帮众将照其所图把主角擒下押往无量山（系统落账）", text)
        self.assertNotIn("本回合再无结构性变化", text)
        w.player.set("scene", {**sc, "state": "转", "stall": pacing.STALL_SEIZE})
        self.assertIn("本回合再无结构性变化", brief.compose(w, None, [])["text"])

    def test_the_brief_teaches_the_intent_only_under_siege(self):
        w = cliff()
        sc = scene.begin(w)
        w.player.set("scene", {**sc, "state": "转", "stall": pacing.STALL_WARN})
        self.assertIn("这群人若要擒人，写 打算（谁=那一群，为=擒下某人押往某处）", brief.compose(w, None, [])["text"])
        w2 = World.create("测")
        w2.player.set("location", "无量山·谷底")
        w2.player.set("hp", 10)                                                           # 只是命悬一线：没有人群可教
        sc = scene.begin(w2)
        w2.player.set("scene", {**sc, "state": "转", "stall": pacing.STALL_WARN})
        text = brief.compose(w2, None, [])["text"]
        self.assertIn("危局已僵持", text)
        self.assertNotIn("这群人若要擒人", text)

    def test_what_counts_as_meaning_to_seize(self):
        for intent in ("围住此人，不许他走脱", "拿下无量山要地", "不再擒人，放他走"):
            w, _ = self.seize(intent)
            self.assertNotIn("seized", w.turn, intent)
            self.assertEqual(w.here, "澜沧江边高崖")
        for intent in ("正要擒下此人押走", "不要放走此人，擒下押回帮中", "饶他不得，擒下押回无量山"):  # 「正要」不是否定
            w, _ = self.seize(intent)
            self.assertEqual(w.turn.get("seized", {}).get("who"), "player", intent)

    def test_one_who_can_break_out_is_not_taken(self):
        w = cliff()
        w.player.set("power", 60)                                                         # 冲得出二十八名帮众
        w, _ = self.seize("擒下这闯山的小子，押回去见帮主", w)
        self.assertNotIn("seized", w.turn)

    def test_the_directors_own_turn_of_events_comes_first(self):
        hostage = (GANG, "帮众一拥而上，揪住了段誉", [{"做": "结下", "谁": GANG, "对": "段誉", "为": "扣为人质"}])
        w, r = self.seize("擒下这闯山的小子，押回去见帮主", beats=(hostage,))
        self.assertNotIn("seized", w.turn)                                               # 本回合已有结构性变化
        self.assertEqual(w.here, "澜沧江边高崖")

    def test_seizing_duan_yu_leaves_you_behind(self):
        w, r = self.seize("擒下段誉押回帮中")
        g = w.graph
        self.assertEqual((g.get("段誉", "location"), w.here), ("无量山", "澜沧江边高崖"))
        self.assertIn({"src": GANG, "dst": "段誉", "rel": "押解"}, g.edges)              # 段誉受制
        self.assertEqual(crowd.besiegers(w), [])                                          # 主角不再被围
        self.assertEqual(w.player["cast"], [])                                            # 主角的名册不变
        self.assertIn("神农帮众照其所图，将段誉擒下，押往无量山", r.notes)
        w = cliff()
        w.graph.set("段誉", "location", "无量山")                                        # 段誉不在眼前：另有所图
        w, _ = self.seize("擒下段誉押回帮中", w, beats=(CURSE,))
        self.assertNotIn("seized", w.turn)

    def test_held_on_the_spot(self):
        w = World.create("测")
        w.player.set("location", "剑湖宫·练武厅")
        w.graph.link("东宗弟子众", "player", "围攻")
        w.graph.set("东宗弟子众", "intent", "擒下此人交掌门发落")                      # 没有首领，据点剑湖宫就在近旁
        r = judge(w, plan(("东宗弟子众", "东宗弟子齐声呼喝", [])), stall=pacing.STALL_SEIZE)
        self.assertEqual(w.here, "剑湖宫·练武厅")
        self.assertEqual(crowd.holders(w), [("东宗弟子众", "押解")])
        self.assertTrue(any(n.endswith("就地扣下") for n in r.notes))

    def test_another_ring_spoils_the_whole_seizure(self):
        w = cliff()
        crowd.relocate(w, "东宗弟子众", "澜沧江边高崖")
        w.graph.link("东宗弟子众", "player", "围攻")
        w.graph.set(GANG, "intent", "擒下这闯山的小子，押回去见帮主")
        edges, where = copy.deepcopy(w.graph.edges), w.graph.get(GANG, "location")
        r = judge(w, plan(CURSE), stall=pacing.STALL_SEIZE)
        self.assertNotIn("seized", w.turn)
        self.assertEqual((w.graph.edges, w.graph.get(GANG, "location"), w.here), (edges, where, "澜沧江边高崖"))  # 世界不变
        self.assertTrue([f for f in r.soft if f.kind == "seize" and not f.hard])

    def test_held_you_cannot_walk_off(self):
        w, _ = self.seize("擒下这闯山的小子，押回去见帮主")
        w.turn = {}
        _, rejected = effects.apply(w, [{"做": "前往", "谁": "player", "到": "剑湖宫"}], "director")
        self.assertIn("押着，走不脱", rejected[0][1])
        _, rejected = effects.apply(w, [{"做": "脱身", "谁": "player"}], "director")
        self.assertIn("冲不出", rejected[0][1])
        w.player.set("power", 60)
        done, rejected = effects.apply(w, [{"做": "脱身", "谁": "player", "到": "剑湖宫"}], "director")
        self.assertEqual((rejected, w.here, crowd.holders(w)), ([], "剑湖宫", []))
        self.assertIn({"op": "unlink", "src": GANG, "dst": "player", "rel": "押解"}, done)

    def test_the_director_may_march_you_off_in_one_beat(self):
        ops = [{"做": "了断", "谁": GANG, "对": "player", "为": "围攻"}, {"做": "结下", "谁": GANG, "对": "player", "为": "押解"},
               {"做": "前往", "谁": GANG, "到": "无量山"}, {"做": "前往", "谁": "player", "到": "无量山"}]
        w = cliff()
        r = judge(w, plan((None, "帮众一拥而上，将你反剪双手，押下高崖，径往无量山而去", ops)))
        self.assertEqual(([f for f in r.hard if f.kind == "custody"], r.void), ([], []))  # 四条全部成立，没有擒者人质异地
        self.assertEqual((w.here, crowd.present(w, GANG), crowd.holders(w)), ("无量山", True, [(GANG, "押解")]))

    def test_the_gang_follows_its_chief_and_lets_you_go(self):
        w, _ = self.seize("擒下这闯山的小子，押回去见帮主")
        w.turn = {}
        effects.apply(w, [{"op": "set", "id": "司空玄", "key": "location", "value": "大理城"}], "canon")  # 原著挪走首领
        self.assertEqual(w.graph.get(GANG, "location"), "大理城")                       # 人群随首领而去
        self.assertIn("你不再受神农帮众看押", situation.sunder(w))                       # 回合末了断押解
        w.turn = {}
        done, _ = effects.apply(w, [{"做": "前往", "谁": "player", "到": "剑湖宫"}], "director")
        self.assertEqual(w.here, "剑湖宫")

    def test_the_engine_hands_over_the_stall(self):
        w = cliff()
        w.graph.set(GANG, "intent", "擒下这闯山的小子，押回去见帮主")
        sc = scene.begin(w)
        w.player.set("scene", {**sc, "state": "转", "stall": pacing.STALL_SEIZE})
        game = Game(w, StubLLM({"说书人与导演": {"beats": [{"who": GANG, "text": "帮众纷纷叫骂", "ops": []}],
                                               "scene": {"state": "转", "ask": "能否脱身"}, "pace": "瞬息"}}))
        game.act("挥剑抵挡")
        self.assertEqual(w.here, "无量山")
        self.assertEqual(w.player["scene"]["stall"], 0)                                  # 押走是结构性变化：僵持归零

    def test_the_same_proposal_settles_the_same_way(self):
        w = cliff()
        w.graph.set(GANG, "intent", "擒下这闯山的小子，押回去见帮主")
        a, b = copy.deepcopy(w), copy.deepcopy(w)
        judge(a, plan(CURSE, PALE), stall=pacing.STALL_SEIZE)
        judge(b, plan(CURSE, PALE), stall=pacing.STALL_SEIZE)
        self.assertEqual(a.dump(), b.dump())
        self.assertEqual(a.turn["seized"], b.turn["seized"])


if __name__ == "__main__":
    unittest.main()
