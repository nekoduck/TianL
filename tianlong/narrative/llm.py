"""
[INPUT]: 依赖 urllib（标准库直连 Gemini REST，零第三方依赖），读取环境变量 GEMINI_API_KEY / GEMINI_MODEL
[OUTPUT]: 对外提供 _object()（v12 JSON 回包 → 对象的纯函数：去围栏、补括号、单元素数组取其中的对象，重演工具同一口径）、Gemini（text / json / stream 三种调用，可选 trace 把每次调用记成 JSONL，含收尾缘由 finishReason；v11 json 漏了末尾几个右括号按括号栈补齐(_mend)）、sse_texts()（SSE 行 → 文本增量）、LLMError、from_env()
[POS]: narrative 层的模型网关，是全项目唯一发出网络请求的地方；关闭思考预算以省 token，累计用量供 /debug 查看。
       stream 走 streamGenerateContent?alt=sse，供编剧边写边送；trace 供提示词迭代留下证据。
       一切网络与回包故障（连不上、超时、断流 IncompleteRead、回包不是 JSON、被安全策略半途截断）都化为 LLMError，交上层兜底——绝不让一回合半途炸开；
       用量与 trace 加锁：场外编剧、梗概折叠与编剧并行调用；strict=True(v5)：导演这一笔失败即整回合作废(agents._ask)，不以离线说书人代演
       v13：_object 把一串带 text 的拍(返工回成拍数组，第 46 回)包成 {beats}
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import http.client
import json
import logging
import os
import re
import threading
import time
import urllib.request
from pathlib import Path

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}"
DEFAULT_MODEL = "gemini-flash-latest"
NET_ERRORS = (OSError, http.client.HTTPException, ValueError)  # 连不上、超时、断流(IncompleteRead)、回包不是 JSON：一律化为 LLMError
log = logging.getLogger("tianlong")


class LLMError(Exception):
    pass


def _texts(data: dict) -> str:
    try:
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        return ""


def sse_texts(lines, usage: dict):
    """把 SSE 字节行解成文本增量；每块的 usageMetadata 累计值写入 usage["total"]（取最后一次）。"""
    for raw in lines:
        line = raw.decode("utf-8").strip() if isinstance(raw, bytes) else raw.strip()
        if not line.startswith("data:"):
            continue
        data = json.loads(line[5:].strip())
        usage["total"] = data.get("usageMetadata", {}).get("totalTokenCount", usage.get("total", 0))
        usage["finish"] = (data.get("candidates") or [{}])[0].get("finishReason") or usage.get("finish")
        text = _texts(data)
        if text:
            yield text


class Gemini:
    strict = True  # 导演失声不演假戏：导演这一笔调用失败即整回合作废(agents._ask)，其余 Agent 照旧兜底

    def __init__(self, key: str, model: str = DEFAULT_MODEL, timeout: int = 60, trace=None):
        self.key, self.model, self.timeout = key, model, timeout
        self.tokens = 0  # 累计消耗，用于自查成本
        self.trace = Path(trace) if trace else None  # 每次调用一行 JSONL：提示词、回答、用量、耗时、收尾缘由
        self._lock = threading.Lock()  # 场外编剧、梗概折叠与编剧并行：用量与 trace 一笔一锁

    def _log(self, system: str, user: str, text: str, used: int, t0: float, finish=None):
        with self._lock:
            self.tokens += used
            if self.trace:
                self.trace.parent.mkdir(parents=True, exist_ok=True)
                with self.trace.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"model": self.model, "secs": round(time.time() - t0, 1), "tokens": used,
                                        "finish": finish, "system": system, "user": user, "raw": text},
                                       ensure_ascii=False) + "\n")

    def _request(self, method: str, system: str, user: str, *, as_json: bool, max_tokens: int,
                 temperature: float) -> urllib.request.Request:
        config = {"maxOutputTokens": max_tokens, "temperature": temperature,
                  "thinkingConfig": {"thinkingBudget": 0}}
        if as_json:
            config["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": config}
        return urllib.request.Request(ENDPOINT.format(model=self.model, method=method), data=json.dumps(body).encode(),
                                      headers={"Content-Type": "application/json", "X-goog-api-key": self.key})

    def _call(self, system: str, user: str, *, as_json: bool, max_tokens: int, temperature: float) -> str:
        req = self._request("generateContent", system, user, as_json=as_json, max_tokens=max_tokens,
                            temperature=temperature)
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except NET_ERRORS as e:
            raise LLMError(f"请求失败：{e}") from e
        used = data.get("usageMetadata", {}).get("totalTokenCount", 0)
        text = _texts(data)
        self._log(system, user, text, used, t0, (data.get("candidates") or [{}])[0].get("finishReason"))
        if not text:
            raise LLMError(f"响应无内容：{str(data)[:200]}")
        return text

    def text(self, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.9) -> str:
        return self._call(system, user, as_json=False, max_tokens=max_tokens, temperature=temperature).strip()

    def json(self, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.7) -> dict:
        return _object(self._call(system, user, as_json=True, max_tokens=max_tokens, temperature=temperature))

    def stream(self, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.9):
        """逐块产出正文增量；任何网络或解析失败都化为 LLMError（调用方据已得多少决定如何收场）。"""
        req = self._request("streamGenerateContent?alt=sse", system, user, as_json=False, max_tokens=max_tokens,
                            temperature=temperature)
        usage, parts, t0 = {}, [], time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for delta in sse_texts(resp, usage):
                    parts.append(delta)
                    yield delta
        except NET_ERRORS as e:
            raise LLMError(f"流式请求中断：{e}") from e
        finally:
            self._log(system, user, "".join(parts), usage.get("total", 0), t0, usage.get("finish"))
        if usage.get("finish") not in (None, "STOP", "MAX_TOKENS"):  # 安全策略等半途截断：交上层判断已写出的够不够用
            raise LLMError(f"流式输出被截断：{usage['finish']}")


def _object(raw: str) -> dict:
    """模型的 JSON 回包 → 一个对象(纯函数，重演工具同一口径)：去掉围栏；漏了末尾几个右括号按括号栈补齐(_mend)；
    v12 偶尔回成单元素数组 [{…}]，元素是对象即取它(记一条日志)；多元素或不是对象仍抛 LLMError 交兜底。"""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        mended = _mend(raw)
        try:
            data = json.loads(mended) if mended else None
        except json.JSONDecodeError:
            data = None
        if data is None:
            raise LLMError(f"JSON 解析失败：{raw[:200]}") from e
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        log.info("模型回了单元素数组，取其中的对象")
        data = data[0]
    elif isinstance(data, list) and data and all(isinstance(x, dict) and "text" in x for x in data):
        log.info("模型回了一串拍，包成 {beats: […]}")  # v13 第 46 回返工回的是四元素的拍数组，被当作格式错误放弃，服用那一拍就此作废
        data = {"beats": data}
    if not isinstance(data, dict):
        raise LLMError("期望 JSON 对象")
    return data


def _mend(raw: str) -> str | None:
    """模型偶尔漏写末尾的几个右括号(JSON 模式下、层层嵌套的清单里也会，收尾缘由照样是 STOP)：按括号栈补齐，字串没收口先收口。
    括号对不上、或本就齐全，返回 None——那是别的毛病，照旧交兜底。"""
    stack, quoted, escaped = [], False, False
    for ch in raw:
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and (not stack or stack.pop() != ch):
            return None
    if not stack:
        return None
    body = raw + ('"' if quoted else "")
    body = body.rstrip().rstrip(",")
    return body + "".join(reversed(stack))


def from_env(trace=None) -> Gemini | None:
    key = os.environ.get("GEMINI_API_KEY")
    return Gemini(key, os.environ.get("GEMINI_MODEL", DEFAULT_MODEL), trace=trace) if key else None
