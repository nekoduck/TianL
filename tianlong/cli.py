"""
[INPUT]: 依赖 tianlong/engine 的 Game，world/world 的 World，narrative/llm 的 from_env；读取 .env 与命令行参数
[OUTPUT]: 对外提供 main()（终端交互循环）
[POS]: 表现层——只负责输入输出与斜杠指令，不含任何游戏逻辑；展示正文、江湖传闻、状态栏、导演给出的 3 个建议与自由输入
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .engine import Game
from .narrative.llm import from_env
from .world.world import World

QUICKSAVE = Path("saves/quick.json")
HELP = "指令：数字选择选项｜直接输入你想做的事｜/save [路径]｜/load [路径]｜/me 玩家黑板｜/debug 双账本对照｜/quit"
TTY = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if TTY else text


def _load_dotenv(path=Path(".env")):
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def show(turn: dict):
    bar = "━" * 36
    print(f"\n{_c(bar, '2')}\n  {_c(turn['time'] + ' · ' + turn['place'], '1;33')}\n{_c(bar, '2')}")
    print(turn["text"])
    for line in turn["news"]:
        print(_c(f"  ☰ 江湖传闻｜{line}", "36"))
    print(_c(f"\n  {turn['status']}", "2"))
    for i, label in enumerate(turn["options"], 1):
        print(f"  {_c(f'[{i}]', '1;32')} {label}")
    print(_c("  （或直接输入你想做的事；/help 查看指令）", "2"))


def _command(game: Game, line: str) -> Game | None:
    """处理斜杠指令；返回 None 表示退出，否则返回（可能被读档替换的）Game。"""
    cmd, _, arg = line.partition(" ")
    path = Path(arg.strip()) if arg.strip() else QUICKSAVE
    if cmd == "/quit":
        return None
    if cmd == "/save":
        game.world.save(path)
        print(f"  已存档至 {path}")
    elif cmd == "/load":
        game = Game(World.load(path), game.llm)
        show(game.open())
    elif cmd == "/me":
        print(json.dumps(game.world.player.snapshot(), ensure_ascii=False, indent=1))
    elif cmd == "/debug":
        print(json.dumps(game.debug(), ensure_ascii=False, indent=1))
    else:
        print(HELP)
    return game


def main(argv=None):
    ap = argparse.ArgumentParser(description="天龙八部 · 文字沙盒")
    ap.add_argument("--offline", action="store_true", help="不调用大模型，全部走确定性兜底")
    ap.add_argument("--load", type=Path, help="读取存档")
    ap.add_argument("--name", help="主角名号")
    ap.add_argument("--verbose", action="store_true", help="输出 LLM 失败、创造未成立等诊断日志")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR, format="  [%(levelname)s] %(message)s")
    _load_dotenv()

    llm = None if args.offline else from_env()
    if llm is None and not args.offline:
        print(_c("  未检测到 GEMINI_API_KEY，以离线模式运行。", "33"))
    if args.load:
        world = World.load(args.load)
    else:
        name = args.name or input("  侠客名号（回车默认「无名」）：").strip()
        world = World.from_seed(name or None)

    game = Game(world, llm)
    show(game.open())
    while True:
        try:
            line = input(_c("\n> ", "1")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.startswith("/"):
            game = _command(game, line)
            if game is None:
                break
            continue
        show(game.act(line))
    print("\n  江湖路远，后会有期。")
