"""
[INPUT]: 依赖 tianlong.engine 的 Game、tianlong.world.world 的 World 与 blackboard 的 ORIGINS、world/situation 的 around / cast、narrative/llm 的 LLMError / _object（v12 原始输出与线上同一口径解析）；
         读一份对局日志(markdown：每回合「#### 角色（trace 第 N 行…）」下有 <details> 里的系统提示与上下文，其后是模型的原始输出)
[OUTPUT]: 命令行工具：python -m tools.rerun <日志.md> [--turns N] [--watch 人名,…] [--out 报告.md]——
          用日志里真实的导演/返工/编剧/账房(v6)/复核(v7)/场外编剧与审稿(v11)/书记输出驱动当前引擎重演一遍，逐回合报告去处、未成立之事、体检、结算入账与账文分歧、补记与新立的外号(v7)、眼前之人、
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
from tianlong.narrative.llm import LLMError, _object
from tianlong.world import body, situation
from tianlong.world.settle import TECHNICAL
from tianlong.world.blackboard import ORIGINS
from tianlong.world.world import World

TURN = re.compile(r"^## 第 (\d+) 回 · ", re.M)
CALL = re.compile(r"^#### ([^（\s·]+)(?:（[^（）]*）)?\s*(?:（|·\s*)trace 第 \d+ 行", re.M)  # 「书记（后台）（trace…」与导出的「导演初稿 · trace 第 N 行」都认(v13)
OUTPUT = "**模型输出（原文）**"                                               # 导出的 game.md 里，系统提示词与输入上下文在前，这一行之后才是模型的原始输出
BLOCK = re.compile(r"```(?:json|text)?\n(.*?)\n```", re.S)
DEED = re.compile(r"【主角此刻】(.*)")
ROLES = {"导演初稿": "draft", "导演返工": "repair", "编剧": "writer", "账房": "settle", "复核": "recheck", "场外编剧": "plot", "审稿": "review", "书记": "recap"}
QUEUED = (("审稿", "review"), ("场外编剧", "plot"), ("书记", "recap"))  # 审稿人的系统提示里也有「场外编剧」：先认审稿


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
            inside, _, after = chunk.partition(OUTPUT) if OUTPUT in chunk else chunk.partition("</details>")
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


class ReplayLLM:
    """按回合吐出日志里的原始输出：导演首稿与返工、编剧正文、账房的结算单(v6)、复核的裁定(v7)按本回合取；场外编剧与审稿(v11，后台写)、书记按出现次序排队。没有的就当模型失声
    (账房失声即只以词表对账——v6 之前的日志没有账房；复核失声，那几句只记分歧)。"""
    strict = False

    def __init__(self, turns: list[dict]):
        self.turns, self.now, self.tokens = turns, 0, 0
        self.queues = {k: [r for t in turns for r in t["calls"].get(k, [])] for _, k in QUEUED}
        self.used = {k: 0 for k in self.queues}

    def at(self, i: int):
        self.now = i
        self.repairs = list(self.turns[i]["calls"].get("repair", []))

    def _queued(self, kind: str) -> str:
        q, n = self.queues[kind], self.used[kind]
        if n >= len(q):
            raise LLMError(f"日志里没有更多的{kind}输出")
        self.used[kind] += 1
        return q[n]

    def json(self, system, user, max_tokens=0):
        """原始输出过 narrative/llm._object 再交引擎(v12)：与线上同一口径——单元素数组取其中的对象，解析不了即抛 LLMError 交兜底。"""
        return _object(self._raw(system, user))

    def _raw(self, system, user) -> str:
        calls = self.turns[self.now]["calls"]
        if "说书人与导演" in system:
            if "【上一稿】" in user:
                if not self.repairs:
                    raise LLMError("这一回合日志里没有返工")
                return self.repairs.pop(0)
            if not calls.get("draft"):
                raise LLMError("这一回合日志里导演失声")
            return calls["draft"][0]
        if "复核" in system:  # v7 双录复核：旧日志没有即当失声，那几句只记分歧
            if not calls.get("recheck"):
                raise LLMError("这一回合日志里没有复核")
            return calls["recheck"][0]
        if "账房" in system:
            if not calls.get("settle"):
                raise LLMError("这一回合日志里没有账房")
            return calls["settle"][0]
        for key, kind in QUEUED:
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


def load(path: Path) -> list[dict]:
    """对局日志(markdown)或固定样本(json，tests/fixtures/replay60.json)→ 回合清单 [{turn, deed, calls, context}]。"""
    text = path.read_text("utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        return [{**t, "context": "", "hero": data["hero"]} for t in data["turns"]]
    return parse(text)


def dump(turns: list[dict], path: Path):
    """只留举动与各角色的原始输出（约 0.3 MB），存成固定样本：日志太大不进仓库，重演只需要这些。"""
    name, origin = _hero(turns)
    data = {"hero": {"name": name, "origin": origin},
            "turns": [{"turn": t["turn"], "deed": t["deed"], "calls": t["calls"]} for t in turns]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), "utf-8")


def _hero(turns: list[dict]) -> tuple[str | None, str | None]:
    """主角名号与出身：固定样本里直接写着；日志则从首回合导演上下文的【主角】一行读出。"""
    if turns and turns[0].get("hero"):
        return turns[0]["hero"]["name"], turns[0]["hero"]["origin"]
    m = re.search(r"【主角】([^｜\n]+)｜([^｜\n]+)", turns[0]["context"]) if turns else None
    if not m:
        return None, None
    origin = next((k for k, v in ORIGINS.items() if v["origin"] == m.group(2).strip()), None)
    return m.group(1).strip(), origin


def replay(turns: list[dict], limit: int | None = None, watch=("段誉",)) -> tuple[Game, list[dict]]:
    """逐回合重演，返回 (终局的 Game, 每回合的记录)：记录里有回合前后的所在、气血、时刻、时限，本回合的日志、未成立之事、账文分歧、亲见与传闻、选项；
    作废的回合只有 {turn, deed, error}。报告与 --check 都读它。"""
    name, origin = _hero(turns)
    llm, records = ReplayLLM(turns), []
    game = Game(World.create(name, origin=origin), llm)
    sink = _Log()
    logging.getLogger("tianlong").addHandler(sink)
    logging.getLogger("tianlong").setLevel(logging.INFO)
    try:
        for i, t in enumerate(turns[:limit] if limit else turns):
            llm.at(i)
            w, sink.lines = game.world, []
            rec = {"turn": t["turn"], "deed": t["deed"] or "开卷", "here0": w.here, "hp0": w.player["hp"], "tick0": w.clock.tick}
            try:
                turn = game.open() if i == 0 else game.act(t["deed"] or "")
            except LLMError as e:
                records.append({**rec, "error": str(e)})
                continue
            w = game.world
            records.append({**rec, "time": turn["time"], "here": w.here, "hp": w.player["hp"], "tick": w.clock.tick, "log": list(sink.lines),
                            "void": list(turn["void"]), "news": turn["news"], "options": turn["options"], "drift": list(w.player["drift"]),
                            "scene": (w.player["scene"] or {}).get("state"), "ask": (w.player["scene"] or {}).get("ask"),
                            "around": sorted(situation.around(w)), "cast": sorted(situation.cast(w)),
                            "watch": {p: (w.graph.get(p, "location"), w.graph.get(p, "status")) for p in watch},
                            "hurt": w.turn.get("hurt", 0), "study": {a: dict(r) for a, r in (w.player.get("study") or {}).items()},
                            "poisoned": {p: sorted(body.poisons(w, p)) for p in ["player", *w.graph.where(type="person")] if body.poisons(w, p)},
                            "clocks": [dict(c) for c in w.player["clocks"]], "conditions": list(w.player["conditions"])})
    finally:
        logging.getLogger("tianlong").removeHandler(sink)
    return game, records


def report(game: Game, records: list[dict]) -> str:
    """重演报告（markdown）：逐回合去处、场况、眼前与名册、所盯人物的真实下落、未成立之事、返工/体检/原著日志、亲见与传闻、选项，末附账本与原著结算。"""
    out = []
    for r in records:
        if r.get("error"):
            out.append(f"## 第 {r['turn']} 回 · {r['deed']}\n- 回合作废：{r['error']}\n")
            continue
        out.append(f"## 第 {r['turn']} 回 · {r['deed']}\n"
                   f"- {r['time']}｜{r['here0']} → {r['here']}｜场：{r['scene']}「{r['ask']}」\n"
                   f"- 眼前：{'、'.join(r['around']) or '无人'}｜名册：{'、'.join(r['cast']) or '—'}\n"
                   + "".join(f"- 盯着 {p}：{loc}（{st}）\n" for p, (loc, st) in r["watch"].items())
                   + "".join(f"- 未成立：{v}\n" for v in r["void"])
                   + "".join(f"- 日志：{line}\n" for line in r["log"] if line.startswith(("导演返工", "体检", "原著", "结算入账", "账文分歧", "补记", "立外号", "幕间省略")))
                   + "".join(f"- {'亲见' if n['witnessed'] else '传闻'}：{n['text']}\n" for n in r["news"])
                   + f"- 选项：{' / '.join(r['options'])}\n")
    w = game.world
    out.append("## 账本\n" + "".join(f"- [{e['origin']}·{e['day']}·{e['where']}] {e['summary']}\n" for e in w.truth.events))
    out.append(f"## 原著\n- 已结算 {len(w.done)} 桩：{'、'.join(w.done)}\n")
    return "\n".join(out)


def rerun(turns: list[dict], limit: int | None = None, watch=("段誉",)) -> str:
    return report(*replay(turns, limit, watch))


# ============================================================
#  --check：逐回合不变量（v13，60 回重演的验收）
# ============================================================
def check(game: Game, records: list[dict]) -> list[str]:
    """逐回合断言账上的不变量，返回违例清单（空即全过）：
    气血只因成立的伤、毒发而降；账文分歧里没有技术性条目；到期的时限回合开头就兑现或作罢（没有拖过一回合的）；
    研习账各门武学的真实光阴之和不超过世界流过的光阴；中了毒的人境况里留着中毒的标记；没有因「拍文里无据」被丢掉的气血增减。"""
    bad, start = [], records[0]["tick0"] if records else 0
    for r in records[1:]:  # 开卷那一回没有玩家的举动，不查
        if r.get("error"):
            continue
        n = r["turn"]
        if r["hp"] < r["hp0"] and not r["hurt"] and "player" not in r["poisoned"]:
            bad.append(f"第{n}回 气血无故下降：{r['hp0']} → {r['hp']}")
        bad += [f"第{n}回 技术性条目进了账文分歧：{d}" for d in r["drift"] if TECHNICAL.search(d)]
        bad += [f"第{n}回 时限「{c['what']}」到期（{c['due']}）而回合开头没有了断" for c in r["clocks"] if c["due"] <= r["tick0"]]
        spent = sum(rec["minutes"] for rec in r["study"].values())
        if spent > r["tick"] - start:
            bad.append(f"第{n}回 研习账的光阴之和{spent}超过了世界流过的{r['tick'] - start}")
        bad += [f"第{n}回 {p}中着{'、'.join(names)}而境况里没有中毒的标记" for p, names in r["poisoned"].items()
                if p == "player" and "中毒" not in r["conditions"]]
        bad += [f"第{n}回 {line}" for line in r["log"] if "拍文里无据" in line and ("hp" in line or "气血" in line)]
    return bad


def summary(game: Game, records: list[dict]) -> str:
    """P0 之后的目标一览（review §七）：账文分歧的回合、无据丢弃、返工、作废拍、终局气血、通天草持有者、研习账。"""
    live = [r for r in records if not r.get("error")]
    w = game.world
    drift = [r["turn"] for r in live if r["drift"]]
    dropped = sum(1 for r in live for line in r["log"] if "拍文里无据" in line)
    repair = sum(1 for r in live for line in r["log"] if line.startswith("导演返工"))
    voided = sum(1 for r in live for v in r["void"] if "未曾发生" in v and "主角并未起意" not in v)
    return (f"账文分歧 {len(drift)} 回{drift}；无据丢弃 {dropped} 条；导演返工 {repair} 次；作废的拍 {voided} 拍；整回合作废 {len(records) - len(live)}；"
            f"终局气血 {w.player['hp']}；通天草在 {w.graph.get('通天草', 'holder') or w.graph.get('通天草', 'location')}；"
            f"研习账 {sorted(w.player.get('study') or {})}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="用对局日志里的真实模型输出驱动当前引擎重演")
    ap.add_argument("log", type=Path, help="对局日志(game.md)或固定样本(tests/fixtures/replay60.json)")
    ap.add_argument("--turns", type=int)
    ap.add_argument("--watch", default="段誉")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true", help="逐回合断言账上的不变量，有违例即退出码 1")
    ap.add_argument("--dump", type=Path, help="把日志里的举动与各角色原始输出存成固定样本(json)")
    args = ap.parse_args(argv)
    turns = load(args.log)
    if args.dump:
        dump(turns, args.dump)
        sys.stdout.write(f"已存 {len(turns)} 回 → {args.dump}\n")
        return
    game, records = replay(turns, args.turns, tuple(x for x in args.watch.split(",") if x))
    text = report(game, records)
    if args.out:
        args.out.write_text(text, "utf-8")
    elif not args.check:
        sys.stdout.write(text)
    if args.check:
        bad = check(game, records)
        sys.stdout.write(summary(game, records) + "\n" + ("\n".join(bad) + "\n" if bad else "不变量全过\n"))
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
