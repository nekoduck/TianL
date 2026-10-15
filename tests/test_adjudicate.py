"""
[INPUT]: 依赖 tianlong.world 的 adjudicate / situation / growth / menu / lod / lexicon / rag 与 data/canon 原著世界，tianlong.engine 的 Game；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——80 回对局暴露的病灶逐条转成离线验收：
          焦点检索让导演看见解药在谁身上、器物近似名归一、同伴随主角移动且过不去的关留下、救人即解押、未了之事谓词满足自动收束、
          原著救人之事在人已获救时不再照演、一人一回合只听一处调遣(v11 导演与日程两处：原著与场外剧情同一条轨道)、纠缠之人的场外原著不照本宣科、
          研习分阶段(一刻调息不涨功力)、吸功双边结算、导演不得直接加功力、赶来须路程够、场景实体的归属与禁令(v8 物件一概不立)、
          拍文写了变化却无指令即违例并交导演返工、返工仍不成立则整拍作废、只追认获救(解押)、漏写的随行交导演写明、
          越权之举不演而成下回合选项、打断须有来源、选项出口检查(够不着/说破隐情/须回应)、伏笔记账、回放基准量得出旧对局的违例；
          v12 选项链路(OptionChainTest)：授意标记不当选项对象(A1)；TopicTest：话题里的人不验可达、眼前的遗体够得着、对象栏认人群叫法(A2)；DedupeTest：对象相同且文字相近才去重(A3)；ReplyTest：须回应只认收尾时仍悬着的话、按优先级合并(A4)
[POS]: tests 的裁决层验证——「LLM 提议，世界裁决，文字只渲染已成立之事」的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_engine import StubLLM, WRITER
from tianlong.engine import Game
from tianlong.world import adjudicate, growth, lexicon, lod, menu, perspective, rag, situation
from tianlong.world.world import World

GO = lambda dest: {"op": "set", "id": "player", "key": "location", "value": dest}


def plan(*beats, **kw):
    """一份 v2 导演提议：beats 为 (who, text, ops[, to])。"""
    return {"beats": [{"who": b[0], "text": b[1], "ops": b[2], "to": b[3] if len(b) > 3 else None} for b in beats],
            "question": kw.get("question", {"ask": "", "state": "open", "by": None}), "spawn": kw.get("spawn", []),
            "pace": kw.get("pace", "片刻"), "canon": {"unfolds": True, "why": ""}, "tension": "起", "options": []}


def judge(w, p, aim=(), **kw):
    w.turn = {"minutes": w.clock.minutes(p["pace"])}
    return adjudicate.judge(w, p, set(aim), **kw)


class SituationTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")

    def test_the_director_sees_who_holds_the_antidote(self):
        aim = adjudicate.targets(self.w, "去万劫谷向甘宝宝求闪电貂解药")       # 近似名也认得
        self.assertIn("闪电貂毒解药", aim)
        focus = rag.backstage(self.w, aim=aim)["focus"]
        self.assertIn("闪电貂毒解药：由甘宝宝随身（甘宝宝在万劫谷）", focus)

    def test_companions_walk_with_the_player(self):
        r = judge(self.w, plan(("player", "你携段誉出了大厅", [{"op": "link", "src": "段誉", "dst": "player", "rel": "随行"}, GO("无量山")])))
        self.assertEqual(r.hard, [])
        self.assertEqual((self.w.here, self.w.graph.get("段誉", "location")), ("无量山", "无量山"))
        self.assertIn("段誉", situation.party(self.w))

    def test_a_companion_can_catch_up_in_a_later_beat(self):
        r = judge(self.w, plan(("player", "你夺门而出", [GO("无量山")]),
                               ("段誉", "段誉随后跟上", [{"op": "link", "src": "段誉", "dst": "player", "rel": "随行"}])))
        self.assertEqual((r.hard, self.w.graph.get("段誉", "location")), ([], "无量山"))
        self.assertEqual([f.kind for f in judge(self.w, plan(("乔峰", "乔峰与你结伴", [{"op": "link", "src": "乔峰", "dst": "player", "rel": "随行"}]))).hard],
                         ["void", "absent"])                                          # 不在身边的人跟不上来

    def test_a_written_but_unrecorded_companion_goes_back_to_the_director(self):
        r = judge(self.w, plan(("player", "你拉着段誉奔出大厅", [GO("无量山")])))      # 漏写随行：词表不替导演挪人，交返工
        self.assertEqual([f.kind for f in r.hard], ["follow"])
        self.assertEqual(self.w.graph.get("段誉", "location"), "剑湖宫·练武厅")

    def test_rescue_frees_the_hostage_and_settles_the_quest(self):
        g = self.w.graph
        g.link("司空玄", "钟灵", "扣为人质")
        self.w.player.push("threads", "救出钟灵")
        situation.track(self.w, "救出钟灵", ["钟灵"], [["司空玄", "!扣为人质", "钟灵"]])
        judge(self.w, plan(("player", "你护着钟灵", [{"op": "link", "src": "钟灵", "dst": "player", "rel": "随行"}])))
        self.assertEqual(situation.captors(self.w, "钟灵"), [])                       # 随你同行即脱离拘押
        self.assertEqual(situation.settle(self.w), ["救出钟灵"])                       # 谓词满足，自动了结
        self.assertNotIn("救出钟灵", self.w.player["threads"])

    def test_canon_rescue_does_not_replay_once_the_hostage_is_free(self):
        ev = next(e for e in self.w.canon if e["id"] == "甘宝宝托段誉向段家求援")
        self.w.player.set("location", "大理城")
        self.w.graph.set("段誉", "status", "wounded")
        self.assertIn(["司空玄", "~扣为人质", "钟灵"], ev["requires"])               # 情境前提已并入原著
        self.assertTrue(lod.broken(self.w, ev))                                      # 钟灵从未被扣，求援无从谈起
        self.w.graph.link("司空玄", "钟灵", "扣为人质")
        self.assertFalse(lod.broken(self.w, ev))

    def test_one_person_one_dispatcher_per_turn(self):
        w = self.w
        w.turn = {"days": 1}
        w.apply([{"op": "set", "id": "段誉", "key": "location", "value": "剑湖宫·内堂"}], "director")  # 导演先挪动了他
        _, rejected = w.apply([{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"}], "canon")
        self.assertEqual(rejected[0][1], "段誉此日已另有去向")                        # 第 67 回：三处同时挪动段誉
        _, rejected = w.apply([{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"}], "derived", {"无量后山", "段誉"})
        self.assertIn("主角身边", rejected[0][1])                                      # 场外剧情(v11)动不了主角身边的人

    def test_entangled_people_leave_the_canon_rails(self):
        ev = next(e for e in self.w.canon if e["id"] == "段誉坠入无量山谷")
        self.w.player.set("location", "大理城")
        self.w.graph.set("段誉", "status", "wounded")
        self.assertFalse(lod.broken(self.w, ev))
        self.w.player.push("threads", "护送段誉回大理")
        situation.track(self.w, "护送段誉回大理", ["段誉"])
        self.assertTrue(any("同行或系于主角未了之事" in r for r in lod.dirt(self.w, ev)))

    def test_spawned_extras_need_a_home_and_cannot_impersonate(self):
        w = self.w
        _, why = situation.spawn(w, {"kind": "thing", "name": "神功卷轴"})
        self.assertIsNotNone(why)                                                     # 与原著之物相混
        nid, why = situation.spawn(w, {"kind": "thing", "name": "火折"})
        self.assertEqual((nid, why), (None, situation.FORGE))                        # v8：器物在创世时布齐，剧情不新造物件
        self.assertFalse(w.graph.has("火折"))
        for s in list(w.graph.where(type="group", faction="神农帮")):  # 世界底座(v11 23)在无量山一带本有神农帮的人群：先撤走
            del w.graph.nodes[s]
        _, why = situation.spawn(w, {"kind": "group", "name": "神农帮帮众", "faction": "神农帮"}, embargo={"神农帮"})
        self.assertIn("尚未到此", why)                                                # 原著近事里尚未到场的势力
        _, why = situation.spawn(w, {"kind": "group", "name": "少林僧众", "faction": "少林派"})
        self.assertIsNotNone(why)                                                     # 少林远在千里之外


class GrowthTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.graph.set("北冥神功卷轴", "location", self.w.here)

    def test_a_quarter_hour_of_study_is_not_a_breakthrough(self):
        p0 = self.w.player["power"]
        judge(self.w, plan(("player", "你展卷细读", [{"op": "study", "id": "player", "value": "北冥神功卷轴"}]), pace="瞬息"), {"北冥神功卷轴"})
        self.assertEqual(self.w.player["power"], p0)
        judge(self.w, plan(("player", "你潜心研读", [{"op": "study", "id": "player", "value": "北冥神功"}]), pace="一顿饭"), {"北冥神功"})
        self.assertEqual(self.w.player["power"], p0 + 12)                             # 初窥：兑现四成
        self.assertIn("北冥神功", self.w.player["skills"])

    def test_the_director_cannot_hand_out_power(self):
        r = judge(self.w, plan(("player", "你功力大进", [{"op": "add", "id": "player", "key": "power", "value": 30}])))
        self.assertTrue(any("功力由系统结算" in v for v in r.void))

    def test_draining_is_computed_on_both_sides(self):
        w = self.w
        w.player.push("skills", "北冥神功")
        p0, k0 = w.player["power"], w.graph.get("龚光杰", "power")
        r = judge(w, plan(("player", "你扣住龚光杰脉门，他内力源源涌来", [{"op": "drain", "id": "player", "value": "龚光杰"}])), aim={"龚光杰"})
        loss = k0 - w.graph.get("龚光杰", "power")
        self.assertEqual((loss, w.player["power"] - p0), (round(k0 * 0.3), round(loss * 0.5)))
        self.assertEqual(r.hard, [])


class AdjudicateTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")

    def test_a_far_away_person_cannot_simply_arrive(self):
        r = judge(self.w, plan(("乔峰", "乔峰大步走进厅来", [{"op": "arrive", "id": "乔峰"}])))
        self.assertEqual(self.w.graph.get("乔峰", "location") == self.w.here, False)
        self.assertTrue(any("赶不到" in f.message for f in r.hard))

    def test_written_change_without_an_op_is_a_violation(self):
        r = judge(self.w, plan(("龚光杰", "龚光杰一剑刺死褚师弟", [])))                 # 写了死，账上没死
        self.assertEqual([f.kind for f in r.hard], ["kill"])
        self.assertIn("褚师弟身亡", adjudicate.brief(self.w, r)[0])

    def test_the_system_does_not_decide_for_the_player(self):
        w = self.w
        w.graph.set("北冥神功卷轴", "location", w.here)
        r = judge(w, plan(("player", "你顺手将卷轴揣入怀中", [{"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"}])),
                  aim={"段誉"})
        self.assertNotIn("北冥神功卷轴", w.player["inventory"])                       # 第 72 回：顺手夺草
        self.assertEqual(r.candidates, ["取走北冥神功卷轴"])
        self.assertEqual(r.beats, [])

    def test_an_interruption_needs_a_source(self):
        r = judge(self.w, plan(("段誉", "段誉正要开口", []), question={"ask": "打听", "state": "interrupted", "by": "王家追兵"}))
        self.assertEqual([f.kind for f in r.hard], ["interrupt"])
        r = judge(self.w, plan(("段誉", "段誉正要开口", []), question={"ask": "打听", "state": "interrupted", "by": "龚光杰"}))
        self.assertEqual(r.hard, [])

    def test_backstage_terms_and_secrets_are_flagged(self):
        r = judge(self.w, plan(("钟灵", "命运骰落在高处，钟灵笑嘻嘻地看你", [])))
        self.assertEqual([f.kind for f in r.soft], ["backstage"])
        r = judge(self.w, plan(("钟灵", "原来段正淳便是钟灵的生父", [])))
        self.assertIn("secret", [f.kind for f in r.hard])


class RepairLoopTest(unittest.TestCase):
    """导演写了变化而没写指令：返工一次；返工仍不成立，整拍作废，化作失败的事实交编剧。"""

    def test_repair_fixes_the_omission(self):
        bad = {"beats": [{"who": "龚光杰", "text": "龚光杰一剑刺死褚师弟", "ops": []}], "pace": "瞬息"}
        good = {"beats": [{"who": "龚光杰", "text": "龚光杰一剑刺死褚师弟",
                           "ops": [{"op": "set", "id": "褚师弟", "key": "status", "value": "dead"}]}], "pace": "瞬息"}

        class Learns(StubLLM):
            def json(self, system, user, max_tokens=0):
                if "账本对不上" in system:
                    self.repairs = getattr(self, "repairs", 0) + 1
                    return good
                return super().json(system, user, max_tokens)

        llm = Learns({"说书人与导演": bad, "小说家": WRITER})
        game = Game(World.create("测"), llm)
        turn = game.act("看")
        self.assertEqual(llm.repairs, 1)
        self.assertEqual((game.world.graph.get("褚师弟", "status"), turn["void"]), ("dead", []))

    def test_a_beat_that_stays_wrong_is_voided(self):
        llm = StubLLM({"说书人与导演": {"beats": [{"who": "龚光杰", "text": "龚光杰一剑刺死褚师弟", "ops": []}], "pace": "瞬息"},
                       "小说家": WRITER})
        game = Game(World.create("测"), llm)
        turn = game.act("看")
        self.assertNotEqual(game.world.graph.get("褚师弟", "status"), "dead")
        self.assertTrue(turn["void"][0].startswith("龚光杰一剑刺死褚师弟——未曾发生"))
        self.assertNotIn("【已成立之事】", llm.writer_prompts[-1])


class MenuTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")

    def test_options_are_checked_at_the_exit(self):
        w = self.w
        picked = menu.check(w, [{"text": "向乔峰讨教降龙掌", "targets": ["乔峰"]},          # 主角不知乔峰下落
                                {"text": "问钟灵生父是不是段正淳", "targets": ["钟灵"]},      # 说破未揭的隐情
                                {"text": "向段誉请教易经", "targets": ["段誉"]}],
                            addressed=["左子穆"])
        texts = [t for t, _ in picked]
        self.assertEqual(len(texts), 3)
        self.assertIn("向段誉请教易经", texts)
        self.assertNotIn("向乔峰讨教降龙掌", texts)
        self.assertFalse(any("段正淳" in t for t in texts))
        self.assertIn("回应左子穆", texts)                                              # 有人刚对你开口

    def test_selected_option_carries_its_targets(self):
        llm = StubLLM({"说书人与导演": {"beats": [{"who": "player", "text": "你走上前", "ops": []}], "pace": "瞬息"},
                       "小说家": "正文\n===\n梗概：看\n选项：\n1. 与钟灵说话｜对象：钟灵\n2. 去剑湖宫｜对象：剑湖宫\n3. 歇一歇\n伏笔：远处有女子娇叱｜期限：2\n传言：无"})
        game = Game(World.create("测"), llm)
        turn = game.act("看")
        self.assertEqual(turn["options"], ["与大眼圆脸的少女说话", "去剑湖宫", "歇一歇"])  # v6 选项也从主角的视角说：叫不出的名字换成叫法
        self.assertEqual(game.menu["与大眼圆脸的少女说话"], ["钟灵"])                    # 对象仍是她：授意不失准
        self.assertEqual(game.world.player["hooks"][0]["text"], "远处有女子娇叱")
        game.act("与大眼圆脸的少女说话")
        self.assertIn("【焦点·主角此举所指之物的真相（主角未必知道）】\n- 钟灵", llm.director_prompts[-1])
        self.assertIn("【未兑现的伏笔】\n- 远处有女子娇叱", llm.director_prompts[-1])


class OptionChainTest(unittest.TestCase):
    """v12 选项链路：15 回实录里 8 回编剧原拟的一项被换掉——授意标记、话题里的人、对象相同即去重、过时的须回应。"""

    def setUp(self):
        self.w = World.create("测")

    def test_marks_are_not_option_targets(self):
        w = self.w                                                                      # A1：大喝、打听、写信不是够不着的对象
        picked = menu.check(w, [{"text": "大喝一声，喝止众人", "targets": []},
                                {"text": "向段誉打听来历", "targets": ["段誉"]},
                                {"text": "写一封信给左子穆", "targets": ["左子穆"]}])
        self.assertEqual([t for t, _ in picked], ["大喝一声，喝止众人", "向段誉打听来历", "写一封信给左子穆"])
        self.assertFalse(any(adjudicate.marked(i) for _, ids in picked for i in ids))   # 交还引擎的对象不带标记
        self.assertNotIn(adjudicate.TRADE, adjudicate.targets(w, "大喝一声"))
        self.assertNotIn(adjudicate.TRADE, adjudicate.targets(w, "顺段誉佛理大喝神农帮滥杀必遭天谴"))
        self.assertIn(adjudicate.TRADE, adjudicate.targets(w, "向店小二要一壶黄酒"))     # 真要花钱的照旧是授意

    def test_shopping_needs_a_shop(self):
        from tests.test_founding import INN, STREET, at, go, shichen
        w = self.w
        texts = [t for t, _ in menu.check(w, [{"text": "向店小二买一壶黄酒", "targets": []}])]
        self.assertNotIn("向店小二买一壶黄酒", texts)                                    # 练武厅里没有铺子
        self.assertIn("卖个破绽诱敌", [t for t, _ in menu.check(w, [{"text": "卖个破绽诱敌", "targets": []}])])
        w = at(World.create("测"), STREET)
        go(w, INN)
        shichen(w, "辰")
        texts = [t for t, _ in menu.check(w, [{"text": "向店小二打听近来江湖上的新鲜事", "targets": []}])]
        self.assertIn("向店小二打听近来江湖上的新鲜事", texts)                          # 进了客栈：打听照收
        self.assertIn("向店小二买一壶黄酒", [t for t, _ in menu.check(w, [{"text": "向店小二买一壶黄酒", "targets": []}])])


def cliff(w=None):
    """日志第 12–15 回的崖上场面：主角在澜沧江边高崖被神农攻山帮众围住，段誉在眼前，手里有剑架青钢剑，马五德留在剑湖宫。"""
    from tianlong.world import crowd, effects
    w = w or World.create("测")
    w.player.set("location", "澜沧江边高崖")
    crowd.relocate(w, "神农攻山帮众", "澜沧江边高崖")
    w.graph.link("神农攻山帮众", "player", "围攻")
    w.graph.set("段誉", "location", "澜沧江边高崖")
    effects._hand(w, "剑架青钢剑", holder="player")
    return w


class TopicTest(unittest.TestCase):
    """A2：只对物理对象验可达，话题放行；眼前的遗体够得着；对象栏的叫法先查名表。"""

    def setUp(self):
        self.w = World.create("测")

    def texts(self, *opts):
        return [t for t, _ in menu.check(self.w, [{"text": t, "targets": list(o)} for t, *o in opts])]

    def test_a_name_in_talk_is_not_a_touch(self):
        self.w.graph.set("马五德", "location", "大理城")
        self.assertIn("报马五德之名求饶", self.texts(("报马五德之名求饶",)))               # 第 13 回：报他的名头，不是要碰到他
        self.assertNotIn("报马五德之名求饶", self.texts(("报马五德之名求饶", "马五德")))  # 对象栏写了他：他就是物理对象
        self.assertNotIn("向乔峰讨教降龙掌", self.texts(("向乔峰讨教降龙掌", "乔峰")))
        self.assertNotIn("向乔峰讨教降龙掌", self.texts(("向乔峰讨教降龙掌", "降龙十八掌")))  # 讨教要人在跟前，对象写武学也一样

    def test_a_body_in_front_can_be_searched(self):
        from tianlong.world import effects
        w = self.w
        w.graph.set("容子矩", "location", "剑湖宫·练武厅")
        effects.apply(w, [{"op": "set", "id": "容子矩", "key": "status", "value": "dead"}], "director")
        self.assertIn("搜检容子矩的遗体", self.texts(("搜检容子矩的遗体",)))              # 第 7 回：遗体就在厅上
        w.graph.set("容子矩", "location", "无量山")
        self.assertNotIn("搜检容子矩的遗体", self.texts(("搜检容子矩的遗体",)))

    def test_the_target_column_knows_a_crowds_handle(self):
        w = cliff(self.w)
        self.assertIn("神农攻山帮众", adjudicate.targets(w, "挥剑虚晃抢步贴近段誉身旁", ["段誉", "神农帮众"]))
        texts = self.texts(("报马五德之名求饶", "神农帮众"), ("挥剑拼死劈开缺口", "神农帮众", "剑架青钢剑"),
                           ("佯称深谷藏有灵药", "神农帮众", "段誉"))
        self.assertEqual(texts, ["报马五德之名求饶", "挥剑拼死劈开缺口", "佯称深谷藏有灵药"])  # 日志第 13 回：三项全部入选


class DedupeTest(unittest.TestCase):
    """A3：对象相同且文字相近才去重——场面上只剩一两个实体时，不同路数的选项不再互相顶掉。"""

    def test_same_target_different_moves_stay(self):
        texts = TopicTest.texts(self, ("挟持段誉保命", "段誉", "神农帮众"), ("弃剑伏地求饶", "剑架青钢剑", "神农帮众"),
                                ("劝段誉讲和脱身", "段誉", "神农帮众"))
        self.assertEqual(texts, ["挟持段誉保命", "弃剑伏地求饶", "劝段誉讲和脱身"])         # 日志第 14 回
        texts = TopicTest.texts(self, ("伏在岩后屏息观望", "澜沧江边高崖"), ("攀藤摸下高崖探看虚实", "澜沧江边高崖"))
        self.assertEqual(texts[:2], ["伏在岩后屏息观望", "攀藤摸下高崖探看虚实"])            # 日志第 10 回
        texts = TopicTest.texts(self, ("挺身护住段誉", "段誉"), ("挺身护住段誉退后", "段誉"))
        self.assertIn("挺身护住段誉", texts)
        self.assertNotIn("挺身护住段誉退后", texts)                                     # 同一件事换个说法：只留一项

    def setUp(self):
        self.w = cliff()


class ReplyTest(unittest.TestCase):
    """A4：须回应只认收尾时仍悬着的话；候选、回应、此后按优先级合并，不按下标覆盖。"""

    def setUp(self):
        self.w = World.create("测")

    def opts(self, *texts, scales=()):
        return [{"text": t, "targets": [], **({"scale": scales[i]} if scales else {})} for i, t in enumerate(texts)]

    def test_candidate_and_reply_both_stay_with_one_of_the_writers(self):
        w = self.w
        mine = ("护着段誉退向宫门", "向左子穆陈说利害", "抓起剑架上的青钢剑防身")
        texts = [t for t, _ in menu.check(w, self.opts(*mine), addressed=["干光豪"], candidates=["取走辛双清的长剑"])]
        self.assertIn("取走辛双清的长剑", texts)                                         # 越权候选
        self.assertIn(f"回应{perspective.handle(w, '干光豪')}", texts)                  # 须回应
        self.assertEqual(texts[0], mine[0])                                             # 编剧原拟至少留一项

    def test_the_one_that_gives_way_repeats_a_target(self):
        mine = ("挟持段誉保命", "劝段誉讲和离去", "抓起剑架上的青钢剑防身")
        texts = [t for t, _ in menu.check(self.w, self.opts(*mine), addressed=["干光豪"])]
        self.assertEqual(texts[:2], ["挟持段誉保命", "抓起剑架上的青钢剑防身"])       # 让位的是对象重复的那一项，不是固定的第三项

    def test_three_wants_insert_only_two(self):
        mine = ("挟持段誉保命", "向左子穆陈说利害", "抓起剑架上的青钢剑防身")
        later = [("寻个僻静处歇息养伤（两个时辰）", [])]
        texts = [t for t, _ in menu.check(self.w, self.opts(*mine, scales=("此刻", "此刻", "机缘")), addressed=["干光豪"],
                                          candidates=["取走辛双清的长剑"], later=later)]
        self.assertEqual(sum(t in mine for t in texts), 1)                              # 强插至多两项
        self.assertNotIn(later[0][0], texts)                                            # 第三条要求作罢

    def test_only_the_last_two_beats_still_hang(self):
        w = self.w
        r = judge(w, plan(("player", "你上前一步", []), ("龚光杰", "龚光杰喝道：「你是什么来历？」", [], "player"),
                          ("左子穆", "左子穆喝止龚光杰", [], "龚光杰"), (None, "容子矩一声闷哼，倒在地上", []),
                          ("左子穆", "左子穆转向辛双清拱手", [], "辛双清")))
        self.assertEqual(adjudicate.hanging(w, r), [])                                  # 第 3、4、8 回：那句话之后又过了三四拍
        mine = ("护着段誉退向宫门", "向左子穆陈说利害", "抓起剑架上的青钢剑防身")
        self.assertEqual([t for t, _ in menu.check(w, self.opts(*mine), adjudicate.hanging(w, r))], list(mine))
        w = World.create("测")
        r = judge(w, plan(("player", "你上前一步", []), ("左子穆", "左子穆道：「阁下请坐。」", [], "player"),
                          ("干光豪", "干光豪喝道：「你是何人？报上名来！」", [], "player"), ("马五德", "马五德向左子穆赔笑", [], "左子穆")))
        self.assertEqual(adjudicate.hanging(w, r), ["干光豪"])
        first = [{"text": "冷冷瞪了持剑少年一眼", "targets": ["干光豪"]}, {"text": "向左子穆陈说利害", "targets": []},
                 {"text": "抓起剑架上的青钢剑防身", "targets": []}]
        self.assertEqual([t for t, _ in menu.check(w, first, adjudicate.hanging(w, r))][1:], ["向左子穆陈说利害", "抓起剑架上的青钢剑防身"])
        mine = ("挟持段誉保命", "劝段誉讲和离去", "抓起剑架上的青钢剑防身")
        texts = [t for t, _ in menu.check(w, self.opts(*mine), adjudicate.hanging(w, r), said=adjudicate.lines_to_player(w, r))]
        self.assertIn(f"答{perspective.handle(w, '干光豪')}所问", texts)                # 回应的措辞按那一句的主题：盘问即答其所问

    def test_who_has_walked_off_is_not_owed_a_reply(self):
        def turn(ops):
            llm = StubLLM({"说书人与导演": {"beats": [{"who": "干光豪", "to": "player", "text": "干光豪喝道：「哼，你等着！」", "ops": ops}],
                                       "pace": "瞬息"}})
            Game(World.create("测"), llm).act("看")
            return llm.writer_prompts[-1]
        self.assertIn("【须回应】", turn([]))
        self.assertNotIn("【须回应】", turn([{"做": "前往", "谁": "干光豪", "到": "无量山"}]))  # 回合末已不在眼前


class ReplayBaselineTest(unittest.TestCase):
    def test_the_old_80_turn_log_still_measures_its_violations(self):
        import json
        from tools import replay
        found = replay.audit(json.loads(replay.FIXTURE.read_text("utf-8")))
        self.assertIn(74, [n for n, _ in found["drain"]])                               # 第 74 回：吸功未入账
        self.assertIn(79, [n for n, _ in found["absent"]])                              # 第 79 回：不在场的段誉开口
        self.assertTrue(lexicon.leaks("命运骰落在八十七"))


if __name__ == "__main__":
    unittest.main()
