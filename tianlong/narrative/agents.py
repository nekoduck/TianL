"""
[INPUT]: 依赖 narrative/prompts 的五组提示词组装器与 TENSIONS，narrative/llm 的 LLMError，world/clock 的 PACES（时长措辞表）；llm 参数鸭子类型（Gemini 或 None）
[OUTPUT]: 对外提供 direct()（导演：节拍/后果/时长措辞/原著去留/张力/3 自由选项）、write()（编剧：正文/真实梗概/可传之事，给 on_text 即边写边送）、
          recap()（书记：把挤出的近事折叠进梗概）、simulate()（LOD1 场外剧情，可附江湖近闻）、chronicle()（LOD2 改写原著，可附江湖近闻）
[POS]: narrative 层的五个 Agent——每个都是「组装→调用→整形→兜底」：整形只保证输出形状可用，不审查内容，
       剧情后果能否落账交给 world/effects，时长换算交给 world/clock；llm 为 None 或调用失败时走朴素兜底，离线亦可运行
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


def _ask(llm, prompt: tuple[str, str], fallback, *, as_json=True, tokens=800):
    if llm is None:
        return fallback()
    try:
        return llm.json(*prompt, max_tokens=tokens) if as_json else llm.text(*prompt, max_tokens=tokens)
    except LLMError as e:
        log.warning("LLM 调用失败，走兜底：%s", e)
        return fallback()


def _dicts(xs) -> list[dict]:
    return [x for x in xs or [] if isinstance(x, dict)]


# ============================================================
#  LOD0：导演（剧情 + 选项）
# ============================================================
def _plain_director(pack: dict, deed: str) -> dict:
    """离线兜底：只会走路与旁观的朴素说书人；原著照常上演。"""
    exits = [e["name"] for e in pack["exits"]]
    dest = next((e for e in exits if e in deed), None)
    beats = [f"你动身前往{dest}。"] if dest else [f"你{deed}。" if deed else "你凝神四顾。"]
    return {"beats": beats, "pace": "片刻" if deed else "瞬息", "canon": {"unfolds": True, "why": ""}, "tension": "平",
            "effects": [{"op": "set", "id": "player", "key": "location", "value": dest}] if dest else [],
            "options": _plain_options(pack)}


def _plain_options(pack: dict) -> list[str]:
    opts = [f"与{p['name']}攀谈" for p in pack["people"][:2]] + [f"前往{e['name']}" for e in pack["exits"]]
    return (opts + ["歇息片刻", "四下察看"])[:3]


def direct(llm, pack: dict, gm: dict, deed: str) -> dict:
    r = _ask(llm, prompts.director(pack, gm, deed or "初来乍到，环顾四周"),
             lambda: _plain_director(pack, deed), tokens=1500)
    beats = [str(b) for b in r.get("beats") or [] if b][:6] or ["你凝神四顾。"]
    canon = r.get("canon") if isinstance(r.get("canon"), dict) else {}
    options = [str(o)[:20] for o in r.get("options") or [] if o][:3]
    return {"beats": beats,
            "effects": _dicts(r.get("effects")),
            "pace": r.get("pace") if r.get("pace") in PACES else ("片刻" if deed else "瞬息"),
            "canon": {"unfolds": canon.get("unfolds") is not False, "why": str(canon.get("why") or "")[:60]},
            "tension": r.get("tension") if r.get("tension") in TENSIONS else "起",
            "options": options + _plain_options(pack)[len(options):]}


def _page(raw: str, frame: dict) -> dict:
    """编剧原文 → {text, memory, headline}：分隔线之前是正文，之后两行是只记已成立之事的梗概与可传之事。"""
    text, tail = (TAIL.split(raw, maxsplit=1) + [""])[:2]
    memory = headline = None
    for line in tail.splitlines():
        key, _, val = line.strip().lstrip("=-—").strip().partition("：")
        if key == "梗概" and val.strip():
            memory = val.strip()
        elif key == "传言" and val.strip() not in ("", "无", "null", "None"):
            headline = val.strip()
    return {"text": text.strip(), "memory": (memory or frame["beats"][0])[:60], "headline": headline[:40] if headline else None}


def _show(on_text, acc: str, delta: str) -> bool:
    """把正文增量送给读者；见到分隔线即止——梗概与传言是账房的事，不是读者的。返回是否继续送。"""
    m = TAIL.search(acc)
    if not m:
        on_text(delta)
        return True
    cut = m.start() - (len(acc) - len(delta))
    if cut > 0:
        on_text(delta[:cut])
    return False


def write(llm, pack: dict, frame: dict, on_text=None) -> dict:
    """编剧成文，并写下本回合实际成立之事的梗概（它同时看见节拍与未成立，是唯一有资格记账的人）。
    给了 on_text 且模型能流式，就边写边送；半途失声时已写出的即为正文，一字未得才走兜底。"""
    prompt = prompts.writer(pack, frame)
    fallback = lambda: "\n".join([pack["scene"]["desc"], *frame["beats"]])
    if on_text and hasattr(llm, "stream"):
        parts, showing = [], True
        try:
            for delta in llm.stream(*prompt, max_tokens=1400):
                parts.append(delta)
                if showing:
                    showing = _show(on_text, "".join(parts), delta)
            return _page("".join(parts), frame)
        except LLMError as e:
            log.warning("编剧流式中断（已得 %d 段）：%s", len(parts), e)
            if parts:
                return _page("".join(parts), frame)
    page = _page(_ask(llm, prompt, fallback, as_json=False, tokens=1400), frame)
    if on_text:
        on_text(page["text"])  # 不能流式时，整段作一次送出，调用方无须区分
    return page


def recap(llm, synopsis: str, lines: list[str]) -> str:
    """近事溢出时折叠进梗概：上下文有界，记忆无界。"""
    fallback = lambda: {"synopsis": "；".join(x for x in [synopsis, *lines] if x)[-300:]}
    r = _ask(llm, prompts.recap(synopsis, lines), fallback, tokens=400)
    return str(r.get("synopsis") or fallback()["synopsis"])[:300]


# ============================================================
#  LOD1 / LOD2：场外剧情，后果落账在 world/lod + world/effects
# ============================================================
def simulate(llm, time: str, days: int, actors: list[dict], heard=()) -> list[dict]:
    r = _ask(llm, prompts.simulator(time, days, actors, heard), lambda: {"reports": []}, tokens=800)
    return _dicts(r.get("reports"))[:2]


def chronicle(llm, ev: dict, reasons: list[str], actors: list[dict], broken: bool, heard=()) -> dict:
    fallback = lambda: {"happens": not broken, "summary": ev["summary"], "effects": ev["effects"]}
    r = _ask(llm, prompts.chronicler(ev, reasons, actors, heard), fallback, tokens=800)
    return {"happens": bool(r.get("happens")), "summary": str(r.get("summary") or ev["summary"])[:120],
            "effects": _dicts(r.get("effects"))}
