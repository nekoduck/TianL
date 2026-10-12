"""
[INPUT]: 依赖 re，world/situation 的 captors / imperiled（幕间省略的闸门）；World 门面的 player / here（鸭子类型）；本回合导演已成立的拍与「局面是否有了物理变化」由引擎给出
[OUTPUT]: 对外提供 THEMES / tag()（一段文字的主题标签）、record()（把本回合记进节奏账）、tired()（打转的主题或诉求，纯函数）、UNTIL（幕间省略可等到的时刻）、
          advise()（给导演后台的阻尼提示）、calm()（幕间省略的闸门：本幕了结、无人相逼才许光阴跳过）、CUTS、STREAK / WINDOW / LOG
[POS]: world 层的阻尼器——慢变量之外，剧情还会在「快变量」上打转：连着几回合都是被拦、赔罪、催促，同一个人反复同一句诉求，
       主角在一处僵持多回合而局面纹丝不动（43 回与 25 回两份实录里都见过）。这里只做确定性统计：按词表给每回合打主题标签、
       记下谁对主角说了什么主题、局面有没有变；近 WINDOW 回合里有 STREAK 回合是同一题，即在后台写明「此题不得再起」「此人换个推进方式」。
       v4：「在一处僵持」不再由这里提示——由 story/scene 的场上限取代(一场演满即须有个结果)；局面动没动仍记在账上，供回放量度。
       不调 LLM、不改世界，只给导演一句话——阻尼，不是禁令之外的另一套规则。
       光阴分两段：戏内光阴(pace，举动本身耗时)与幕间省略(cut，一幕了结后跳到下一处有戏的时刻)；后者是场面结构的决定，由 calm 把关——
       25 回实录里导演回回取「片刻」，因为一回合只写到此刻为止的三五拍，戏内光阴本就是片刻，缺的是幕与幕之间的空白
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import re

from . import situation

# 主题词表：只认强字眼，宁漏勿滥——漏了不过少一句提示，滥了会把正常的戏也拦下
THEMES = {
    "拦阻": re.compile(r"拦住|拦下|拦在|挡在|挡住|截住|截断|不准|不许|休想|不得离|横剑|喝止|不放"),
    "赔罪": re.compile(r"赔罪|赔笑|赔礼|告罪|息怒|恕罪|得罪了|见谅"),
    "催促": re.compile(r"快走|快跑|快逃|再不走|迟则|来不及|危在旦夕|刻不容缓|事不宜迟|赶紧"),
    "盘问": re.compile(r"何方神圣|什么来历|何人|来历|报上名|是谁派|盘问|审问"),
    "伤病": re.compile(r"受伤|伤势|伤口|中毒|毒发|吐血|呕血|昏迷|疼痛|岔气|内伤"),
    "追杀": re.compile(r"追兵|追杀|追来|杀来|追赶|围杀|围住"),
    "练功": re.compile(r"研习|修习|练功|习练|参悟|图谱|卷轴|经脉"),
}
STREAK = 3   # 最近 WINDOW 回合里出现几回合算打转(25 回实录里「拦阻」是隔一回合又来，严格连续会漏)
WINDOW = 4
LOG = 6      # 节奏账只留最近几回合
CUTS = ("一顿饭", "半日", "一夜", "一日")  # 幕间省略可取的措辞：戏内光阴归 pace，幕与幕之间的空白归 cut
UNTIL = ("入夜", "天明", "正午")             # 幕间省略也可以是「到某一刻」：{"until": 入夜/天明/正午/某个时限}，换算归 story/timing
TENSE = {"拦阻", "追杀"}                   # 本回合还在写这些，局面就没有平静下来


def tag(text: str) -> list[str]:
    return [t for t, rx in THEMES.items() if rx.search(text or "")]


def record(world, beats: list[dict], changed: bool):
    """beats：本回合已成立的拍 {who, to, text}；changed：局面有无物理变化(去留、得失、生死、随行拘押、研习…)。"""
    me = world.player
    themes = sorted({t for b in beats for t in tag(b.get("text"))})
    pleas = sorted({f"{b['who']}|{t}" for b in beats if b.get("to") == "player" and b.get("who") not in (None, "player")
                    for t in tag(b.get("text"))})
    log = (me.get("pacing") or []) + [{"themes": themes, "pleas": pleas, "place": world.here, "still": not changed}]
    me.set("pacing", log[-LOG:])


def calm(world, state: str, beats=()) -> str | None:
    """幕间省略的闸门：本幕之问了结、无人相逼，光阴才可跳过；否则返回不许跳的缘由。
    省略是场面结构的决定，不是举动的时长——刀架在脖子上时，没有「半日之后」。"""
    if state != "resolved":
        return "本幕之问未了"
    if situation.captors(world, "player"):
        return "主角受制于人"
    if situation.imperiled(world):
        return "主角命悬一线"
    tense = TENSE & {t for b in beats for t in tag(b.get("text"))}
    return f"局面仍紧（{'、'.join(sorted(tense))}）" if tense else None


def tired(log: list[dict], field: str = "themes") -> list[str]:
    """最近 WINDOW 回合里出现满 STREAK 回合的主题(或诉求)。纯函数：回放工具量旧对局也用它。"""
    tail = log[-WINDOW:]
    counts = {}
    for x in tail:
        for k in set(x[field]):
            counts[k] = counts.get(k, 0) + 1
    return sorted(k for k, n in counts.items() if n >= STREAK)


def advise(world) -> list[str]:
    """节奏账 → 给导演的阻尼提示；没有打转就是空的。"""
    log = world.player.get("pacing") or []
    out = [f"「{t}」近{WINDOW}回合里已有{STREAK}回合：本回合不得再写，给人物的图谋或主角的所求让路" for t in tired(log)]
    for p in tired(log, "pleas"):
        who, t = p.split("|")
        out.append(f"{who}近来一再对主角{t}：换个推进方式（让他做点什么，或让事情有个结果），不要再说同样的话")
    return out
