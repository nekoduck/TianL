"""
[INPUT]: 依赖 world/situation 的 near / around（近旁与眼前）、world/effects 的 place / usable（器物此刻所在、是否尚存）、world/stock 的 measure / purse / say（v9 数量与钱袋）、world/scribe 的 label / readable（v9 文书的样子与读得到的字），World 门面的 graph / player / here（鸭子类型）
[OUTPUT]: 对外提供 GRADES / TRIFLE / PLAIN / KEY、grade()（器物的详略等级）、trifles()（寻常之物：取用不硬性返工、易手不成江湖事件）、
          card()（一件器物交给 LLM 的样子：寻常只有名字与方位，器物另有类别、描述与属性，要物到了主角手里连内容一起给）、feature()（一件景物）、
          nicknames()（够得着的器物的简称：「青钢剑」即剑架青钢剑——授意与体检都认得出玩家与导演说的是哪一件）、
          rooms()（近旁各处的景物与器物，暗藏的注明，供导演）、dossiers()（要物的内容与底细，供导演）
[POS]: world 层的布景读者面(v8 场景清单)——一处场景的建筑、景物、器物在创世时由 genesis 从 data/canon/18_scenes.json 布齐，
       此后它们的去留只经 effects 的指令流转(拾起即入随身、离手即落在原处，主角走了，原处便不再有它)；本模块把「此刻场景里有什么」
       翻成 LLM 读得懂的清单：眼前的交导演与编剧(编剧那份另过视角掩码)，隔壁与暗藏的、要物的内容与底细只交导演。纯读，不写世界
       v9：卡片另有数量(碎银二两、信笺二十张、残卷三张(全本十二张))、钱袋里有多少(只在主角手里时)、文书的样子(封着口、撕开的两份之一)、用途(书写、纸)；
       内容只给读得到的字(封着口的读不到、撕下的一份只有那几段)；近旁各处的器物只报名字、方位与数量，详情到了那里再看
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import scribe, situation, stock
from .effects import place, usable

GRADES = ("寻常", "器物", "要物")  # 与 genesis.GRADES 同一张表：寻常只有名字；器物带几样简单属性；要物详写，文书另有内容与底细
TRIFLE, PLAIN, KEY = GRADES
NICK = 2  # 简称至少两个字：「茶碗」可以，「碗」不行


def grade(world, item: str) -> str:
    """器物的详略：创世数据里没写等级的(原著抽取的那九十八件)按器物算。"""
    return world.graph.get(item, "grade") or PLAIN


def trifles(world) -> set[str]:
    g = world.graph
    return {n for n in g.where(type="item") if g.get(n, "grade") == TRIFLE}


def card(world, item: str, inside: bool = False) -> dict:
    """一件器物交给 LLM 的样子(形状恒定，缺的字段为空)：寻常之物只有名字与方位；器物另有类别、描述与几样属性；
    要物的内容(text)只在 inside——它在主角手里、主角读得到——时给出，摆在桌上的信不等于读过，封着口的信在手里也读不到。
    v9 另有：数量(amount：碎银二两、信笺二十张、残卷三张(全本十二张))、钱袋里有多少(purse，只在主角手里时)、文书的样子(doc：封着口、撕开的两份之一)、用途(uses：书写、纸)。"""
    g = world.graph
    out = {"name": item, "grade": grade(world, item), "spot": None if g.get(item, "holder") else g.get(item, "spot"),
           "kind": None, "desc": None, "props": {}, "text": None,
           "amount": stock.measure(g, item) or None, "purse": None, "doc": scribe.label(g, item), "uses": list(g.get(item, "uses") or [])}
    if out["grade"] != TRIFLE:
        out.update(kind=g.get(item, "kind"), desc=g.get(item, "desc"), props=dict(g.get(item, "props") or {}))
    if inside and stock.purse(g, item) > stock.EPS:
        out["purse"] = stock.say(stock.purse(g, item))
    if inside and (out["grade"] == KEY or g.get(item, "doc")):
        out["text"] = scribe.readable(g, item)
    return out


def feature(world, fid: str) -> dict:
    g = world.graph
    return {"name": fid, "desc": g.get(fid, "desc"), "state": g.get(fid, "state")}


def nicknames(world) -> dict[str, str]:
    """够得着的器物的简称：名字的后半截(两字起)——剑架青钢剑叫「青钢剑」、宾客茶碗叫「茶碗」、段誉折扇叫「折扇」。
    几件撞了简称，先认主角身上的，再认此地地上的、近旁地上的、身边之人手里的、暗藏的；同一档里仍撞了便不认(交器物近似名与校验)。"""
    g, close, around = world.graph, situation.near(world), situation.around(world)

    def rank(i) -> int | None:
        holder = g.get(i, "holder")
        if holder == "player":
            return 0
        if g.get(i, "hidden"):
            return 4
        if holder is None:
            return 1 if g.get(i, "location") == world.here else 2
        return 3 if holder in around else None
    pool: dict[str, list[tuple[int, str]]] = {}
    for i in g.where(type="item"):
        r = rank(i) if usable(world, i) and place(world, i) in close else None
        if r is not None:
            for k in range(1, len(i) - NICK + 1):
                pool.setdefault(i[k:], []).append((r, i))
    out = {}
    for short, cands in pool.items():
        cands.sort()
        if len(cands) == 1 or cands[0][0] < cands[1][0]:
            out[short] = cands[0][1]
    return out


def line(world, item: str) -> str:
    """后台里的一行：名字、方位、类别与属性(寻常之物只有名字与方位)。"""
    c = card(world, item)
    out = c["name"] + (f"（{c['spot']}）" if c["spot"] else "") + (f"｜{c['amount']}" if c["amount"] else "")
    if c["grade"] != TRIFLE:
        out += "".join(f"｜{x}" for x in (c["kind"], c["desc"]) if x)
        out += "".join(f"｜{k}：{v}" for k, v in c["props"].items())
    return out


def _short(world, item: str) -> str:
    """隔壁的一件东西只报名字、方位与数量(v9)：详情到了那里再看。"""
    g = world.graph
    cells = [x for x in (g.get(item, "spot"), stock.measure(g, item)) if x]
    return item + (f"（{'·'.join(cells)}）" if cells else "")


def rooms(world) -> list[str]:
    """近旁各处(主角此刻不在的那几间)有什么：景物、摆着的器物、暗藏的(注明藏法)——导演知道隔壁有什么，不必也不许凭空添置。"""
    g, out = world.graph, []
    for loc in sorted(situation.near(world) - {world.here}):
        feats = [f for f in g.where(type="feature", location=loc) if not g.get(f, "hidden")]
        items = [i for i in g.where(type="item", location=loc) if usable(world, i)]
        cells = [loc]
        cells += ["景物：" + "、".join(feats)] if feats else []
        cells += ["器物：" + "、".join(_short(world, i) for i in items if not g.get(i, "hidden"))] if any(not g.get(i, "hidden") for i in items) else []
        cells += ["暗藏：" + "；".join(f"{i}（{g.get(i, 'hint') or g.get(i, 'spot') or '藏而未露'}）" for i in items if g.get(i, "hidden"))] \
            if any(g.get(i, "hidden") for i in items) else []
        if len(cells) > 1:
            out.append("｜".join(cells))
    return out


def dossiers(world) -> list[str]:
    """要物的内容与底细(只给导演)：主角身上的、此地与近旁摆着或藏着的、身边之人手里的——拍里有人翻看它就照此写，不另编内容。"""
    g, close, around, out = world.graph, situation.near(world), situation.around(world), []
    for i in sorted(g.where(type="item")):
        if grade(world, i) != KEY or not usable(world, i):
            continue
        holder = g.get(i, "holder")
        if holder == "player" or holder in around or (holder is None and g.get(i, "location") in close):
            text, secret = scribe.readable(g, i, through_seal=True), g.get(i, "secret")  # 残卷与撕下的一份只有那几段(v9)
            if text or secret:
                out.append(f"{i}：" + "｜".join(x for x in (f"内容「{text}」" if text else "", f"底细：{secret}" if secret else "") if x))
    return out
