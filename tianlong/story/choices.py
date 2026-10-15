"""
[INPUT]: 依赖 story/stakes（时限）、story/timing 的 study_minutes 与 world/clock 的 span（选项上写的耗时与规则主张同一张表）、world/growth 的 studiable / progress（研习对象与进度）、world/access 的 exits（出路与日程）、world/situation 的 imperiled / captors / quests、
         world/body 的 severity，world/perspective 的 handle（v12 C 槽的叫法照主角眼中的）；World 门面的 player / graph（鸭子类型）
[OUTPUT]: 对外提供 doings()（v12 眼前之人的眼下之事：C 槽从看得见的东西里找机会）、slots()（给编剧的三个槽位：此刻 / 此后 / 机缘，各写明它要回答什么与可用的素材；v12 收尾时仍悬着话的人平常写进 A 槽、险境写进 B 槽：在举动里顺带回应他）、later()（此后槽的兜底项 [(文字, 对象)]，供 menu.check 补位）、
          SCALES、peril()
[POS]: story 层的选项编排——选项从「正文的附录」变成「先定槽位、再让编剧措辞」：
       A 此刻：用还没试过的路数推进本场之问；B 此后：一件持续之事或一次过场(赶路、研习、养伤、等人、找人)，写出代价；C 机缘：一个两难或机会(时限冲突、眼前之人眼下之事里的破绽)。
       v12：C 槽不引用图谋(编剧看不见 agenda)，只列看得见的眼下之事与最急的时限；引擎交编剧前整段槽位再过一遍视角掩码；
       危局(world/pacing.danger)只有一个口径：危局里没有此后，三槽改为 A 刚/奇、B 智/言、C 势/变；要找的人还没寻到，A 槽续线、B 槽不拿远路顶替
       槽位只规定每项回答什么，不规定措辞；险境里 B 槽改为脱身一类的此刻之举。编剧在每项后写「｜尺度：此刻/此后/机缘」，
       引擎记下玩家所选之举的尺度：选了此后，下一回合的场记要求略写、时长按那件事的规则结算——选项与时间从此互相咬合
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from ..world import access, body, growth, pacing, perspective, situation
from ..world.clock import span
from . import stakes, timing

SCALES = ("此刻", "此后", "机缘")


def peril(world, danger=None) -> bool:
    """处在危局里(v12 与 world/pacing.danger 同一口径：被围、受制、命悬一线、同伴受制、有人拦阻追杀主角)；danger 由引擎算好传入，缺省现算。"""
    return bool(pacing.danger(world) if danger is None else danger)


def later(world, danger=None) -> list[tuple[str, list[str]]]:
    """此后槽的素材(也是兜底项)：续行、出路(带日程)、研习手边的秘籍、带伤歇息、去推进未了之事。危局里没有此后。"""
    if peril(world, danger):
        return []
    me, out = world.player, []
    if me.get("en_route"):
        out.append((f"继续赶往{me['en_route']['to']}（余{me['en_route']['left']}日）", [me["en_route"]["to"]]))
    for src in [b for b in growth.studiable(world) if world.graph.kind(b) == "item" and growth.next_art(world, b)][:1]:  # 手边的秘籍；求教要对人开口，是此刻之举
        art = growth.next_art(world, src)  # v13 账按武学记：点名这回练哪一门，练到顶的不再给
        out.append((f"静心研习{art}（约{span(timing.study_minutes(world, src, art))}）", [src, art]))  # 耗时与规则主张同一张表
    if body.severity(world) or me["hp"] < me["max_hp"] * 0.8:
        out.append((f"寻个僻静处歇息养伤（{span(body.REST)}）", []))
    for e in access.exits(world):
        if e["days"] >= 1 and not e["back"]:
            out.append((f"{e['way']}（约{e['days']}日）", [e["name"]]))
            break
    return out


def slots(world, addressed=(), danger=None, seek=()) -> list[str]:
    """给编剧的三个槽位说明(每行一个)。addressed：收尾时仍悬着话的人(叫法，v12)——平常写进 A 槽、危局写进 B 槽：在举动里顺带回应他，兜底便少用。
    danger(v12 pacing.danger，引擎用成文前的拍与世界算好传入)：危局的三槽——A 刚/奇(借景物器物地势拼死一搏或突围)、B 智/言(对围困者周旋、诈称、求援)、
    C 势/变(眼前之人的眼下之事里的变数)；平常照旧 A 此刻、B 此后、C 机缘。"""
    danger = pacing.danger(world) if danger is None else danger
    sc, hurry = world.player["scene"] or {}, stakes.urgent(world)
    reply = f"；{'、'.join(addressed)}刚对你说了话：在举动里顺带回应他" if addressed else ""
    tried = f"（已试：{'、'.join(sc['tried'][-3:])}）" if sc.get("tried") else ""
    hooks = [f"时限「{hurry[0]['what']}」{hurry[1]}"] if hurry else []
    hooks += doings(world)
    if danger:
        a = f"A 此刻·刚/奇：危局（{'；'.join(danger)}）——借此处的景物、器物或地势拼死一搏，或设法突围脱身{tried}"
        b = "B 此刻·智/言：对围困、逼迫你的人周旋、诈称、求援" + reply
        c = "C 机缘·势/变：眼前局势里的变数" + (f"（可从{'；'.join(hooks)}里找）" if hooks else "——有人心思松动、有人另有所图，就是破局的缝")
        return [a, b, c]
    lost = [perspective.handle(world, p) for p in seek if p not in situation.around(world) and world.graph.get(p, "status") != "dead"]
    hunt = "".join(f"；你此行要找的{h}尚未寻到：可写继续循迹寻他，对象写{h}" for h in lost)  # v12 续线：寻人还没着落，A 槽接着找
    a = f"A 此刻：用一种还没试过的路数(力、智、情、术、退)推进本场之问「{sc.get('ask') or '眼前之事'}」{tried}{reply}{hunt}"
    stuff = [t for t, ids in later(world, danger) if not (lost and any(world.graph.kind(i) == "location" for i in ids))]  # 寻人未果：B 槽不拿远路顶替
    b = "B 此后：一件持续之事或一次过场(赶路、研习、养伤、等人、去找某人)，写出代价或耗时" + (f"；可用：{'、'.join(stuff)}" if stuff else "")
    c = "C 机缘：一个两难或一个机会" + (f"（可从{'；'.join(hooks)}里找）" if hooks else "；没有时，换一种与 A 迥异的路数")
    return [a, b, c]


def doings(world, limit: int = 2) -> list[str]:
    """眼前之人此刻在做、要做的事(v12)：C 槽从看得见的东西里找机会——编剧看不见图谋(agenda)，只看得见眼下之事(intent)；
    叫法照主角眼中的(不识名只叫外貌)，引擎交编剧前整句再过一遍视角掩码。与主角有过交集的人在前。"""
    g = world.graph
    people = sorted((p for p in situation.around(world) if g.get(p, "intent")),
                    key=lambda p: (-len((g.get(p, "bond") or {}).get("log", [])), p))
    return [f"{perspective.handle(world, p)}眼下：{g.get(p, 'intent')}" for p in people[:limit]]
