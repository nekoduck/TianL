"""
[INPUT]: 依赖 tianlong.world 的 World / lod / body / bond / effects / rag / graph 与 data/canon 原著世界，tianlong.engine 的 Game（离线 llm=None 结算场外原著），
         tianlong.narrative 的 prompts（后台成文），tests/test_engine 的 StubLLM / director（桩导演）
[OUTPUT]: unittest 用例——v5「连贯性」的离线验收，每一类对应 PR #2 review 里一条 P0：
          剧情前提与体征分开(原著宣告的负伤不被养伤抹掉、明写痊愈才消、读路径不写气血、原著主线离线连演不断)；
          一人一主(OneMasterTest)、场外说法对账(OffstageProseTest)、场外事务(TransactionTest)、近旁(NextDoorTest)、原著来要主角身边的人(FarewellTest)
[POS]: tests 的连贯性验证——36 回实录里「段誉不来」「剧情前后打架」的病灶在这里逐条成为用例；与 test_state(v4 状态层)、test_story(v4 故事层)互补
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import unittest

from tests.test_engine import StubLLM, director
from tianlong.engine import Game
from tianlong.narrative import prompts
from tianlong.world import body, bond, effects, graph, lod, rag
from tianlong.world.clock import PER_DAY
from tianlong.world.world import World

logging.disable(logging.WARNING)


def canon(w, eid):
    return next(e for e in w.canon if e["id"] == eid)


# ============================================================
#  P0-1 剧情前提与体征分开
# ============================================================
class PlightTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.player.set("location", "大理城")  # 主角远在大理：段誉的原著全在场外，主角一指不碰

    def test_a_canon_wound_outlives_the_healing(self):
        w = self.w
        effects.apply(w, [{"op": "set", "id": "段誉", "key": "status", "value": "wounded"}], "canon")
        body.recover(w, 2 * body.REST)
        self.assertEqual(w.graph.get("段誉", "status"), "alive")                      # 气血养好了，体征是安好
        self.assertTrue(graph.holds(w.graph, "段誉", "status", "wounded"))              # 剧情上的伤还在
        self.assertFalse(lod.broken(w, canon(w, "段誉坠入无量山谷")))                    # 坠崖的原著照样成立

    def test_only_a_written_recovery_heals_the_plot(self):
        w = self.w
        effects.apply(w, [{"op": "set", "id": "段誉", "key": "status", "value": "wounded"}], "canon")
        effects.apply(w, [{"op": "set", "id": "段誉", "key": "status", "value": "alive"}], "canon")
        self.assertFalse(graph.holds(w.graph, "段誉", "status", "wounded"))
        self.assertTrue(lod.broken(w, canon(w, "段誉坠入无量山谷")))

    def test_looking_at_someone_does_not_touch_his_blood(self):
        w = World.create("测")
        self.assertNotIn("hp", w.graph.nodes["段誉"])
        rag.build(w)
        rag.backstage(w)
        self.assertNotIn("hp", w.graph.nodes["段誉"])                                   # 读路径只读：看一眼不拖进全局养伤

    def test_the_canon_spine_survives_days_of_offstage_time(self):
        w, game = self.w, Game(self.w, llm=None)
        target = canon(w, "甘宝宝托段誉向段家求援")["day"]
        while w.clock.day <= target:
            w.turn = {}
            w.advance(PER_DAY // 2)
            body.recover(w, PER_DAY // 2)
            for ev, tier in lod.split_due(w)[0]:
                game._settle(ev, tier)
        told = {e["summary"] for e in w.truth.events}
        for eid in ("段誉赴万劫谷求解药", "段誉坠入无量山谷", "段誉发现琅嬛福地", "甘宝宝托段誉向段家求援"):
            self.assertIn(canon(w, eid)["summary"], told, eid)                          # v4 里这四桩全被养伤养断


# ============================================================
#  P0-2 一人一主：场外推演、原著结算与散文验真
# ============================================================
def report(where, event, result, *ops):
    return {"where": where, "event": event, "result": result, "effects": list(ops)}


class OneMasterTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_only_free_people_are_simulated(self):
        actors, scope = lod.lod1_scope(self.w)
        self.assertEqual(actors, ["秦红棉"])                     # 段誉在近旁归导演，木婉清、甘宝宝、钟万仇七日内有原著
        self.assertTrue({"段誉", "木婉清", "甘宝宝", "钟万仇"}.isdisjoint(scope))

    def test_people_next_door_belong_to_the_director(self):
        w = self.w
        w.done.extend(e["id"] for e in w.canon if "秦红棉" in lod._cast(e))  # 秦红棉再无原著之约
        w.graph.set("秦红棉", "location", "剑湖宫·练武厅")
        w.player.set("location", "剑湖宫")
        self.assertNotIn("秦红棉", lod.lod1_scope(w)[1])        # 喊一声就到的人，场外推演碰不得

    def test_people_who_met_the_player_wait_for_the_story(self):
        w = self.w
        bond.event(w, "秦红棉", 1.5, "你替她挡过一箭")
        self.assertNotIn("秦红棉", lod.lod1_scope(w)[1])

    def test_the_simulator_cannot_touch_the_canon_cast(self):
        w = self.w
        actors, scope = lod.lod1_scope(w)
        told = lod.absorb(w, [report("木婉清居所", "秦红棉寻仇", "一掌打死了甘宝宝",
                                     {"op": "set", "id": "甘宝宝", "key": "status", "value": "dead"},
                                     {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"},
                                     {"op": "set", "id": "秦红棉", "key": "mood", "value": "恨极"})], scope)
        self.assertEqual(told, [])                                                    # 心思变了，不成江湖事
        self.assertEqual(w.graph.get("甘宝宝", "status"), "alive")                     # 原著认领之人
        self.assertEqual(w.graph.get("秦红棉", "location"), "木婉清居所")               # 尚有原著之约，去向归原著
        self.assertEqual(w.graph.get("秦红棉", "mood"), "恨极")


class OffstageProseTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.done.extend(e["id"] for e in self.w.canon if "秦红棉" in lod._cast(e))  # 让秦红棉成为可以走动的自由之人
        self.scope = lod.lod1_scope(self.w)[1]

    def absorb(self, *reports):
        return [e["summary"] for e in lod.absorb(self.w, list(reports), self.scope)]

    def test_a_fall_without_a_move_is_not_news(self):
        told = self.absorb(report("木婉清居所", "秦红棉坠崖大难不死", "跌落崖下幸免于难，探寻谷底别寻出路",
                                  {"op": "set", "id": "秦红棉", "key": "intent", "value": "寻找出谷之路"}))
        self.assertEqual(told, [])                                                    # 36 回实录里「段誉坠崖」的传闻就是这样来的
        self.assertEqual(self.w.graph.get("秦红棉", "location"), "木婉清居所")

    def test_words_that_match_the_ledger_are_kept(self):
        told = self.absorb(report("木婉清居所", "秦红棉下山", "秦红棉穿林往万劫谷·谷外树林疾驰",
                                  {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"}))
        self.assertEqual(told, ["秦红棉下山：秦红棉穿林往万劫谷·谷外树林疾驰"])

    def test_a_wrong_destination_falls_back_to_facts(self):
        told = self.absorb(report("木婉清居所", "秦红棉远行", "秦红棉动身前往大理城",
                                  {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"}))
        self.assertEqual(told, ["秦红棉前往万劫谷·谷外树林"])

    def test_the_player_is_never_in_offstage_news(self):
        told = self.absorb(report("木婉清居所", "秦红棉追敌", "秦红棉与测一同前往万劫谷·谷外树林",
                                  {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"}))
        self.assertEqual(told, ["秦红棉前往万劫谷·谷外树林"])                          # 主角不在场：说法换成核实过的后果


class TransactionTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_standing_still_is_not_an_event(self):
        w = self.w
        applied, rejected = effects.apply(w, [{"op": "set", "id": "段誉", "key": "location", "value": "剑湖宫·练武厅"},
                                              {"op": "set", "id": "段誉", "key": "status", "value": "alive"}], "canon")
        self.assertEqual((applied, rejected), ([], []))                               # 「龚光杰前往剑湖宫·练武厅」不再成为传闻
        w.graph.nodes["段誉"][graph.PLIGHT] = True
        applied, _ = effects.apply(w, [{"op": "set", "id": "段誉", "key": "status", "value": "alive"}], "canon")
        self.assertEqual(len(applied), 1)                                             # 剧情上的伤明写治好，不是空话

    def test_a_canon_that_cannot_land_is_not_half_played(self):
        w = self.w
        w.player.set("location", "大理城")
        ev = canon(w, "段誉赴万劫谷求解药")
        effects.apply(w, [{"op": "set", "id": "段誉", "key": "status", "value": "wounded"}], "canon")
        w.graph.link("司空玄", "钟灵", "扣为人质")                                     # 前提都在
        self.assertFalse(lod.broken(w, ev))
        w.turn = {"movers": {"段誉": "director"}}                                     # 后果却落不了：此日已另有去向
        path, reasons = lod.verdict(w, ev, 2)
        self.assertEqual(path, "skip")
        self.assertTrue(any("落不了" in r for r in reasons))

    def test_a_chronicle_lands_whole_or_not_at_all(self):
        w = self.w
        w.player.set("location", "大理城")
        ev = canon(w, "段誉赴万劫谷求解药")
        torn = {"happens": True, "summary": "段誉转投后山求药，路遇南海鳄神",
                "effects": [{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"},
                            {"op": "set", "id": "南海鳄神", "key": "location", "value": "无量后山"}]}  # 南海鳄神不是相关者
        self.assertIsNone(lod.settle(w, ev, torn, "chronicle"))
        self.assertEqual(w.graph.get("段誉", "location"), "剑湖宫·练武厅")
        whole = {"happens": True, "summary": "段誉独自赶往无量后山求药",
                 "effects": [{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"}]}
        self.assertEqual(lod.settle(w, ev, whole, "chronicle")["summary"], "段誉独自赶往无量后山求药")


class NextDoorTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_canon_next_door_is_played_not_whispered(self):
        w = self.w
        ev = canon(w, "段誉发现琅嬛福地")
        w.done.extend(e["id"] for e in w.canon if e["order"] < ev["order"])
        w.player.set("location", "琅嬛福地·书房")
        w.advance((ev["day"] - w.clock.day) * PER_DAY)
        offstage, staged = lod.split_due(w)
        self.assertEqual(staged["id"], ev["id"])                                      # 段誉推门进的是隔壁石室：交导演，两人得以相见
        self.assertIn("近旁的琅嬛福地·玉像石室", prompts.render_backstage(rag.backstage(w, stage=staged)))

    def test_people_next_door_cannot_be_elsewhere(self):
        w = self.w
        w.player.set("location", "剑湖宫")                                           # 段誉在近旁的练武厅
        ev = canon(w, "段誉赴万劫谷求解药")
        effects.apply(w, [{"op": "set", "id": "段誉", "key": "status", "value": "wounded"}], "canon")
        w.done.extend(e["id"] for e in w.canon if e["order"] < 5)
        w.clock.tick = (ev["day"] - 3) * PER_DAY                                    # 尚未到期：只是在近旁，原著不拿他
        self.assertIn("段誉正在主角近旁的剑湖宫·练武厅", "".join(lod.dirt(w, ev)))


class FarewellTest(unittest.TestCase):
    """原著要把人从主角身边带走：交导演演出这一别，而不是场外悄悄传送、或就此作罢。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.fall = canon(self.w, "段誉坠入无量山谷")
        self.w.done.extend(e["id"] for e in self.w.canon if e["order"] < self.fall["order"])
        self.w.player.set("location", "无量后山")
        self.w.graph.set("段誉", "location", "无量后山")
        effects.apply(self.w, [{"op": "set", "id": "段誉", "key": "status", "value": "wounded"}], "canon")
        self.w.advance((self.fall["day"] - self.w.clock.day) * PER_DAY)

    def test_the_canon_comes_for_him_in_front_of_the_player(self):
        w = self.w
        staged = lod.split_due(w)[1]
        self.assertEqual(staged["id"], "段誉坠入无量山谷")
        text = prompts.render_backstage(rag.backstage(w, stage=staged))
        self.assertIn("段誉此刻正在主角身边", text)
        self.assertIn("把这一别演出来", text)

    def test_his_leaving_reaches_the_writer(self):
        w = self.w
        llm = StubLLM(director())
        Game(w, llm).act("看")
        self.assertEqual(w.graph.get("段誉", "location"), "无量山·谷底")              # 原著照演：他坠下了山谷
        self.assertIn("离开了你身边，往无量山·谷底去了", llm.writer_prompts[-1])       # 编剧知道人是怎么不见的

    def test_a_companion_is_not_taken_back(self):
        w = self.w
        w.graph.link("段誉", "player", "随行")
        self.assertIsNone(lod.split_due(w)[1])                                        # 主角把人带在身边：原著不来要人
        self.assertEqual(lod.verdict(w, self.fall, 1)[0], "skip")

    def test_old_business_does_not_drag_him_back(self):
        w = self.w
        w.advance(3 * PER_DAY)
        offstage, staged = lod.split_due(w)
        self.assertIn(self.fall["id"], [ev["id"] for ev, _ in offstage])              # 过了时候的旧事不回头拽人：场外作罢
        self.assertTrue(lod.broken(w, self.fall))
        self.assertEqual(staged["id"], "段誉借乘黑玫瑰")                               # 来要他的是当下的那一桩
