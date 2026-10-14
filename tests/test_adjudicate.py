"""
[INPUT]: 依赖 tianlong.world 的 adjudicate / situation / growth / menu / lod / lexicon / rag 与 data/canon 原著世界，tianlong.engine 的 Game；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——80 回对局暴露的病灶逐条转成离线验收：
          焦点检索让导演看见解药在谁身上、器物近似名归一、同伴随主角移动且过不去的关留下、救人即解押、未了之事谓词满足自动收束、
          原著救人之事在人已获救时不再照演、一人一回合只听一处调遣、纠缠之人的场外原著不照本宣科、
          研习分阶段(一刻调息不涨功力)、吸功双边结算、导演不得直接加功力、赶来须路程够、场景实体的归属与禁令(v8 物件一概不立)、
          拍文写了变化却无指令即违例并交导演返工、返工仍不成立则整拍作废、只追认获救(解押)、漏写的随行交导演写明、
          越权之举不演而成下回合选项、打断须有来源、选项出口检查(够不着/说破隐情/须回应)、伏笔记账、回放基准量得出旧对局的违例
[POS]: tests 的裁决层验证——「LLM 提议，世界裁决，文字只渲染已成立之事」的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_engine import StubLLM, WRITER
from tianlong.engine import Game
from tianlong.world import adjudicate, growth, lexicon, lod, menu, rag, situation
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
        w.graph.set("段誉", "location", "无量山")
        w.apply([{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"}], "canon")
        _, rejected = w.apply([{"op": "set", "id": "段誉", "key": "location", "value": "无量山"}], "lod1", {"无量山", "无量后山", "段誉"})
        self.assertEqual(rejected[0][1], "段誉此日已另有去向")                        # 第 67 回：三处同时挪动段誉

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
