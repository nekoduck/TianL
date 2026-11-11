"""计数器式随机数（计划 2.2 第 1 条）。

每次抽签由 (种子, 用途, 日期, 时辰, 人 …) 这一串键完全决定，与调用次序无关；
所以“多生成一条叙述”“观察者换个位置”都不会改写任何人的未来。

两个哈希实现，口径固定，不得改动（否则回归哈希全部失效）：
  rnd     sha256 取前 8 字节，v0.2 内核与集成后的整个世界使用。
  rnd_b2  blake2b(8)，仅为复现 npc_spike.py 原型（哈希 e8f8209eeb8ca94a）而保留。
"""
import hashlib
import math


def rnd(*keys):
    """[0,1) 的确定性随机数。v0.2 口径：sha256，键用 '|' 连接。"""
    h = hashlib.sha256('|'.join(map(str, keys)).encode()).digest()
    return int.from_bytes(h[:8], 'big') / 2 ** 64


def rnd_b2(*keys):
    """npc_spike.py 原型口径（blake2b-8）。"""
    h = hashlib.blake2b('|'.join(map(str, keys)).encode(), digest_size=8).digest()
    return int.from_bytes(h, 'big') / 2 ** 64


def gauss(mean, sd, *keys, rng=rnd):
    """Box-Muller，两个独立键 'a'/'b'；与原型 gauss 口径一致（rng 可换）。"""
    u1 = max(rng(*keys, 'a'), 1e-12)
    u2 = rng(*keys, 'b')
    return mean + sd * math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def clamp(x, lo=0.0, hi=100.0):
    return lo if x < lo else hi if x > hi else x
