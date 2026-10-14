"""
[INPUT]: 依赖 tianlong.world 的 genesis / effects / adjudicate / situation / scenery / rag / perspective 与 data/canon 原著世界(含 18_scenes.json 场景清单)，
         tianlong.engine 的 Game 与 _newsworthy；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——v8 场景清单「言出法随」：剑湖宫的建筑、景物、分级器物在创世时布齐(错一处拒绝开局)；拾起青钢剑即入随身、走开之后原处不再有它、
          放下便落在那里的地上；玩家原话里的简称(「青钢剑」「茶碗」)认得出是哪一件、不被当作越权剥掉，拍文写取下而账上没有即违例；
          器物一件也不新造(spawn 物件驳回，写的若就是现场之物便认回)；寻常之物端起放下不返工、易手不成江湖事件；
          导演看得见此处与近旁的全部陈设与器物、要物的内容与底细，编剧只看得见眼前的(要物到了手里才读得到内容)；旧档读入补上新布景
[POS]: tests 的布景验证——「基础设施掌管世界、LLM 只调度」在器物上的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_adjudicate import GO, judge, plan
from tests.test_engine import StubLLM, director
from tianlong.engine import Game, _newsworthy
from tianlong.narrative import prompts
from tianlong.world import adjudicate, effects, genesis, perspective, rag, scenery, settle, situation
from tianlong.world.world import World

HALL, GATE, INNER, COURT = "剑湖宫·练武厅", "剑湖宫·宫门", "剑湖宫·内堂", "剑湖宫"
SWORD, BOWL, SILVER, BOOK, NOTES = "剑架青钢剑", "宾客茶碗", "碎银", "剑会胜负簿", "玉壁剑影图"
TAKE = lambda item: {"op": "push", "id": "player", "key": "inventory", "value": item}
DROP = lambda item: {"op": "pull", "id": "player", "key": "inventory", "value": item}


def items_here(w) -> list[str]:
    return [i["name"] for i in rag.build(w)["items"]]


class GenesisTest(unittest.TestCase):
    """剑湖宫这一处场景在创世时就布齐了：建筑是地点、景物不可携带、器物分三等。"""

    def test_jianhu_palace_is_dressed(self):
        g = World.create().graph
        self.assertEqual({g.get(p, "parent") for p in (HALL, GATE, INNER)}, {COURT})
        self.assertIsNotNone(g.road(COURT, GATE))
        self.assertIsNotNone(g.road(GATE, "无量山"))
        self.assertIsNone(g.road(COURT, "无量山"))                                    # 出入剑湖宫须经宫门
        self.assertEqual(g.distances(HALL)["无量山"], 0)                              # 路程不变：同处 0 日
        self.assertEqual((g.kind("练武厅剑架"), g.get("练武厅剑架", "location")), ("feature", HALL))
        self.assertEqual((g.get(SWORD, "grade"), g.get(SWORD, "spot"), g.get(SWORD, "props")["材质"]), ("器物", "剑架上", "青钢"))
        self.assertEqual((g.get(BOWL, "grade"), g.get(BOWL, "desc")), ("寻常", None))  # 寻常之物只有名字
        self.assertIn("五场三胜", g.get(BOOK, "text"))                                 # 要物详写：文书另有内容
        self.assertTrue(g.get(NOTES, "hidden") and g.get(NOTES, "secret"))
        self.assertEqual((g.get("段誉折扇", "holder"), g.get("段誉折扇", "location")), ("段誉", None))

    def stage(self, items=(), features=(), places=()):
        """只布一处小场景：最小的 00_index 与一份 18_scenes，交 genesis._stage 校验。"""
        root = Path(tempfile.mkdtemp())
        (root / "00_index.json").write_text(json.dumps({"items": [{"id": "旧物", "aliases": ["古剑"]}]}), "utf-8")
        (root / genesis.SCENES).write_text(json.dumps({"scenes": [{"scene": "宫", "places": list(places), "features": list(features),
                                                                    "items": list(items)}]}, ensure_ascii=False), "utf-8")
        nodes = {"宫": {"type": "location", "parent": None, "region": "某地"}, "远处": {"type": "location", "parent": None},
                 "甲": {"type": "person", "location": "宫"}, "乙": {"type": "person", "location": "远处"}, "旧物": {"type": "item"}}
        return genesis._stage(root, nodes), nodes

    def test_a_bad_manifest_refuses_to_open(self):
        ok, nodes = self.stage(items=[{"id": "剑", "grade": "器物", "desc": "一柄剑", "location": "宫·厅"}],
                               places=[{"id": "宫·厅", "parent": "宫", "desc": "厅"}], features=[{"id": "梁", "location": "宫·厅", "desc": "梁"}])
        self.assertEqual(ok, [])
        self.assertEqual((nodes["宫·厅"]["region"], nodes["梁"]["type"], nodes["剑"]["state"]), ("某地", "feature", {"exists": True, "available": True}))
        bad = {
            "等级": {"id": "x", "grade": "神物", "desc": "d", "location": "宫"},
            "须有描述": {"id": "x", "grade": "器物", "location": "宫"},
            "只有要物": {"id": "x", "grade": "寻常", "text": "信上写着", "location": "宫"},
            "有且只有一处": {"id": "x", "grade": "寻常", "location": "宫", "holder": "甲"},
            "不在场景之内": {"id": "x", "grade": "寻常", "location": "远处"},
            "不是此刻身在场景里的人": {"id": "x", "grade": "寻常", "holder": "乙"},
            "相撞": {"id": "旧物", "grade": "寻常", "location": "宫"},
            "属性": {"id": "x", "grade": "器物", "desc": "d", "location": "宫", "props": {"重": 3}},
        }
        for why, row in bad.items():
            errors, _ = self.stage(items=[row])
            self.assertTrue(errors and why in errors[0], (why, errors))
        errors, _ = self.stage(items=[{"id": "古剑", "grade": "寻常", "location": "宫"}])  # 盖住了书中器物的别名
        self.assertIn("相撞", errors[0])
        errors, _ = self.stage(places=[{"id": "外·屋", "parent": "远处"}])
        self.assertIn("不在场景之内", errors[0])


class FlowTest(unittest.TestCase):
    """言出法随：拾起即入随身，走开之后原处便不再有它；放下便落在那里的地上。"""

    def setUp(self):
        self.w = World.create("测")

    def test_take_the_sword_and_the_hall_no_longer_has_it(self):
        w = self.w
        self.assertIn(SWORD, items_here(w))
        applied, rejected = w.apply([TAKE(SWORD)], "director")
        self.assertEqual((len(applied), rejected), (1, []))
        self.assertIn(SWORD, w.player["inventory"])
        self.assertEqual((w.graph.get(SWORD, "holder"), w.graph.get(SWORD, "location"), w.graph.get(SWORD, "spot")), ("player", None, None))
        self.assertNotIn(SWORD, items_here(w))
        self.assertIn(SWORD, [i["name"] for i in rag.build(w)["player"]["inventory"]])
        w.apply([GO(GATE)], "director")
        self.assertEqual((w.here, effects.place(w, SWORD)), (GATE, GATE))             # 剑随身走
        w.apply([DROP(SWORD)], "director")
        self.assertEqual((w.graph.get(SWORD, "location"), w.graph.get(SWORD, "spot")), (GATE, "地上"))
        self.assertIn("剑架青钢剑（地上）", [f"{c['name']}（{c['spot']}）" for c in rag.build(w)["items"]])
        w.apply([GO(HALL)], "director")
        self.assertNotIn(SWORD, items_here(w))                                        # 回到厅上，剑架上已经没有它
        self.assertEqual(w.player["inventory"], [])

    def test_hidden_notes_need_someone_in_the_room(self):
        w = self.w
        _, rejected = w.apply([TAKE(NOTES)], "director")
        self.assertTrue(rejected)                                                     # 暗藏在内堂抽屉里：人不到那里找不着
        w.apply([GO(INNER)], "director")
        self.assertEqual(w.apply([TAKE(NOTES)], "director")[1], [])
        self.assertFalse(w.graph.get(NOTES, "hidden"))

    def test_a_spot_is_soft(self):
        w = self.w
        op = {"op": "set", "id": SWORD, "key": "spot", "value": "掌门座旁"}
        self.assertEqual(w.apply([op], "director")[1], [])
        self.assertEqual(w.graph.get(SWORD, "spot"), "掌门座旁")
        self.assertFalse(adjudicate.physical(op))                                     # 挪个方位不是得失：落不了也不废整拍
        self.assertEqual(effects.describe(op), "剑架青钢剑放到了掌门座旁")
        self.assertTrue(w.apply([{"op": "set", "id": "段誉", "key": "spot", "value": "梁上"}], "director")[1])


class NicknameTest(unittest.TestCase):
    """玩家说「青钢剑」，系统认得是剑架上那一柄：不当作越权剥掉，拍文写取下而账上没有即违例。"""

    def setUp(self):
        self.w = World.create("测")

    def test_free_words_point_at_the_rack_sword(self):
        aim = adjudicate.targets(self.w, "我从剑架上取下那柄青钢剑")
        self.assertIn(SWORD, aim)
        self.assertEqual(scenery.nicknames(self.w)["青钢剑"], SWORD)                  # 地上的先于褚师弟手里的那柄
        self.assertNotIn("长剑", scenery.nicknames(self.w))                           # 两柄长剑都在别人手里：撞了便不认
        r = judge(self.w, plan(("player", "你从剑架上取下青钢剑，握在手中", [TAKE("青钢剑")])), aim)
        self.assertEqual((r.hard, r.candidates), ([], []))
        self.assertIn(SWORD, self.w.player["inventory"])

    def test_writing_a_take_without_the_op_goes_back(self):
        r = judge(self.w, plan(("player", "你从剑架上取下青钢剑", [])), {SWORD})
        self.assertEqual([(f.kind, f.entity) for f in r.hard], [("acquire", SWORD)])


class ForgeTest(unittest.TestCase):
    """器物一件也不新造：spawn 物件驳回；导演要的若就是现场之物，认回它。"""

    def setUp(self):
        self.w = World.create("测")

    def test_a_tinderbox_cannot_be_conjured(self):
        r = judge(self.w, plan(("player", "你掏出火折晃亮", [TAKE("火折")]), spawn=[{"kind": "thing", "name": "火折"}]))
        self.assertIn("spawn", [f.kind for f in r.hard])
        self.assertFalse(self.w.graph.has("火折"))
        self.assertTrue(any("火折" in v for v in r.void))

    def test_narration_cannot_conjure_either(self):
        """真模型第四回合：导演在旁白里写「向内堂取密图备御」——没有一条指令碰它，世上却凭空多了一张密图。"""
        r = judge(self.w, plan(("左子穆", "左子穆急召门人向内堂取密图备御", [])))
        self.assertEqual([(f.kind, f.entity) for f in r.hard], [("conjure", "密图")])
        r = judge(World.create("测"), plan(("干光豪", "干光豪取出火折交给龚光杰", [])))        # 后面提到了人，那件东西仍是凭空造的
        self.assertEqual([(f.kind, f.entity) for f in r.hard], [("conjure", "火折")])
        self.assertIn("此地与身边可及之物", "".join(adjudicate.brief(self.w, r)))       # 返工清单写明此地有什么
        for beat in ("左子穆拿起长剑", "马五德掏出一锭银子", "钟灵抓起一把瓜子", "左子穆取信于众人"):  # 世上有的、说的是眼前之物、不是器物
            self.assertEqual(judge(World.create("测"), plan(("左子穆", beat, []))).hard, [], beat)
        self.assertIn("正文写到「防守密图」，世上并无此物", settle.ruled(self.w, "左子穆命门人往内堂去取防守密图。"))

    def test_a_named_thing_already_here_is_recognised(self):
        r = judge(self.w, plan(("player", "你俯身拾起椅下的碎银子", [TAKE("碎银子")]), spawn=[{"kind": "thing", "name": "碎银子"}]), {SILVER})
        self.assertEqual(r.hard, [])
        self.assertIn(SILVER, self.w.player["inventory"])
        self.assertFalse(self.w.graph.has("碎银子"))


class TrifleTest(unittest.TestCase):
    """寻常之物：端起茶碗喝一口不必记账；茶碗易手不成江湖事件，青钢剑易手才是。"""

    def setUp(self):
        self.w = World.create("测")

    def test_sipping_tea_is_not_bookkeeping(self):
        r = judge(self.w, plan(("player", "你端起茶碗啜了一口", [])), {BOWL})
        self.assertEqual(r.hard, [])
        self.assertIn(("acquire", BOWL), [(f.kind, f.entity) for f in r.soft])

    def test_a_trifle_changing_hands_is_no_news(self):
        trifles = scenery.trifles(self.w)
        self.assertIn(BOWL, trifles)
        give = lambda item: [{"op": "set", "id": item, "key": "holder", "value": "段誉"}]
        self.assertEqual(_newsworthy(give(BOWL), 10, 0, trifles), 0)
        self.assertEqual(_newsworthy(give(SWORD), 10, 0, trifles), 1)


class ContextTest(unittest.TestCase):
    """导演看得见此处与近旁的全部陈设与器物、要物的内容与底细；编剧只看得见眼前的，要物到了手里才读得到内容。"""

    def test_the_director_and_the_writer_see_the_manifest(self):
        llm = StubLLM(director())
        game = Game(World.create("测"), llm)
        game.open()
        brief, page = llm.director_prompts[-1], llm.writer_prompts[-1]
        self.assertIn("【此处器物", brief)
        self.assertIn("- 剑架青钢剑（剑架上）｜兵刃｜", brief)
        self.assertIn("- 宾客茶碗（宾客椅旁的茶几上）\n", brief)                         # 寻常之物只有名字与方位
        self.assertIn("- 练武厅剑架：靠壁立着的木制剑架。", brief)
        self.assertIn("剑湖宫·内堂｜景物：内堂书案｜暗藏：玉壁剑影图", brief)          # 近旁各处(后台)
        self.assertIn("剑会胜负簿：内容「无量剑东西二宗比剑", brief)                     # 要物底细(后台)
        self.assertIn("随身：折扇", page)                                              # 编剧那份过视角掩码：生人的名号不带在器物上
        self.assertIn("- 剑会胜负簿（掌门座旁的茶几上）｜文书｜", page)
        self.assertNotIn("胜负未记", page)                                             # 摆在几上的簿子不等于读过
        self.assertNotIn(NOTES, page)
        self.assertIn("器物一件也不得新造", prompts.PLOT_GUIDE)                       # 导演的纲领：清单之外没有器物
        self.assertNotIn('"kind":"thing"', prompts.PLOT_GUIDE)

    def test_what_you_picked_up_moves_from_the_room_to_your_hands(self):
        take = [{"who": "player", "text": "你走到剑架前，取下胜负簿翻看", "ops": [TAKE(BOOK)]}]
        llm = StubLLM(director(beats=take))
        game = Game(World.create("测"), llm)
        game.act("取下胜负簿翻看")
        self.assertIn(BOOK, game.world.player["inventory"])
        game.act("四下看看")
        brief = llm.director_prompts[-1]
        here = brief.split("【此处器物", 1)[1].split("\n【", 1)[0]
        self.assertNotIn(BOOK, here)
        self.assertIn("- 剑会胜负簿｜文书｜", brief.split("【随身之物】", 1)[1])
        self.assertIn("内容：无量剑东西二宗比剑", llm.writer_prompts[-1])               # 到了手里，编剧才读得到内容


class LiveTest(unittest.TestCase):
    """真模型短程实测(第一回合)抓到的三处：导演把方位当作主角站的地方、写「去掉方位」；正文写「那柄青钢剑」被当作没写到而补记；
    「目光全被胜负吸了过去」被词表当作吸功、记成分歧。"""

    def setUp(self):
        self.w = World.create("测")

    def test_spot_ops_are_forgiving(self):
        applied, rejected = self.w.apply([{"op": "set", "id": "player", "key": "spot", "value": "练武厅剑架旁"},
                                          {"op": "pull", "id": SWORD, "key": "spot"}, TAKE(SWORD)], "director")
        self.assertEqual((rejected, [op.get("key") for op in applied]), ([], ["inventory"]))  # 软的方位不写也不算错，只有拾起入账

    def test_the_short_name_counts_as_written(self):
        w = self.w
        w.turn = {}
        glance0 = settle.glance(w)
        w.apply([TAKE(SWORD)], "director")
        change = settle.delta(w, glance0)
        self.assertIn("青钢剑", next(c for c in change if c["key"] == f"got:{SWORD}")["marks"])
        self.assertEqual(settle.unwritten(change, "你顺势将剑架上的那柄青钢剑抄在手中。", missed=set()), [])  # 写到了，不补记

    def test_being_drawn_by_the_duel_is_not_drain(self):
        r = judge(self.w, plan(("左子穆", "满厅目光全被这一场胜负吸了过去，左子穆倒吸了一口凉气", [])))
        self.assertNotIn("drain", [f.kind for f in r.hard + r.soft])
        self.assertEqual(settle.ruled(self.w, "满厅宾客的目光全被这一场胜负吸了过去。"), [])


class SaveTest(unittest.TestCase):
    """旧档读入：新布下的景物与器物补上，已有的照存档；重绘多少次都是同一个样子。"""

    def test_an_old_save_gets_the_new_dressing(self):
        w = World.create("测")
        w.apply([TAKE(SWORD)], "director")
        dump = json.loads(json.dumps(w.dump(), ensure_ascii=False))
        for nid in ("练武厅屋梁", BOWL, NOTES):
            del dump["graph"]["nodes"][nid]
        dump["graph"]["nodes"]["掌门座"]["state"] = "左首一张被劈成两半"
        old = World.from_dump(dump)
        self.assertEqual({old.graph.kind(n) for n in ("练武厅屋梁", BOWL, NOTES)}, {"feature", "item"})
        self.assertEqual(old.graph.get("掌门座", "state"), "左首一张被劈成两半")          # 景物的现状照存档
        self.assertEqual((old.graph.get(SWORD, "holder"), old.player["inventory"]), ("player", [SWORD]))  # 已在手里的不被摆回剑架
        twice = World.from_dump(json.loads(json.dumps(old.dump(), ensure_ascii=False)))
        self.assertEqual(twice.graph.nodes, old.graph.nodes)


if __name__ == "__main__":
    unittest.main()
