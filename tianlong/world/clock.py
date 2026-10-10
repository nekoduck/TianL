"""
[INPUT]: 无外部依赖
[OUTPUT]: 对外提供 Clock（分钟计数 / 跨日跨月检测 / 年号·时辰·刻历法渲染：parts 分段、label 成句 / minutes 时长措辞换算）、
          day_of()（"元祐六年二月"→日序）、PACES（时长措辞表）、PER_DAY、PER_SHICHEN
[POS]: world 层的全局时钟，唯一的时间真相；被 World.advance 驱动，被 lod 用来判定刷新节拍，被 genesis 用来排定原著日程
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import re

# ============================================================
#  历法常量：以分钟为最小刻度——一刻十五分，一时辰八刻，一日十二时辰，一月三十日，一年十二月（简化农历）
#  刻度足够细，说一句话与赶一程路才能各自流过合乎情理的光阴
# ============================================================
PER_KE = 15
PER_SHICHEN = 120
PER_DAY = 12 * PER_SHICHEN
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
SHICHEN = "子丑寅卯辰巳午未申酉戌亥"
MONTHS = ("正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "腊")
ERAS = (("元祐", 1, 9), ("绍圣", 1, 4), ("元符", 1, 3))  # (年号, 起年, 末年)；tick=0 即元祐元年正月初一子时
DIGITS = "〇一二三四五六七八九"
MORNING = 4 * PER_SHICHEN  # 辰时：「一夜」歇到次日清晨
# 时长措辞：导演只选词，分钟由系统换算——时间是世界的，不是 LLM 的。「一夜」依当下时刻算到次日辰时
PACES = {"瞬息": 1, "片刻": 15, "一顿饭": 45, "半日": 3 * PER_SHICHEN, "一夜": None, "一日": PER_DAY}


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


def _parse_cn(text: str) -> int:
    """一~九十九的中文数字；元/正 视作一，腊 视作十二。"""
    if text in ("元", "正"):
        return 1
    if text == "腊":
        return 12
    if "十" in text:
        tens, _, ones = text.partition("十")
        return (DIGITS.index(tens) if tens else 1) * 10 + (DIGITS.index(ones) if ones else 0)
    return DIGITS.index(text)


def day_of(when: str) -> int:
    """把「元祐六年二月」「元符二年三月（占位）」之类的年月换算为自 tick 原点起的日序（取当月初一）。"""
    m = re.match(r"(元祐|绍圣|元符)(.+?)年(.+?)月", when)
    if not m:
        raise ValueError(f"无法解析的日期：{when}")
    era, year, month = m.group(1), _parse_cn(m.group(2)), _parse_cn(m.group(3))
    index = 0
    for name, first, last in ERAS:
        if name == era:
            index += year - first
            break
        index += last - first + 1
    return (index * MONTHS_PER_YEAR + month - 1) * DAYS_PER_MONTH


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

    def advance(self, minutes: int) -> tuple[int, int]:
        """推进若干分钟，返回 (跨越的日数, 跨越的月数) —— LOD 节拍据此触发。"""
        day, month = self.day, self.month
        self.tick += max(0, minutes)
        return self.day - day, self.month - month

    def minutes(self, pace: str) -> int:
        """时长措辞 → 分钟。「一夜」算到次日辰时；不识的措辞视作片刻。"""
        if pace == "一夜":
            morning = self.day * PER_DAY + MORNING
            return (morning if morning > self.tick else morning + PER_DAY) - self.tick
        return PACES.get(pace) or PACES["片刻"]

    def parts(self, day: int | None = None) -> dict:
        """历法分段：{year: 元祐六年, date: 二月初一, hour: 辰时三刻}；给定 day 时只有年与日。"""
        d = self.day if day is None else day
        m = d // DAYS_PER_MONTH
        out = {"year": _year_name(m // MONTHS_PER_YEAR),
               "date": f"{MONTHS[m % MONTHS_PER_YEAR]}月{_day_name(d % DAYS_PER_MONTH + 1)}"}
        if day is None:
            minute = self.tick % PER_DAY
            ke = minute % PER_SHICHEN // PER_KE
            out["hour"] = f"{SHICHEN[minute // PER_SHICHEN]}时" + (f"{DIGITS[ke]}刻" if ke else "")
        return out

    def label(self, day: int | None = None) -> str:
        p = self.parts(day)
        return p["year"] + p["date"] + (f" {p['hour']}" if "hour" in p else "")
