"""
[INPUT]: 依赖 tianlong.world 的 settle / effects / perspective / situation / adjudicate 与 data/canon 原著世界，tianlong.engine 的 Game；以桩 LLM(含账房)替代 Gemini
[OUTPUT]: unittest 用例——v6「账文同构」：玩家读到的正文是本回合的定本，账本是它经世界裁决的投影。
          用户报告的病(正文里与段誉互报了姓名，账上却不知，之后两回合又互报一遍)及其各种写法；结算覆盖状态的各个维度(去留、易手、神色、打算、现状、应承之事、看法)；
          据须是正文原句；规则之事(生死伤病、功力进境)与主角未起意之举只记分歧、交下回合导演；结算与导演的账幂等；
          出闸放行即存档、报名先入账再掩码(不再「小生兄台」)；低声报名只那人听见；识名指令的几种写法、在场、原样不动、不算污染、不随传闻误读；
          此地原著的亲历以回合开始的所在为准
[POS]: tests 的结算验证——v6 根治「双写」的离线证据：导演的指令与编剧的正文各写各的，结算让下一回合在一本与玩家所读相符的账上接着演
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import judge, plan
from tests.test_engine import StreamLLM, StubLLM, director
from tianlong.engine import Game
from tianlong.world import effects, perspective, settle, situation
from tianlong.world.world import World

SWORD = "褚师弟青钢剑"


def page(text: str, memory: str = "记") -> str:
    return f"{text}\n===\n梗概：{memory}\n传言：无"


def bill(*changes, rifts=()):
    """账房的结算单：changes 为 (据, 谁, ops)。"""
    return {"账房": {"changes": [{"据": b, "谁": who, "ops": ops} for b, who, ops in changes],
                     "rifts": [{"据": b, "账上": t} for b, t in rifts]}}


def people_line(prompt: str, pid: str) -> str:
    """导演上下文【在场人物】里某人的那一行。"""
    return next(line for line in prompt.splitlines() if line.startswith(f"- {pid}｜"))


class UserReportTest(unittest.TestCase):
    """用户报告的病：正文里与段誉互报了姓名，账上却不知，之后两回合又互报一遍。"""

    def setUp(self):
        self.w = World.create("郑大风", origin="随从")

    def _talk(self, prose: str, extra=None):
        llm = StubLLM({**director(beats=[{"who": "player", "to": "段誉", "text": "你上前与那青衫少年寒暄", "ops": []}]),
                       "小说家": page(prose), **(extra or {})})
        game = Game(self.w, llm)
        turn = game.act("向那位青衫少年拱手搭话")
        game.act("与段誉说话")
        return turn, llm

    def test_names_given_in_the_page_are_known_next_turn(self):
        turn, llm = self._talk("你拱手道：「在下郑大风。」那青衫少年还礼道：「小生段誉，大理人氏。」")
        self.assertIn("小生段誉", turn["text"])                                       # 报名先入账再掩码：不再涂成「小生兄台」
        w = self.w
        self.assertTrue(perspective.knows(w, "player", "段誉") and perspective.knows(w, "段誉", "player"))
        line = people_line(llm.director_prompts[-1], "段誉")
        self.assertNotIn("主角不知其名", line)                                        # 下一回合导演不会再让他俩互报一遍
        self.assertNotIn("不知你姓名", line)

    def test_every_way_of_saying_it_settles_the_same(self):
        for prose in ("你与那青衫少年互通了姓名，相谈甚欢。",
                      "那青衫少年拱手道：「小生姓段，单名一个誉字。」你也报了姓名。",
                      "你拱手道：「小弟郑大风。」那青衫少年道：「在下大理段誉。」"):
            with self.subTest(prose=prose):
                self.setUp()
                self._talk(prose)
                self.assertTrue(perspective.knows(self.w, "player", "段誉"))
                self.assertTrue(perspective.knows(self.w, "段誉", "player"))

    def test_the_accountant_settles_what_no_word_list_could_catch(self):
        prose = "那青衫少年听罢，也将自家来历一一说了，原来是大理来的书生。"
        extra = bill(("也将自家来历一一说了", "段誉", [{"op": "reveal", "id": "段誉", "key": "name", "to": "player"}]))
        _, llm = self._talk(prose, extra)
        self.assertTrue(perspective.knows(self.w, "player", "段誉"))                 # 账房读定本记账：词表认不出的写法也入账
        self.assertNotIn("主角不知其名", people_line(llm.director_prompts[-1], "段誉"))

    def test_whispered_names_reach_only_the_one_spoken_to(self):
        w = self.w
        judge(w, plan(("player", "你凑近段誉，压低嗓子道：「在下郑大风。」", [], "段誉")))
        self.assertTrue(perspective.knows(w, "段誉", "player"))
        self.assertFalse(perspective.knows(w, "左子穆", "player"))                   # 满厅的人听不见主角低声报的名
        self.assertFalse(perspective.knows(w, "钟灵", "player"))
        judge(w, plan(("player", "你朗声道：「在下郑大风，见过诸位。」", [])))
        self.assertTrue(perspective.knows(w, "左子穆", "player"))                    # 当众说的，满厅皆闻


    def test_names_told_after_leaving_are_not_heard_back_in_the_hall(self):
        w = self.w
        judge(w, plan(("player", "你奔出练武厅，直往后山去", [{"op": "set", "id": "player", "key": "location", "value": "无量后山"}]),
                      ("player", "你朗声道：「在下郑大风，谁在那里？」", [])))
        self.assertEqual(w.here, "无量后山")
        self.assertFalse(perspective.knows(w, "左子穆", "player"))                   # 主角在后山报的名，厅上的人听不见


class SettleTest(unittest.TestCase):
    """结算：定本里确立而账上没有的变化，经世界裁决落账；规则之事与未起意之举只记分歧。"""

    def setUp(self):
        self.w = World.create("郑大风", origin="随从")

    def test_the_page_settles_every_kind_of_state(self):
        prose = ("那无量剑西宗的少年将青钢剑递到你手中，道：「兄台拿着防身。」那青衫少年起身道：「我去后山走走。」说罢出厅而去。"
                 "左子穆脸色铁青，喝令弟子把守厅门。厅门已被弟子关上。你应承替马五德照看厅外。")  # 编剧看见的是叫法：正文里不识名之人只写叫法
        extra = bill(("将青钢剑递到你手中", "褚师弟", [{"op": "set", "id": SWORD, "key": "holder", "value": "player"}]),
                     ("说罢出厅而去", "段誉", [{"op": "set", "id": "段誉", "key": "location", "value": "无量后山"}]),
                     ("左子穆脸色铁青，喝令弟子把守厅门", "左子穆", [{"op": "set", "id": "左子穆", "key": "mood", "value": "铁青"},
                                                             {"op": "set", "id": "左子穆", "key": "intent", "value": "令弟子把守厅门"}]),
                     ("厅门已被弟子关上", "左子穆", [{"op": "set", "id": "剑湖宫·练武厅", "key": "state", "value": "厅门紧闭，弟子把守"}]),
                     ("你应承替马五德照看厅外", "player", [{"op": "push", "id": "player", "key": "threads", "value": "替马五德照看厅外"}]))
        llm = StubLLM({**director(), "小说家": page(prose), **extra})
        game = Game(self.w, llm)
        turn = game.act("看看四周")
        w = self.w
        self.assertIn(SWORD, w.player["inventory"])                                  # 易手
        self.assertEqual(w.graph.get("段誉", "location"), "无量后山")               # 去留
        self.assertNotIn("段誉", situation.around(w))
        self.assertEqual(w.graph.get("剑湖宫·练武厅", "state"), "厅门紧闭，弟子把守")  # 现状
        self.assertIn("替马五德照看厅外", w.player["threads"])                       # 应承之事
        self.assertIn(SWORD, "".join(t["text"] for t in turn["status"]))            # 界面的身况与账本同一口径
        game.act("看看四周")
        prompt = llm.director_prompts[-1]
        self.assertIn("此刻神色：铁青", people_line(prompt, "左子穆"))                # 下一回合导演看见的就是玩家读到的
        self.assertIn("眼下之事：令弟子把守厅门", people_line(prompt, "左子穆"))
        self.assertIn("厅门紧闭", prompt)
        self.assertNotIn("- 段誉｜", prompt)

    def test_a_basis_not_in_the_page_is_not_taken(self):
        extra = bill(("段誉把长命金牌赠给了你", "段誉", [{"op": "set", "id": "段誉长命金牌", "key": "holder", "value": "player"}]))
        Game(self.w, StubLLM({**director(), "小说家": page("厅中众人议论纷纷。"), **extra})).act("看看四周")
        self.assertNotIn("段誉长命金牌", self.w.player["inventory"])                # 账房自己编的出处：不收

    def test_rules_are_not_changed_by_the_page_but_reconciled_next_turn(self):
        prose = "左子穆惨呼一声，气绝身亡。"
        extra = bill(("左子穆惨呼一声，气绝身亡", "左子穆", [{"op": "set", "id": "左子穆", "key": "status", "value": "dead"}]))
        llm = StubLLM({**director(), "小说家": page(prose), **extra})
        game = Game(self.w, llm)
        game.act("看看四周")
        self.assertEqual(self.w.graph.get("左子穆", "status"), "alive")             # 生死归规则：正文改不了账
        self.assertTrue(any("气绝身亡" in d for d in self.w.player["drift"]))         # 记作分歧
        game.act("看看四周")
        self.assertIn("上回合正文与账本的分歧", llm.director_prompts[-1])            # 下回合导演由剧情圆回

    def test_the_heros_unchosen_deeds_stay_unwritten(self):
        prose = "你趁乱将地上的青钢剑揣入怀中。"
        extra = bill(("你趁乱将地上的青钢剑揣入怀中", "player", [{"op": "push", "id": "player", "key": "inventory", "value": SWORD}]))
        Game(self.w, StubLLM({**director(), "小说家": page(prose), **extra})).act("看看四周")
        self.assertNotIn(SWORD, self.w.player["inventory"])                          # 玩家没指着它：编剧替主角拿的不入账
        self.assertTrue(any("并未起意" in d for d in self.w.player["drift"]))

    def test_settling_twice_is_settling_once(self):
        follow = {"op": "link", "src": "段誉", "dst": "player", "rel": "随行"}
        llm = StubLLM({**director(beats=[{"who": "段誉", "to": "player", "text": "段誉道：「我随兄台走一遭。」", "ops": [follow]}]),
                       "小说家": page("段誉道：「我随兄台走一遭。」便跟在你身后。"),
                       **bill(("便跟在你身后", "段誉", [dict(follow)]))})
        Game(self.w, llm).act("看看四周")
        edges = [e for e in self.w.graph.edges if (e["src"], e["dst"], e["rel"]) == ("段誉", "player", "随行")]
        self.assertEqual(len(edges), 1)                                              # 导演落过的账，结算再写一遍也只是一件事
        self.assertEqual(len([x for x in self.w.graph.get("段誉", "bond")["log"] if "同行" in x["why"]]), 1)

    def test_a_misspelt_id_is_the_accountants_slip_not_a_rift(self):
        extra = bill(("左子穆脸色铁青", "zuo_zimu", [{"op": "set", "id": "zuo_zimu", "key": "mood", "value": "铁青"}]))
        Game(self.w, StubLLM({**director(), "小说家": page("左子穆脸色铁青。"), **extra})).act("看看四周")
        self.assertFalse(any("zuo_zimu" in d for d in self.w.player["drift"]))         # 拼音的 id 不入账，也不冒充分歧交给导演

    def test_offline_the_word_list_still_records_the_rifts(self):
        game = Game(self.w, StubLLM({**director(), "小说家": page("你俯身拾起神仙姊姊玉钏，揣入怀中。")}))
        game.act("看")                                                               # 没有账房：词表对账，只记分歧不改账
        self.assertTrue(any("玉钏" in d for d in self.w.player["drift"]))


class GateTest(unittest.TestCase):
    """出闸：正文按段放行，放行的拼起来就是存下的正文；报名先入账再掩码。"""

    def setUp(self):
        self.w = World.create("郑大风", origin="随从")

    def test_released_is_stored(self):
        llm = StreamLLM(director(), ["那青衫少年拱手道：「小生", "段誉。」\n\n", "你也报了姓名。", "\n===\n梗概：记\n传言：无"])
        shown = []
        turn = Game(self.w, llm).act("看", on=lambda kind, data: shown.append(data) if kind == "text" else None)
        self.assertEqual("".join(shown), turn["text"])                               # 读者读到的逐字就是存下的(补记也在其中)
        self.assertTrue(turn["text"].startswith("那青衫少年拱手道：「小生段誉。」\n\n你也报了姓名。"))
        self.assertTrue(perspective.knows(self.w, "player", "段誉"))

    def test_a_name_that_cannot_be_heard_is_dropped_not_mangled(self):
        gate = settle.Gate(self.w)
        gate.feed("远处的说书人学舌道：「在下木婉清。」")
        gate.close()
        self.assertFalse(perspective.knows(self.w, "player", "木婉清"))             # 她不在眼前：这名字没人当面报给你
        self.assertNotIn("兄台", gate.text)
        self.assertIn("「在下。」", gate.text.replace("在下木婉清", "在下"))

    def test_strangers_cannot_name_the_hero_in_the_page(self):
        gate = settle.Gate(self.w)
        gate.feed("龚光杰冷笑道：「郑大风，你也配？」")
        gate.close()
        self.assertNotIn("郑大风", gate.text)                                       # 他不知主角姓名：正文里也叫不出
        self.assertIn("兄台", gate.text)


class NamingOpTest(unittest.TestCase):
    """识名是一等指令：reveal 的 id 形，导演可宣告，几种写法同一口径。"""

    def setUp(self):
        self.w = World.create("郑大风", origin="随从")

    def test_the_ways_a_director_declares_a_name(self):
        w = self.w
        applied, rejected = effects.apply(w, [{"op": "set", "id": "段誉", "key": "epithet", "value": "段誉"},       # 给段誉立外号「段誉」
                                              {"op": "reveal", "src": "player", "dst": "钟灵", "rel": "姓名"},       # 关系形
                                              {"op": "push", "id": "player", "key": "acquaintances", "value": "龚光杰"},
                                              {"op": "reveal", "id": "木婉清", "key": "name"}], "director")        # 不在眼前
        self.assertTrue(all(effects.named(op) for op in applied))
        self.assertTrue(perspective.knows(w, "player", "段誉") and perspective.knows(w, "钟灵", "player"))
        self.assertTrue(perspective.knows(w, "player", "龚光杰"))
        self.assertEqual([op["id"] for op, _ in rejected], ["木婉清"])
        self.assertEqual(w.taint, set())                                              # 报个姓名不算扰动原著
        self.assertEqual(effects.apply(w, [{"op": "reveal", "id": "段誉", "key": "name"}], "director"), ([], []))  # 人人已知：不是一件事

    def test_a_declared_name_needs_someone_to_say_it(self):
        w = self.w
        r = judge(w, plan(("龚光杰", "龚光杰长剑一挺，怒喝道：「哪个要你来品评？」", [{"op": "reveal", "id": "龚光杰", "key": "name"}], "段誉"),
                          ("段誉", "段誉还礼道：「小生段誉。」", [{"op": "reveal", "id": "段誉", "key": "name"}], "player")))
        self.assertFalse(perspective.knows(w, "player", "龚光杰"))                  # 没人说出口：不因导演想在旁白里叫他就算知道
        self.assertTrue(any(f.kind == "baseless" for f in r.soft))
        self.assertTrue(perspective.knows(w, "player", "段誉"))                     # 说出口了：照文字落账
        self.assertFalse(perspective.knows(w, "左子穆", "段誉"))                    # 说给主角听的：谁听见由文字定

    def test_a_named_event_travels_without_breaking_the_rumour_mill(self):
        w = self.w
        applied, _ = effects.apply(w, [{"op": "reveal", "id": "段誉", "key": "name"}], "director")
        w.record("段誉自报家门", w.here, applied, "director", witnessed=True)
        w.sync()                                                                      # 识名(id 形)当场已落，不被当作隐情误读


class WitnessTest(unittest.TestCase):
    def test_canon_staged_here_is_witnessed_even_if_the_hero_then_leaves(self):
        llm = StubLLM(director(effects=[{"op": "set", "id": "player", "key": "location", "value": "无量后山"}]))
        game = Game(World.create("离线"), llm)
        game.open()
        w = game.world
        self.assertEqual(w.here, "无量后山")
        ev = next(e for e in w.truth.events if e["summary"].startswith("龚光杰刺伤褚师弟"))
        self.assertTrue(ev["witnessed"])                                             # 导演把它编在主角动身之前：亲历以回合开始的所在为准


if __name__ == "__main__":
    unittest.main()
