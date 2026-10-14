"""
[INPUT]: 只依赖 re；World 门面的 graph / player（鸭子类型）——被 effects / acts / crowd / scribe / scenery / growth 共用的最底层
[OUTPUT]: 对外提供 物量(v9)——
          qty() / unit() / full() / pages() / is_cash() / purse() / divisible() / fragment()：一件东西有多少、论什么、全本几份、是不是钱；
          amount()（「一两半」「三钱」「十二张」「两人」→ 数）、cn()（数 → 汉字）、say()（银两的说法：一两三钱）、measure()（器物的数量说法：二两、三张(全本十二张)）；
          pocket() / funds() / earn() / pay()：某人身上的银两(零钱 + 手里钱袋里的)，付出时先零钱后钱袋，不够即不成；
          part()：拿走一部分——原物只剩其余，拿走的那份另成一件(或并入接的人手里、落处地上同源的那一件)；absorb()：同源的几份合回一件(一叠图纸摞得起来自会合，撕开的信要人拼合)；
          materialize()：人群身上的东西(或别处的总数)化作一件实实在在的器物；pile()：放下的银两落在此地；retire()：一件东西用尽了；
          cap()：残卷能研习到第几阶；MONEY_WORDS / MONEY
[POS]: world 层的物量规则——凡有数量的东西(银两、碎银、瓜子、一叠十二张的图、撕成两半的信)在世界生成时就定了数，此后只流转不凭空：
       拿一两，地上剩一两；给出去，身上就少了；撕成两半各是半份，合起来又是一份。数在这里算，不由 LLM 报。
       一件可分之物的每一份都记着同源(base)：同源的几份落到同一个人手里或同一处地上即合回一件，全了便是完整的原物；
       银两是数不是器物：在人身上是零钱(pocket)或钱袋里的(purse)，在地上是一堆碎银(cash)——三处之间流转，总数守恒
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

MONEY = {"两": 1.0, "钱": 0.1, "分": 0.01, "文": 0.001}     # 银两的进位：一两十钱，一钱十分；铜钱千文作一两
MONEY_WORDS = {"银两", "银子", "钱", "银钱", "钱财", "铜钱", "金银", "碎银子"}  # 说的是身上的钱，不是某一件器物
EPS = 1e-6
STAGES = 3  # 研习的三阶(growth.STAGES)：残卷按所存的份数折算能到第几阶
_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_TENS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_NUM = r"[\d.]+|[零〇一二两三四五六七八九十百千万半]+"
_COIN = r"[\d.]+|[零〇一二三四五六七八九十百千万半]+|两(?=[两钱分文])"  # 银两里的「两」是单位，只有紧跟着单位时才是二(两钱)
_COUNT = re.compile(rf"^\s*({_NUM})")


# ============================================================
#  数：一件东西有多少
# ============================================================
def qty(g, item) -> float:
    q = g.get(item, "qty")
    return 1 if q is None else q


def unit(g, item) -> str:
    return g.get(item, "unit") or ("两" if g.get(item, "cash") else "件")


def is_cash(g, item) -> bool:
    return bool(g.get(item, "cash"))


def purse(g, item) -> float:
    return g.get(item, "purse") or 0


def divisible(g, item) -> bool:
    """拿得出一部分的东西：碎银、一把瓜子、一叠纸；一柄剑、一本簿子只有整件。"""
    return bool(g.get(item, "split")) or is_cash(g, item)


def full(g, item) -> int | None:
    """全本几份(文书与秘籍)：没有即不是一部可分的书。"""
    return g.get(item, "full")


def pages(g, item) -> list[int]:
    return list(g.get(item, "pages") or [])


def fragment(g, item) -> bool:
    """残卷：一部书只存其中几份。"""
    f = full(g, item)
    return bool(f) and len(pages(g, item)) < f


def cap(g, item) -> int:
    """残卷能研习到第几阶：全本三阶；存一半只到初窥，存三分之二到小成——功夫只在书上有的那几页里。"""
    f = full(g, item)
    if not f:
        return STAGES
    return max(1, STAGES * len(pages(g, item)) // f)


# ============================================================
#  说法：数 ↔ 汉字
# ============================================================
def _cn(s: str) -> float | None:
    if re.fullmatch(r"[\d.]+", s):
        try:
            return float(s)
        except ValueError:
            return None
    if s == "半":
        return 0.5
    total, cur = 0, 0
    for ch in s:
        if ch in _DIGITS:
            cur = _DIGITS[ch]
        elif ch in _TENS:
            total += (cur or 1) * _TENS[ch]
            cur = 0
        else:
            return None
    return total + cur


def amount(x, money: bool = False) -> float | None:
    """「一两半」「二两」「两两」「三钱」「五分」→ 两；「十二张」「三」「两人」「半」→ 数。读不出即 None(当作没写，缺省为全部)。"""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x) if x > 0 else None
    if not isinstance(x, str) or not x.strip():
        return None
    s = x.strip().replace(" ", "")
    s = re.sub(r"^两两", "二两", s)
    pairs = re.findall(rf"({_COIN})(两|钱|分|文)(半)?", s)
    if pairs and (money or any(u in ("钱", "分", "文") for _, u, _ in pairs) or s.endswith(("两", "两半"))):
        total = 0.0
        for num, u, half in pairs:
            v = _cn(num)
            if v is None:
                return None
            total += v * MONEY[u] + (0.5 * MONEY[u] if half else 0)
        return round(total, 3) if total > 0 else None
    m = _COUNT.match(s)
    v = _cn(m.group(1)) if m else None
    return v if v and v > 0 else None


def cn(n: float) -> str:
    """数 → 汉字：3 → 三、12 → 十二、20 → 二十、0.5 → 半。"""
    if abs(n - 0.5) < EPS:
        return "半"
    n = int(round(n))
    if n <= 0:
        return "零"
    digits, out = "零一二三四五六七八九", ""
    for value, name in ((10000, "万"), (1000, "千"), (100, "百"), (10, "十")):
        if n >= value:
            head, n = divmod(n, value)
            out += ("" if value == 10 and head == 1 and not out else digits[head]) + name
            if 0 < n < value // 10:
                out += "零"
    return out + (digits[n] if n else "")


def say(liang: float) -> str:
    """银两的说法：1.3 → 一两三钱、0.3 → 三钱、2 → 二两、0 → 分文全无。"""
    fen = int(round(liang * 100))
    if fen <= 0:
        return "分文全无"
    l, rest = divmod(fen, 100)
    q, f = divmod(rest, 10)
    out = (cn(l) + "两" if l else "") + (cn(q) + "钱" if q else "") + (cn(f) + "分" if f else "")
    return out or "分文全无"


def measure(g, item) -> str:
    """一件器物的数量说法：碎银「二两」、一叠「十二张」、残卷「三张（全本十二张）」；单件无须说数即空。"""
    if is_cash(g, item):
        return say(qty(g, item))
    q, f = qty(g, item), full(g, item)
    if f and len(pages(g, item)) < f:
        return f"{cn(len(pages(g, item)))}{unit(g, item)}（全本{cn(f)}{unit(g, item)}）"
    return f"{cn(q)}{unit(g, item)}" if abs(q - 1) > EPS or unit(g, item) != "件" or (f and f > 1) else ""


# ============================================================
#  银两：零钱(pocket) + 手里钱袋里的(purse)
# ============================================================
def pocket(world, who) -> float:
    if who == "player":
        return world.player.get("money", 0) or 0
    return world.graph.get(who, "money") or 0


def _set_pocket(world, who, value: float):
    value = round(max(0.0, value), 3)
    if who == "player":
        world.player.set("money", value)
    else:
        world.graph.nodes[who]["money"] = value


def purses(world, who) -> list[str]:
    g = world.graph
    return sorted(i for i in g.where(type="item", holder=who) if purse(g, i) > EPS and _usable(g, i))


def funds(world, who) -> float:
    """某人身上的银两：零钱加上他手里钱袋里的。"""
    return round(pocket(world, who) + sum(purse(world.graph, i) for i in purses(world, who)), 3)


def earn(world, who, a: float):
    _set_pocket(world, who, pocket(world, who) + a)


def pay(world, who, a: float) -> bool:
    """付出 a 两：先零钱、后钱袋；不够即不成(什么也不动)。"""
    if funds(world, who) + EPS < a:
        return False
    take = min(pocket(world, who), a)
    _set_pocket(world, who, pocket(world, who) - take)
    a -= take
    for i in purses(world, who):
        if a <= EPS:
            break
        out = min(purse(world.graph, i), a)
        world.graph.nodes[i]["purse"] = round(purse(world.graph, i) - out, 3)
        a -= out
    return True


# ============================================================
#  分与合：拿走一部分另成一件，同源的几份合回一件
# ============================================================
def _usable(g, item) -> bool:
    state = g.get(item, "state")
    return not isinstance(state, dict) or (state.get("exists", True) and state.get("available", True))


def base(g, item) -> str:
    return g.get(item, "base") or item


def _fresh(g, root: str) -> str:
    k = 1
    while g.has(f"{root}·{k}"):
        k += 1
    return f"{root}·{k}"


def _place(world, holder, location, spot):
    return {"holder": holder, "location": None if holder else location, "spot": None if holder else (spot or "地上")}


def _take_in(world, item: str, holder):
    if holder == "player":
        world.player.push("inventory", item)


def retire(world, item: str):
    """一件东西用尽了(碎银拿光、几份都并进了别处)：不删节点(读档不复活、id 永远认得)，只是世上不再有它。"""
    node = world.graph.nodes[item]
    if node.get("holder") == "player":
        world.player.pull("inventory", item)
    node.update(qty=0, holder=None, location=None, spot=None, state={"exists": False, "available": False})
    if "pages" in node:
        node["pages"] = []


def _same(g, a: str, b: str) -> bool:
    return a != b and base(g, a) == base(g, b) and _usable(g, b)


def _at(g, item, holder, location) -> bool:
    return g.get(item, "holder") == holder if holder else (g.get(item, "holder") is None and g.get(item, "location") == location)


def merge(world, dst: str, src: str):
    """src 并进 dst：数目相加、所存的份合在一起(全了即是完整的原物)；src 用尽。"""
    g = world.graph
    a, b = g.nodes[dst], g.nodes[src]
    if "pages" in a or "pages" in b:
        a["pages"] = sorted(set(a.get("pages") or []) | set(b.get("pages") or []))
        a["qty"] = len(a["pages"])
    else:
        a["qty"] = round(qty(g, dst) + qty(g, src), 3)
    if purse(g, src):
        a["purse"] = round(purse(g, dst) + purse(g, src), 3)
    retire(world, src)


def absorb(world, item: str, force: bool = False) -> str:
    """同源的几份落到同一人手里或同一处地上即合回一件：留下原物的 id(它在就用它)，返回合成之后的那一件。
    银两、瓜子、剑、一叠图纸这样摞得起来的东西自会合在一起；撕开的信是各自的一片，要人拼合(force)才合。"""
    g = world.graph
    if not g.has(item) or not _usable(g, item) or (g.get(item, "torn") and not force):
        return item
    holder, location = g.get(item, "holder"), g.get(item, "location")
    kin = [x for x in g.where(type="item") if _same(g, item, x) and _at(g, x, holder, location)]
    if not kin:
        return item
    group = [item, *kin]
    keep = base(g, item) if base(g, item) in group else sorted(group)[0]
    for x in group:
        if x != keep:
            merge(world, keep, x)
    return keep


def part(world, item: str, n: float, holder=None, location=None, spot=None) -> str:
    """从 item 里分出 n(数目或银两，文书取其前 n 份)交给 holder 或落在 location；返回接到这一份的那一件(并入了同源的就是那一件)。
    调用方先核过 0 < n < 原数、而且可分。"""
    g = world.graph
    src = g.nodes[item]
    node = {k: v for k, v in src.items() if k not in ("holder", "location", "spot", "qty", "pages", "purse")}
    node.update(base=base(g, item), **_place(world, holder, location, spot))
    if "pages" in src:
        moved = sorted(src["pages"])[:int(n)]
        src["pages"] = [p for p in src["pages"] if p not in moved]
        src["qty"] = len(src["pages"])
        node.update(pages=moved, qty=len(moved))
    else:
        src["qty"] = round(qty(g, item) - n, 3)
        node["qty"] = round(n, 3)
    nid = _fresh(g, node["base"])
    g.nodes[nid] = node
    _take_in(world, nid, holder)
    return absorb(world, nid)


def materialize(world, root: str, template: dict, n: float, holder=None, location=None, spot=None) -> str:
    """别处的总数(人群身上的十五柄剑)化作一件实实在在的器物：root 这件还没有就立它，有了而不在这里就另立同源的一份，
    最后与接的人手里、落处地上同源的那件合起来。这是流转，不是新造——东西本来就在那十五个人身上。"""
    g = world.graph
    node = {"type": "item", "kind": "杂物", "grade": "器物", "desc": None, "hidden": False, "hint": None, "grants": None,
            "effect": None, "state": {"exists": True, "available": True}, "split": True, **template,
            "base": root, "qty": round(n, 3), **_place(world, holder, location, spot)}
    nid = root if not g.has(root) else _fresh(g, root)
    if g.has(root) and not _usable(g, root):  # 原物早已用尽：就地复用它的 id
        nid = root
    g.nodes[nid] = node
    _take_in(world, nid, holder)
    return absorb(world, nid)


def pile(world, location: str, a: float, spot=None) -> str:
    """放下的银两落在此地：并进此地地上的一堆碎银，没有就堆成一堆(id 随地名：宫门碎银)。"""
    g = world.graph
    spot = spot or "地上"  # 同一处地上、同一个方位的碎银才算一堆：倒地弟子怀里的钱不并进宾客椅下那几块
    heap = next((i for i in sorted(g.where(type="item", location=location)) if is_cash(g, i) and g.get(i, "holder") is None
                 and (g.get(i, "spot") or "地上") == spot), None)
    if heap is not None:
        node = g.nodes[heap]
        node.update(qty=round((qty(g, heap) if _usable(g, heap) else 0) + a, 3), state={"exists": True, "available": True})
        return heap
    root = f"{location.split('·')[-1]}碎银"
    template = {"kind": "杂物", "desc": "一小堆碎银子", "cash": True, "unit": "两"}
    return materialize(world, root, template, a, location=location, spot=spot)
