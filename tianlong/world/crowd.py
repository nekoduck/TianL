"""
[INPUT]: 依赖 world/situation 的 near / around / party（近旁、身边、同行）、world/stock 的 earn / materialize / pile / cn / say / MONEY_WORDS（银两与器物的流转）、
         world/body 的 fate（命运骰：偷取时身法相当看它）、world/bond 的 event（杀伤夺物记在这一门的人账上）；功力档读 world/profile(用时才引)；World 门面（graph / player / clock / turn）
[OUTPUT]: 对外提供 人群(v9 无名弟子)——GROUP / BESIEGE / FORCE / DISBAND / STEAL_ROLL、force()（功力 → 武力，指数尺度）、is_squad() / standing() / handle() / squads() / besiegers()、
          might()（整群之力：站着的人数 × 每人之力）、side()（一方之力：本人连同身边同行助阵者）、agility()（身法之档：功力之档与所会轻功的档取高）、
          forecast()（群战预裁：硬拼胜不胜、冲不冲得出去、偷不偷得到、败了失多少气血）、lines()（后台的群战预裁）、card()（视锥里的一群人）、
          kit()（一群人身上的东西；名字宽松认——去掉这一群的名目再看包含与末一字：佩剑、青钢剑都是长剑，长衫、衣服都是衣衫）、CLOTH、steal() / rob() / strike() / escape()（偷取、夺取、杀伤打晕、脱身——规则之事，不成即返回缘由）
[POS]: world 层的人群规则——原著里有名有姓的人是一个个节点；同门的无名之众(东西宗各十五名弟子)是一群：十五人一体，各有一点零钱、一件衣衫、一柄剑。
       对其中一人动手就是对整群动手(同仇敌忾)：
       夺物、杀伤、打晕须一方之力过整群——武力按功力取指数(档位本是对数尺度：每高九点功力，力气约翻一倍)，整群之力是站着的人数乘每人之力；
       力过整群一半才冲得出围攻(围攻是人群→某人的一条拘押之边，被围住便走不脱，只有脱身)；单独偷取不看力气看身法：身法高过他们一档即得手，相当看命运骰；
       倒下的人(杀死、打晕)身上的东西落在原地，人群照少；站着的不足三人即散——剧情里写作逃散，底层留个空壳(读档不复活)，世上不再有这一群。
       全是确定的规则，不调 LLM；导演开口前看得见预裁，只演出、不裁决
       is_squad 只认场景清单布下的人群：剧情临时立的一队人马(ephemeral)只活在叙事里；一群人只在近旁走动(effects 拦远行)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import body, bond, situation, stock

GROUP = "group"
BESIEGE = "围攻"             # 人群 —围攻→ 某人：同仇敌忾地围住(situation.CUSTODY 之一：被围者受制、走不脱)
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
    """一群有人头、有零钱器物的无名之众(场景清单布下的)；剧情临时立的一队人马(ephemeral)只活在叙事里，不是这里说的人群。"""
    return g.kind(s) == GROUP and not g.get(s, "ephemeral") and not g.get(s, "disbanded")


def standing(g, s) -> int:
    return int(g.get(s, "count") or 0)


def handle(g, s) -> str:
    return g.get(s, "handle") or s


def member(g, s) -> int:
    return g.get(s, "power") if g.get(s, "power") is not None else 15


def squads(world) -> list[str]:
    """眼前的人群：近旁之内、未散、还有人站着。"""
    g, spots = world.graph, situation.near(world)
    return sorted(s for s in g.where(type=GROUP) if is_squad(g, s) and not g.get(s, "hidden")
                  and g.get(s, "location") in spots and standing(g, s) > 0)


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
        fallen = "".join(f"，{w}{stock.cn(g.get(s, k))}人" for k, w in (("down", "倒地"), ("dead", "已死")) if g.get(s, k))
        head = f"{s}（{handle(g, s)}，站着{stock.cn(n)}人{fallen}）" + ("此刻正围攻主角" if s in besiegers(world) else "")
        fight = "主角之力压得住整群：夺物、杀伤、打晕由他" if f["fight"] else \
            f"主角之力不及整群：对其中任何一人硬夺、杀伤、打晕，整群同仇敌忾一拥而上，必败，主角失气血约{f['loss']}" \
            f"（写 结下 {s}→player 围攻，再写 伤人）"
        flee = "被围也冲得出去(脱身)" if f["flee"] else "一旦被围便冲不出去：只有智取、求情或有人解围"
        steal = "单独偷取一人身上的东西可以得手" if f["steal"] else "单独偷取必被察觉：失手即遭围攻"
        wares = "、".join(t["name"] for t in kit(g, s))
        out.append(f"{head}：{fight}；{flee}；{steal}" + (f"；身上的东西：{wares}、零钱(偷夺时物写其一)" if wares else ""))
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
    """站着的不足三人：散了。剧情里写作四散逃去；底层留个空壳(disbanded，读档不复活)，世上不再有这一群，站着的几人连同身上的东西一并走了。"""
    g = world.graph
    left, node = standing(g, s), g.nodes[s]
    node.update(disbanded=True, hidden=True, count=0, location=None, pool={})
    g.edges = [e for e in g.edges if s not in (e["src"], e["dst"])]
    return f"{handle(g, s)}" + (f"只剩{stock.cn(left)}人，无心恋战，四散逃去" if left else "尽数倒地，再无一人站着")


def escape(world, who, s) -> str | None:
    """脱身：一方之力过整群一半才冲得出去；冲得出去返回 None(调用方解围、挪人)。"""
    g = world.graph
    return None if forecast(world, who, s)["flee"] else f"冲不出{handle(g, s)}的围困：须有整群一半之力"
