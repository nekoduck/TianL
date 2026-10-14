"""
[INPUT]: 依赖 world/situation 的 near / around（手边与在场）、world/stock 的 part / absorb / retire / qty / pages / full / base / cn（纸的消耗、撕与合）；World 门面（graph / player / clock / here）
[OUTPUT]: 对外提供 文书(v9 有限造物)——STATES / WRITTEN / SEALED / OPENED / TOOL / PAPER / TEXT_LEN、
          is_doc()、state()、literate()、tool()（手边有没有某样用途的东西：书写之具、纸）、
          write()（书写：识字、手边有笔墨与纸、内容定稿——写成即是一件新文书）、seal() / unseal()（封缄、拆封）、read()（阅读：读过的人记在 read_by）、
          tear()（撕开：一件文书撕成几份）、join()（拼合：手里同一文书的几份合回一件）、burn()（毁去：任何器物，烧毁砸碎即不复存在）、readable()（此刻读得到的字；导演看底细时可透过封口）、
          label()（文书此刻的样子：封着口、拆了封、撕开的几份之一）
[POS]: world 层唯一的造物通道，而且是一台确定的有限状态机——剧情不能凭空多出「一封信」，人物却真能提笔写一封：
       写之前须识字、手边有笔墨、有一张纸(纸少一张)，写成的那一件内容就是写下的字，此后不可再改；
       状态只沿 写成 → 封缄 → 拆封 走(封口一拆便回不去)，毁去即不复存在；撕开是分不是造(各是几分之一份，可散落各处)，拼合是合不是造(份数齐了即完整)。
       每一步都有前提，不成即返回缘由；id 由作者、收信人与文书的样子定(左子穆致辛双清书信、林舟的字条)，重名续编号——试演与定稿得到同一件；
       写的人这一拍正要走进去的那一间(also)，那里的纸笔也够得着
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import situation, stock

WRITTEN, SEALED, OPENED = "写成", "封缄", "拆封"
STATES = (WRITTEN, SEALED, OPENED)
TOOL, PAPER = "书写", "纸"       # 器物的用途(uses)：笔墨是书写之具，信笺是纸
TEXT_LEN = 200                   # 一封信至多写这么多字
DOC_KINDS = {"文书", "秘籍", "信物"}


def is_doc(g, item) -> bool:
    return g.kind(item) == "item" and (g.get(item, "kind") in DOC_KINDS or bool(g.get(item, "doc")) or bool(g.get(item, "text")))


def state(g, item) -> str:
    return (g.get(item, "doc") or {}).get("state") or WRITTEN


def literate(world, who) -> bool:
    return not (world.player.get("illiterate") if who == "player" else world.graph.get(who, "illiterate"))


def _where(world, who):
    return world.here if who == "player" else world.graph.get(who, "location")


def _usable(g, item) -> bool:
    st = g.get(item, "state")
    return not isinstance(st, dict) or (st.get("exists", True) and st.get("available", True))


def tool(world, who, use: str, also=()) -> str | None:
    """who 手边有没有派得上 use 用场的东西：自己手里的，或就摆在他所在之处而不是暗藏的——隔壁书案上的笔墨写不了这里的信。
    also：主角这一拍正要走去的地方(与取物同一口径：走进内堂提笔写信，写的是内堂书案上的纸笔)。"""
    g, spots = world.graph, {_where(world, who), *also}
    found = [i for i in g.where(type="item") if use in (g.get(i, "uses") or []) and _usable(g, i) and stock.qty(g, i) > stock.EPS
             and (g.get(i, "holder") == who or (g.get(i, "holder") is None and g.get(i, "location") in spots and not g.get(i, "hidden")))]
    return sorted(found, key=lambda i: (g.get(i, "holder") != who, i))[0] if found else None


def _held(world, who, item) -> bool:
    return world.graph.get(item, "holder") == who


def _handy(world, who, item) -> bool:
    g = world.graph
    reach = situation.near(world, _where(world, who)) if _where(world, who) else set()
    return _held(world, who, item) or (g.get(item, "holder") is None and g.get(item, "location") in reach and not g.get(item, "hidden"))


def _id(world, who, to, kind: str = "书信") -> str:
    g = world.graph
    author = world.player["name"] if who == "player" else who
    target = (world.player["name"] if to == "player" else to) if to else None
    root = f"{author}致{target}{kind}" if target else f"{author}的{kind}"
    k, nid = 1, root
    while g.has(nid):
        k += 1
        nid = f"{root}·{k}"
    return nid


def write(world, who, text, to=None, kind: str = "书信", also=()) -> tuple[list, str | None]:
    """书写：识字、手边有笔墨与纸、写下的字不为空——纸少一张，世上多一件文书，内容就是写下的字。"""
    g = world.graph
    text = str(text or "").strip()
    if not text:
        return [], "书写须写明内容：写下的字就是这件文书的内容，此后不可再改"
    if not literate(world, who):
        return [], f"{'主角' if who == 'player' else who}不识字，写不成"
    if to is not None and to != "player" and g.kind(to) != "person":
        return [], f"世上没有「{to}」这个人，信写给谁？"
    brush, paper = tool(world, who, TOOL, also), tool(world, who, PAPER, also)
    if not brush or not paper:
        return [], "手边" + "、".join(x for x, ok in (("没有笔墨", brush), ("没有纸", paper)) if not ok) + "，写不成"
    _spend(world, paper)
    nid = _id(world, who, to, kind)
    g.nodes[nid] = {"type": "item", "kind": "文书", "grade": "要物", "desc": f"一{'封' if kind == '书信' else '张'}墨迹新干的{kind}",
                    "text": text[:TEXT_LEN], "holder": who, "location": None, "hidden": False, "hint": None, "grants": None, "effect": None,
                    "state": {"exists": True, "available": True}, "qty": 1, "full": 1, "pages": [0], "base": nid,
                    "doc": {"state": WRITTEN, "form": kind, "author": who, "to": to, "day": world.clock.day, "read_by": [who]}}
    if who == "player":
        world.player.push("inventory", nid)
    return [{"op": "forge", "id": nid, "by": who, "to": to, "use": [brush, paper]}], None


def _spend(world, paper: str):
    """用掉一张纸：一叠纸少一张，最后一张用了这叠纸就没了。"""
    g = world.graph
    left = round(stock.qty(g, paper) - 1, 3)
    if left <= stock.EPS:
        stock.retire(world, paper)
    else:
        g.nodes[paper]["qty"] = left


def _doc(world, item):
    return world.graph.nodes[item].setdefault("doc", {"state": WRITTEN, "author": None, "to": None, "read_by": []})


def seal(world, who, item) -> tuple[list, str | None]:
    g = world.graph
    if not is_doc(g, item):
        return [], f"{item}不是文书，无从封缄"
    if not _held(world, who, item):
        return [], f"{item}不在{'你' if who == 'player' else who}手里"
    if state(g, item) != WRITTEN:
        return [], f"{item}已经{state(g, item)}，不能再封"
    _doc(world, item)["state"] = SEALED
    return [{"op": "doc", "id": item, "key": "state", "value": SEALED, "by": who}], None


def unseal(world, who, item) -> tuple[list, str | None]:
    g = world.graph
    if not is_doc(g, item) or state(g, item) != SEALED:
        return [], f"{item}并未封缄，无从拆封"
    if not _held(world, who, item):
        return [], f"{item}不在{'你' if who == 'player' else who}手里"
    _doc(world, item)["state"] = OPENED
    return [{"op": "doc", "id": item, "key": "state", "value": OPENED, "by": who}], None


def read(world, who, item) -> tuple[list, str | None]:
    """阅读：手里的或手边摆着的、没有封缄的文书——读过的人记在 read_by。"""
    g = world.graph
    if not is_doc(g, item):
        return [], f"{item}上没有字可读"
    if not _handy(world, who, item):
        return [], f"{item}不在{'你' if who == 'player' else who}手边"
    if state(g, item) == SEALED:
        return [], f"{item}封着口：拆封才读得到"
    seen = _doc(world, item).setdefault("read_by", [])
    if who not in seen:
        seen.append(who)
    return [{"op": "doc", "id": item, "key": "read_by", "value": who, "by": who}], None


def tear(world, who, item, k=None) -> tuple[list, str | None]:
    """撕开：手里一件完整的文书撕成 k 份(缺省两份)——各是几分之一份，内容按份切开，可散落各处、可再拼合。"""
    g = world.graph
    k = int(k or 2)
    if not is_doc(g, item):
        return [], f"{item}不是文书"
    if not _held(world, who, item):
        return [], f"{item}不在{'你' if who == 'player' else who}手里"
    if not 2 <= k <= 8:
        return [], "至多撕成八份"
    node = g.nodes[item]
    if stock.full(g, item) not in (None, 1) or len(stock.pages(g, item) or [0]) != 1:
        return [], f"{item}已是几份之一，或本是一叠纸：一张一张拿，不必撕"
    node.update(full=k, pages=list(range(k)), qty=k, torn=True, split=True, base=stock.base(g, item))
    out = []
    for _ in range(k - 1):  # 撕下来的每一份都另成一件(仍在撕的人手里)，原物留下第一份
        out.append(stock.part(world, item, 1, holder=who))
    return [{"op": "doc", "id": item, "key": "torn", "value": k, "by": who, "parts": [item, *out]}], None


def join(world, who, item) -> tuple[list, str | None, str]:
    """拼合：手里同一文书的几份合回一件；份数齐了即完整。返回 (记录, 缘由, 连带说明)。"""
    g = world.graph
    if not _held(world, who, item):
        return [], f"{item}不在{'你' if who == 'player' else who}手里", ""
    kin = [x for x in g.where(type="item", holder=who) if x != item and stock.base(g, x) == stock.base(g, item) and _usable(g, x)]
    if not kin:
        return [], f"手里没有{item}的另几份可拼", ""
    keep = stock.absorb(world, item, force=True)
    whole = not stock.fragment(g, keep)
    return [{"op": "doc", "id": keep, "key": "joined", "value": len(kin) + 1, "by": who}], None, \
        f"{keep}{'拼成了完整的一份' if whole else f'合在一起，仍缺几份（存{stock.cn(len(stock.pages(g, keep)))}份，全本{stock.cn(stock.full(g, keep))}份）'}"


def burn(world, who, item) -> tuple[list, str | None]:
    """毁去：手里或手边的一件器物烧毁、砸碎，此后不复存在。"""
    g = world.graph
    if g.kind(item) != "item" or not _usable(g, item):
        return [], f"{item}已不复存在"
    if not _handy(world, who, item):
        return [], f"{item}不在{'你' if who == 'player' else who}手边"
    stock.retire(world, item)
    return [{"op": "set", "id": item, "key": "state", "value": {"exists": False, "available": False}}], None


def label(g, item) -> str | None:
    """文书此刻的样子(交给 LLM 的卡片用)：封着口、拆了封、撕下的几份之一、残缺几份——不是文书即 None。"""
    if not is_doc(g, item):
        return None
    f, own = stock.full(g, item), stock.pages(g, item)
    cells = [] if state(g, item) == WRITTEN else [{SEALED: "封着口", OPENED: "拆了封"}[state(g, item)]]
    if g.get(item, "torn") and f and len(own) < f:
        cells.append(f"撕开的{stock.cn(f)}份之{stock.cn(len(own))}")
    return "、".join(cells) or None


def readable(g, item, through_seal: bool = False) -> str | None:
    """此刻读得到的字：封着口的读不到(导演看底细时 through_seal)；撕开的几份只读得到自己那几段；一叠只存几张的照录全文而注明残缺。"""
    text = g.get(item, "text")
    if not text or (state(g, item) == SEALED and not through_seal):
        return None
    f, own = stock.full(g, item), stock.pages(g, item)
    if not f or len(own) >= f:
        return text
    if g.get(item, "torn"):
        size = -(-len(text) // f)
        segs = [text[i * size:(i + 1) * size] for i in range(f)]
        return "……".join(segs[i] for i in sorted(own)) + "……（残）"
    return f"（残，存{stock.cn(len(own))}{g.get(item, 'unit') or '份'}，全本{stock.cn(f)}{g.get(item, 'unit') or '份'}）{text}"
