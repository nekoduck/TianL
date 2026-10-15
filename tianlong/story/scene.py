"""
[INPUT]: 依赖 world/situation 的 near（同一处所之内的地点簇）、world/pacing 的 calm（幕间省略的闸门），World 门面的 player / here（鸭子类型）
[OUTPUT]: 对外提供 settles()（v12 合场的账：危局里只认结构性变化）、begin()（回合开始：续场或开新场）、close()（回合结束：按导演报的场况推进、记下试过的路数、合场或断场）、
          question()（场况 → 裁决器认的本幕之问 {ask, state, by}）、tension()（张力由场推出）、over()、STATES、CAP
[POS]: story 层的「场」——叙事的基本单位，跨回合：一场有一个问题(ask)、试过的路数(tried)、演了几回合(turns)、场况(开/转/合/断)。
       开：上一场合了或断了、或主角走出了这个地点簇；转：同一个问题跨回合推进；合：问题有了结果(v5 须账上真有变化，空口的「合」仍记作转)；断：被打断、留待来日。
       一场演满 CAP 回合仍未合，场记写明本回合必须有个结果——这一条取代 v3 的僵持检测。
       张力不再由导演填，由场况推出；裁决器仍按「本幕之问」核对打断的来源，场况与它一一对应
       v12 危局：合要有账可依的口径随危局变(settles)；stall 记连着几回合处在危局里而没有结构性变化——跟着危局走，与场的上限并存
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from ..world import pacing, situation

STATES = ("开", "转", "合", "断")
TO_QUESTION = {"开": "open", "转": "open", "合": "resolved", "断": "interrupted"}
FROM_QUESTION = {"open": "转", "resolved": "合", "interrupted": "断"}
CAP = 6           # 一场至多演几回合
TRIED = 4         # 记最近几种试过的路数
ASK_LEN, DEED_LEN = 24, 14


def _cluster(world) -> str:
    """地点簇：同一处所之内零日可达的子地点同属一场。"""
    return min(situation.near(world) | {world.here})


def begin(world) -> dict:
    """回合开始：上一场已合、已断、或主角走出了那个地点簇，就开新场；否则续场。
    v12 僵持计数(stall)跟着危局走、不跟着场走：开了新场而危局仍在(pacing.danger)，上一场的 stall 带过来。"""
    me = world.player
    sc, where = me["scene"], _cluster(world)
    if not sc or sc.get("state") in ("合", "断") or sc.get("where") != where:
        stall = (sc or {}).get("stall", 0) if pacing.danger(world) else 0
        sc = {"id": (sc or {}).get("id", 0) + 1, "where": where, "ask": "", "state": "开", "turns": 0, "tried": [],
              "since": me["turn"], "stall": stall}
        me.set("scene", sc)
    return sc


def settles(applied: list, moved: bool = False, pressed: bool = False) -> bool:
    """这一回合的账够不够「合」(v12)：平常同 v5——主角挪了步，或有 mood、外号之外的任何成立之事；
    危局里(pressed)只认结构性变化(pacing.structural：去留、易手、生死、随行拘押、人群倒下)——只扣气血、只改打算神色不算。"""
    if pressed:
        return pacing.structural(applied, moved)
    return moved or any(op.get("key") not in ("mood", "epithet") for op in applied)


def question(report: dict | None, deed: str = "") -> dict:
    """导演报的场况 {state 开/转/合/断, ask, by} → 本幕之问 {ask, state resolved/open/interrupted, by}。"""
    report = report or {}
    state = report.get("state") if report.get("state") in STATES else "转"
    return {"ask": str(report.get("ask") or deed)[:40], "state": TO_QUESTION[state], "by": report.get("by")}


def close(world, q: dict, deed: str = "", settled: bool = True, pressed: bool = False, shifted: bool = False):
    """回合结束：问题措辞以导演最新所写为准，记下主角这一回合试过的路数，场况取裁决之后的本幕之问。
    合要有账可依(v5)：导演报「合」而这一回合账上什么也没变(settled 为假：没有成立的后果、主角也没挪步)，那只是换了个说法——仍是「转」，
    场不散、试过的路数不清，演满上限照样要求收场。
    v12 僵持计数：本回合处在危局里(pressed)而没有结构性变化(shifted 为假)，stall 加一；有结构性变化或脱离危局即归零(旧场没有这个键按 0 读)。"""
    me = world.player
    sc = dict(me["scene"] or begin(world))
    sc["stall"] = sc.get("stall", 0) + 1 if pressed and not shifted else 0
    if q.get("ask") and (not sc["ask"] or sc["state"] == "开"):
        sc["ask"] = str(q["ask"])[:ASK_LEN]
    if deed:
        sc["tried"] = (sc["tried"] + [deed[:DEED_LEN]])[-TRIED:]
    sc["turns"] += 1
    state = FROM_QUESTION.get(q.get("state"), "转")
    sc["state"] = "转" if state == "合" and not settled else state
    me.set("scene", sc)


def over(sc: dict) -> bool:
    return bool(sc) and sc["turns"] >= CAP - 1 and sc["state"] not in ("合", "断")


def tension(sc: dict, urgent: bool = False) -> str:
    if sc["state"] == "合":
        return "收"
    if over(sc) or urgent:
        return "高潮"
    return "起" if sc["turns"] else "平"
