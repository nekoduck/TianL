"""
[INPUT]: 依赖 story/scene（场）、story/stakes（时限）、story/arc（主角线）、story/setups（系统伏笔），world/situation 的 around，World 门面的 graph / player（鸭子类型）
[OUTPUT]: 对外提供 compose()（本回合的场记：几行字 + 主干的来源）、allow_pull()（轮转：原著连占三场主干，就不再提前拉原著）、remember()（记下本回合主干的来源）、SPINES
[POS]: story 层的戏剧调度器与场记——给导演的焦点，而不是一堆资料：确定性地选出本回合的主干，优先级
       此地上演的原著 > 到期的时限 > 该回收的伏笔 > 主角线 > 在场人物的图谋 > 顺着主角的举动推进本场之问；
       轮转：最近 SPINES 回合的主干都来自原著，就不再提前拉原著(到期的照演)，让主角线有机会作主干——「段誉占四成」由此回落。
       场记是导演上下文的第一节，三到七行：场况与问题、主干、已试路数、最急的时限、主角线、伏笔、光阴与收场提示
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from ..world import situation
from . import arc, scene, setups, stakes

SPINES = 3


def allow_pull(world) -> bool:
    recent = world.player["spines"][-SPINES:]
    return not (len(recent) == SPINES and all(s == "canon" for s in recent))


def remember(world, kind: str):
    world.player.set("spines", (world.player["spines"] + [kind])[-SPINES * 2:])


def _agenda(world) -> str:
    g = world.graph
    for p in sorted(situation.around(world)):
        if g.get(p, "agenda") and g.get(p, "status") != "dead":
            return f"{p}的图谋：{g.get(p, 'agenda')}"
    return ""


def compose(world, staged: dict | None, due: list[dict], scale: str | None = None) -> dict:
    """本回合的场记 {text, spine}。due：本回合到期的时限(stakes.due 已除去)；scale：玩家上回合所选之举的尺度。"""
    sc = world.player["scene"]
    hurry = stakes.urgent(world)
    head = f"第{sc['id']}场·{sc['state']}（第{sc['turns'] + 1}回合）｜问：{sc['ask'] or '本回合由主角此举定下'}"
    if hurry:
        head += f"｜赌注：{hurry[0]['what']}，{hurry[1]}"
    lines = [head]
    seed, back, plot = setups.plant(world), setups.payoff(world, staged), arc.line(world)
    if staged:
        spine, trunk = "canon", f"原著「{staged['summary']}」在此上演（见后台）"
    elif due:
        spine, trunk = "clock", f"时限已到——{'；'.join(c['what'] for c in due)}：本回合让它有个结果"
    elif seed:
        spine, trunk = "setup", seed
        seed = ""
    elif plot and (world.player["spines"][-1:] != ["arc"] or not _agenda(world)):  # 主角线与在场之人的图谋轮流作主干
        spine, trunk = "arc", plot
        plot = ""
    elif _agenda(world):
        spine, trunk = "agenda", _agenda(world)
    else:
        spine, trunk = "deed", "顺着主角的举动推进本场之问"
    lines.append(f"主干：{trunk}")
    if due and spine != "clock":  # 原著占了主干，到期的时限也不能悄悄过去
        lines.append(f"时限已到：{'；'.join(c['what'] for c in due)}——在本回合交代它的结果")
    if back:
        lines.append(back)
    if sc["tried"] and sc["state"] != "开":
        lines.append(f"已试路数：{'、'.join(sc['tried'])}｜本回合换一种推进，不要原样再来")
    for line in (seed, plot):
        if line:
            lines.append(line)
    if scale == "此后":
        lines.append("主角上回合选的是一件持续之事：本回合略写那段光阴，pace 取那件事实际耗时，写到它有了结果或被打断")
    if scene.over(sc):
        lines.append(f"这一场已演{sc['turns']}回合：本回合必须有个结果（scene.state 写 合 或 断）")
    lines.append("光阴：pace 照拍里的事如实取；本场若在本回合合上且无人相逼，用 cut 跳到下一处有戏的时刻"
                 "（可写一段长度，或 {\"until\":\"入夜/天明/正午/某个时限\"}）")
    return {"text": "\n".join(lines), "spine": spine, "tension": scene.tension(sc, bool(hurry and hurry[1] == "迫在眉睫"))}
