"""
[INPUT]: 依赖 tianlong.world 的 World / lod / body / effects / rag / graph 与 data/canon 原著世界，tianlong.engine 的 Game（离线 llm=None 结算场外原著）
[OUTPUT]: unittest 用例——v5「连贯性」的离线验收，每一类对应 PR #2 review 里一条 P0：
          剧情前提与体征分开(原著宣告的负伤不被养伤抹掉、明写痊愈才消、读路径不写气血、原著主线离线连演不断)
[POS]: tests 的连贯性验证——36 回实录里「段誉不来」「剧情前后打架」的病灶在这里逐条成为用例；与 test_state(v4 状态层)、test_story(v4 故事层)互补
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import unittest

from tianlong.engine import Game
from tianlong.world import body, effects, graph, lod, rag
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
