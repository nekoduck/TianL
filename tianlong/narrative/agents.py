"""
[INPUT]: 依赖 narrative/prompts 的提示词组装器与 TENSIONS，narrative/llm 的 LLMError，world/clock 的 PACES（时长措辞表）；llm 参数鸭子类型（Gemini 或 None）
[OUTPUT]: 对外提供 direct()（导演：逐拍{who,to,text,mood,ops}(mood 是情绪快变量，只给编剧)/本幕之问/场景实体/时长措辞/原著去留/张力）、repair()（导演返工一次：只改有问题的拍）、
          write()（编剧：正文 + 梗概/选项(文字｜对象)/伏笔/可传之事，给 on_text 即边写边送）、
          recap()（书记：把挤出的近事折叠进梗概）、simulate()（LOD1 场外剧情，可附江湖近闻）、chronicle()（LOD2 改写原著，可附江湖近闻）
[POS]: narrative 层的 Agent——每个都是「组装→调用→整形→兜底」：整形只保证输出形状可用，不审查内容
       （一句话的旧拍也收、顶层 effects 挂到一个无文字的拍上、单条指令当一批、"false"当否；绝不把「拔剑」拆成「拔」「剑」），
       后果成不成立交给 world/adjudicate 与 effects，选项能不能用交给 world/menu，时长换算交给 world/clock；llm 为 None 或调用失败时走朴素兜底，离线亦可运行(离线说书人认全名，也认兜底选项的方向措辞；兜底选项统一归 world/menu 看局面生成)。
       编剧的梗概与传言宽松读取；没写就是没写（None），由引擎以系统核实过的后果代记；流式被拦腰截断只得只言片语时，以已成立之事续成正文
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging
import re

from . import prompts
from .llm import LLMError
from .prompts import TENSIONS
from ..world.clock import PACES

log = logging.getLogger("tianlong")
TAIL = re.compile(r"\n[ \t]*={3,}")  # 编剧正文之后的分隔线，其后是 梗概/传言 两行
HOLD = re.compile(r"\n[ \t]*={0,2}$")  # 流式正文末尾疑似分隔线的开头：先扣下，等下一块再定
FIELD = re.compile(r"^[\s*#>\-—=]*(梗概|传言|伏笔|选项)[\s*]*[:：][\s*]*(.*)$")  # 半角冒号、markdown 粗体都认
SPLIT = re.compile(r"[、，,；;／/|\n]+")  # 选项被写成一句时的分隔
NO = {"false", "no", "否", "不", "0", "none", "null", ""}
SCRAP = 60  # 流式半途被截断、正文又不足此数：只言片语，须以已成立之事续成


def _ask(llm, prompt: tuple[str, str], fallback, *, as_json=True, tokens=800):
    if llm is None:
        return fallback()
    try:
        return llm.json(*prompt, max_tokens=tokens) if as_json else llm.text(*prompt, max_tokens=tokens)
    except LLMError as e:
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
    return {"beats": [{"who": "player", "text": text, "ops": ops}], "pace": "片刻" if deed else "瞬息",
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
    pace, tension = r.get("pace"), r.get("tension")
    return {"beats": beats,
            "question": {"ask": str(q.get("ask") or deed)[:40],
                         "state": q.get("state") if q.get("state") in QUESTION_STATES else "open",
                         "by": q.get("by") if isinstance(q.get("by"), str) and q.get("by") else None},
            "spawn": _dicts(r.get("spawn"))[:3],
            "pace": pace if isinstance(pace, str) and pace in PACES else ("片刻" if deed else "瞬息"),
            "canon": {"unfolds": _yes(canon.get("unfolds"), True), "why": str(canon.get("why") or "")[:60]},
            "tension": tension if isinstance(tension, str) and tension in TENSIONS else "起",
            "options": [o[:20] for o in _texts(r.get("options"), split=True)][:3]}  # 旧写法的选项：编剧未拟时兜底


def direct(llm, pack: dict, gm: dict, deed: str) -> dict:
    r = _ask(llm, prompts.director(pack, gm, deed or "初来乍到，环顾四周"), lambda: _plain_director(pack, deed), tokens=2000)
    return _plan(r, pack, deed)


def _draft(plan: dict) -> dict:
    """交还导演返工的上一稿：去掉系统补的字段，形状与它写的一样。"""
    return {k: plan[k] for k in ("beats", "question", "spawn", "pace", "canon", "tension")}


def repair(llm, pack: dict, gm: dict, deed: str, plan: dict, problems: list[str]) -> dict | None:
    """导演返工一次：只改有问题的拍。离线或失败返回 None——由系统把仍不成立的拍作废。"""
    if llm is None:
        return None
    r = _ask(llm, prompts.repair(pack, gm, deed or "初来乍到，环顾四周", _draft(plan), problems), lambda: None, tokens=2000)
    return _plan(r, pack, deed) if isinstance(r, dict) else None


OPTION = re.compile(r"^[\s*#>\-]*(?:\d+|[一二三])[\.、．:：)）]\s*(.+)$")
TARGETS = re.compile(r"[｜|]\s*(?:对象|目标)\s*[:：]\s*(.*)$")
DUE = re.compile(r"[｜|]\s*期限\s*[:：]\s*(\d+)")


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
            t = TARGETS.search(body)
            label = (body[:t.start()] if t else body).strip().strip("*").strip()
            if label:
                options.append({"text": label[:20], "targets": [x.strip() for x in SPLIT.split(t.group(1)) if x.strip()] if t else []})
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


def recap(llm, synopsis: str, lines: list[str]) -> str:
    """近事溢出时折叠进梗概：上下文有界，记忆无界。"""
    fallback = lambda: {"synopsis": "；".join(x for x in [synopsis, *lines] if x)[-300:]}
    r = _ask(llm, prompts.recap(synopsis, lines), fallback, tokens=400)
    return str(r.get("synopsis") or fallback()["synopsis"])[-300:]  # 超长时留下新近的一端


# ============================================================
#  LOD1 / LOD2：场外剧情，后果落账在 world/lod + world/effects
# ============================================================
def simulate(llm, time: str, days: int, actors: list[dict], heard=()) -> list[dict]:
    r = _ask(llm, prompts.simulator(time, days, actors, heard), lambda: {"reports": []}, tokens=800)
    return _dicts(r.get("reports"))[:2]


def chronicle(llm, ev: dict, reasons: list[str], actors: list[dict], broken: bool, heard=()) -> dict:
    fallback = lambda: {"happens": not broken, "summary": ev["summary"], "effects": ev["effects"]}
    r = _ask(llm, prompts.chronicler(ev, reasons, actors, heard), fallback, tokens=800)
    effects = _dicts(r.get("effects"))
    return {"happens": _yes(r.get("happens"), bool(r.get("summary") or effects)),
            "summary": str(r.get("summary") or ev["summary"])[:120], "effects": effects}
