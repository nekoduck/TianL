"""
[INPUT]: 依赖 tianlong.world 的 crowd / situation / effects / stock / settle / rag / genesis 与 data/canon 原著世界，tests.test_adjudicate 的 judge / plan；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——v10 人群随剧情走：
          重组(spawn 一队人马即从眼前或一日之内的同门人群里分出几人，身上的零钱器物按人头带走；整群调来即那一群；分不出、门派不对、不是人群即驳回；
          附近没有同门人群才按门下模板补一队无名之众，有名有姓的人不得立；分出的一队离远即并回原群，人头与身上之物守恒；补来的一队同受群战规则)；
          远行(导演让一群人前往远处、赶来按路程、结下随行即随主角走、换了地方即不再围着谁、原著挪走带队之人同处的人群随他走、出没时段 since/until、片区里要带到跟前)；
          醒转(打晕的人过两个时辰醒转归队，落在原地的东西还在就捡回去，被人拿走的捡不回)；
          NPC 银两(段誉给马五德三两即段誉少三两马五德多三两、不够即给不出、正文写了易手而两人的银两没动即漏记、账房开的单子入账)；
          创世(门下模板 kits、人物零钱 money、原著器物补注 canon_items、不识字 illiterate、人群的 leader/since/until 校验，错一处拒绝开局)；
          真模型实测抓到的(一记耳光也是伤)；v12 B2 原著近事要用的人群事前叫不来、分不出人，后台单列(ReservedTest)；P1-2 首领所图眼下(LeaderTest)
[POS]: tests 的 v10 验证——「弟子群是纯 NPC 资源：人头、零钱、兵刃衣衫都有账，随剧情驱动底层」的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.test_adjudicate import judge, plan
from tianlong.world import crowd, effects, genesis, rag, scribe, settle, situation, stock
from tianlong.world.world import World

EAST, WEST = "东宗弟子众", "西宗弟子众"
HALL = "剑湖宫·练武厅"
ESCORT = "随你去的东宗弟子"


def do(w, *ops, origin="director"):
    w.turn = w.turn or {}
    ok, bad = effects.apply(w, list(ops), origin)
    return ok, [why for _, why in bad]


def heads(w, *flocks) -> int:
    return sum(crowd.standing(w.graph, s) + int(w.graph.get(s, "down") or 0) for s in flocks if w.graph.has(s))


class RegroupTest(unittest.TestCase):
    """临时立的人马是既有人群的重组：分出几人，带着他们身上的零钱器物；附近没有同门人群才补一队纯 NPC。"""

    def setUp(self):
        self.w = World.create("测")
        self.g = self.w.graph

    def carve(self, **spec):
        return judge(self.w, plan(("左子穆", "左子穆点了五名弟子随你同去", []),
                                  spawn=[{"kind": "group", "name": ESCORT, "faction": "无量剑东宗", "count": 5, **spec}]), set())

    def test_five_disciples_split_off_with_their_kit(self):
        r = self.carve()
        g = self.g
        self.assertEqual((r.spawned, r.hard), ([ESCORT], []))
        self.assertEqual((crowd.standing(g, EAST), crowd.standing(g, ESCORT)), (10, 5))
        self.assertEqual(g.get(ESCORT, "pool"), {"银两": 1.5, "长剑": 5, "衣衫": 5})        # 五人的零钱、剑、衣衫一并带走
        self.assertEqual(g.get(EAST, "pool"), {"银两": 3.0, "长剑": 10, "衣衫": 10})
        self.assertIn(ESCORT, crowd.squads(self.w))
        self.assertIn(ESCORT, [q["name"] for q in rag.build(self.w)["squads"]])

    def test_the_split_rejoins_when_left_behind(self):
        w, g = self.w, self.g
        self.carve()
        do(w, {"做": "结下", "谁": ESCORT, "对": "player", "为": "随行"})
        w.turn = {"minutes": 24 * 60}
        do(w, {"做": "前往", "到": "无量山"})
        self.assertEqual(g.get(ESCORT, "location"), "无量山")                            # 随主角走
        self.assertEqual(situation.sweep(w), [])                                        # 随行的不收
        do(w, {"做": "了断", "谁": ESCORT, "对": "player", "为": "随行"})
        w.player.set("location", "大理城")
        self.assertEqual(situation.sweep(w), [ESCORT])
        self.assertFalse(g.has(ESCORT))
        self.assertEqual((crowd.standing(g, EAST), g.get(EAST, "pool")), (15, {"银两": 4.5, "长剑": 15, "衣衫": 15}))  # 人头与身上之物守恒

    def test_what_cannot_be_split(self):
        self.assertIn("分不出十六人", self.carve(count=16, **{"from": EAST}).hard[0].message)  # 指明了那一群而人数不够
        w = World.create("测")
        r = judge(w, plan(("左子穆", "左子穆点了弟子", []), spawn=[{"kind": "group", "name": "援兵", "faction": "无量剑西宗", "from": EAST}]), set())
        self.assertIn("分不出无量剑西宗的人马", r.hard[0].message)
        r = judge(World.create("测"), plan(("左子穆", "左子穆点了弟子", []), spawn=[{"kind": "group", "name": "援兵", "from": "段誉"}]), set())
        self.assertIn("不是一群人", r.hard[0].message)

    def test_the_whole_squad_comes_as_itself(self):
        w = World.create("测")
        r = judge(w, plan(("辛双清", "辛双清带着全部弟子赶到", []),
                          spawn=[{"kind": "group", "name": "西宗众人", "faction": "无量剑西宗", "count": 15}]), set())
        self.assertEqual((r.spawned, w.aliases.get("西宗众人")), ([WEST], WEST))       # 就是那一群，叫法照旧

    def test_a_supplied_band_is_a_pure_npc_squad(self):
        w = scatter(World.create("测"), "神农帮")
        nid, why = situation.spawn(w, {"kind": "group", "name": "神农帮帮众", "faction": "神农帮", "count": 12})
        self.assertEqual((nid, why), ("神农帮帮众", None))
        tpl = crowd.template(w.graph, "神农帮")                                          # 门下模板(23)
        self.assertEqual(w.graph.get(nid, "pool"), {"银两": round(12 * tpl["money"], 3), **{t["name"]: 12 for t in tpl["items"]}})  # 人头、零钱、兵刃、衣衫
        self.assertIn(nid, crowd.squads(w))
        self.assertIn("至多五十人", situation.spawn(w, {"kind": "group", "name": "大队", "faction": "神农帮", "count": 80})[1])
        self.assertEqual(situation.spawn(w, {"kind": "group", "name": "采药的帮众", "faction": "神农帮", "count": 4})[0], "采药的帮众")
        self.assertEqual(w.graph.get("采药的帮众", "base"), nid)                         # 附近已有同门人群：从那一群里分出
        self.assertEqual(situation.spawn(w, {"kind": "group", "name": "增援的帮众", "faction": "神农帮", "count": 20})[0], "增援的帮众")
        self.assertIsNone(w.graph.get("增援的帮众", "base"))                              # 人数不够分：是另一队增援
        self.assertIn("已是书中之名", situation.spawn(w, {"kind": "group", "name": "段誉", "faction": "大理国", "count": 3})[1])
        w.player.set("power", 70)
        do(w, {"做": "打晕", "对": nid, "数": 7})                                         # 分出四人之后还剩八人
        self.assertFalse(w.graph.has(nid))                                              # 补来的一队散了即删去
        self.assertIn("四散逃去", " ".join(w.turn.get("notes", [])))

    def test_a_faction_template_dresses_the_band(self):
        w = scatter(World.create("测"), "神农帮")
        w.graph.nodes["神农帮"]["squad_kit"] = {"handle": "神农帮帮众", "power": 20, "money": 0.2,
                                                "items": [{"name": "药锄", "kind": "兵刃", "steal": True}]}
        nid, _ = situation.spawn(w, {"kind": "group", "name": "采药的帮众", "faction": "神农帮", "count": 6})
        self.assertEqual((w.graph.get(nid, "power"), w.graph.get(nid, "pool")), (20, {"银两": 1.2, "药锄": 6}))


def scatter(w, faction):
    """世界底座(v11 23)在无量山一带本就布了神农帮的人群：要验「附近没有同门人群才补一队」，先把这一门的人群撤走。"""
    for s in list(w.graph.where(type=crowd.GROUP, faction=faction)):
        del w.graph.nodes[s]
    return w


class TravelTest(unittest.TestCase):
    """一群人随剧情远行：导演让他们去哪都行，赶来按路程，随行跟主角走，原著挪走带队之人他们跟着走。"""

    def setUp(self):
        self.w = World.create("测")
        self.g = self.w.graph

    def test_the_director_sends_them_far(self):
        w, g = self.w, self.g
        do(w, {"做": "结下", "谁": EAST, "对": "player", "为": "围攻"})
        self.assertEqual(do(w, {"做": "前往", "谁": EAST, "到": "大理城"})[1], [])
        self.assertEqual((g.get(EAST, "location"), crowd.besiegers(w)), ("大理城", []))  # 人走了，围不住
        self.assertNotIn(EAST, crowd.squads(w))
        self.assertIn("不在你跟前", do(w, {"做": "前往", "谁": EAST, "到": "无量山"})[1][0])

    def test_arrival_takes_the_road(self):
        w, g = self.w, self.g
        g.nodes[EAST]["location"] = "大理城"
        w.turn = {"minutes": 60}
        self.assertIn("赶不到", do(w, {"做": "赶来", "谁": EAST})[1][0])
        w.turn = {"minutes": 5 * 24 * 60}
        self.assertEqual(do(w, {"做": "赶来", "谁": EAST})[1], [])
        self.assertIn(EAST, crowd.squads(w))

    def test_the_leader_takes_his_men(self):
        w, g = self.w, self.g
        g.nodes[EAST]["leader"] = "左子穆"
        do(w, {"op": "set", "id": "左子穆", "key": "location", "value": "无量后山"}, origin="canon")
        self.assertEqual(g.get(EAST, "location"), "无量后山")
        w2 = World.create("测")
        w2.graph.nodes[EAST]["leader"] = "左子穆"
        do(w2, {"op": "set", "id": "左子穆", "key": "location", "value": "剑湖宫·内堂"})   # 导演挪人：一群人要另写
        self.assertEqual(w2.graph.get(EAST, "location"), HALL)

    def test_they_come_and_go_with_the_canon(self):
        w, g = self.w, self.g
        late = max(w.canon, key=lambda e: e["day"])
        g.nodes[EAST]["since"] = late["id"]
        self.assertNotIn(EAST, crowd.squads(w))
        w.done.append(late["id"])
        self.assertIn(EAST, crowd.squads(w))
        g.nodes[WEST]["until"] = w.canon[0]["id"]
        w.done.append(w.canon[0]["id"])
        self.assertNotIn(WEST, crowd.squads(w))

    def test_in_an_area_they_must_be_brought_near(self):
        w, g = self.w, self.g
        w.player.set("location", "无量山")
        g.nodes[EAST]["location"] = "无量山"
        self.assertTrue(situation.area(w, "无量山"))
        self.assertNotIn(EAST, crowd.squads(w))                                         # 同在一片，不在跟前
        w.turn = {"minutes": 60}
        do(w, {"做": "赶来", "谁": EAST})
        self.assertIn(EAST, crowd.squads(w))


class RecoverTest(unittest.TestCase):
    """打晕的人过两个时辰醒转归队：纯规则，不经 LLM。"""

    def test_they_wake_and_pick_up_their_swords(self):
        w = World.create("测")
        g = w.graph
        w.player.set("power", 70)
        do(w, {"做": "打晕", "对": EAST, "数": 4})
        do(w, {"做": "拿取", "物": "东宗弟子长剑", "量": 1})                              # 主角拿走一柄
        self.assertEqual((crowd.standing(g, EAST), g.get(EAST, "down")), (11, 4))
        w.advance(120)
        self.assertEqual(crowd.recover(w), [])                                           # 还没到两个时辰
        w.advance(120)
        self.assertEqual(crowd.recover(w), ["东宗弟子倒地的人里有四人醒转过来"])
        self.assertEqual((crowd.standing(g, EAST), g.get(EAST, "down")), (15, 0))
        self.assertEqual(g.get(EAST, "pool"), {"银两": 4.5, "长剑": 14, "衣衫": 15})     # 被拿走的那柄捡不回
        self.assertEqual(heads(w, EAST), 15)

    def test_the_dead_stay_dead(self):
        w = World.create("测")
        w.player.set("power", 70)
        do(w, {"做": "杀死", "对": EAST, "数": 2})
        w.advance(600)
        crowd.recover(w)
        self.assertEqual(crowd.standing(w.graph, EAST), 13)


class MoneyTest(unittest.TestCase):
    """NPC 之间给钱是一次加减：段誉给马五德三两，段誉少三两、马五德多三两。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.graph.nodes["段誉"]["money"] = 5.0

    def test_duan_yu_pays_ma_wude(self):
        w = self.w
        his = stock.funds(w, "马五德")
        self.assertEqual(do(w, {"做": "交给", "谁": "段誉", "物": "银两", "量": "三两", "与": "马五德"})[1], [])
        self.assertEqual((stock.funds(w, "段誉"), stock.funds(w, "马五德")), (2.0, his + 3))
        self.assertIn("给不出", do(w, {"做": "交给", "谁": "段誉", "物": "银两", "量": "三两", "与": "马五德"})[1][0])

    def test_money_written_but_not_moved_is_caught(self):
        r = judge(self.w, plan(("段誉", "段誉取出三两银子递给马五德", [])), set())
        self.assertIn(("give", "银两"), [(f.kind, f.entity) for f in r.hard])
        w = World.create("测")
        w.graph.nodes["段誉"]["money"] = 5.0
        r = judge(w, plan(("段誉", "段誉取出三两银子递给马五德", [{"做": "交给", "谁": "段誉", "物": "银两", "量": "三两", "与": "马五德"}])), set())
        self.assertEqual(r.hard, [])

    def test_the_bookkeeper_moves_npc_money(self):
        w = self.w
        judge(w, plan(("段誉", "段誉拱了拱手", [])), set())
        text = "青衫少年取出三两银子递给那老武师，笑道：「权当茶资。」"
        applied, rifts = settle.commit(w, {"changes": [{"据": "青衫少年取出三两银子递给那老武师", "谁": "段誉",
                                                         "ops": [{"做": "交给", "谁": "段誉", "物": "银两", "量": "三两", "与": "马五德"}]}]}, text)
        self.assertEqual((rifts, stock.funds(w, "段誉")), ([], 2.0))
        self.assertIn("银两：二两", next(p for p in settle.books(w, text)["people"] if p.startswith("段誉")))


class ReservedTest(unittest.TestCase):
    """v12 B2：原著近事要用的人群——带队之人是近事的相关者，事前叫不来、分不出人，后台单列一节(远远望见可以)。
    日志第 11 回：后台一边写「其相关者与其门派人马不得提前登场」，一边写「近处的人群……剧情要他们来写 赶来」，导演照后一句赶来了神农帮众。"""
    EVENT = "神农帮留钟灵下毒逼援"

    def setUp(self):
        from tianlong.world import lod
        self.w = World.create("测")
        self.w.done += ["无量剑第四场比剑", "龚光杰掌掴段誉", "容子矩毒伤毙命"]  # lod.upcoming 至多列三桩：先了掉厅上那三桩
        self.w.player.set("location", "澜沧江边高崖")
        self.soon = lod.upcoming(self.w)
        self.held = lod.reserved(self.w, self.soon)

    def test_the_leaders_crowd_is_held_for_the_canon(self):
        from tianlong.world import lod
        w, g = self.w, self.w.graph
        self.assertEqual(self.held, {"神农攻山帮众": self.EVENT})                       # 首领司空玄是这桩近事的相关者
        self.assertNotIn(EAST, self.held)                                              # 东宗弟子众没有首领：不受影响
        r = judge(w, plan((None, "林莽间钻出一群黄衫汉子", [{"做": "赶来", "谁": "神农帮众"}])), reserved=self.held)
        self.assertEqual(g.get("神农攻山帮众", "location"), "无量山")
        self.assertTrue(any("原著近事" in f.message for f in r.hard))                  # 赶来被驳回：整拍交返工
        r = judge(w, plan(spawn=[{"kind": "group", "name": "围山的帮众", "faction": "神农帮", "count": 5}]), reserved=self.held)
        self.assertTrue(any(f.kind == "spawn" and "原著近事" in f.message for f in r.hard))  # 分人也被驳回
        self.assertEqual(crowd.standing(g, "神农攻山帮众"), 28)
        r = judge(w, plan((None, "东宗弟子赶到崖上", [{"做": "赶来", "谁": EAST}])), reserved=self.held)
        self.assertEqual(g.get(EAST, "location"), "澜沧江边高崖")
        self.assertEqual(lod.reserved(w, lod.upcoming(w, {self.EVENT})), {})          # 那一桩被拉上台作主干：它的人马就能用了
        w.done.append(self.EVENT)
        held = lod.reserved(w, lod.upcoming(w))
        self.assertEqual(held, {})                                                     # 那一桩了了：可以赶来
        judge(w, plan((None, "林莽间钻出一群黄衫汉子", [{"做": "赶来", "谁": "神农帮众"}])), reserved=held)
        self.assertEqual(g.get("神农攻山帮众", "location"), "澜沧江边高崖")

    def test_the_backstage_lists_them_apart(self):
        from tianlong.narrative import prompts
        gm = rag.backstage(self.w, upcoming=self.soon, reserved=self.held)
        self.assertFalse(any("神农攻山帮众" in x for x in gm["flocks"]))               # 【近处的人群】里没有它
        self.assertTrue(any("神农攻山帮众" in x and self.EVENT in x for x in gm["reserved"]))
        text = prompts.render_backstage({**gm, "upcoming": []})
        self.assertIn("【原著近事要用的人马·事前不得登场（远远望见可以）", text)


class LeaderTest(unittest.TestCase):
    """v12 P1-2：人群卡与群战预裁显示首领、门派所图、眼下之事——日志第 12–15 回人群卡只写「站着28人｜分工行事」，帮众四回只会合围砍杀。"""
    GOAL = "所图：奉灵鹫宫令攻占无量山要地"

    def test_the_backstage_shows_the_leader_and_the_aim(self):
        from tests.test_adjudicate import cliff
        w = cliff()
        line = next(x for x in rag.backstage(w)["crowd"] if x.startswith("神农攻山帮众"))
        self.assertIn("首领司空玄（在无量山）", line)                                  # 首领不在群里：注明他在哪
        self.assertIn(self.GOAL, line)
        w2 = World.create("测")
        w2.player.set("location", "剑湖宫·宫门")
        line = next(x for x in rag.backstage(w2)["flocks"] if x.startswith("神农攻山帮众"))
        self.assertIn(f"首领司空玄｜{self.GOAL}", line)                                 # 近处的人群：首领与他们同处

    def test_the_writer_sees_a_masked_leader_and_their_aim(self):
        from tests.test_adjudicate import cliff
        from tianlong.narrative import prompts
        from tianlong.world import perspective
        w = cliff()
        w.graph.set("司空玄", "location", "澜沧江边高崖")                              # 首领在眼前，主角不识其名(帮主名号显赫，不在眼前时照叫其名)
        do(w, {"做": "打算", "谁": "神农帮众", "为": "擒下司空玄要的人"})
        self.assertEqual(w.graph.get("神农攻山帮众", "intent"), "擒下司空玄要的人")    # 导演可给一群人写打算
        view = perspective.veil(w, rag.build(w))
        q = view["squads"][0]
        self.assertEqual(q["leader"], perspective.handle(w, "司空玄"))
        self.assertNotIn("司空玄", q["intent"])
        text = prompts.render(view)
        self.assertIn(f"首领：{perspective.handle(w, '司空玄')}", text)
        self.assertNotIn("司空玄", text)


class LiveTest(unittest.TestCase):
    """真模型实测(v10 两回合)抓到的：一记耳光也是伤。"""

    def test_a_slap_is_a_wound(self):
        w = World.create("测")
        r = judge(w, plan(("龚光杰", "持剑少年扬手一记耳光掴在青衫少年脸上", [{"做": "伤人", "谁": "龚光杰", "对": "段誉", "血": 3}])), set())
        self.assertNotIn("baseless", [f.kind for f in r.soft])
        self.assertLess(w.graph.get("段誉", "hp"), w.graph.get("段誉", "max_hp"))


class GenesisTest(unittest.TestCase):
    """场景清单的顶层段落(v10)：交外部依原著抽取，genesis 编入并校验，错一处拒绝开局。"""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        for f in genesis.DATA.glob("*.json"):
            shutil.copy(f, cls.root / f.name)
        cls.base = json.loads((genesis.DATA / genesis.SCENES).read_text("utf-8"))

    def compile(self, **extra):
        data = json.loads(json.dumps(self.base))
        scenes = extra.pop("scenes", None)
        data.update(extra)
        if scenes:
            data["scenes"][0]["squads"] += scenes
        (self.root / genesis.SCENES).write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        genesis._compile.cache_clear()
        try:
            return genesis._compile(str(self.root)), None
        except genesis.GenesisError as e:
            return None, str(e)
        finally:
            genesis._compile.cache_clear()

    def test_the_extracted_sections_compile(self):
        book = next(i for i in json.loads((genesis.DATA / "05_items.json").read_text("utf-8"))
                    if (i.get("grants") or {}).get("skill") == "北冥神功")["id"]
        d, why = self.compile(kits={"神农帮": {"handle": "神农帮帮众", "power": 20, "money": 0.2, "items": [{"name": "药锄", "kind": "兵刃"}]}},
                              money=[{"id": "段誉", "money": 3, "basis": "推定"}],
                              canon_items=[{"id": book, "grade": "要物", "text": "帛卷上画着裸女与经脉，写着北冥神功", "full": 2}],
                              illiterate=[{"id": "南海鳄神", "basis": "推定"}],
                              scenes=[{"id": "神农帮围山众", "faction": "神农帮", "location": HALL, "count": 30, "leader": "司空玄",
                                       "since": self.base_event()}])
        self.assertIsNone(why)
        n = d["nodes"]
        self.assertEqual(n["神农帮"]["squad_kit"]["power"], 20)
        self.assertEqual(n["段誉"]["money"], 3.0)
        self.assertEqual((n[book]["grade"], n[book]["pages"], n[book]["qty"]), ("要物", [0, 1], 2))
        self.assertTrue(n["南海鳄神"]["illiterate"])
        flock = n["神农帮围山众"]
        self.assertEqual((flock["power"], flock["pool"]["药锄"], flock["leader"]), (20, 30, "司空玄"))  # 没写 kit 即用门下模板

    def base_event(self):
        return json.loads((genesis.DATA / "08_canon.json").read_text("utf-8"))[0]["id"]

    def test_bad_sections_refuse_to_open(self):
        cases = {
            "不是已登记的门派": {"kits": {"天外飞仙派": {"money": 0.1, "items": []}}},
            "零钱：「无名氏」": {"money": [{"id": "无名氏", "money": 1}]},
            "身上的银两须是数": {"money": [{"id": "段誉", "money": "很多"}]},
            "不是原著登记的器物": {"canon_items": [{"id": "剑架青钢剑", "grade": "器物"}]},
            "不改 holder": {"canon_items": [{"id": self.some_item(), "holder": "段誉"}]},
            "不识字：「无名氏」": {"illiterate": ["无名氏"]},
            "leader": {"scenes": [{"id": "某众", "faction": "神农帮", "location": HALL, "count": 5, "leader": "无名氏",
                                   "kit": {"money": 0, "items": []}}]},
            "不是原著事件": {"scenes": [{"id": "某众", "faction": "神农帮", "location": HALL, "count": 5, "since": "没有这回事",
                                        "kit": {"money": 0, "items": []}}]},
        }
        for why, extra in cases.items():
            d, err = self.compile(**extra)
            self.assertIsNone(d, why)
            self.assertIn(why, err)

    def some_item(self):
        return json.loads((genesis.DATA / "05_items.json").read_text("utf-8"))[0]["id"]


if __name__ == "__main__":
    unittest.main()
