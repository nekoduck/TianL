"""
[INPUT]: 依赖 tianlong.engine 的 Game，tianlong.world 的 World 与 data/canon 原著世界；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——原著在主角眼前一回合一桩交导演上演且可被主角阻断、远方原著按距离延迟传来、剧情后果与自由选项跨回合延续、
          跋涉时日由道路结算、门前之关止步并交下一回合导演兑现、时长由措辞换算、同伴随行不被误判(v5：宫院与练武厅同属近旁，厅中之事交下一回合导演)、新造实体被驳回且账本不记未成立之事、
          众目之下的事入江湖账本、史官改写被扰动的大事(v5：改写是一个事务，筋骨落不了整桩不入账)、写了不成立之事的拍整拍作废、选项在落账之后拟定(head 不带选项)、
          流式进度依序报告(head 为快照)、分隔线之后的梗概不给读者只给账房(分隔线被拆在两块之间也不漏一个等号)、编剧半途失声保留已写、无监听不流式、
          回合原子(中途抛错则世界与记忆回到回合开始)、终端的数字快捷写法只认半角；v7 流式与整形的用例在大理城的静处(quiet)开局——账上不变，正文之后没有补记搅进逐字比对
[POS]: tests 的主循环验证，证明 LLM 编织剧情与选项、基础设施掌管原著世界并负责记住、裁决与校准
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import json
import logging
import unittest

from tianlong import cli
from tianlong.engine import Game
from tianlong.narrative.llm import LLMError
from tianlong.world import access, perspective
from tianlong.world.clock import PER_DAY
from tianlong.world.world import World

logging.disable(logging.WARNING)  # 兜底告警在测试中属预期

WRITER = "（正文）\n===\n梗概：记\n传言：无"


class StubLLM:
    """按 system 提示词关键词返回预设 JSON；记录导演与编剧收到的提示词。"""

    def __init__(self, replies: dict):
        self.replies, self.tokens, self.director_prompts, self.writer_prompts = replies, 0, [], []

    def json(self, system, user, max_tokens=0):
        if "说书人与导演" in system:
            self.director_prompts.append(user)
        for key, reply in self.replies.items():
            if key in system:
                return copy.deepcopy(reply)  # 如真模型：每次都是新解析出的 JSON，落账时的规整不会改到预设
        raise LLMError("无预设")

    def text(self, system, user, max_tokens=0):
        self.writer_prompts.append(user)
        return self.replies.get("小说家", WRITER)


class StreamLLM(StubLLM):
    """能流式的桩：按 chunks 逐块产出；chunks 中的异常在该处抛出，模拟半途断流。"""

    def __init__(self, replies: dict, chunks: list):
        super().__init__(replies)
        self.chunks = chunks

    def stream(self, system, user, max_tokens=0):
        for c in self.chunks:
            if isinstance(c, Exception):
                raise c
            yield c


def eve_of_month_after(world, day: int):
    """把时钟拨到 day 之后那个月末的最后一分钟：下一回合必然跨日，远方到期原著随之结算。"""
    world.clock.tick = (day // 30 + 1) * 30 * PER_DAY - 1


def quiet() -> World:
    """一处无事的所在(大理城)：这一回合账上什么也不变，正文之后不会有补记——只验流式与整形的机关。"""
    w = World.create()
    w.player.set("location", "大理城")
    return w


def director(**kw):
    return {"说书人与导演": {"beats": ["甲"], "pace": "瞬息", "options": ["一", "二", "三"], **kw}}


class CanonLoopTest(unittest.TestCase):
    def test_opening_canon_is_staged_for_the_director_one_per_turn(self):
        llm = StubLLM(director())
        game = Game(World.create("离线"), llm)
        turn = game.open()
        w = game.world
        self.assertIn("【原著此刻在此上演】龚光杰刺伤褚师弟", llm.director_prompts[-1])  # 导演在开口前就知道这一幕的主干
        self.assertEqual(w.done, ["无量剑第四场比剑"])                                 # 一回合只上演一桩
        self.assertEqual(w.graph.get("褚师弟", "status"), "wounded")
        seen = [n for n in turn["news"] if n["witnessed"]]
        self.assertIn("无量剑东宗的持剑少年刺伤无量剑西宗的少年，东宗四赛三胜", "".join(n["text"] for n in seen))  # 界面从主角的视角说(v5)：不识名的人只剩叫法；四个东宗少年各有叫法(v7 叫法即主键)
        self.assertNotIn("【刚刚传到的消息】", llm.writer_prompts[-1])  # 亲历之事已在节拍里，不再当传闻
        self.assertEqual(turn["clock"], {"year": "元祐六年", "date": "二月初一", "hour": "辰时"})
        self.assertEqual(turn["status"][0], {"text": "安然无恙", "tone": "plain"})
        game.act("看")
        self.assertIn("【原著此刻在此上演】段誉拒比武并讲佛理", llm.director_prompts[-1])  # 下一桩在下一回合
        self.assertEqual(len(w.done), 2)

    def test_player_can_block_canon_before_their_eyes(self):
        llm = StubLLM(director(canon={"unfolds": False, "why": "主角挡下了那一剑"}))
        game = Game(World.create(), llm)
        game.open()
        w = game.world
        self.assertIn("无量剑第四场比剑", w.done)                      # 这一桩已了，不会再来
        self.assertEqual(w.graph.get("褚师弟", "status"), "alive")       # 原著结局未落账
        self.assertIn("龚光杰", w.taint)                                # 因果涟漪记下

    def test_offline_travel_follows_roads(self):
        game = Game(World.create())
        turn = game.act("去剑湖宫")
        self.assertEqual(turn["place"], "剑湖宫")

    def test_distant_canon_arrives_as_delayed_news_dated_when_it_happened(self):
        game = Game(World.create())
        w = game.world
        far = next(e for e in w.canon if e["id"] == "鸠摩智押段誉抵姑苏")
        w.player.set("location", "大理城")  # 主角在无事发生的城里(剑湖宫的宫院与练武厅同属近旁，厅中之事会交导演)，无量山与远方的原著都在场外依序上演
        w.clock.tick = (far["day"] + 3) * PER_DAY - 1  # 下一回合跨入排定之日后的第三天：迟了三日才结算
        game.act("歇息")
        self.assertIn(far["id"], w.done)
        self.assertEqual(next(e for e in w.truth.events if e["summary"] == far["summary"])["day"], far["day"])  # 日戳是排定之日
        known = lambda: {w.truth.get(i)["summary"] for i in w.knowledge.known}
        self.assertGreater(w.graph.distances(w.here)[far["where"]], 3)
        self.assertNotIn(far["summary"], known())  # 姑苏远在二十余日之外，消息才走了三日
        w.advance(PER_DAY * w.graph.distances(w.here)[far["where"]])
        w.sync()
        self.assertIn(far["summary"], known())


class DirectorTest(unittest.TestCase):
    def test_plot_and_free_options_persist_across_turns(self):
        llm = StubLLM({**director(effects=[
            {"op": "link", "src": "段誉", "dst": "player", "rel": "结为知交", "note": "你替他解了围"},
            {"op": "set", "id": "左子穆", "key": "mood", "value": "疑心大起"}],
            options=["替段誉挡下一掌", "偷看钟灵的布囊", "向左子穆讨教剑法"]),
            "小说家": "（正文）\n===\n梗概：你替段誉解围，与他结交\n传言：无量剑比剑被一名外客搅乱"})
        game = Game(World.create(), llm)
        perspective.learn(game.world, "player", "段誉")  # 主角已识得段誉：写的是跨回合延续，不是称谓
        turn = game.act("替段誉解围")
        self.assertEqual(turn["options"], ["替段誉挡下一掌", "偷看大眼圆脸的少女的布囊", "向左子穆讨教剑法"])  # 主角叫不出钟灵：选项上只是叫法(v6)
        llm.replies = {**director(), "小说家": WRITER}
        game.act(turn["options"][0])  # 选项即原话，交回导演
        self.assertIn("【主角此刻】替段誉挡下一掌", llm.writer_prompts[-1])
        self.assertIn("对你友善（你替他解了围）", llm.writer_prompts[-1])  # 印象由恩怨账折叠，缘由随之
        self.assertIn("你替段誉解围，与他结交", llm.writer_prompts[-1])  # 前情记的是编剧核实过的梗概
        self.assertEqual(game.world.graph.get("左子穆", "mood"), "疑心大起")
        self.assertIn("无量剑比剑被一名外客搅乱", [e["summary"] for e in game.world.truth.events])  # 众目之下结交，江湖有传

    def test_journey_time_from_roads_not_llm(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "大理城"}]))
        game = Game(World.create(), llm)
        w = game.world
        start, ride = w.clock.day, access.distances(w, w.here)["大理城"]
        turn = game.act("直奔大理城")
        self.assertEqual(turn["place"], "大理城")
        self.assertEqual((ride, w.clock.day), (2, start + ride))  # 步行 3 日，骑马 2 日；导演只说了"瞬息"

    def test_the_gate_at_the_door_becomes_the_next_scene(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "镇南王府"}]))
        game = Game(World.create(), llm)
        turn = game.act("直奔镇南王府")
        self.assertEqual(turn["place"], "大理城")                                                # 王府门前止步
        self.assertIn("主角前往镇南王府——行至大理城便止步，往镇南王府是一道关（守卫）", llm.writer_prompts[-1])  # 编剧知道为何止步
        self.assertIn("镇南王府（0日·守卫）", llm.writer_prompts[-1])                            # 出路注明关口
        turn = game.act("求见王府")
        self.assertIn("往镇南王府（守卫）：王府守卫核认来人", llm.director_prompts[-1])           # 导演开口前看见门前之关
        self.assertEqual((turn["place"], turn["void"]), ("镇南王府", []))                         # 由导演兑现，过关入府

    def test_time_flows_by_pace_words_not_numbers(self):
        llm = StubLLM(director(pace="瞬息"))
        game = Game(World.create(), llm)
        w = game.world
        tick = w.clock.tick
        game.act("对段誉说了句话")
        self.assertEqual(w.clock.tick, tick + 1)
        llm.replies = director(pace="一顿饭")
        game.act("与段誉用饭")
        self.assertEqual(w.clock.tick, tick + 1 + 45)
        llm.replies = director(pace="一夜")
        game.act("歇息一夜")
        self.assertTrue(w.clock.label().endswith("二月初二 辰时"))        # 一夜歇到次日清晨
        self.assertIn("【本回合光阴】一夜（", llm.writer_prompts[-1])      # 编剧知道流逝了多久

    def test_companion_moves_with_the_player_and_his_canon_waits(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "剑湖宫"},
                                         {"op": "set", "id": "段誉", "key": "location", "value": "剑湖宫"}]))
        game = Game(World.create(), llm)
        w = game.world
        turn = game.act("拉段誉同去剑湖宫")
        self.assertEqual((turn["void"], w.graph.get("段誉", "location")), ([], "剑湖宫"))  # 先走一步不算"不在此地"
        self.assertNotIn("龚光杰掌掴段誉", w.done)                                     # 厅就在近旁：那一掌不在场外悄悄落下
        self.assertEqual(w.graph.get("段誉", "status"), "alive")                        # 原著不能把身边的人传送回去挨打
        llm.replies = director()
        game.act("看")
        self.assertIn("【原著此刻在近旁的剑湖宫·练武厅", llm.director_prompts[-1])      # 交导演：演不演、怎么演由眼前的剧情定

    def test_invented_entities_rejected_and_ledgers_stay_honest(self):
        llm = StubLLM(director(beats=["你隔空一掌击毙乔峰"], effects=[
            {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},
            {"op": "create", "id": "神秘剑客", "type": "person", "attrs": {}},
            {"op": "set", "id": "player", "key": "location", "value": "后山禁地"}]))
        game = Game(World.create(), llm)
        turn = game.act("隔空一掌打死乔峰")
        self.assertEqual(game.world.graph.get("乔峰", "status"), "alive")
        self.assertFalse(game.world.graph.has("神秘剑客"))
        self.assertEqual(len(turn["void"]), 4)                                                # 三条驳回的指令 + 一拍作废
        self.assertIn("乔峰身亡——乔峰不在你身边", llm.writer_prompts[-1])                      # 驳回译成人话回告编剧
        self.assertIn("你隔空一掌击毙乔峰——未曾发生", llm.writer_prompts[-1])                  # 写了却不成立的拍：整拍作废，化作失败的事实
        self.assertNotIn("【已成立之事】\n- 你隔空一掌击毙乔峰", llm.writer_prompts[-1])
        self.assertEqual([e for e in game.world.truth.events if e["origin"] == "director"], [])  # 未成立之事不入账
        self.assertNotIn("击毙", game.world.player["journal"][-1])                             # 前情也不记

    def test_chronicler_rewrites_a_disturbed_major_event(self):
        w = World.create()
        ev = next(e for e in w.canon if e["id"] == "乔峰携阿朱赴聚贤庄")
        w.done.extend(e["id"] for e in w.canon if e["order"] < ev["order"])  # 前事已了
        w.graph.set("阿朱", "status", "dead")  # 主角早先改变了阿朱的命运
        llm = StubLLM({**director(), "史官": {"happens": True, "summary": "乔峰孤身闯庄", "effects": [
            {"op": "set", "id": "乔峰", "key": "mood", "value": "万念俱灰"},
            {"op": "set", "id": "段誉", "key": "status", "value": "dead"},
            {"op": "add", "id": "player", "key": "power", "value": 100}]}})
        game = Game(w, llm)
        eve_of_month_after(w, ev["day"])
        game.act("歇息")
        self.assertEqual(w.graph.get("段誉", "status"), "alive")  # 越出相关者
        self.assertLess(w.player["power"], 100)                  # 场外碰不到主角
        self.assertNotEqual(w.graph.get("乔峰", "mood"), "万念俱灰")  # 改写是一个事务(v5)：筋骨(段誉之死)落不了，整桩不入账，心境也不留半截
        self.assertNotIn("乔峰孤身闯庄", [e["summary"] for e in w.truth.events])  # 说法里夹着不成立之事，不照录


class LedgerHonestyTest(unittest.TestCase):
    """账本只记已成立之事：编剧没写的梗概、破了前提的原著、主角做完便走的事、空口的场外战报，都不得把假话写进账本。"""

    def test_an_unverified_beat_never_reaches_the_ledger(self):
        reply = {**director(beats=["你隔空一掌击毙乔峰"], effects=[
            {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},
            {"op": "link", "src": "段誉", "dst": "player", "rel": "畏惧"}])}
        for tail, memory in (("梗概: 你一掌落空\n传言: 无", "你一掌落空"),          # 半角冒号也认
                             ("**梗概**：\n你一掌落空", "你一掌落空"),             # markdown 粗体、值另起一行
                             ("", "你意欲隔空打死乔峰：段誉与你结下「畏惧」")):     # 没写：意图加核实过的后果
            game = Game(World.create("测"), StubLLM({**reply, "小说家": "正文\n===\n" + tail}))
            perspective.learn(game.world, "player", "段誉")
            game.act("隔空打死乔峰")
            self.assertTrue(game.world.player["journal"][-1].endswith(memory), game.world.player["journal"][-1])
            self.assertFalse(any("击毙" in e["summary"] for e in game.world.truth.events))

    def test_a_staged_canon_with_broken_premises_does_not_unfold(self):
        game = Game(World.create("测"))
        game.world.graph.set("龚光杰", "status", "dead")
        turn = game.open()
        self.assertEqual(game.world.graph.get("褚师弟", "status"), "alive")                # 死人刺不伤人
        self.assertNotIn("龚光杰刺伤褚师弟", "".join(n["text"] for n in turn["news"]))

    def test_a_deed_done_before_leaving_is_witnessed_where_and_when_it_happened(self):
        llm = StubLLM({**director(effects=[{"op": "set", "id": "左子穆", "key": "status", "value": "wounded"},
                                            {"op": "set", "id": "player", "key": "location", "value": "大理城"}]),
                       "小说家": "正文\n===\n梗概：你刺伤左子穆后远走\n传言：测当众刺伤左子穆"})
        game = Game(World.create("测"), llm)
        w = game.world
        w.done += [e["id"] for e in w.canon if e["day"] == w.clock.day]
        day0 = w.clock.day
        game.act("刺伤左子穆，远走大理")
        deed = next(e for e in w.truth.events if e["origin"] == "director")
        self.assertEqual((deed["witnessed"], deed["day"], deed["where"]), (True, day0, "剑湖宫·练武厅"))
        self.assertEqual(w.knowledge.view("左子穆")["status"], "wounded")                  # 走了也记得刚才所见
        llm.replies = {**director(pace="一日"), "小说家": WRITER}
        game.act("歇")
        self.assertNotIn("测当众刺伤左子穆", llm.writer_prompts[-1].partition("【刚刚传到的消息】")[2])  # 自己做的事不会再当新到的传闻

    def test_a_staged_canon_seen_late_is_dated_today(self):
        game = Game(World.create("测"), StubLLM(director(pace="一夜")))
        game.open()
        morning = game.act("歇")["time"].split(" ")[0]           # 一夜醒来已是第三日，原著排的却是第一日
        turn = game.act("看")                                      # 这一回合开头，厅中那一幕才在主角眼前上演
        seen = [n for n in turn["news"] if n["witnessed"]]
        self.assertTrue(seen and all(n["date"] == morning for n in seen))

    def test_every_leg_of_a_round_trip_takes_time(self):
        game = Game(World.create("测"), StubLLM(director(effects=[
            {"op": "set", "id": "player", "key": "location", "value": "大理城"},
            {"op": "set", "id": "player", "key": "location", "value": "剑湖宫·练武厅"}])))
        tick = game.world.clock.tick
        game.act("去大理再回来")
        self.assertEqual(game.world.clock.tick - tick, 4 * PER_DAY)                         # 去两日，回两日


class AgentShapeTest(unittest.TestCase):
    def test_loose_director_output_is_read_kindly(self):
        llm = StubLLM({"说书人与导演": {"beats": "你拔剑出鞘", "options": "拔剑、离去、观望", "pace": ["片刻"],
                                       "canon": {"unfolds": "false"}, "effects": {"op": "set", "id": "player", "key": "posture", "value": "拔剑"}}})
        game = Game(World.create(), llm)
        turn = game.open()
        self.assertEqual(turn["options"], ["拔剑", "离去", "观望"])                          # 不逐字拆散
        self.assertEqual(game.world.player["posture"], "拔剑")                              # 单条指令也收
        self.assertEqual(game.world.graph.get("褚师弟", "status"), "alive")                 # "false" 就是否

    def test_an_empty_stream_falls_back_instead_of_a_blank_page(self):
        turn = Game(World.create(), StreamLLM(director(), [])).act("看", on=lambda *_: None)
        self.assertTrue(turn["text"])

    def test_a_separator_split_across_chunks_never_reaches_the_reader(self):
        llm = StreamLLM(director(), ["灯下如豆。\n=", "==\n梗概：看\n传言：无"])
        shown = []
        Game(quiet(), llm).act("看", on=lambda kind, data: shown.append(data) if kind == "text" else None)
        self.assertEqual("".join(shown), "灯下如豆。")

    def test_offline_travel_picks_the_place_named_in_full(self):
        game = Game(World.create())
        game.world.player.set("location", "无量山")
        self.assertEqual(game.act("前往澜沧江边高崖")["place"], "澜沧江边高崖")


class AtomicTurnTest(unittest.TestCase):
    def test_a_turn_that_breaks_midway_never_happened(self):
        class Breaks(StubLLM):
            def text(self, system, user, max_tokens=0):
                raise RuntimeError("编剧落笔时出了岔子")  # 不是网络错误：兜底接不住，回合只能作废
        llm = Breaks(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "剑湖宫"},
                                       {"op": "add", "id": "player", "key": "hp", "value": -30}]))
        game = Game(World.create(), llm)
        before = json.dumps(game.world.dump(), ensure_ascii=False)
        with self.assertRaises(RuntimeError):
            game.act("冲出大厅")
        self.assertEqual(json.dumps(game.world.dump(), ensure_ascii=False), before)  # 世界回到回合开始之时
        self.assertEqual((game.world.here, game.world.player["hp"], game.last_text), ("剑湖宫·练武厅", 100, ""))

    def test_number_shortcuts_belong_to_the_terminal(self):
        game = Game(World.create())
        game.open()
        self.assertEqual(cli._pick(game, "1"), game.options[0])                    # 终端：打 1 即第一个选项
        self.assertEqual((cli._pick(game, "①"), cli._pick(game, "9")), ("①", "9"))  # 全角或越界之数仍是原话
        game.act("①")                                                              # 内核照收原话，不再因它崩溃
        self.assertTrue(game.world.player["journal"][-1].endswith("你意欲①"))


class StreamingTest(unittest.TestCase):
    def test_progress_is_reported_in_order(self):
        llm = StreamLLM(director(), ["剑光", "一闪，", "\n满堂寂然。"])
        events = []
        turn = Game(quiet(), llm).act("看", on=lambda kind, data: events.append((kind, data)))
        kinds = [k for k, _ in events]
        self.assertEqual(kinds, ["stage", "stage", "stage", "head", "text", "text"])          # 正文按段送出：一段齐了才过视角掩码
        self.assertEqual([d for k, d in events if k == "stage"], ["direct", "settle", "write"])
        head = events[3][1]
        self.assertEqual((head["text"], head["options"]), ("", []))  # 落笔前，除正文与选项外都已定：选项在落账之后由编剧拟、规则验收
        self.assertEqual(turn["options"], ["一", "二", "三"])
        self.assertEqual(turn["text"], "剑光一闪，\n满堂寂然。")
        self.assertEqual("".join(d for k, d in events if k == "text"), turn["text"])

    def test_tail_is_kept_from_the_reader_but_feeds_the_ledger(self):
        llm = StreamLLM(director(), ["剑光一闪。", "\n===\n梗概：", "你看了一眼\n传言：无"])
        shown = []
        game = Game(quiet(), llm)
        turn = game.act("看", on=lambda kind, data: shown.append(data) if kind == "text" else None)
        self.assertEqual(("".join(shown), turn["text"]), ("剑光一闪。", "剑光一闪。"))      # 读者只见正文
        self.assertTrue(game.world.player["journal"][-1].endswith("：你看了一眼"))           # 账房得到梗概

    def test_writer_falling_silent_midway_keeps_what_was_written(self):
        llm = StreamLLM(director(), ["前半句已写成，", LLMError("断流")])
        turn = Game(quiet(), llm).act("看", on=lambda *_: None)
        self.assertTrue(turn["text"].startswith("前半句已写成，\n"))  # 已写的保留
        self.assertIn("甲", turn["text"])                             # 只言片语：以已成立之事续成，读者不至于只看到半句
        long = "前半句已写成，" * 10
        llm = StreamLLM(director(), [long, LLMError("断流")])
        self.assertEqual(Game(quiet(), llm).act("看", on=lambda *_: None)["text"], long)  # 写够了便是正文

    def test_without_listener_nothing_streams(self):
        llm = StreamLLM(director(), [AssertionError("不该流式")])
        self.assertEqual(Game(quiet(), llm).act("看")["text"], "（正文）")


if __name__ == "__main__":
    unittest.main()
