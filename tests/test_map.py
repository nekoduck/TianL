"""
[INPUT]: 依赖 tianlong.world 的 adjudicate / effects / menu / perspective / rag / scenery / settle / situation / body / lexicon、tianlong.story 的 choices / timing、
         tianlong.narrative 的 agents，tests.test_adjudicate 的 judge / plan 与 data/canon 原著世界
[OUTPUT]: unittest 用例——v14 文与图同一份：v13 一局 52 回实录与 v13 引擎上两局 20 回逐回合体检(run1、run2)抓到的病逐条转成离线验收：
          NearTest(近旁认父：玉壁与谷底同一处所，站在玉壁揭得开谷底的暗路)、AheadTest(去处一瞥与机关实情)、NameTest(器物名认回、驳回给正解)、
          FoundTest(顺手之物：本回合揭出、玩家此举指着那一处才算授意)、SettleBenignTest(读者读到的拿起无主之物照记)、OverreachTest(越权的物理之举先交返工)、
          OptionTest(景物够得着、兜底不重样、久悬之事不兜底、歇息不连喂、候选不收报名与所求、不截半句、漏写「对象：」也认)、
          FaceTest(器物叫法去掉所在地、身况同口径、情绪标注不入正文、暗路补记、掉了血不是安然无恙)、StateTest(一时气氛不入现状、一记耳光不算负伤)、
          WordTest(两字人名撞常用词、进境的否定、简称不连着、等到月出)
[POS]: tests 的 v14 验收——导演对着真图写戏，驳回给正解，被否决的事不以文字活下来，读者读到的平常之举照记
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tianlong.narrative import agents
from tianlong.story import choices, timing
from tianlong.world import adjudicate, body, effects, lexicon, menu, perspective, rag, scenery, settle, situation
from tianlong.world.clock import PER_DAY, PER_SHICHEN
from tianlong.world.world import World

VAULT, MIRROR, CAVE, FLOOR, WALL = "琅嬛福地·玉像石室", "琅嬛福地·铜镜后室", "琅嬛福地", "无量山·谷底", "无量玉壁"
BOOK = "北冥神功卷轴"


def at(loc: str) -> World:
    w = World.create("测")
    w.player.set("location", loc)
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


if __name__ == "__main__":
    unittest.main()
