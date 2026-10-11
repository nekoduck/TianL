"""
[INPUT]: 依赖 tianlong.world 全部基础设施与 data/canon 原著硬知识（不接入 LLM）
[OUTPUT]: unittest 用例——创世导入(含章节成簇日程、别名表、道路补丁严丝合缝、关口须落在道路上)、历法、剧情后果落账、地理器物武学归基础设施、器物易手、
          世界物理、场外在场性、通行(此路不通拦所有人、暗路须经剧情发现且回头路认得、硬前提由系统判、远行止步门前)、
          消息延迟、隐情与隐秘字段(含揭示门控)、LOD 按距离分层、到期原著远近分流与依序结算、裁定、存读档
[POS]: tests 的状态层验证，以真实原著世界为对象，证明剧情能自由改变既有世界，而人、地、物、武学只由系统掌管
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from tianlong.world import genesis, lod, rag
from tianlong.world.clock import PER_DAY, Clock, day_of
from tianlong.world.world import World

GO = lambda dest: {"op": "set", "id": "player", "key": "location", "value": dest}
START = "剑湖宫·练武厅"
EXITS = lambda w: [e["name"] for e in rag.build(w)["exits"]]


@contextmanager
def tampered(name: str, mutate):
    """拷贝一份原著数据，用 mutate 改动其中一个文件，交出该目录——验证坏数据在开局前就被拦下。"""
    with tempfile.TemporaryDirectory() as d:
        for f in genesis.DATA.glob("*.json"):
            (Path(d) / f.name).write_bytes(f.read_bytes())
        data = json.loads((Path(d) / name).read_text("utf-8"))
        mutate(data)
        (Path(d) / name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        yield Path(d)


class GenesisTest(unittest.TestCase):
    def test_canon_world_opens_in_chapter_one(self):
        w = World.create("测试")
        self.assertEqual((w.here, w.clock.label()), (START, "元祐六年二月初一 辰时"))
        self.assertIn("段誉", rag.scene(w)["people"])
        self.assertEqual(w.canon[0]["id"], "无量剑第四场比剑")
        self.assertEqual([e["order"] for e in w.canon], sorted(e["order"] for e in w.canon))
        self.assertTrue(all(a["day"] <= b["day"] for a, b in zip(w.canon, w.canon[1:])))  # 日序随 order 单调

    def test_a_chapter_scene_happens_on_one_day(self):
        w = World.create()
        hall = [e for e in w.canon if e["where"] == START and e["order"] <= 4]  # 第一回练武厅里的四件事
        self.assertEqual(len({e["day"] for e in hall}), 1)                       # 同一天，而非撒在三天里
        self.assertEqual(w.aliases["萧峰"], "乔峰")
        self.assertEqual(w.aliases["剑湖宫练武厅"], START)

    def test_roads_are_ridden_not_walked(self):
        raw = {frozenset((a, b)): d for a, b, d in genesis._roads(genesis.DATA)}  # 打过补丁的步行日数
        w = World.create()
        for e in w.graph.edges:
            if e["rel"] == "road":
                walk = raw[frozenset((e["src"], e["dst"]))]
                self.assertEqual(e["days"], genesis._ride(walk))
                self.assertTrue(e["days"] <= walk and (walk == 0) == (e["days"] == 0))

    def test_unconfirmed_persons_are_dormant(self):
        w = World.create()
        self.assertTrue(w.graph.get("黎老汉", "dormant"))
        self.assertTrue(w.graph.get("黎老汉", "hidden"))

    def test_broken_reference_fails_before_the_world_opens(self):
        with tampered("04_persons.json", lambda rows: rows[0].update(location="蓬莱仙岛")) as d:
            with self.assertRaises(genesis.GenesisError):
                genesis.load(d)

    def test_roads_patch_must_fit_the_roads_it_patches(self):
        bad = {"remove": ["无量后山", "大理城"],            # 要删的路并不存在
               "add": ["无量山·山崖", "无量山·谷底", 0],     # 补丁已加过：每个补丁只应用一次
               "change": ["无量后山", "大理城", 1]}         # 要改的路并不存在
        for key, row in bad.items():
            with self.subTest(key), tampered("15_roads_patch.json", lambda p: p[key].append(row)) as d:
                with self.assertRaises(genesis.GenesisError):
                    genesis.load(d)
        stray = {"from": "无量后山", "to": "大理城", "kind": "守卫", "blocked": False, "hidden": False, "how": "", "requires": []}
        with tampered("14_access.json", lambda rows: rows.append(stray)) as d:  # 关口必须落在一条道路上
            with self.assertRaises(genesis.GenesisError):
                genesis.load(d)

    def test_false_shortcuts_are_gone(self):
        w = World.create()
        self.assertIsNone(w.graph.road("无量后山", "无量山·谷底"))        # 后山平路下不到谷底，须坠崖
        self.assertIsNone(w.graph.road("琅嬛福地", "琅嬛福地·玉像石室"))   # 不依 parent 自动连路
        self.assertEqual(sum(len(e.get("gates", {})) for e in w.graph.edges), 179)


class ClockTest(unittest.TestCase):
    def test_calendar(self):
        self.assertEqual(Clock().label(), "元祐元年正月初一 子时")
        self.assertEqual(Clock().label(day_of("绍圣元年三月")), "绍圣元年三月初一")
        self.assertEqual(day_of("元符二年三月（多年后，占位推断）"), day_of("元符二年三月"))
        self.assertEqual(Clock(0).advance(PER_DAY * 30), (30, 1))
        self.assertEqual(Clock(4 * 120 + 45).label(), "元祐元年正月初一 辰时三刻")  # 分钟刻度：辰时过三刻


class PlotTest(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测试")

    def test_plot_consequences_become_truth(self):
        ops = [{"op": "set", "id": "段誉", "key": "status", "value": "wounded"},
               {"op": "set", "id": "左子穆", "key": "mood", "value": "恼羞成怒"},
               {"op": "link", "src": "左子穆", "dst": "player", "rel": "记恨"},
               {"op": "add", "id": "player", "key": "hp", "value": -20},
               {"op": "set", "id": START, "key": "state", "value": "比剑被搅散，满厅狼藉"}]
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual((len(applied), rejected), (5, []))
        pack = rag.build(self.w)
        self.assertEqual(pack["scene"]["state"], "比剑被搅散，满厅狼藉")
        self.assertIn("左子穆→你：记恨", next(p for p in pack["people"] if p["name"] == "左子穆")["toward_you"])
        self.assertEqual(self.w.player["hp"], 80)
        self.assertIn("段誉", self.w.taint)

    def test_people_places_things_and_arts_belong_to_infrastructure(self):
        ops = [{"op": "create", "id": "青衫剑客", "type": "person", "attrs": {}},
               GO("后山禁地"),                                                              # 世上没有此地
               {"op": "push", "id": "player", "key": "inventory", "value": "倚天剑"},       # 世上没有此物
               {"op": "push", "id": "player", "key": "inventory", "value": "北冥神功卷轴"},  # 远在琅嬛福地
               {"op": "push", "id": "player", "key": "skills", "value": "九阳神功"},        # 世上没有此功
               {"op": "set", "id": "北冥神功卷轴", "key": "grants", "value": {}},            # 器物定义不可改
               {"op": "set", "id": "北冥神功", "key": "desc", "value": "天下第一"},          # 武学定义不可改
               {"op": "set", "id": START, "key": "desc", "value": "一片废墟"}]              # 地理定义不可改
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual((applied, len(rejected)), ([], 8))

    def test_items_change_hands_only_within_reach(self):
        sword = "褚师弟青钢剑"
        applied, _ = self.w.apply([{"op": "push", "id": "player", "key": "inventory", "value": sword}], "director")
        self.assertEqual((len(applied), self.w.graph.get(sword, "holder")), (1, "player"))
        self.w.apply([{"op": "set", "id": sword, "key": "holder", "value": "段誉"}], "director")  # 赠与在场之人
        self.assertNotIn(sword, self.w.player["inventory"])
        _, rejected = self.w.apply([{"op": "set", "id": sword, "key": "holder", "value": "乔峰"}], "director")
        self.assertEqual(len(rejected), 1)  # 乔峰不在此地

    def test_loose_writing_is_understood(self):
        ops = [{"op": "set", "id": "测试", "key": "姿态", "value": "跌坐"}, GO("巴天石"),  # 名号当 id；中文属性名；走向某人
               {"op": "link", "src": "段誉", "dst": "主角", "rel": "结交", "note": "同去王府"}]
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual((len(applied), rejected), (3, []))
        self.assertEqual((self.w.player["posture"], self.w.here), ("跌坐", "大理城"))
        self.assertEqual(self.w.graph._find("段誉", "player", "结交")["note"], "同去王府")
        self.w.apply([{"op": "link", "src": "段誉", "dst": "player", "rel": "结义"}], "director")
        self.assertEqual([e["rel"] for e in self.w.graph.edges if e["src"] == "段誉" and e["dst"] == "player"], ["结义"])  # 写新覆盖旧

    def test_hidden_item_found_through_plot(self):
        self.w.player.set("location", "琅嬛福地·玉像石室")
        items = lambda: [i["name"] for i in rag.build(self.w)["items"]]
        self.assertNotIn("北冥神功卷轴", items())
        self.assertTrue(any("北冥神功卷轴" in h for h in rag.backstage(self.w)["hidden"]))
        self.w.apply([{"op": "set", "id": "北冥神功卷轴", "key": "hidden", "value": False}], "director")
        self.assertIn("北冥神功卷轴", items())

    def test_dormant_and_dead_are_beyond_plot(self):
        self.w.graph.set("左子穆", "status", "dead")
        self.w.graph.set("黎老汉", "location", START)
        ops = [{"op": "set", "id": "左子穆", "key": "status", "value": "alive"},  # 死者复生
               {"op": "set", "id": "乔峰", "key": "status", "value": "dead"},     # 远在中原
               {"op": "set", "id": "黎老汉", "key": "mood", "value": "惊"},        # 休眠之人
               {"op": "set", "id": "段誉", "key": "status", "value": "wounded"}]
        applied, rejected = self.w.apply(ops, "director")
        self.assertEqual(([op["id"] for op in applied], len(rejected)), (["段誉"], 3))

    def test_offscreen_cannot_touch_player_but_can_hate_him(self):
        ops = [{"op": "add", "id": "player", "key": "hp", "value": -50},
               {"op": "link", "src": "段正淳", "dst": "player", "rel": "起了疑心"},
               {"op": "set", "id": "段正淳", "key": "status", "value": "wounded"},
               {"op": "set", "id": "段正淳", "key": "location", "value": "聚贤庄"},  # 一日千里
               {"op": "set", "id": "段正淳", "key": "location", "value": "大理城"}]
        applied, rejected = self.w.apply(ops, "lod1", {"镇南王府"})
        self.assertEqual((len(applied), len(rejected)), (3, 2))
        self.assertEqual(self.w.player["hp"], 100)

    def test_garbage_rejected(self):
        _, rejected = self.w.apply([{"op": "rm"}, "x", {"op": "set", "id": "无此人", "key": "a", "value": 1},
                                    {"op": "set", "id": ["段誉"], "key": "mood", "value": 1},
                                    {"op": "set", "id": "player", "key": "location", "value": {"a": 1}}], "director")
        self.assertEqual(len(rejected), 5)


class AccessTest(unittest.TestCase):
    """道路是地理，通行是物理与认知：不通之路拦所有人，暗路只拦尚未发现它的主角，过法与风险交导演。"""

    def setUp(self):
        self.w = World.create()

    def test_a_blocked_direction_stops_everyone(self):
        w = self.w
        w.player.set("location", "雁门关·谷底")
        _, rejected = w.apply([GO("雁门关·石壁")], "director")
        self.assertEqual((w.here, EXITS(w)), ("雁门关·谷底", []))                   # 常人不能逆攀，谷底别无出路
        self.assertTrue(rejected[0][1].startswith("此路不通（悬崖）：常人不能逆攀"))
        self.assertIn("此路不通，主角过不去", "".join(rag.backstage(w)["passes"]))   # 导演知道为何
        w.graph.set("乔峰", "location", "雁门关·谷底")
        climb = {"op": "set", "id": "乔峰", "key": "location", "value": "雁门关·石壁"}
        self.assertEqual(len(w.apply([climb], "lod1", {"雁门关·谷底"})[1]), 1)      # 场外之人也攀不上去

    def test_a_secret_way_opens_only_through_plot(self):
        w = self.w
        w.player.set("location", "无量山·谷底")
        self.assertNotIn("琅嬛福地", EXITS(w))                                     # 暗路不在出路里
        self.assertIn("无量山·谷底→琅嬛福地（机关）", "".join(rag.backstage(w)["secret_ways"]))  # 导演知道
        _, rejected = w.apply([GO("琅嬛福地")], "director")
        self.assertEqual((w.here, rejected[0][1]), ("无量山·谷底", "找不到去路"))     # 缘由不点破暗路
        found = {"op": "reveal", "src": "无量山·谷底", "dst": "琅嬛福地", "rel": "机关"}
        applied, rejected = w.apply([GO("琅嬛福地"), found], "director")             # 同一批里先发现、后穿过
        self.assertEqual((len(applied), rejected, w.here), (2, [], "琅嬛福地"))
        self.assertIn("无量山·谷底", EXITS(w))                                      # 进来的暗门，回头也认得

    def test_the_way_out_is_the_way_back(self):
        w = self.w
        w.player.set("location", "琅嬛福地·石级隧道")
        w.apply([GO("澜沧江")], "director")                                         # 从洞里爬出江岸
        self.assertEqual(w.here, "澜沧江")
        self.assertIn("琅嬛福地·石级隧道", EXITS(w))                                 # 江面上的洞口在哪，出来的人心里有数

    def test_hard_requirements_are_judged_by_the_system(self):
        w = self.w
        w.player.set("location", "万劫谷·石屋")
        w.apply([{"op": "reveal", "src": "万劫谷·石屋", "dst": "万劫谷·地道", "rel": "通路"}, GO("万劫谷·地道")], "director")
        self.assertEqual(w.here, "万劫谷·石屋")                                      # 知道了，地道却还没掘通
        dug = {"op": "set", "id": "万劫谷·地道", "key": "state", "value": {"exists": True, "accessible": True}}
        w.apply([dug], "canon")                                                     # 巴天石、华赫艮掘通地道
        w.apply([GO("万劫谷·地道")], "director")
        self.assertEqual(w.here, "万劫谷·地道")
        cliff = w.graph.road("无量后山", "无量山·山崖")["gates"]["无量山·山崖"]
        cliff["requires"] = [["player", "skills", "凌波微步"]]
        w.player.set("location", "无量后山")
        _, rejected = w.apply([GO("无量山·山崖")], "director")
        self.assertEqual(rejected[0][1], "条件未备：主角须有凌波微步")

    def test_a_journey_halts_before_the_gate_at_its_door(self):
        w = self.w
        _, rejected = w.apply([GO("万劫谷")], "director")
        self.assertEqual(w.here, "万劫谷·谷外树林")                                  # 途中渡江的险径一笔带过，谷前的路止步门前
        self.assertTrue(rejected[0][1].startswith("行至万劫谷·谷外树林便止步，往万劫谷是一道关（潜入）"))
        self.assertIn("往万劫谷（潜入）", "".join(rag.backstage(w)["passes"]))       # 下一回合导演看见这道关
        w.apply([GO("万劫谷")], "director")                                         # 门前之关成了第一步：由导演兑现
        self.assertEqual(w.here, "万劫谷")

    def test_only_a_hidden_way_can_be_revealed(self):
        _, rejected = self.w.apply([{"op": "reveal", "src": "无量后山", "dst": "无量山", "rel": "通路"},
                                    {"op": "reveal", "src": "无量后山", "dst": "大理城", "rel": "通路"}], "director")
        self.assertEqual([why for _, why in rejected], ["两地之间并无暗路", "要揭露的隐情并不存在"])
        _, rejected = self.w.apply([{"op": "unlink", "src": "无量后山", "dst": "无量山", "rel": "road"}], "director")
        self.assertEqual(rejected[0][1], "道路属于地理，由系统掌管")                       # 剧情拆不掉道路


class KnowledgeTest(unittest.TestCase):
    def test_news_delay_follows_road_distance(self):
        w = World.create()
        dist = w.graph.distances(w.here)["聚贤庄"]
        op = {"op": "set", "id": "游骥", "key": "status", "value": "dead"}
        w.apply([op], "canon")
        w.record("游骥身亡", "聚贤庄", [op], "canon", 1)
        self.assertEqual(w.knowledge.view("游骥")["status"], "alive")  # 真相已变，认知未变
        w.advance(PER_DAY * (dist - 1))
        self.assertNotIn("游骥身亡", [e["summary"] for e in w.sync()])
        w.advance(PER_DAY)
        self.assertIn("游骥身亡", [e["summary"] for e in w.sync()])
        self.assertEqual(w.knowledge.view("游骥")["status"], "dead")

    def test_observation_overrides_belief(self):
        w = World.create()
        w.apply([{"op": "set", "id": "段正淳", "key": "location", "value": "大理城"}], "canon")
        w.player.set("location", "镇南王府")
        w.sync()
        self.assertIsNone(w.knowledge.view("段正淳")["location"])  # 亲眼所见：段正淳不在府中

    def test_secret_fields_stay_out_of_common_knowledge(self):
        w = World.create()
        for nid, node in w.graph.nodes.items():
            for key in node.get("secret_fields") or []:
                self.assertNotIn(key, w.knowledge.view(nid))
        self.assertFalse(w.knowledge.knows("慕容博"))  # 诈死潜伏者不在常识之中

    def test_secrets_reach_the_director_only_when_their_time_is_near(self):
        w = World.create()
        self.assertNotIn("段延庆—生父", str(rag.build(w)))
        self.assertNotIn("段延庆—生父—段誉", rag.backstage(w)["secrets"])   # 第四十八回的真相，第一回不摆上桌
        w.done.append("刀白凤揭示段誉生父")                                  # 揭示之事已在江湖上发生
        self.assertIn("段延庆—生父—段誉", rag.backstage(w)["secrets"])
        w.apply([{"op": "reveal", "src": "段延庆", "dst": "段誉", "rel": "生父"}], "director")
        self.assertNotIn("段延庆—生父—段誉", rag.backstage(w)["secrets"])   # 主角已知，无需再提

    def test_scoped_reveal_reaches_only_witnesses(self):
        w = World.create()
        reveal = {"op": "reveal", "src": "段延庆", "dst": "段誉", "rel": "生父"}
        w.knowledge.learn({"id": 900, "effects": [reveal], "public": False, "witnessed": False})
        self.assertEqual(w.knowledge.secrets, [])
        w.knowledge.learn({"id": 901, "effects": [reveal], "public": False, "witnessed": True})
        self.assertEqual(w.knowledge.secrets, [["段延庆", "段誉", "生父"]])


class LodTest(unittest.TestCase):
    def test_tiers_follow_road_distance_not_hops(self):
        w = World.create()
        t = lod.tiers(w)
        self.assertEqual((t[START], t["无量山"], t["琅嬛福地·玉像石室"], t["万劫谷"], t["聚贤庄"]), (0, 1, 1, 1, 2))  # 零日路一簇皆为近处

    def test_due_canon_splits_into_offstage_and_the_one_on_stage(self):
        w = World.create()
        offstage, staged = lod.split_due(w)
        self.assertEqual((offstage, staged["id"]), ([], "无量剑第四场比剑"))  # 开局：此地一桩，交导演
        self.assertEqual(lod.verdict(w, staged, 0), ("canon", []))
        self.assertEqual([ev["id"] for ev, _ in lod.upcoming(w, {staged["id"]})][:1], ["龚光杰掌掴段誉"])  # 近事可伏笔

    def test_offstage_events_settle_in_order_never_skipping_ahead(self):
        w = World.create()
        quiet = next(l for l in w.graph.where(type="location") if all(e["where"] != l for e in w.canon))
        w.player.set("location", quiet)
        w.advance(PER_DAY * 40)
        offstage, staged = lod.split_due(w)
        orders = [ev["order"] for ev, _ in offstage]
        self.assertEqual((orders, staged), (list(range(1, len(orders) + 1)), None))

    def test_verdicts(self):
        w = World.create()
        minor = next(e for e in w.canon if e["id"] == "龚光杰掌掴段誉")
        major = next(e for e in w.canon if e["id"] == "乔峰携阿朱赴聚贤庄")
        w.graph.set("阿朱", "status", "wounded")  # 让大事的前提成立，只剩"被扰动"
        w.taint.update({"段誉", "乔峰"})
        self.assertEqual(lod.verdict(w, minor, 0)[0], "canon")       # 小事被扰动但前提仍在：照常
        self.assertEqual(lod.verdict(w, major, 2)[0], "chronicle")   # 大事被扰动：史官改写
        w.graph.set("龚光杰", "status", "dead")
        self.assertEqual(lod.verdict(w, minor, 2)[0], "skip")        # 远方小事破局：悄然作罢
        self.assertEqual(lod.verdict(w, minor, 1)[0], "chronicle")   # 近处破局：史官改写

    def test_requires_on_lists(self):
        w = World.create()
        ev = next(e for e in w.canon if ["段誉", "skills", "凌波微步"] in e["requires"])
        self.assertTrue(lod.broken(w, ev))
        w.graph.nodes["段誉"]["skills"].append("凌波微步")
        self.assertFalse(any(r == ("段誉", "skills", "凌波微步") for r in lod._unmet(w, ev)))


class PersistenceTest(unittest.TestCase):
    def test_roundtrip(self):
        w = World.create("存档")
        w.apply([GO("大理城"), {"op": "reveal", "src": "段延庆", "dst": "段誉", "rel": "生父"},
                 {"op": "reveal", "src": "无量山·谷底", "dst": "琅嬛福地", "rel": "通路"}], "director")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            w.save(path)
            v = World.load(path)
        self.assertEqual(v.dump(), w.dump())


if __name__ == "__main__":
    unittest.main()
