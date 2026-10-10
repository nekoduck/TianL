"""
[INPUT]: 依赖 urllib（标准库直连 Gemini REST，零第三方依赖），读取环境变量 GEMINI_API_KEY / GEMINI_MODEL
[OUTPUT]: 对外提供 Gemini（text / json 两种调用）、LLMError、from_env()
[POS]: narrative 层的模型网关，是全项目唯一发出网络请求的地方；关闭思考预算以省 token，累计用量供 /debug 查看
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import os
import re
import urllib.error
import urllib.request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-flash-latest"


class LLMError(Exception):
    pass


class Gemini:
    def __init__(self, key: str, model: str = DEFAULT_MODEL, timeout: int = 60):
        self.key, self.model, self.timeout = key, model, timeout
        self.tokens = 0  # 累计消耗，用于自查成本

    def _call(self, system: str, user: str, *, as_json: bool, max_tokens: int, temperature: float) -> str:
        config = {"maxOutputTokens": max_tokens, "temperature": temperature,
                  "thinkingConfig": {"thinkingBudget": 0}}
        if as_json:
            config["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": config}
        req = urllib.request.Request(ENDPOINT.format(model=self.model), data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "X-goog-api-key": self.key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise LLMError(f"请求失败：{e}") from e
        self.tokens += data.get("usageMetadata", {}).get("totalTokenCount", 0)
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as e:
            raise LLMError(f"响应无内容：{str(data)[:200]}") from e

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


def from_env() -> Gemini | None:
    key = os.environ.get("GEMINI_API_KEY")
    return Gemini(key, os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)) if key else None
