"""
[INPUT]: 依赖 tianlong.world 的 body / adjudicate / settle / effects 与 data/canon 原著世界，复用 tests/test_adjudicate 的 plan / judge
[OUTPUT]: unittest 用例——v13「否决即事件」：60 回实录(王天龙)里系统对导演已宣告的后果握有的「静默否决权」逐条转成离线验收：
          DamageTest(P0-1)：伤人落多少血归规则封顶——攻守档位差×本回合命运骰查较量预裁表、一群人看胜算比、无人出手 SCRATCH、涉险 HAZARD；
          导演报的血只是轻重(擦伤照落、重击被封顶)，拍文没写伤字眼不再丢指令而记软违例并连带交编剧；明写被避开的与研习之拍才不扣且记软违例；
          疗伤一拍至多 HEAL_CAP；出手者缺省时取这一拍的说话人；正文写你负了伤而账上并无伤势记作分歧
          ConjureTest(P0-2)：凭空造物只查旁白不查台词(第 8 回「奉上此灵草」)、泛称说的是手边同类唯一之物而有名有姓的不算、降为返工不作废、「拾起散落的帛卷」的散是动词；
          HeroAsVictimTest：账房写的 自=player 不再被驳回(司空玄夺过通天草)、已在他手里的不是一件事；BillActorTest：单子写明谁做的，事码里没写谁就是他(第 7 回段誉服毒不再记成主角服用)；
          DriftTest(P0-3)：账房自己写歪的(id、格式)只记日志不算账文分歧，规则性的分歧交导演两回、导演写出碰到点名之人的后果即算圆回、满了作罢，导演后台的措辞写明读者读过的话不可推翻
[POS]: tests 的 v13 验证——「被否决的事要么成立、要么返工、要么明告读者，没有第四种」的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tianlong.world import adjudicate, body, effects, lexicon, settle
from tianlong.world.world import World

HURT = lambda who, to, n: {"做": "伤人", "谁": who, "对": to, "血": n}


class DamageTest(unittest.TestCase):
    """第 4、15、32、34、35、39、60 回：导演宣告的伤因拍文里没有伤字眼被悄悄丢掉，74 点伤只落了 7 点。"""

    def setUp(self):
        self.w = World.create("测")

    def loss(self, before):
        return before - self.w.player["hp"]

    def test_the_cap_follows_the_tiers_and_the_dice(self):
        w = self.w
        table = lambda gap: max(int(body.rule(gap, body.fate(w))[1].split("~")[-1]), body.SCRATCH)
        self.assertEqual(body.cap(w, "左子穆", "player"), table(2))                  # 二流好手对不会武功：差两档
        self.assertEqual(body.cap(w, "龚光杰", "player"), table(1))                  # 三流对不会武功：差一档
        self.assertEqual(body.cap(w, "player", "左子穆"), body.SCRATCH)              # 庸手伤不了高手，擦伤也算
        self.assertGreater(body.cap(w, "左子穆", "player"), body.cap(w, "龚光杰", "player"))
        self.assertEqual(body.cap(w, None, "player"), body.SCRATCH)                 # 无人出手
        self.assertEqual(body.cap(w, None, "player", moving=True), body.HAZARD)     # 涉险之地的坠跌磕碰
        self.assertEqual(body.cap(w, "player", "player"), body.SCRATCH)             # 自己磕自己

    def test_a_graze_keeps_its_size_and_a_slaughter_is_capped(self):
        w, hp = self.w, self.w.player["hp"]
        judge(w, plan(("龚光杰", "龚光杰长剑一抖，剑锋擦过你肩头", [HURT("龚光杰", "player", 5)])))
        self.assertEqual(self.loss(hp), 5)                                          # 第 4 回：「擦过肩头」无伤字眼，从前被丢；如今照落，导演报的轻重不变
        cap = body.cap(w, "龚光杰", "player")
        judge(w, plan(("龚光杰", "龚光杰一剑刺中你胸口，鲜血直流", [HURT("龚光杰", "player", 90)])))
        self.assertEqual(self.loss(hp), 5 + cap)                                    # 报九十点，规则只许这一击落到封顶

    def test_a_crowd_blow_is_capped_by_the_odds(self):
        w, hp = self.w, self.w.player["hp"]
        from tianlong.world import crowd
        east = "东宗弟子众"
        self.assertTrue(crowd.is_squad(w.graph, east))
        top = body.cap(w, east, "player")
        self.assertIn(top, (15, 25, 40))
        judge(w, plan(("东宗弟子众", "东宗弟子众挥剑合围，劈头盖脸斩落", [HURT(east, "player", 90)])))
        self.assertEqual(self.loss(hp), top)

    def test_when_the_act_names_no_attacker_the_speaker_of_the_beat_is_one(self):
        w, hp = self.w, self.w.player["hp"]
        judge(w, plan(("龚光杰", "龚光杰一剑刺中你肩头，鲜血直流", [{"做": "伤人", "对": "player", "血": 90}])))   # 谁省略即主角，可这是龚光杰的拍
        self.assertEqual(self.loss(hp), body.cap(w, "龚光杰", "player"))
        hp = w.player["hp"]
        judge(w, plan(("player", "你脚下一滑，膝头重重磕在岩上，疼得直抽冷气", [{"做": "伤人", "对": "player", "血": 90}])))
        self.assertEqual(self.loss(hp), body.SCRATCH)                               # 主角自己的拍、无人出手：磕碰封顶

    def test_a_wound_without_a_word_of_injury_lands_and_the_writer_is_told(self):
        w, hp = self.w, self.w.player["hp"]
        r = judge(w, plan(("player", "你环顾四周", [{"op": "add", "id": "player", "key": "hp", "value": -5}])))
        self.assertEqual(self.loss(hp), 5)
        self.assertIn("unwritten", [f.kind for f in r.soft])
        told = [n for n in r.notes if "你受了" in n]
        self.assertEqual(len(told), 1)
        self.assertFalse(any(ch.isdigit() for ch in told[0]))                       # 只说轻重，不报数字
        r = judge(w, plan(("干光豪", "干光豪一剑刺中你肩头，鲜血直流", [HURT("干光豪", "player", 8)])))
        self.assertNotIn("unwritten", [f.kind for f in r.soft])                     # 写了伤就不用补写

    def test_a_blow_the_text_says_was_parried_is_a_finding_not_a_secret(self):
        w, hp = self.w, self.w.player["hp"]
        r = judge(w, plan(("干光豪", "干光豪横剑直刺你肩头", [HURT("干光豪", "player", 18)]),
                          ("马五德", "马五德挥袖将那一剑荡了开去", [])))
        self.assertEqual(self.loss(hp), 0)
        self.assertIn("parried", [f.kind for f in r.soft])                          # 拍文明写荡开：以拍文为准，且记一条
        r = judge(w, plan(("干光豪", "干光豪一剑刺中你肩头，你险些避开，鲜血直流", [HURT("干光豪", "player", 8)]),
                          ("马五德", "马五德挥袖荡开了第二剑", [])))
        self.assertGreater(self.loss(hp), 0)                                        # 本拍已明写刺中：下一拍荡开的是第二剑，这一伤照落

    def test_a_study_beat_does_not_cost_blood_but_says_so(self):
        w = self.w
        ops = [{"op": "study", "id": "player", "value": "北冥神功卷轴"}, {"op": "add", "id": "player", "key": "hp", "value": -9}]
        keep, dropped, odd = adjudicate._grounded(w, ops, "你盘膝运功，真气走岔，吐出一口血", "", "player")
        self.assertEqual([k["op"] for k in keep], ["study"])                        # 研习的顺逆归预裁，不另扣血
        self.assertEqual([(kind) for _, kind, _ in dropped], ["study_hurt"])

    def test_healing_by_hand_is_capped_not_dropped(self):
        w = self.w
        effects.apply(w, [{"op": "add", "id": "段誉", "key": "hp", "value": -40}], "director")
        before = w.graph.get("段誉", "hp")
        r = judge(w, plan(("player", "你按住段誉后心，运功护住他的心脉", [{"做": "疗伤", "对": "段誉", "血": 30}])), {"段誉"})
        self.assertEqual(w.graph.get("段誉", "hp") - before, body.HEAL_CAP)         # 第 55 回「护住心脉」无疗字眼，从前被丢；如今落了，封顶十点
        self.assertEqual(r.void, [])

    def test_the_old_ruling_table_still_lives_in_rag(self):
        from tianlong.world import rag
        self.assertIs(rag.rule, body.rule)
        self.assertIs(rag.WIN, body.WIN)


class WoundClaimTest(unittest.TestCase):
    """第 60 回编剧写「连中数记短刀」而账上气血 100：正文写了你负伤、账上并无伤势，记作分歧交下回合导演。"""

    def setUp(self):
        self.w = World.create("测")
        judge(self.w, plan(("player", "你环顾四周", [])))

    def test_a_claimed_wound_the_ledger_never_took_is_a_rift(self):
        said = "乱刃加身，劲风刺骨，你避无可避，后背与肩臂登时连中数记短刀，剧痛钻心。"
        self.assertTrue(any("负了伤" in x for x in settle.ruled(self.w, said)))

    def test_not_when_the_ledger_took_it_or_the_hero_is_already_hurt(self):
        said = "你被龚光杰一剑砍中肩头。"
        judge(self.w, plan(("龚光杰", "龚光杰一剑刺中你肩头，鲜血直流", [HURT("龚光杰", "player", 9)])))
        self.assertFalse(any("负了伤" in x for x in settle.ruled(self.w, said)))   # 本回合账上落了伤
        self.w.turn["hurt"] = 0
        self.w.player.set("hp", 50)
        self.assertFalse(any("负了伤" in x for x in settle.ruled(self.w, "你强忍伤口剧痛，咬牙前行。")))  # 身上本就有伤

    def test_other_peoples_wounds_and_denials_are_not_the_heros(self):
        for said in ("你见段誉受了伤，急忙上前。", "你并未受伤。", "「你受了伤！」钟灵叫道。", "你险些受伤，侧身避过。"):
            self.assertFalse(any("负了伤" in x for x in settle.ruled(self.w, said)), said)


class ConjureTest(unittest.TestCase):
    """第 8 回：台词里一句「奉上此灵草」被判凭空造物，整拍作废，主角自己的「交给」随之作废。"""

    def setUp(self):
        self.w = World.create("测")
        g = self.w.graph
        g.nodes["通天草"].update(holder="player", location=None)
        self.w.player.push("inventory", "通天草")
        self.w.player.set("location", "无量山")
        for p in ("司空玄", "段誉", "钟灵"):
            g.set(p, "location", "无量山")
        self.w.player.set("cast", ["司空玄", "段誉", "钟灵"])

    def test_words_in_a_line_are_not_things_that_appeared(self):
        w = self.w
        tab = adjudicate.names(w)[0]
        said = "你双手捧出通天草朗声道：「帮主留步！在下奉上此灵草，愿换两位性命！」"
        self.assertEqual(lexicon._conjures(1, said, tab), [])                      # 台词不查
        self.assertEqual([f.entity for f in lexicon._conjures(1, "左子穆急召门人向内堂取密图备御", tab)], ["密图"])  # 旁白照查
        self.assertEqual(lexicon._conjures(1, "「去内堂取密图！」左子穆喝道。", tab), [])
        self.assertEqual(settle.ruled(w, "钟灵喊道：「快去万劫谷取解药来！」"), [])        # 第 9、58 回的「解药」是话，不是账文分歧

    def test_the_hand_over_stands_and_the_herb_changes_hands(self):
        w = self.w
        r = judge(w, plan(("player", "你双手捧出通天草朗声道：「帮主留步！在下奉上此灵草，愿换两位性命！」",
                           [{"做": "交给", "物": "通天草", "与": "司空玄"}], "司空玄"),
                          ("司空玄", "那汉子目光如电，一把夺过草药嗅了嗅", [{"做": "打算", "谁": "司空玄", "为": "拿通天草交差"}], "player")),
                  {"通天草", "司空玄"})
        self.assertEqual((r.hard, r.void), ([], []))
        self.assertEqual(w.graph.get("通天草", "holder"), "司空玄")
        self.assertNotIn("通天草", w.player["inventory"])                            # 账上与读者读到的一致

    def test_a_generic_name_means_the_one_thing_at_hand_but_a_named_one_does_not(self):
        w = self.w
        self.assertFalse(adjudicate.forged(w, "灵草"))                              # 手边同类的只有这一株
        self.assertTrue(adjudicate.forged(w, "断肠草"))                             # 有名有姓的另一味草：世上没有
        self.assertTrue(adjudicate.forged(w, "金创药"))
        self.assertTrue(adjudicate.forged(w, "火折"))

    def test_a_suspected_conjure_goes_back_once_but_never_voids_the_beat(self):
        w = self.w
        r = judge(w, plan(("司空玄", "司空玄急召帮众向内堂取密图备御", [])))
        self.assertEqual([(f.kind, f.entity) for f in r.hard], [("conjure", "密图")])
        self.assertEqual(adjudicate.doomed(r), {})                                   # 返工一次，仍不成立也不作废整拍
        r = judge(w, plan(("player", "你掏出火折晃亮", [{"做": "拿取", "物": "火折"}])))
        self.assertTrue(any("火折" in v for v in r.void))                            # 真碰了指令的，指令自己落不了，照样作废

    def test_a_scattered_scroll_is_not_a_powder(self):
        tab = adjudicate.names(self.w)[0]
        self.assertEqual(lexicon._conjures(1, "你一把拾起散落的白绸帛卷，借水光急切展开查验", tab), [])
        self.assertIsNone(lexicon.itemish("散落的白绸"))
        self.assertEqual(lexicon.itemish("一包金创散"), "一包金创散")


class HeroAsVictimTest(unittest.TestCase):
    """第 8 回账房写 夺取 自=player：从前被驳回为「不是在场之人」，通天草多活了三十八回。"""

    def setUp(self):
        self.w = World.create("测")
        g = self.w.graph
        g.nodes["通天草"].update(holder="player", location=None)
        self.w.player.push("inventory", "通天草")
        self.w.player.set("location", "无量山")
        self.w.player.set("cast", ["司空玄"])
        g.set("司空玄", "location", "无量山")
        self.w.turn = {}

    def test_a_stronger_man_takes_it_from_the_heros_hand(self):
        w = self.w
        ok, bad = effects.apply(w, [{"做": "夺取", "谁": "司空玄", "自": "player", "物": "通天草"}], "director")
        self.assertEqual(bad, [])
        self.assertEqual(w.graph.get("通天草", "holder"), "司空玄")
        self.assertNotIn("通天草", w.player["inventory"])

    def test_what_is_already_in_his_hand_is_not_a_discrepancy(self):
        w = self.w
        effects.apply(w, [{"做": "交给", "物": "通天草", "与": "司空玄"}], "director")
        self.assertEqual(effects.apply(w, [{"做": "夺取", "谁": "司空玄", "自": "player", "物": "通天草"}], "director"), ([], []))

    def test_the_hero_cannot_take_from_himself_and_a_weak_man_cannot_rob_a_strong_one(self):
        w = self.w
        self.assertEqual(effects.apply(w, [{"做": "夺取", "谁": "player", "自": "player", "物": "通天草"}], "director"), ([], []))
        w.graph.set("段誉", "location", "无量山")
        w.player.set("cast", ["司空玄", "段誉"])
        w.graph.nodes["通天草"].update(holder="司空玄")
        _, bad = effects.apply(w, [{"做": "夺取", "谁": "段誉", "自": "司空玄", "物": "通天草"}], "director")
        self.assertTrue(bad)                                                         # 段誉不会武功，夺不下来：照较量预裁


class BillActorTest(unittest.TestCase):
    """第 7 回账房的单子写「谁：段誉」，里面的 服用 没写谁——缺省成了主角，记成「主角服用断肠散——玩家并未起意」。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.graph.nodes["断肠散"].update(holder="司空玄")
        for p in ("司空玄", "段誉", "钟灵"):
            self.w.graph.set(p, "location", "无量山")
        self.w.player.set("location", "无量山")
        self.w.player.set("cast", ["司空玄", "段誉", "钟灵"])
        self.w.turn = {}
        self.text = "汉子自怀中摸出一包断肠散，捏住青衫少年的下颌，硬生生灌了下去。青衫少年被迫服毒，呛咳连连，面如死灰。"

    def bill(self, who):
        return {"changes": [{"据": "汉子自怀中摸出一包断肠散，捏住青衫少年的下颌，硬生生灌了下去", "谁": "司空玄",
                             "ops": [{"做": "交给", "谁": "司空玄", "物": "断肠散", "与": "段誉"}]},
                            {"据": "青衫少年被迫服毒，呛咳连连，面如死灰", "谁": who, "ops": [{"做": "服用", "物": "断肠散"}]}], "rifts": []}

    def test_whose_bill_it_is_decides_who_did_it(self):
        applied, rifts = settle.commit(self.w, self.bill("段誉"), self.text)
        self.assertEqual(rifts, [])
        self.assertTrue(any(op.get("op") == "trade" and op.get("to") == "段誉" for op in applied))   # 段誉服下的，不是主角
        self.assertEqual(self.w.player["conditions"], [])

    def test_an_unknown_actor_blocks_the_act_instead_of_blaming_the_hero(self):
        applied, rifts = settle.commit(self.w, self.bill("duan_yu"), self.text)
        self.assertFalse(any(op.get("op") == "trade" for op in applied))
        self.assertEqual(rifts, [])                                                    # 账房写错了人，是它的错，不是账文分歧

    def test_the_hero_still_needs_the_players_say_so(self):
        applied, rifts = settle.commit(self.w, self.bill("player"), self.text)
        self.assertTrue(any("玩家并未起意" in r for r in rifts))


class DriftTest(unittest.TestCase):
    """第 8 回：账房那条「从谁身上夺取？player 不是在场之人」是自己写歪的，却被当作账文分歧交导演「圆回」，读者读过的「夺过」被演成了「冷笑不接」。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_the_accountants_own_mistakes_are_not_rifts(self):
        w = self.w
        bill = {"changes": [{"据": "上前一把夺过你手中的北冥神功卷轴", "谁": "段誉", "ops": [{"做": "夺取", "谁": "段誉", "自": "北冥神功卷轴", "物": "神仙姊姊蒲团"}]}], "rifts": []}
        applied, rifts = settle.commit(w, bill, "段誉上前一把夺过你手中的北冥神功卷轴。")
        self.assertEqual((applied, rifts), ([], []))                                  # 「北冥神功卷轴」不是人：账房写歪了，只记日志

    def test_rule_matters_still_reach_the_director(self):
        w = self.w
        bill = {"changes": [{"据": "龚光杰被一掌震得气血翻涌", "谁": "player", "ops": [{"op": "add", "id": "龚光杰", "key": "hp", "value": -30}]}], "rifts": []}
        applied, rifts = settle.commit(w, bill, "龚光杰被一掌震得气血翻涌，退了三步。")
        self.assertTrue(rifts and "正文改不了账" in rifts[0])                          # 伤病多少归规则：这才是分歧

    def test_a_rift_is_handed_over_twice_then_let_go(self):
        me = self.w.player
        me.set("drift", ["正文「内力顿觉充盈大进」，账上：功力与武学进境由规则结算"])
        self.assertEqual(len(settle.age(self.w)), 1)                                   # 这一回合导演看到它(第一回)，留到下回合
        self.assertEqual(me["drift_seen"], {me["drift"][0]: 1})
        self.assertEqual(settle.age(self.w), [])                                       # 下一回合再提一回(第二回)，随即作罢
        self.assertEqual((me["drift"], me["drift_seen"]), ([], {}))

    def test_touching_the_named_person_counts_as_reconciling_it(self):
        w = self.w
        entry = "正文「段誉倚在空荡荡的书架木柱下，穴道未解」，账上：段誉已被解开穴道"
        self.assertTrue(settle.addressed(w, entry, [{"op": "push", "id": "段誉", "key": "conditions", "value": "被点穴"}]))
        self.assertFalse(settle.addressed(w, entry, [{"op": "set", "id": "左子穆", "key": "intent", "value": "守在门口"}]))
        self.assertFalse(settle.addressed(w, "正文写主角「功力大进」，账上：北冥神功·初窥门径", [{"op": "set", "id": "段誉", "key": "intent", "value": "催促出洞"}]))   # 只点了主角自己的：靠期限作罢

    def test_the_engine_carries_a_rift_for_exactly_two_turns(self):
        from tianlong.engine import Game
        game = Game(World.create("测"))
        game.world.player.set("drift", ["正文「某事」，账上：并无此事"])
        game.act("环顾四周")
        self.assertEqual(game.world.player["drift"], ["正文「某事」，账上：并无此事"])      # 导演看过一回，没人碰它：留着
        game.act("环顾四周")
        self.assertEqual(game.world.player["drift"], [])                                 # 看过两回：作罢

    def test_the_director_is_told_the_reader_has_already_read_it(self):
        from tianlong.narrative import prompts
        gm = {"drift": ["正文「x」，账上：y"], "upcoming": [], "ruling": [], "fate": 50, "odds": [], "agendas": [], "hidden": [], "secrets": [],
              "passes": [], "secret_ways": [], "arts": [], "grants": [], "places": []}
        text = prompts.render_backstage(gm)
        self.assertIn("不可推翻", text)
        self.assertIn("不能当没说过", text)


if __name__ == "__main__":
    unittest.main()
