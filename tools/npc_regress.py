#!/usr/bin/env python3
"""NPC 引擎回归：复现 reference/npc_spike.py main(--all) 的输出格式，并与 reference/logs/npc_run_log.txt 逐行比对。

    python3 tools/npc_regress.py          基准部分（60 僧 30 日 + 确定性 + 传闻 + 轨迹 + 因果链）
    python3 tools/npc_regress.py --all    再加 实验 N1、90 日、五个种子
    python3 tools/npc_regress.py --diff   输出之后，与日志逐行比对（耗时行只记录不比对），不一致则退出码 1

标准输出与原型 main() 的输出同格式（可直接 `python3 tools/npc_regress.py --all | diff - reference/logs/npc_run_log.txt`，
只会有两行耗时不同）；页脚与比对结论写到标准错误。
退出码：0 全部一致（或没要求比对）；1 有不一致。每次决策耗时只用于报告，不是通过线。
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianl.npc.report import proto_report, strip_timing   # noqa: E402

LOG = ROOT / 'reference' / 'logs' / 'npc_run_log.txt'


def main(argv):
    include_all = '--all' in argv
    t0 = time.perf_counter()
    lines, info = proto_report(include_all=include_all)
    for ln in lines:
        print(ln)
    wall = time.perf_counter() - t0
    print('（回归总耗时 %.2f 秒；基准每次决策 %.1f 微秒）' % (wall, info['m']['us']), file=sys.stderr)
    if '--diff' not in argv:
        return 0
    ref = LOG.read_text(encoding='utf-8').splitlines()
    if not include_all:                     # 基准部分 = 日志里 N1 标题之前的行
        k = next(i for i, x in enumerate(ref) if x.startswith('== 实验 N1'))
        ref = ref[:k]
    bad = 0
    for i, (a, b) in enumerate(zip(lines, ref), 1):
        if strip_timing(a) != strip_timing(b):
            bad += 1
            print('第 %d 行不一致：\n  本实现：%s\n  日志  ：%s' % (i, a, b), file=sys.stderr)
    if len(lines) != len(ref):
        bad += 1
        print('行数不同：本实现 %d 行，日志 %d 行' % (len(lines), len(ref)), file=sys.stderr)
    print('与日志逐行比对：%s（共 %d 行，不一致 %d 处）' % ('一致' if bad == 0 else '不一致', len(ref), bad),
          file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
