"""
[INPUT]: 依赖 tianlong/engine 的 Game，world/world 的 World，world/blackboard 的 ORIGINS，narrative/llm 的 from_env，tianlong/server 的 make_server / AUTOSAVE；读取 .env 与命令行参数
[OUTPUT]: 对外提供 main()（终端交互循环：选名号与出身、开卷、自由输入；--web 时改为启动 Web 服务，续读 --load 存档或上次的自动存档；--trace 记录大模型调用）
[POS]: 表现层——只负责输入输出与斜杠指令，不含任何游戏逻辑；展示正文、江湖传闻、状态栏、导演给出的 3 个建议与自由输入；
       "打数字选第几项"是终端独有的快捷写法(只认半角数字)，内核只收原话；读档失败只提示、不丢下眼前这一局
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
from .world.blackboard import ORIGINS
from .world.world import World

QUICKSAVE = Path("saves/quick.json")
HELP = "指令：数字选择选项｜直接输入你想做的事｜/save [路径]｜/load [路径]｜/me 玩家黑板｜/debug 双账本对照｜/quit"
TTY = sys.stdout.isatty()
UNREADABLE = (OSError, ValueError, KeyError, TypeError)  # 找不到、不是 JSON、缺字段、形状不对：都是"读不了这份档"


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if TTY else text


def _load_dotenv(path=Path(".env")):
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def _pick(game: Game, line: str) -> str:
    """终端快捷写法：半角数字即眼前第几个选项；其余一律当原话。"""
    if line.isascii() and line.isdigit() and 1 <= int(line) <= len(game.options):
        return game.options[int(line) - 1]
    return line


def _unreadable(path, e: Exception) -> str:
    return f"  存档 {path} 无法读取（{type(e).__name__}：{str(e)[:80]}）"


def show(turn: dict):
    bar = "━" * 36
    print(f"\n{_c(bar, '2')}\n  {_c(turn['time'] + ' · ' + turn['place'], '1;33')}\n{_c(bar, '2')}")
    print(turn["text"])
    for n in turn["news"]:
        print(_c(f"  ☰ {'亲眼所见' if n['witnessed'] else '江湖传闻'}｜{n['date']}·{n['place']}：{n['text']}", "36"))
    print(_c("\n  " + "　".join(tag["text"] for tag in turn["status"]), "2"))
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
        game.flush()  # 后台折叠中的梗概先汇合，存下的才是完整的记忆
        game.world.save(path)
        print(f"  已存档至 {path}")
    elif cmd == "/load":
        try:
            game = Game(World.load(path), game.llm)
        except UNREADABLE as e:  # 读不了就留在眼前这一局，不崩、不丢
            print(_c(_unreadable(path, e), "33"))
            return game
        show(game.open())
    elif cmd == "/me":
        print(json.dumps(game.world.player.snapshot(), ensure_ascii=False, indent=1))
    elif cmd == "/debug":
        print(json.dumps(game.debug(), ensure_ascii=False, indent=1))
    else:
        print(HELP)
    return game


def _choose_origin() -> str:
    keys = list(ORIGINS)
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {k}：{ORIGINS[k]['origin']}——所求：{ORIGINS[k]['goal']}")
    pick = input("  出身（回车默认 1）：").strip()
    return keys[int(pick) - 1] if pick.isdigit() and 1 <= int(pick) <= len(keys) else keys[0]


def _serve_web(args, llm):
    """Web 模式：续读 --load 指定的存档，否则续读上次的自动存档；之后每回合自动存档。"""
    from .server import AUTOSAVE, make_server
    source = args.load or (AUTOSAVE if AUTOSAVE.exists() else None)
    if source:
        print(f"  正在续卷：{source}")
    try:
        httpd = make_server(llm, args.host, args.port, autosave=AUTOSAVE, resume=source)
    except UNREADABLE as e:  # 坏档不覆盖：请玩家自行处置
        print(_c(_unreadable(source, e) + "。请移走或删除它后再开卷。", "33"))
        return
    session = httpd.RequestHandlerClass.hub.session
    if session:
        print(f"  {session.hero} 的这一卷已写到第 {len(session.transcript)} 回")
    print(f"  天龍八部已在 http://{args.host}:{args.port} 开卷，每回合自动存入 {AUTOSAVE}（Ctrl+C 合卷）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  江湖路远，后会有期。")
    finally:
        httpd.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="天龙八部 · 文字沙盒")
    ap.add_argument("--offline", action="store_true", help="不调用大模型，全部走确定性兜底")
    ap.add_argument("--load", type=Path, help="读取存档")
    ap.add_argument("--name", help="主角名号")
    ap.add_argument("--origin", choices=list(ORIGINS), help="主角出身（不给则在终端选择）")
    ap.add_argument("--trace", type=Path, help="把每次大模型调用记成 JSONL，供提示词迭代")
    ap.add_argument("--verbose", action="store_true", help="输出 LLM 失败、剧情后果未成立等诊断日志")
    ap.add_argument("--web", action="store_true", help="以 Web 界面开卷（浏览器访问），而非终端")
    ap.add_argument("--host", default="127.0.0.1", help="Web 服务监听地址")
    ap.add_argument("--port", type=int, default=8000, help="Web 服务端口")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR, format="  [%(levelname)s] %(message)s")
    _load_dotenv()

    llm = None if args.offline else from_env(trace=args.trace)
    if llm is None and not args.offline:
        print(_c("  未检测到 GEMINI_API_KEY，以离线模式运行。", "33"))
    if args.web:
        return _serve_web(args, llm)
    if args.load:
        try:
            world = World.load(args.load)
        except UNREADABLE as e:
            print(_c(_unreadable(args.load, e), "33"))
            return
    else:
        name, origin = args.name or input("  侠客名号（回车默认「无名」）：").strip(), args.origin or _choose_origin()
        while True:
            try:
                world = World.create(name or None, origin=origin)
                break
            except ValueError as e:  # 与书中人物、地名重名
                print(_c(f"  {e}", "33"))
                name = input("  侠客名号（回车默认「无名」）：").strip()

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
        show(game.act(_pick(game, line)))
    print("\n  江湖路远，后会有期。")
