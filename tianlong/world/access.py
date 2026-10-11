"""
[INPUT]: 依赖 world/graph 的 matches / ROAD，依赖 World 门面的 graph / knowledge / player / here（鸭子类型）
[OUTPUT]: 对外提供 barrier()（一步为何走不通）、stranded()（是否身陷绝境）、distances()（主角可走的里程）、walk()（主角远行的实际路线与止步缘由）、learn()（走过的路就认得）、
          exits()（主角眼中的出路）、steps()（场外人物可去的相邻地）、passes()（此地出发的关口，供导演）、secret_ways()（近处未被发现的暗路，供导演）、
          hidden()（道路是否藏有暗路）
[POS]: world 层的通行裁判——道路是地理，通行是物理与认知：blocked 与 requires 由系统硬判、拦住所有人（唯一的例外是主角身陷绝境——
       此地除不通之路外别无出路，如坠入谷底——此时不通之路交导演以奇遇兑现，世界不会把主角永远困死）；hidden 只拦尚未发现它的主角，
       暗路被剧情 reveal 或被主角走过之后按整条道路记入认知账本；how/risk 只能文字描述，交导演在剧情里兑现。
       主角远行：第一步的关导演已在后台看见、可在本回合兑现；途中的关一笔带过（原著某一阶段的情形未必是此刻的情形）；
       目的地门前的关（通往目的地，或与目的地同在 0 日一簇）与绝路则止步于前，留给下一回合的导演——门前之关必成一场戏。传闻与 LOD 分层仍按纯地理
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from .graph import ROAD, matches

STATE_WORDS = {"exists": "存在", "accessible": "可通行"}
LOST = "找不到去路"  # 未被发现的暗路对主角而言就是无路：缘由里不泄露它的存在与去向


def _gate(edge: dict, to: str) -> dict | None:
    return (edge.get("gates") or {}).get(to)


def hidden(edge: dict) -> bool:
    return any(g["hidden"] for g in (edge.get("gates") or {}).values())


def _need(nid: str, key: str, want) -> str:
    """一条硬前提的人话：某处须存在且可通行、主角须有某武学/器物、某人的某属性须为某值。"""
    who = "主角" if nid == "player" else nid
    if key == "state" and isinstance(want, dict):
        return who + "须" + "且".join(("" if v else "不") + STATE_WORDS.get(k, k) for k, v in want.items())
    if key in ("skills", "inventory"):
        return f"{who}须有{want}"
    return f"{who}的{key}须为{want}"


def barrier(world, a: str, b: str, edge: dict, player: bool = True, strict: bool = False) -> str | None:
    """a→b 这一步为何走不通；None 即可走。认知先于物理：主角不知其存在的暗路，连撞墙的机会都没有。
    此路不通拦所有人，唯主角身陷绝境时网开一面（strict 即不开这一面，供判定绝境本身）。"""
    gate = _gate(edge, b)
    if not gate:
        return None
    if player and gate["hidden"] and not _known(world, edge):
        return LOST
    if gate["blocked"] and (strict or not player or not stranded(world, a)):
        return f"此路不通（{gate['kind']}）：{gate['how']}"
    value = lambda nid, key: world.player.get(key) if nid == "player" else world.graph.get(nid, key)
    lack = [_need(*r) for r in gate["requires"] if not matches(value(r[0], r[1]), r[2])]
    return f"条件未备：{'；'.join(lack)}" if lack else None


def _known(world, edge: dict) -> bool:
    """主角认得这条暗路吗——两个朝向都算：数据日后翻转了道路的存储朝向，主角也不会忘了走过的路。"""
    k = world.knowledge
    return k.knows_secret(edge) or k.knows_secret({"src": edge["dst"], "dst": edge["src"], "rel": edge["rel"]})


def _passable(world, player: bool = True):
    return lambda a, b, edge: barrier(world, a, b, edge, player) is None


def stranded(world, loc: str) -> bool:
    """绝境：此地除了此路不通者别无出路（坠入谷底、困于绝壁之下）——原著里萧远山也是这样脱谷的，只是"方法未载"。"""
    return not world.graph.ways(loc, lambda a, b, edge: barrier(world, a, b, edge, strict=True) is None)


def distances(world, src: str) -> dict[str, int]:
    """主角眼中可走的里程（日）：绕开不通、条件未备与未被发现之路。"""
    return world.graph.distances(src, _passable(world))


# ============================================================
#  主角远行：沿可走的最短路；无路可走时沿地理最短路走到绝路之前
# ============================================================
def walk(world, dest: str) -> tuple[list[str], str | None]:
    """返回 (实际路线, 半途止步的缘由)。路线只有一站即寸步未移。"""
    g, here = world.graph, world.here
    route = g.path(here, dest, _passable(world)) or g.path(here, dest)
    if route is None:
        return [here], f"{dest}与此地不相通"
    edges = [g.road(a, b) for a, b in zip(route, route[1:])]
    left = [sum(e["days"] for e in edges[i:]) for i in range(len(edges))]  # 每一站距目的地还有几日
    for i, ((a, b), edge) in enumerate(zip(zip(route, route[1:]), edges)):
        why = barrier(world, a, b, edge)
        if why:  # 绝路：暗路只说找不到去路，不点出通往何处；断在半途才点明断在哪一步
            told = why if why == LOST or b == dest else f"往{b}{why}"
            return route[:i + 1], f"行至{a}便止步，{'再往前' if why == LOST else ''}{told}" if i else told
        gate = _gate(edge, b)
        if gate and i and (b == dest or left[i] == 0):  # 门前之关：通往目的地，或与目的地同在 0 日一簇
            return route[:i + 1], f"行至{a}便止步，往{b}是一道关（{gate['kind']}）：{gate['how']}"
    return route, None


def learn(world, route: list[str]):
    """走过的路就认得：途经的暗路回头也找得到，按整条道路记入认知账本。"""
    for a, b in zip(route, route[1:]):
        edge = world.graph.road(a, b)
        if hidden(edge):
            world.knowledge.reveal(edge["src"], edge["dst"], ROAD)


# ============================================================
#  视图：主角的出路、场外人物的相邻地、导演的关口与暗路
# ============================================================
def exits(world) -> list[dict]:
    """主角眼中的出路：走不通、条件未备、未被发现的都不算；有关口的注明其类。"""
    return [{"name": b, "days": e["days"], "kind": (_gate(e, b) or {}).get("kind")}
            for b, e in world.graph.ways(world.here, _passable(world))]


def steps(world, loc: str) -> list[str]:
    """场外人物一日可去的相邻地：不通与条件未备之路拦住所有人；暗路不拦——知情与否只对主角建模。"""
    return [b for b, _ in world.graph.ways(loc, _passable(world, player=False))]


def passes(world) -> list[str]:
    """此地出发的每一道关（主角已知者）：过法、风险，以及走不通的缘由。"""
    out = []
    for b, e in world.graph.ways(world.here):
        gate, why = _gate(e, b), barrier(world, world.here, b, e)
        if gate and why != LOST:
            line = f"往{b}（{gate['kind']}）：{gate['how']}" + (f"｜风险：{gate['risk']}" if gate["risk"] else "")
            if gate["blocked"]:
                line += "｜此路不通，主角过不去" if why else "｜此路本不通，此地却别无出路：唯有奇遇方能脱身，须在节拍里写明奇遇"
            out.append(line + (f"｜{why}" if why and not gate["blocked"] else ""))
    return out


def secret_ways(world, near: set[str]) -> list[str]:
    """从近处出发、主角尚未发现的暗路：导演可让它在剧情中被发现，或由知情人领着走过。"""
    g, out = world.graph, []
    for a in sorted(near):
        for b, e in g.ways(a):
            if barrier(world, a, b, e) == LOST:
                out.append(f"{a}→{b}（{_gate(e, b)['kind']}）：{_gate(e, b)['how']}")
    return out
