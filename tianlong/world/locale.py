"""
[INPUT]: 依赖 world/venue（场所、货架、伙计当值）、world/lore（消息与知者）、world/situation 的 around、world/perspective 的 handle、world/stock（银两说法）；
         World 门面(graph / atlas / player / here / clock，鸭子类型)
[OUTPUT]: 对外提供 此地的世情(v11 世界底座的读者面)——shop()（此处的铺子：招牌、开闭、当值的伙计、货架价目、能办的事、招工；writer=True 只给看得见的那几样）、
          asks()（此处向谁、怎么打听得到哪几条，连同在场有名之人知道而肯说的——给导演，假的附真相）、
          law()（此地归哪一国：官差多久赶到、几条律条、宵禁，在场门派的规矩）、season()（四季气候、此地的险、节令集期）、
          traits()（在场有名之人的名声、好恶软肋、手段底线、能替人做的事、通晓的言语）、heard()（主角听来的消息，照原样）、polity()、SEASONS
[POS]: world 层的世情读者面——近大远小的「眼前」一层：主角所在之处的铺子、伙计、价目、消息、国法、天时，导演看全、编剧看明处；
       纯读，不写世界(打听、买卖、服务由 world/trade 执行)。千里之外的不在这里(远处只给公论，见 rag 的远景)。
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from . import lore, perspective, situation, stock, venue

SEASONS = ("春", "春", "春", "夏", "夏", "夏", "秋", "秋", "秋", "冬", "冬", "冬")  # 正月至三月为春(4.6)
CN_MONTH = ("正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "腊")


def _chain(world, loc) -> list[str]:
    g, out = world.graph, []
    for _ in range(12):
        if loc is None:
            break
        out.append(loc)
        loc = g.get(loc, "parent")
    return out


def polity(world, loc=None) -> str | None:
    g = world.graph
    return next((g.get(x, "polity") for x in _chain(world, loc or world.here) if g.get(x, "polity")), None)


def _season(world) -> str:
    return SEASONS[world.clock.month % 12]


# ============================================================
#  铺子：招牌、开闭、伙计、货架、能办的事、招工
# ============================================================
def shop(world, writer: bool = False) -> dict | None:
    g = world.graph
    vid = venue.venue_of(g, world.here)
    sp = venue.spec(world, vid) if vid else None
    if not sp:
        return None
    goods = world.atlas.get("goods") or {}
    sign = g.get(vid, "sign")
    wares = []
    for gid, w in venue.wares(world, vid).items():
        unit = (goods.get(gid) or {}).get("unit") or "件"
        line = f"{gid[2:]}：{stock.say(w['price'])}一{unit}"
        if w["stock"] is not None and w["stock"] <= stock.EPS:
            line += "（卖完了）"
        elif w["stock"] is not None and not writer:
            line += f"（存{stock.cn(w['stock'])}{unit}{'，每日补' if w.get('restock') else ''}）"
        wares.append(line)
    around = situation.around(world)
    services = []
    for s in sp["services"]:
        here_on = [p for p in s["by"] if p in around and venue.on_duty(world, p)]
        line = f"{s['name']}：{stock.say(s['price']) if s['price'] else '不收钱'}" + (f"一{s['per']}" if s.get("per") and s["price"] else "") \
            + f"（{s['role']}办" + ("" if here_on else "，此刻不在跟前或不当值") + (f"；{s['time']}" if s.get("time") else "") + "）" \
            + (f"｜须{s['need']}" if s.get("need") else "") \
            + (f"｜{'住' if s['name'] in ('住宿', '借宿') else '在'}{s['room'].rpartition('·')[2]}" if s.get("room") else "")
        services.append(line)
    out = {"name": vid, "sign": sign, "type": g.get(vid, "venue"), "hours": g.get(vid, "hours"),
           "wares": wares, "services": services}
    if writer:
        return out
    staff = []
    for s in sp["staff"]:
        pid = s["id"]
        if not g.has(pid) or g.get(pid, "status") == "dead":
            continue
        duty = "当值" if venue.on_duty(world, pid) else f"不当值（{g.get(pid, 'hours')}当值）"
        staff.append(f"{perspective.handle(world, pid)}（{pid}）：{s.get('role')}｜{duty}｜在{g.get(pid, 'location')}"
                     + (f"｜能办：{'、'.join(g.get(pid, 'services') or [])}" if g.get(pid, "services") else "")
                     + (f"｜知道：{'、'.join(g.get(pid, 'tags') or [])}的消息" if g.get(pid, "tags") else ""))
    out.update(staff=staff, jobs=[f"{j.get('job')}：{stock.say(j.get('pay') or 0)}一{j.get('per') or '日'}" + (f"（{j['need']}）" if j.get("need") else "")
                                  for j in sp["jobs"]],
               till=stock.say(stock.qty(g, f"{vid}·柜银")) if g.has(f"{vid}·柜银") else None)
    return out


# ============================================================
#  消息：此处打听得到的，在场有名之人肯说的
# ============================================================
def _line(entry: dict) -> str:
    text = f"「{entry.get('text')}」"
    if entry.get("true") is not True:
        text += f"（{'假的' if entry.get('true') is False else '半真半假'}；真相：{entry.get('truth')}）"
    return text


def asks(world, limit: int = 6) -> list[str]:
    g, table, out = world.graph, lore.entries(world), []
    for s in lore.sources(world)[:limit]:
        who = f"{perspective.handle(world, s['by'])}（{s['by']}）" if s["by"] else "此处"
        out.append(f"向{who}{s.get('how') or '打探'}，赏钱{stock.say(s['price']) if s['price'] else '不必'}"
                   + (f"，须{s['need']}" if s.get("need") else "") + f"：{_line(table[s['id']])}")
    heard = set(lore.heard(world))
    for p in sorted(situation.around(world)):
        if g.get(p, "staff"):
            continue
        told = [lid for lid in lore.tells(world, p) if lid not in heard][:2]
        out += [f"{p}知道而肯说(要看交情与处境)：{_line(table[lid])}" for lid in told]
    return out[:limit + 4]


def heard(world, limit: int = 6) -> list[str]:
    """主角听来的消息：照原样(可以是假的)，近的在后。"""
    table = lore.entries(world)
    return [table[lid]["text"] for lid in lore.heard(world)[-limit:] if lid in table]


# ============================================================
#  国法与规矩、天时、人物底子
# ============================================================
def law(world) -> list[str]:
    g, atlas = world.graph, world.atlas or {}
    pid = polity(world)
    entry = (atlas.get("polities") or {}).get(pid)
    out = []
    if entry:
        chain = _chain(world, world.here)
        forms = {g.get(x, "form") for x in chain}
        officers = [o for o in entry.get("officers") or [] if set(o.get("at") or []) & (forms | set(chain))]
        out += [f"{pid}的{o['role']}：一处{stock.cn(o.get('count') or 0)}人，出了事{o.get('respond')}赶到（门下模板「{o.get('kit')}」）" for o in officers]
        laws = entry.get("laws") or []
        out.append(f"{pid}律条：" + "；".join(f"{x['crime']}——{x['punish']}（{x.get('pursue')}）" for x in laws[:5]))
        if entry.get("curfew"):
            out.append(f"宵禁：{entry['curfew']}")
    factions = {g.get(p, "faction") for p in situation.around(world)} - {None}
    rules = [r for r in (atlas.get("rules") or {}).values() if isinstance(r.get("who"), list) and set(r["who"]) & factions]
    out += [f"{r['rule']}（{'、'.join(r['who'])}）：{r['text']}；坏了规矩{r.get('breach')}" for r in rules[:3]]
    return out


def season(world) -> list[str]:
    g, nature = world.graph, (world.atlas or {}).get("nature") or {}
    chain, now = _chain(world, world.here), _season(world)
    places = set(chain) | {polity(world)}
    out = []
    climate = next((c for at in [*chain, polity(world)] for c in nature.get("climate") or [] if c.get("at") == at), None)
    if climate:
        out.append(f"{now}：{(climate.get('seasons') or {}).get(now)}")
    month = CN_MONTH[world.clock.month % 12]
    day = world.clock.day % 30 + 1
    for f in nature.get("festivals") or []:
        when = str(f.get("when") or "")
        if places & set(f.get("at") or []) and when.startswith(month) and (when == f"{month}月" or when.endswith(f"{_cn_day(day)}")):
            out.append(f"节令·{f['name']}：{f.get('what')}（人流{f.get('bustle')}）")
    out += [f"集期：{m.get('when')}——{m.get('what')}" for m in nature.get("markets") or [] if m.get("at") in places]
    near = situation.near(world)
    out += [f"险·{h['id'][2:]}（{h.get('chance')}）：{h.get('harm')}；避法：{h.get('avoid')}" for h in nature.get("hazards") or []
            if now in (h.get("when") or []) and set(h.get("at") or []) & (near | set(chain))]
    return out


def _cn_day(d: int) -> str:
    digits = "零一二三四五六七八九十"
    return digits[d] if d <= 10 else ("十" + digits[d - 10] if d < 20 else ("二十" if d == 20 else ("廿" + digits[d - 20] if d < 30 else "三十")))


def traits(world) -> list[str]:
    """在场有名之人的底子(导演拿来打动、激怒、要挟他)：名声、好恶软肋、惯用手段与底线、能替人做的事、通晓的言语。隐情不在这里。"""
    g, out = world.graph, []
    for p in sorted(situation.around(world)):
        if g.get(p, "staff") or g.kind(p) != "person":
            continue
        cells = [("名声", g.get(p, "fame")), ("好", "、".join(g.get(p, "likes") or [])), ("恶", "、".join(g.get(p, "dislikes") or [])),
                 ("软肋", "、".join(g.get(p, "soft") or [])), ("手段", "、".join(g.get(p, "means") or [])),
                 ("底线", "、".join(g.get(p, "limits") or [])),
                 ("能替人做", "、".join(s.get("name", "") + (f"({s['skill']})" if s.get("skill") else "") + (f"({s['level']})" if s.get("level") else "")
                                        for s in g.get(p, "services") or [])),
                 ("言语", "、".join(t for t in g.get(p, "tongues") or [] if t != "汉话")), ("作息", g.get(p, "routine"))]
        line = "｜".join(f"{k}：{v}" for k, v in cells if v)
        if line:
            out.append(f"{p}：{line}")
    return out
