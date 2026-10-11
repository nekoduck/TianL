"""
[INPUT]: 依赖 urllib（标准库直连 Gemini REST，零第三方依赖），读取环境变量 GEMINI_API_KEY / GEMINI_MODEL
[OUTPUT]: 对外提供 Gemini（text / json / stream 三种调用，可选 trace 把每次调用记成 JSONL）、sse_texts()（SSE 行 → 文本增量）、LLMError、from_env()
[POS]: narrative 层的模型网关，是全项目唯一发出网络请求的地方；关闭思考预算以省 token，累计用量供 /debug 查看。
       stream 走 streamGenerateContent?alt=sse，供编剧边写边送；trace 供提示词迭代留下证据。
       一切网络与回包故障（连不上、超时、断流 IncompleteRead、回包不是 JSON）都化为 LLMError，交上层兜底——绝不让一回合半途炸开
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import http.client
import json
import os
import re
import time
import urllib.request
from pathlib import Path

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}"
DEFAULT_MODEL = "gemini-flash-latest"
NET_ERRORS = (OSError, http.client.HTTPException, ValueError)  # 连不上、超时、断流(IncompleteRead)、回包不是 JSON：一律化为 LLMError


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
        text = _texts(data)
        if text:
            yield text


class Gemini:
    def __init__(self, key: str, model: str = DEFAULT_MODEL, timeout: int = 60, trace=None):
        self.key, self.model, self.timeout = key, model, timeout
        self.tokens = 0  # 累计消耗，用于自查成本
        self.trace = Path(trace) if trace else None  # 每次调用一行 JSONL：提示词、回答、用量、耗时

    def _log(self, system: str, user: str, text: str, used: int, t0: float):
        if self.trace:
            self.trace.parent.mkdir(parents=True, exist_ok=True)
            with self.trace.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"model": self.model, "secs": round(time.time() - t0, 1), "tokens": used,
                                    "system": system, "user": user, "raw": text}, ensure_ascii=False) + "\n")

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
        self.tokens += used
        text = _texts(data)
        if not text:
            raise LLMError(f"响应无内容：{str(data)[:200]}")
        self._log(system, user, text, used, t0)
        return text

    def text(self, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.9) -> str:
        return self._call(system, user, as_json=False, max_tokens=max_tokens, temperature=temperature).strip()

    def json(self, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.7) -> dict:
        raw = self._call(system, user, as_json=True, max_tokens=max_tokens, temperature=temperature)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise LLMError(f"JSON 解析失败：{raw[:200]}") from e
        if not isinstance(data, dict):
            raise LLMError("期望 JSON 对象")
        return data

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
            self.tokens += usage.get("total", 0)
            self._log(system, user, "".join(parts), usage.get("total", 0), t0)


def from_env(trace=None) -> Gemini | None:
    key = os.environ.get("GEMINI_API_KEY")
    return Gemini(key, os.environ.get("GEMINI_MODEL", DEFAULT_MODEL), trace=trace) if key else None
