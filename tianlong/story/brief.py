"""
[INPUT]: 依赖 story/scene（场）、story/stakes（时限）、story/arc（主角线）、story/setups（系统伏笔），world/situation 的 around，world/pacing 的 danger 与僵持阈值，world/crowd 的 seizure 与 world/adjudicate 的 names（v12 僵持押走的预告），World 门面的 graph / player（鸭子类型）
[OUTPUT]: 对外提供 compose()（本回合的场记：几行字 + 主干的来源 canon/clock/crisis(v12)/setup/scene/arc/agenda/deed）、allow_pull()（轮转：原著连占三场主干，就不再提前拉原著）、remember()（记下本回合主干的来源）、SPINES
[POS]: story 层的戏剧调度器与场记——给导演的焦点：确定性地选出本回合的主干，优先级(v5，与 L1 宪法同构)
       主角眼前上演的原著(v11 场外编剧写到主角跟前的那一桩同此) > 到期的时限 > 该埋的系统伏笔 > 续场的本场之问 > 开场时眼前之人的图谋(无人、或主角线刚有进展则是主角线) > 顺着主角的举动推进；
       一场之内主干不换题，换题看哪条线有了进展，不再按回合在主角线与图谋之间机械轮换；
       轮转：最近 SPINES 回合的主干都来自原著，就不再提前拉原著(到期的照演)，让主角线有机会作主干——「段誉占四成」由此回落。
       场记是导演上下文的第一节、「至少要处理什么」而非「只处理什么」：场况与问题、主干、开场时眼前有谁(抵达即遭遇)、
       在场各怀打算之人(不得当他们不在)、已试路数、最急的时限、主角线、伏笔、光阴与收场提示；
       v12 危局：危局里新开的场主干是眼前的危局(不落回某人的图谋)；危局僵持满 STALL_WARN 回合，写明本回合须有结构性的变化，
       并说明僵持下去系统的兜底(P1-7 _seizing：围困的人群照其所图把谁擒下押往哪里；满 STALL_SEIZE 即本回合；没写打算即教导演写)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from ..world import adjudicate, crowd, pacing, situation
from . import arc, scene, setups, stakes

SPINES = 3


def _seizing(world, stall: int) -> list[str]:
    """僵持下去系统会怎样兜底(v12 P1-7)：围困的人群写下了擒人的打算即说明它将擒谁押往哪里(满 STALL_SEIZE 即本回合)；
    没写而有人群围着主角，教导演写打算；危局里没有人群围攻(只是命悬一线)就不写。"""
    plan = crowd.seizure(world, adjudicate.names(world)[0])
    if plan:
        g = world.graph
        who = "主角" if plan["who"] == "player" else plan["who"]
        whither = f"押往{plan['to']}" if plan["to"] else "就地扣下"
        when = "本回合" if stall >= pacing.STALL_SEIZE else ""
        return [f"{when}再无结构性变化，{crowd.handle(g, plan['by'])}将照其所图把{who}擒下{whither}（系统落账）"]
    if crowd.besiegers(world):
        return ["这群人若要擒人，写 打算（谁=那一群，为=擒下某人押往某处）；再僵持下去系统照此落账"]
    return []


def allow_pull(world) -> bool:
    recent = world.player["spines"][-SPINES:]
    return not (len(recent) == SPINES and all(s == "canon" for s in recent))


def remember(world, kind: str):
    world.player.set("spines", (world.player["spines"] + [kind])[-SPINES * 2:])


def _schemers(world) -> list[str]:
    """眼前各怀打算的人：与主角有过交集的在前，再按名——不按字码挑一个了事。"""
    g = world.graph
    return sorted((p for p in situation.around(world) if g.get(p, "agenda") and g.get(p, "status") != "dead"),
                  key=lambda p: (-len((g.get(p, "bond") or {}).get("log", [])), p))


def compose(world, staged: dict | None, due: list[dict], scale: str | None = None) -> dict:
    """本回合的场记 {text, spine}。due：本回合到期的时限(stakes.due 已除去)；scale：玩家上回合所选之举的尺度。
    主干(v5)：此地原著 > 到期的时限 > 该埋的系统伏笔 > 续场的本场之问 > 开场时眼前之人的图谋(没有人、或主角线刚有了进展，就是主角线) > 顺着举动推进；
    一场之内主干不换题，换题看哪条线有了进展，不看上一回合用过谁。场记是「至少要处理什么」，不是「只处理什么」。"""
    me, sc = world.player, world.player["scene"]
    hurry = stakes.urgent(world)
    head = f"第{sc['id']}场·{sc['state']}（第{sc['turns'] + 1}回合）｜问：{sc['ask'] or '本回合由主角此举定下'}"
    if hurry:
        head += f"｜赌注：{hurry[0]['what']}，{hurry[1]}"
    lines = [head]
    seed, back, plot = setups.plant(world), setups.payoff(world, staged), arc.line(world)
    schemers = _schemers(world)
    fresh = bool(me["arc"]) and me["arc"].get("since", -1) >= me["turn"] - 1  # 主角线刚跨进一阶
    danger = pacing.danger(world)  # v12 危局的单一口径：开头还没有拍，读上一回合记下的逼迫
    if staged:
        spine, trunk = "canon", f"{'场外剧情' if staged.get('derived') else '原著'}「{staged['summary']}」在主角眼前上演（见后台）"  # v11 场外编剧写到主角跟前的一桩，同原著一样作主干
    elif due:
        spine, trunk = "clock", f"时限已到——{'；'.join(c['what'] for c in due)}：本回合让它有个结果"
    elif danger and sc["state"] == "开" and sc["turns"] == 0:  # 危局里新开的场(v12)：主干是眼前的危局，不落回某人的图谋
        spine, trunk = "crisis", f"眼前的危局（{'；'.join(danger)}）：这一场问的就是怎么脱出这一局"
    elif seed:
        spine, trunk = "setup", seed
        seed = ""
    elif sc["state"] == "转" and sc["ask"]:  # 续场：一场之内主干不换题
        spine, trunk = "scene", f"推进本场之问「{sc['ask']}」，直到它有个结果"
    elif plot and (fresh or not schemers):
        spine, trunk = "arc", plot
        plot = ""
    elif schemers:
        spine, trunk = "agenda", f"{schemers[0]}的图谋：{world.graph.get(schemers[0], 'agenda')}"
    else:
        spine, trunk = "deed", "顺着主角的举动推进本场之问"
    lines.append(f"主干：{trunk}")
    if sc["state"] == "开" and sc["turns"] == 0:  # 抵达即遭遇：开场时眼前有谁，先让他们与主角照面
        faces = sorted(situation.around(world))
        if faces:
            lines.append(f"此场开在{world.here}：眼前有{'、'.join(faces[:6])}{'等人' if len(faces) > 6 else ''}——先让主角看见他们")
    others = [f"{p}（{world.graph.get(p, 'agenda')}）" for p in schemers if p not in trunk][:3]
    if others:
        lines.append(f"在场各怀打算：{'；'.join(others)}——不必人人开口，但他们照自己的打算行事，不得当他们不在")
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
    if sc.get("stall", 0) >= pacing.STALL_WARN:  # 危局僵持(v12)：与场的上限并存——上限管一场演多久，僵持管危局里有没有动
        lines.append(f"危局已僵持{sc['stall']}回合：本回合须有结构性的变化——被擒押走、脱身、有人赶来解围、谈妥罢手（了断围攻）或有人倒下；"
                     "只扣气血、只改打算不算；上回合已说过的话不再原样重说")
        lines += _seizing(world, sc["stall"])
    lines.append("光阴：pace 照拍里的事如实取；无人相逼时，平静的光阴(等候、练功、歇宿、赶路)用 cut 跳过，不必逐刻细磨"
                 "（可写一段长度，或 {\"until\":\"入夜/天明/正午/某个时限\"}）；本场有了结果才写合")
    return {"text": "\n".join(lines), "spine": spine, "tension": scene.tension(sc, bool(hurry and hurry[1] == "迫在眉睫"))}
