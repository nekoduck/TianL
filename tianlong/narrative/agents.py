"""
[INPUT]: 依赖 narrative/prompts 的四组提示词组装器，依赖 narrative/llm 的 LLMError；llm 参数鸭子类型（Gemini 或 None）
[OUTPUT]: 对外提供 direct()（导演：裁定+创造）、write()（编剧）、simulate()（LOD1 推演）、chronicle()（LOD2 史官）
[POS]: narrative 层的四个 Agent——每个都是「组装→调用→整形→兜底」：整形只保证输出形状可用，不审查内容，
       内容是否成立交给 world/effects 的世界物理；llm 为 None 或调用失败时走朴素兜底，离线亦可运行
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging

from . import prompts
from .llm import LLMError

log = logging.getLogger("tianlong")
MAX_ELAPSED = 12 * 30  # 单回合至多一月，长途跋涉由系统另按道路结算


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
#  LOD0：导演（裁定 + 创造）
# ============================================================
def _plain_director(pack: dict, deed: str) -> dict:
    """离线兜底：只会走路与旁观的朴素说书人。"""
    exits = [e["name"] for e in pack["exits"]]
    dest = next((e for e in exits if e in deed), None)
    beats = [f"你动身前往{dest}。"] if dest else [f"你{deed}。" if deed else "你凝神四顾。"]
    return {"beats": beats, "elapsed": 1 if deed else 0, "event": None, "memory": beats[0],
            "effects": [{"op": "set", "id": "player", "key": "location", "value": dest}] if dest else [],
            "options": _plain_options(pack)}


def _plain_options(pack: dict) -> list[str]:
    opts = [f"与{p['name']}攀谈" for p in pack["people"][:2]] + [f"前往{e['name']}" for e in pack["exits"]]
    return (opts + ["歇息片刻", "四下察看"])[:3]


def direct(llm, pack: dict, gm: dict, deed: str) -> dict:
    r = _ask(llm, prompts.director(pack, gm, deed or "初来乍到，环顾四周"),
             lambda: _plain_director(pack, deed), tokens=1500)
    beats = [str(b) for b in r.get("beats") or [] if b][:6] or ["你凝神四顾。"]
    elapsed = r.get("elapsed")
    event = r.get("event") if isinstance(r.get("event"), dict) and r["event"].get("summary") else None
    options = [str(o)[:20] for o in r.get("options") or [] if o][:3]
    return {"beats": beats,
            "effects": _dicts(r.get("effects")),
            "elapsed": max(0, min(MAX_ELAPSED, elapsed)) if isinstance(elapsed, int) else 1,
            "event": event and {"summary": str(event["summary"])[:80], "weight": 2 if event.get("weight") == 2 else 1},
            "options": options + _plain_options(pack)[len(options):],
            "memory": str(r.get("memory") or beats[0])[:60]}


def write(llm, pack: dict, deed: str, beats: list[str], void: list[str], news: list[str]) -> str:
    fallback = lambda: "\n".join([pack["scene"]["desc"], *beats, *(f"（传闻）{n}" for n in news)])
    return _ask(llm, prompts.writer(pack, deed, beats, void, news), fallback, as_json=False, tokens=1200)


# ============================================================
#  LOD1 / LOD2：场外创造，物化与物理校验在 world/lod + world/effects
# ============================================================
def simulate(llm, time: str, days: int, actors: list[dict]) -> list[dict]:
    r = _ask(llm, prompts.simulator(time, days, actors), lambda: {"reports": []}, tokens=800)
    return _dicts(r.get("reports"))[:2]


def chronicle(llm, ev: dict, reasons: list[str], actors: list[dict], broken: bool) -> dict:
    fallback = lambda: {"happens": not broken, "summary": ev["summary"], "effects": ev["effects"]}
    r = _ask(llm, prompts.chronicler(ev, reasons, actors), fallback, tokens=800)
    return {"happens": bool(r.get("happens")), "summary": str(r.get("summary") or ev["summary"])[:120],
            "effects": _dicts(r.get("effects"))}
