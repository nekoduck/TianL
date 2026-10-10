"""
[INPUT]: 无外部依赖
[OUTPUT]: 对外提供 Clock（时辰计数 / 跨日跨月检测 / 年号历法渲染）
[POS]: world 层的全局时钟，唯一的时间真相；被 World.advance 驱动，被 lod 用来判定刷新节拍
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

# ============================================================
#  历法常量：一日十二时辰，一月三十日，一年十二月（简化农历）
# ============================================================
PER_DAY = 12
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
SHICHEN = "子丑寅卯辰巳午未申酉戌亥"
MONTHS = ("正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "腊")
ERAS = (("元祐", 7, 9), ("绍圣", 1, 4), ("元符", 1, 3))  # (年号, 起年, 末年)；tick=0 即元祐七年正月初一子时
DIGITS = "〇一二三四五六七八九"


def _cn(n: int) -> str:
    if n < 10:
        return DIGITS[n]
    tens, ones = divmod(n, 10)
    return (DIGITS[tens] if tens > 1 else "") + "十" + (DIGITS[ones] if ones else "")


def _day_name(d: int) -> str:
    if d <= 10:
        return "初" + _cn(d)
    if d < 20 or d == 30:
        return _cn(d)
    return "二十" if d == 20 else "廿" + DIGITS[d - 20]


def _year_name(index: int) -> str:
    for era, first, last in ERAS:
        span = last - first + 1
        if index < span:
            n = first + index
            return era + ("元" if n == 1 else _cn(n)) + "年"
        index -= span
    return f"元符后{_cn(index + 1)}年"


class Clock:
    def __init__(self, tick: int = 0):
        self.tick = tick

    @property
    def day(self) -> int:
        return self.tick // PER_DAY

    @property
    def month(self) -> int:
        return self.day // DAYS_PER_MONTH

    def advance(self, shichen: int) -> tuple[int, int]:
        """推进时间，返回 (跨越的日数, 跨越的月数) —— LOD 节拍据此触发。"""
        day, month = self.day, self.month
        self.tick += max(0, shichen)
        return self.day - day, self.month - month

    def label(self, day: int | None = None) -> str:
        d = self.day if day is None else day
        m = d // DAYS_PER_MONTH
        text = f"{_year_name(m // MONTHS_PER_YEAR)}{MONTHS[m % MONTHS_PER_YEAR]}月{_day_name(d % DAYS_PER_MONTH + 1)}"
        return text if day is not None else f"{text} {SHICHEN[self.tick % PER_DAY]}时"
