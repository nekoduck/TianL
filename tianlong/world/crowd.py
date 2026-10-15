"""
[INPUT]: 依赖 world/situation 的 near / around / party（近旁、身边、同行）、world/stock 的 earn / materialize / pile / cn / say / MONEY_WORDS（银两与器物的流转）、
         world/body 的 fate（命运骰：偷取时身法相当看它）、world/bond 的 event（杀伤夺物记在这一门的人账上）；功力档读 world/profile(用时才引)；World 门面（graph / player / clock / turn）
[OUTPUT]: 对外提供 人群(v9 无名弟子)——GROUP / BESIEGE / FORCE / DISBAND / STEAL_ROLL、force()（功力 → 武力，指数尺度）、is_squad() / standing() / handle() / squads() / besiegers()、
          might()（整群之力：站着的人数 × 每人之力）、side()（一方之力：本人连同身边同行助阵者）、agility()（身法之档：功力之档与所会轻功的档取高）、
          forecast()（群战预裁：硬拼胜不胜、冲不冲得出去、偷不偷得到、败了失多少气血）、lines()（后台的群战预裁）、card()（视锥里的一群人）、
          kit()（一群人身上的东西；名字宽松认——去掉这一群的名目再看包含与末一字：佩剑、青钢剑都是长剑，长衫、衣服都是衣衫）、CLOTH、
          v10：active()（出没时段 since/until）、present()（与人同一口径的眼前）、recover()（打晕的两个时辰醒转归队、捡回东西）、escort() / relocate()（随首领、换地方即解围）、
          afar()（近处不在跟前的人群；v12 不列原著近事要用的人马）、reserved_lines()（v12 原著近事要用的人马：要在哪一桩里登场）、template() / split() / rejoin() / muster()（spawn 的一队人马：重组或补充，离远并回）、RECOVER / SUPPLY / DEFAULT_KIT、steal() / rob() / strike() / escape()（偷取、夺取、杀伤打晕、脱身——规则之事，不成即返回缘由）
[POS]: world 层的人群规则——原著里有名有姓的人是一个个节点；同门的无名之众(东西宗各十五名弟子)是一群：十五人一体，各有一点零钱、一件衣衫、一柄剑。
       对其中一人动手就是对整群动手(同仇敌忾)：
       夺物、杀伤、打晕须一方之力过整群——武力按功力取指数(档位本是对数尺度：每高九点功力，力气约翻一倍)，整群之力是站着的人数乘每人之力；
       力过整群一半才冲得出围攻(围攻是人群→某人的一条拘押之边，被围住便走不脱，只有脱身)；单独偷取不看力气看身法：身法高过他们一档即得手，相当看命运骰；
       倒下的人(杀死、打晕)身上的东西落在原地，人群照少；站着的不足三人即散——剧情里写作逃散，底层留个空壳(读档不复活)，世上不再有这一群。
       全是确定的规则，不调 LLM；导演开口前看得见预裁，只演出、不裁决
       is_squad 只认场景清单布下的人群：剧情临时立的一队人马(ephemeral)只活在叙事里；一群人只在近旁走动(effects 拦远行)
       v10 人群随剧情驱动底层：一群人远行、赶来(按道路里程)、随行、随首领(原著挪走带队之人)、按出没时段在场；打晕的人倒下满两个时辰醒转归队(纯规则)；
       剧情临时立的一队人马是既有人群的重组(从同门人群里分出几人，身上之物按人头带走，离远即并回)，附近没有同门人群或人数不够才按门下模板补一队纯 NPC——人头、零钱、兵刃、衣衫，绝不立有名有姓的人
       v12：原著近事要用的人马(world.turn["reserved"]，lod 算好交来；本模块不 import lod)事前分不出人
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import body, bond, situation, stock

import copy

GROUP = "group"
BESIEGE = "围攻"             # 人群 —围攻→ 某人：同仇敌忾地围住(situation.CUSTODY 之一：被围者受制、走不脱)
RECOVER = 240                # 打晕的人过两个时辰醒转归队(v10，与 body.REST 同一口径)：纯规则，不经 LLM
SUPPLY = 50                  # 剧情补充的一队无名之众至多几人(v10)
DEFAULT_KIT = {"money": 0.1, "items": [{"name": "兵刃", "kind": "兵刃", "desc": "随身的兵刃", "steal": True},
                                       {"name": "衣衫", "kind": "杂物", "desc": "身上的衣衫", "steal": False}]}  # 这一门没有模板时的无名之众
FORCE = 1.08                 # 武力 = FORCE ** 功力：功力每高九点力气约翻一倍——十五个功力十五的弟子合起来约抵一个功力五十的好手
DISBAND = 3                  # 站着的不足三人即散
STEAL_ROLL = 70              # 身法与对方同档：命运骰过此才得手
SKILL_TIERS = {"不会武功": 0, "三流": 1, "二流": 2, "一流": 3, "绝顶": 4}  # 武学的 tier 与 profile.TIERS 同序


def force(power) -> float:
    return FORCE ** max(0, power or 0)


def _tier(power) -> int:
    from .profile import tier_index  # profile 引 effects，effects 引本模块：用时才引，不成环
    return tier_index(power or 0)


# ============================================================
#  读：一群人此刻什么样
# ============================================================
def is_squad(g, s) -> bool:
    """一群有人头、有零钱器物的无名之众：场景清单布下的，连同剧情从中分出、或补充来的一队(v10 ephemeral 的也是)；散了的不算。"""
    return g.kind(s) == GROUP and not g.get(s, "disbanded")


def active(world, s) -> bool:
    """出没的时段(v10)：写了 since 的，那一桩原著到期(演了、作罢了或今天该演)之后才在江湖上；写了 until 的，那一桩结算之后便不在。"""
    g = world.graph
    since, until = g.get(s, "since"), g.get(s, "until")
    if since and since not in world.done:
        ev = next((e for e in world.canon if e["id"] == since), None)
        if ev is None or ev["day"] > world.clock.day:
            return False
    return not (until and until in world.done)


def present(world, s, loc: str | None = None) -> bool:
    """这一群此刻在不在跟前：在近旁、未散、未藏、正当出没；片区里(无量山、中原)须被剧情带到跟前(名册)或正随行——与人同一口径。"""
    g = world.graph
    at = g.get(s, "location")
    if not is_squad(g, s) or g.get(s, "hidden") or not active(world, s) or at not in situation.near(world, loc):
        return False
    return not situation.area(world, at) or s in situation.cast(world) | set(situation.party(world))


def standing(g, s) -> int:
    return int(g.get(s, "count") or 0)


def handle(g, s) -> str:
    return g.get(s, "handle") or s


def member(g, s) -> int:
    return g.get(s, "power") if g.get(s, "power") is not None else 15


def squads(world) -> list[str]:
    """眼前的人群：在跟前(present)、还有人站着。"""
    g = world.graph
    return sorted(s for s in g.where(type=GROUP) if present(world, s) and standing(g, s) > 0)


def besiegers(world, who: str = "player") -> list[str]:
    g = world.graph
    return [e["src"] for e in g.edges if e["rel"] == BESIEGE and e["dst"] == who and is_squad(g, e["src"])]


def might(world, s) -> float:
    g = world.graph
    return standing(g, s) * force(member(g, s))


def side(world, who) -> float:
    """一方之力：本人，连同此刻在身边同行助阵的人。"""
    g = world.graph
    if who == "player":
        allies = [p for p in situation.party(world) if p in situation.around(world)]
        return force(world.player["power"]) + sum(force(g.get(p, "power")) for p in allies)
    return force(g.get(who, "power"))


def agility(world, who) -> int:
    """身法之档：功力之档与所会轻功之档取高——学会了凌波微步，便是绝顶的身法。"""
    g = world.graph
    power = world.player["power"] if who == "player" else g.get(who, "power")
    arts = world.player["skills"] if who == "player" else g.get(who, "skills") or []
    light = [SKILL_TIERS.get(g.get(k, "tier"), 0) for k in arts if g.get(k, "style") == "轻功"]
    return max([_tier(power), *light])


CLOTH = set("衣衫服裳袍褂")  # 衣衫、长衫、衣服、衣裳说的是同一样


def kit(g, s, name=None):
    """一群人身上的东西：不给名字即全部模板；给名字即那一样，认不出为 None。
    名字宽松认(真模型写过「东宗弟子众佩剑」)：去掉这一群的名目，再看包含、末一字(佩剑、青钢剑、剑都是长剑；长衫、衣服都是衣衫)。"""
    items = (g.get(s, "kit") or {}).get("items") or []
    if name is None:
        return items
    name = str(name).strip()
    for head in sorted({s, handle(g, s), handle(g, s).removesuffix("弟子"), "弟子们", "弟子", "众人", "众", "的"} - {""}, key=len, reverse=True):
        name = name.replace(head, "")
    tail = lambda x: "衣" if x[-1:] in CLOTH else x[-1:]
    hit = [t for t in items if name == t["name"]] or [t for t in items if name and (t["name"] in name or name in t["name"])] \
        or [t for t in items if name and tail(name) == tail(t["name"])]
    return hit[0] if len(hit) == 1 else None


def _kit_text(g, s) -> str:
    """「人人带着长剑、衣衫，身上有些零钱」。"""
    names = [t["name"] for t in kit(g, s)]
    money = (g.get(s, "kit") or {}).get("money") or 0
    parts = ([f"带着{'、'.join(names)}"] if names else []) + (["身上有些零钱"] if money else [])
    return "人人" + "，".join(parts) if parts else ""


def forecast(world, who, s) -> dict:
    """群战预裁：{fight 硬拼胜不胜, flee 冲不冲得出, steal 偷不偷得到, loss 败了失多少气血}——同一回合同一世界，算两遍结果相同。"""
    g = world.graph
    mine, theirs = side(world, who), might(world, s)
    gap = agility(world, who) - _tier(member(g, s))
    ratio = theirs / max(mine, 1e-6)
    return {"fight": mine > theirs, "flee": mine > theirs / 2,
            "steal": gap >= 1 or (gap == 0 and body.fate(world) >= STEAL_ROLL),
            "loss": "25~40" if ratio >= 4 else "15~25" if ratio >= 2 else "5~15"}


def lines(world) -> list[str]:
    """后台的群战预裁：主角对眼前每一群人，硬拼、脱身、偷取各是什么结局——导演照此演出，节拍里不写「武力」「预裁」。"""
    g, out = world.graph, []
    for s in squads(world):
        f, n = forecast(world, "player", s), standing(g, s)
        fallen = "".join(f"，{w}{stock.cn(g.get(s, k))}人" for k, w in (("down", "倒地(两个时辰内醒转)"), ("dead", "已死")) if g.get(s, k))
        head = f"{s}（{handle(g, s)}，站着{stock.cn(n)}人{fallen}）" + ("此刻正围攻主角" if s in besiegers(world) else "")
        fight = "主角之力压得住整群：夺物、杀伤、打晕由他" if f["fight"] else \
            f"主角之力不及整群：对其中任何一人硬夺、杀伤、打晕，整群同仇敌忾一拥而上，必败，主角失气血约{f['loss']}" \
            f"（写 结下 {s}→player 围攻，再写 伤人）"
        flee = "被围也冲得出去(脱身)" if f["flee"] else "一旦被围便冲不出去：只有智取、求情或有人解围"
        steal = "单独偷取一人身上的东西可以得手" if f["steal"] else "单独偷取必被察觉：失手即遭围攻"
        wares = "、".join(t["name"] for t in kit(g, s))
        out.append(f"{head}：{fight}；{flee}；{steal}" + (f"；身上的东西：{wares}、零钱(偷夺时物写其一)" if wares else ""))
    return out


def afar(world, days: int = 1, held=None) -> list[str]:
    """不在跟前、而在 days 日路程之内的人群(v10，供导演)：剧情要他们来就写 赶来，要几人就从中分出(spawn 的 from)。
    held(v12 lod.reserved)：原著近事要用的人马不在此列——它们另起一节(reserved_lines)，事前不得登场。"""
    g, dist = world.graph, world.graph.distances(world.here)
    out = []
    for s in sorted(g.where(type=GROUP)):
        if is_squad(g, s) and active(world, s) and not present(world, s) and standing(g, s) > 0 \
                and dist.get(g.get(s, "location"), 99) <= days and s not in (held or {}):
            out.append(f"{s}（{handle(g, s)}，站着{stock.cn(standing(g, s))}人）在{g.get(s, 'location')}（距此{dist[g.get(s, 'location')]}日）")
    return out


def reserved_lines(world, held: dict) -> list[str]:
    """原著近事要用的人马(v12，供导演)：在哪、几人、要在哪一桩近事里登场——事前叫不来、分不出人，远远望见可以。"""
    g, dist = world.graph, world.graph.distances(world.here)
    out = []
    for s, ev in sorted((held or {}).items()):
        at = g.get(s, "location")
        out.append(f"{s}（{handle(g, s)}，站着{stock.cn(standing(g, s))}人）在{at}（距此{dist.get(at, '?')}日）：要在原著近事「{ev}」里登场")
    return out


def card(world, s) -> dict:
    g = world.graph
    return {"name": s, "handle": handle(g, s), "count": standing(g, s), "down": g.get(s, "down") or 0, "dead": g.get(s, "dead") or 0,
            "desc": g.get(s, "desc"), "kit": _kit_text(g, s), "hostile": s in besiegers(world)}


# ============================================================
#  写：偷取、夺取、杀伤打晕、脱身——规则之事，不成即返回缘由(什么也不动)
# ============================================================
def _pool(g, s) -> dict:
    return g.nodes[s].setdefault("pool", {})


def _name(world, who) -> str:
    return "主角" if who == "player" else who


def _grudge(world, who, s, why: str):
    """主角对一群人下手：这一门在场的人(掌门、有名有姓的同门)都记一笔怨。"""
    if who != "player":
        return
    g, faction = world.graph, world.graph.get(s, "faction")
    for p in sorted(situation.around(world)):
        if faction and g.get(p, "faction") == faction:
            bond.event(world, p, -4, why)


def _take(world, who, s, what, n) -> tuple[list, str | None]:
    """从一群人身上拿走东西：钱是一人(或 n 人)身上的零钱，器物是 n 件——都从这一群的总数里扣，交到 who 手里。"""
    g, pool = world.graph, _pool(world.graph, s)
    if what is None or str(what) in stock.MONEY_WORDS:
        per = (g.get(s, "kit") or {}).get("money") or 0
        got = round(min(pool.get("银两", 0), per * max(1, int(n or 1))), 3)
        if got <= stock.EPS:
            return [], f"{handle(g, s)}身上已没有钱"
        pool["银两"] = round(pool.get("银两", 0) - got, 3)
        stock.earn(world, who, got)
        return [{"op": "money", "id": who, "value": got, "from": s}], None
    tpl = kit(g, s, what)
    if tpl is None:
        return [], f"{handle(g, s)}身上没有{what}（只有{'、'.join(t['name'] for t in kit(g, s))}与零钱：物写其一，或写银两）"
    have = int(pool.get(tpl["name"], 0))
    if have < 1:
        return [], f"{handle(g, s)}身上的{tpl['name']}已经没有了"
    k = min(max(1, int(n or 1)), have)
    pool[tpl["name"]] = have - k
    nid = stock.materialize(world, f"{handle(g, s)}{tpl['name']}", _template(tpl), k, holder=who)
    return [{"op": "set", "id": nid, "key": "holder", "value": who}], None


def _template(tpl: dict) -> dict:
    return {"kind": tpl.get("kind") or "杂物", "desc": tpl.get("desc"), "unit": tpl.get("unit") or "件"}


def steal(world, who, s, what=None, n=None) -> tuple[list, str | None]:
    """单独偷取：不看力气看身法——偷得到即入手(无人察觉，不记怨)；偷不到便不成，照预裁写成失手。"""
    g = world.graph
    if not forecast(world, who, s)["steal"]:
        return [], f"身法不及{handle(g, s)}：一伸手便被察觉——照预裁写成失手（结下 {s}→player 围攻）"
    tpl = None if what is None or str(what) in stock.MONEY_WORDS else kit(g, s, what)
    if tpl is not None and tpl.get("steal") is False:
        return [], f"{tpl['name']}穿在人身上，偷不下来"
    return _take(world, who, s, what, n)


def rob(world, who, s, what=None, n=None) -> tuple[list, str | None]:
    """强夺：一方之力须过整群，否则一动手便遭围攻。"""
    g = world.graph
    if not forecast(world, who, s)["fight"]:
        return [], f"{_name(world, who)}之力不及{handle(g, s)}整群：一动手便遭同仇敌忾的围攻——照预裁写成落败（结下 {s}→player 围攻，伤人）"
    done, why = _take(world, who, s, what, n)
    if done:
        _grudge(world, who, s, f"你夺了其门下弟子的东西")
    return done, why


def strike(world, who, s, n=None, mode: str = "dead") -> tuple[list, str | None, str]:
    """杀死(mode=dead)或打晕(mode=down) n 人：一方之力须过整群。倒下的人身上的东西落在原地；站着的不足三人即散。
    返回 (成立的记录, 不成立的缘由, 连带说明)。"""
    g = world.graph
    if not forecast(world, who, s)["fight"]:
        return [], f"{_name(world, who)}之力不及{handle(g, s)}整群：一动手便遭同仇敌忾的围攻——照预裁写成落败（结下 {s}→player 围攻，伤人）", ""
    k, left = max(1, int(n or 1)), standing(g, s)
    if k > left:
        return [], f"{handle(g, s)}只剩{stock.cn(left)}人站着", ""
    node = g.nodes[s]
    node["count"] = left - k
    node[mode] = (node.get(mode) or 0) + k
    if mode == "down":  # 打晕的过两个时辰醒转(recover)：记下是什么时候倒的
        node.setdefault("downs", []).append([world.clock.tick, k])
    _drop(world, s, k)
    _grudge(world, who, s, f"你{'杀' if mode == 'dead' else '打倒'}了其门下弟子{stock.cn(k)}人")
    note = dissolve(world, s) if node["count"] < DISBAND else ""
    return [{"op": "squad", "id": s, "key": mode, "value": k, "by": who}], None, note


def _drop(world, s, k: int):
    """倒下的 k 人身上的东西落在原地：剑落在手边，衣衫还穿在身上，零钱揣在怀里——都搜得着、拿得走。"""
    g, pool, at = world.graph, _pool(world.graph, s), world.graph.get(s, "location")
    per = (g.get(s, "kit") or {}).get("money") or 0
    cash = round(min(pool.get("银两", 0), per * k), 3)
    if cash > stock.EPS and at:
        pool["银两"] = round(pool.get("银两", 0) - cash, 3)
        stock.pile(world, at, cash, spot="倒地的弟子怀里")
    for tpl in kit(g, s):
        c = min(int(pool.get(tpl["name"], 0)), k)
        if c > 0 and at:
            pool[tpl["name"]] = int(pool.get(tpl["name"], 0)) - c
            stock.materialize(world, f"{handle(g, s)}{tpl['name']}", _template(tpl), c, location=at,
                              spot="倒地的弟子身上" if tpl.get("steal") is False else "倒地的弟子手边")


def dissolve(world, s) -> str:
    """站着的不足三人：散了。剧情里写作四散逃去；底层删去这一群——场景清单布下的留个空壳(disbanded，读档不复活)，剧情临时分出的一队直接删去；
    站着的几人连同身上的东西、倒地未醒的人一并走了。"""
    g = world.graph
    left, node, name = standing(g, s), g.nodes[s], handle(g, s)
    if node.get("ephemeral"):
        del g.nodes[s]
    else:
        node.update(disbanded=True, hidden=True, count=0, location=None, pool={}, downs=[])
    g.edges = [e for e in g.edges if s not in (e["src"], e["dst"])]
    return f"{name}" + (f"只剩{stock.cn(left)}人，无心恋战，四散逃去" if left else "尽数倒地，再无一人站着")


def escape(world, who, s) -> str | None:
    """脱身：一方之力过整群一半才冲得出去；冲得出去返回 None(调用方解围、挪人)。"""
    g = world.graph
    return None if forecast(world, who, s)["flee"] else f"冲不出{handle(g, s)}的围困：须有整群一半之力"


# ============================================================
#  光阴(v10)：打晕的人醒转归队——纯规则，与 LLM 无关
# ============================================================
def recover(world) -> list[str]:
    """打晕的人倒下满 RECOVER 分钟即醒转归队：人数回来，落在原地的兵刃、衣衫、零钱还在就捡回去。返回眼前醒转的说明。"""
    g, now, told = world.graph, world.clock.tick, []
    for s in sorted(g.where(type=GROUP)):
        if not is_squad(g, s):
            continue
        node = g.nodes[s]
        downs = node.get("downs")
        if downs is None and node.get("down"):  # 旧档没有倒下的时刻：当作早已倒下
            downs = [[0, node["down"]]]
        if not downs:
            continue
        woke = sum(k for t, k in downs if now - t >= RECOVER)
        node["downs"] = [[t, k] for t, k in downs if now - t < RECOVER]
        if woke <= 0:
            continue
        node["down"] = max(0, int(node.get("down") or 0) - woke)
        node["count"] = standing(g, s) + woke
        _regather(world, s, woke)
        if present(world, s):
            told.append(f"{handle(g, s)}倒地的人里有{stock.cn(woke)}人醒转过来")
    return told


def _regather(world, s, k: int):
    """醒转的 k 人捡回落在原地的东西(还在、没人拿走的才捡得回)：兵刃衣衫按件，零钱从倒地处的那一堆里。"""
    g, at, pool = world.graph, world.graph.get(s, "location"), _pool(world.graph, s)
    for tpl in kit(g, s):
        need, root = k, f"{handle(g, s)}{tpl['name']}"
        for i in sorted(g.where(type="item", location=at)):
            if need <= 0:
                break
            if stock.base(g, i) == root and g.get(i, "holder") is None and stock._usable(g, i):
                take = min(int(stock.qty(g, i)), need)
                if take >= stock.qty(g, i):
                    stock.retire(world, i)
                else:
                    g.nodes[i]["qty"] = stock.qty(g, i) - take
                pool[tpl["name"]] = int(pool.get(tpl["name"], 0)) + take
                need -= take
    per = (g.get(s, "kit") or {}).get("money") or 0
    want = round(per * k, 3)
    for i in sorted(g.where(type="item", location=at)):
        if want <= stock.EPS:
            break
        if stock.is_cash(g, i) and g.get(i, "holder") is None and g.get(i, "spot") == "倒地的弟子怀里" and stock._usable(g, i):
            take = round(min(stock.qty(g, i), want), 3)
            g.nodes[i]["qty"] = round(stock.qty(g, i) - take, 3)
            if g.nodes[i]["qty"] <= stock.EPS:
                stock.retire(world, i)
            pool["银两"] = round(pool.get("银两", 0) + take, 3)
            want = round(want - take, 3)


# ============================================================
#  行止(v10)：一群人随剧情远行——带队之人被原著挪走，同在一处的这一群随他走；挪走了的不再围着谁
# ============================================================
def escort(world, leader: str, old: str | None):
    """原著把带队之人(leader)从 old 挪到别处：同在 old 的这一门人群随他走(场景清单写了 leader 的)。"""
    g, new = world.graph, world.graph.get(leader, "location")
    for s in sorted(g.where(type=GROUP)):
        if is_squad(g, s) and g.get(s, "leader") == leader and g.get(s, "location") == old and old != new:
            relocate(world, s, new)


def relocate(world, s, where: str | None):
    """一群人换了地方：原先围着的人不再被围(人走了，围不住)。"""
    g = world.graph
    g.nodes[s]["location"] = where
    g.edges = [e for e in g.edges if not (e["src"] == s and e["rel"] == BESIEGE)]


# ============================================================
#  重组与补充(v10)：剧情临时立的一队人马是既有人群的重组(分出几人，带着他们身上的零钱器物)；
#  附近没有同门人群而这一门在附近有据点或人手，才另补一队无名之众(人头、零钱、兵刃、衣衫，像资源一样按模板)——绝不凭空立有名有姓的人
# ============================================================
def template(g, faction: str | None) -> dict:
    """这一门的无名之众长什么样：门下模板(场景清单 kits) > 世上任一同门人群 > 缺省(一件兵刃、一件衣衫、一钱零钱)。"""
    tpl = g.get(faction, "squad_kit") if faction else None
    if tpl:
        return copy.deepcopy(tpl)
    kin = next((s for s in sorted(g.where(type=GROUP)) if is_squad(g, s) and g.get(s, "faction") == faction
                and not g.get(s, "ephemeral")), None)
    if kin:
        return {"handle": handle(g, kin), "power": member(g, kin), **copy.deepcopy(g.get(kin, "kit") or DEFAULT_KIT), "desc": g.get(kin, "desc")}
    return {"handle": f"{faction}门人" if faction else "无名之众", "power": 15, **copy.deepcopy(DEFAULT_KIT), "desc": None}


def _body(world, nid, faction, location, n, power, kit_: dict, pool: dict, name, desc, base=None) -> dict:
    return {"type": GROUP, "ephemeral": True, "born": world.clock.day, "faction": faction, "location": location, "count": n,
            "down": 0, "dead": 0, "power": power, "handle": name, "desc": desc, "hidden": False, "status": "alive",
            "kit": {"money": kit_.get("money", 0), "items": copy.deepcopy(kit_.get("items") or [])}, "pool": pool,
            **({"base": base} if base else {})}


def split(world, src: str, n: int, nid: str, location: str, name: str | None = None, desc: str | None = None) -> str:
    """从 src 里分出 n 人另成一队(nid)：他们身上的零钱与器物按人头一并带走，src 只剩其余。"""
    g, node = world.graph, world.graph.nodes[src]
    pool, per = _pool(g, src), (node.get("kit") or {}).get("money") or 0
    share = {"银两": round(min(pool.get("银两", 0), per * n), 3)}
    for tpl in kit(g, src):
        share[tpl["name"]] = min(int(pool.get(tpl["name"], 0)), n)
    for k, v in share.items():
        pool[k] = round(pool.get(k, 0) - v, 3) if k == "银两" else int(pool.get(k, 0)) - v
    node["count"] = standing(g, src) - n
    g.nodes[nid] = _body(world, nid, node.get("faction"), location, n, member(g, src), node.get("kit") or {}, share,
                         name or handle(g, src), desc or node.get("desc"), base=src)
    return nid


def rejoin(world, s) -> str | None:
    """分出去的一队回到原来那一群(人头与身上之物并回去，倒地的也带回去醒转)；原来那一群已散，这一队就地散去。返回并入的那一群。"""
    g = world.graph
    node, base = g.nodes.get(s), (g.get(s, "base") if g.has(s) else None)
    if node is None:
        return None
    if base and is_squad(g, base):
        b = g.nodes[base]
        b["count"] = standing(g, base) + standing(g, s) + int(node.get("down") or 0)
        bp = _pool(g, base)
        for k, v in (node.get("pool") or {}).items():
            bp[k] = round(bp.get(k, 0) + v, 3) if k == "银两" else int(bp.get(k, 0)) + int(v)
    del g.nodes[s]
    g.edges = [e for e in g.edges if s not in (e["src"], e["dst"])]
    return base if base and is_squad(g, base) else None


def _match(world, x) -> str | None:
    """叫法或 id 认出一群人：「东宗弟子」「东宗弟子众」。"""
    g = world.graph
    x = world.aliases.get(x, x) if isinstance(x, str) else x
    hits = [s for s in sorted(g.where(type=GROUP)) if is_squad(g, s) and isinstance(x, str)
            and x.strip().rstrip("们") in (s, handle(g, s))]
    return hits[0] if hits else None


def muster(world, spec: dict, name: str, embargo=frozenset(), rooted=None) -> tuple[str | None, str | None]:
    """剧情要的一队人马(spawn 的 group)：先从眼前或一日之内的同门人群里分出 count 人(from 可指明哪一群，指明了而人数不够即驳回)；
    附近没有同门人群、或人数不够(那是另一队增援)，而这一门在附近有据点或人手，才另补一队无名之众(至多 SUPPLY 人，按门下模板带零钱器物)。返回 (id, 不成立的缘由)。"""
    g, here = world.graph, world.here
    faction = spec.get("faction")
    faction = world.aliases.get(faction, faction) if isinstance(faction, str) else faction
    count = spec.get("count")
    n = int(count) if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 0 else None
    dist = g.distances(here)
    if not faction and not spec.get("from"):
        return None, f"群体「{name}」须写明属于哪一门(faction)，或从哪一群里分出(from)"
    src = _match(world, spec.get("from")) if spec.get("from") else None
    if spec.get("from") and src is None:
        return None, f"「{spec.get('from')}」不是一群人：分人只能从既有的人群里分"
    if src is None:
        pool = [s for s in g.where(type=GROUP) if is_squad(g, s) and active(world, s) and standing(g, s) > 0
                and (faction is None or g.get(s, "faction") == faction) and dist.get(g.get(s, "location"), 99) <= 1]
        src = min(pool, key=lambda s: (not present(world, s), dist.get(g.get(s, "location"), 99), s)) if pool else None
        if src is not None and n and n > standing(g, src):  # 附近那一群人数不够：这是另一队增援，按补充算
            src = None
    held = (getattr(world, "turn", None) or {}).get("reserved") or {}
    if src is not None and src in held and not present(world, src):  # 原著近事要用的人马(v12)：事前分不出人
        return None, f"{handle(g, src)}要在原著近事「{held[src]}」里登场，此时分不出人来"
    if src is not None:
        if faction and g.get(src, "faction") != faction:
            return None, f"{handle(g, src)}是{g.get(src, 'faction')}的人，分不出{faction}的人马"
        if not active(world, src) or dist.get(g.get(src, "location"), 99) > 1:
            return None, f"{handle(g, src)}远在{g.get(src, 'location')}，一时分不出人来"
        left = standing(g, src)
        n = n or min(10, left)
        if n > left:
            return None, f"{handle(g, src)}只有{stock.cn(left)}人站着，分不出{stock.cn(n)}人"
        desc = str(spec.get("desc") or "")[:40] or None
        if n >= left:  # 整群都来了：就是那一群，叫法照旧
            relocate(world, src, here)
            world.aliases[name] = src
            return src, None
        return split(world, src, n, name, here, name, desc), None
    if g.kind(faction) != "faction":
        return None, f"群体「{name}」须属于一个已登记的门派"
    if faction in embargo:
        return None, f"{faction}的人马此时尚未到此（原著近事），不得先行登场"
    if rooted is not None and not rooted(world, faction):
        return None, f"{faction}在此地附近既无据点也无人手，凭空来不了一队人"
    n = n or 10
    if n > SUPPLY:
        return None, f"一队人马至多{stock.cn(SUPPLY)}人"
    tpl = template(g, faction)
    pool = {"银两": round(n * (tpl.get("money") or 0), 3), **{t["name"]: n for t in tpl.get("items") or []}}
    g.nodes[name] = _body(world, name, faction, here, n, tpl.get("power", 15), tpl, pool, name,
                          str(spec.get("desc") or "")[:40] or tpl.get("desc"))
    return name, None
