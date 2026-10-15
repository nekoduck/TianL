"""
[INPUT]: 依赖 world/effects 的 resolve / apply / place / usable / _handy / OFFSCREEN（唯一写入通道与它的物理）、world/stock（数量与银两）、world/crowd（人群规则）、
         world/scribe（文书状态机）、world/situation 的 around / near / party、world/access 的 exits、world/body 的 fate；较量预裁 rule 读 world/rag(用时才引)；World 门面
[OUTPUT]: 对外提供 事码(v9，LLM 说的类代码)——VERBS / ALIAS / RULE / RULED / SOFT / MONEY / FIELDS、
          is_act()、verb()、normalize()（动词归一、人地物落到 id、量与数读成数）、expand()（一批后果里，平常之事化为指令、规则之事留作一件事）、
          lower()（一件平常之事 → 既有的指令）、perform()（一件规则之事：前提、规则、执行，不成即返回缘由——什么也不动）、
          moves_player() / destination()（主角的去留：前往、脱身）、targets()（一件事碰到的实体：授意、体检、污染共用）、describe()（人话）
[POS]: world 层的类代码——导演与账房说同一种话：每一件事写成一条 {"做":动作, 字段…}，LLM 只宣告发生了什么，世界推导这意味着什么。
       一条事码是一个事务：前提不成(够不着、不在手里、不识字、手边没纸笔、力不及整群)即整条不成并说明缘由，数量(拿多少、剩多少、几个人倒下)由规则算；
       平常之事(去留、伤疗、关系、神色打算、识名、揭开、研习吸功)降为既有的十条指令照旧裁决，旧写法的指令也照收——事码是 LLM 的语言，指令是世界的微指令；
       规则之事(拿取、放下、交给、偷取、夺取、毁去、撕开、拼合、书写、封缄、拆封、阅读、脱身，以及对人群的杀死打晕)在这里执行，记录写成下游认得的形状
       (易手仍是 set holder / push inventory，银两是 money，人群是 squad，造物是 forge，文书是 doc)，恩怨、兑现原著、江湖事件照旧从记录里读
       偷得无人察觉的记录带 stealth(恩怨账不记)；夺取一个人身上的东西看较量预裁(rag.WIN 那几档才夺得下)，偷取看身法；书写用过的纸笔、拿过一部分的原物记作经手(turn["traded"])，
       主角这一拍正要走进去的那一间，那里的纸笔也够得着(与取物同一口径)
       v11 世界底座：市——买下、卖出、服用、打探、办事(服务名即事码：住宿、打尖、诊治……)交 world/trade 执行，花主角的钱须是玩家起意(MARKET)；
       v12：望见——隔着关口远远看见某人或一群人(situation.sightable)，记进本回合望见的人，不挪人不上名册；识名事码另可写「知」:「身份」——连来历一并说破，主角听见即识底；
       P1-7 脱身认围攻与押解(crowd.holders)：一样须过整群一半之力，冲得出去即了断那一条拘押；
       v11：所求写到某人身上即他的志向(agenda)——眼前的剧情改了谁的志向，他的原著线就此变了，往后的路交场外编剧；场外剧情(衍生事件)不写事码
       v13：伤人带出手者(by)，落多少血由 body.blow 按攻守档位封顶；拿取/夺取认 player 为一方(导演写 自=player 不再驳回)，自己手里的东西夺不得、已在他手里的不是一件事
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import access, body, crowd, effects, scribe, situation, stock, trade

# ============================================================
#  动词表：规范名 → 别名(模型常写的单字或口语)
# ============================================================
VERBS = {
    # 物：流转与文书
    "拿取": ("取", "拿", "拾", "拾取", "捡", "捡起", "拿起", "取出"), "放下": ("放", "丢下", "搁下", "放回"),
    "交给": ("给", "递给", "送给", "交付", "赠"), "偷取": ("偷", "窃取", "摸走"), "夺取": ("夺", "抢", "抢夺", "夺下"),
    "毁去": ("毁", "烧毁", "砸碎", "撕碎"), "撕开": ("撕", "撕成"), "拼合": ("合", "合拢", "拼"),
    "书写": ("写", "写信", "手书", "提笔"), "封缄": ("封", "封好", "封口"), "拆封": ("拆", "拆开"), "阅读": ("读", "看信", "阅", "翻看"),
    # 人：去留、身体、关系
    "前往": ("去", "走", "到", "移动"), "赶来": ("来", "到来", "赶到"), "脱身": ("逃", "突围", "逃脱", "冲出"),
    "伤人": ("伤", "打伤", "刺伤"), "疗伤": ("疗", "医", "治伤"), "杀死": ("杀", "击杀", "杀了"), "打晕": ("晕", "点倒", "打昏", "击晕"),
    "境况": ("境",), "结下": ("结", "立"), "了断": ("断", "解除"), "看法": ("看", "态度"),
    # 心：认知与软状态(v12 望见：隔着关口远远看见)
    "望见": ("望", "远望", "遥望", "瞥见"),
    "识名": ("名", "报名", "道名", "姓名"), "神色": ("色", "情绪"), "打算": ("意", "意图"), "外号": ("号", "叫法"),
    "揭开": ("揭", "找出", "发现"), "现状": ("景", "状态"), "应承": ("诺", "答应", "承诺"), "了结": ("了", "完结"),
    "所求": ("立志", "志向"),
    # 功
    "研习": ("习", "练", "求教"), "吸功": ("吸",),
    # 市(v11 世界底座)：买卖、服用、办事、打探——货架、价目、伙计与消息都在数据里
    "买下": ("买", "购买", "采买", "沽"), "卖出": ("卖", "出售", "变卖", "典当", "当掉"),
    "服用": ("服", "服下", "吃", "喝", "饮", "敷", "敷上"), "打探": ("打听", "探听", "听书", "问讯"),
    "办事": ("雇", "托办", "请办"),
}
ALIAS = {a: v for v, aliases in VERBS.items() for a in (v, *aliases)}
RULE = {"拿取", "放下", "交给", "偷取", "夺取", "毁去", "撕开", "拼合", "书写", "封缄", "拆封", "阅读", "脱身",
        "买下", "卖出", "服用", "打探", "办事", "望见"}  # 在这里执行的规则之事(v11 市：交 trade；v12 望见)
MARKET = {"买下", "卖出", "服用", "打探", "办事"}  # 花主角的钱、用主角的东西：须是玩家起意(授意)
RULED = {"伤人", "疗伤", "杀死", "打晕", "研习", "吸功"}  # 伤病生死、功力进境归规则：正文写了也改不了账(结算只记分歧)
SOFT = {"神色", "打算", "外号", "现状", "看法", "应承", "了结", "识名", "所求", "望见"}  # 不是物理：落不了只丢这一条，拍照常成立
MONEY = "银两"
FIELDS = ("谁", "物", "量", "与", "自", "对", "数", "到", "为", "文", "致", "处", "因", "添", "消", "听", "秘", "路", "血", "份", "直到", "事", "知")
ENTITY = ("谁", "与", "自", "对", "到", "致", "听")
ME = {"你", "主角", "player", "自己"}


def is_act(x) -> bool:
    return isinstance(x, dict) and "做" in x


def verb(x) -> str | None:
    return x.get("做") if is_act(x) else None


# ============================================================
#  规整：动词归一、人地物落到 id、量与数读成数
# ============================================================
def _resolve(world, name):
    if not isinstance(name, str):
        return name
    name = name.strip()
    if name in ME or name == world.player["name"]:
        return "player"
    hit = effects.resolve(world, name)
    if world.graph.has(hit):
        return hit
    g = world.graph  # 人群认叫法：「东宗弟子」「东宗弟子们」就是东宗弟子众
    squads = [s for s in g.where(type=crowd.GROUP) if crowd.is_squad(g, s)]
    return next((s for s in squads if name in (crowd.handle(g, s), s) or name.rstrip("们众") == crowd.handle(g, s)), hit)


def normalize(world, act: dict) -> dict:
    v = ALIAS.get(str(act.get("做") or "").strip(), str(act.get("做") or "").strip())
    out = {"做": v, **{k: act[k] for k in FIELDS if k in act and act[k] not in (None, "", [])}}
    if v not in ALIAS and v in ((getattr(world, "atlas", None) or {}).get("services") or ()):  # 服务名即事码(v11)：住宿、打尖、诊治、摆渡……
        out.update({"做": "办事", "事": v})
        v = "办事"
    for k in ENTITY:
        out[k] = _resolve(world, out[k]) if k in out else out.get(k)
        if out.get(k) is None:
            out.pop(k, None)
    if v == "望见" and "对" not in out and out.get("谁") not in (None, "player"):  # 望见写在「谁」上(v12)：望见的是他，望的人是主角
        out["对"], out["谁"] = out.pop("谁"), "player"
    out.setdefault("谁", "player")
    raw = out.get("物")
    if isinstance(raw, str):
        raw = raw.strip()
        squad_side = crowd.is_squad(world.graph, out.get("自"))
        if raw in stock.MONEY_WORDS:
            out["物"] = MONEY
        elif v in ("书写", "买下", "打探", "办事"):
            out["物"] = raw  # 写的是一种文书、货架上的一样货、打听的事——不是既有之物
        elif not squad_side:  # 从人群身上偷夺：物是他们身上那一样(长剑)，交 crowd 认
            out["物"] = _resolve(world, raw)
    money = out.get("物") == MONEY or stock.is_cash(world.graph, out.get("物")) or bool(stock.purse(world.graph, out.get("物")))
    if "量" in out:
        out["量"] = stock.amount(out["量"], money=money)
        if out["量"] is None:
            out.pop("量")
    for k in ("数", "血", "份"):
        if k in out:
            out[k] = stock.amount(out[k])
            if out[k] is None:
                out.pop(k)
    return out


def _squad(world, x) -> bool:
    return crowd.is_squad(world.graph, x)


def lower(world, a: dict) -> list[dict] | None:
    """一件平常之事 → 既有的指令(照旧经 effects 裁决)；规则之事返回 None，留给 perform。"""
    v, who = a["做"], a.get("谁", "player")
    to, val = a.get("对"), a.get("为")
    if v == "前往":
        return [{"op": "set", "id": who, "key": "location", "value": a.get("到")}]
    if v == "赶来":
        return [{"op": "arrive", "id": who}]
    if v == "伤人":  # v13 带上出手者(by)：落多少血由规则按攻守档位封顶（body.cap），「血」只是轻重
        return [{"op": "add", "id": to, "key": "hp", "value": -abs(a.get("血") or 10), **({"by": who} if who and who != to else {})}]
    if v == "疗伤":
        return [{"op": "add", "id": to or who, "key": "hp", "value": abs(a.get("血") or 10)}]
    if v == "境况":
        return [{"op": "push" if a.get("添") else "pull", "id": to or who, "key": "conditions", "value": a.get("添") or a.get("消")}]
    if v == "结下":
        return [{"op": "link", "src": who, "dst": to, "rel": val}]
    if v == "了断":
        return [{"op": "unlink", "src": who, "dst": to, "rel": val}]
    if v == "看法":
        return [{"op": "link", "src": who, "dst": to or "player", "rel": val, **({"note": a["因"]} if a.get("因") else {})}]
    if v == "识名":  # v12 「知」:"身份"——连来历一并说破，主角听见即识底(头衔、门派、关系)
        return [{"op": "reveal", "id": who, "key": "name", **({"to": a["听"]} if a.get("听") else {}),
                 **({"know": effects.KNOW} if a.get("知") == effects.KNOW else {})}]
    if v in ("神色", "打算", "外号"):
        return [{"op": "set", "id": who, "key": {"神色": "mood", "打算": "intent", "外号": "epithet"}[v], "value": val}]
    if v == "现状":
        return [{"op": "set", "id": to or a.get("物") or a.get("到"), "key": "state", "value": val}]
    if v == "揭开":
        if isinstance(a.get("路"), list) and len(a["路"]) == 2:
            return [{"op": "reveal", "src": _resolve(world, a["路"][0]), "dst": _resolve(world, a["路"][1]), "rel": "通路"}]
        if isinstance(a.get("秘"), list) and len(a["秘"]) == 3:
            src, rel, dst = a["秘"]
            return [{"op": "reveal", "src": _resolve(world, src), "rel": rel, "dst": _resolve(world, dst)}]
        return [{"op": "set", "id": a.get("物") or to, "key": "hidden", "value": False}]
    if v == "应承":
        goal = {"goal": val, "done_when": a["直到"]} if isinstance(a.get("直到"), list) else val
        return [{"op": "push", "id": "player", "key": "threads", "value": goal}]
    if v == "了结":
        return [{"op": "pull", "id": "player", "key": "threads", "value": val}]
    if v == "所求":  # 主角的所求；某人的所求即他的志向(v11：眼前的剧情改了他的志向，往后的路交场外编剧)
        return [{"op": "set", "id": who, "key": "goal" if who == "player" else "agenda", "value": val}]
    if v == "研习":
        return [{"op": "study", "id": "player", "value": a.get("物") or to}]
    if v == "吸功":
        return [{"op": "drain", "id": "player", "value": to}]
    if v == "杀死" and not _squad(world, to):
        return [{"op": "set", "id": to, "key": "status", "value": "dead"}]
    if v == "打晕" and not _squad(world, to):
        return [{"op": "push", "id": to, "key": "conditions", "value": "昏迷"}]
    return None


def expand(world, ops: list) -> list:
    """一批后果：平常之事化为指令，规则之事留作一件事(规整过的)，旧写法的指令原样照收。"""
    out = []
    for op in ops if isinstance(ops, list) else []:
        if not is_act(op):
            out.append(op)
            continue
        a = normalize(world, op)
        low = lower(world, a) if a["做"] in ALIAS else None
        out.extend(low if low is not None else [a])
    return out


# ============================================================
#  读：一件事动了谁、是不是主角的去留
# ============================================================
def moves_player(world, a) -> bool:
    return is_act(a) and a.get("做") == "脱身" and a.get("谁", "player") == "player"


def destination(a):
    return a.get("到") if is_act(a) else None


def targets(a) -> list[str]:
    return [a[k] for k in ("谁", "物", "与", "自", "对", "到") if isinstance(a.get(k), str)]


def _who(world, x) -> str:
    return "主角" if x in (None, "player") else str(x)


def describe(a: dict) -> str:
    """一件事的人话——回告编剧「什么没成立」、记进近事时用。"""
    v, who, item, n = a.get("做"), _who(None, a.get("谁")), a.get("物"), a.get("量")
    coin = item == MONEY or "银" in str(item)  # 碎银拿一两：说成「一两」，不说「一」(人话不读图，只看名字)
    thing = (stock.say(n) if item == MONEY and n else f"{item}" + (f"（{stock.say(n) if coin else stock.cn(n)}）" if n else "")) if item else "东西"
    src, to = a.get("自"), a.get("对")
    lines = {
        "拿取": f"{who}拿取{thing}", "放下": f"{who}放下{thing}", "交给": f"{who}把{thing}交给{_who(None, a.get('与'))}",
        "偷取": f"{who}从{src}身上偷取{thing}", "夺取": f"{who}从{src}手里夺取{thing}", "毁去": f"{who}毁去{item}",
        "撕开": f"{who}把{item}撕成{stock.cn(a.get('份') or 2)}份", "拼合": f"{who}拼合{item}",
        "书写": f"{who}写下一封{item or '书信'}" + (f"给{_who(None, a.get('致'))}" if a.get("致") else ""),
        "封缄": f"{who}封缄{item}", "拆封": f"{who}拆开{item}", "阅读": f"{who}阅读{item}",
        "脱身": f"{who}从{src or '围困'}中脱身" + (f"，往{a['到']}" if a.get("到") else ""),
        "杀死": f"{who}杀死{to}" + (f"{stock.cn(a['数'])}人" if a.get("数") else ""),
        "买下": f"{who}买下{thing}", "卖出": f"{who}卖出{thing}", "服用": f"{who}服用{item}" + (f"（给{to}）" if to else ""),
        "打探": f"{who}向{_who(None, a.get('与'))}打探" + (f"「{item}」" if item else ""), "办事": f"{who}请人办{a.get('事') or '事'}",
        "打晕": f"{who}打晕{to}" + (f"{stock.cn(a['数'])}人" if a.get("数") else ""),
    }
    return lines.get(v, f"{who}{v}{item or to or ''}")


# ============================================================
#  执行：规则之事——前提、规则、执行；不成即返回缘由，什么也不动
# ============================================================
def _present(world, who) -> bool:
    return who == "player" or who in situation.around(world)


def _where(world, who):
    return world.here if who == "player" else world.graph.get(who, "location")


def _reach(world, who, item, heading) -> bool:
    """够得着一件不在别人手里的东西：主角照 effects 的取物口径；旁人是他所在之处(及近旁)摆着而不是暗藏的。"""
    g = world.graph
    if who == "player":
        return effects._handy(world, item, heading)
    at = _where(world, who)
    return bool(at) and effects.place(world, item) in situation.near(world, at) and not g.get(item, "hidden")


def _trade(world, who, *items):
    """主角这一回合经手的东西(拿过一部分、交出一部分)：体检不把「拿起碎银而碎银还在地上」当作没拿。"""
    if who == "player" and getattr(world, "turn", None) is not None:
        world.turn.setdefault("traded", set()).update(i for i in items if i)


def _note(world, text: str):
    if text and getattr(world, "turn", None) is not None:
        world.turn.setdefault("notes", []).append(text)


def _hold_op(who, item) -> dict:
    return {"op": "push", "id": "player", "key": "inventory", "value": item} if who == "player" \
        else {"op": "set", "id": item, "key": "holder", "value": who}


def _move(world, ops) -> tuple[list, str | None]:
    ok, bad = effects.apply(world, ops, "director")
    return (ok, None) if not bad else ([], bad[0][1])


def _item(world, item) -> str | None:
    g = world.graph
    if not isinstance(item, str) or g.kind(item) != "item":
        return f"世上没有「{item}」这件器物"
    return None if effects.usable(world, item) else f"{item}已不复存在"


def _take(world, a, who, heading):
    g, item, n = world.graph, a.get("物"), a.get("量")
    if item == MONEY:
        return [], "银两在人身上或某件东西里：写从哪一件里拿(碎银、钱袋)，或写交给、偷取"
    why = _item(world, item)
    if why:
        return [], why
    holder = g.get(item, "holder")
    if holder not in (None, who):
        return [], f"{item}在{_who(world, holder)}手里：要么他交给，要么偷取、夺取"
    if holder is None and not _reach(world, who, item, heading):
        return [], f"{item}不在此地，够不着" + ("（暗藏着，要人到了那里才找得着）" if g.get(item, "hidden") else "")
    if stock.purse(g, item) > stock.EPS and n:  # 从钱袋里取钱：钱袋留着
        if n > stock.purse(g, item) + stock.EPS:
            return [], f"{item}里只有{stock.say(stock.purse(g, item))}"
        g.nodes[item]["purse"] = round(stock.purse(g, item) - n, 3)
        stock.earn(world, who, n)
        _trade(world, who, item)
        return [{"op": "money", "id": who, "value": n, "from": item}], None
    if stock.is_cash(g, item):  # 一堆碎银：拿多少，地上便少多少，拿光了这一堆就没了
        have = stock.qty(g, item)
        n = n or have
        if n > have + stock.EPS:
            return [], f"{item}只有{stock.say(have)}，拿不出{stock.say(n)}"
        g.nodes[item]["qty"] = round(have - n, 3)
        if g.nodes[item]["qty"] <= stock.EPS:
            stock.retire(world, item)
        else:
            g.nodes[item]["hidden"] = False
        stock.earn(world, who, n)
        _trade(world, who, item)
        return [{"op": "money", "id": who, "value": n, "from": item}], None
    have = stock.qty(g, item)
    if n is not None and n > have + stock.EPS:
        return [], f"{item}只有{stock.measure(g, item) or '一件'}，拿不出那么多"
    if n is not None and n < have - stock.EPS:
        if not stock.divisible(g, item):
            return [], f"{item}是整件的东西，分不开"
        nid = stock.part(world, item, n, holder=who)
        g.nodes[nid]["hidden"] = False
        _trade(world, who, item, nid)
        return [_hold_op(who, nid)], None
    if holder == who:
        return [], None  # 本就在手里：不是一件事
    done, why = _move(world, [_hold_op(who, item)])
    if not why:
        stock.absorb(world, item)
        _trade(world, who, item)
    return done, why


def _put(world, a, who, heading):
    g, item, n, spot = world.graph, a.get("物"), a.get("量"), str(a.get("处") or "")[:16] or None
    at = _where(world, who)
    if item == MONEY:
        if not n:
            return [], "放下多少银两？写量"
        if not stock.pay(world, who, n):
            return [], f"{_who(world, who)}身上只有{stock.say(stock.funds(world, who))}"
        pid = stock.pile(world, at, n, spot=spot)
        _trade(world, who, pid)
        return [{"op": "money", "id": who, "value": -n, "to": pid}], None
    why = _item(world, item)
    if why:
        return [], why
    if g.get(item, "holder") != who:
        return [], f"{item}不在{_who(world, who)}手里"
    if n is not None and n < stock.qty(g, item) - stock.EPS:
        if not stock.divisible(g, item):
            return [], f"{item}是整件的东西，分不开"
        nid = stock.part(world, item, n, location=at, spot=spot)
        _trade(world, who, item, nid)
        return [{"op": "set", "id": nid, "key": "location", "value": at}], None
    op = {"op": "pull", "id": "player", "key": "inventory", "value": item} if who == "player" else {"op": "set", "id": item, "key": "holder", "value": None}
    done, why = _move(world, [op])
    if not why:
        if spot:
            g.nodes[item]["spot"] = spot
        stock.absorb(world, item)
        _trade(world, who, item)
    return done, why


def _give(world, a, who, heading):
    g, item, n, to = world.graph, a.get("物"), a.get("量"), a.get("与")
    if to == who:
        return [], None
    if to != "player" and g.kind(to) != "person":
        return [], f"交给谁？「{to}」不是在场之人"
    if not _present(world, to):
        return [], f"{to}不在跟前，交不到他手里"
    if item == MONEY:
        if not n:
            return [], "交给多少银两？写量"
        if not stock.pay(world, who, n):
            return [], f"{_who(world, who)}身上只有{stock.say(stock.funds(world, who))}，给不出{stock.say(n)}"
        stock.earn(world, to, n)
        _trade(world, who, MONEY)
        return [{"op": "money", "id": to, "value": n, "from": who}], None
    why = _item(world, item)
    if why:
        return [], why
    if g.get(item, "holder") != who:
        return [], f"{item}不在{_who(world, who)}手里"
    if n is not None and n < stock.qty(g, item) - stock.EPS:
        if not stock.divisible(g, item):
            return [], f"{item}是整件的东西，分不开"
        nid = stock.part(world, item, n, holder=to)
        _trade(world, who, item, nid)
        return [{"op": "set", "id": nid, "key": "holder", "value": to}], None
    done, why = _move(world, [{"op": "set", "id": item, "key": "holder", "value": to}])
    if not why:
        stock.absorb(world, item)
        _trade(world, who, item)
    return done, why


def _grab(world, a, who, by: str):
    """偷取或夺取一个人身上的东西(人群另有规则)：偷看身法、夺看较量预裁；成了才动，东西交到 who 手里。"""
    g, src, item, n = world.graph, a.get("自"), a.get("物"), a.get("量")
    if src != "player" and g.kind(src) != "person":  # v13 主角也是被夺被偷的一方：司空玄从主角手里夺过通天草（第 8 回账房写的 自=player 曾被驳回为「不是在场之人」）
        return [], f"从谁身上{by}？「{src}」不是在场之人"
    if src == who:
        return [], None  # 自己拿自己的东西：不是一件事
    if not _present(world, src) or (who != "player" and not _present(world, who)):
        return [], f"{src}不在跟前"
    power = lambda x: world.player["power"] if x == "player" else g.get(x, "power")
    if by == "偷取":
        gap = crowd.agility(world, who) - crowd._tier(power(src))
        if not (gap >= 1 or (gap == 0 and body.fate(world) >= crowd.STEAL_ROLL)):
            return [], f"身法不及{src}：一伸手便被察觉——照预裁写成失手"
        done, why = _seize(world, a, who, src)
        return [{**r, "stealth": True} for r in done], why  # 偷得无人察觉：恩怨账上不记这一笔
    else:
        outcome, _ = body.rule(crowd._tier(power(src)) - crowd._tier(power(who)), body.fate(world))  # 较量预裁：与后台给导演看的同一张表、同一颗命运骰
        if outcome not in body.WIN:
            return [], f"夺不下来：与{src}交手的结局是「{outcome}」——照较量预裁演出"
    return _seize(world, a, who, src)


def _seize(world, a, who, src):
    """偷到了、夺下了：东西从 src 身上到 who 手里(银两从零钱与钱袋里出)。"""
    g, item, n = world.graph, a.get("物"), a.get("量")
    if item in (MONEY, None):
        have = stock.funds(world, src)
        take = min(n or have, have)
        if take <= stock.EPS:
            return [], f"{src}身上没有银两"
        stock.pay(world, src, take)
        stock.earn(world, who, take)
        _trade(world, who, MONEY)
        return [{"op": "money", "id": who, "value": take, "from": src}], None
    why = _item(world, item)
    if why:
        return [], why
    if g.get(item, "holder") == who:
        return [], None  # 本就在他手里（这一回合导演已交过手）：不是一件事，也不是分歧
    if g.get(item, "holder") != src:
        return [], f"{item}不在{src}身上"
    if n is not None and n < stock.qty(g, item) - stock.EPS and stock.divisible(g, item):
        nid = stock.part(world, item, n, holder=who)
        _trade(world, who, item, nid)
        return [_hold_op(who, nid)], None
    done, why = _move(world, [_hold_op(who, item)])
    if not why:
        stock.absorb(world, item)
        _trade(world, who, item)
    return done, why


def _steal(world, a, who, heading):
    src = a.get("自")
    if _squad(world, src):
        if src not in crowd.squads(world):
            return [], f"{crowd.handle(world.graph, src)}不在跟前"
        done, why = crowd.steal(world, who, src, a.get("物"), a.get("数") or a.get("量"))
        _trade(world, who, *(r.get("id") for r in done))
        return [{**r, "stealth": True} for r in done], why
    return _grab(world, a, who, "偷取")


def _rob(world, a, who, heading):
    src = a.get("自")
    if _squad(world, src):
        if src not in crowd.squads(world):
            return [], f"{crowd.handle(world.graph, src)}不在跟前"
        done, why = crowd.rob(world, who, src, a.get("物"), a.get("数") or a.get("量"))
        _trade(world, who, *(r.get("id") for r in done))
        return done, why
    return _grab(world, a, who, "夺取")


def _strike(world, a, who, heading):
    s = a.get("对")
    if s not in crowd.squads(world):
        return [], f"{crowd.handle(world.graph, s)}不在跟前"
    done, why, note = crowd.strike(world, who, s, a.get("数"), "dead" if a["做"] == "杀死" else "down")
    _note(world, note)
    return done, why


def _flee(world, a, who, heading):
    """脱身：被一群人围住(v12 或押着)，一方之力须过整群一半；冲得出去便了断那一条拘押、往去处(没写就往近处一条出路)。没人拘着就只是前往。"""
    g = world.graph
    hold = dict(crowd.holders(world, who))  # 围攻与押解(v12)
    src = a.get("自") if a.get("自") in hold else (next(iter(hold)) if hold else None)
    dest = a.get("到")
    if who == "player" and not dest:
        way = next((e for e in access.exits(world) if not e.get("back")), None) or next(iter(access.exits(world)), None)
        dest = way["name"] if way else None
    if src is None:
        return _move(world, [{"op": "set", "id": who, "key": "location", "value": dest}]) if dest else ([], "并无人围困：要去哪里，写到")
    why = crowd.escape(world, who, src)
    if why:
        return [], why
    rel = hold[src]
    g.unlink(src, who, rel)
    if not dest:
        return [{"op": "unlink", "src": src, "dst": who, "rel": rel}], None
    done, why = _move(world, [{"op": "set", "id": who, "key": "location", "value": dest}])
    if why:
        g.link(src, who, rel)
        return [], why
    return [{"op": "unlink", "src": src, "dst": who, "rel": rel}, *done], None


def _glimpse(world, a, who, heading):
    """望见(v12)：隔着悬崖、险径、水路远远看见某人或一群人(situation.sightable)——记进本回合望见的人(turn["sighted"]，按先后、不重复)；
    不挪人、不改名册、不产生指令记录、不算因果污染。就在眼前的原样不动；望不见的驳回(软的：只丢这一条)。"""
    g, x = world.graph, a.get("对")
    if x in situation.around(world) or (crowd.is_squad(g, x) and crowd.present(world, x)):
        return [], None
    if x not in situation.sightable(world):
        return [], f"{crowd.handle(g, x) if crowd.is_squad(g, x) else x}不在望得见的地方"
    if getattr(world, "turn", None) is not None and x not in world.turn.setdefault("sighted", []):
        world.turn["sighted"].append(x)
    return [], None


def _write(world, a, who, heading):
    kind = a.get("物") if a.get("物") in ("书信", "字条", "手书", "便笺") else "书信"
    to = a.get("致")
    done, why = scribe.write(world, who, a.get("文"), to=to if to in ("player",) or world.graph.kind(to) == "person" else None, kind=kind,
                             also=heading if who == "player" else ())  # 这一拍正要走进去的那一间：那里的纸笔也够得着
    for r in done:
        _trade(world, who, r["id"], *r.get("use", ()))  # 抄起笔墨、扯过一张信笺：用过的纸笔是经手之物，不当作「取得了却没到手」
    return done, why


def _join(world, a, who, heading):
    done, why, note = scribe.join(world, who, a.get("物"))
    _note(world, note)
    return done, why


HANDLERS = {
    "拿取": _take, "放下": _put, "交给": _give, "偷取": _steal, "夺取": _rob,
    "毁去": lambda w, a, who, h: scribe.burn(w, who, a.get("物")),
    "撕开": lambda w, a, who, h: scribe.tear(w, who, a.get("物"), a.get("份")),
    "拼合": _join, "书写": _write,
    "封缄": lambda w, a, who, h: scribe.seal(w, who, a.get("物")),
    "拆封": lambda w, a, who, h: scribe.unseal(w, who, a.get("物")),
    "阅读": lambda w, a, who, h: scribe.read(w, who, a.get("物")),
    "脱身": _flee, "杀死": _strike, "打晕": _strike, "望见": _glimpse,
    "买下": trade.buy, "卖出": trade.sell, "服用": trade.consume, "打探": trade.inquire, "办事": trade.serve,
}


def perform(world, a: dict, origin: str, scope=None, heading=frozenset()) -> tuple[list, str | None]:
    """一件规则之事落账：返回 (记录, 不成立的缘由)。场外剧情(衍生事件)不写事码：器物、人群与文书的规则之事只在主角跟前演(场外写既有的指令)；
    做这件事的人须在主角跟前(主角自己当然在)。"""
    v, who = a.get("做"), a.get("谁", "player")
    handler = HANDLERS.get(v)
    if handler is None:
        return [], f"不识的事码「{v}」：动作只用事码表里的那几个"
    if origin in effects.OFFSCREEN:
        return [], "场外剧情不写事码：器物、人群与文书的规则之事只在主角跟前演"
    if who != "player" and (world.graph.kind(who) != "person" or not _present(world, who)):
        return [], f"{who}不在你身边"
    return handler(world, a, who, heading)
