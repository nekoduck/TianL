"""历法与时间（v0.2 口径）。

一年 360 日、每月 30 日；一日十二时辰（子丑寅卯辰巳午未申酉戌亥）；
时辰内再分 8 刻——刻只用于观察者所在场所的细节叙述，从不参与决定。
绝对时刻 t = day * 12 + slot。第 0 年为“预热年”。

本模块不带任何一座寺院的历法：节日、结夏、收麦收粟日都在 defs/calendar/<scope>.toml 里，经 Calendar.from_def 构造
（B1 内核的做法见 tianl.kernel.spec.Spec.cal）。Calendar 的这四个字段没有缺省值，漏写就报错，不会悄悄用上别处的历法。
模块级 cal() / cal_str()（NPC 引擎的原型场景还在用）读“默认历法”：第一次用到时从 defs 里读 DEFAULT_CALENDAR 指的那份，
也可以用 set_default_calendar 换掉。tests/test_b1_defs.py 把这份历法与 reference/shaolin_spike.py 的 cal() 逐日核对。
"""
SLOTS = '子丑寅卯辰巳午未申酉戌亥'
SLOTS_PER_DAY = 12
KE_PER_SLOT = 8
YEAR = 360
TERMS = ('立春 雨水 惊蛰 春分 清明 谷雨 立夏 小满 芒种 夏至 小暑 大暑 '
         '立秋 处暑 白露 秋分 寒露 霜降 立冬 小雪 大雪 冬至 小寒 大寒').split()
MONTHS = '正二三四五六七八九十冬腊'
NUM = '一二三四五六七八九十'

DEFAULT_CALENDAR = 'calendar:shaolin:main'     # 默认历法的定义编号（文件 defs/calendar/<scope>.toml，scope 取编号的中段）
REQUIRED_FIELDS = ('festivals', 'retreat', 'wheat_doy', 'millet_doy')


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
    def __init__(self, festivals, retreat, wheat_doy, millet_doy, year=YEAR):
        """festivals：{(月, 日): 节名}；retreat：((月, 日), (月, 日))，含两端；wheat_doy / millet_doy：收麦、收粟的年内日序（0 起）。"""
        self.festivals = dict(festivals)
        self.retreat = tuple(retreat)
        self.wheat_doy, self.millet_doy, self.year = wheat_doy, millet_doy, year

    @classmethod
    def from_def(cls, d):
        """从 defs 里的 calendar 定义构造。festivals 形如 {"4-8": "佛诞"}；festivals / retreat / wheat_doy / millet_doy 必填，缺了报 ValueError。"""
        miss = [k for k in REQUIRED_FIELDS if k not in d]
        if miss:
            raise ValueError(f"历法定义 {d.get('id', '?')} 缺少字段：" + '、'.join(miss))
        fest = {tuple(int(x) for x in k.split('-')): v for k, v in d['festivals'].items()}
        r = d['retreat']
        return cls(fest, (tuple(r[0]), tuple(r[1])), d['wheat_doy'], d['millet_doy'], d.get('year', YEAR))

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


_default = None


def default_calendar():
    """默认历法：第一次用到时从 defs 读 DEFAULT_CALENDAR 指的那份（只读那一个文件，不经过完整加载器）。"""
    global _default
    if _default is None:
        import tomllib
        from pathlib import Path
        scope = DEFAULT_CALENDAR.split(':')[1]
        f = Path(__file__).resolve().parents[2] / 'defs' / 'calendar' / f'{scope}.toml'
        with open(f, 'rb') as fh:
            _default = Calendar.from_def(tomllib.load(fh)[DEFAULT_CALENDAR])
    return _default


def set_default_calendar(c):
    global _default
    _default = c


def cal(day):
    return default_calendar().cal(day)


def cal_str(day):
    return default_calendar().cal_str(day)
