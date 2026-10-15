"""
[INPUT]: 依赖 tianlong.world 的 situation / adjudicate / perspective / rag / crowd 与 data/canon 原著世界，tianlong.narrative 的 prompts；复用 tests/test_adjudicate 的 plan / judge / GO
[OUTPUT]: unittest 用例——v12 P1-6 望见：隔着悬崖、险径、水路望得见、够不着。日志第 11 回导演要写崖下山道间的段誉与林莽间的帮众，手里只有「赶来」，
          拍文写他们在崖下，账上却到了崖上；第 12 回导演改口「竟已兜转摸上高崖」，伏在岩后的主角当即与二十八人短兵相接：
          望得见的地方(高崖望无量山、山崖望谷底、练武厅望不见)、望得见的人与人群、写了望见的远处举动不报 absent 而开口报 afar(返工不作废)、
          走到之后才望见、望不见的只丢这一条、望见不上名册、人群叫法、生人望见不立信念、编剧只见叫法与【远处可见】而导演见【隔着关口望得见】、试演与定稿同一结果
[POS]: tests 的望见验证——v12 P1-6 的离线证据：「眼前」之外另开一档，看得见、听不见、够不着
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import json
import unittest

from tests.test_adjudicate import GO, judge, plan
from tianlong.narrative import prompts
from tianlong.world import adjudicate, perspective, rag, situation
from tianlong.world.world import World

SEE = lambda x: {"做": "望见", "对": x}
CLIFF = "澜沧江边高崖"


def cliff_top():
    """主角在澜沧江边高崖，段誉、钟灵在崖下的无量山。"""
    w = World.create("测")
    w.player.set("location", CLIFF)
    for p in ("段誉", "钟灵"):
        w.graph.set(p, "location", "无量山")
    return w


class VistaTest(unittest.TestCase):
    def test_where_one_can_see_but_not_reach(self):
        w = World.create("测")
        self.assertEqual(situation.vista(w), set())                                     # 练武厅：宫门—无量山没有关口，走得到，不算望见
        w.player.set("location", CLIFF)
        self.assertEqual(situation.vista(w), {"无量山"})                                 # 隔着险径
        w.player.set("location", "无量山·山崖")
        self.assertEqual(situation.vista(w), {"无量山·谷底"})                            # 隔着悬崖

    def test_who_can_be_seen(self):
        able = situation.sightable(cliff_top())
        self.assertTrue({"段誉", "钟灵", "神农攻山帮众"} <= able)


class SightTest(unittest.TestCase):
    def test_a_distant_gesture_needs_a_sighting_not_an_arrival(self):
        w = cliff_top()
        r = judge(w, plan((None, "崖下山道间，段誉挥手招呼钟灵", [])))
        self.assertIn("absent", [f.kind for f in r.hard])                               # 不写望见：让不在身边的人言行
        w = cliff_top()
        r = judge(w, plan((None, "崖下山道间，段誉挥手招呼钟灵", [SEE("段誉"), {"做": "望见", "谁": "钟灵"}])))
        self.assertEqual(r.hard, [])
        self.assertEqual(w.turn["sighted"], ["段誉", "钟灵"])                            # 写在「谁」上也认
        self.assertFalse({"段誉", "钟灵"} & situation.around(w))
        self.assertFalse({"段誉", "钟灵"} & perspective.audience(w))                     # 听不见
        w.sync()
        self.assertEqual(w.knowledge.view("段誉").get("location"), "无量山")              # 开局见过他：只校正所在

    def test_speaking_from_afar_is_heard_by_no_one(self):
        for beat in ((None, "崖下段誉高声叫道：「钟姑娘，快走！」", [SEE("段誉")]),
                     ("段誉", "段誉在崖下挥手：「快走！」", [SEE("段誉")])):
            w = cliff_top()
            r = judge(w, plan(beat))
            self.assertIn("afar", [f.kind for f in r.hard])
            self.assertNotIn(1, adjudicate.doomed(r))                                   # 返工一次，不作废
        w = cliff_top()
        r = judge(w, plan((None, "段誉沿着山道往下走", [SEE("段誉")])))
        self.assertEqual(r.hard, [])

    def test_the_sight_comes_after_the_walk(self):
        w = World.create("测")
        w.graph.set("段誉", "location", CLIFF)
        r = judge(w, plan(("player", "你出了宫门来到无量山，抬头见高崖上段誉挥手", [GO("无量山"), SEE("段誉")])))
        self.assertEqual(w.here, "无量山")
        self.assertEqual(r.hard, [])
        self.assertEqual(w.turn["sighted"], ["段誉"])                                   # 望的是到了之后的景

    def test_a_soft_state_of_one_sighted_lands(self):
        w = cliff_top()
        judge(w, plan((None, "崖下的青衫少年神色惶急，频频回望", [{"做": "打算", "谁": "段誉", "为": "护着少女下山"}, SEE("段誉")])))
        self.assertEqual(w.graph.get("段誉", "intent"), "护着少女下山")                  # 同批望见了他：打算够得着(B3)
        w = cliff_top()
        judge(w, plan((None, "崖下的青衫少年神色惶急", [{"做": "打算", "谁": "段誉", "为": "护着少女下山"}])))
        self.assertIsNone(w.graph.get("段誉", "intent"))                                 # 没望见：够不着

    def test_what_cannot_be_seen_drops_alone(self):
        w = cliff_top()
        r = judge(w, plan((None, "你极目远眺", [SEE("乔峰")])))
        self.assertEqual(r.hard, [])
        self.assertTrue(any("乔峰不在望得见的地方" in v for v in r.void))
        self.assertNotIn(1, adjudicate.doomed(r))

    def test_a_sighting_does_not_list_them(self):
        w = World.create("测")
        w.player.set("location", "无量山")
        w.graph.set("段誉", "location", "无量山")
        self.assertIn("段誉", situation.elsewhere(w))
        judge(w, plan((None, "你远远望见山道上一个青衫人影", [SEE("段誉")]), ("段誉", "那青衫人影在山道上踱来踱去", [])))
        self.assertNotIn("段誉", situation.cast(w))                                      # 署名也不拉上名册
        self.assertNotIn("段誉", situation.around(w))

    def test_a_crowd_by_its_handle(self):
        w = cliff_top()
        judge(w, plan((None, "林莽间晃动着数十道黄衫人影", [SEE("神农帮众")])))
        self.assertEqual(w.turn["sighted"], ["神农攻山帮众"])

    def test_a_strangers_name_does_not_leak_from_a_glance(self):
        w = cliff_top()
        self.assertFalse(w.knowledge.knows("阿洪"))
        judge(w, plan((None, "崖下有人策马而过", [SEE("阿洪")])))
        w.sync()
        self.assertFalse(w.knowledge.knows("阿洪"))                                      # 不新立信念
        w.turn = {}                                                                     # 下一回合
        self.assertNotIn("阿洪", perspective.mask(w, "阿洪策马而过"))

    def test_the_writer_and_the_director_see_it_their_ways(self):
        w = cliff_top()
        judge(w, plan((None, "崖下山道间，一个青衫少年挥手", [SEE("段誉")])))
        view = perspective.veil(w, rag.build(w))
        self.assertEqual(view["afar"][0]["name"], "青衫少年")
        text = prompts.render(view)
        self.assertIn("【远处可见·隔着关口望得见、听不见、够不着】", text)
        self.assertNotIn("段誉", text)
        back = prompts.render_backstage(rag.backstage(cliff_top()))
        self.assertIn("【隔着关口望得见·不在眼前", back)
        self.assertIn("段誉（镇南王世子）在无量山（隔着险径）", back)

    def test_the_same_plan_twice_is_the_same_world(self):
        w = cliff_top()
        p = plan((None, "崖下山道间，段誉挥手招呼钟灵", [SEE("段誉"), SEE("钟灵")]))
        a, b = copy.deepcopy(w), copy.deepcopy(w)
        judge(a, copy.deepcopy(p))
        judge(b, copy.deepcopy(p))
        self.assertEqual(json.dumps(a.dump(), ensure_ascii=False, sort_keys=True), json.dumps(b.dump(), ensure_ascii=False, sort_keys=True))
        self.assertEqual(a.turn["sighted"], b.turn["sighted"])


if __name__ == "__main__":
    unittest.main()
