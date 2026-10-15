"""
[INPUT]: 依赖 tianlong.world 的 World / plot / lod / effects / rag / adjudicate / access / situation / bond、tianlong.narrative 的 prompts / agents（以 data/canon 编译出的真实原著世界为对象，离线）
[OUTPUT]: 场外编剧(v11)的离线验收——主角不在的地方，江湖照样在走：
          演绎与创作(ModeTest：原著前置未变照原著演、被扰动也照演；前提破了附近的与分量重的交改写、远方小事作罢、衍生事件与纠缠者作罢；作罢、被主角拦下、志向被眼前的剧情改了即原著线已变)；
          剧情推力(DriveTest：数据写了照数据、不甘现状者强隐退者弱；谁该有下一步——原著线变了的都写、没变的只写推力强的，近旁与见过主角的人不写，七日内另有安排的不写，按推力隔日)；
          规则审(RuleTest：名实、时空(日子够、道路走得通、事后的去向一日之内、不分身)、归属(主角身边、等着主角、七日内照原著的人)、胜负(武功高低、手段、悬殊)、武学来路、
          器物(在谁手里、暗藏要知情、主角手里的)、地理不动、说法(对得上后果、不剧透——这桩事自己杀的人与揭开的隐情不算)、心愿了了要写新志向；会因此改变的原著只列作 ripples)；
          落地与结算(AdoptTest：与原著同一格式排进日程、到期照前提结算、被场外剧情带走的人原著要用时得赶得回来、写到主角跟前交近处导演、只差路程的原著延后、存档)；
          剧透(SpoilerTest)、来人(ArrivalTest)、提示词与整形(PromptTest：提示词写明与规则审同一套规矩，审稿读不出判定即不过)
          v13：与主角有过交集的人不再被冻住（救过的人、认得主角的人场外编剧照写）；未了之事所系者才算等着主角的故事
[POS]: tests 的场外编剧组：「只减不增」之后的那一版——场外有剧情安排，先贴原著，原著被动了就创作新的剧情线；合理才入日程，不合理的一律不过
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import unittest

from tianlong.narrative import agents, prompts
from tianlong.world import access, adjudicate, bond, effects, lod, plot, rag, situation
from tianlong.world.clock import PER_DAY
from tianlong.world.world import World


def canon(w, eid):
    return next(e for e in w.canon if e["id"] == eid)


def freed(w, *people):
    """这几人再无原著之约：原著里已没有他们的戏，往后的路交创作家。"""
    w.done.extend(e["id"] for e in w.canon if set(people) & lod._cast(e) and e["id"] not in w.done)


def event(day=2, where="万劫谷", actors=("秦红棉",), summary="秦红棉往万劫谷寻仇", **kw):
    return {"day": day, "where": where, "actors": list(actors), "summary": summary, **kw}


class _World(unittest.TestCase):
    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        freed(self.w, "秦红棉", "木婉清", "甘宝宝", "钟万仇")  # 万劫谷一带的几人原著已尽：场外编剧的地界

    def vet(self, *events, who="秦红棉", **draft):
        return plot.vet(self.w, plot.sequel(self.w, who), {"line": "测", "goal": "测", "events": list(events), **draft})

    def rejects(self, phrase, *events, **kw):
        plan, problems = self.vet(*events, **kw)
        self.assertIsNone(plan)
        self.assertTrue(any(phrase in p for p in problems), problems)
        return problems


# ============================================================
#  演绎与创作
# ============================================================
class ModeTest(_World):
    def test_canon_ahead_is_performed_and_a_changed_line_is_created(self):
        w = self.w
        self.assertEqual(plot.mode(w, "南海鳄神"), "演绎")                            # 原著前置未变：照原著演
        self.assertEqual(plot.mode(w, "秦红棉"), "创作")                              # 原著里已没有她的戏
        w.graph.nodes["南海鳄神"]["adrift"] = True
        self.assertEqual(plot.mode(w, "南海鳄神"), "创作")                            # 原著线变了
        w.graph.set("段延庆", "agenda", "杀了段正淳夺回皇位")
        self.assertEqual(plot.awaken(w), [])                                          # 白世镜要掩盖的杀马大元之事：马大元开局前就死了，不算
        w.apply([{"op": "set", "id": "段正淳", "key": "status", "value": "dead"}], "canon")
        self.assertIn("段延庆", plot.awaken(w))
        self.assertEqual(plot.mode(w, "段延庆"), "创作")                              # 志向所系之人在这一局里死了：了了，或落了空
        self.assertNotIn("段延庆", plot.awaken(w))                                    # 一桩死讯只醒一次
        w.graph.nodes["钟万仇"]["wishes"] = [{"wish": "杀了段正淳", "target": "段正淳", "done_when": [["段正淳", "status", "dead"]]}]
        self.assertIn("钟万仇", plot.awaken(w))                                       # 数据里的心愿：done_when 成立即了了
        self.assertEqual(w.graph.nodes["钟万仇"]["wishes"][0]["done"], w.clock.day)

    def test_a_disturbed_canon_with_its_premises_intact_is_still_performed(self):
        w = World.create()
        major = canon(w, "乔峰携阿朱赴聚贤庄")
        w.graph.set("阿朱", "status", "wounded")
        w.taint.update({"乔峰", "阿朱"})
        self.assertEqual(lod.verdict(w, major, 2)[0], "canon")                       # 演绎家：被扰动也照原著演，不调模型

    def test_a_broken_canon_goes_to_the_creator_or_lapses(self):
        w = World.create()
        major, minor = canon(w, "乔峰携阿朱赴聚贤庄"), canon(w, "龚光杰掌掴段誉")
        w.graph.set("阿朱", "status", "dead")
        w.graph.set("龚光杰", "status", "dead")
        self.assertEqual(lod.verdict(w, major, 2)[0], "rewrite")                     # 分量重：交场外编剧改写
        self.assertEqual(lod.verdict(w, minor, 1)[0], "rewrite")                     # 近处：改写
        self.assertEqual(lod.verdict(w, minor, 2)[0], "skip")                        # 远方小事：作罢
        w.graph.link("乔峰", "player", "随行")
        self.assertEqual(lod.verdict(w, major, 2)[0], "skip")                        # 纠缠者的场外之事：作罢

    def test_a_lapsed_or_blocked_event_sets_its_people_adrift(self):
        w = self.w
        ev = canon(w, "无量剑第四场比剑")
        lod.settle(w, ev, {"happens": False}, "director")                            # 被主角拦下
        self.assertTrue(all(w.graph.get(a, "adrift") for a in ev["actors"] if w.graph.get(a, "status") != "dead"))

    def test_the_near_director_changing_an_aspiration_changes_the_line(self):
        w = self.w
        w.apply([{"做": "所求", "谁": "左子穆", "为": "退隐江湖"}], "director")         # 眼前的剧情改了他的志向
        self.assertEqual((w.graph.get("左子穆", "agenda"), w.graph.get("左子穆", "adrift")), ("退隐江湖", True))
        w.apply([{"op": "set", "id": "南海鳄神", "key": "agenda", "value": "收徒"}], "derived", {"南海鳄神"})
        self.assertFalse(w.graph.get("南海鳄神", "adrift"))                          # 场外编剧自己写的新志向：已是下文，不算又变了


# ============================================================
#  剧情推力：谁该有下一步
# ============================================================
class DriveTest(_World):
    def test_drive_follows_the_data_then_the_temper(self):
        w = self.w
        self.assertGreaterEqual(plot.drive(w, "段延庆"), 4)                          # 夺回大理皇位：不甘现状
        w.graph.set("段延庆", "drive", 1)
        self.assertEqual(plot.drive(w, "段延庆"), 1)                                 # 抽取的数据写了就照数据
        w.graph.nodes["钟灵"].update(persona="淡泊无争", agenda=None)
        self.assertLess(plot.drive(w, "钟灵"), plot.drive(w, "钟万仇"))

    def test_who_gets_a_next_step(self):
        w = self.w
        w.graph.set("秦红棉", "drive", 3)                                            # 数据(22)写她不甘现状(四)：这里验进取者近处才写
        self.assertIn("秦红棉", plot.idle(w, 10))                                    # 原著已尽、推力三，就在近处：主角随时撞得上
        w.player.set("location", "少林寺")
        self.assertNotIn("秦红棉", plot.idle(w, 10))                                 # 远在别处：不必写
        w.graph.nodes["秦红棉"]["adrift"] = True
        self.assertIn("秦红棉", plot.idle(w, 10))                                    # 原著线变了：写
        w.graph.set("钟万仇", "drive", 5)
        self.assertEqual(plot.idle(w, 10)[0], "秦红棉")                               # 原著线变了的先写
        self.assertNotIn("钟万仇", plot.idle(w, 10))                                 # v14 远在七日路程之外、原著线没变：不写(传闻要月余才到)
        w.player.set("location", "无量山")
        self.assertIn("钟万仇", plot.idle(w, 10))                                    # 野心炽烈：原著尽了也闲不住
        w.graph.set("钟万仇", "drive", 0)
        self.assertNotIn("钟万仇", plot.idle(w, 10))                                 # 无欲无求：不写

    def test_cadence_and_busy_people(self):
        w = self.w
        w.graph.nodes["秦红棉"]["adrift"] = True
        w.plotted["秦红棉"] = w.clock.day
        self.assertNotIn("秦红棉", plot.idle(w, 10))                                 # 刚写过：按推力隔几日
        w.plotted["秦红棉"] = w.clock.day - plot.CADENCE[plot.drive(w, "秦红棉")]
        self.assertIn("秦红棉", plot.idle(w, 10))
        w.canon.append({"id": "衍·测·1", "order": 0.5, "day": w.clock.day + 3, "where": "万劫谷", "weight": 1, "actors": ["秦红棉"],
                        "requires": [], "effects": [], "summary": "测", "derived": True, "made": w.clock.day})
        self.assertNotIn("秦红棉", plot.idle(w, 10))                                 # 七日之内另有安排
        w.canon.pop()
        bond.event(w, "秦红棉", 1.5, "你替她挡过一箭")
        w.graph.set("秦红棉", "location", "剑湖宫")
        self.assertIn("秦红棉", plot.idle(w, 10))                                    # v13 与主角有过交集不等于等着主角：不再冻住她
        situation.enlist(w, ["秦红棉"])
        self.assertNotIn("秦红棉", plot.idle(w, 10))                                 # 站到了主角跟前：归近处导演


# ============================================================
#  规则审：合不合天龙世界的物理与规矩
# ============================================================
class RuleTest(_World):
    def test_a_sound_plan_lands_with_its_people_placed(self):
        plan, problems = self.vet(event(effects=[{"op": "set", "id": "秦红棉", "key": "intent", "value": "找钟万仇算账"}]))
        self.assertEqual(problems, [])
        ev = plan["events"][0]
        self.assertEqual(ev["day"], self.w.clock.day + 2)
        self.assertIn({"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷"}, ev["effects"])  # 与原著同一格式：先把人摆到事发之地

    def test_names_must_exist(self):
        self.rejects("世上没有「桃花岛」", event(where="桃花岛"))
        self.rejects("世上没有「黄蓉」", event(actors=["秦红棉", "黄蓉"]))
        self.rejects("不写主角", event(actors=["秦红棉", "主角"]))
        self.w.graph.set("木婉清", "status", "dead")
        self.rejects("木婉清已死", event(actors=["秦红棉", "木婉清"]))

    def test_time_and_roads(self):
        self.rejects("要", event(day=0, where="大理城"))                               # 日子不够
        self.w.graph.set("秦红棉", "location", "长春谷外山岭")
        self.rejects("无路可通", event(day=30, where="不老长春谷"))                    # 不通之路拦所有人
        self.w.graph.set("秦红棉", "location", "木婉清居所")
        self.rejects("远行另写一桩事", event(effects=[{"op": "set", "id": "秦红棉", "key": "location", "value": "大理城"}]))
        a, b = event(day=2), event(day=2, where="大理城", summary="秦红棉入大理城")
        self.rejects("只有0日", a, b)                                                 # 同一人不分身：先后两桩按先后算路程

    def test_people_who_belong_elsewhere(self):
        w = self.w
        self.rejects("主角身边", event(where="剑湖宫·练武厅", day=5, actors=["秦红棉", "钟灵"]))
        w.graph.link("木婉清", "player", "随行")
        self.rejects("主角身边或与主角同行", event(actors=["秦红棉", "木婉清"]))
        w.graph.unlink("木婉清", "player", "随行")
        w.graph.set("木婉清", "location", "无量山")
        bond.event(w, "木婉清", 1.5, "你救过她")
        plan, problems = self.vet(event(day=3, where="万劫谷", actors=["秦红棉", "木婉清"]))
        self.assertFalse([p for p in problems if "等着主角的故事" in p], problems)        # v13 救过的人、认得主角的人不再被冻住：只要不在主角身边、不是同行者
        plan, _ = self.vet(event(day=3, where="剑湖宫", actors=["秦红棉", "木婉清"], summary="秦红棉与木婉清找上剑湖宫"))
        self.assertIsNotNone(plan)                                                   # 写她来到主角跟前另当别论：到时交近处导演当面演出
        w.player.push("threads", "护送木婉清")
        situation.track(w, "护送木婉清", ["木婉清"], [])
        self.rejects("主角身边或与主角同行", event(day=3, where="万劫谷", actors=["秦红棉", "木婉清"]))   # 未了之事所系的人，才算等着主角的故事
        self.rejects("七日之内照原著", event(day=1, actors=["秦红棉", "司空玄"], where="无量山"))

    def test_martial_odds(self):
        hit = lambda kind, how="": event(how=how, actors=["秦红棉", "钟万仇"], summary="秦红棉在万劫谷与钟万仇交手",
                                         effects=[{"op": "set", "id": "钟万仇", "key": "status", "value": kind, "by": "秦红棉"}])
        self.vet(hit("wounded"))
        self.assertEqual(self.vet(hit("wounded"))[1], [])                            # 四十四对四十五：伤得了
        self.w.graph.set("钟万仇", "power", 60)
        self.rejects("杀不了他", hit("dead"))                                         # 武功高低定胜负
        self.assertEqual(self.vet(hit("dead", "暗中下毒"))[1], [])                    # 以弱胜强须有手段
        self.w.graph.set("钟万仇", "power", 90)
        self.rejects("手段也救不了这么悬殊", hit("dead", "暗中下毒"))
        self.rejects("杀不了他", event(actors=["秦红棉", "钟万仇"], effects=[{"op": "set", "id": "钟万仇", "key": "status", "value": "dead"}]))  # 只有一个旁人：不写 by 也知道是谁出的手
        self.rejects("写明 by", event(actors=["秦红棉", "木婉清", "钟万仇"], effects=[{"op": "set", "id": "钟万仇", "key": "status", "value": "dead"}]))
        self.assertEqual(self.vet(event(actors=["秦红棉", "钟万仇"], how="积郁成病", summary="钟万仇在万劫谷病故",
                                        effects=[{"op": "set", "id": "钟万仇", "key": "status", "value": "dead"}]))[1], [])  # 病故不必有人出手

    def test_martial_arts_need_a_source(self):
        teach = lambda art: event(actors=["秦红棉", "木婉清"], where="木婉清居所", day=0, summary="秦红棉传艺",
                                  effects=[{"op": "push", "id": "木婉清", "key": "skills", "value": art}])
        self.assertEqual(self.vet(teach("五罗轻烟掌"))[1], [])                        # 会它的人在侧
        self.rejects("无从学起", teach("六脉神剑"))
        self.rejects("凭空涨", event(effects=[{"op": "add", "id": "秦红棉", "key": "power", "value": 20}]))

    def test_things(self):
        w = self.w
        w.graph.nodes["无量玉璧"] = {"type": "item", "kind": "宝物", "holder": "钟万仇", "location": None}  # 一件在旁人手里的东西
        take = event(summary="秦红棉在万劫谷取宝", effects=[{"op": "set", "id": "无量玉璧", "key": "holder", "value": "秦红棉"}])
        self.rejects("钟万仇得在这桩事里", take)
        w.graph.nodes["无量玉璧"].update(holder="player")
        self.rejects("在主角手里", take)
        w.graph.nodes["无量玉璧"].update(holder=None, location="万劫谷", hidden=True)
        self.rejects("只有知情者找得到", take)
        w.graph.nodes["无量玉璧"]["known"] = ["秦红棉"]
        self.assertEqual(self.vet(take)[1], [])                                      # 知情者找得到

    def test_geography_does_not_move(self):
        self.rejects("地理不动", event(effects=[{"op": "set", "id": "大理城", "key": "state", "value": "化为焦土"}]))
        self.assertEqual(self.vet(event(summary="秦红棉一把火烧了万劫谷的谷口", effects=[{"op": "set", "id": "万劫谷", "key": "state", "value": "谷口焦黑"}]))[1], [])

    def test_the_words_must_match_and_not_spoil(self):
        self.rejects("effects 里却没有", event(summary="秦红棉在万劫谷杀了钟万仇"))         # 说了死人，后果里却没有
        self.assertEqual(self.vet(event(summary="秦红棉心事重重，赶赴万劫谷探望钟万仇"))[1], [])  # 去的是承上的秦红棉，钟万仇是去看的人(真模型实测抓到的误判)
        self.rejects("说破了", event(summary="秦红棉在万劫谷逢人便说木婉清是她亲生的女儿"))
        plan, _ = self.vet(event(actors=["秦红棉", "木婉清"], where="木婉清居所", day=0, summary="秦红棉对木婉清说破：你是我亲生的女儿",
                                 effects=[{"op": "reveal", "src": "秦红棉", "rel": "生母", "dst": "木婉清"}]))
        self.assertIsNotNone(plan)                                                   # 这桩事自己揭开的隐情：随传闻一同抵达，不算说破

    def test_a_death_the_plot_itself_causes_is_not_a_spoiler(self):
        w = self.w
        w.graph.set("容子矩", "location", "万劫谷")
        freed(w, "容子矩")
        w.canon.append({"id": "测·容子矩之死", "order": 999, "day": w.clock.day + 40, "where": "无量山", "weight": 1, "actors": ["容子矩"],
                        "requires": [], "summary": "测", "effects": [{"op": "set", "id": "容子矩", "key": "status", "value": "dead"}]})
        kill = event(actors=["秦红棉", "容子矩"], summary="秦红棉在万劫谷杀了容子矩",
                     effects=[{"op": "set", "id": "容子矩", "key": "status", "value": "dead", "by": "秦红棉"}])
        plan, problems = self.vet(kill)
        self.assertEqual(problems, [])                                               # 原著日后要他死；这桩事先杀了他，是新的事实，不是剧透
        self.assertTrue(any("测" in r for r in plan["ripples"]))                     # 会因此改变的原著：列给审稿人，不拦

    def test_a_line_may_break_its_own_canon(self):
        w = self.w
        meet = event(day=1, actors=["秦红棉", "司空玄"], where="无量山", summary="秦红棉在无量山截住司空玄")
        self.rejects("主角跟前", meet, drops=["神农帮留钟灵下毒逼援"])               # 钟灵、段誉正在主角身边：那一桩归近处导演
        w.player.set("location", "大理城")
        self.rejects("七日之内照原著", meet)
        follow = canon(w, "神农帮留钟灵下毒逼援")
        plan, problems = self.vet(meet, drops=[follow["id"]])
        self.assertEqual(problems, [])                                               # 原著线可以断：明说这条线一走，那一桩便不再发生
        self.assertEqual(plan["drops"], [follow["id"]])
        self.assertIn("原著里不再发生", "".join(plot.render(w, plan)))
        self.rejects("相关者不在这条线里", event(), drops=["乔峰携阿朱赴聚贤庄"])    # 只能断自己这几人的原著
        self.rejects("原著里没有尚未演的", event(), drops=["桃花岛论剑"])
        plot.adopt(w, plot.sequel(w, "秦红棉"), plan)
        self.assertIn(follow["id"], w.done)
        self.assertTrue(w.graph.get("司空玄", "adrift") is None and w.graph.get("钟灵", "adrift"))  # 断掉的那一桩里别的人：原著线也变了(写进新线的人已有下文)

    def test_a_fulfilled_wish_needs_a_new_aspiration(self):
        w = self.w
        w.graph.set("秦红棉", "agenda", "杀了刀白凤")
        w.apply([{"op": "set", "id": "刀白凤", "key": "status", "value": "dead"}], "canon")
        self.rejects("写明他的新志向", event())
        plan, _ = self.vet(event(summary="秦红棉在万劫谷隐居", effects=[{"op": "set", "id": "秦红棉", "key": "agenda", "value": "隐居万劫谷"}]))
        self.assertIsNotNone(plan)


# ============================================================
#  落地与结算
# ============================================================
class AdoptTest(_World):
    def adopt(self, *events, who="秦红棉"):
        task = plot.sequel(self.w, who)
        plan, problems = plot.vet(self.w, task, {"line": "寻仇", "goal": "找钟万仇算账", "events": list(events)})
        self.assertEqual(problems, [])
        return plot.adopt(self.w, task, plan)

    def test_a_plan_joins_the_schedule_like_the_canon(self):
        w = self.w
        w.graph.nodes["秦红棉"]["adrift"] = True
        ids = self.adopt(event(day=2), event(day=4, summary="秦红棉在万劫谷候到入夜"))
        evs = [canon(w, i) for i in ids]
        self.assertEqual([e["day"] for e in evs], [w.clock.day + 2, w.clock.day + 4])
        orders = [e["order"] for e in w.canon]
        self.assertEqual(orders, sorted(orders))                                      # 日程仍按 order 走
        days = [e["day"] for e in w.canon if e["id"] not in w.done]
        self.assertEqual(days, sorted(days))                                          # 日子仍随 order 单调
        self.assertEqual(w.lines["寻仇"]["events"], ids)
        self.assertEqual((w.plotted["秦红棉"], w.graph.get("秦红棉", "adrift")), (w.clock.day, None))
        v = World.from_dump(copy.deepcopy(w.dump()))
        self.assertEqual((v.lines, v.plotted), (w.lines, w.plotted))                  # 存档

    def test_due_plots_settle_by_their_premises(self):
        w = self.w
        w.player.set("location", "大理城")
        [eid] = self.adopt(event(day=2))
        w.advance(2 * PER_DAY)
        offstage, staged = lod.split_due(w)
        ev = canon(w, eid)
        self.assertIn(ev, [e for e, _ in offstage])
        self.assertEqual(lod.verdict(w, ev, 2)[0], "canon")
        told = lod.settle(w, ev, ev, plot.origin(ev))
        self.assertEqual((told["summary"], told["origin"]), ("秦红棉往万劫谷寻仇", "derived"))
        self.assertEqual((w.graph.get("秦红棉", "location"), w.graph.get("秦红棉", "strayed")), ("万劫谷", ev["day"]))

    def test_someone_moved_away_meanwhile_misses_the_plot(self):
        w = self.w
        w.player.set("location", "大理城")
        [eid] = self.adopt(event(day=2))
        w.graph.set("秦红棉", "location", "少林寺")                                      # 排定之后被别处挪去了远方
        w.advance(2 * PER_DAY)
        self.assertIn("秦红棉身在少林寺，赶不到万劫谷", lod.dirt(w, canon(w, eid)))
        self.assertEqual(lod.verdict(w, canon(w, eid), 2)[0], "skip")

    def test_people_carried_off_by_a_plot_must_make_it_back_for_the_canon(self):
        w = World.create("测")
        ev = canon(w, "南海鳄神扣木婉清待徒")
        self.assertTrue(lod.intact(w, ev))
        w.graph.set("南海鳄神", "location", "少林寺")                                  # 远在少林寺，原著却要他九日后在无量山
        self.assertTrue(lod.intact(w, ev))                                             # 原著自己的日程压缩旅途：照样演
        lod.stray(w, {"day": w.clock.day}, [{"op": "set", "id": "南海鳄神", "key": "location", "value": "少林寺"}])
        self.assertFalse(lod.intact(w, ev))                                            # 是场外剧情把他带去的：得赶得回来，赶不回来原著线就断了
        self.assertIn("南海鳄神身在少林寺，赶不到无量山·山崖", lod.dirt(w, ev))
        w.apply([{"op": "set", "id": "南海鳄神", "key": "location", "value": ev["where"]}], "canon")
        self.assertIsNone(w.graph.get("南海鳄神", "strayed"))                          # 原著把他摆回轨道上

    def test_a_plot_that_reaches_the_player_is_played_by_the_near_director(self):
        w = self.w
        w.done.extend(e["id"] for e in w.canon if e["day"] <= w.clock.day + 1)        # 开局此地的原著已了
        [eid] = self.adopt(event(day=1, where="剑湖宫", summary="秦红棉找上剑湖宫"))
        w.advance(PER_DAY)
        offstage, staged = lod.split_due(w)
        self.assertEqual(staged["id"], eid)                                            # 写到主角跟前：交近处导演当面演出
        text = prompts.render_backstage({**rag.backstage(w, stage=staged, upcoming=[]), "brief": ""})
        self.assertIn("【场外剧情此刻", text)

    def test_a_canon_that_only_waits_on_travel_is_postponed(self):
        w = self.w
        ev = {"id": "测·会面", "order": 0.5, "day": w.clock.day, "where": "大理城", "weight": 2, "public": True, "actors": ["秦红棉"],
              "requires": [["秦红棉", "location", "大理城"]], "summary": "秦红棉入大理城", "effects": []}
        w.canon.insert(0, ev)
        self.assertTrue(plot.postpone(w, ev))                                          # 先贴原著：等人赶到再演
        self.assertGreater(ev["day"], w.clock.day)
        self.assertTrue(plot.postpone(w, ev))
        self.assertFalse(plot.postpone(w, ev))                                         # 至多延后两回


# ============================================================
#  剧透、来人
# ============================================================
class SpoilerTest(_World):
    """衍生事件的说法会变成传闻：说破隐情、把尚未发生的原著说成已成之事，到期结算时也只记核实过的后果。"""

    def settle(self, summary):
        move = {"op": "set", "id": "秦红棉", "key": "location", "value": "万劫谷·谷外树林"}
        ev = {"id": "衍·测·1", "order": 0.5, "day": self.w.clock.day, "where": "木婉清居所", "weight": 1, "public": True,
              "actors": ["秦红棉"], "requires": [], "effects": [move], "summary": summary, "derived": True, "made": self.w.clock.day}
        told = lod.settle(self.w, ev, ev, "derived")
        return told and told["summary"]

    def test_a_secret_is_not_spread_as_news(self):
        self.assertEqual(self.settle("秦红棉往万劫谷·谷外树林去，逢人便说木婉清是她亲生的女儿"), "秦红棉前往万劫谷·谷外树林")

    def test_the_future_is_not_spread_as_news(self):
        self.assertEqual(self.settle("秦红棉往万劫谷·谷外树林去，一路听说容子矩已经死了"), "秦红棉前往万劫谷·谷外树林")

    def test_plain_news_is_kept(self):
        self.assertEqual(self.settle("秦红棉穿林往万劫谷·谷外树林去"), "秦红棉穿林往万劫谷·谷外树林去")

    def test_the_sieve(self):
        self.assertTrue(adjudicate.spoilers(self.w, "段延庆才是段誉的生父"))
        self.assertFalse(adjudicate.spoilers(self.w, "段延庆才是段誉的生父", {("段延庆", "生父", "段誉")}))  # 这桩事自己揭开的
        self.assertFalse(adjudicate.spoilers(self.w, "段誉赶往无量后山求药"))


class ArrivalTest(unittest.TestCase):
    """原著要把人送到主角这里：交近处导演演出来人，远处的结算不把人悄悄塞到他跟前。"""

    def setUp(self):
        self.w = World.create("测")
        self.w.turn = {}
        self.w.done.extend(e["id"] for e in self.w.canon if e["day"] <= self.w.clock.day)

    def due(self, dest):
        w = self.w
        ev = {"id": "测·来人", "order": 0, "day": w.clock.day, "where": "大理城", "weight": 1, "public": True,
              "actors": ["秦红棉"], "requires": [], "summary": "秦红棉动身寻人",
              "effects": [{"op": "set", "id": "秦红棉", "key": "location", "value": dest}]}
        w.canon.insert(0, ev)
        return ev

    def test_a_canon_arrival_is_staged_by_the_near_director(self):
        ev = self.due(self.w.here)
        offstage, staged = lod.split_due(self.w)
        self.assertIs(staged, ev)
        self.assertEqual(offstage, [])
        gm = rag.backstage(self.w, stage=staged, upcoming=[])
        self.assertEqual(gm["stage"]["coming"], ["秦红棉"])
        self.assertIn("秦红棉要来到主角这里", prompts.render_backstage({**gm, "brief": ""}))

    def test_a_canon_move_elsewhere_stays_offstage(self):
        ev = self.due("万劫谷·谷外树林")
        offstage, staged = lod.split_due(self.w)
        self.assertIsNone(staged)
        self.assertIn(ev, [e for e, _ in offstage])

    def test_offstage_plots_cannot_reach_into_the_players_room(self):
        w = self.w
        _, rejected = w.apply([{"op": "arrive", "id": "秦红棉"}], "derived", {"秦红棉"})
        self.assertIn("场外叫不来人", rejected[0][1])
        _, rejected = w.apply([{"op": "set", "id": "钟灵", "key": "status", "value": "dead"}], "derived", {"钟灵"})
        self.assertIn("主角身边", rejected[0][1])


# ============================================================
#  提示词与整形
# ============================================================
class PromptTest(_World):
    def test_the_prompts_spell_out_the_same_rules(self):
        w = self.w
        w.graph.nodes["秦红棉"]["adrift"] = True
        b = plot.brief(w, plot.sequel(w, "秦红棉"))
        system, user = prompts.plotter([b], {b["key"]: ["秦红棉身在木婉清居所，到大理城要3日，只有0日"]})
        for phrase in ("场外编剧", "原著线可以断", "剧情推力", "六成之力", "以弱胜强", "暗藏之物只有知情者找得到", "七日之内照原著要上场的人", "不提主角"):
            self.assertIn(phrase, system)
        for phrase in ("续写·秦红棉", "剧情推力", "上一稿退回的缘由", "走得到的地方"):
            self.assertIn(phrase, user)
        system, user = prompts.reviewer([{"key": b["key"], "brief": b, "lines": ["剧情线「测」：测"]}])
        self.assertIn("审稿", system)
        self.assertNotIn("账房", system)                                               # 桩模型按关键词分派：别串台
        self.assertIn("续写：秦红棉", user)

    def test_the_agents_only_shape(self):
        class Echo:
            strict = False

            def __init__(self, reply):
                self.reply = reply

            def json(self, system, user, max_tokens=0):
                return copy.deepcopy(self.reply)

        w = self.w
        briefs = [plot.brief(w, plot.rewrite(w, canon(w, "龚光杰掌掴段誉"), ["龚光杰已死"])), plot.brief(w, plot.sequel(w, "秦红棉"))]
        self.assertEqual(agents.plot(None, briefs), {})                                # 离线：不写
        drafts = agents.plot(Echo({"plans": [{"events": [1]}, {"key": "改写·龚光杰掌掴段誉", "events": [2]}]}), briefs)
        self.assertEqual(drafts, {"改写·龚光杰掌掴段誉": {"events": [1]}})              # 写了 key 就认 key，没写按次序(第一份没写 key 即第一份任务)
        items = [{"key": k, "brief": briefs[1], "lines": []} for k in ("a", "b", "c", "d")]
        r = agents.review(Echo({"reviews": [{"key": "a", "verdict": "通过"}, {"key": "b", "verdict": "不过"},
                                            {"key": "c", "verdict": "再斟酌"}, {"key": "d", "verdict": "改", "why": "动机不足"}]}), items)
        self.assertEqual({k: v["verdict"] for k, v in r.items()}, {"a": "过", "b": "否", "c": "改", "d": "改"})
        self.assertEqual(agents.review(None, items), {})                                # 审稿失声：都不过


if __name__ == "__main__":
    unittest.main()
