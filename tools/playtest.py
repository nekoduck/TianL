"""
[INPUT]: 依赖 tianlong.engine 的 Game、tianlong.world.world 的 World、world/situation 的 around / cast / elsewhere、narrative/llm 的 from_env / LLMError（读 GEMINI_API_KEY，可选 .env）
[OUTPUT]: 命令行工具：python -m tools.playtest [--route 琅嬛] [--deeds 文件] [--turns N] [--offline] [--name 名号] [--origin 出身]
          [--watch 段誉,钟灵] [--out 对局.md] [--trace 调用.jsonl]——按一条固定路线(或自备的一行一举)真打一局，写出一份对局记录：
          逐回合的举动、正文、选项、亲见与传闻、身况，以及后台视角(眼前之人、名册、所盯人物的真实下落、场况、原著结算)；
          举动写成「1」「2」「3」即选上一回合的第几项
[POS]: 本地试玩——发网络请求的只有这一个工具(经 narrative/llm)；同一条路线前后各打一局，对局记录可直接对比：
       段誉什么时候、在哪里与主角相遇，原著主线断没断，传闻与账本对不对得上；v6 逐回合摊开结算(账房记进账本的、与账本对不上的)与所盯人物的识名(v7 另摊开补记与新立的外号；v11 另摊开场外编剧的作罢、改写、续写与审稿，末附场外剧情线)，
       正文与账本对不对得上一眼可见。说书人失声的回合记为作罢，接着打下一回合
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from tianlong.engine import Game
from tianlong.narrative.llm import LLMError, from_env
from tianlong.world import perspective, situation
from tianlong.world.world import World

# 剑湖宫 → 后山 → 谷底 → 琅嬛福地 → 出洞：原著里段誉坠崖、入洞、得北冥的那条路，主角先走一遍
ROUTES = {
    "琅嬛": ["向那位青衫少年拱手搭话", "1", "借故离开练武厅，往后山去", "沿着溪流往后山深处走", "攀着藤蔓下到崖底",
             "在谷底湖畔四处察看", "照着石壁上的剑影找那块巨岩，推转它", "钻进石洞看看", "细看满壁铜镜，摸索镜后有无机关",
             "细看玉像与蒲团", "撕开蒲团，看里面藏着什么", "静心研习帛卷上的功夫", "歇息一夜", "继续研习帛卷", "四下找找出路",
             "循石级隧道往上走", "出洞", "1", "1", "1"],
}


def _load_dotenv(path=Path(".env")):
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() and value.strip() and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip())


def _deed(raw: str, options: list[str]) -> str:
    """「1」「2」「3」即选上一回合的第几项；其余照原话。"""
    if raw.strip() in ("1", "2", "3") and len(options) >= int(raw):
        return options[int(raw) - 1]
    return raw.strip()


class _Ledger(logging.Handler):
    """收下引擎这一回合的结算日志(v6)：账房记进账本的、与账本对不上的；v7 另收账本替正文补记的、为分清撞名之人新立的外号——对局记录里逐回合摊开，账与文对不对得上一眼可见。"""

    def __init__(self):
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record):
        msg = record.getMessage()
        if msg.startswith(("结算入账", "账文分歧", "补记", "立外号", "场外", "原著延后", "原著线已变")):  # v11 场外编剧：作罢、改写、续写、规则审与审稿
            self.lines.append(msg)


def _backstage(game, watch, ledger=()) -> str:
    w = game.world
    sc = w.player["scene"] or {}
    lines = [f"- 眼前：{'、'.join(sorted(situation.around(w))) or '无人'}｜名册：{'、'.join(sorted(situation.cast(w))) or '—'}"
             f"｜同在这一片：{'、'.join(situation.elsewhere(w)) or '—'}",
             f"- 场：第{sc.get('id')}场·{sc.get('state')}「{sc.get('ask')}」｜原著已结算 {len(w.done)} 桩"]
    lines += [f"- 盯着 {p}：{w.graph.get(p, 'location')}（{w.graph.get(p, 'status')}）"
              f"｜主角{'叫得出' if perspective.knows(w, 'player', p) else '叫不出'}其名｜其人{'知道' if perspective.knows(w, p, 'player') else '不知'}主角名号"
              for p in watch]
    lines += [f"- {line}" for line in ledger]
    return "\n".join(lines)


def play(deeds: list[str], llm, name=None, origin=None, watch=("段誉",), limit=None) -> str:
    game, out = Game(World.create(name, origin=origin), llm), []
    options, turn, ledger = [], None, _Ledger()
    log = logging.getLogger("tianlong")
    log.addHandler(ledger)
    log.setLevel(logging.INFO)
    for i, raw in enumerate(([""] + deeds)[:limit] if limit else [""] + deeds):  # limit 与 rerun 同一口径：连开卷共几回合
        deed = _deed(raw, options)
        ledger.lines.clear()
        try:
            turn = game.open() if i == 0 else game.act(deed)
        except LLMError as e:
            out.append(f"## 第 {i + 1} 回 · {deed}\n说书人失声，这一回合作罢：{e}\n")
            continue
        options = turn["options"]
        out.append(f"## 第 {i + 1} 回 · {turn['time']} · {turn['place']}\n**举动**：{deed or '开卷'}\n\n{turn['text']}\n\n"
                   f"- **选项**：{' / '.join(f'{k + 1}. {o}' for k, o in enumerate(options))}\n"
                   f"- **身况**：{'、'.join(t['text'] for t in turn['status'])}\n"
                   + "".join(f"- **{'亲见' if n['witnessed'] else '传闻'}**（{n['date']}·{n['place']}）：{n['text']}\n" for n in turn["news"])
                   + "".join(f"- 未成立：{v}\n" for v in turn["void"])
                   + "\n<details><summary>后台</summary>\n\n" + _backstage(game, watch, ledger.lines) + "\n</details>\n")
    game.flush()
    log.removeHandler(ledger)
    w = game.world
    out.append("## 附录 · 客观账本\n" + "".join(f"- [{e['origin']}·{w.clock.label(e['day'])}·{e['where']}{'·亲历' if e.get('witnessed') else ''}] {e['summary']}\n"
                                          for e in w.truth.events))
    out.append(f"## 附录 · 原著\n- 已结算：{'、'.join(w.done)}\n- 前情梗概：{w.player['synopsis']}\n")
    out.append("## 附录 · 场外剧情线\n" + ("".join(f"- 「{k}」{v['goal']}（{'、'.join(v['owners'])}，自{v['from']}）：{'；'.join(v['events'])}\n"
                                              for k, v in w.lines.items()) or "- 无\n"))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="按固定路线真打一局，写出对局记录")
    ap.add_argument("--route", default="琅嬛", choices=list(ROUTES))
    ap.add_argument("--deeds", type=Path, help="自备举动：一行一举，「1」「2」「3」即选上一回合的第几项")
    ap.add_argument("--turns", type=int, help="连开卷共打几回合")
    ap.add_argument("--offline", action="store_true", help="不调用模型(只验证流程)")
    ap.add_argument("--name", default="郑大风")
    ap.add_argument("--origin", default="随从")
    ap.add_argument("--watch", default="段誉,钟灵,木婉清")
    ap.add_argument("--out", type=Path, default=Path("saves/playtest.md"))
    ap.add_argument("--trace", type=Path, help="把每次大模型调用记成 JSONL")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.ERROR)
    _load_dotenv()
    llm = None if args.offline else from_env(trace=args.trace)
    if llm is None and not args.offline:
        sys.exit("未检测到 GEMINI_API_KEY：请在环境变量或 .env 里设置，或加 --offline")
    deeds = [x for x in args.deeds.read_text("utf-8").splitlines() if x.strip()] if args.deeds else ROUTES[args.route]
    report = play(deeds, llm, args.name, args.origin, tuple(x for x in args.watch.split(",") if x), args.turns)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, "utf-8")
    print(f"对局记录已写入 {args.out}" + (f"，调用记录在 {args.trace}" if args.trace else ""))


if __name__ == "__main__":
    main()
