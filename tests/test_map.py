"""
[INPUT]: 依赖 tianlong.world 的 adjudicate / effects / menu / perspective / rag / scenery / settle / situation / body / lexicon、tianlong.story 的 choices / timing、
         tianlong.narrative 的 agents，tests.test_adjudicate 的 judge / plan 与 data/canon 原著世界
[OUTPUT]: unittest 用例——v14 文与图同一份：v13 一局 52 回实录与 v13 引擎上两局 20 回逐回合体检(run1、run2)抓到的病逐条转成离线验收：
          NearTest(近旁认父：玉壁与谷底同一处所，站在玉壁揭得开谷底的暗路)、AheadTest(去处一瞥与机关实情)、NameTest(器物名认回、驳回给正解)、
          FoundTest(顺手之物：本回合揭出、玩家此举指着那一处才算授意)、SettleBenignTest(读者读到的拿起无主之物照记)、OverreachTest(越权的物理之举先交返工)、
          OptionTest(景物够得着、兜底不重样、久悬之事不兜底、歇息不连喂、候选不收报名与所求、不截半句、漏写「对象：」也认)、
          FaceTest(器物叫法去掉所在地、身况同口径、情绪标注不入正文、暗路补记、掉了血不是安然无恙)、StateTest(一时气氛不入现状、一记耳光不算负伤、赶路不是歇息)、
          WordTest(两字人名撞常用词、进境的否定、简称不连着、等到月出)；
          run3(人物戏多的一局)：PeopleTest(手边的毒药即是那一味毒、走开而去处说不出从眼前划掉、同一屋里才听得见、登门见得着主人、放下缺省为持有者)、
          LedgerTest(账房看得见伤势、伤势与查无此人的说法不作数、伙计领路不是江湖事、挣名字五桩才了结)、OptionMoreTest(为救某人是话题、四字概括写明对谁、报名作废只去名字)；
          run4(验收局)：ForgedMoreTest(拍文的「石上药瓶」就是同一拍事码里的断肠散、刚服下的仍说得出名字也仍在返工清单、不在眼前的人手里的不算)、
          QuestTest(换个说法的同一件事只记一条、撂狠话不必硬塞回应而问句仍要、服下的毒够得着)、GuideTest(引路的人随主角进了片区仍在眼前、选项不报节点全名)、JourneyTest(场记写明上回合选的赶路、要去的地方写 前往)、MaidTest(婢女的外号不用胡须秃顶)
[POS]: tests 的 v14 验收——导演对着真图写戏，驳回给正解，被否决的事不以文字活下来，读者读到的平常之举照记
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tianlong.narrative import agents
from tianlong.story import choices, timing
from tianlong.world import adjudicate, body, effects, lexicon, menu, perspective, rag, scenery, settle, situation, venue
from tianlong.world.clock import PER_DAY, PER_SHICHEN
from tianlong.world.world import World

VAULT, MIRROR, CAVE, FLOOR, WALL = "琅嬛福地·玉像石室", "琅嬛福地·铜镜后室", "琅嬛福地", "无量山·谷底", "无量玉壁"
BOOK = "北冥神功卷轴"


def at(loc: str) -> World:
    w = World.create("测")
    w.player.set("location", loc)
    venue.settle(w)  # 场所的近景(房间、伙计、陈设)要主角走近才布好
    w.turn = {}
    return w


class NearTest(unittest.TestCase):
    def test_the_jade_wall_is_part_of_the_valley_floor(self):
        w = at(WALL)
        self.assertIn(FLOOR, situation.near(w))                                       # 52 回局：玉壁与谷底不同根，揭不开暗路，原地编出一座石室
        self.assertNotIn(CAVE, situation.near(w))                                     # 隔着机关的洞府仍不是近旁
        ok, bad = effects.apply(w, [{"做": "揭开", "路": [FLOOR, CAVE]}], "director")
        self.assertTrue(ok and not bad)
        self.assertNotIn("剑湖宫", situation.near(at("无量后山")))                    # 不连成一片：剑湖宫与后山各是一处


class AheadTest(unittest.TestCase):
    def test_the_director_sees_where_the_hero_is_going(self):
        w = at(FLOOR)
        lines = "\n".join(scenery.ahead(w, [CAVE]))
        self.assertIn("卧室石床", lines)                                                # run1 第 11 回：入口厅里没有玉像
        self.assertNotIn("玉像（", lines.split("暗门")[0])
        self.assertIn(f"暗门·{MIRROR}→{VAULT}", lines)                                 # 玉像在暗门之后，找法写明
        gm = rag.backstage(w, aim={CAVE})
        self.assertTrue(gm["ahead"])
        self.assertIn("未找到·找法", gm["mechanism"])
        self.assertIn("不得编造", gm["mechanism"])
        self.assertEqual(scenery.ahead(w, [WALL]), [])                                # 近旁的去处已在【近旁各处】里

    def test_nothing_hidden_means_nothing_to_find(self):
        self.assertIn("暗门暗道：没有", rag.mechanism(at("无量后山")))


class NameTest(unittest.TestCase):
    def test_a_long_name_finds_the_scroll_and_a_refusal_says_where_it_is(self):
        w = at(CAVE)
        self.assertEqual(effects.resolve(w, "北冥神功兼凌波微步帛卷"), BOOK)             # run1 第 12 回认不回，返工把奇遇演没了
        _, bad = effects.apply(w, [{"做": "拿取", "物": "北冥神功兼凌波微步帛卷"}], "director")
        self.assertIn(f"在{VAULT}", bad[0][1])
        self.assertIn("暗藏着", bad[0][1])


class FoundTest(unittest.TestCase):
    def kneel(self, aim, deed=""):
        w = at(VAULT)
        w.turn = {"deed": deed}
        r = adjudicate.judge(w, plan(("player", "蒲团破裂，你从夹层里抽出一卷帛卷", [{"做": "揭开", "物": BOOK}, {"做": "拿取", "物": BOOK}])), set(aim))
        return w, r

    def test_what_the_chosen_act_uncovers_may_be_picked_up(self):
        w, r = self.kneel({"神仙姊姊蒲团"})                                           # run1 第 16 回：磕首千遍，帛卷就在脚边
        self.assertIn(BOOK, w.player["inventory"])
        self.assertEqual((r.candidates, [f.kind for f in r.hard]), ([], []))

    def test_a_search_may_pick_up_what_it_finds(self):
        w, _ = self.kneel(set(), deed="四下翻找有无藏着的东西")
        self.assertIn(BOOK, w.player["inventory"])

    def test_an_unrelated_act_does_not_pocket_a_hidden_thing(self):
        w, r = self.kneel({"段誉"}, deed="劝段誉歇一歇")                              # 第 72 回：顺手夺草仍是越权
        self.assertNotIn(BOOK, w.player["inventory"])
        self.assertEqual(r.candidates, [f"取走{BOOK}"])
        self.assertEqual([f.kind for f in r.hard], ["overreach"])                     # 越权的物理之举先交返工
        self.assertEqual(adjudicate.doomed(r), {})


class SettleBenignTest(unittest.TestCase):
    def test_what_the_reader_saw_the_hero_pick_up_is_recorded(self):
        w = at(MIRROR)
        text = "你随手拿起石桌上那面生满铜绿的旧铜镜。"
        bill = {"changes": [{"据": "你随手拿起石桌上那面生满铜绿的旧铜镜", "谁": "player",
                             "ops": [{"做": "拿取", "物": "琅嬛福地·铜镜后室·石桌铜镜"}]}]}
        applied, rifts = settle.commit(w, bill, text, aim=set())
        self.assertIn("琅嬛福地·铜镜后室·石桌铜镜", w.player["inventory"])
        self.assertEqual(rifts, [])

    def test_taking_from_a_person_still_needs_the_players_word(self):
        w = at("剑湖宫·练武厅")
        text = "你一把夺过段誉手中的折扇。"
        bill = {"changes": [{"据": "你一把夺过段誉手中的折扇", "谁": "player", "ops": [{"做": "夺取", "物": "段誉折扇", "自": "段誉"}]}]}
        applied, rifts = settle.commit(w, bill, text, aim=set())
        self.assertNotIn("段誉折扇", w.player["inventory"])
        self.assertTrue(rifts)


class OptionTest(unittest.TestCase):
    def test_scenery_is_within_reach(self):
        w = at("琅嬛福地·书房")
        picked = menu.check(w, [{"text": "细查书架", "targets": ["琅嬛福地·书房·木书架列"], "scale": "此刻"},
                                {"text": "四下走走", "targets": [], "scale": "机缘"}])
        self.assertIn("细查书架", [t for t, _ in picked])                            # run1 第 18 回落选

    def test_fallbacks_do_not_repeat_what_is_already_there(self):
        w = at(MIRROR)
        picked = [t for t, _ in menu.check(w, [{"text": "静坐室中歇息调匀气息（半个时辰）", "targets": [], "scale": "此后"}])]
        self.assertEqual(sum(1 for t in picked if menu.KINDRED[0].search(t)), 1)    # run1 第 13 回「静坐歇息」与「歇息」并列

    def test_a_stale_errand_is_not_a_fallback(self):
        w = at(FLOOR)
        w.player.set("threads", ["探明神农帮虚实回报"])
        w.player.set("quests", {"探明神农帮虚实回报": {"about": [], "done_when": None, "since": 1, "touched": 1}})
        w.player.set("turn", 20)
        self.assertFalse([t for t, _ in menu._fallbacks(w, []) if t.startswith("继续")])  # 52 回局困在谷底十几回都给这一项

    def test_rest_is_not_fed_every_turn(self):
        w = at(FLOOR)
        w.player.set("hp", 50)
        self.assertTrue(any("歇息养伤" in t for t, _ in choices.later(w)))
        menu.offer(w, [("寻个僻静处歇息养伤（两个时辰）", [])])
        self.assertFalse(any("歇息养伤" in t for t, _ in choices.later(w)))           # 近两回合给过就不再喂

    def test_name_and_goal_are_not_forced_in_as_options(self):
        w = at("剑湖宫·练武厅")
        r = judge(w, plan(("player", "你朗声道：「在下测，愿为贵派效力！」", [{"做": "识名", "谁": "player"}, {"做": "所求", "为": "扬名立万"}], "左子穆")),
                  adjudicate.targets(w, "劝青衫少年莫惹祸"))
        self.assertEqual(r.candidates, [])                                            # run1 第 3、4 回「改写你的所求」「报上姓名」
        self.assertTrue(any("报上姓名" in v for v in r.void))

    def test_option_words_are_never_cut_mid_word(self):
        raw = ("正文\n===\n梗概：x\n选项：\n1. 借着厅中众人分神，弯腰拾起地上碎银（耗时片刻）｜对象：碎银｜尺度：此后\n"
               "2. 设法撬开书案下上了锁的抽屉｜内堂书案｜尺度：此刻\n3. 大喊神农帮杀进来了以乱其心并奔向练武厅辛双清处求援｜尺度：机缘\n")
        texts = [o["text"] for o in agents._page(raw)["options"]]
        self.assertTrue(texts[0].startswith("借着厅中众人分神，弯腰拾起地上碎银"))      # run1 第 2 回「拾起地上碎」
        self.assertEqual(agents._page(raw)["options"][1], {"text": "设法撬开书案下上了锁的抽屉", "targets": ["内堂书案"], "scale": "此刻"})
        self.assertTrue(texts[2].endswith("求援"))


class FaceTest(unittest.TestCase):
    def test_a_furnished_thing_goes_by_its_own_name(self):
        w = at(MIRROR)
        mirror = "琅嬛福地·铜镜后室·石桌铜镜"
        self.assertEqual(perspective.thing(w, mirror), "石桌铜镜")                     # run1 第 14 回身况与补记露出内部 id
        effects.apply(w, [{"做": "拿取", "物": mirror}], "director")
        self.assertIn("持有石桌铜镜", "".join(t["text"] for t in rag.condition(w)))

    def test_mood_marks_never_reach_the_page(self):
        w = at(FLOOR)
        w.turn = {"moments": [{"here": FLOOR, "ears": [], "bodies": []}], "beats_at": []}
        gate = settle.Gate(w)
        gate.feed("你〔狂喜〕难抑，捧起帛卷（此刻情绪：狂喜）。\n")
        gate.close()
        self.assertNotIn("狂喜", gate.text)                                            # run1 第 17 回

    def test_a_secret_road_note_does_not_name_unknown_places(self):
        w = at(FLOOR)
        before = settle.glance(w)
        effects.apply(w, [{"做": "揭开", "路": [FLOOR, CAVE]}], "director")
        notes = [c["text"] for c in settle.delta(w, before)]
        self.assertTrue(any("暗路" in n for n in notes))
        self.assertFalse(any("琅嬛" in n for n in notes))                              # run1 第 10 回：主角还不知那是琅嬛福地
        self.assertEqual(settle.unwritten([c for c in settle.delta(w, before) if c["key"].startswith("secret:")],
                                          "你推开石门，门后一道石阶直通地底。", None), [])  # 正文写到了门与阶，就不补记

    def test_any_lost_blood_is_not_unhurt(self):
        w = at(FLOOR)
        w.player.set("hp", 80)
        self.assertEqual(body.wound(w)[0], "皮肉之伤")                                  # run2 第 7 回肩头皮肉翻卷、身况写安然无恙
        w.player.set("hp", 100)
        self.assertEqual(body.wound(w)[0], "安然无恙")


class StateTest(unittest.TestCase):
    def test_a_passing_mood_is_not_a_lasting_state(self):
        w = at("剑湖宫·练武厅")
        ok, _ = effects.apply(w, [{"做": "现状", "对": "剑湖宫·练武厅", "为": "两宗弟子握紧长剑，气氛肃杀已极"}], "director")
        self.assertEqual(ok, [])                                                      # run1 第 3、7 回
        ok, _ = effects.apply(w, [{"做": "现状", "对": "剑湖宫·练武厅", "为": "大门已被东宗弟子拔剑封锁"}], "director")
        self.assertTrue(ok)

    def test_the_road_is_not_a_rest(self):
        w = at("澜沧江")
        w.player.set("hp", 55)
        body.recover(w, PER_DAY, PER_DAY)
        self.assertEqual(w.player["hp"], 55)                                           # run4 第 11 回：带毒赶了一整日路，气血不该回三十点
        body.recover(w, PER_DAY, PER_DAY // 2)
        self.assertGreater(w.player["hp"], 55)                                         # 走半日、歇半日，歇的那半日照养

    def test_a_slap_is_not_a_wound(self):
        w = World.create("测")
        ev = next(e for e in w.canon if e["id"] == "龚光杰掌掴段誉")
        self.assertFalse(any(op.get("key") == "status" for op in ev["effects"]))      # run1 第 2 回一记耳光掉了 40 点血


class WordTest(unittest.TestCase):
    def test_a_two_character_name_does_not_eat_ordinary_words(self):
        w = at(VAULT)
        self.assertEqual(perspective.mask(w, "空荡荡的石室里只有沉闷的回响"), "空荡荡的石室里只有沉闷的回响")  # run2 第 18 回「石大辽的汉子」
        self.assertEqual(perspective.mask(w, "你知道清楚了么"), "你知道清楚了么")

    def test_failing_to_enter_is_not_entering(self):
        for text in ("你闭目苦思良久，仍难参透入门法门。", "你全然摸不着入门的门径。", "你未能入门。"):
            self.assertEqual(lexicon.mastery(text), [], text)                         # run2 第 19、20 回
        self.assertEqual(lexicon.mastery("你苦练一个时辰，终于入门。"), ["入门"])

    def test_a_shortened_name_is_the_thing_in_hand(self):
        w = at(WALL)
        effects.apply(w, [{"op": "set", "id": "玉壁剑影图", "key": "hidden", "value": False}], "director")
        w.player.push("inventory", "玉壁剑影图")
        w.graph.set("玉壁剑影图", "holder", "player")
        self.assertFalse(adjudicate.forged(w, "剑图"))                                  # run2 第 11 回白返工一次
        self.assertTrue(adjudicate.forged(w, "密图"))

    def test_waiting_for_the_moon_runs_the_clock_to_nightfall(self):
        w = at(WALL)
        w.clock.tick = (w.clock.tick // PER_DAY) * PER_DAY + 5 * PER_SHICHEN         # 巳时
        floor, why = timing.claim(w, plan(("player", "你缩在石隙里苦挨", [])), "寻处隐蔽山石静坐调息苦挨至月出")
        self.assertEqual(floor, 4 * PER_SHICHEN)                                      # 到酉时入夜(run2 第 11 回正文写月出，时钟停在申时)
        self.assertIn("等到入夜", why)


class PeopleTest(unittest.TestCase):
    def mountain(self):
        w = at("无量山")
        situation.enlist(w, ["司空玄", "段誉", "钟灵"])
        for p in ("司空玄", "段誉", "钟灵"):
            w.graph.set(p, "location", "无量山")
        return w

    def test_the_poison_in_hand_is_the_poison_given(self):
        w = self.mountain()
        effects.apply(w, [{"做": "境况", "对": "段誉", "添": "中毒"}], "director")
        self.assertIn("断肠散", body.poisons(w, "段誉"))                              # run3 第 7 回只记了一个「中毒」字串
        effects.apply(w, [{"做": "境况", "对": "司空玄", "添": "中毒"}], "director")
        self.assertEqual(body.poisons(w, "司空玄"), {})                               # 自己身上的毒、地上的莽牯朱蛤都不算

    def test_those_who_vanish_leave_the_hero_s_sight(self):
        w = self.mountain()
        effects.apply(w, [{"op": "link", "src": "司空玄", "dst": "钟灵", "rel": "扣为人质"}], "director")
        text = "汉子推搡着少女，招呼帮众隐入险峻密林深处，转瞬不见了踪影。"
        settle.commit(w, {"changes": [{"据": "招呼帮众隐入险峻密林深处，转瞬不见了踪影", "谁": "司空玄",
                                        "ops": [{"做": "前往", "谁": "司空玄", "到": "密林深处"}]}]}, text)
        self.assertEqual(situation.around(w), {"段誉"})                               # 押着的钟灵一并走开
        self.assertEqual(w.graph.get("司空玄", "location"), "无量山")                 # 人仍在这一片

    def test_a_word_in_the_hall_is_not_heard_at_the_gate(self):
        w = at("万劫谷·大厅")
        w.graph.set("段誉", "location", "万劫谷·大厅")
        effects.apply(w, [{"op": "link", "src": "段誉", "dst": "player", "rel": "随行"}], "director")
        self.assertIn("段誉", perspective.audience(w))
        self.assertNotIn("万劫谷·门丁", perspective.audience(w))                     # run3 第 13、18 回门房的人也「听见」了

    def test_the_mistress_is_at_home(self):
        w = at("万劫谷·大厅")
        self.assertIn("甘宝宝", situation.elsewhere(w))                               # run3 第 16~19 回谷主夫人一直不露面
        ok, bad = effects.apply(w, [{"做": "赶来", "谁": "甘宝宝"}], "director")
        self.assertTrue(ok and not bad)
        self.assertNotIn("南海鳄神", situation.elsewhere(at("无量山")))               # 不在自己家里的，原著戏份未到仍不露面

    def test_whoever_holds_it_puts_it_down(self):
        w = at("剑湖宫·练武厅")
        self.assertEqual(adjudicate.acts.normalize(w, {"做": "放下", "物": "龚光杰长剑"})["谁"], "龚光杰")  # 两局都缺省成主角、白返工


class LedgerTest(unittest.TestCase):
    def test_the_accountant_sees_the_hero_s_wound(self):
        w = at(FLOOR)
        w.player.set("hp", 90)
        self.assertIn("伤势：皮肉之伤", settle.books(w, "")["player"])               # run3 第 6 回「账上无伤」

    def test_health_and_missing_person_claims_are_not_rifts(self):
        w = at(FLOOR)
        text = "你身上的剑伤随风微痛。"
        _, rifts = settle.commit(w, {"rifts": [{"据": "你身上的剑伤随风微痛", "账上": "主角伤势为安然无恙，并无剑伤"}]}, text)
        self.assertEqual(rifts, [])                                                   # run3 第 11 回

    def test_a_servant_showing_the_way_is_not_news(self):
        from tianlong.engine import _newsworthy
        link = [{"op": "link", "src": "万劫谷·管家", "dst": "player", "rel": "随行"}]
        self.assertEqual(_newsworthy(link, 5, 0, staff={"万劫谷·管家"}), 0)         # run3 第 16 回管家引路成了一桩江湖事
        self.assertGreater(_newsworthy([{"op": "link", "src": "段誉", "dst": "player", "rel": "随行"}], 5, 0), 0)

    def test_a_name_takes_more_than_three_small_deeds(self):
        from tianlong.story import arc
        self.assertEqual(arc.FAMED, 5)


class OptionMoreTest(unittest.TestCase):
    def test_who_it_is_for_is_a_topic(self):
        w = at("万劫谷·大厅")
        w.graph.set("段誉", "location", "万劫谷·大厅")
        picked = [t for t, _ in menu.check(w, [{"text": "答言为救钟灵姑娘而来请见谷主", "targets": ["管家"], "scale": "此刻"},
                                                {"text": "主动提及钟灵被扣以探其神色", "targets": ["管家"], "scale": "机缘"}])]
        self.assertIn("答言为救钟灵姑娘而来请见谷主", picked)                          # run3 第 14、19 回落选
        self.assertIn("主动提及钟灵被扣以探其神色", picked)

    def test_a_four_word_summary_says_to_whom(self):
        w = at("万劫谷·大厅")
        w.graph.set("万劫谷·管家", "location", "万劫谷·大厅")
        opts = [{"text": "试探虚实", "targets": ["万劫谷·管家"], "scale": "此刻"}]
        picked = [t for t, _ in menu.check(w, opts)]
        self.assertIn("向管家试探虚实", picked)
        self.assertEqual(opts[0]["text"], "向管家试探虚实")                           # 引擎按改过的文字记尺度

    def test_a_voided_self_introduction_keeps_the_rest_of_the_speech(self):
        w = at("万劫谷·门房")
        r = judge(w, plan(("player", "你拱手道：「在下测，这位是舍弟杜誉。」", [{"做": "识名", "谁": "player"}], "万劫谷·管家")),
                  adjudicate.targets(w, "替段誉遮掩身份"))
        self.assertTrue(any("其余的话照说" in v for v in r.void))                    # run3 第 15 回连假名也略去了
        self.assertIn(adjudicate.SELF, adjudicate.targets(w, "抢先代段誉编造假姓名"))  # 话里说到姓名，通名也在其中

    def test_scenery_goes_by_its_own_name_for_the_writer(self):
        w = at("万劫谷·大厅")
        names = [f["name"] for f in perspective.veil(w, rag.build(w))["features"]]
        self.assertIn("厅案", names)                                                   # run3 第 17 回「万劫谷厅案」


class ForgedMoreTest(unittest.TestCase):
    def test_a_generic_word_for_the_poison_in_hand(self):
        w = PeopleTest().mountain()
        self.assertFalse(adjudicate.forged(w, "腥黑药丸"))                              # run3 第 7 回
        self.assertTrue(adjudicate.forged(w, "金创药"))                                # 有名有姓的另一味药仍是凭空
        w.player.push("inventory", "通天草")
        w.graph.set("通天草", "holder", "player")
        self.assertFalse(adjudicate.forged(w, "怀中异草"))                              # run3 第 9 回

    def test_the_beat_names_what_its_text_describes(self):
        w = PeopleTest().mountain()
        effects.apply(w, [{"做": "放下", "谁": "司空玄", "物": "断肠散"}], "director")  # 掷在山石上
        aim = adjudicate.targets(w, "抢步拾起山石上的断肠散替青衫少年服下")
        r = judge(w, plan(("player", "你抢步抓起石上药瓶，拔塞仰首吞下。",
                           [{"做": "拿取", "物": "断肠散（山石上）"}, {"做": "服用", "物": "断肠散"}])), aim)
        self.assertFalse([f for f in r.hard if f.kind in ("conjure", "unnamed")])     # run4 第 8 回：「石上药瓶」就是事码里的断肠散
        self.assertFalse(adjudicate.doomed(r))
        w2 = PeopleTest().mountain()
        effects.apply(w2, [{"做": "放下", "谁": "司空玄", "物": "断肠散"}], "director")
        r = judge(w2, plan(("player", "你抢步抓起石上的断肠散，拔塞仰首吞下。",
                            [{"做": "拿取", "物": "断肠散"}, {"做": "服用", "物": "断肠散"}])), aim)
        self.assertFalse([f for f in r.hard if f.kind in ("conjure", "unnamed")])     # 刚服下(经手)的断肠散仍是说得出名字的东西，不是凭空
        self.assertIn("断肠散", body.poisons(w, "player"))
        self.assertIn("断肠散", adjudicate.reach(w))                                  # 刚服下的照样在返工清单里
        self.assertNotIn("鳄嘴剪", adjudicate.reach(w))                               # 同在无量山而不在眼前的南海鳄神手里的不算


class GuideTest(unittest.TestCase):
    def test_whoever_leads_the_way_stays_in_sight(self):
        w = at("万劫谷·谷外树林")                                                      # 走近了才布好万劫谷的房间与伙计
        w.player.set("location", "万劫谷·门房")
        w.graph.set("万劫谷·管家", "location", "万劫谷·门房")
        self.assertIn("万劫谷·管家", situation.around(w))
        judge(w, plan(("万劫谷·管家", "管家在前引路，绕过影壁。", [{"做": "前往", "谁": "万劫谷·管家", "到": "万劫谷"}]),
                      ("player", "你随他入谷。", [{"做": "前往", "谁": "player", "到": "万劫谷"}])), adjudicate.targets(w, "随管家快步入内"))
        self.assertEqual(w.here, "万劫谷")
        self.assertIn("万劫谷·管家", situation.around(w))                              # run4 第 14 回：引路的管家没有「离开」
        self.assertNotIn("钟万仇", situation.around(w))                                # 谷里别的人照旧要被剧情带到跟前
        opts = [{"text": "随管家直入万劫谷·大厅", "targets": ["万劫谷·大厅"], "scale": "此刻"}]
        self.assertEqual(menu.check(w, opts)[0][0], "随管家直入大厅")                   # 选项不报节点全名


class JourneyTest(unittest.TestCase):
    def test_a_chosen_journey_is_walked(self):
        from tianlong.story import brief, scene
        w = at("万劫谷·谷外树林")
        w.player.set("location", "万劫谷·大厅")
        scene.begin(w)
        text = brief.compose(w, None, [], "此后", "强忍剧痛随段誉同奔大理王府（一日路程）")["text"]
        self.assertIn("同奔大理王府", text)                                            # run4 第 17 回：场记写明上回合选的是哪件事
        self.assertIn("写 前往 那里", text)                                             # 赶路就真走，别只走出门口
        self.assertNotIn("前往 那里", brief.compose(w, None, [], "此后", "盘膝调息一个时辰")["text"])


class MaidTest(unittest.TestCase):
    def test_a_maid_has_no_beard(self):
        w = at("大理城")
        w.player.set("location", "镇南王府")
        venue.settle(w)
        w.turn = {}
        ops = perspective.distinguish(w)
        maids = [op["value"] for op in ops if "婢女" in op["value"]]
        self.assertTrue(maids)
        self.assertFalse([m for m in maids if any(t in m for t in ("须", "秃", "络腮"))])  # run4 第 20 回「短须婢女」「秃顶婢女」


class QuestTest(unittest.TestCase):
    def test_the_same_errand_said_twice_is_one_thread(self):
        w = at("无量山")
        for goal in ("七日之内取来解药救下钟灵", "七日之内取来解药换回钟灵", "护送钟灵回万劫谷"):
            effects.apply(w, [{"op": "push", "id": "player", "key": "threads", "value": goal}], "director")
        self.assertEqual(w.player["threads"], ["七日之内取来解药救下钟灵", "护送钟灵回万劫谷"])  # run4 第 9 回同一件事记了两条

    def test_a_parting_threat_needs_no_forced_reply(self):
        w = PeopleTest().mountain()
        opts = [{"text": "追问万劫谷去路与信物", "targets": ["钟灵"], "scale": "此刻"},
                {"text": "携段誉兼程赶往大理城求医", "targets": ["大理城", "段誉"], "scale": "此后"},
                {"text": "问明万劫谷地界后径往澜沧江寻路", "targets": ["段誉"], "scale": "机缘"}]
        texts = [t for t, _ in menu.check(w, opts, ["司空玄"], said={"司空玄": "滚罢！七日后不见解药，连你二人一并收尸！"})]
        self.assertEqual(texts, [o["text"] for o in opts])                             # run4 第 9 回：狠话不必硬塞「回应神农帮的汉子」
        texts = [t for t, _ in menu.check(w, opts, ["司空玄"], said={"司空玄": "你这小子究竟是谁派来的？"})]
        self.assertTrue(any("神农帮" in t or "所问" in t for t in texts))               # 问句仍要回应

    def test_the_poison_inside_is_within_reach(self):
        w = PeopleTest().mountain()
        effects.apply(w, [{"做": "放下", "谁": "司空玄", "物": "断肠散"}], "director")
        judge(w, plan(("player", "你拾起断肠散吞下。", [{"做": "拿取", "物": "断肠散"}, {"做": "服用", "物": "断肠散"}])),
              adjudicate.targets(w, "拾起断肠散吞下"))
        self.assertTrue(menu._reachable(w, "断肠散", "就地运功强压断肠散毒性"))           # run4 第 10 回：毒在你身上，压毒的选项不该落选


if __name__ == "__main__":
    unittest.main()
