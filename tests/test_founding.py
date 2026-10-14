"""
世界底座(v11)：19~27 编进世界，近大远小——远处的店只是一个地名，主角走近时近景才布齐。
"""
import json
import tempfile
import unittest
from pathlib import Path

from tianlong.world import access, effects, genesis, lore, perspective, rag, situation, venue
from tianlong.world.clock import PER_DAY, PER_SHICHEN
from tianlong.world.world import World

INN, STREET = "大理城·东街客栈", "大理城·东街"


def at(w, loc):
    w.player.set("location", loc)
    venue.settle(w)
    return w


def go(w, loc):
    return effects.apply(w, [{"op": "set", "id": "player", "key": "location", "value": loc}], "director")


def shichen(w, name):
    """把时钟拨到当天的某个时辰(往后拨，不倒退)。"""
    now = w.clock.tick % PER_DAY
    w.advance(("子丑寅卯辰巳午未申酉戌亥".index(name) * PER_SHICHEN - now) % PER_DAY)


class CompileTest(unittest.TestCase):
    """十个文件编进世界：处所卡补到地点上、场所立为地点、人物门派人群补注，静态的表进 atlas，零错误开局。"""

    @classmethod
    def setUpClass(cls):
        cls.w = World.create("测")

    def test_cards_and_new_places(self):
        g = self.w.graph
        self.assertEqual((g.get("大理城", "form"), g.get("大理城", "layer"), g.get("大理城", "polity")), ("都城", 1, "大理国"))
        self.assertTrue(g.get("燕子坞", "far"))                                     # 一层的处所有远景
        self.assertEqual(g.get(STREET, "parent"), "大理城")                           # 新处所：城里的坊市
        road = g.road("大理城", STREET)
        self.assertEqual((road["days"], road["li"]), (0, 1))                          # 零日之路另带里数
        self.assertNotIn(STREET, situation.near(at(World.create("测"), "大理城")))   # 隔了街巷：当日走得到，却不是近旁

    def test_venues_people_factions(self):
        g, a = self.w.graph, self.w.atlas
        self.assertEqual((g.get(INN, "venue"), g.get(INN, "form"), g.get(INN, "parent")), ("客栈", "场所", STREET))
        self.assertEqual(g.get("松鹤楼", "venue"), "酒楼")                             # 01 已登记的场所只补注
        self.assertIsNone(g.get(INN, "furnished"))                                    # 远处的店只是一个地名
        self.assertEqual(len(a["venues"]), 496)
        self.assertTrue(g.get("段延庆", "drive") >= 4 and g.get("段誉", "arc") and g.get("段誉", "money") > 0)  # 22 的推力、走向、零钱
        self.assertTrue(g.has("木婉清·长剑") and g.get("木婉清·长剑", "holder") == "木婉清")  # 随身之物
        self.assertTrue(g.get("丐帮", "goal") and g.get("丐帮", "squad_kits"))          # 23 的所图与门下模板
        self.assertEqual(g.get("神农攻山帮众", "type"), "group")                        # 23 的人群
        self.assertEqual((len(a["lore"]), len(a["lines"]), len(a["notes"]), len(a["precepts"])), (316, 50, 235, 25))

    def test_a_bad_section_refuses_to_open(self):
        root = Path(tempfile.mkdtemp())
        for f in genesis.DATA.iterdir():
            (root / f.name).write_bytes(f.read_bytes())
        data = json.loads((root / "20_venues.json").read_text("utf-8"))
        next(v for v in data["venues"] if v["id"] == INN)["type"] = "天外客栈"
        (root / "20_venues.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        with self.assertRaises(genesis.GenesisError) as e:
            genesis._compile(str(root))
        self.assertIn("模板「天外客栈」没有登记", str(e.exception))


class VenueTest(unittest.TestCase):
    """主角走近才布置：站在街上，街边的店门就在眼前(一步之遥即布好)；走进店里进的是前堂，伙计只有职名。"""

    def test_furnished_when_near(self):
        w = at(World.create("测"), STREET)
        g = w.graph
        self.assertIsNotNone(g.get(INN, "furnished"))
        self.assertTrue(g.has(f"{INN}·大堂") and g.has(f"{INN}·掌柜") and g.has(f"{INN}·柜银"))
        self.assertEqual(g.get(f"{INN}·掌柜", "location"), f"{INN}·大堂")
        self.assertIsNone(g.get("苏州·中市茶馆", "furnished"))                          # 千里之外的不布
        before = len(g.nodes)
        self.assertEqual(venue.settle(w), [])                                           # 幂等
        self.assertEqual(len(g.nodes), before)

    def test_walking_in_lands_in_the_front_room(self):
        w = at(World.create("测"), STREET)
        go(w, INN)
        self.assertEqual(w.here, f"{INN}·大堂")                                        # 柜台所在的那一间
        people = rag.scene(w)["people"]
        self.assertIn("掌柜", [perspective.handle(w, p) for p in people])               # 只有职名，人人这样叫
        names = {perspective.handle(w, p) for p in situation.around(w)}
        ops = perspective.distinguish(w)
        self.assertEqual(len({op["value"] for op in ops}), len(ops))                    # 两个店小二各分一个外号
        self.assertIn("店小二", names)

    def test_staff_keep_their_hours(self):
        w = at(World.create("测"), STREET)
        go(w, INN)
        boss = f"{INN}·掌柜"
        shichen(w, "辰")
        self.assertIn(boss, situation.around(w))
        shichen(w, "子")                                                                # 卯开子闭：子时回屋歇着了
        self.assertNotIn(boss, situation.around(w))
        self.assertFalse(venue.on_duty(w, boss))

    def test_a_locked_storeroom(self):
        w = at(World.create("测"), STREET)
        go(w, INN)
        store, key = f"{INN}·库房", f"{INN}·库门钥匙"
        self.assertNotIn(store, situation.near(w))                                      # 锁着的库房不是隔壁
        _, rejected = go(w, store)
        self.assertTrue(rejected and "门上了锁" in rejected[0][1] and "库门钥匙" in rejected[0][1])
        w.player.push("inventory", key)
        w.graph.nodes[key].update(holder="player", location=None)
        go(w, store)
        self.assertEqual(w.here, store)

    def test_city_walks_take_time_by_li(self):
        w = at(World.create("测"), "大理城")
        self.assertEqual(access.stroll(w, "大理城", STREET), venue.LI_MINUTES)          # 一里
        self.assertGreater(access.stroll(w, "大理城", INN), access.stroll(w, "大理城", STREET))
        self.assertEqual(access.stroll(w, "大理城", "无量山"), 0)                       # 远行按日数另算

    def test_wares_prices_and_restock(self):
        w = at(World.create("测"), "大理城·中街")
        shop = "大理城·中街茶馆"
        wares = venue.wares(w, shop)
        tea = wares["货·茶水"]
        self.assertAlmostEqual(tea["price"], round(w.atlas["goods"]["货·茶水"]["price"] * 0.6, 4))  # 大理国茶贱
        bun = wares["货·馒头"]
        bun["stock"] = 0
        venue.restock(w, 1)
        self.assertEqual(bun["stock"], bun["full"])

    def test_gate_hours(self):
        w = at(World.create("测"), "镇南王府·牌楼外院")
        shichen(w, "戌")
        _, rejected = go(w, "镇南王府")                                                # 卯开酉闭：入夜府门紧闭
        self.assertTrue(rejected and "关口已闭" in rejected[0][1])
        shichen(w, "辰")
        go(w, "镇南王府")
        self.assertEqual(w.here, "镇南王府")

    def test_save_and_load_keep_the_rooms(self):
        w = at(World.create("测"), STREET)
        go(w, INN)
        path = Path(tempfile.mkdtemp()) / "s.json"
        w.save(path)
        v = World.load(path)
        self.assertEqual(v.here, f"{INN}·大堂")
        self.assertTrue(v.graph.road(INN, f"{INN}·大堂"))                              # 读档重绘道路之后接回房间之路
        self.assertIn(f"{INN}·后厨", situation.near(v))
        self.assertIsNotNone(v.atlas.get("venues"))


class KnownTest(unittest.TestCase):
    """知者：外人不知的秘境不在开局常识里；消息随原著起落。"""

    def test_secret_places_are_not_common_knowledge(self):
        w = World.create("测")
        self.assertFalse(w.knowledge.knows("琅嬛福地"))                               # 只有李秋水、无崖子知道
        self.assertTrue(w.knowledge.knows("大理城"))
        self.assertTrue(lore.open_to(w, "李秋水", w.graph.get("琅嬛福地", "known")))
        self.assertTrue(lore.open_to(w, "player", w.graph.get("剑湖宫·练武厅", "known")))  # 身在剑湖宫：那一带的人知道

    def test_lore_windows(self):
        w = World.create("测")
        table = lore.entries(w)
        day = {ev["id"]: ev["day"] for ev in w.canon}
        later = next(e for e in table.values() if e.get("since") and day[e["since"]] > w.clock.day)
        self.assertFalse(lore.live(w, later))                                           # 那一桩还没到期：风声未起
        w.done.append(later["since"])
        self.assertTrue(lore.live(w, later))
        gone = next(e for e in table.values() if e.get("until"))
        w.done.append(gone["until"])
        self.assertFalse(lore.live(w, gone))                                            # 过时的风声不算数

    def test_what_a_shop_can_tell(self):
        w = at(World.create("测"), STREET)
        go(w, INN)
        shichen(w, "辰")
        found = lore.sources(w)
        self.assertTrue(found)
        self.assertTrue(all(f["by"] is None or venue.on_duty(w, f["by"]) for f in found))
        self.assertTrue(lore.learn(w, found[0]["id"]))
        self.assertNotIn(found[0]["id"], [f["id"] for f in lore.sources(w)])           # 听过的不再列


if __name__ == "__main__":
    unittest.main()
