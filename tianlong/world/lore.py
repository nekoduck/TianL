"""
[INPUT]: 依赖 world/venue 的 venue_of / on_duty（场所与伙计当值）；World 门面(graph / atlas / player / here / done / canon / clock / knowledge，鸭子类型)；
         消息表由 world/founding 编进 atlas["lore"]
[OUTPUT]: 对外提供 within()（某处在不在那几处之内）、open_to()（知者口径：某人知不知道一处地方、一件东西、一条消息）、
          live()（消息此刻还算不算数：since 到期之后、until 结算之前）、entries()、tells()（某人知道而肯说的消息）、
          sources()（此处向谁、怎么打听得到哪几条，带价钱与条件）、heard()（主角听来的消息，真假照原样记）、learn()、hide()（开局常识去掉外人不知的处所与器物）
[POS]: world 层的消息与知者(v11 世界底座)——防剧透的第三条轴：层级只管多远还看得见，谁可以知道归明暗与知者。
       知者 known = {in 那一带的人, tags 行当, who 某人, faction 门内, item 写在哪件文书里}，满足一条即知道，不写即天下皆知；
       开局常识只有天下皆知的处所与器物——琅嬛福地只有李秋水、无崖子知道，主角要听人说起或亲身走到才知道有这么个地方。
       消息(闻·…)不是常识：说书人只从这里取消息给玩家——向店小二打探、问掌柜、听书、读书，谁知道、在哪里、要多少赏钱都在数据里；
       主角听来的消息照原样记(可以是假的，真相 truth 只给导演)，尚未到期(since)或已过时(until)的风声不算数。
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""


def within(g, loc: str | None, places) -> bool:
    """loc 在不在 places 之内(那一处本身或它下辖之处)。"""
    places = set(places or ())
    for _ in range(12):
        if loc is None:
            return False
        if loc in places:
            return True
        loc = g.get(loc, "parent")
    return False


def _tags(world, who) -> set:
    return set((world.player.get("tags") if who == "player" else world.graph.get(who, "tags")) or [])


def open_to(world, who: str, known: dict | None) -> bool:
    """知者口径：满足一条即知道——身在那一带、干那一行、就是那人、是那一门的人、读过(或拿着)那件文书。不写即天下皆知。"""
    if not known:
        return True
    g = world.graph
    loc = world.here if who == "player" else g.get(who, "location")
    if within(g, loc, known.get("in")):
        return True
    if _tags(world, who) & set(known.get("tags") or []):
        return True
    if who in (known.get("who") or []):
        return True
    faction = world.player.get("faction") if who == "player" else g.get(who, "faction")
    if faction and faction in (known.get("faction") or []):
        return True
    item = known.get("item")
    return bool(item) and (g.get(item, "holder") == who or who in ((g.get(item, "doc") or {}).get("read_by") or []))


def hide(world):
    """开局常识只含天下皆知的处所、景物与器物：外人不知的(写了 known 而主角不在其列)从认知里去掉，要听说或亲身走到才知道。"""
    g, beliefs = world.graph, world.knowledge.beliefs
    for nid in [n for n in beliefs if g.get(n, "known")]:
        if not open_to(world, "player", g.get(nid, "known")):
            del beliefs[nid]


def entries(world) -> dict:
    return (getattr(world, "atlas", None) or {}).get("lore") or {}


def _due(world, eid: str) -> bool:
    if eid in world.done:
        return True
    ev = next((e for e in world.canon if e["id"] == eid), None)
    return ev is not None and ev["day"] <= world.clock.day


def live(world, entry: dict) -> bool:
    """消息的时段：写了 since 的那一桩原著到期之后才传开；写了 until 的那一桩结算之后便过时(与人群的出没时段同一口径)。"""
    since, until = entry.get("since"), entry.get("until")
    return not (since and not _due(world, since)) and not (until and until in world.done)


def tells(world, who: str) -> list[str]:
    """某人知道而肯说(或被逼得出)的消息：有名之人的补注(tells)，连同按知者口径落到他身上的；此刻不算数的不说。"""
    out, table = [], entries(world)
    for lid in world.graph.get(who, "tells") or []:
        if lid in table and live(world, table[lid]):
            out.append(lid)
    for lid, entry in table.items():
        if lid not in out and live(world, entry) and (entry.get("known") or {}) and open_to(world, who, entry["known"]):
            out.append(lid)
    return out


def sources(world, people=None) -> list[dict]:
    """此处打听得到的消息：每条 {id, how, by, price, need}——在这处场所(或这一类场所)、向当值的那个职名或那个人；
    people 缺省为主角眼前的人。只列此刻算数、而主角还没听过的。"""
    from . import situation, venue
    g, here = world.graph, world.here
    shop = venue.venue_of(g, here)
    kinds = {x for x in (shop, g.get(shop, "venue") if shop else None, here) if x}
    people = sorted(situation.around(world)) if people is None else list(people)
    roles = {}
    for p in people:
        roles.setdefault(g.get(p, "role") or p, []).append(p)
    heard_ids, out = set(world.player.get("lore") or []), []
    for lid, entry in entries(world).items():
        if lid in heard_ids or not live(world, entry):
            continue
        for way in entry.get("get") or []:
            at, by = way.get("at"), way.get("by")
            if at not in kinds and not within(g, here, [at]):
                continue
            if by:
                who = roles.get(by) or ([by] if by in people else [])
            else:
                who = people[:1]
            who = [p for p in who if venue.on_duty(world, p)]
            if by and not who:
                continue
            out.append({"id": lid, "how": way.get("how"), "by": (who or [None])[0], "price": way.get("price") or 0,
                        "need": way.get("need")})
            break
    return out


def heard(world) -> list[str]:
    return list(world.player.get("lore") or [])


def learn(world, lid: str) -> bool:
    """主角听来一条消息：照原样记下(可以是假的)；已听过的不再记。"""
    if lid not in entries(world) or lid in (world.player.get("lore") or []):
        return False
    world.player.push("lore", lid)
    return True
