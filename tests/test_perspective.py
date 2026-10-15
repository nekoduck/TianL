"""
[INPUT]: 依赖 tianlong.world 的 perspective / adjudicate / menu / effects 与 data/canon 原著世界，tianlong.engine 的 Game；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——43 回对局(王侠墨)里「主角都没认识钟灵，开口就是钟姑娘」逐条转成离线验收：
          开局只识出身带来的人与当众主持剑会的掌门、无名之辈不在开局常识里、叫出不知其名之人(全名或姓+称谓)即违例、
          NPC 不知主角姓名却叫「王兄」即违例、自报家门与当面点名让在场者听来名字、编剧从主角视角看世界(只剩外貌叫法、不露身份)、
          交编剧之前与成文之后确定性地把漏出的名字换成叫法与泛称(编剧熟读原著，名字可能是它自己带来的)、编剧与玩家用的叫法落得回实体；
          v12 A5：编剧提示词全文(连同【选项槽位】)没有未识之人的真名与「图谋」，C 槽读看得见的眼下之事；C2 外号示例是占位、赶来即到跟前
          v13：同上，自报家门要玩家起意（SELF）
[POS]: tests 的认知视角验证——v3 方案 P0-2「视角即上下文」的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tests.test_engine import StubLLM, WRITER, director
from tianlong.engine import Game
from tianlong.world import adjudicate, effects, perspective, rag
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
        self.assertEqual([f.entity for f in r.soft if f.kind == "name"], ["player"])   # v14 仍是违例，但掩码会换成「兄台」：记软违例、不交返工
        self.assertEqual([f for f in r.hard if f.kind == "name"], [])

    def test_names_are_heard_when_given(self):
        w = self.w
        r = judge(w, plan(("钟灵", "钟灵笑道：「我叫钟灵，你呢？」", [], "player"),
                          ("player", "你拱手道：「在下王侠墨，钟姑娘好。」", [])), {adjudicate.SELF})   # v13 主角的姓名只有玩家起意自报才入账
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
        self.assertNotIn("钟灵", prompt)                                               # v12 A5：排在后面的【选项槽位】也一样

    def test_slots_speak_from_the_heros_eyes(self):
        w = self.w
        self.assertTrue(w.graph.get("段誉", "agenda"))                                # 段誉怀着图谋，主角却不识他
        w.graph.set("段誉", "intent", "护着钟灵离开练武厅")
        game = Game(w, StubLLM(director()))
        game.act("看")
        prompt = game.llm.writer_prompts[-1]
        for word in ("段誉", "钟灵", "图谋"):                                         # 第 1 回：槽位直呼「段誉的图谋」，视锥里却只有青衫少年
            self.assertNotIn(word, prompt)
        self.assertIn("青衫少年眼下：护着大眼圆脸的少女离开练武厅", prompt)             # C 槽读看得见的眼下之事



class DirectorPromptTest(unittest.TestCase):
    """v12 C2：外号示例不拿原著人物(17 次导演调用都带着「钟灵→绿衫少女」，第 11 回导演照写「那乘马绿衫少女」而没有事码)；写明「赶来」即到跟前。"""

    def test_the_example_is_a_placeholder_and_arrival_means_at_hand(self):
        from tianlong.narrative import prompts
        from tianlong.world import rag
        system = prompts._director_system(rag.build(World.create("测")))
        self.assertNotIn("绿衫少女", system)
        self.assertIn("<正文里的叫法>", system)
        self.assertIn("赶来就是来到主角跟前、伸手可及", system)                        # 第 11 回：崖下山道间的人用了赶来，账上却到了崖上


class IdentityTest(unittest.TestCase):
    """v12 P1-5 识名不等于识底：第 2 回段誉自报「小生段誉」，同回编剧视锥里就是「段誉｜镇南王世子｜大理国」与「段正淳—父子—段誉」，
    选项出了「借机结交世子」；第 15 回又出「报出大理段氏之名以骇退帮众」。"""

    def test_a_name_alone_does_not_bare_the_background(self):
        from tianlong.narrative import prompts
        w = World.create("测")
        perspective.learn(w, "player", "段誉")                                         # 只报了姓名
        view = perspective.veil(w, rag.build(w))
        duan = next(p for p in view["people"] if p["name"] == "段誉")
        self.assertEqual((duan["title"], duan["faction"]), ("来历未明", "门派不明"))
        text = prompts.render(view)
        for word in ("镇南王世子", "大理国", "段正淳—父子—段誉"):
            self.assertNotIn(word, text)
        zuo = next(p for p in view["people"] if p["name"] == "左子穆")
        self.assertEqual(zuo["title"], "无量剑东宗掌门")                                 # 当众主持的掌门：识名即识底

    def test_fame_reads_the_end_of_each_title(self):
        from tianlong.world import ledger
        g = World.create("测").graph
        fame = lambda p: ledger.famous(g.nodes[p])
        self.assertFalse(fame("小兰"))                                                  # 王家婢女：中间带个王字不算闻名
        self.assertFalse(fame("段誉"))                                                  # 世子不在词表里
        self.assertTrue(fame("段正淳") and fame("司空玄"))                              # 皇太弟、镇南王；神农帮帮主
        self.assertTrue(fame("刀白凤") and fame("宗赞王子"))                              # 镇南王妃、吐蕃王子：补了王妃、王子

    def test_saying_the_title_with_the_name_bares_it(self):
        from tianlong.world import effects
        w = World.create("测")
        ops = perspective.hear(w, "段誉拱手道：「小生大理段誉，乃镇南王世子。」", "段誉")
        self.assertEqual(ops[0].get("know"), "身份")                                     # 报名的那一句里说破了来历
        w.turn = {}
        effects.apply(w, ops, "director")
        self.assertTrue(perspective.identified(w, "段誉"))
        w2 = World.create("测")
        effects.apply(w2, perspective.hear(w2, "段誉拱手道：「小生段誉。」", "段誉"), "director")
        self.assertTrue(perspective.knows(w2, "player", "段誉"))
        self.assertFalse(perspective.identified(w2, "段誉"))                            # 只报姓名：识名不识底
        effects.apply(w2, [{"做": "识名", "谁": "段誉", "知": "身份"}], "director")
        self.assertTrue(perspective.identified(w2, "段誉"))                              # 名字早已知道：说破来历仍是一件事

    def test_an_old_save_without_the_ledger_loads(self):
        w = World.create("测")
        perspective.learn(w, "player", "段誉")
        old = w.dump()
        old["player"].pop("identified")
        w2 = World.from_dump(old)
        self.assertTrue(perspective.identified(w2, "段誉"))                              # 旧档：叫得出名字的人照旧当作识底
        self.assertTrue(perspective.identified(w2, "司空玄"))

if __name__ == "__main__":
    unittest.main()
