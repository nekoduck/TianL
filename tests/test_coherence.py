"""
[INPUT]: 依赖 tianlong.world 的 World / lod / plot(v11 场外编剧的规则审) / body / bond / effects / rag / graph / situation / menu 与 data/canon 原著世界，tianlong.engine 的 Game（离线 llm=None 结算场外原著），
         tianlong.narrative 的 prompts（后台成文）/ agents（选项解析）与 llm.LLMError，tianlong.story 的 brief / choices / scene / timing，tests/test_engine 的 StubLLM / director（桩导演），tests/test_adjudicate 的 plan / judge
[OUTPUT]: unittest 用例——v5「连贯性」的离线验收，每一类对应 PR #2 review 里一条 P0：
          剧情前提与体征分开(原著宣告的负伤不被养伤抹掉、明写痊愈才消、读路径不写气血、原著主线离线连演不断)；
          一人一主(OneMasterTest：v11 原著前置未变归演绎家、近旁与见过主角的人场外编剧不写、七日内照原著的人创作家不先改)、场外说法对账(OffstageProseTest：v11 衍生事件的说法)、场外事务(TransactionTest)、近旁(NextDoorTest)、原著来要主角身边的人(FarewellTest)；
          账文一致(AgreementTest：只剥越权的那条、旁白里的「你」、走进而没走、暗路与隐情的来由、取物口径、返工写明东西在哪、摸索心法即研习、成文之后再对账、导演失声)；
          眼前(PresenceTest：片区不是一间屋子、名册、尚未登场、走出近旁、原著上台、此地另有其人、近处的熟人、兜底攀谈)；
          P1(TimeTableTest 一张时长表、StudyStallTest 受阻不跨门槛、SceneTest 合要有账与主干不换题、BondTest 恩怨口径、OptionTest 括号、NewsTest 江湖大事)；
          P2(LeakTest：器物名不带生人、本回合见过的生人(刚走开的、死在眼前的)不露名、地点现状与器物描述不泄底、石洞里听不到传闻、无人时示例不出人名、近事以「你」称主角)；
          回放(ReplayTest：tools/rerun 以真模型输出重演抓到的病——主角「去」原地、同片之人被写进拍里、导演先演了原著那一走)；
          终局验收(MeetingTest：「段誉不来」——主角守在石室，原著日子一到他推门进来，原著来要他时目送他走，走开的生人不露名、别处的事不算亲见)
[POS]: tests 的连贯性验证——36 回实录里「段誉不来」「剧情前后打架」的病灶在这里逐条成为用例；与 test_state(v4 状态层)、test_story(v4 故事层)互补
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import unittest

from tests.test_adjudicate import judge, plan
from tests.test_engine import StubLLM, director
from tianlong.engine import Game, _newsworthy
from tianlong.narrative import agents, prompts
from tianlong.narrative.llm import LLMError
from tianlong.story import brief, choices, scene, timing
from tianlong.world import adjudicate, body, bond, effects, graph, growth, lod, menu, perspective, plot, rag, situation
from tianlong.world.clock import PACES, PER_DAY, span
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
#  P0-2 一人一主：场外编剧、日程结算与散文验真(v11 场外推演换成场外编剧：规则审在 world/plot)
# ============================================================
def derived(w, where, actors, summary, *ops, day=None):
    """一桩场外编剧写好、排进日程的衍生事件：与原著同一格式，先把人摆到事发之地。"""
    day = w.clock.day if day is None else day
    place = [{"op": "set", "id": a, "key": "location", "value": where} for a in actors]
    return {"id": f"衍·测·{len(w.canon)}", "order": 0.5, "day": day, "where": where, "weight": 1, "public": True,
            "actors": list(actors), "requires": [], "effects": place + list(ops), "summary": summary,
            "derived": True, "line": "测", "made": w.clock.day}


def freed(w, pid):
    w.done.extend(e["id"] for e in w.canon if pid in lod._cast(e))  # 此人再无原著之约：原著里已没有他的戏


class OneMasterTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_people_with_canon_ahead_are_performed_not_invented(self):
        w = self.w
        self.assertEqual(plot.mode(w, "秦红棉"), "演绎")                 # 原著前置未变：照原著演
        freed(w, "秦红棉")
        self.assertEqual(plot.mode(w, "秦红棉"), "创作")                 # 原著里已没有她的戏：往后的路交创作家

    def test_people_next_door_belong_to_the_director(self):
        w = self.w
        freed(w, "秦红棉")
        w.graph.nodes["秦红棉"]["adrift"] = True
        w.graph.set("秦红棉", "location", "剑湖宫·练武厅")
        w.player.set("location", "剑湖宫")
        self.assertNotIn("秦红棉", plot.idle(w))                          # 喊一声就到的人，场外编剧不写
        _, problems = plot.vet(w, plot.sequel(w, "秦红棉"), {"events": [{"day": 0, "where": "剑湖宫·练武厅", "actors": ["秦红棉"], "summary": "秦红棉拂袖而去"}]})
        self.assertTrue(any("主角身边" in p for p in problems))

    def test_people_who_met_the_player_are_not_frozen_but_the_ones_his_story_hangs_on_are(self):
        w = self.w
        freed(w, "秦红棉")
        w.graph.nodes["秦红棉"]["adrift"] = True
        self.assertIn("秦红棉", plot.idle(w))
        bond.event(w, "秦红棉", 1.5, "你替她挡过一箭")
        self.assertIn("秦红棉", plot.idle(w))                             # v13 一日之内与主角有过交集不等于等着主角：不再冻住他（司空玄 held 了 60 回，从未进过 idle）
        w.graph.set("秦红棉", "location", "剑湖宫·练武厅")
        w.player.push("threads", "寻回秦红棉")
        situation.track(w, "寻回秦红棉", ["秦红棉"], [])
        self.assertNotIn("秦红棉", plot.idle(w))                          # 主角未了之事所系的人，才是等着主角的故事

    def test_the_creator_cannot_beat_the_canon_to_its_cast(self):
        w = self.w
        freed(w, "秦红棉")
        task = plot.sequel(w, "秦红棉")
        _, problems = plot.vet(w, task, {"events": [{"day": 0, "where": "木婉清居所", "actors": ["秦红棉", "甘宝宝"], "summary": "秦红棉一掌打死了甘宝宝",
                                                      "effects": [{"op": "set", "id": "甘宝宝", "key": "status", "value": "dead", "by": "秦红棉"}]}]})
        self.assertTrue(any("七日之内照原著" in p for p in problems))     # 原著前置未变就照原著演：创作家不先一步改掉她
        self.assertEqual(w.graph.get("甘宝宝", "status"), "alive")


class OffstageProseTest(unittest.TestCase):
    """衍生事件的说法是 LLM 写的：到期结算时与账对得上才照录，提到主角即只记核实过的后果。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        freed(self.w, "秦红棉")

    def settle(self, summary, *ops):
        ev = derived(self.w, "木婉清居所", ["秦红棉"], summary, *ops)
        self.w.canon.append(ev)
        e = lod.settle(self.w, ev, ev, "derived")
        return [e["summary"]] if e else []

    def test_a_fall_without_a_move_is_not_news(self):
        told = self.settle("秦红棉跌落崖下幸免于难，探寻谷底别寻出路",
                           {"op": "set", "id": "秦红棉", "key": "intent", "value": "寻找出谷之路"})
        self.assertEqual(told, [])                                                    # 36 回实录里「段誉坠崖」的传闻就是这样来的
        self.assertEqual(self.w.graph.get("秦红棉", "location"), "木婉清居所")

    def test_words_that_match_the_ledger_are_kept(self):
        told = self.settle("秦红棉穿林往万劫谷·谷外树林疾驰",
                           {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"})
        self.assertEqual(told, ["秦红棉穿林往万劫谷·谷外树林疾驰"])

    def test_a_wrong_destination_falls_back_to_facts(self):
        told = self.settle("秦红棉动身前往大理城",
                           {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"})
        self.assertEqual(told, ["秦红棉前往万劫谷·谷外树林"])

    def test_the_player_is_never_in_offstage_news(self):
        told = self.settle("秦红棉与测一同前往万劫谷·谷外树林",
                           {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"})
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

    def test_an_offstage_plot_lands_whole_or_not_at_all(self):
        w = self.w
        w.player.set("location", "大理城")
        w.graph.set("钟万仇", "status", "dead")
        ev = derived(w, "无量后山", ["段誉"], "段誉转投后山求药，钟万仇死而复生",
                     {"op": "set", "id": "钟万仇", "key": "status", "value": "alive"})  # 死者不能复生：这一条落不了
        self.assertIsNone(lod.settle(w, ev, ev, "derived"))
        self.assertEqual(w.graph.get("段誉", "location"), "剑湖宫·练武厅")             # 筋骨落不了一条：整桩不半截照演
        self.assertTrue(w.graph.get("段誉", "adrift"))                                # 没演成：他的原著线变了
        whole = derived(w, "无量后山", ["段誉"], "段誉独自赶往无量后山求药")
        self.assertEqual(lod.settle(w, whole, whole, "derived")["summary"], "段誉独自赶往无量后山求药")


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
        situation.enlist(self.w, ["段誉"])                                            # 两人在后山碰上了：他在主角跟前
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


# ============================================================
#  P0-3 账文一致：授意、词表、reveal、成文对账、导演失声
# ============================================================
VAULT, STUDY, TUNNEL = "琅嬛福地·玉像石室", "琅嬛福地·书房", "琅嬛福地·石级隧道"


class AgreementTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.player.set("location", VAULT)

    def test_only_the_overreach_is_stripped(self):
        w = self.w
        r = judge(w, plan(("player", "你抓起石室烛台，快步奔向来时的石级隧道。",
                           [{"op": "push", "id": "player", "key": "inventory", "value": "琅嬛洞烛台"},
                            {"op": "set", "id": "player", "key": "location", "value": TUNNEL}])), aim={TUNNEL})
        self.assertEqual(w.here, TUNNEL)                                              # 玩家要走：照走
        self.assertNotIn("琅嬛洞烛台", w.player["inventory"])                          # 顺手牵羊：不演
        self.assertEqual(r.candidates, ["取走琅嬛洞烛台"])
        self.assertIn("取走琅嬛洞烛台——主角并未起意，未曾发生", r.void)                 # 编剧知道那件事没有发生
        self.assertIn("「取走琅嬛洞烛台」主角并未起意", r.beats[0]["text"])
        self.assertEqual(r.hard, [])                                                  # 剥掉的那件不再算拍文违例

    def test_a_narrated_hand_is_still_the_players(self):
        w = self.w
        r = judge(w, plan((None, "你顺手拾起地上的玉钏", [{"op": "push", "id": "player", "key": "inventory", "value": "神仙姊姊玉钏"}])))
        self.assertEqual(r.candidates, ["取走神仙姊姊玉钏"])                            # 旁白里写「你」，也是主角的举动
        w.graph.set("钟灵", "location", VAULT)
        r = judge(w, plan((None, "钟灵把玉钏塞给你", [{"op": "push", "id": "player", "key": "inventory", "value": "神仙姊姊玉钏"}])))
        self.assertEqual(r.candidates, [])                                            # 别人递给你的不归授意管
        self.assertIn("神仙姊姊玉钏", w.player["inventory"])

    def test_walking_in_without_walking_is_a_violation(self):
        w = self.w
        r = judge(w, plan(("player", "你走进书房，四下打量", [])))
        self.assertEqual([f.kind for f in r.hard], ["move"])                          # 账上你仍在石室
        r = judge(w, plan(("player", "你走进书房，四下打量", [{"op": "set", "id": "player", "key": "location", "value": STUDY}])))
        self.assertEqual(r.hard, [])
        r = judge(w, plan(("player", "你问道：「你们是何时来到无量山的？」", [])))
        self.assertEqual(r.hard, [])                                                  # 台词里说到的去处不是你的行止

    def test_a_secret_way_is_found_where_it_is(self):
        w = self.w
        road = {"op": "reveal", "src": "无量山·谷底", "dst": "琅嬛福地", "rel": "通路"}
        w.player.set("location", "剑湖宫")
        _, rejected = effects.apply(w, [dict(road)], "director")
        self.assertIn("发现不了这条暗路", rejected[0][1])                               # 隔着几重山，发现不了谷底的石门
        w.player.set("location", "无量山·谷底")
        self.assertEqual(effects.apply(w, [dict(road)], "director")[1], [])
        _, rejected = effects.apply(w, [{"op": "reveal", "src": "段延庆", "dst": "段誉", "rel": "生父"}], "director")
        self.assertIn("无从得知", rejected[0][1])                                       # 当事人都不在身边

    def test_taking_needs_reach(self):
        w = self.w
        w.player.set("location", STUDY)
        take = lambda item: effects.apply(w, [{"op": "push", "id": "player", "key": "inventory", "value": item}], "director")[1]
        self.assertEqual(take("琅嬛洞烛台"), [])                                       # 隔壁石室里摆着的，走两步就拿到
        self.assertTrue(take("北冥神功卷轴"))                                           # 藏在隔壁蒲团里的，人不到那里找不着
        _, rejected = effects.apply(w, [{"op": "set", "id": "北冥神功卷轴", "key": "holder", "value": "player"}], "director")
        self.assertTrue(rejected)                                                     # 换成 set holder 也一样
        _, rejected = effects.apply(w, [{"op": "set", "id": "player", "key": "location", "value": VAULT},
                                        {"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"}], "director")
        self.assertEqual(rejected, [])                                                # 走过去再找：同一拍里也成立

    def test_the_repair_says_where_the_thing_is(self):
        w = self.w
        w.player.set("location", "琅嬛福地")
        r = judge(w, plan(("player", "你扯开蒲团，抽出夹层里的帛卷。",
                           [{"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"}])), aim={"北冥神功卷轴"})
        self.assertIn("现在琅嬛福地·玉像石室，藏而未露", "".join(adjudicate.brief(w, r)))  # 返工时导演知道要先走进石室
        self.assertNotIn("玉像石室", "".join(r.void))                                     # 交编剧的作废缘由不带暗藏之处

    def test_groping_through_the_method_is_studying(self):
        w = self.w
        w.graph.set("北冥神功卷轴", "hidden", False)
        effects.apply(w, [{"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"}], "director")
        self.assertIn("北冥神功卷轴", adjudicate.targets(w, "借微光继续摸索内功心法（一个时辰）"))  # 不说哪部，手边的秘籍就是所指
        self.assertNotIn("北冥神功卷轴", adjudicate.targets(w, "摸索石壁，找找出路"))

    def test_the_page_is_audited_after_it_is_written(self):
        w = self.w
        llm = StubLLM({**director(), "小说家": "你俯身拾起神仙姊姊玉钏，揣入怀中。\n===\n梗概：记\n传言：无"})
        game = Game(w, llm)
        game.act("看")
        self.assertTrue(any("玉钏" in d for d in w.player["drift"]))                   # 账上没有：记作偏差
        game.act("看")
        self.assertIn("正文写你取得神仙姊姊玉钏", llm.director_prompts[-1])              # 下回合导演圆回

    def test_a_silent_director_voids_the_turn(self):
        class Strict(StubLLM):
            strict = True
        w = self.w
        game = Game(w, Strict({}))
        turn0 = w.player["turn"]
        with self.assertRaises(LLMError):
            game.act("看")
        self.assertEqual(game.world.player["turn"], turn0)                            # 回合作废：不以离线说书人代演


# ============================================================
#  P0-4 眼前：片区不是一间屋子，名册记着被剧情带到跟前的人
# ============================================================
class PresenceTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_a_region_is_not_one_room(self):
        w = self.w
        w.player.set("location", "中原")
        crowd = [p for p in w.graph.where(type="person") if w.graph.get(p, "location") == "中原"]
        self.assertGreater(len(crowd), 30)
        self.assertEqual(rag.scene(w)["people"], [])                                  # 四十多人同在「中原」，不同处一室
        self.assertTrue(situation.elsewhere(w))                                       # 交导演：要谁登场写 arrive

    def test_the_mountain_hides_who_has_not_come_forward(self):
        w = self.w
        w.player.set("location", "无量山")
        self.assertEqual(situation.around(w), set())                                  # 走到无量山，不是撞进神农帮的营帐
        self.assertIn("司空玄", situation.elsewhere(w))
        self.assertNotIn("南海鳄神", situation.elsewhere(w))                           # 第四回才登场的人，此刻不在任何人眼前
        _, rejected = effects.apply(w, [{"op": "arrive", "id": "南海鳄神"}], "director")
        self.assertIn("还没在江湖上露面", rejected[0][1])
        applied, _ = effects.apply(w, [{"op": "arrive", "id": "司空玄"}], "director")
        self.assertEqual(len(applied), 1)
        self.assertIn("司空玄", situation.around(w))                                   # 找上门来：在跟前了
        self.assertIn("司空玄", rag.scene(w)["people"])

    def test_leaving_the_place_leaves_them_behind(self):
        w = self.w
        w.player.set("location", "无量山")
        situation.enlist(w, ["司空玄"])
        effects.apply(w, [{"op": "set", "id": "player", "key": "location", "value": "剑湖宫"}], "director")
        self.assertEqual(situation.cast(w), set())
        w.player.set("location", "无量山")
        self.assertNotIn("司空玄", situation.around(w))                                # 回来时，他不会还站在原处等你

    def test_canon_on_stage_brings_its_cast(self):
        w = self.w
        ev = canon(w, "神农帮留钟灵下毒逼援")
        w.done.extend(e["id"] for e in w.canon if e["order"] < ev["order"])
        w.player.set("location", "无量山")
        w.advance((ev["day"] - w.clock.day) * PER_DAY)
        llm = StubLLM(director())
        Game(w, llm).act("看")
        self.assertIn("司空玄｜", llm.director_prompts[-1])                              # 原著在眼前上演：它的相关者就在跟前

    def test_the_director_knows_who_else_is_about(self):
        w = self.w
        w.player.set("location", "无量山")
        text = prompts.render_backstage(rag.backstage(w))
        self.assertIn("此地另有其人", text)
        self.assertIn("司空玄（神农帮帮主）在无量山一带", text)

    def test_familiar_faces_nearby_are_remembered(self):
        w = self.w
        w.player.set("location", "澜沧江")
        w.graph.set("段誉", "location", "澜沧江边高崖")
        self.assertFalse(any(line.startswith("段誉") for line in rag.acquainted(w)))  # 素不相识：不算熟人
        bond.event(w, "段誉", 1.5, "你替他解过围")
        self.assertTrue(rag.acquainted(w)[0].startswith("段誉：身在澜沧江边高崖（距此0日）"))  # 一日之内的熟人(有过交集者在前)，导演记得他就在不远处

    def test_small_talk_goes_to_someone_who_matters(self):
        w = self.w
        bond.event(w, "钟灵", 1.5, "你替她挡过一剑")
        picked = menu.check(w, [])
        self.assertTrue(any("钟灵" in str(ids) for _, ids in picked))                   # 兜底攀谈先找与主角有过交集的人


# ============================================================
#  P1 时长一张表、研习受阻、场与主干、恩怨、选项括号、江湖大事
# ============================================================
class TimeTableTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.player.set("location", VAULT)
        effects.apply(self.w, [{"op": "push", "id": "player", "key": "inventory", "value": "神仙姊姊玉钏"}], "director")

    def test_options_promise_what_the_rules_will_charge(self):
        w = self.w
        w.graph.nodes["北冥神功卷轴"].update(hidden=False)
        effects.apply(w, [{"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"}], "director")
        label = next(t for t, _ in choices.later(w) if "研习" in t)
        self.assertIn(f"约{span(timing.study_minutes(w, '北冥神功卷轴'))}", label)    # 选项上的耗时与规则主张同一张表
        self.assertEqual(span(240), "两个时辰")
        self.assertIn("一个时辰", PACES)

    def test_breathing_exercises_are_not_a_nap(self):
        w = self.w
        p = plan(("player", "你盘膝打坐，调息运功", []))
        self.assertEqual(timing.claim(w, p)[0], 0)                                     # 调息、打坐是练功的字眼，不是歇息半日

    def test_a_voided_beat_claims_no_time(self):
        w = self.w
        p = plan(("player", "你歇息养伤", []))
        self.assertGreater(timing.claim(w, p)[0], 0)
        self.assertEqual(timing.claim(w, p, drop={1})[0], 0)                          # 整拍作废的歇息不主张时长


class StudyStallTest(unittest.TestCase):
    def test_a_stalled_session_never_crosses_a_threshold(self):
        w = World.create("测")
        w.turn = {}
        real = body.forecast
        body.forecast = lambda world, src, art=None: {"tier": "受阻", "factor": 0.5, "strain": False, "why": ""}
        try:
            said = growth.study(w, "北冥神功卷轴", 600)
        finally:
            body.forecast = real
        self.assertEqual(growth.stage_of(w, "北冥神功卷轴"), 0)                         # 预裁说受阻，账上就没有初窥门径
        self.assertIn("研习受阻", said)
        self.assertNotIn("北冥神功", w.player["skills"])


class SceneTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        scene.begin(self.w)

    def test_saying_settled_is_not_settling(self):
        w = self.w
        scene.close(w, {"ask": "能否取走烛台", "state": "resolved"}, "看", settled=False)
        self.assertEqual(w.player["scene"]["state"], "转")                            # 账上什么也没变：场不散
        scene.close(w, {"ask": "能否取走烛台", "state": "resolved"}, "取烛台", settled=True)
        self.assertEqual(w.player["scene"]["state"], "合")

    def test_the_spine_stays_with_the_scene(self):
        w = self.w
        first = brief.compose(w, None, [])
        self.assertIn("此场开在剑湖宫·练武厅：眼前有", first["text"])                  # 抵达即遭遇
        scene.close(w, {"ask": "能否劝住两派", "state": "open"}, "劝架", settled=True)
        for _ in range(3):
            scene.begin(w)
            self.assertEqual(brief.compose(w, None, [])["spine"], "scene")            # 一场之内主干不换题
            w.player.set("turn", w.player["turn"] + 1)


class BondTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")

    def test_the_first_word_decides_the_feeling(self):
        self.assertEqual(bond.weigh("感激他杀退仇人"), 3)
        self.assertEqual(bond.weigh("恨他救了仇人"), -3)
        self.assertEqual(bond.weigh("怒不可遏"), -3)

    def test_saying_it_again_is_not_another_grievance(self):
        w = self.w
        for _ in range(5):
            w.player.set("turn", w.player["turn"] + 1)
            bond.attitude(w, {"op": "link", "src": "木婉清", "dst": "player", "rel": "提防", "note": "袖箭相胁带路"})
        self.assertEqual(bond.stance(w, "木婉清")[0], "相识")                           # 五回合各写一遍，仍是同一件事

    def test_feelings_fade_with_days_not_turns(self):
        w = self.w
        bond.event(w, "钟灵", 3, "你救了她")
        w.player.set("turn", w.player["turn"] + 20)
        self.assertEqual(bond.stance(w, "钟灵")[0], "友善")                             # 二十回合挤在半日里，恩情不淡
        w.clock.tick += 10 * PER_DAY
        self.assertEqual(bond.stance(w, "钟灵")[0], "相识")


class OptionTest(unittest.TestCase):
    def test_a_parenthesis_is_a_cost_only_when_it_tells_time(self):
        page = agents._page("正文\n===\n选项：\n1. 伏地细察水面投影处（无量玉壁）｜尺度：此刻\n"
                            "2. 前往大理城｜对象：大理城（两日路程）｜尺度：此后\n")
        self.assertEqual([(o["text"], o["targets"]) for o in page["options"]],
                         [("伏地细察水面投影处", ["无量玉壁"]), ("前往大理城（两日路程）", ["大理城"])])


class NewsTest(unittest.TestCase):
    def test_a_whispered_suspicion_is_not_news(self):
        suspect = [{"op": "link", "src": "木婉清", "dst": "player", "rel": "提防", "note": "袖箭相胁"}]
        sworn = [{"op": "link", "src": "段誉", "dst": "player", "rel": "结义"}]
        self.assertEqual(_newsworthy(suspect, 5, 0), 0)
        self.assertEqual(_newsworthy(sworn, 5, 0), 1)


# ============================================================
#  P2 信息分级与账本杂症
# ============================================================
class LeakTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("秦天")
        self.w.turn = {}

    def test_things_do_not_name_strangers(self):
        w = self.w
        self.assertEqual(perspective.thing(w, "云中鹤钢爪"), "钢爪")                    # 不识其人，只见其物
        perspective.learn(w, "player", "云中鹤")
        self.assertEqual(perspective.thing(w, "云中鹤钢爪"), "云中鹤钢爪")

    def test_the_vault_does_not_tell_where_the_scroll_is(self):
        w = self.w
        w.player.set("location", "琅嬛福地")
        view = perspective.veil(w, rag.build(w))
        self.assertNotIn("卷轴", str(view["scene"]))                                  # 地点现状不再写着「卷轴藏在蒲团内」
        self.assertNotIn("段誉", w.graph.get("琅嬛洞烛台", "desc"))                     # 器物描述只写此刻看得见的样子

    def test_strangers_seen_this_turn_stay_strangers(self):
        game = Game(World.create("测", origin="随从"), StubLLM(director()))
        game.open()
        game.act("看")
        dies = game.act("看")                                                          # 容子矩撞进厅来，倒地毙命
        self.assertIn("入厅撞倒后毙命", "".join(n["text"] for n in dies["news"]))
        self.assertNotIn("容子矩", "".join(n["text"] for n in dies["news"]))            # 死在眼前的生人也叫不出名字
        takes = game.act("看")                                                         # 钟灵放貂，携段誉离开
        self.assertNotIn("段誉", "".join(n["text"] for n in takes["news"]))              # 刚走开的生人，不因走开就露了名
        self.assertIn("容子矩", situation.seen(game.world))                             # 遗体就在厅里：看得见、搜得着

    def test_a_sealed_cave_hears_no_rumors(self):
        w = self.w
        w.player.set("location", "琅嬛福地·书房")
        ev = w.record("乔峰力战群雄", "聚贤庄", [], "canon", weight=2, day=w.clock.day - 30)
        self.assertNotIn(ev["id"], [e["id"] for e in w.sync()])                        # 独处石洞：没有传话的人
        w.player.set("location", "大理城")
        self.assertIn(ev["id"], [e["id"] for e in w.sync()])                           # 见到人了，才听说

    def test_the_example_names_nobody_when_alone(self):
        w = self.w
        w.player.set("location", "琅嬛福地·书房")
        system = prompts._director_system(rag.build(w))
        example = system[system.index("【示例"):]
        self.assertFalse(any(p in example for p in ("段誉", "钟灵", "木婉清")))         # 空石室里不再回回想起段誉

    def test_the_journal_calls_the_player_you(self):
        w = self.w
        llm = StubLLM({**director(), "小说家": "正文\n===\n梗概：秦天探查玉壁\n传言：无"})
        Game(w, llm).act("看")
        self.assertIn("你探查玉壁", w.player["journal"][-1])                            # 书记不会把「你」与「秦天」当成两个人


# ============================================================
#  回放：真模型的写法落在 v5 引擎上抓到的病(tools/rerun.py 重演 36 回实录)
# ============================================================
class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}

    def test_going_where_you_stand_is_not_a_journey(self):
        w = self.w
        w.player.set("location", VAULT)
        came = w.player["came_from"]
        for value in (VAULT, "琅嬛福地玉像石室", "玉像石室"):  # 全名、去「·」的写法、近处的短名都一样：人已在那里
            applied, rejected = effects.apply(w, [{"op": "set", "id": "player", "key": "location", "value": value}], "director")
            self.assertEqual((applied, rejected), ([], []))                           # 原地不动：不是一程路，也不该崩
        self.assertEqual((w.here, w.player["came_from"], w.player["en_route"]), (VAULT, came, None))

    def test_whom_the_director_writes_in_comes_forward(self):
        w = self.w
        w.player.set("location", "无量山")
        r = judge(w, plan(("司空玄", "司空玄从林中踱出，冷冷打量着你。", [], "player")))
        self.assertNotIn("absent", [f.kind for f in r.hard])                         # 同在这一片、已露面的人：写进拍里就是走到了跟前
        self.assertIn("司空玄", situation.around(w))
        r = judge(w, plan(("南海鳄神", "南海鳄神从林中跳了出来。", [])))
        self.assertIn("absent", [f.kind for f in r.hard])                            # 尚未登场的人：照旧不在

    def test_a_step_the_director_already_took_does_not_spoil_the_canon(self):
        w = self.w
        ev = canon(w, "钟灵以闪电貂御敌")
        w.done.extend(e["id"] for e in w.canon if e["order"] < ev["order"])
        effects.apply(w, [{"op": "set", "id": p, "key": "location", "value": "无量山"} for p in ("钟灵", "段誉")], "director")
        e = lod.settle(w, ev, ev, "canon", day=w.clock.day, witnessed=True, partial=True)
        self.assertEqual(e["summary"], ev["summary"])                                # 导演先演了「携段誉离开」：原著的结局照样成立，不换成一串清单
        self.assertEqual(w.graph.get("龚光杰", "status"), "wounded")


# ============================================================
#  终局验收：「段誉不来」——主角守在石室，原著的日子一到，他推门进来
# ============================================================
class MeetingTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测", origin="随从")
        self.w.player.set("location", VAULT)
        self.w.advance((canon(self.w, "段誉发现琅嬛福地")["day"] - self.w.clock.day) * PER_DAY)
        self.llm = StubLLM(director())
        self.game = Game(self.w, self.llm)

    def test_he_walks_into_the_vault_and_out_again(self):
        game, llm = self.game, self.llm
        game.act("静坐等候")
        w = game.world
        face = perspective.handle(w, "段誉")
        self.assertIn("段誉", situation.around(w))                                   # 他推开隐门：两人在石室里相见，不是在传闻里
        self.assertIn(f"{face}来到了此地", llm.writer_prompts[-1])
        game.act("看那人在做什么")
        self.assertIn("磕首取得北冥卷轴", game.world.done)                             # 磕首取卷就在主角眼前
        game.act("上前拱手相见")
        w = game.world
        self.assertEqual(w.graph.get("段誉", "location"), "万劫谷")                    # 原著来要他：交导演演这一别，不是场外悄悄传送
        self.assertIn(f"{face}离开了你身边", llm.writer_prompts[-1])                    # 刚从眼前走开的生人仍只叫外貌——不替主角认出他
        far = next(e for e in w.truth.events if e["where"] == "万劫谷")
        self.assertFalse(far["witnessed"])                                          # 万劫谷里的事主角没看见：只看见他走，那桩事随传闻来
