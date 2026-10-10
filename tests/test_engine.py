"""
[INPUT]: 依赖 tianlong.engine 的 Game，tianlong.world 的 World 与 data/canon 原著世界；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——原著在主角眼前一回合一桩交导演上演且可被主角阻断、远方原著按距离延迟传来、剧情后果与自由选项跨回合延续、
          跋涉时日由道路结算、时长由措辞换算、同伴随行不被误判、新造实体被驳回且账本不记未成立之事、众目之下的事入江湖账本、史官改写被扰动的大事、
          流式进度依序报告(head 为快照)、分隔线之后的梗概不给读者只给账房、编剧半途失声保留已写、无监听不流式
[POS]: tests 的主循环验证，证明 LLM 编织剧情与选项、基础设施掌管原著世界并负责记住、裁决与校准
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import unittest

from tianlong.engine import Game
from tianlong.narrative.llm import LLMError
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
                return reply
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
        self.assertIn("龚光杰刺伤褚师弟", "".join(n["text"] for n in seen))
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
        w.player.set("location", "剑湖宫")  # 主角在无事发生的宫院里，厅中与远方的原著都在场外依序上演
        eve_of_month_after(w, far["day"])
        game.act("歇息")
        self.assertIn(far["id"], w.done)
        self.assertEqual(next(e for e in w.truth.events if e["summary"] == far["summary"])["day"], far["day"])  # 日戳是排定之日
        known = lambda: {w.truth.get(i)["summary"] for i in w.knowledge.known}
        self.assertNotIn(far["summary"], known())  # 姑苏远在数十日之外
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
        turn = game.act("替段誉解围")
        self.assertEqual(turn["options"], ["替段誉挡下一掌", "偷看钟灵的布囊", "向左子穆讨教剑法"])
        llm.replies = {**director(), "小说家": WRITER}
        game.act("1")  # 选项即原话，交回导演
        self.assertIn("【主角此刻】替段誉挡下一掌", llm.writer_prompts[-1])
        self.assertIn("段誉→你：结为知交（你替他解了围）", llm.writer_prompts[-1])
        self.assertIn("你替段誉解围，与他结交", llm.writer_prompts[-1])  # 前情记的是编剧核实过的梗概
        self.assertEqual(game.world.graph.get("左子穆", "mood"), "疑心大起")
        self.assertIn("无量剑比剑被一名外客搅乱", [e["summary"] for e in game.world.truth.events])  # 众目之下结交，江湖有传

    def test_journey_time_from_roads_not_llm(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "镇南王府"}]))
        game = Game(World.create(), llm)
        w = game.world
        start, ride = w.clock.day, w.graph.distances(w.here)["镇南王府"]
        turn = game.act("直奔镇南王府")
        self.assertEqual(turn["place"], "镇南王府")
        self.assertEqual((ride, w.clock.day), (2, start + ride))  # 步行 3 日，骑马 2 日；导演只说了"瞬息"

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
        self.assertIn("龚光杰掌掴段誉", w.done)                                        # 厅中那一掌没了对象
        self.assertEqual(w.graph.get("段誉", "status"), "alive")                        # 原著不能把身边的人传送回去挨打

    def test_invented_entities_rejected_and_ledgers_stay_honest(self):
        llm = StubLLM(director(beats=["你隔空一掌击毙乔峰"], effects=[
            {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},
            {"op": "create", "id": "神秘剑客", "type": "person", "attrs": {}},
            {"op": "set", "id": "player", "key": "location", "value": "后山禁地"}]))
        game = Game(World.create(), llm)
        turn = game.act("隔空一掌打死乔峰")
        self.assertEqual(game.world.graph.get("乔峰", "status"), "alive")
        self.assertFalse(game.world.graph.has("神秘剑客"))
        self.assertEqual(len(turn["void"]), 3)
        self.assertIn("乔峰身亡——乔峰不在此地", llm.writer_prompts[-1])                      # 驳回译成人话回告编剧
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
        self.assertEqual(w.graph.get("乔峰", "mood"), "万念俱灰")
        self.assertEqual(w.graph.get("段誉", "status"), "alive")  # 越出相关者
        self.assertLess(w.player["power"], 100)                  # 场外碰不到主角
        self.assertIn("乔峰孤身闯庄", [e["summary"] for e in w.truth.events])


class StreamingTest(unittest.TestCase):
    def test_progress_is_reported_in_order(self):
        llm = StreamLLM(director(), ["剑光", "一闪，", "\n满堂寂然。"])
        events = []
        turn = Game(World.create(), llm).act("看", on=lambda kind, data: events.append((kind, data)))
        kinds = [k for k, _ in events]
        self.assertEqual(kinds, ["stage", "stage", "stage", "head", "text", "text", "text"])
        self.assertEqual([d for k, d in events if k == "stage"], ["direct", "settle", "write"])
        head = events[3][1]
        self.assertEqual((head["text"], head["options"]), ("", ["一", "二", "三"]))  # 落笔前，除正文外都已定
        self.assertEqual(turn["text"], "剑光一闪，\n满堂寂然。")

    def test_tail_is_kept_from_the_reader_but_feeds_the_ledger(self):
        llm = StreamLLM(director(), ["剑光一闪。", "\n===\n梗概：", "你看了一眼\n传言：无"])
        shown = []
        game = Game(World.create(), llm)
        turn = game.act("看", on=lambda kind, data: shown.append(data) if kind == "text" else None)
        self.assertEqual(("".join(shown), turn["text"]), ("剑光一闪。", "剑光一闪。"))      # 读者只见正文
        self.assertTrue(game.world.player["journal"][-1].endswith("：你看了一眼"))           # 账房得到梗概

    def test_writer_falling_silent_midway_keeps_what_was_written(self):
        llm = StreamLLM(director(), ["前半句已写成，", LLMError("断流")])
        turn = Game(World.create(), llm).act("看", on=lambda *_: None)
        self.assertEqual(turn["text"], "前半句已写成，")

    def test_without_listener_nothing_streams(self):
        llm = StreamLLM(director(), [AssertionError("不该流式")])
        self.assertEqual(Game(World.create(), llm).act("看")["text"], "（正文）")


if __name__ == "__main__":
    unittest.main()
