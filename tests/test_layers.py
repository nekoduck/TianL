"""
[INPUT]: 依赖 tianlong.world 的 World / lod / rag / adjudicate、tianlong.narrative.prompts（以 data/canon 编译出的真实原著世界为对象，离线）
[OUTPUT]: 分层导演(v11)的离线验收——远处没有自由发挥的导演：
          一日之内的场外推演只演自由之人的小事(去留一步且不进主角近旁、伤病境况、心思、同处一地的擒放结怨与寻常之物的递交)，
          功力武学、门庭名分、地理陈设、人群、暗藏之物与要紧之物、原著要用的人与物、叫人赶来，一概落不了；
          史官只裁剪原著(照抄、删去、减弱)，越界即照原著或作罢；场外的说法说破隐情、把尚未发生的原著说成已成之事即只记核实过的后果；
          原著要把人送到主角这里，交近处导演演出来人
[POS]: tests 的分层导演组：审计里坐实的八处漏洞(场外送出暗藏的秘籍、加功力、传武学、改门派、瞬移到主角屋里、抹掉地点、揭开暗藏、立结义)逐条成为用例
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import unittest

from tianlong.narrative import prompts
from tianlong.world import adjudicate, lod, rag
from tianlong.world.world import World


def report(where, event, result, *ops):
    return {"where": where, "event": event, "result": result, "effects": list(ops)}


def canon(w, eid):
    return next(e for e in w.canon if e["id"] == eid)


class CharterTest(unittest.TestCase):
    """场外推演能写什么(world/effects._charter)：直接走写入通道，只看权限本身。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.done.extend(e["id"] for e in self.w.canon if "秦红棉" in lod._cast(e))  # 秦红棉成为可以走动的自由之人
        self.scope = lod.lod1_scope(self.w)[1]

    def lands(self, *ops):
        w = copy.deepcopy(self.w)
        applied, rejected = w.apply(list(copy.deepcopy(ops)), "lod1", self.scope)
        return w, bool(applied), [why for _, why in rejected]

    def test_nobody_grows_or_changes_station_offstage(self):
        for op in ({"op": "add", "id": "秦红棉", "key": "power", "value": 40},
                   {"op": "push", "id": "秦红棉", "key": "skills", "value": "六脉神剑"},
                   {"op": "set", "id": "秦红棉", "key": "faction", "value": "星宿派"},
                   {"op": "set", "id": "秦红棉", "key": "title", "value": "星宿派弟子"}):
            _, ok, why = self.lands(op)
            self.assertFalse(ok, op)
            self.assertIn("场外推演改不得", why[0])

    def test_nobody_is_summoned_or_slips_into_the_players_room(self):
        w, ok, why = self.lands({"op": "arrive", "id": "秦红棉"})
        self.assertFalse(ok)
        self.assertEqual(w.graph.get("秦红棉", "location"), "木婉清居所")                 # 不再瞬移到主角屋里
        self.assertIn("近处导演", why[0])
        _, ok, why = self.lands({"op": "set", "id": "南海鳄神", "key": "location", "value": "剑湖宫·宫门"})
        self.assertFalse(ok)                                                               # 一步就到主角近旁：那是近处导演的事
        self.assertIn("主角近旁", why[0])
        w, ok, _ = self.lands({"op": "set", "id": "南海鳄神", "key": "location", "value": "无量后山"})
        self.assertTrue(ok)                                                                # 往别处走一步照走
        _, ok, why = self.lands({"op": "set", "id": "南海鳄神", "key": "location", "value": "大理城"})
        self.assertFalse(ok)                                                               # 两日路程：场外一日只走一程
        self.assertIn("赶不到", why[0])

    def test_geography_crowds_and_hidden_or_precious_things_stay_put(self):
        for op in ({"op": "set", "id": "无量山", "key": "state", "value": {"exists": False}},   # 把无量山从地图上抹掉
                   {"op": "set", "id": "北冥神功卷轴", "key": "holder", "value": "南海鳄神"},   # 暗藏的秘籍
                   {"op": "set", "id": "北冥神功卷轴", "key": "hidden", "value": False},        # 揭开暗藏
                   {"op": "set", "id": "神仙姊姊玉钏", "key": "holder", "value": "南海鳄神"},   # 宝物
                   {"op": "set", "id": "通天草", "key": "location", "value": "无量后山"}):      # 场外只让人递交东西
            w, ok, why = self.lands(op)
            self.assertFalse(ok, op)
        self.assertTrue(w.graph.get("北冥神功卷轴", "hidden"))

    def test_no_sworn_bonds_and_no_reaching_across_places(self):
        _, ok, why = self.lands({"op": "link", "src": "秦红棉", "dst": "云中鹤", "rel": "结义"})
        self.assertFalse(ok)
        self.assertIn("名分", why[0])
        _, ok, why = self.lands({"op": "link", "src": "秦红棉", "dst": "云中鹤", "rel": "擒获"})
        self.assertFalse(ok)                                                               # 秦红棉在木婉清居所，云中鹤在无量山
        self.assertIn("不在一处", why[0])
        _, ok, why = self.lands({"op": "set", "id": "鳄尾鞭", "key": "holder", "value": "秦红棉"})
        self.assertFalse(ok)                                                               # 接的人不在东西所在之处
        self.assertIn("接不过来", why[0])

    def test_small_things_still_happen(self):
        w, ok, _ = self.lands({"op": "set", "id": "鳄尾鞭", "key": "holder", "value": "云中鹤"})
        self.assertTrue(ok)                                                                # 同在无量山：递一件兵刃
        self.assertEqual(w.graph.get("鳄尾鞭", "holder"), "云中鹤")
        w, ok, _ = self.lands({"op": "set", "id": "秦红棉", "key": "mood", "value": "恨极"},
                              {"op": "set", "id": "秦红棉", "key": "intent", "value": "去找段正淳问个明白"},
                              {"op": "add", "id": "秦红棉", "key": "hp", "value": -10})
        self.assertTrue(ok)
        _, ok, _ = self.lands({"op": "link", "src": "秦红棉", "dst": "player", "rel": "起了疑心"})
        self.assertTrue(ok)                                                                # 听了传闻对主角起了心思：不必同处


class CanonRailTest(unittest.TestCase):
    """原著要用的人与物(world/lod._foreign)：走真实的战报落账。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def absorb(self, *reports):
        return [e["summary"] for e in lod.absorb(self.w, list(reports), lod.lod1_scope(self.w)[1])]

    def test_people_the_canon_still_needs_cannot_be_carried_off(self):
        told = self.absorb(report("无量山", "南海鳄神擒人", "南海鳄神擒下云中鹤",
                                  {"op": "link", "src": "南海鳄神", "dst": "云中鹤", "rel": "擒获"}))
        self.assertEqual(told, [])                                                         # 云中鹤后面还有原著
        self.assertFalse(any(e["rel"] == "擒获" for e in self.w.graph.edges))

    def test_things_the_canon_still_needs_cannot_change_hands(self):
        w = self.w
        w.canon.append({"id": "测·取药", "order": 10 ** 6, "day": w.clock.day + 90, "where": "无量山", "weight": 1, "public": True,
                        "actors": ["司空玄"], "requires": [["通天草", "location", "无量山"]], "effects": [], "summary": "司空玄来取通天草"})
        w.graph.set("通天草", "holder", "南海鳄神")                                        # 南海鳄神拿着原著要用的药草
        w.graph.set("通天草", "location", None)
        self.absorb(report("无量山", "南海鳄神送药", "南海鳄神把通天草给了云中鹤",
                           {"op": "set", "id": "通天草", "key": "holder", "value": "云中鹤"}))
        self.assertEqual(w.graph.get("通天草", "holder"), "南海鳄神")

    def test_free_people_can_still_quarrel_side_by_side(self):
        w = self.w
        w.done.extend(e["id"] for e in w.canon if "云中鹤" in lod._cast(e) or "南海鳄神" in lod._cast(e))
        told = self.absorb(report("无量山", "南海鳄神擒人", "南海鳄神擒下云中鹤",
                                  {"op": "link", "src": "南海鳄神", "dst": "云中鹤", "rel": "擒获"}))
        self.assertEqual(len(told), 1)
        self.assertTrue(any(e["rel"] == "擒获" for e in w.graph.edges))


class ChronicleTest(unittest.TestCase):
    """史官只裁剪原著(world/lod._vet)。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.player.set("location", "大理城")

    def ready(self):  # 段誉赴万劫谷求解药的前提都在
        self.w.graph.set("段誉", "status", "wounded")
        self.w.graph.link("司空玄", "钟灵", "扣为人质")
        return canon(self.w, "段誉赴万劫谷求解药")

    def test_a_faithful_cut_lands_as_written(self):
        ev = self.ready()
        told = lod.settle(self.w, ev, {"happens": True, "summary": "段誉独自赶往无量后山求药",
                                       "effects": [*ev["effects"], {"op": "set", "id": "段誉", "key": "mood", "value": "焦急"}]},
                          "chronicle")
        self.assertEqual(told["summary"], "段誉独自赶往无量后山求药")
        self.assertEqual(self.w.graph.get("段誉", "location"), "无量后山")

    def test_an_invention_falls_back_to_the_canon_rail(self):
        ev = self.ready()
        told = lod.settle(self.w, ev, {"happens": True, "summary": "段誉转投后山求药，路遇南海鳄神",
                                       "effects": [*ev["effects"], {"op": "set", "id": "南海鳄神", "key": "location", "value": "无量后山"}]},
                          "chronicle")
        self.assertEqual(told["summary"], ev["summary"])                                    # 原著没有的事写不出：照原著
        self.assertEqual(self.w.graph.get("南海鳄神", "location"), "无量山")
        self.assertEqual(self.w.graph.get("段誉", "location"), "无量后山")

    def test_an_invention_on_a_broken_event_comes_to_nothing(self):
        ev = canon(self.w, "段誉赴万劫谷求解药")                                           # 段誉安好、钟灵未被扣：前提已破
        told = lod.settle(self.w, ev, {"happens": True, "summary": "段誉被南海鳄神一掌打死",
                                       "effects": [{"op": "set", "id": "段誉", "key": "status", "value": "dead"}]}, "chronicle")
        self.assertIsNone(told)
        self.assertNotEqual(self.w.graph.get("段誉", "status"), "dead")

    def test_a_passing_mood_for_a_bystander_is_dropped_not_fatal(self):
        ev = self.ready()
        told = lod.settle(self.w, ev, {"happens": True, "summary": "段誉独自赶往无量后山求药",
                                       "effects": [{"做": "前往", "谁": "段誉", "到": "无量后山"},             # 写成事码也认
                                                   {"op": "set", "id": "南海鳄神", "key": "mood", "value": "得意"}]},
                          "chronicle")
        self.assertEqual(told["summary"], "段誉独自赶往无量后山求药")                    # 照史官，不退回原著
        self.assertNotEqual(self.w.graph.get("南海鳄神", "mood"), "得意")                  # 旁人的心境丢掉

    def test_a_death_may_soften_into_a_wound(self):
        w = self.w
        ev = canon(w, "木婉清射杀平婆婆")
        told = lod.settle(w, ev, {"happens": True, "summary": "平婆婆中箭重伤",
                                  "effects": [{"op": "set", "id": "平婆婆", "key": "status", "value": "wounded"}]}, "chronicle")
        self.assertIsNotNone(told)
        self.assertEqual(w.graph.get("平婆婆", "status"), "wounded")


class SpoilerTest(unittest.TestCase):
    """场外的说法会变成传闻：说破隐情、把尚未发生的原著说成已成之事，只记核实过的后果。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.done.extend(e["id"] for e in self.w.canon if "秦红棉" in lod._cast(e))

    def absorb(self, result):
        move = {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"}
        return [e["summary"] for e in lod.absorb(self.w, [report("木婉清居所", "秦红棉下山", result, move)],
                                                    lod.lod1_scope(self.w)[1])]

    def test_a_secret_is_not_spread_as_news(self):
        self.assertEqual(self.absorb("秦红棉往万劫谷·谷外树林去，逢人便说木婉清是她亲生的女儿"),
                         ["秦红棉前往万劫谷·谷外树林"])

    def test_the_future_is_not_spread_as_news(self):
        self.assertEqual(self.absorb("秦红棉往万劫谷·谷外树林去，一路听说容子矩已经死了"), ["秦红棉前往万劫谷·谷外树林"])

    def test_plain_news_is_kept(self):
        self.assertEqual(self.absorb("秦红棉穿林往万劫谷·谷外树林去"), ["秦红棉下山：秦红棉穿林往万劫谷·谷外树林去"])

    def test_the_chronicler_is_held_to_the_same_sieve(self):
        w = self.w
        w.player.set("location", "大理城")
        w.graph.set("段誉", "status", "wounded")
        w.graph.link("司空玄", "钟灵", "扣为人质")
        ev = canon(w, "段誉赴万劫谷求解药")
        told = lod.settle(w, ev, {"happens": True, "summary": "段誉赶往无量后山求药，原来段延庆才是他的生父",
                                  "effects": ev["effects"]}, "chronicle")
        self.assertNotIn("生父", told["summary"])
        self.assertTrue(adjudicate.spoilers(w, "段延庆才是段誉的生父"))
        self.assertFalse(adjudicate.spoilers(w, "段誉赶往无量后山求药"))


class ArrivalTest(unittest.TestCase):
    """原著要把人送到主角这里：交近处导演演出来人，远处的结算不把人悄悄塞到他跟前。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.done.extend(e["id"] for e in self.w.canon if e["day"] <= self.w.clock.day)

    def due(self, dest):
        w = self.w
        ev = {"id": "测·来人", "order": 0, "day": w.clock.day, "where": "大理城", "weight": 1, "public": True,
              "actors": ["秦红棉"], "requires": [], "summary": "秦红棉动身寻人",
              "effects": [{"op": "set", "id": "秦红棉", "key": "location", "value": dest}]}
        w.canon.insert(0, ev)
        return ev

    def test_a_canon_arrival_is_staged_by_the_near_director(self):
        ev = self.due(self.w.here)
        offstage, staged = lod.split_due(self.w)
        self.assertIs(staged, ev)
        self.assertEqual(offstage, [])
        gm = rag.backstage(self.w, stage=staged, upcoming=[])
        self.assertEqual(gm["stage"]["coming"], ["秦红棉"])
        self.assertIn("秦红棉要来到主角这里", prompts.render_backstage({**gm, "brief": ""}))

    def test_a_canon_move_elsewhere_stays_offstage(self):
        ev = self.due("万劫谷·谷外树林")
        offstage, staged = lod.split_due(self.w)
        self.assertIsNone(staged)
        self.assertIn(ev, [e for e, _ in offstage])


class PromptTest(unittest.TestCase):
    def test_the_offstage_prompts_spell_out_the_same_rules(self):
        system, _ = prompts.simulator("元祐六年二月", 1, [], [])
        for phrase in ("功力、武学、门派", "不往主角那里去", "两人须在一处", "秘籍、信物、宝物与暗藏之物递交不得", "不说破任何隐情"):
            self.assertIn(phrase, system)
        w = World.create("测")
        system, _ = prompts.chronicler(canon(w, "段誉赴万劫谷求解药"), [], [], [], [])
        for phrase in ("只能从【原著结果】里挑", "前提都在就照原著，前提已破就作罢"):
            self.assertIn(phrase, system)


if __name__ == "__main__":
    unittest.main()
