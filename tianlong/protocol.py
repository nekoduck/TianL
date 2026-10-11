"""
[INPUT]: 依赖 engine 回合产物 Turn（纯 dict）的字段约定：time/clock/place/region/text/options/news/status
[OUTPUT]: 对外提供 VERSION、ProtocolError、present()（Turn → 回合载荷）、relay()（引擎进度 → 流式事件）、session_payload()、
          resolve()（玩家行动 → 引擎原话；写明所应答的卷与回合时须与眼下一致）、hero_name()（开卷名号校验）
[POS]: 前后端契约的 Python 实现——向外把引擎回合翻译成协议载荷，向内把协议行动翻译回引擎原话；
       契约正文见 web/PROTOCOL.md，web/js/api.js 与 web/js/mock.js 是它在前端的两面镜子
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

VERSION = "tianlong/1.3"  # 次版本只做向后兼容的增补（1.1：流式推送；1.2：行动写明卷与回合；1.3：选项随 done 放出，head 的 options 为空）；客户端只比对主版本
ACTION_TYPES = ("selection", "free_text")
MAX_TEXT = 200
MAX_NAME = 12


class ProtocolError(Exception):
    """携带 HTTP 状态与机器可读错误码的契约错误；传输层原样转成错误载荷。"""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def payload(self) -> dict:
        return {"protocol": VERSION, "error": {"code": self.code, "message": self.message}}


# ============================================================
#  向外：引擎回合 → 协议载荷
# ============================================================
def present(turn: dict, n: int, deed: dict | None) -> dict:
    """第 n 回合的载荷。选项编号带回合序（t{n}-{i}），过期的选择因此可被识破。"""
    return {
        "protocol": VERSION,
        "turn": n,
        "deed": deed,
        "scene": {"place": turn["place"], "region": turn.get("region")},
        "time": {**turn["clock"], "label": turn["time"]},
        "narrative": turn["text"],
        "options": [{"id": f"t{n}-{i}", "label": label} for i, label in enumerate(turn["options"], 1)],
        "status": turn["status"],
        "events": [{"id": e["id"], "kind": "witnessed" if e["witnessed"] else "rumor",
                    "date": e["date"], "place": e["place"], "text": e["text"]} for e in turn["news"]],
    }


def relay(send, n: int, deed: dict | None):
    """引擎监听 → 协议流式事件：stage{stage} · head(回合载荷，narrative 为空串) · text{delta}；done 由传输层补上。"""
    def on(kind: str, data):
        if kind == "stage":
            send("stage", {"stage": data})
        elif kind == "head":
            send("head", present(data, n, deed))
        elif kind == "text":
            send("text", {"delta": data})
    return on


def session_payload(sid: str | None, hero: str | None, transcript: list[dict]) -> dict:
    """会话载荷；尚未开卷时 session 为 null。"""
    session = {"id": sid, "hero": hero} if sid else None
    return {"protocol": VERSION, "session": session, "transcript": transcript}


# ============================================================
#  向内：协议行动 → 引擎原话（选项即原话）
# ============================================================
def resolve(body, current: dict, sid: str | None = None) -> tuple[dict, str]:
    """校验行动并解出交给引擎的原话；返回 (deed, 原话)。selection 必须指向当前回合的选项；
    行动若写明所应答的卷(session)与回合(turn)，须与眼下一致——刷新、另开一卷、超时重试之后的旧笔，不会落在翻过的书页上。"""
    if not isinstance(body, dict) or body.get("action_type") not in ACTION_TYPES \
            or not isinstance(body.get("action_content"), str):
        raise ProtocolError(400, "bad_request", "行动须含 action_type（selection 或 free_text）与文本 action_content")
    if ("session" in body and body["session"] != sid) or ("turn" in body and body["turn"] != current["turn"]):
        raise ProtocolError(409, "stale_turn", "书页已经翻过，请依眼下情形重新落笔")
    kind, content = body["action_type"], body["action_content"].strip()
    if kind == "selection":
        text = next((o["label"] for o in current["options"] if o["id"] == content), None)
        if text is None:
            raise ProtocolError(409, "stale_option", "这个选项已随时势而去，请依眼下情形重新抉择")
    else:
        if not content:
            raise ProtocolError(400, "bad_request", "请写下你想做的事")
        if len(content) > MAX_TEXT:
            raise ProtocolError(400, "bad_request", f"一次行动请勿超过{MAX_TEXT}字")
        text = content
    return {"action_type": kind, "action_content": content, "text": text}, text


def hero_name(body) -> str | None:
    if not isinstance(body, dict):
        raise ProtocolError(400, "bad_request", "开卷请求须为 JSON 对象")
    name = body.get("name")
    if name is not None and not isinstance(name, str):
        raise ProtocolError(400, "bad_request", "名号须为文字")
    name = (name or "").strip()
    if len(name) > MAX_NAME:
        raise ProtocolError(400, "bad_request", f"名号请勿超过{MAX_NAME}字")
    return name or None
