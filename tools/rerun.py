"""
[INPUT]: 依赖 tianlong.engine 的 Game、tianlong.world.world 的 World 与 blackboard 的 ORIGINS、world/situation 的 around / cast、narrative/llm 的 LLMError；
         读一份对局日志(markdown：每回合「#### 角色（trace 第 N 行…）」下有 <details> 里的系统提示与上下文，其后是模型的原始输出)
[OUTPUT]: 命令行工具：python -m tools.rerun <日志.md> [--turns N] [--watch 人名,…] [--out 报告.md]——
          用日志里真实的导演/返工/编剧/账房(v6)/史官/推演/书记输出驱动当前引擎重演一遍，逐回合报告去处、未成立之事、体检、结算入账与账文分歧、眼前之人、
          所盯人物的下落、亲见与传闻、场况，末尾附账本与原著结算；亦可 import：parse(text) → [{turn, deed, calls{角色: [输出…]}}]
[POS]: 回放验收——不调用模型、不发网络请求：同一份真实模型输出交给新引擎，看裁决、在场、原著与账本还会不会打架。
       世界会与原局分叉(新引擎裁决不同)，越往后越只是「同样的模型话语落在新世界上」；它量的是新引擎能否接住真模型的写法，而不是复刻原局
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

from tianlong.engine import Game
from tianlong.narrative.llm import LLMError
from tianlong.world import situation
from tianlong.world.blackboard import ORIGINS
from tianlong.world.world import World

TURN = re.compile(r"^## 第 (\d+) 回 · ", re.M)
CALL = re.compile(r"^#### ([^（\s]+)(?:（[^（）]*）)?（trace 第 \d+ 行", re.M)  # 「书记（后台）（trace…」也认
BLOCK = re.compile(r"```(?:json|text)?\n(.*?)\n```", re.S)
DEED = re.compile(r"【主角此刻】(.*)")
ROLES = {"导演初稿": "draft", "导演返工": "repair", "编剧": "writer", "账房": "settle", "史官": "chronicle", "场外推演": "simulate", "书记": "recap"}


# ============================================================
#  解析：每回合的举动与各角色的原始输出
# ============================================================
def parse(text: str) -> list[dict]:
    marks = list(TURN.finditer(text))
    turns = []
    for i, m in enumerate(marks):
        body = text[m.start():marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        turn = {"turn": int(m.group(1)), "deed": None, "calls": {}, "context": ""}
        calls = list(CALL.finditer(body))
        for j, c in enumerate(calls):
            role = ROLES.get(c.group(1))
            if not role:
                continue
            chunk = body[c.start():calls[j + 1].start() if j + 1 < len(calls) else len(body)]
            inside, _, after = chunk.partition("</details>")
            blocks = BLOCK.findall(after)
            if not blocks:
                continue
            raw = blocks[0]
            turn["calls"].setdefault(role, []).append(raw)
            if role == "draft":
                prompt = "\n".join(BLOCK.findall(inside))
                turn["context"] = prompt
                d = DEED.search(prompt)
                turn["deed"] = d.group(1).strip() if d else None
        turns.append(turn)
    return turns


def _json(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return None


class ReplayLLM:
    """按回合吐出日志里的原始输出：导演首稿与返工、编剧正文、账房的结算单(v6)按本回合取；史官、推演、书记按出现次序排队。没有的就当模型失声
    (账房失声即只以词表对账——v6 之前的日志没有账房)。"""
    strict = False

    def __init__(self, turns: list[dict]):
        self.turns, self.now, self.tokens = turns, 0, 0
        self.queues = {k: [r for t in turns for r in t["calls"].get(k, [])] for k in ("chronicle", "simulate", "recap")}
        self.used = {k: 0 for k in self.queues}

    def at(self, i: int):
        self.now = i
        self.repairs = list(self.turns[i]["calls"].get("repair", []))

    def _queued(self, kind: str):
        q, n = self.queues[kind], self.used[kind]
        if n >= len(q):
            raise LLMError(f"日志里没有更多的{kind}输出")
        self.used[kind] += 1
        return _json(q[n])

    def json(self, system, user, max_tokens=0):
        calls = self.turns[self.now]["calls"]
        if "说书人与导演" in system:
            if "【上一稿】" in user:
                if not self.repairs:
                    raise LLMError("这一回合日志里没有返工")
                return _json(self.repairs.pop(0))
            if not calls.get("draft"):
                raise LLMError("这一回合日志里导演失声")
            return _json(calls["draft"][0])
        if "账房" in system:
            if not calls.get("settle"):
                raise LLMError("这一回合日志里没有账房")
            return _json(calls["settle"][0])
        for key, kind in (("史官", "chronicle"), ("场外推演", "simulate"), ("书记", "recap")):
            if key in system:
                return self._queued(kind)
        raise LLMError("日志里没有对应的调用")

    def text(self, system, user, max_tokens=0):
        out = self.turns[self.now]["calls"].get("writer")
        if not out:
            raise LLMError("这一回合日志里编剧失声")
        return out[-1]


# ============================================================
#  重演与报告
# ============================================================
class _Log(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def _hero(turns: list[dict]) -> tuple[str | None, str | None]:
    """主角名号与出身：从首回合导演上下文的【主角】一行读出。"""
    m = re.search(r"【主角】([^｜\n]+)｜([^｜\n]+)", turns[0]["context"]) if turns else None
    if not m:
        return None, None
    origin = next((k for k, v in ORIGINS.items() if v["origin"] == m.group(2).strip()), None)
    return m.group(1).strip(), origin


def rerun(turns: list[dict], limit: int | None = None, watch=("段誉",)) -> str:
    name, origin = _hero(turns)
    llm, out = ReplayLLM(turns), []
    game = Game(World.create(name, origin=origin), llm)
    sink = _Log()
    logging.getLogger("tianlong").addHandler(sink)
    logging.getLogger("tianlong").setLevel(logging.INFO)
    try:
        for i, t in enumerate(turns[:limit] if limit else turns):
            llm.at(i)
            w, sink.lines = game.world, []
            before = w.here
            try:
                turn = game.open() if i == 0 else game.act(t["deed"] or "")
            except LLMError as e:
                out.append(f"## 第 {t['turn']} 回 · {t['deed']}\n- 回合作废：{e}\n")
                continue
            w = game.world
            out.append(f"## 第 {t['turn']} 回 · {t['deed'] or '开卷'}\n"
                       f"- {turn['time']}｜{before} → {w.here}｜场：{(w.player['scene'] or {}).get('state')}「{(w.player['scene'] or {}).get('ask')}」\n"
                       f"- 眼前：{'、'.join(sorted(situation.around(w))) or '无人'}｜名册：{'、'.join(sorted(situation.cast(w))) or '—'}\n"
                       + "".join(f"- 盯着 {p}：{w.graph.get(p, 'location')}（{w.graph.get(p, 'status')}）\n" for p in watch)
                       + "".join(f"- 未成立：{v}\n" for v in turn["void"])
                       + "".join(f"- 日志：{line}\n" for line in sink.lines if line.startswith(("导演返工", "体检", "原著", "结算入账", "账文分歧", "幕间省略")))
                       + "".join(f"- {'亲见' if n['witnessed'] else '传闻'}：{n['text']}\n" for n in turn["news"])
                       + f"- 选项：{' / '.join(turn['options'])}\n")
    finally:
        logging.getLogger("tianlong").removeHandler(sink)
    w = game.world
    out.append("## 账本\n" + "".join(f"- [{e['origin']}·{e['day']}·{e['where']}] {e['summary']}\n" for e in w.truth.events))
    out.append(f"## 原著\n- 已结算 {len(w.done)} 桩：{'、'.join(w.done)}\n")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="用对局日志里的真实模型输出驱动当前引擎重演")
    ap.add_argument("log", type=Path)
    ap.add_argument("--turns", type=int)
    ap.add_argument("--watch", default="段誉")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    report = rerun(parse(args.log.read_text("utf-8")), args.turns, tuple(x for x in args.watch.split(",") if x))
    if args.out:
        args.out.write_text(report, "utf-8")
    else:
        sys.stdout.write(report)


if __name__ == "__main__":
    main()
