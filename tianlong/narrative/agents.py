"""
[INPUT]: 依赖 narrative/prompts 的提示词组装器与 TENSIONS，narrative/llm 的 LLMError，world/clock 的 PACES（时长措辞表）、world/pacing 的 CUTS / UNTIL（幕间省略措辞与可等到的时刻）；llm 参数鸭子类型（Gemini 或 None）
[OUTPUT]: 对外提供 direct()（导演：逐拍{who,to,text,mood,ops}(mood 是情绪快变量，给编剧渲染、挂在此人脸上几回合)/场况 scene(开/转/合/断，旧写法的本幕之问亦收)/场景实体/时长措辞 pace 与幕间省略 cut(长度或到某一刻)/时限 clock/原著去留）、repair()（导演返工一次：只改有问题的拍）、
          write()（编剧：正文 + 梗概/选项(文字｜对象｜尺度｜代价，代价写在字段或括号里都认——括号写在文字末尾或对象之后皆可，说耗时路程的才是代价、其余是对象(v5)；至多八字，写不下就不写、不截半句)/伏笔/可传之事，给 on_text 即边写边送）、
          settle()（v6 账房：读定本正文与账本快照，开出账上缺的变化 {changes:[{据,谁,ops}], rifts, 未写到(v7 对稿：账上变了而正文没写到的编号)}，离线或失声返回 None 交词表对账）、
          recheck()（v7 双录复核：词表看出、账上没有的几句交账房逐句裁定 {changes, 不记}）、
          recap()（书记：把挤出的近事折叠进梗概）、plot()（v11 场外编剧·创作家：每份任务书一条剧情线草稿）、review()（v11 审稿人：过/改/否 与缘由）
[POS]: narrative 层的 Agent——每个都是「组装→调用→整形→兜底」：整形只保证输出形状可用，不审查内容
       （一句话的旧拍也收、顶层 effects 挂到一个无文字的拍上、单条指令当一批、"false"当否；绝不把「拔剑」拆成「拔」「剑」），
       后果成不成立交给 world/adjudicate 与 effects，选项能不能用交给 world/menu，时长换算交给 world/clock；llm 为 None 或调用失败时走朴素兜底，离线亦可运行(离线说书人认全名，也认兜底选项的方向措辞；兜底选项统一归 world/menu 看局面生成)。
       编剧的梗概与传言宽松读取；没写就是没写（None），由引擎以系统核实过的后果代记；流式被拦腰截断只得只言片语时，以已成立之事续成正文；
       导演失声不演假戏(v5)：严格的模型(llm.strict)导演调用失败即抛出，整回合作废、玩家重试；桩与离线照旧兜底；
       账房(v6)只整形不审内容：据与谁是文字、ops 是一批指令——收不收、成不成立归 world/settle 与 effects；
       场外编剧(v11)只认回任务名，规则审归 world/plot；审稿人读不出判定的当作「改」，失声即都不过——不合理的一律不过
       v14 选项文字不截半句(_clip 写不下就不写代价)；漏写「对象：」而写了「｜某某」的也认作对象
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import re

from . import prompts
from .llm import LLMError
from .prompts import TENSIONS
from ..world.clock import PACES
from ..world.pacing import CUTS, UNTIL

log = logging.getLogger("tianlong")
TAIL = re.compile(r"\n[ \t]*={3,}")  # 编剧正文之后的分隔线，其后是 梗概/传言 两行
HOLD = re.compile(r"\n[ \t]*={0,2}$")  # 流式正文末尾疑似分隔线的开头：先扣下，等下一块再定
FIELD = re.compile(r"^[\s*#>\-—=]*(梗概|传言|伏笔|选项)[\s*]*[:：][\s*]*(.*)$")  # 半角冒号、markdown 粗体都认
SPLIT = re.compile(r"[、，,；;／/|\n]+")  # 选项被写成一句时的分隔
NO = {"false", "no", "否", "不", "0", "none", "null", ""}
SCRAP = 60  # 流式半途被截断、正文又不足此数：只言片语，须以已成立之事续成


def _ask(llm, prompt: tuple[str, str], fallback, *, as_json=True, tokens=800, strict=False):
    """调用模型；失败走兜底。strict 的调用(导演)遇上严格的模型(真 Gemini，strict=True)不演假戏：抛出去，整回合作废、玩家重试——
    离线说书人那句「你看了看四周」配上编剧的一番铺陈，比一次重试更伤剧情。"""
    if llm is None:
        return fallback()
    try:
        return llm.json(*prompt, max_tokens=tokens) if as_json else llm.text(*prompt, max_tokens=tokens)
    except LLMError as e:
        if strict and getattr(llm, "strict", False):
            raise
        log.warning("LLM 调用失败，走兜底：%s", e)
        return fallback()


def _dicts(xs) -> list[dict]:
    """一批指令或战报：单条也收，非清单视为空。"""
    xs = [xs] if isinstance(xs, dict) else xs
    return [x for x in xs if isinstance(x, dict)] if isinstance(xs, list) else []


def _texts(xs, split: bool = False) -> list[str]:
    """一列文字：模型把清单写成一个字串时包成一项（选项可按顿号拆开），绝不逐字拆散；非清单视为空。"""
    if isinstance(xs, str):
        xs = SPLIT.split(xs) if split else [xs]
    return [str(x).strip() for x in xs if x and str(x).strip()] if isinstance(xs, list) else []


def _yes(value, default: bool) -> bool:
    """真假的宽松读法：false、"false"、"否"、0 都是否；缺省取 default。"""
    if value is None:
        return default
    return value.strip().lower() not in NO if isinstance(value, str) else bool(value)


# ============================================================
#  LOD0：导演（逐拍的剧情与后果；选项归编剧）
# ============================================================
QUESTION_STATES = ("resolved", "open", "interrupted")
ME = {"player", "主角", "你"}


def _plain_director(pack: dict, deed: str) -> dict:
    """离线兜底：只会走路与旁观的朴素说书人；原著照常上演。"""
    dest = max((e["name"] for e in pack["exits"] if e["name"] in deed or e.get("way") == deed),
               key=len, default=None)  # 「澜沧江边高崖」不被「澜沧江」截胡；兜底选项的方向措辞(出练武厅)也认得
    text = f"你动身前往{dest}。" if dest else f"你{deed}。" if deed else "你凝神四顾。"
    ops = [{"op": "set", "id": "player", "key": "location", "value": dest}] if dest else []
    return {"beats": [{"who": "player", "text": text, "ops": ops}], "pace": "片刻" if deed else "瞬息", "cut": None,
            "canon": {"unfolds": True, "why": ""}, "tension": "平",
            "question": {"ask": deed, "state": "resolved" if dest or not deed else "open", "by": None}}


def _beat(x, me: str) -> dict | None:
    """一拍：{who, to, text, ops}；只给一句话的旧写法也收（who 不明、ops 为空）。"""
    if isinstance(x, str):
        return {"who": None, "to": None, "text": x.strip()[:80], "ops": []} if x.strip() else None
    if not isinstance(x, dict) or not str(x.get("text") or "").strip():
        return None
    norm = lambda v: "player" if v in ME or v == me else (v if isinstance(v, str) and v else None)
    return {"who": norm(x.get("who")), "to": norm(x.get("to")), "text": str(x["text"]).strip()[:80], "ops": _dicts(x.get("ops")),
            "mood": str(x.get("mood") or "").strip()[:8]}  # 情绪是快变量：只给编剧渲染，不入账、不回喂


def _plan(r: dict, pack: dict, deed: str) -> dict:
    me = pack["player"]["name"]
    beats = [b for b in (_beat(x, me) for x in (r.get("beats") if isinstance(r.get("beats"), list) else [])) if b][:6]
    loose = _dicts(r.get("effects"))  # 旧写法：后果写在顶层，挂到一个无文字的拍上——裁决照样逐条落账
    if loose:
        beats.append({"who": None, "to": None, "text": "", "ops": loose})
    beats = beats or [{"who": "player", "to": None, "text": "你凝神四顾。", "ops": []}]
    canon = r.get("canon") if isinstance(r.get("canon"), dict) else {}
    q = r.get("question") if isinstance(r.get("question"), dict) else {}
    pace, cut, tension = r.get("pace"), r.get("cut"), r.get("tension")
    sc = r.get("scene") if isinstance(r.get("scene"), dict) else None
    clocks = [c for c in _dicts(r.get("clock")) if str(c.get("what") or "").strip()][:2]
    return {"beats": beats,
            "question": {"ask": str(q.get("ask") or deed)[:40],
                         "state": q.get("state") if q.get("state") in QUESTION_STATES else "open",
                         "by": q.get("by") if isinstance(q.get("by"), str) and q.get("by") else None},
            "spawn": _dicts(r.get("spawn"))[:3],
            "pace": pace if isinstance(pace, str) and pace in PACES else ("片刻" if deed else "瞬息"),
            "cut": _cut(cut),  # 幕间省略：一段长度或「到某一刻」；「无」与不识的措辞都当没有
            "scene": {"state": str(sc.get("state") or "").strip()[:1], "ask": str(sc.get("ask") or "").strip()[:40],
                      "by": sc.get("by") if isinstance(sc.get("by"), str) and sc.get("by") else None} if sc else None,
            "clock": clocks,
            "canon": {"unfolds": _yes(canon.get("unfolds"), True), "why": str(canon.get("why") or "")[:60]},
            "tension": tension if isinstance(tension, str) and tension in TENSIONS else "起",
            "options": [o[:20] for o in _texts(r.get("options"), split=True)][:3]}  # 旧写法的选项：编剧未拟时兜底


def _cut(cut):
    """幕间省略的宽松读法：长度措辞、「入夜/天明/正午」、或 {"until": 某一刻/某个时限}；其余都当没有。"""
    if isinstance(cut, str) and (cut in CUTS or cut in UNTIL):
        return cut
    if isinstance(cut, dict) and isinstance(cut.get("until"), str) and cut["until"].strip() and cut["until"].strip() not in NO | {"无"}:
        return {"until": cut["until"].strip()[:20]}
    return None


def direct(llm, pack: dict, gm: dict, deed: str) -> dict:
    r = _ask(llm, prompts.director(pack, gm, deed or "初来乍到，环顾四周"), lambda: _plain_director(pack, deed), tokens=2000, strict=True)
    return _plan(r, pack, deed)


def _draft(plan: dict) -> dict:
    """交还导演返工的上一稿：去掉系统补的字段，形状与它写的一样。"""
    return {k: plan[k] for k in ("beats", "scene", "question", "spawn", "pace", "cut", "clock", "canon") if plan.get(k) is not None}


def repair(llm, pack: dict, gm: dict, deed: str, plan: dict, problems: list[str]) -> dict | None:
    """导演返工一次：只改有问题的拍。离线或失败返回 None——由系统把仍不成立的拍作废。"""
    if llm is None:
        return None
    r = _ask(llm, prompts.repair(pack, gm, deed or "初来乍到，环顾四周", _draft(plan), problems), lambda: None, tokens=2000)
    return _plan(r, pack, deed) if isinstance(r, dict) else None


OPTION = re.compile(r"^[\s*#>\-]*(?:\d+|[一二三])[\.、．:：)）]\s*(.+)$")
TARGETS = re.compile(r"[｜|]\s*(?:对象|目标)\s*[:：]\s*(.*)$")
SCALE = re.compile(r"[｜|]\s*尺度\s*[:：]\s*(此刻|此后|机缘)[^｜|]*")
COST = re.compile(r"[｜|]\s*(?:代价|耗时)\s*[:：]\s*([^｜|]*)")
LABEL = 26  # 选项连同代价的字数上限
COST_LEN = 8  # 代价至多八字
HARD = 32  # 没有标点的长选项宽限到这么多字才硬截(v14：「…奔向练武厅辛双清处求」截掉了「援」)
PAREN = re.compile(r"[（(]([^（）()]*)[）)]\s*$")
TIMEISH = re.compile(r"日|时辰|顿饭|一夜|片刻|路程|里路|天|刻|更|宿|盏茶|炷香")  # 括号里说的是耗时路程，才是代价；否则多半是对象
DUE = re.compile(r"[｜|]\s*期限\s*[:：]\s*(\d+)")


def _clip(text: str, n: int) -> str:
    """选项文字的上限(v14)：不截在词中间——超了先在最后一个标点处截(截下的至少过半)；没有标点的长句宽限到 HARD 字才硬截。"""
    if len(text) <= n:
        return text
    cut = max(text.rfind(c, 0, n) for c in "，、；,;")
    return text[:cut] if cut >= n // 2 else text if len(text) <= HARD else text[:HARD]


def _page(raw: str) -> dict:
    """编剧原文 → {text, memory, headline, options, hook}：分隔线之前是正文，之后是梗概、选项（文字｜对象）、伏笔与可传之事。
    写法宽松（半角冒号、markdown 粗体、值另起一行皆可）；没写就是 None 或空——由引擎代记、由选项出口检查补齐。"""
    text, tail = (TAIL.split(raw, maxsplit=1) + [""])[:2]
    lines, found, options = [line.strip() for line in tail.splitlines()], {}, []
    for i, line in enumerate(lines):
        m = FIELD.match(line)
        if m:
            nxt = lines[i + 1] if i + 1 < len(lines) and not FIELD.match(lines[i + 1]) and not OPTION.match(lines[i + 1]) else ""
            found.setdefault(m.group(1), m.group(2).strip().strip("*").strip() or nxt)
            continue
        o = OPTION.match(line)
        if o and len(options) < 3:
            body = o.group(1).strip().strip("*")
            scale, cost = SCALE.search(body), COST.search(body)
            body = COST.sub("", SCALE.sub("", body))  # 尺度与代价写在对象前后都认：先摘下来，免得被对象一并吞掉
            t = TARGETS.search(body)
            label = (body[:t.start()] if t else body).strip().strip("*").strip()
            aims = t.group(1).strip() if t else ""
            if not t and re.search(r"[｜|]", label):  # v14 对象栏漏写「对象：」(「撬开抽屉｜内堂书案」)：竖线后的就是对象，不混进选项文字
                head, rest = re.split(r"\s*[｜|]\s*", label, maxsplit=1)
                label, aims = head.strip(), re.split(r"\s*[｜|]\s*", rest, maxsplit=1)[0].strip()
            price, more = cost.group(1).strip().strip("（）()") if cost else "", []
            for part in ("label", "aims"):  # 括号写在文字末尾或对象之后都认(v5)：说耗时路程的是代价，其余是对象
                m = PAREN.search(label if part == "label" else aims)
                if not m:
                    continue
                inner = m.group(1).strip()
                if part == "label":
                    label = label[:m.start()].strip()
                else:
                    aims = aims[:m.start()].strip()
                if TIMEISH.search(inner):
                    price = price or inner
                elif inner:
                    more.append(inner)
            label = _clip(label, LABEL - 2)  # v14 不截在词中间：太长先在标点处截(run1 第 2 回「弯腰拾起地上碎（耗时片刻）」)
            if price and len(price) <= COST_LEN and len(label) + len(price) + 2 <= LABEL + COST_LEN:  # 代价太长或放不下就不写，宁缺不截半句
                label += f"（{price}）"
            if label.strip("（）"):
                options.append({"text": label, "targets": [x.strip() for x in SPLIT.split(aims) if x.strip()] + more,
                                "scale": scale.group(1) if scale else None})
    memory = found.get("梗概") or None
    headline = (found.get("传言") or "").strip("。. ")
    hook = found.get("伏笔") or ""
    due = DUE.search(hook)
    hook = re.split(r"[｜|]", hook)[0].strip().strip("。")
    return {"text": text.strip(), "memory": memory[:60] if memory else None,
            "headline": headline[:40] if headline and headline.lower() not in NO | {"无"} else None,
            "options": options,
            "hook": {"text": hook[:40], "turns": min(int(due.group(1)), 8) if due else 3} if hook and hook not in NO | {"无"} else None}


def _show(on_text, acc: str, sent: int) -> int | None:
    """把正文里尚未送出的部分送给读者；见到分隔线即止（返回 None）——梗概与传言是账房的事，不是读者的。
    末尾若像分隔线的开头（换行后跟零到两个等号），先扣下这几个字等下一块：半截分隔线漏给读者，打字机上就多出一个「=」。"""
    m = TAIL.search(acc)
    hold = None if m else HOLD.search(acc)
    end = m.start() if m else hold.start() if hold else len(acc)
    if end > sent:
        on_text(acc[sent:end])
    return None if m else max(sent, end)


def write(llm, pack: dict, frame: dict, on_text=None) -> dict:
    """编剧成文，并写下本回合实际成立之事的梗概（它同时看见节拍与未成立，是唯一有资格记账的人）。
    给了 on_text 且模型能流式，就边写边送；半途失声时已写出的即为正文，只得只言片语则以已成立之事续成，一字未得才走兜底。"""
    prompt = prompts.writer(pack, frame)
    fallback = lambda: "\n".join([pack["scene"]["desc"], *frame["beats"], *frame.get("notes", []), *(f"（{v}）" for v in frame["void"])])
    if on_text and hasattr(llm, "stream"):
        parts, sent, cut = [], 0, False
        try:
            for delta in llm.stream(*prompt, max_tokens=1800):
                parts.append(delta)
                if sent is not None:
                    sent = _show(on_text, "".join(parts), sent)
        except LLMError as e:
            cut = True
            log.warning("编剧流式中断（已得 %d 段）：%s", len(parts), e)
        raw = "".join(parts)
        page = _page(raw)
        if cut and raw.strip() and len(page["text"]) < SCRAP:  # 只得只言片语（多半被安全策略拦腰截断）：以已成立之事续成正文
            rest = fallback()
            on_text("\n" + rest)
            return {**page, "text": (page["text"] + "\n" + rest).strip()}
        if raw.strip():  # 一字未得（断在开头，或被安全策略整段拦下）才走下面的兜底
            if sent is not None and sent < len(raw.rstrip()):
                on_text(raw.rstrip()[sent:])  # 流尽而不见分隔线：扣下的尾巴放行
            return page
    page = _page(_ask(llm, prompt, fallback, as_json=False, tokens=1800))
    if on_text:
        on_text(page["text"])  # 不能流式时，整段作一次送出，调用方无须区分
    return page


def settle(llm, books: dict) -> dict | None:
    """账房(v6)：读本回合的定本(正文)与账本快照，开出正文确立而账上没有的变化 {changes:[{据, 谁, ops}], rifts:[{据, 账上}]}。
    整形只保形状(据与谁是文字、ops 是一批指令)，收不收、成不成立归 world/settle 与 effects；离线或失声返回 None——由系统以词表对账。"""
    if llm is None or not books.get("text"):
        return None
    r = _ask(llm, prompts.settler(books), lambda: None, tokens=1200)
    if not isinstance(r, dict):
        return None
    return {"changes": _bills(r.get("changes")),
            "rifts": [{"据": str(x.get("据") or ""), "账上": str(x.get("账上") or "")} for x in _dicts(r.get("rifts"))],
            "未写到": [int(x) for x in (r.get("未写到") if isinstance(r.get("未写到"), list) else [])
                     if isinstance(x, (int, str)) and str(x).strip().isdigit()]}


def recheck(llm, books: dict, disputes: list[dict]) -> dict | None:
    """双录复核(v7)：词表看出、账上没有的几句交账房逐句裁定 {changes:[{据,谁,ops}], 不记:[{据,缘由}]}；离线或失声返回 None(这几句只记分歧)。"""
    if llm is None or not disputes:
        return None
    r = _ask(llm, prompts.rechecker(books, disputes), lambda: None, tokens=900)
    if not isinstance(r, dict):
        return None
    return {"changes": _bills(r.get("changes")),
            "不记": [{"据": str(x.get("据") or ""), "缘由": str(x.get("缘由") or "")} for x in _dicts(r.get("不记"))]}


def _bills(xs) -> list[dict]:
    """结算单的形状：据与谁是文字、ops 是一批指令。"""
    return [{"据": str(c.get("据") or ""), "谁": c.get("谁") if isinstance(c.get("谁"), str) else None, "ops": _dicts(c.get("ops"))}
            for c in _dicts(xs)]


def recap(llm, synopsis: str, lines: list[str]) -> str:
    """近事溢出时折叠进梗概：上下文有界，记忆无界。"""
    fallback = lambda: {"synopsis": "；".join(x for x in [synopsis, *lines] if x)[-300:]}
    r = _ask(llm, prompts.recap(synopsis, lines), fallback, tokens=400)
    return str(r.get("synopsis") or fallback()["synopsis"])[-300:]  # 超长时留下新近的一端


# ============================================================
#  场外编剧(v11)：创作家写剧情线、审稿人审合不合理；规则审在 world/plot
# ============================================================
VERDICTS = ("过", "改", "否")


def _keyed(xs, keys: list[str]) -> dict:
    """按任务名认回每一份：写了 key 就认 key，没写按次序。"""
    out = {}
    for i, x in enumerate(_dicts(xs)):
        key = x.get("key") if x.get("key") in keys else (keys[i] if i < len(keys) else None)
        if key and key not in out:
            out[key] = x
    return out


def plot(llm, briefs: list[dict], notes: dict | None = None) -> dict:
    """创作家：每份任务书一条剧情线草稿 {key: {line, goal, events}}。整形只认回任务名，合不合理交 world/plot 规则审与审稿；离线或失声返回空(交系统兜底)。"""
    if llm is None or not briefs:
        return {}
    r = _ask(llm, prompts.plotter(briefs, notes), dict, tokens=800 + 900 * len(briefs))  # 一条剧情线连同动机、手段、戏眼，汉字吃 token：给足，免得 JSON 被拦腰截断
    return _keyed(r.get("plans") if isinstance(r, dict) else None, [b["key"] for b in briefs])


def review(llm, items: list[dict]) -> dict:
    """审稿人：{key: {verdict: 过/改/否, why}}。读不出判定的当作「改」——不合理的一律不过；离线或失声返回空(都不过)。"""
    if llm is None or not items:
        return {}
    r = _ask(llm, prompts.reviewer(items), dict, tokens=300 + 200 * len(items))
    out = {}
    for key, x in _keyed(r.get("reviews") if isinstance(r, dict) else None, [i["key"] for i in items]).items():
        v = str(x.get("verdict") or "").strip()
        verdict = "否" if v.startswith(("否", "不过", "驳")) else "过" if v.startswith(("过", "通过", "pass")) else "改"
        out[key] = {"verdict": verdict, "why": str(x.get("why") or "")[:120]}
    return out
