"""
[INPUT]: 依赖 World 门面的 graph / player / turn（鸭子类型），不依赖其他 world 模块
[OUTPUT]: 对外提供 vitals() / hurt() / mend()（任何人的气血：主角在黑板、NPC 在图节点、惰性初始化）、conditions() / set_conditions()（任何人的境况清单）、
          sync()（NPC 的 status 由气血推出）、feel() / mood()（NPC 的心境：拍上的情绪留 MOOD_TURNS 回合）、INTENT_LEN、MOOD_TURNS
[POS]: world 层的「人」组件——主角与 NPC 同构：身体(气血、境况、生死)、心境、眼下之事(intent)走同一组访问器，
       body(内伤与养伤)、effects(add hp、push conditions 对任何活人成立)、profile(投影)都只经这里读写，不再各写一遍 id=="player" 的特判。
       NPC 的气血不入原著数据：首次被碰到时由 status 推出(负伤即六成)，存档时随图节点走；status 由气血推出——
       气血跌破八成即负伤，养回八成五即安好；导演写 set status wounded/alive 时气血随之对齐，死只能明写，不由扣血推出
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

MAX_HP = 100
WOUNDED_HP = 60      # 原著里「负伤」的人，初见时的气血
HURT_LINE = 0.8      # 气血跌破此比例即负伤
WELL_LINE = 0.85     # 养回此比例即安好
MOOD_TURNS = 3       # 拍上写下的情绪，几回合内仍挂在此人脸上（只给编剧渲染，不入关系账）
MOOD_LEN, INTENT_LEN = 8, 30


def _node(world, who: str) -> dict:
    return world.graph.nodes[who]


def vitals(world, who: str) -> tuple[int, int]:
    """任何人的 (气血, 上限)：主角在黑板；NPC 惰性初始化——原著只说他负没负伤，气血从这一句推出。"""
    if who == "player":
        return world.player["hp"], world.player["max_hp"]
    node = _node(world, who)
    if "hp" not in node:
        node["max_hp"] = node.get("max_hp") or MAX_HP
        node["hp"] = 0 if node.get("status") == "dead" else WOUNDED_HP if node.get("status") == "wounded" else node["max_hp"]
    return node["hp"], node["max_hp"]


def hurt(world, who: str, delta: int):
    """增减气血（负为伤、正为疗）：主角夹在 [1, 上限]（主角不在规则层死亡），NPC 夹在 [1, 上限]——死须明写 set status dead。"""
    if who == "player":
        world.player.add("hp", delta)
        return
    hp, cap = vitals(world, who)
    _node(world, who)["hp"] = max(1, min(cap, hp + delta))
    sync(world, who)


def sync(world, who: str):
    """NPC 的 status 由气血推出：跌破八成负伤、养回八成五安好；死者不动。"""
    node = _node(world, who)
    if node.get("status") == "dead" or "hp" not in node:
        return
    ratio = node["hp"] / node["max_hp"]
    if ratio < HURT_LINE:
        node["status"] = "wounded"
    elif ratio >= WELL_LINE and node.get("status") == "wounded":
        node["status"] = "alive"


def declare(world, who: str, status: str):
    """导演明写 set status：气血随之对齐——写负伤即不高于六成，写安好即不低于八成五；死者气血归零。"""
    hp, cap = vitals(world, who)
    node = _node(world, who)
    if status == "wounded":
        node["hp"] = min(hp, round(cap * WOUNDED_HP / MAX_HP))
    elif status == "alive":
        node["hp"] = max(hp, round(cap * WELL_LINE))
    elif status == "dead":
        node["hp"] = 0
    node["status"] = status


def mend(world, who: str, amount: int):
    """自然恢复：只增不减，死者不养。"""
    if who != "player" and _node(world, who).get("status") == "dead":
        return
    hurt(world, who, amount)


def conditions(world, who: str) -> list[str]:
    return list(world.player["conditions"] if who == "player" else _node(world, who).get("conditions") or [])


def set_conditions(world, who: str, value: list[str]):
    if who == "player":
        world.player.set("conditions", value)
    else:
        _node(world, who)["conditions"] = value


# ============================================================
#  心境与眼下之事：拍上的情绪留几回合；intent 是一句话，可由导演或场外推演改写
# ============================================================
def feel(world, who: str, mood: str):
    if who and who != "player" and world.graph.kind(who) == "person" and mood:
        node = _node(world, who)
        node["mood"], node["mood_turn"] = str(mood)[:MOOD_LEN], world.player["turn"]


def mood(world, who: str) -> str | None:
    """此人脸上的情绪：MOOD_TURNS 回合内写下的才算，过时即淡去。"""
    node = world.graph.nodes.get(who, {})
    if node.get("mood") and world.player["turn"] - node.get("mood_turn", -MOOD_TURNS) < MOOD_TURNS:
        return node["mood"]
    return None
