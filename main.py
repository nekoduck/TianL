"""
[INPUT]: 依赖 tianlong/cli 的 main
[OUTPUT]: 命令行入口：python main.py [--offline] [--load 存档] [--name 名号]
[POS]: 项目根入口，仅做转发
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
from tianlong.cli import main

if __name__ == "__main__":
    main()
