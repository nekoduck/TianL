"""B1 测试共用：全进程只算一遍的基准世界。

基准 `World().run(360*4)` 约 2.7 秒，B1 的几个测试模块都要用它；各算各的会把默认整套测试（60 秒线）吃掉一大块。
这里按进程缓存一份，**只读**：谁要改库或往里推日子，请自己造一个 World。（本文件里没有测试，只放帮手。）
"""
from tianl.kernel import World

REF_HASH = '49f6ddde04dfa7f5'          # reference/shaolin_spike.py 基准（预热 1 年 + 3 年）的 state_hash
BASELINE_DAYS = 360 * 4

_cache = {}


def baseline_world():
    """预热 1 年 + 3 年的基准世界（只读，进程内共享）。"""
    if 'w' not in _cache:
        _cache['w'] = World().run(BASELINE_DAYS)
    return _cache['w']
