"""
[INPUT]: 依赖 tianlong.world 的 settle / perspective / situation 与 data/canon 原著世界，tianlong.engine 的 Game；以桩 LLM(含账房与复核)替代 Gemini
[OUTPUT]: unittest 用例——v7 把账文同构补齐成四条轴：
          两相对账(账上变了、正文没写到的由账本补记：人走了、名字只在拍里报过、东西到了手；写到了就不补；账房指出的照补；结算从正文记下的不补；补记随流送出、放行即存档，戏里没有人听见补记)；
          叫法即主键(四个「无量剑东宗的少年」落笔之前各分一个稳定外号、叫法落得回原人、人散了外号不改、立外号不算扰动原著、分开了就不再动)；
          双录复核(词表看出而账房漏记的句子交复核：复核记账即入账、裁定不记即作罢、离线才是分歧；离线说书人写进正文的作废之拍不是分歧)；
          正文有时间轴(动身之前在厅上报的名厅上的人听见、到了后山报的名厅上的人听不见、结算单在据所在那一刻的听众里生效；
          同一段里在动身之处切开、出了厅门而没写去处也算动身、别人出厅不是你动身、想起江边不是到了江边)；
          看得见与听得见(对着遗体叫出「容师叔」，死者是谁满厅皆知、不记分歧；「持剑少年见容师叔毙命」死的是容师叔，不返工)
[POS]: tests 的对账验证——v7 根治 v6 留下的四个缺口：反方向的遗漏、同一叫法的几个人、账房的召回率、正文里动身之前说的话；
       另收两局真模型实测抓到的病：遗体的名字落不了账、「姓+称谓」认错了死者
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_engine import StreamLLM, StubLLM, director
from tianlong.engine import Game
from tianlong.world import perspective, situation
from tianlong.world.world import World

CALM = {"canon": {"unfolds": False, "why": "测试里不演原著"}}  # 不让开场的比剑给账上添一笔伤，只看本条用例的那件事
GO = lambda dest: {"op": "set", "id": "player", "key": "location", "value": dest}
EAST = ("干光豪", "郁光标", "钱光胜", "龚光杰")


def page(text: str) -> str:
    return f"{text}\n===\n梗概：记\n传言：无"


def game(beats, prose, **extra) -> Game:
    return Game(World.create("郑大风", origin="随从"), StubLLM({**director(beats=beats, **CALM), "小说家": page(prose), **extra}))


class TwoWayTest(unittest.TestCase):
    """两相对账：账上变了、主角看得见、正文却没写到的，由账本补记一句接在正文之后。"""

    def test_a_departure_the_page_forgot_is_recorded(self):
        g = game([{"who": "段誉", "to": "player", "text": "段誉拱手作别", "ops": [{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"}]}],
                 "厅中众人议论纷纷。")
        shown = []
        turn = g.act("看看四周", on=lambda kind, data: shown.append(data) if kind == "text" else None)
        self.assertTrue(turn["text"].endswith("（青衫少年离开了。）"))              # 人走了，正文一字未提：账本补记
        self.assertEqual("".join(shown), turn["text"])                             # 补记随流送出，放行的就是存下的

    def test_a_name_only_the_beat_heard_reaches_the_page(self):
        g = game([{"who": "段誉", "to": "player", "text": "段誉还礼道：「小生段誉。」", "ops": []}], "那青衫少年还了一礼。")
        turn = g.act("向那位青衫少年拱手搭话")
        self.assertTrue(perspective.knows(g.world, "player", "段誉"))
        self.assertIn("青衫少年原来名叫段誉", turn["text"])                         # 账上知道了名字，读者也读到了它
        self.assertFalse(perspective.knows(g.world, "辛双清", "段誉"))              # 补记是账本对读者说的，满厅的人没有因此听见

    def test_what_the_page_already_says_is_not_repeated(self):
        g = game([{"who": "段誉", "to": "player", "text": "段誉还礼道：「小生段誉。」", "ops": []}], "那青衫少年还礼道：「小生段誉。」")
        turn = g.act("向那位青衫少年拱手搭话")
        self.assertNotIn("（", turn["text"].replace("（", "", 0)[-1:] + "")         # 无补记
        self.assertNotIn("原来名叫", turn["text"])

    def test_the_accountant_points_out_what_the_page_left_out(self):
        beats = [{"who": "褚师弟", "to": "player", "text": "褚师弟将青钢剑塞给你", "ops": [{"op": "set", "id": "褚师弟青钢剑", "key": "holder", "value": "player"}]}]
        settle_bill = {"账房": {"changes": [], "rifts": [], "未写到": [1]}}
        g = game(beats, "你瞧了一眼那青钢剑，没有作声。", **settle_bill)        # 字眼写到了，账房仍说没交代清楚
        turn = g.act("看看四周")
        self.assertIn("青钢剑到了你手上", turn["text"])

    def test_what_the_page_settled_is_not_recorded_again(self):
        prose = "那青衫少年起身出厅而去。"
        settle_bill = {"账房": {"changes": [{"据": "那青衫少年起身出厅而去", "谁": "段誉",
                                             "ops": [{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"}]}],
                                "rifts": [], "未写到": []}}
        turn = game([], prose, **settle_bill).act("看看四周")
        self.assertNotIn("离开了", turn["text"])                                   # 正文自己写的，结算记下了，不必补


    def test_a_few_steps_within_the_compound_drag_no_one_along(self):
        g = game([{"who": "player", "text": "你踱出厅门，到了宫院里", "ops": [GO("剑湖宫")]}], "你踱出厅门，到了宫院里。")
        turn = g.act("出厅走走")
        self.assertNotIn("随你同行", turn["text"])                                  # 近旁之内挪几步：厅上的人不是跟着你走的
        self.assertNotIn("离开了", turn["text"])

    def test_leaving_far_reports_where_you_are_not_who_stayed(self):
        g = game([{"who": "player", "text": "你出了练武厅，直往后山去", "ops": [GO("无量后山")]}], "你出了练武厅，一路疾行。")
        turn = g.act("去后山")
        self.assertIn("你到了无量后山", turn["text"])                               # 正文没说到了哪里：补一句
        self.assertNotIn("离开了", turn["text"])                                   # 被留在厅上的人不是「离开了」


class HandleTest(unittest.TestCase):
    """叫法即主键：主角眼中叫不出名字的人，叫法两两不同。"""

    def test_four_eastern_disciples_are_four_people(self):
        g = game([], "厅中众人议论纷纷。")
        g.act("看看四周")
        w = g.world
        names = {perspective.handle(w, p) for p in EAST}
        self.assertEqual(len(names), 4)                                            # 落笔之前各分一个外号
        self.assertIn("无量剑东宗的持剑少年", names)                                # 手里有剑的就叫持剑的
        self.assertEqual({perspective.by_handle(w, h) for h in names}, set(EAST))  # 叫法落得回原人
        handles = [perspective.handle(w, p) for p in situation.around(w)]
        self.assertEqual(len(handles), len(set(handles)))
        before = perspective.handle(w, "郁光标")
        w.graph.set("郁光标", "location", "无量后山")                               # 人散了，外号不改回去
        self.assertEqual(perspective.handle(w, "郁光标"), before)

    def test_naming_people_apart_does_not_disturb_the_canon(self):
        w = World.create("郑大风", origin="随从")
        w.apply(perspective.distinguish(w), "director")
        self.assertEqual(w.taint, set())                                           # 立个外号不算扰动原著
        self.assertEqual(perspective.distinguish(w), [])                           # 分开了就不再动


class RecheckTest(unittest.TestCase):
    """双录复核：词表看出、账房漏记的句子交账房逐句裁定。"""

    BEATS = [{"who": "player", "text": "你出了练武厅，直奔后山", "ops": [GO("无量后山")]}]
    PROSE = "你携着那青衫少年出了练武厅，直奔后山。"

    def test_a_follow_the_accountant_missed_is_rechecked_into_the_books(self):
        verdict = {"复核": {"changes": [{"据": "你携着那青衫少年出了练武厅，直奔后山", "谁": "player",
                                       "ops": [{"op": "link", "src": "段誉", "dst": "player", "rel": "随行"}]}], "不记": []}}
        g = game(self.BEATS, self.PROSE, **{"账房": {"changes": [], "rifts": [], "未写到": []}}, **verdict)
        g.act("出练武厅")
        self.assertIn("段誉", situation.party(g.world))                             # 复核记了账：他随你同行
        self.assertFalse(any("青衫少年" in d for d in g.world.player["drift"]))     # 不再是分歧

    def test_a_sentence_ruled_unreal_is_not_a_rift(self):
        verdict = {"复核": {"changes": [], "不记": [{"据": "你携着那青衫少年出了练武厅，直奔后山", "缘由": "只是虚写"}]}}
        g = game(self.BEATS, self.PROSE, **{"账房": {"changes": [], "rifts": [], "未写到": []}}, **verdict)
        g.act("出练武厅")
        self.assertNotIn("段誉", situation.party(g.world))
        self.assertFalse(any("携着" in d for d in g.world.player["drift"]))

    def test_an_act_marked_as_never_happened_is_not_a_rift(self):
        g = Game(World.create("郑大风", origin="随从"), None)                       # 离线说书人把作废之拍照原样写进正文
        g.act("借故离开练武厅，往后山去")
        self.assertIn("未曾发生", g.last_text)
        self.assertFalse(any("离开" in d for d in g.world.player["drift"]))          # 「…——未曾发生」整句是否定：不是分歧

    def test_offline_the_word_list_only_records_a_rift(self):
        g = game(self.BEATS, self.PROSE)
        g.act("出练武厅")
        self.assertNotIn("段誉", situation.party(g.world))                          # 没有账房：词表不替正文挪人
        self.assertTrue(any("携着那青衫少年" in d for d in g.world.player["drift"]))


class TimelineTest(unittest.TestCase):
    """正文有时间轴：一段正文写的是主角在哪一处的事，从它听出的名字只那一处的人听见。"""

    BEATS = [{"who": "player", "text": "你环顾厅中", "ops": []},
             {"who": "player", "text": "你出了练武厅，直往后山去", "ops": [GO("无量后山")]}]

    def test_a_name_given_in_the_hall_before_leaving_is_heard_in_the_hall(self):
        prose = "你环顾厅中，朗声道：「在下郑大风，见过诸位。」\n你出了练武厅，一路奔到后山。"
        g = game(self.BEATS, prose)
        g.act("出练武厅去后山")
        self.assertEqual(g.world.here, "无量后山")
        self.assertTrue(perspective.knows(g.world, "左子穆", "player"))             # 动身之前在厅上报的名：厅上的人听见了

    def test_a_name_given_on_the_back_hill_is_not_heard_in_the_hall(self):
        prose = "你环顾厅中，没有作声。\n你出了练武厅，一路奔到后山。四下无人，你自语道：「在下郑大风，到此一游。」"
        g = game(self.BEATS, prose)
        g.act("出练武厅去后山")
        self.assertFalse(perspective.knows(g.world, "左子穆", "player"))            # 到了后山才报的名：厅上的人听不见

    def test_the_accountants_entry_takes_effect_where_its_sentence_was_said(self):
        prose = "你环顾厅中，拱手道：「诸位请了。」\n你出了练武厅，一路奔到后山。"
        settle_bill = {"账房": {"changes": [{"据": "拱手道：「诸位请了。」", "谁": "player",
                                             "ops": [{"op": "reveal", "id": "player", "key": "name"}]}],
                                "rifts": [], "未写到": []}}
        g = game(self.BEATS, prose, **settle_bill)
        g.act("出练武厅去后山")
        self.assertTrue(perspective.knows(g.world, "辛双清", "player"))             # 那句话是在厅上说的：厅上的人记下了

    RIVER = [{"who": "player", "text": "你出了练武厅，直奔江边", "ops": [GO("澜沧江")]}]

    def river(self, prose):
        g = game(self.RIVER, prose)
        w = g.world
        w.graph.set("钟灵", "location", "澜沧江")                                   # 江边有人：到了那里说的话有人听
        w.graph.set("钟灵", "hidden", False)
        g.act("出练武厅去江边")
        self.assertEqual(w.here, "澜沧江")
        return w

    def test_one_paragraph_cut_where_you_set_out(self):
        w = self.river("你朗声道：「在下郑大风，告辞！」转身出了练武厅，一路奔到澜沧江边，见江边立着一个少女。")
        self.assertTrue(perspective.knows(w, "左子穆", "player"))                   # 同一段里动身之前说的：厅上的人听见
        self.assertFalse(perspective.knows(w, "钟灵", "player"))                    # 江边的人那时不在

    def test_setting_out_moves_the_clock_even_when_the_place_goes_unnamed(self):
        w = self.river("你向厅上众人一拱手，转身出了厅门。\n江边立着一个少女，你上前道：「在下郑大风，见过姑娘。」")
        self.assertTrue(perspective.knows(w, "钟灵", "player"))                     # 出了厅门之后说的：江边的人听见
        self.assertFalse(perspective.knows(w, "左子穆", "player"))                  # 厅上的人听不见

    def test_a_place_remembered_is_not_a_place_reached(self):
        w = self.river("你想起昨日在澜沧江边见过的少女，朗声道：「在下郑大风，告辞！」\n你转身出了厅门，一路奔到澜沧江边。")
        self.assertTrue(perspective.knows(w, "左子穆", "player"))                   # 想起江边，人还在厅上
        self.assertFalse(perspective.knows(w, "钟灵", "player"))

    def test_someone_elses_departure_is_not_yours(self):
        w = self.river("那青衫少年起身出了练武厅。你朗声道：「在下郑大风，见过诸位！」\n你随后出厅，奔到澜沧江边。")
        self.assertTrue(perspective.knows(w, "左子穆", "player"))                   # 走的是青衫少年，你还在厅上
        self.assertFalse(perspective.knows(w, "钟灵", "player"))


class EyesTest(unittest.TestCase):
    """名字是谁的要看得见，谁听见要在耳边：对着遗体叫出的名字落得到死者身上；「容师叔」也是一种叫法。"""

    def body(self, beats, prose) -> Game:
        g = game(beats, prose)
        g.world.graph.set("容子矩", "location", "剑湖宫·练武厅")
        g.world.graph.set("容子矩", "status", "dead")
        g.world.graph.set("龚光杰", "epithet", "持剑少年")
        return g

    def test_a_name_called_over_a_body_names_the_dead(self):
        g = self.body([], "持剑少年扑到那具尸身旁，惊呼一声：「容师叔！」")
        turn = g.act("看看四周")
        self.assertTrue(perspective.knows(g.world, "player", "容子矩"))            # 认得他的人当面叫出：死者是谁满厅皆知
        self.assertTrue(perspective.knows(g.world, "辛双清", "容子矩"))
        self.assertFalse(g.world.player["drift"])                                  # 不是分歧：正文写对了，账也记下了
        self.assertIn("原来名叫容子矩", turn["text"])                               # 读者只读到「容师叔」：账上记的全名补记一句

    def test_a_call_form_points_at_the_one_called(self):
        beats = [{"who": "龚光杰", "text": "持剑少年见容师叔毙命，怒火攻心，按剑四顾。", "ops": []}]
        g = self.body(beats, "厅中一片死寂。")
        turn = g.act("看看四周")
        self.assertEqual(turn["void"], [])                                         # 死的是容师叔，不是叫他的持剑少年：不返工、不作废
        self.assertNotEqual(g.world.graph.get("龚光杰", "status"), "dead")


class StreamTest(unittest.TestCase):
    def test_the_note_streams_after_the_page(self):
        beats = [{"who": "段誉", "to": "player", "text": "段誉拱手作别", "ops": [{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"}]}]
        llm = StreamLLM({**director(beats=beats, **CALM)}, ["厅中众人", "议论纷纷。", "\n===\n梗概：记\n传言：无"])
        events = []
        turn = Game(World.create("郑大风", origin="随从"), llm).act("看", on=lambda kind, data: events.append((kind, data)))
        texts = [d for k, d in events if k == "text"]
        self.assertEqual(texts[-1], "\n\n（青衫少年离开了。）")                    # 正文送完，补记作最后一段送出
        self.assertEqual("".join(texts), turn["text"])


if __name__ == "__main__":
    unittest.main()
