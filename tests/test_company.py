"""
[INPUT]: 依赖 tianlong.world 的 adjudicate / effects / situation 与 data/canon 原著世界；复用 tests/test_adjudicate 的 plan / judge / GO
[OUTPUT]: unittest 用例——v12 B1 同行与押解随调遣：15 回实录里第 4 回导演结下「段誉—随行→钟灵」，第 11 回只赶来段誉，钟灵留在无量山，这条边悬空到终局：
          赶来段誉钟灵同来(边的方向反过来亦然)、赶来擒者人质同来且仍受制、送段誉去大理城钟灵同去、受制于不在场之人的同行者不被拆走、
          原著挪人不带人而回合末了断异地的同行、离队的同伴不再瞬移回主角身边(同一回合先送走后移动亦然)、本回合已被原著挪过的同伴不被带走；
          v12 P1-3 近处的熟人另收三日内见过的人、附注同行(MetTest)
[POS]: tests 的同行连带验证——v12 B1 的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import unittest

from tests.test_adjudicate import GO, judge, plan
from tianlong.world import adjudicate, effects, situation
from tianlong.world.world import World

COME = lambda pid: {"做": "赶来", "谁": pid}
SEND = lambda pid, to: {"做": "前往", "谁": pid, "到": to}


class CompanyTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.g = self.w.graph
        self.w.player.set("location", "澜沧江边高崖")
        for p in ("段誉", "钟灵"):
            self.g.set(p, "location", "无量山")

    def test_summoning_one_brings_the_other(self):
        for src, dst in (("段誉", "钟灵"), ("钟灵", "段誉")):                       # 边的方向反过来，结果相同
            self.setUp()
            self.g.link(src, dst, "随行")
            r = judge(self.w, plan(("段誉", "段誉奔上崖来，身后跟着一名少女", [COME("段誉")])))
            self.assertEqual({self.g.get(p, "location") for p in ("段誉", "钟灵")}, {"澜沧江边高崖"})
            self.assertTrue({"段誉", "钟灵"} <= situation.around(self.w))           # 第 11 回：钟灵同来，二人都在眼前
            self.assertEqual([f.kind for f in r.hard], [])
            self.assertIn({"op": "arrive", "id": "钟灵", "by": "段誉"}, r.applied)   # 连带也是成立的指令

    def test_the_hostage_comes_with_the_captor(self):
        g = self.g
        g.set("司空玄", "location", "无量山")
        g.link("司空玄", "钟灵", "扣为人质")
        r = judge(self.w, plan(("司空玄", "司空玄押着一名少女上了崖", [COME("司空玄")])))
        self.assertEqual(g.get("钟灵", "location"), "澜沧江边高崖")
        self.assertIn("司空玄", situation.captors(self.w, "钟灵"))                  # 仍受制
        self.assertNotIn("custody", [f.kind for f in r.hard])                      # 擒者与人质不再死锁

    def test_sending_one_away_takes_the_companion(self):
        g, w = self.g, self.w
        for p in ("段誉", "钟灵"):
            g.set(p, "location", "澜沧江边高崖")
        g.link("段誉", "钟灵", "随行")
        judge(w, plan(("段誉", "段誉携着少女往大理城去了", [SEND("段誉", "大理城")])))
        self.assertEqual((g.get("段誉", "location"), g.get("钟灵", "location")), ("大理城", "大理城"))

    def test_a_companion_held_by_someone_absent_stays(self):
        g, w = self.g, self.w
        for p in ("段誉", "钟灵"):
            g.set(p, "location", "澜沧江边高崖")
        g.link("段誉", "钟灵", "随行")
        g.link("司空玄", "钟灵", "扣为人质")                                          # 司空玄在无量山，不在被带走之列
        judge(w, plan(("段誉", "段誉独自往大理城去了", [SEND("段誉", "大理城")])))
        self.assertEqual(g.get("钟灵", "location"), "澜沧江边高崖")                   # 不把人质与擒者拆开

    def test_canon_moves_alone_and_the_bond_is_cut_at_the_end(self):
        g, w = self.g, self.w
        g.link("段誉", "钟灵", "随行")
        w.turn = {}
        effects.apply(w, [{"op": "set", "id": "段誉", "key": "location", "value": "大理城"}], "canon")
        self.assertEqual(g.get("钟灵", "location"), "无量山")                         # 原著挪人不带人
        self.assertTrue(situation.sunder(w))
        self.assertEqual(situation.company(w, "段誉"), [])                             # 回合末两端异地：了断

    def test_a_companion_sent_away_does_not_teleport_back(self):
        g, w = self.g, self.w
        g.set("段誉", "location", "澜沧江边高崖")
        g.link("段誉", "player", "随行")
        r = judge(w, plan(("段誉", "段誉拱手作别，往大理城去了", [SEND("段誉", "大理城")]),
                          ("player", "你转身往无量山去", [GO("无量山")])))           # 同一回合先送走，后移动
        self.assertEqual(g.get("段誉", "location"), "大理城")
        self.assertNotIn("段誉", situation.party(w))
        self.assertTrue(any("段誉已不在你身边" in n for n in r.notes))
        self.setUp()
        g, w = self.g, self.w
        g.set("段誉", "location", "澜沧江边高崖")
        g.link("段誉", "player", "随行")
        judge(w, plan(("段誉", "段誉拱手作别，往大理城去了", [SEND("段誉", "大理城")])))
        judge(w, plan(("player", "你转身往无量山去", [GO("无量山")])))               # 下一回合主角移动：他不再瞬移回来
        self.assertEqual(g.get("段誉", "location"), "大理城")
        self.assertNotIn("段誉", situation.party(w))

    def test_a_companion_moved_by_canon_this_turn_is_not_carried(self):
        g, w = self.g, self.w
        g.set("钟灵", "location", "无量后山")
        g.link("段誉", "钟灵", "随行")
        w.turn = {"minutes": 15}
        effects.apply(w, [{"op": "set", "id": "钟灵", "key": "location", "value": "无量山"}], "canon")  # 原著这一回合已调遣过她
        self.assertEqual(w.turn["movers"]["钟灵"], "canon")
        adjudicate.judge(w, plan(("段誉", "段誉奔上崖来", [COME("段誉")])), set())
        self.assertEqual(g.get("段誉", "location"), "澜沧江边高崖")
        self.assertEqual(g.get("钟灵", "location"), "无量山")                         # 一回合一人只听一处调遣


class MetTest(unittest.TestCase):
    """v12 P1-3 近处的熟人另收三日内见过的人：钟灵在练武厅当着主角放貂救人，没报过名、没与主角交手，此后从没进过导演后台的【近处的熟人】。"""

    def test_a_face_seen_two_days_ago_is_an_acquaintance(self):
        from tianlong.world import rag
        w = World.create("测")
        day = w.clock.day
        w.player.set("met", {"钟灵": day - 2, "段誉": day - 2})
        for p in ("段誉", "钟灵"):
            w.graph.set(p, "location", "无量后山")                                     # 一日路程之内，不在眼前
        w.graph.link("段誉", "钟灵", "随行")
        lines = rag.acquainted(w)
        zhong = next(x for x in lines if x.startswith("钟灵："))
        self.assertIn("主角只识其貌：大眼圆脸的少女", zhong)                           # 未识名：只识其貌
        self.assertIn("与钟灵同行", next(x for x in lines if x.startswith("段誉：")))
        w.player.set("met", {"钟灵": day - 5})
        self.assertFalse(any(x.startswith("钟灵：") for x in rag.acquainted(w)))        # 见过是五日前的事：不算

    def test_the_engine_remembers_who_was_met(self):
        from tests.test_engine import StubLLM, director
        from tianlong.engine import Game
        w = World.create("测")
        Game(w, StubLLM(director())).act("看")
        self.assertEqual(w.player["met"].get("钟灵"), w.clock.day)                     # 本回合见过的人记下见到的日子
        old = w.dump()
        old["player"].pop("met")
        self.assertEqual(World.from_dump(old).player["met"], {})                        # 旧档没有 met 也读得进来

if __name__ == "__main__":
    unittest.main()
