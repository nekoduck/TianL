"""
[INPUT]: 依赖 narrative/prompts 的五组提示词组装器，依赖 narrative/llm 的 LLMError；llm 参数鸭子类型（Gemini 或 None）
[OUTPUT]: 对外提供 parse()（动作解析）、direct()（导演）、write()（编剧）、simulate()（LOD1 推演）、chronicle()（LOD2 史官）
[POS]: narrative 层的五个 Agent——每个都是「组装→调用→校验→兜底」四步；llm 为 None 或调用失败时走确定性兜底，
       故离线模式与在线模式共用同一条代码路径。Agent 只产出文本或"提案"，从不直接触碰 World
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import logging

from . import prompts
from .llm import LLMError

log = logging.getLogger("tianlong")

VERB_HINTS = {"go": "去往赴走回奔", "talk": "说问聊谈拜请", "fight": "打攻杀斗战劈", "take": "拿取捡拾收",
              "examine": "看察查观翻摸磕拜跪", "study": "练读学研修参", "rest": "歇睡坐休息调"}
DIVERSITY = ("talk", "examine", "take", "study", "go", "fight", "rest")  # 兜底选项的方向优先级


def _ask(llm, prompt: tuple[str, str], fallback, *, as_json=True, tokens=800):
    if llm is None:
        return fallback()
    try:
        return llm.json(*prompt, max_tokens=tokens) if as_json else llm.text(*prompt, max_tokens=tokens)
    except LLMError as e:
        log.warning("LLM 调用失败，走确定性兜底：%s", e)
        return fallback()


def _keyword_match(text: str, actions: list[dict]) -> int:
    best, score = -1, 0
    for i, a in enumerate(actions):
        s = (2 if a["target"] and a["target"] in text else 0) + any(ch in text for ch in VERB_HINTS[a["verb"]])
        if s > score and (a["target"] is None or s >= 2):
            best, score = i, s
    return best


def _diverse(actions: list[dict]) -> list[int]:
    picks = []
    for verb in DIVERSITY:
        picks += [i for i, a in enumerate(actions) if a["verb"] == verb][:1]
    return picks


# ============================================================
#  LOD0
# ============================================================
def parse(llm, text: str, actions: list[dict]) -> dict:
    """自由文本 → 合法行动之一（或 emote）。LLM 只能挑序号，不能发明目标。"""
    r = _ask(llm, prompts.parser(text, actions), lambda: {"i": _keyword_match(text, actions)}, tokens=150)
    i = r.get("i")
    intent = dict(actions[i]) if isinstance(i, int) and 0 <= i < len(actions) else \
        {"verb": "emote", "target": None, "label": "自行其是"}
    intent["manner"] = str(r.get("manner") or text)[:60]
    return intent


def direct(llm, pack: dict, act: str, facts: list[str], actions: list[dict]) -> dict:
    """导演：节拍 + 从合法行动中挑 3 个方向迥异的选项。"""
    fallback = lambda: {"beats": facts, "options": []}
    r = _ask(llm, prompts.director(pack, act, facts, actions), fallback, tokens=600)
    beats = [str(b) for b in r.get("beats") or [] if b][:5] or facts or ["你凝神四顾。"]
    picks: dict[int, str] = {}
    for o in r.get("options") or []:
        i = o.get("i") if isinstance(o, dict) else None
        if isinstance(i, int) and 0 <= i < len(actions) and i not in picks:
            picks[i] = str(o.get("label") or actions[i]["label"])[:20]
    for i in _diverse(actions):  # LLM 给不足 3 个合法选项时，由系统补齐
        if len(picks) >= 3:
            break
        picks.setdefault(i, actions[i]["label"])
    return {"beats": beats, "options": [{**actions[i], "label": label} for i, label in list(picks.items())[:3]]}


def write(llm, pack: dict, act: str, facts: list[str], beats: list[str]) -> str:
    fallback = lambda: "\n".join([pack["scene"]["desc"], *beats])
    return _ask(llm, prompts.writer(pack, act, facts, beats), fallback, as_json=False, tokens=1200)


# ============================================================
#  LOD1 / LOD2：只产出结构化提案，落账与权限过滤在 world/lod + world/effects
# ============================================================
def simulate(llm, time: str, days: int, actors: list[dict]) -> list[dict]:
    r = _ask(llm, prompts.simulator(time, days, actors), lambda: {"reports": []}, tokens=400)
    return [x for x in r.get("reports") or [] if isinstance(x, dict)][:2]


def chronicle(llm, ev: dict, reasons: list[str], actors: list[dict], broken: bool) -> dict:
    fallback = lambda: {"happens": not broken, "summary": ev["summary"], "effects": ev["effects"]}
    r = _ask(llm, prompts.chronicler(ev, reasons, actors), fallback, tokens=500)
    return {"happens": bool(r.get("happens")), "summary": str(r.get("summary") or ev["summary"])[:120],
            "effects": [x for x in r.get("effects") or [] if isinstance(x, dict)]}
