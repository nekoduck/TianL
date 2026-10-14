"""
[INPUT]: 依赖 tianlong.world 的 acts / stock / crowd / scribe / effects / adjudicate / settle / rag / perspective / scenery 与 data/canon 原著世界(含 18_scenes.json 的物量与人群)，
         tianlong.engine 的 Game 与 _newsworthy、tianlong.narrative 的 prompts；以桩 LLM 替代 Gemini
[OUTPUT]: unittest 用例——v9 事码与物量：事码(动词归一、量读成数、平常之事化为既有指令、旧写法照收)；
          物量(地上二两碎银拿一两便剩一两、拿不出更多、给钱从身上扣且不够即给不出、银两不是器物也写不动、放下的钱落在地上、总数守恒)；
          一叠与残卷(信笺拿三张剩十七、剑影图拿三张是全本十二张之三、残卷只研习得到初窥、几份落到一人手里即拼回完整)；
          无名弟子(十五人一群、力不及整群不得夺杀、力过整群杀二人剩十三人且遗物落地、记怨在同门、只剩二人即散而底层留空壳读档不复活、
          身法够高才偷得到且无人察觉不记怨、衣衫偷不下、被围住走不脱、力过一半才冲得出、后台有群战预裁)；
          文书状态机(识字且手边有笔墨与纸才写得成、纸少一张、写成→封缄→拆封只进不退、封着口读不到、撕成两半各读半段、拼合复原、毁去即无；凭空「取出一封信」即返工)；
          授意(玩家没说拿钱，导演替他拿的被剥掉；说了「银子」够得着的碎银与钱袋都算所指；起意提笔才写得成信；事码写明主角做的，谁的拍都查)；
          词表(写你得了银子而银两分文未动即漏记，拿了一部分的不算没拿)；账房的事码(交给银两入账)；补记(银两多了少了、人群倒下几人)；
          视锥与提示词(此处器物带数量、在场人群、群战预裁、银两、事码纲领)；试演与定稿同一结果；一整回合的事码经引擎落账；
          真模型实测抓到的写法(「东宗弟子众佩剑」认得是长剑、账房的名目也认、书写用过的纸笔不算取得、文书 id 带形制)
[POS]: tests 的 v9 验证——「凡有数量的后果由规则算、LLM 只宣告发生了什么」在银两、人群与文书上的离线证据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import unittest

from tests.test_adjudicate import judge, plan
from tests.test_engine import StubLLM
from tianlong.engine import Game, _newsworthy
from tianlong.narrative import prompts
from tianlong.world import acts, adjudicate, crowd, effects, perspective, rag, scribe, settle, stock
from tianlong.world.world import World

HALL, INNER, COURT = "剑湖宫·练武厅", "剑湖宫·内堂", "剑湖宫"
SILVER, PURSE, PAPER, BRUSH, NOTES = "碎银", "马五德钱袋", "内堂信笺", "内堂笔墨", "玉壁剑影图"
EAST = "东宗弟子众"


def do(w, *ops, origin="director"):
    """直接落账一批事码：返回 (成立的记录, 驳回的缘由)。"""
    w.turn = w.turn or {}
    ok, bad = effects.apply(w, list(ops), origin)
    return ok, [why for _, why in bad]


def total_money(w) -> float:
    """世上的银两总数：人身上的零钱、钱袋里的、地上的碎银、人群身上的。"""
    g = w.graph
    pockets = w.player["money"] + sum(g.get(p, "money") or 0 for p in g.where(type="person"))
    bags = sum(stock.purse(g, i) for i in g.where(type="item") if effects.usable(w, i))
    piles = sum(stock.qty(g, i) for i in g.where(type="item") if stock.is_cash(g, i) and effects.usable(w, i))
    flocks = sum((g.get(s, "pool") or {}).get("银两", 0) for s in g.where(type=crowd.GROUP))
    return round(pockets + bags + piles + flocks, 3)


class CodeTest(unittest.TestCase):
    """事码：LLM 说的类代码——动词归一、量读成数、平常之事化为世界的微指令。"""

    def setUp(self):
        self.w = World.create("测")

    def test_verbs_and_amounts_normalize(self):
        a = acts.normalize(self.w, {"做": "拿", "物": "碎银子", "量": "一两三钱"})
        self.assertEqual((a["做"], a["谁"], a["物"], a["量"]), ("拿取", "player", acts.MONEY, 1.3))
        self.assertEqual(acts.normalize(self.w, {"做": "给", "物": "银子", "量": "两两", "与": "钟灵"})["量"], 2)
        self.assertEqual(acts.normalize(self.w, {"做": "拿取", "物": "信笺", "量": "三张"})["量"], 3)
        self.assertEqual(acts.normalize(self.w, {"做": "偷", "自": "东宗弟子们", "物": "长剑"})["自"], EAST)  # 人群认叫法
        self.assertEqual(stock.say(1.3), "一两三钱")

    def test_plain_acts_lower_to_the_old_ops(self):
        low = acts.expand(self.w, [{"做": "前往", "到": "无量山"}, {"做": "伤人", "谁": "龚光杰", "对": "褚师弟", "血": 15},
                                   {"做": "结下", "谁": "段誉", "对": "player", "为": "随行"}, {"做": "识名", "谁": "段誉"},
                                   {"做": "研习", "物": "无量剑法"}, {"op": "set", "id": "player", "key": "posture", "value": "坐"}])
        self.assertEqual([op.get("op") for op in low], ["set", "add", "link", "reveal", "study", "set"])  # 旧写法原样照收
        self.assertEqual((low[1]["id"], low[1]["value"]), ("褚师弟", -15))
        self.assertTrue(all(not acts.is_act(op) for op in low))
        rule = acts.expand(self.w, [{"做": "拿取", "物": "碎银", "量": "一两"}])
        self.assertTrue(acts.is_act(rule[0]))                                           # 规则之事留作一件事，由 acts.perform 执行

    def test_an_unknown_verb_is_refused_not_crashed(self):
        ok, why = do(self.w, {"做": "飞升", "物": "碎银"})
        self.assertEqual(ok, [])
        self.assertIn("不识的事码", why[0])


class MoneyTest(unittest.TestCase):
    """物量：拿一两，地上剩一两；给出去，身上就少了；银两是数不是器物，总数守恒。"""

    def setUp(self):
        self.w = World.create("测")
        self.g = self.w.graph

    def test_take_part_of_the_silver(self):
        w, g, before = self.w, self.g, total_money(self.w)
        ok, why = do(w, {"做": "拿取", "物": SILVER, "量": "一两"})
        self.assertEqual(why, [])
        self.assertEqual((w.player["money"], stock.qty(g, SILVER)), (1.5, 1))          # 出身带着五钱，拾得一两
        self.assertEqual(ok[0]["op"], "money")
        self.assertIn("一两", [c["amount"] for c in rag.build(w)["items"] if c["name"] == SILVER])
        self.assertEqual(do(w, {"做": "拿取", "物": SILVER, "量": "三两"})[1][0], "碎银只有一两，拿不出三两")
        do(w, {"做": "拿取", "物": SILVER})                                               # 不写量即全部：拿光了这一堆就没了
        self.assertNotIn(SILVER, [c["name"] for c in rag.build(w)["items"]])
        self.assertEqual((w.player["money"], total_money(w)), (2.5, before))

    def test_giving_money_takes_it_from_your_pocket(self):
        w, before = self.w, total_money(self.w)
        hers = stock.funds(w, "钟灵")
        self.assertEqual(do(w, {"做": "交给", "物": "银两", "量": "三钱", "与": "钟灵"})[1], [])
        self.assertEqual((w.player["money"], stock.funds(w, "钟灵")), (0.2, round(hers + 0.3, 3)))
        self.assertIn("给不出", do(w, {"做": "交给", "物": "银两", "量": "一两", "与": "钟灵"})[1][0])  # 身上只有二钱
        self.assertEqual(total_money(w), before)

    def test_money_is_not_written_directly(self):
        ok, why = do(self.w, {"op": "set", "id": "player", "key": "money", "value": 999})
        self.assertEqual(ok, [])
        self.assertTrue(why)
        self.assertEqual(self.w.player["money"], 0.5)

    def test_money_put_down_lies_on_the_floor(self):
        w = self.w
        do(w, {"做": "放下", "物": "银两", "量": "二钱"})
        piles = [i for i in w.graph.where(type="item", location=HALL) if stock.is_cash(w.graph, i)]
        self.assertEqual(sorted(stock.qty(w.graph, i) for i in piles), [0.2, 2])         # 放在另一处的钱不并进宾客椅下那一堆
        self.assertEqual(w.player["money"], 0.3)

    def test_a_purse_is_money_too(self):
        w = self.w
        w.player.set("power", 60)
        w.player.set("skills", ["凌波微步"])                                            # 绝顶的身法
        ok, why = do(w, {"做": "偷取", "自": "马五德", "物": PURSE})
        self.assertEqual(why, [])
        self.assertTrue(ok[0].get("stealth"))
        self.assertEqual(stock.funds(w, "player"), 20.5)
        self.assertEqual(do(w, {"做": "交给", "物": "银两", "量": "十两", "与": "钟灵"})[1], [])  # 先付零钱，不够再从钱袋里出
        self.assertEqual((w.player["money"], stock.purse(w.graph, PURSE)), (0, 10.5))


class StackTest(unittest.TestCase):
    """一叠与残卷：拿几张，原处只剩其余；一部书撕散的几份落到同一人手里即合回一件。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.player.set("location", INNER)
        self.g = self.w.graph

    def test_take_three_sheets(self):
        w, g = self.w, self.g
        ok, why = do(w, {"做": "拿取", "物": PAPER, "量": "三张"})
        self.assertEqual(why, [])
        part = next(i for i in w.player["inventory"] if stock.base(g, i) == PAPER)
        self.assertEqual((stock.qty(g, part), stock.qty(g, PAPER)), (3, 17))
        self.assertEqual(perspective.thing(w, part), PAPER)                              # 分出来的那一份叫的还是那件东西
        do(w, {"做": "放下", "物": part})
        self.assertEqual(stock.qty(g, PAPER), 20)                                        # 放回同一处：合回一叠

    def test_three_pages_of_the_sword_notes(self):
        w, g = self.w, self.g
        w.player.set("location", HALL)
        self.assertIn("暗藏着", do(w, {"做": "拿取", "物": NOTES, "量": 3})[1][0])      # 锁在隔壁的抽屉里：人到了才找得着
        w.player.set("location", INNER)
        do(w, {"做": "拿取", "物": NOTES, "量": "三张"})
        self.assertTrue(self.g.get(NOTES, "hidden"))                                    # 抽出三张，余下的仍锁在抽屉里
        part = next(i for i in w.player["inventory"] if stock.base(g, i) == NOTES)
        self.assertEqual((stock.pages(g, part), stock.full(g, part)), ([0, 1, 2], 12))
        self.assertEqual(stock.measure(g, part), "三张（全本十二张）")
        self.assertEqual(stock.measure(g, NOTES), "九张（全本十二张）")
        do(w, {"做": "拿取", "物": NOTES})                                               # 余下的九张也到了手里：合回完整的一部
        self.assertEqual([i for i in w.player["inventory"] if stock.base(g, i) == NOTES], [NOTES])
        self.assertFalse(stock.fragment(g, NOTES))

    def test_a_fragment_only_teaches_its_pages(self):
        w, g = self.w, self.g
        book = next(i for i in g.where(type="item") if (g.get(i, "grants") or {}).get("skill") == "北冥神功")
        g.nodes[book].update(location=INNER, holder=None, hidden=False, full=2, pages=[0, 1], qty=2, split=True)
        do(w, {"做": "拿取", "物": book, "量": 1})
        part = next(i for i in w.player["inventory"] if stock.base(g, i) == book)
        self.assertEqual(stock.cap(g, part), 1)
        from tianlong.world import growth
        growth._log(w)[book] = {"minutes": 10 ** 6, "stage": 1, "since": -99}         # 攒够了时长，却只有半部
        self.assertIn("残卷", growth.study(w, part, 120))
        self.assertEqual(growth.stage_of(w, book), 1)


class SquadTest(unittest.TestCase):
    """无名弟子：十五人一体；动其中一人即是动整群；只剩二人即散。"""

    def setUp(self):
        self.w = World.create("测")
        self.g = self.w.graph

    def test_two_squads_stand_in_the_hall(self):
        g = self.g
        self.assertEqual({s: crowd.standing(g, s) for s in crowd.squads(self.w)}, {EAST: 15, "西宗弟子众": 15})
        self.assertEqual(g.get(EAST, "pool"), {"银两": 4.5, "长剑": 15, "衣衫": 15})
        self.assertIn("东宗弟子", [q["handle"] for q in rag.build(self.w)["squads"]])

    def test_a_weak_hand_cannot_touch_the_squad(self):
        for act in ({"做": "夺取", "自": "东宗弟子", "物": "长剑"}, {"做": "杀死", "对": EAST}, {"做": "打晕", "对": EAST, "数": 2}):
            ok, why = do(self.w, act)
            self.assertEqual(ok, [])
            self.assertIn("整群", why[0])
        self.assertEqual(crowd.standing(self.g, EAST), 15)

    def test_a_strong_hand_cuts_them_down(self):
        w, g = self.w, self.g
        w.player.set("power", 70)
        ok, why = do(w, {"做": "杀死", "对": "东宗弟子", "数": 2})
        self.assertEqual(why, [])
        self.assertEqual((crowd.standing(g, EAST), g.get(EAST, "dead")), (13, 2))
        loot = {i: stock.qty(g, i) for i in g.where(type="item", location=HALL) if "东宗弟子" in i or stock.is_cash(g, i)}
        self.assertEqual(loot.get("东宗弟子长剑"), 2)
        self.assertIn(0.6, loot.values())                                                # 两人身上的零钱落在地上
        self.assertLess(g.get("左子穆", "bond")["log"][-1]["w"], 0)                       # 杀其门下弟子：同门记怨
        self.assertEqual(_newsworthy(ok, 5, 0), 2)                                       # 众目之下有人身亡
        ok, why = do(w, {"做": "打晕", "对": EAST, "数": 11})
        self.assertFalse(crowd.is_squad(g, EAST))
        self.assertIn("四散逃去", " ".join(w.turn.get("notes", [])))
        self.assertNotIn(EAST, crowd.squads(w))
        self.assertNotIn("东宗弟子", [q["handle"] for q in rag.build(w)["squads"]])
        again = World.from_dump(copy.deepcopy(w.dump()))
        self.assertFalse(crowd.is_squad(again.graph, EAST))                              # 读档不复活

    def test_stealing_wants_a_light_foot(self):
        w, g = self.w, self.g
        self.assertIn("身法不及", do(w, {"做": "偷取", "自": EAST, "物": "长剑"})[1][0])
        w.player.set("skills", ["凌波微步"])
        ok, why = do(w, {"做": "偷取", "自": EAST, "物": "长剑"})
        self.assertEqual((why, w.player["inventory"]), ([], ["东宗弟子长剑"]))
        self.assertEqual(g.get(EAST, "pool")["长剑"], 14)
        self.assertFalse((g.get("左子穆", "bond") or {}).get("log"))                     # 无人察觉：不记怨
        self.assertIn("偷不下来", do(w, {"做": "偷取", "自": EAST, "物": "衣衫"})[1][0])

    def test_besieged_you_must_break_out(self):
        w = self.w
        do(w, {"做": "结下", "谁": EAST, "对": "player", "为": "围攻"})
        self.assertIn("团团围住", do(w, {"做": "前往", "到": "无量山"})[1][0])
        self.assertIn("冲不出", do(w, {"做": "脱身"})[1][0])
        self.assertIn("被东宗弟子围住", [t["text"] for t in rag.condition(w)])
        w.player.set("power", 45)                                                         # 过整群一半之力
        self.assertEqual(do(w, {"做": "脱身", "到": "无量山"})[1], [])
        self.assertEqual((w.here, crowd.besiegers(w)), ("无量山", []))

    def test_the_director_sees_the_squad_forecast(self):
        w = self.w
        gm = rag.backstage(w)
        self.assertTrue(any(line.startswith(EAST) and "必败" in line for line in gm["crowd"]))
        text = prompts.render_backstage(gm)
        self.assertIn("【群战预裁", text)
        self.assertIn("【在场人群", prompts.render(rag.build(w)))


class LiveTest(unittest.TestCase):
    """真模型实测(五回合)抓到的几处：写法宽一些，规则不放松。"""

    def test_the_squads_sword_by_any_name(self):
        w = World.create("测")
        w.player.set("skills", ["凌波微步"])
        ok, why = do(w, {"做": "偷取", "自": "东宗弟子", "物": "东宗弟子众佩剑"})        # 导演写过的名目
        self.assertEqual((why, w.player["inventory"]), ([], ["东宗弟子长剑"]))
        self.assertEqual(crowd.kit(w.graph, EAST, "长衫")["name"], "衣衫")
        self.assertIn("只有长剑、衣衫与零钱", do(w, {"做": "偷取", "自": EAST, "物": "靴子"})[1][0])  # 认不出时告诉导演身上有什么
        text = "你指尖搭上他腰间佩剑的吞口，连鞘带剑悄无声息地滑入你掌中。"
        applied, rifts = settle.commit(w, {"changes": [{"据": "连鞘带剑悄无声息地滑入你掌中", "谁": "player",
                                                         "ops": [{"做": "偷取", "谁": "player", "自": EAST, "物": "东宗弟子佩剑"}]}]},
                                       text, {EAST})                                      # 账房写的名目
        self.assertEqual((rifts, stock.qty(w.graph, "东宗弟子长剑")), ([], 2))

    def test_the_brush_you_wrote_with_is_not_a_theft(self):
        w = World.create("测")
        w.player.set("location", INNER)
        r = judge(w, plan(("player", "你抄起案上笔墨，取过一张信笺，写下「后山相候」", [{"做": "书写", "物": "字条", "文": "后山相候", "致": "马五德"}])),
                  adjudicate.targets(w, "写张字条留给马五德"))
        self.assertEqual([f.kind for f in r.hard + r.soft if f.kind == "acquire"], [])
        letter = r.applied[0]["id"]
        self.assertEqual(letter, "测致马五德字条")
        do(w, {"做": "放下", "物": letter})
        self.assertIsNone(next(c for c in rag.build(w)["items"] if c["name"] == letter)["amount"])  # 一张字条不报「一件」


class ScribeTest(unittest.TestCase):
    """文书状态机：剧情不能凭空多出一封信，人物却真能提笔写一封。"""

    def setUp(self):
        self.w = World.create("测")
        self.g = self.w.graph

    def write(self, **kw):
        return do(self.w, {"做": "书写", "物": "书信", "文": "明日午时，宫门外相候。", "致": "钟灵", **kw})

    def test_no_brush_no_letter(self):
        self.assertIn("没有笔墨", self.write()[1][0])                                    # 练武厅里没有纸笔
        self.w.player.set("location", INNER)
        self.w.player.set("illiterate", True)
        self.assertIn("不识字", self.write()[1][0])

    def test_write_seal_open_read(self):
        w, g = self.w, self.g
        w.player.set("location", INNER)
        ok, why = self.write()
        self.assertEqual(why, [])
        letter = ok[0]["id"]
        self.assertEqual((ok[0]["op"], g.get(letter, "text"), stock.qty(g, PAPER)), ("forge", "明日午时，宫门外相候。", 19))
        self.assertIn(letter, w.player["inventory"])
        self.assertEqual(perspective.thing(w, letter), "你写给大眼圆脸的少女的书信")              # 叫不出名字的收信人只叫外貌
        self.assertEqual(do(w, {"做": "封缄", "物": letter})[1], [])
        self.assertIn("拆封才读得到", do(w, {"做": "阅读", "物": letter})[1][0])
        self.assertIsNone(next(c for c in rag.build(w)["player"]["inventory"] if c["name"] == letter)["text"])
        self.assertEqual(do(w, {"做": "拆封", "物": letter})[1], [])
        self.assertIn("不能再封", do(w, {"做": "封缄", "物": letter})[1][0])            # 封口一拆便回不去
        self.assertEqual(do(w, {"做": "阅读", "物": letter})[1], [])

    def test_tear_and_join(self):
        w, g = self.w, self.g
        w.player.set("location", INNER)
        letter = self.write()[0][0]["id"]
        ok, why = do(w, {"做": "撕开", "物": letter, "份": 2})
        self.assertEqual(why, [])
        half = [i for i in w.player["inventory"] if stock.base(g, i) == letter and i != letter][0]
        self.assertTrue(scribe.readable(g, letter).endswith("（残）"))
        do(w, {"做": "放下", "物": half})
        self.assertEqual(len([i for i in w.player["inventory"] if stock.base(g, i) == letter]), 1)  # 撕下的半张不自己飞回来
        do(w, {"做": "拿取", "物": half})
        self.assertEqual(do(w, {"做": "拼合", "物": letter})[1], [])
        self.assertEqual(scribe.readable(g, letter), "明日午时，宫门外相候。")
        do(w, {"做": "毁去", "物": letter})
        self.assertNotIn(letter, w.player["inventory"])
        self.assertFalse(effects.usable(w, letter))

    def test_a_conjured_letter_goes_back(self):
        r = judge(self.w, plan(("钟灵", "钟灵从怀中取出一封信，塞到你手里", [])))
        self.assertIn("conjure", [f.kind for f in r.hard])                              # 信笺不是信：世上没有这封信


class AgencyTest(unittest.TestCase):
    """授意：主角只做玩家所选之事——拿钱、偷夺、提笔都须是玩家所指。"""

    def setUp(self):
        self.w = World.create("测")

    def test_money_the_player_never_asked_for_is_stripped(self):
        r = judge(self.w, plan(("player", "你四下打量，顺手拾起碎银", [{"做": "拿取", "物": SILVER, "量": "一两"}])),
                  adjudicate.targets(self.w, "四下看看"))
        self.assertEqual(self.w.player["money"], 0.5)
        self.assertTrue(r.candidates)
        aim = adjudicate.targets(self.w, "捡起椅子下的银子")
        self.assertIn(SILVER, aim)
        judge(self.w, plan(("player", "你俯身拾起一两碎银", [{"做": "拿取", "物": SILVER, "量": "一两"}])), aim)
        self.assertEqual(self.w.player["money"], 1.5)

    def test_writing_is_the_players_to_choose(self):
        w = self.w
        w.player.set("location", INNER)
        letter = {"做": "书写", "物": "字条", "文": "后会有期"}
        r = judge(w, plan(("player", "你提笔留下一张字条", [letter])), adjudicate.targets(w, "看看书案"))
        self.assertEqual((r.candidates, stock.qty(w.graph, PAPER)), (["提笔书写"], 20))
        self.assertIn(adjudicate.WRITE, adjudicate.targets(w, "给钟灵写封信"))
        judge(w, plan(("player", "你提笔留下一张字条", [letter])), adjudicate.targets(w, "留书一封"))
        self.assertEqual(stock.qty(w.graph, PAPER), 19)

    def test_an_act_naming_the_player_is_checked_in_anyones_beat(self):
        r = judge(self.w, plan(("钟灵", "钟灵笑嘻嘻地看你拾银子", [{"做": "拿取", "谁": "player", "物": SILVER}])), set())
        self.assertTrue(r.candidates)
        self.assertEqual(self.w.player["money"], 0.5)


class LedgerTest(unittest.TestCase):
    """词表、账房与补记：银两与人群同样账文同构。"""

    def setUp(self):
        self.w = World.create("测")

    def test_writing_money_without_moving_it_is_caught(self):
        r = judge(self.w, plan(("player", "你掏出一两银子递给钟灵", [])), {"钟灵"})
        self.assertIn(("give", "银两"), [(f.kind, f.entity) for f in r.hard])
        w = World.create("测")
        r = judge(w, plan(("player", "你掏出三钱银子递给钟灵", [{"做": "交给", "物": "银两", "量": "三钱", "与": "钟灵"}])), {"钟灵"})
        self.assertEqual(r.hard, [])

    def test_disciples_felled_on_the_page_must_fall_on_the_books(self):
        w = World.create("测")
        w.player.set("power", 70)
        self.assertIn(("fell", EAST), [(f.kind, f.entity) for f in judge(w, plan(("player", "你连出两掌，打倒了两名东宗弟子", [])), {EAST}).hard])
        self.assertEqual(judge(World.create("测"), plan(("东宗弟子众", "东宗弟子扶起倒地的褚师弟", []))).hard, [])  # 倒的是褚师弟
        w = World.create("测")
        w.player.set("power", 70)
        r = judge(w, plan(("player", "你连出两掌，打倒了两名东宗弟子", [{"做": "打晕", "对": EAST, "数": 2}])), {EAST})
        self.assertEqual((r.hard, crowd.standing(w.graph, EAST)), ([], 13))

    def test_taking_part_is_not_taking_nothing(self):
        r = judge(self.w, plan(("player", "你拾起碎银，掂了掂", [{"做": "拿取", "物": SILVER, "量": "一两"}])), {SILVER})
        self.assertEqual([f.kind for f in r.hard], [])                                  # 碎银还在地上，可你确实拿了一两

    def test_the_bookkeeper_speaks_acts(self):
        w = self.w
        hers = stock.funds(w, "钟灵")
        judge(w, plan(("player", "你看了看钟灵", [])), {"钟灵"})
        text = "你摸出三钱银子塞给那少女，她笑着收下了。"
        applied, rifts = settle.commit(w, {"changes": [{"据": "你摸出三钱银子塞给那少女", "谁": "player",
                                                         "ops": [{"做": "交给", "物": "银两", "量": "三钱", "与": "钟灵"}]}]}, text, {"钟灵"})
        self.assertEqual((rifts, applied[0]["op"], stock.funds(w, "钟灵")), ([], "money", round(hers + 0.3, 3)))
        self.assertIn("银两：二钱", settle.books(w, text)["player"])

    def test_the_ledger_notes_what_the_page_left_out(self):
        w = self.w
        w.player.set("power", 70)
        before = settle.glance(w)
        do(w, {"做": "拿取", "物": SILVER, "量": "一两"}, {"做": "打晕", "对": EAST, "数": 2})
        changes = settle.delta(w, before)
        self.assertIn("你身上多了一两银子", [c["text"] for c in changes])
        self.assertIn("东宗弟子倒下了二人", [c["text"] for c in changes])


class ViewTest(unittest.TestCase):
    """视锥与提示词：器物带数量、在场人群、银两；导演的纲领是事码。"""

    def test_the_prompts_speak_acts(self):
        w = World.create("测")
        text = prompts.render(perspective.veil(w, rag.build(w)))
        self.assertIn("碎银（宾客椅下的地上）｜二两", text)
        self.assertIn("银两：五钱", text)
        for word in ('"做":"拿取"', '"做":"书写"', "群战预裁", "银两是数不是器物", "器物一件也不得新造"):
            self.assertIn(word, prompts.PLOT_GUIDE)
        self.assertIn('"做":"识名"', prompts.NAMES)
        self.assertIn('"做":"交给"', prompts.SETTLE_OPS)
        w = World.create("测")
        gm = rag.backstage(w)
        self.assertIn(f"马五德：{stock.say(stock.funds(w, '马五德'))}（马五德钱袋里二十两）", gm["money"])  # 零钱(22)连同钱袋
        self.assertTrue(any("偷取" in line for line in gm["ruling"]))


class TurnTest(unittest.TestCase):
    """试演与定稿同一结果；一整回合的事码经引擎落账。"""

    def test_the_rehearsal_matches_the_final(self):
        w = World.create("测")
        w.player.set("power", 70)
        p = plan(("player", "你连出两掌，打倒两名东宗弟子，又拾起碎银", [{"做": "打晕", "对": EAST, "数": 2}, {"做": "拿取", "物": SILVER, "量": "一两"}]))
        a, b = copy.deepcopy(w), copy.deepcopy(w)
        ra, rb = judge(a, copy.deepcopy(p), {EAST, SILVER}), judge(b, copy.deepcopy(p), {EAST, SILVER})
        self.assertEqual(ra.applied, rb.applied)
        self.assertEqual((a.graph.nodes, a.player.data["money"]), (b.graph.nodes, b.player.data["money"]))

    def test_a_turn_in_acts(self):
        w = World.create("测")
        beats = [{"who": "player", "text": "你俯身从宾客椅下拾起一两碎银，揣入怀中", "ops": [{"做": "拿取", "物": "碎银", "量": "一两"}]},
                 {"who": "钟灵", "to": "player", "text": "梁上少女咯咯一笑：「捡到便宜啦？」", "ops": [{"做": "神色", "谁": "钟灵", "为": "好奇"}]}]
        llm = StubLLM({"说书人与导演": {"beats": beats, "pace": "片刻", "scene": {"state": "开", "ask": "能否得些盘缠"}},
                       "小说家": "你俯身从宾客椅下拾起一两碎银，揣入怀中。梁上少女咯咯一笑。\n===\n梗概：你拾得一两碎银\n传言：无"})
        turn = Game(w, llm).act("捡起椅子下的银子，只拿一两")
        self.assertEqual((w.player["money"], stock.qty(w.graph, SILVER)), (1.5, 1))
        self.assertIn("银两一两五钱", [t["text"] for t in turn["status"]])


if __name__ == "__main__":
    unittest.main()
