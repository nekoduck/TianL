"""历法与时间（v0.2 口径）。

一年 360 日、每月 30 日；一日十二时辰（子丑寅卯辰巳午未申酉戌亥）；
时辰内再分 8 刻——刻只用于观察者所在场所的细节叙述，从不参与决定。
绝对时刻 t = day * 12 + slot。第 0 年为“预热年”。

本模块的默认历法（DEFAULT_FESTIVALS 与 Calendar() 的缺省参数）是 v0.2 原型的历法，保留给两处用途：
M0 的核心测试，以及 NPC 引擎的模块级 cal()（引擎尚未改成从 defs 取历法）。
B1 内核不读它：内核的历法由 defs/calendar/<scope>.toml 经 Calendar.from_def 构造（tianl.kernel.spec.Spec.cal），
节日、结夏、收麦收粟日都在 defs 里；tests/test_b1_defs.py 逐日核对两者相同。set_default_calendar 目前没有调用者。
"""
SLOTS = '子丑寅卯辰巳午未申酉戌亥'
SLOTS_PER_DAY = 12
KE_PER_SLOT = 8
YEAR = 360
TERMS = ('立春 雨水 惊蛰 春分 清明 谷雨 立夏 小满 芒种 夏至 小暑 大暑 '
         '立秋 处暑 白露 秋分 寒露 霜降 立冬 小雪 大雪 冬至 小寒 大寒').split()
MONTHS = '正二三四五六七八九十冬腊'
NUM = '一二三四五六七八九十'

DEFAULT_FESTIVALS = {(1, 1): '元日', (1, 15): '上元', (2, 15): '涅槃日', (4, 8): '佛诞', (4, 15): '结夏',
                     (7, 15): '盂兰盆', (12, 8): '腊八'}


def t_of(day, slot):
    return day * SLOTS_PER_DAY + slot


def day_slot(t):
    return divmod(t, SLOTS_PER_DAY)


def dom_name(d):
    if d <= 10: return '初' + NUM[d - 1]
    if d < 20: return '十' + NUM[d - 11]
    if d == 20: return '二十'
    if d < 30: return '廿' + NUM[d - 21]
    return '三十'


class Calendar:
    def __init__(self, festivals=None, retreat=((4, 15), (7, 15)), wheat_doy=125, millet_doy=245, year=YEAR):
        self.festivals = dict(DEFAULT_FESTIVALS if festivals is None else festivals)
        self.retreat = tuple(retreat)
        self.wheat_doy, self.millet_doy, self.year = wheat_doy, millet_doy, year

    @classmethod
    def from_def(cls, d):
        """从 defs 里的 calendar 定义构造。festivals 形如 {"4-8": "佛诞"}。"""
        fest = {tuple(int(x) for x in k.split('-')): v for k, v in d.get('festivals', {}).items()}
        r = d.get('retreat', [[4, 15], [7, 15]])
        return cls(fest, (tuple(r[0]), tuple(r[1])), d.get('wheat_doy', 125), d.get('millet_doy', 245), d.get('year', YEAR))

    def cal(self, day):
        y, doy = divmod(day, self.year)
        m, d = doy // 30 + 1, doy % 30 + 1
        return dict(day=day, year=y, doy=doy, month=m, dom=d, term=TERMS[doy // 15],
                    festival=self.festivals.get((m, d)), shuowang=d in (1, 15),
                    retreat=self.retreat[0] <= (m, d) <= self.retreat[1],
                    wheat=doy == self.wheat_doy, millet=doy == self.millet_doy)

    def cal_str(self, day):
        c = self.cal(day)
        y = '预热年' if c['year'] == 0 else f"第{c['year']}年"
        return f"{y}{MONTHS[c['month'] - 1]}月{dom_name(c['dom'])}"


_default = Calendar()


def set_default_calendar(c):
    global _default
    _default = c


def cal(day):
    return _default.cal(day)


def cal_str(day):
    return _default.cal_str(day)
