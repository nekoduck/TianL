"""
[INPUT]: 依赖 world/stock（银两与数量）、world/venue（场所、货架、伙计当值）、world/lore（消息）、world/effects 的 apply / usable / resolve（唯一写入通道）、
         world/situation 的 around、world/actor 的 conditions；World 门面(graph / atlas / player / here / turn，鸭子类型)
         v13 另依赖 world/body 的 antidote / envenom / protected（毒是规则态：对症才解、毒药服下即登记）
[OUTPUT]: 对外提供 买卖与服务的执行(v11 世界底座，事码 买下 / 卖出 / 办事 / 服用 / 打探 交这里)——buy()、sell()、serve()、consume()、inquire()，
          shop()（此处的铺子）、clerks()（此刻当值、在眼前的伙计）、ware_of()（认货：目录 id、货名、货架上的 id）、services_here()、RATIO、LODGING、MEALS、TREAT
[POS]: world 层的买卖与服务——底座里有的才买得到、办得成：货架上的货有价有存货(买走即少、每日补回)，服务由当值的那个职名办、价钱照价目，
       钱从主角身上付到柜上(柜银是一堆碎银，总数守恒)；收购与典当按估值的几成、柜上的银两不够即不收；
       药与毒接身体规则(一服回几点气血、内伤降几级、治什么解什么，毒发添上症状)；打探从消息表里取——此处向当值的哪个职名、要多少赏钱，
       听来的照原样记(可以是假的)，原话进连带交编剧照它写；没写问谁先问办打探的伙计，想打听的事是偏好、不是筛子。一件事一个事务：前提不成整条不成并给出人话缘由，什么也不动；记录写成下游认得的形状(money 与 inventory 照旧，另有 trade/service/lore)。
       v13 毒是规则态(P1-1)：_cure 先看对症不对症(body.antidote：对症的毒解去，对不上的写明「X于Y无效」)，再落药力；毒药服下即登记一条毒(body.envenom)，往后随光阴发作
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

from . import actor, body, effects, lore, perspective, situation, stock, venue

RATIO = 0.4                                              # 收购、典当按估值的几成(4.2：当价三到五成)
LODGING = {"住宿", "借宿"}                               # 住下：主角进那一间(住满两个时辰即算歇息养伤，归 body)
MEALS = {"打尖", "饮食", "斋饭", "包席"}                  # 吃喝：一顿饭的光阴，不加气血(养伤归歇息)
TREAT = {"诊治", "敷药", "针灸", "出诊", "抓药"}           # 医治：效用照数据(effect)接身体规则
RULE = "rule"                                            # 药力、医治落账的来源(与 effects.RULED_BY 同名)：规则算的，不是哪一方写的剧情


def _turn(world):
    return getattr(world, "turn", None)


def _traded(world, *items):
    if _turn(world) is not None:
        world.turn.setdefault("traded", set()).update(i for i in items if i)


def _note(world, text: str):
    if text and _turn(world) is not None:
        world.turn.setdefault("notes", []).append(text)


def shop(world) -> str | None:
    """主角此刻所在的铺子(场所本身或它的房间)。"""
    return venue.venue_of(world.graph, world.here)


def clerks(world, vid: str, roles=None) -> list[str]:
    """这处场所此刻当值、就在眼前的伙计(可限职名)。"""
    around, sp = situation.around(world), venue.spec(world, vid) or {}
    ids = [s["id"] for s in sp.get("staff") or [] if roles is None or s.get("role") in roles]
    return [p for p in ids if p in around and venue.on_duty(world, p)]


def ware_of(world, vid: str, name) -> str | None:
    """认货：目录 id(货·黄酒)、货名(黄酒)、货架上的 id(某店·黄酒)；名字宽松认(一壶黄酒、黄酒两斤)，撞了不认。"""
    if not isinstance(name, str):
        return None
    wares, name = venue.wares(world, vid), name.strip()
    for gid, w in wares.items():
        if name in (gid, gid[2:], w["id"]):
            return gid
    hits = [gid for gid in wares if gid[2:] in name or (len(name) >= 2 and name in gid[2:])]
    return hits[0] if len(hits) == 1 else None


def _till(world, vid: str) -> str | None:
    tid = f"{vid}·柜银"
    return tid if world.graph.has(tid) and stock.is_cash(world.graph, tid) and effects.usable(world, tid) else None


def _deposit(world, vid: str, seller: str, amount: float) -> str:
    """钱付到柜上(柜银那一堆)；没有柜银的(庙里、宅院)进伙计的零钱。返回钱去了哪里。"""
    g, tid = world.graph, _till(world, vid)
    if tid:
        g.nodes[tid]["qty"] = round(stock.qty(g, tid) + amount, 3)
        return tid
    stock.earn(world, seller, amount)
    return seller


def _withdraw(world, vid: str, amount: float) -> str | None:
    """从柜上取钱付给主角：柜上不够即不成。"""
    g, tid = world.graph, _till(world, vid)
    if not tid or stock.qty(g, tid) + stock.EPS < amount:
        return None
    g.nodes[tid]["qty"] = round(stock.qty(g, tid) - amount, 3)
    return tid


def _name(world, vid) -> str:
    return world.graph.get(vid, "sign") or vid.rpartition("·")[2]


def _count(a, default=1):
    n = a.get("量")
    return n if isinstance(n, (int, float)) and n > 0 else default


# ============================================================
#  买下：货架上的货，价目照货架，钱付到柜上，东西到主角手里(大件留在店里记作主角的)
# ============================================================
def buy(world, a, who, heading):
    g = world.graph
    if who != "player":
        return [], "买卖只记主角的：旁人买东西交导演一笔带过"
    vid = shop(world)
    if not vid or not venue.wares(world, vid):
        return [], "此处没有铺子卖货"
    gid = ware_of(world, vid, a.get("物"))
    shelf = venue.wares(world, vid)
    if gid is None:
        return [], f"{_name(world, vid)}不卖「{a.get('物')}」：货架上有{'、'.join(k[2:] for k in shelf)}"
    sellers = clerks(world, vid)
    if not sellers:
        return [], f"{_name(world, vid)}此刻没人照看(伙计不当值)"
    w, item = shelf[gid], (world.atlas.get("goods") or {}).get(gid) or {}
    n = _count(a)
    if w["stock"] is not None and n > w["stock"] + stock.EPS:
        return [], f"{gid[2:]}只剩{stock.cn(w['stock'])}{item.get('unit') or '件'}" if w["stock"] else f"{gid[2:]}卖完了"
    total = round(w["price"] * n, 3)
    if not stock.pay(world, "player", total):
        return [], f"身上只有{stock.say(stock.funds(world, 'player'))}，买不起（{stock.say(total)}）"
    to = _deposit(world, vid, sellers[0], total)
    if w["stock"] is not None:
        w["stock"] = round(w["stock"] - n, 3)
    template = {"kind": item.get("kind") or "杂物", "grade": "器物", "desc": item.get("desc"), "unit": item.get("unit") or "件",
                "split": bool(item.get("split")) or n > 1, "uses": list(item.get("uses") or []), "goods": gid, "price": item.get("price"),
                "layer": 3, **({"effect": dict(item["effect"])} if isinstance(item.get("effect"), dict) else {})}
    portable = item.get("portable", True) is not False
    nid = stock.materialize(world, w["id"], template, n, holder="player" if portable else None, location=None if portable else w["in"])
    if not portable:
        g.nodes[nid]["owner"] = "player"
    _traded(world, nid, "银两")
    return [{"op": "money", "id": "player", "value": -total, "to": to},
            {"op": "trade", "id": nid, "key": "bought", "value": n, "from": sellers[0], "price": total},
            *([{"op": "push", "id": "player", "key": "inventory", "value": nid}] if portable else [])], None


# ============================================================
#  卖出：铺子收它卖的货，当铺什么都收；按估值的几成，柜上的银两不够即不收
# ============================================================
def _value(world, item: str) -> float | None:
    g = world.graph
    gid = g.get(item, "goods")
    if gid and gid in (world.atlas.get("goods") or {}):
        return world.atlas["goods"][gid]["price"]
    price = g.get(item, "price")
    return price if isinstance(price, (int, float)) and price > 0 else None


def sell(world, a, who, heading):
    g, item = world.graph, a.get("物")
    if who != "player":
        return [], "买卖只记主角的：旁人卖东西交导演一笔带过"
    vid = shop(world)
    if not vid:
        return [], "此处没有铺子收东西"
    if not isinstance(item, str) or g.kind(item) != "item" or g.get(item, "holder") != "player":
        return [], f"「{item}」不在你手里"
    pawn = g.get(vid, "venue") == "当铺"
    gid = g.get(item, "goods")
    if not pawn and gid not in venue.wares(world, vid):
        return [], f"{_name(world, vid)}不收这样东西(当铺什么都收)"
    value = _value(world, item)
    if value is None:
        return [], f"{item}估不出价，没人肯收"
    buyers = clerks(world, vid)
    if not buyers:
        return [], f"{_name(world, vid)}此刻没人照看(伙计不当值)"
    n = min(_count(a, stock.qty(g, item)), stock.qty(g, item))
    pay = round(value * n * RATIO, 2)
    if pay <= stock.EPS:
        return [], f"{item}不值什么钱"
    src = _withdraw(world, vid, pay)
    if src is None:
        return [], f"{_name(world, vid)}柜上的银两不够，收不起"
    stock.earn(world, "player", pay)
    if n < stock.qty(g, item) - stock.EPS:
        sold = stock.part(world, item, n, location=g.get(vid, "wares", {}).get(gid, {}).get("in") or world.here)
    else:
        sold = item
        world.player.pull("inventory", item)
        g.nodes[item].update(holder=None, location=world.here, spot="柜上")
    if gid in venue.wares(world, vid) and venue.wares(world, vid)[gid]["stock"] is not None:  # 收回的货上了货架
        venue.wares(world, vid)[gid]["stock"] = round(venue.wares(world, vid)[gid]["stock"] + n, 3)
        stock.retire(world, sold)
    _traded(world, item, sold, "银两")
    return [{"op": "money", "id": "player", "value": pay, "from": src},
            {"op": "trade", "id": item, "key": "pawned" if pawn else "sold", "value": n, "to": buyers[0], "price": pay},
            {"op": "pull", "id": "player", "key": "inventory", "value": item}], None


# ============================================================
#  服用：药、食、酒、毒——效用接身体规则
# ============================================================
def _effect(world, item: str) -> dict:
    g = world.graph
    eff = g.get(item, "effect")
    if isinstance(eff, dict):
        return eff
    gid = g.get(item, "goods")
    eff = ((world.atlas.get("goods") or {}).get(gid) or {}).get("effect") if gid else None
    return eff if isinstance(eff, dict) else {}


def _cure(world, target: str, eff: dict, why: str, item: str | None = None) -> list:
    """一服药(或一回医治)的效用落到 target 身上：回气血、降内伤、治与解去掉相应的境况、毒发添上症状、扣气血。
    v13 毒是规则态：先看对症不对症（body.antidote，对症的毒解去、对不上的写明「X于Y无效」），再落药力；毒药服下即登记一条毒（body.envenom）。"""
    cured, miss = body.antidote(world, target, item or why, eff)
    if cured:
        _note(world, f"{why}：{'你' if target == 'player' else target}所中的{'、'.join(cured)}解去了")
    if miss:
        _note(world, miss)
    ops, conds = [], [c for c in actor.conditions(world, target) if not body.protected(world, target, c)]  # 没解去的毒，标记还在，药力碰不得它
    hp = eff.get("气血")
    if isinstance(hp, (int, float)) and hp:
        ops.append({"op": "add", "id": target, "key": "hp", "value": hp})
    if isinstance(eff.get("内伤"), (int, float)) and eff["内伤"] > 0:
        from .body import INNER
        inner = next((c for c in conds if INNER.search(c)), None)
        if inner:
            ops.append({"op": "pull", "id": target, "key": "conditions", "value": inner})
    cures = [str(x) for x in [*(eff.get("治") or []), *(eff.get("解") or [])] if x]
    ops += [{"op": "pull", "id": target, "key": "conditions", "value": c} for c in conds
            if any(x in c or (x == "外伤" and "伤" in c and "内" not in c) for x in cures)]
    if eff.get("症"):
        ops.append({"op": "push", "id": target, "key": "conditions", "value": str(eff["症"])[:10]})
    done, bad = effects.apply(world, ops, RULE) if ops else ([], [])  # 药力归规则：不是导演写的疗伤，不顺带降内伤(降不降看效用里的「内伤」)
    if bad:
        _note(world, f"{why}：{'；'.join(r for _, r in bad)}")
    if eff.get("症") and eff.get("发") and item:  # 毒药：服下即中了毒，往后随光阴发作
        body.envenom(world, target, item, eff, src=item)
    return done


def consume(world, a, who, heading):
    g, item = world.graph, a.get("物")
    target = a.get("对") or who
    if not isinstance(item, str) or g.kind(item) != "item" or not effects.usable(world, item):
        return [], f"世上没有「{item}」这件东西"
    if g.get(item, "holder") != who:
        return [], f"{item}不在{'你' if who == 'player' else who}手里"
    if target != who and target not in situation.around(world) and target != "player":
        return [], f"{target}不在跟前"
    eff = _effect(world, item)
    left = stock.qty(g, item) - 1
    if left > stock.EPS:
        g.nodes[item]["qty"] = round(left, 3)
    else:
        stock.retire(world, item)
    _traded(world, item)
    done = _cure(world, target, eff, f"服用{item}", item)
    return [{"op": "trade", "id": item, "key": "used", "value": 1, "to": target}, *done], None


# ============================================================
#  办事：此处的服务(住宿、打尖、诊治、雇车、摆渡、带信……)由当值的那个职名办，价目照数据
# ============================================================
def services_here(world) -> list[dict]:
    vid = shop(world)
    return venue.services(world, vid) if vid else []


def serve(world, a, who, heading):
    g, name = world.graph, str(a.get("事") or "").strip()
    if who != "player":
        return [], "办事只记主角的：旁人的事交导演一笔带过"
    vid = shop(world)
    offers = [s for s in services_here(world) if s["name"] == name]
    if not offers:
        have = sorted({s["name"] for s in services_here(world)})
        return [], f"此处办不了「{name}」" + (f"：能办的是{'、'.join(have)}" if have else "")
    want = str(a.get("为") or "")
    pick = next((s for s in offers if want and s.get("room") and want in s["room"]), offers[0])
    by = a.get("与")
    hands = [p for p in clerks(world, vid) if p in pick["by"] and (by in (None, p))]
    if not hands:
        return [], f"办{name}的{pick['role']}此刻不在跟前或不当值"
    n = _count(a)
    total = round(pick["price"] * n, 3)
    if total > stock.EPS and not stock.pay(world, "player", total):
        return [], f"身上只有{stock.say(stock.funds(world, 'player'))}，{name}要{stock.say(total)}"
    to = _deposit(world, vid, hands[0], total) if total > stock.EPS else None
    out = ([{"op": "money", "id": "player", "value": -total, "to": to}] if to else []) + \
          [{"op": "service", "id": vid, "key": name, "value": n, "by": hands[0], "price": total, "time": pick.get("time")}]
    if name in LODGING and pick.get("room") and g.has(pick["room"]):
        done, _ = effects.apply(world, [{"op": "set", "id": "player", "key": "location", "value": pick["room"]}], "director")
        out += done
    if name in TREAT and isinstance(pick.get("effect"), dict):
        out += _cure(world, a.get("对") or "player", pick["effect"], name, name)
    if name == "打探":
        told, why = _tell(world, hands[0], a.get("物"), free=True)
        if told:
            out += told
    _traded(world, "银两")
    if _turn(world) is not None:
        world.turn.setdefault("served", set()).add(name)  # 正文复述这件事，账房不再记一遍
    return out, None


# ============================================================
#  打探：向眼前的人打听——伙计按职名知道的那几条、有名之人肯说的；赏钱付给他本人
# ============================================================
VAGUE_TOPIC = re.compile(r"传闻|消息|新鲜|近况|风声|江湖|掌故|见闻|动静|闲话|旧事")  # 泛泛一问：他知道什么就说什么


def _tell(world, person: str, topic=None, free=False) -> tuple[list, str | None]:
    table = lore.entries(world)
    mine = [s for s in lore.sources(world, [person]) if s["by"] == person]
    if not world.graph.get(person, "staff"):  # 有名之人：他知道而肯说的(条件由导演看 need 演)
        heard = set(lore.heard(world))
        mine += [{"id": lid, "how": "问", "by": person, "price": 0, "need": None} for lid in lore.tells(world, person)
                 if lid not in heard and lid not in {m["id"] for m in mine}]
    if topic:  # 想打听的事是偏好，不是筛子：问「江湖传闻」，他就说他知道的那几条里最贴的
        key = str(topic)
        hit = [m for m in mine if key in m["id"] or key in (table[m["id"]].get("text") or "")
               or any(key in str(x) for x in table[m["id"]].get("about") or [])]
        if not hit and mine and not VAGUE_TOPIC.search(key):  # v14 问的是具体的事(后山退路)而他知道的消息都不相干：不硬塞一条答非所问的掌故(run5 第 15 回)
            return [], f"{person}的消息里没有「{key}」这件事：他照自己知道的随口答，打听不到什么"
        mine = hit or mine
    if not mine:
        return [], f"{person}不知道什么新鲜事"
    pick = mine[0]
    price = 0 if free or not world.graph.get(person, "staff") else round(pick.get("price") or 0, 3)  # v14 赏钱只给吃这碗饭的伙计：向同门、熟人打听不掏钱
    if price > stock.EPS:
        if not stock.pay(world, "player", price):
            return [], f"打听这件事要{stock.say(price)}赏钱，身上不够"
        stock.earn(world, person, price)
    lore.learn(world, pick["id"])
    entry = table[pick["id"]]
    _note(world, f"{perspective.handle(world, person)}说起：「{entry.get('text')}」——打听来的就是这一句，台词照它说，不另编消息")
    return ([{"op": "money", "id": person, "value": price, "from": "player"}] if price > stock.EPS else []) + \
        [{"op": "lore", "id": pick["id"], "by": person, "value": entry.get("text"), "how": pick.get("how")}], None


def inquire(world, a, who, heading):
    if who != "player":
        return [], "打探只记主角的：旁人之间说了什么交导演写进台词"
    person = a.get("与") or a.get("对")
    people = situation.around(world)
    if person is None:  # 没写问谁：先找办打探的伙计(店小二)，再找此处知道消息的人
        g = world.graph
        found = sorted((s for s in lore.sources(world) if s["by"]), key=lambda s: "打探" not in (g.get(s["by"], "services") or []))
        person = found[0]["by"] if found else next(iter(sorted(people)), None)
    if person not in people:
        return [], f"{person or '没有人'}不在跟前，问不着"
    if not venue.on_duty(world, person):
        return [], f"{person}此刻不当值，回屋歇着了"
    done, why = _tell(world, person, a.get("物"))
    _traded(world, "银两")
    if done and _turn(world) is not None:
        world.turn.setdefault("asked", set()).add(person)
    return done, why
