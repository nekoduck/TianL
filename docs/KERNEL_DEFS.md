# 内核定义文件（KERNEL_DEFS）

本文说明 B1 把 `reference/shaolin_spike.py`（v0.2 少林寺世界基座）移植成 `tianl/kernel` 之后，**哪些常量迁进了 `defs/*.toml`、每个字段是什么意思、怎么再写一座寺院**。
内核代码在 `tianl/kernel/`；装配规格的代码在 `tianl/kernel/spec.py`。移植的验收是：基准 `World().run(360*4)` 的 `state_hash()` 等于 `49f6ddde04dfa7f5`，
`reference/logs/shaolin_run_log.txt` 里的数字全部复现（`tools/shaolin_regress.py`、`tests/test_b1_*.py`）。

## 1 文件地图

| 文件 | 定义（kind:scope:名） | 内容 | 原型里的出处 |
| --- | --- | --- | --- |
| `defs/calendar/shaolin.toml` | `calendar:shaolin:main` | 年长、节日、结夏、收麦收粟日；农事与香期时刻表；年内结算日 | `TERMS` 以外的 `cal()` 内联常量、`pilgrim_factor`、`grain_price` 的季节、各阶段里的日序号 |
| `defs/space/shaolin.toml` | `place:shaolin:*`（30 个） | 场所：code、中文名、准入 | `PLACE_NAME`、`_populate` 里的 `locked_night` |
| `defs/economy/accounts.toml` | `account:shaolin:*`（10 个） | 账户：边界与否、开局注资、岁末盈余上限 | `_populate` 的账户列表与注资 |
| `defs/economy/goods.toml` | `commodity:shaolin:*`（9 个） | 品类：单价、日用量、补货线、优先级、铺户补货带 | `GOODS`、`SHOP_BANDS` |
| `defs/economy/params.toml` | `param:shaolin:main` | 参数 P | `P` |
| `defs/economy/rules.toml` | `param:shaolin:rules` | 规则参数 K：粮档位、各岗位的开单阈值、审批、收成、农户、损坏修缮……（共 110 项） | 散落在 `phase_*` 里的数字 |
| `defs/economy/opening.toml` | `param:shaolin:opening` | 开局存货序列 | `_populate` 的 `produce` 序列 |
| `defs/economy/households.toml` | `param:shaolin:households` | 农户类别（佃户、自耕户、樵菜户）与特殊户 | `_populate` 的农户循环 |
| `defs/org/shaolin.toml` | `org:shaolin:main` | 辈分、人数、年龄、院堂与配额、要角、继任、任命序、取名池与保留法名、僧寮规则 | `_people`、`CANON`、`RESERVED`、`POOL`、`HALLPLACE` |
| `defs/org/labels.toml` | `param:shaolin:labels` | 日报与报表里推不出来的专有词；粮账类别名 | `chronicle`、`summary` 里的字面量、`tg` 的键 |
| `defs/post/shaolin.toml` | `post:shaolin:*`（16 个）、`rule:shaolin:roster`、`rule:shaolin:timetable` | 岗位与站点、关键岗位、值守班表、作息模板 | `SITE`、`CRITICAL`、`make_roster`、`template` |
| `defs/item/shaolin.toml` | `item:shaolin:*`（2 个） | 独有物 | `_people` 末尾的两条 `item` |
| `defs/scenario/shaolin.toml` | `scenario:shaolin:regress` | 回归工具的探测点与种子 | `people_tests`、`long_and_seeds` |

内核只加载上面这些类别目录（`calendar space economy org post item scenario`，见 `spec.KERNEL_CATEGORIES`），别的模块的定义文件有问题时不拖累内核。

## 2 约定

**稳定编号与角色名。** 编号 `kind:scope:名`，`scope` 是这座寺院的名字（这里是 `shaolin`）。**内核按“角色名”取东西，角色名就是编号的最后一段**
（`place:shaolin:granary` 的角色是 `granary`，代码里写 `self.pl.granary`，得到运行时钥匙 `code`）。品类例外：它的角色由 `role` 字段给出
（`staple` 主粮、`fuel` 柴、`fresh` 鲜菜、`textile` 布、`lumber` 木料），因为品类的编号用的是它们的日常名。

**运行时钥匙是 `code`。** 库表、事件日志里的场所、账户、品类、独有物一律存 `code`；编号只在定义之间互相引用（加载器检查引用完整性）。

**`order` 字段决定插入次序。** 原型的状态哈希对每张表按 rowid 遍历，所以 `place`、`account`、`stock`、人、岗位、任命……的**插入次序必须与原型完全一致**。
`Defs.by_kind` 按编号排序，**不等于**原型的字典顺序（比如 `place:shaolin:abbot` 排在 `place:shaolin:estate` 前面，而原型里 `EST` 在 `SH_ABBOT` 后面很远），
所以每条 place / account / commodity / item / post 定义都带显式 `order`，内核一律按 `(order, 编号)` 排（`spec._scoped`）。
列表型字段（`canon`、`appointments`、`gens`、`classes`、`stock`、`roster.posts`、`timetable.rules`）的次序就是列表的次序。
**不得重排已有条目；新增条目请接在末尾**，否则状态哈希改变（这也是你想要的信号：世界变了）。

**`kernel = false`。** 别的模块（设施、NPC 引擎）往同一个 scope 加的场所、岗位等定义，若不该进内核的库表（进了会改变状态哈希），在定义里写 `kernel = false`，
`spec._scoped` 会跳过它；它们仍可被 `Defs` 查到并被引用。

**键用 ASCII，中文只放值里**（TOML 裸键不接受中文）。所以“按中文名索引”的表（如辈分 -> 配额、节日 -> 倍率）都写成列表里的小表（`{ name = "佛诞", mult = 10 }`）。

**单位。** 粮 1 石 = 1000 合，钱 1 贯 = 1000 文。参数 P 用原始单位（合、文），与原型一致，`World(params={...})` 按 P 的键覆盖；规则参数 K 的后缀写明单位：
`_shi` 石、`_guan` 贯、`_days` 日、`_sla` 订单时限（日）、`_n/_d` 整数分子分母（保持原型“先乘后整除”的取整次序）。

**浮点原样。** 价格倍率、概率等用 TOML 浮点写成与 Python `repr` 一致的字面量（`2/30` 写作 `0.06666666666666667`，已验证与 `2/30` 逐位相等）。

## 3 各类定义的字段

### 3.1 `calendar:<scope>:main`
`tianl.core.Calendar.from_def` 读：`year`、`festivals`（`{"4-8" = "佛诞"}`）、`retreat`（`[[4,15],[7,15]]`，含两端）、`wheat_doy`、`millet_doy`。
内核另读：

* `crops = [{flag="wheat", name="麦"}, …]`：`cal()` 里的 `wheat/millet` 标志对应的作物名（按此序检查收获）。
* `winter_months`、`busy_windows`（`[from, to)`）、`pilgrim_winter / pilgrim_busy / pilgrim_shuowang`、`pilgrim_festival = [{name, mult}]`：香客数的季节因子，
  结构同原型 `pilgrim_factor`（先冬、再农忙覆盖、再朔望乘、再节日乘）。
* `donor_festivals`（大节必有大施主）、`charity_festival`（施粥日）。
* `grain_season = [{from, to, factor}]`：粮价季节因子，先匹配先得，都不中为 1.0。
* 年内结算日：`new_year_doy`（招佃、僧龄加一）、`year_end_doy`、`sell_doys`、`shop_doys`、`after_harvest_doys`、`return_doys`、`recruit_doy`、`cloth_due_doys`、`cloth_hold_windows`。

### 3.2 `place:<scope>:<名>`
`code`（必填，运行时钥匙）、`name`、`access`（`open` / `locked_night`：夜间，见 `org.lock_slots`，无钥匙不得进入）、`order`。
住处（僧寮 `SH_DORM_n`）不是场所表里的行，由 `org.dorm` 规则生成。

### 3.3 `account:<scope>:<名>`
`code`、`boundary`（1 边界账户，可透支）、`order`、`name`；`opening_cash`（贯，开局由 `equity` 角色的账户注资，按 `order` 依次）；`year_end_cap`（贯，岁末超出部分转给 `town`）；
`shop = true`（铺户：报表里与边界账户一同列出）；`office`（铺户开单时的署名，写进 `work_order.office`）；`virtual = true`（只作收款人/货主的占位名，不进 `account` 表，如 `village`）。

### 3.4 `commodity:<scope>:<名>`
`code`、`name`、`unit`、`order`、`role`；`price`（文，主粮缺省——粮价随季节与年景）、`use`（寺院日用量）、`low / up`（补货线 / 补到，单位天；`use x low` 以下补到 `use x up`）、
`prio`（缺钱时的审批优先级，小者先批；`>= K.prio_reserve_from` 者批前先留压库钱）；`band = [低线, 补到]`（铺户的进货带）；`restock = true`（库头按 low/up 补的杂项，按 order 依次检查）；
`consume_order`（每日消耗的检查次序，`> 0` 才每日消耗）；`use_winter_extra`、`use_per_pilgrims`、`use_festival_mult`（日用量的浮动：冬季加量；每 N 香客加一；朔望或节日乘数）；`spoil_cap`（存量超此数当日腐坏）。

### 3.5 参数
* `param:<scope>:main`：参数 P，键名与原型 `P` 完全相同。
* `param:<scope>:rules`：规则参数 K。分组与单位见文件内注释：粮档位（`tiers / tier_mult / tier_cover / tier_pad` 与四个档位语义下标）、天气、香客、收成、农户、价格、寺库规则（调粮、市购、募化、借粮）、杂项补货、损坏与修缮、采买审批、订单时限、铺户、人。
* `param:<scope>:opening`：开局存货序列。每条 `{owner, place, c}` + 数量三选一：`qty`（原始单位）、`days`（品类日用量 x 日数）、`band = "hi"`（取铺户补货带上限）。
* `param:<scope>:households`：`classes`（顺序即造户顺序）：`role`（`tenant` 交租、可借粮；`owner` 纳两税；`wood` 供柴供菜、领工钱）、`code`、`label`、`prefix`（户号前缀，户号 = 前缀 + 三位序号）、
  `count`（P 里的户数键）、`mu`（人均田亩）、`place`、`cash`（贯）；`grain_days`（开局存粮日数）；`special`（按户号指定人口与户名）。
* `param:<scope>:labels`：`grain_market`、`shop`、`temple_store`、`dorm`；`grain_ledger`（寺院粮账各类别的中文名，是 `year_report` 的 `grain` 字典的键）。

### 3.6 `org:<scope>:main`
`name`、`account`（本寺账户）、`default_hall`、`deputy_prefix`（副职 = 前缀 + 正职名）、`visitor_gen / visitor_place / visitor_act`（外来香客恒在客堂）、`lock_slots`（夜间上锁的时辰）、
`elders_home`、`discipline_place`（违规被见、举报送往之处）、`dorm = {prefix, per, recruit}`、`recruit = {gen, age_min, age_span}`、`roster_stride / roster_shift`、`canon_masters`、
`gens`（辈分，次序即造人次序）、`halls`（院堂 -> 场所）、`canon`（要角，次序即人号次序）、`succession`、`appointments`（任命序）、`names = {pool, reserved}`。

* `gens[]`：`gen`、`n`（无名僧人数）、`age = [低, 高]`（含两端）、`master_gen`（师承自该辈全体随机选）、`senior`（长辈，按院堂住处所而非僧寮）、`quota = [{hall, n}]`（前若干人依次分到各院堂）。
* `canon[]`：`name / gen / age / hall`，可选 `home`（缺省按辈分与院堂推出）。要角在造人时排在最前。
* `succession`：`min_age`、`hall_rank`（院堂首座的候选辈分次序）、`other_rank`；同辈先年长，再先入。
* `appointments[]`：`post`（岗位引用）；`canon`（指定要角）或 `pick = "hall"` + `gen/hall/index`（取某辈某院堂的第 index 人）或 `pick = "free"` + `gen`（取该辈尚未分院堂者的下一人）；`deputy = true` 为副职。
* `names.pool` 按出现顺序去重后用随机键取字，**字序不得改动**；`names.reserved` 是保留法名。

### 3.7 `post:<scope>:<名>`、`rule:<scope>:roster`、`rule:<scope>:timetable`
* `post`：`name`（库里存的岗位名）、`site`（岗位站点：夜间上锁场所的“钥匙”、作息里的“执事”处）、`critical`（关键岗位的检查次序，无人任职超过 `K.vac_limit` 日记违规）、`hall`（该岗位是某院堂首座，继任只从该院堂选）。
* `roster.posts[]`：`label`（班名，库里存的值）、`place`、`slots`（时辰序号，子 = 0）、`n`（每时辰几人）、`hall / gen`（候选人）。
* `timetable.rules[]`：作息模板，自上而下取第一条命中的规则。`when` 的条件全部成立才命中：`slots`（时辰字串）、`base`（岗位引用列表，副职按正职算）、`site`、`gen`、`hall_mapped`、`hall_in`、`shuowang`、`retreat`；
  `out[]` 自上而下取第一个条件成立者（无 `when` 为缺省）：`place`（场所引用，或 `$home / $site / $hall`，`$hall` 配 `fallback`）与 `act`。最后一条规则必须无条件（缺省作息）。

### 3.8 `item:<scope>:<名>`
`code`、`name`、`home`（应在处，月朔点检发现不在即记失窃）、`keeper`（保管岗位引用）、`custodian = "keeper"`（开局由该岗位的首任者持有）、`order`。

### 3.9 `scenario:<scope>:regress`
只给 `tools/shaolin_regress.py` 用：`seeds`、`probe_day`、`canon_probe`、`probes`、`visitor`、`lock_probe`、`takes`。

## 4 内核代码里还保留的词汇

下面这些**不是**哪座寺院的常量，是内核的状态机与记账词汇，写在代码里：

* 工作订单状态（待接、已接、进行中、受阻、完成、失败、过期）与订单种类（`TRANSFER PURCHASE IMPORT BORROW REPAIR ALMS`）、人的状态（在寺、圆寂、游方）、农户状态（在、离乡）。
* 流水的“事由”字符串（`ledger.reason`，如“期初”“香火钱”“货款:…”），以及粮账里 `tg` 的英文键；规则编号（`R-RESTOCK` 等）；事件类型（大写英文代码）。
* 计量单位（石、贯，见 `vocab.py`）、日报里的叙述性动词。
* 规则的**结构**（谁在什么条件下开什么单、审批的次序、收成怎么分）——它们是 v0.2 的钱粮闭环，本身不是数据；数据化的是其中的阈值、比例、岗位、品类与名字。

## 5 内核接口摘要（详见 ARCHITECTURE 第 5 节）

```python
from tianl.kernel import World, load_spec
w = World(params=None, spec=None, defs=None, engine=None)
w.day, w.slot                      # 下一个要跑的时辰
w.begin_day(); w.run_slot(); w.end_day(); w.advance(n); w.step(); w.run(days)
w.state_hash(); w.econ_hash()      # 全库 / 只含经济表
w.where(pid, day, slot)            # -> (场所 code, 活动)；where_ex 另带 层 与 原因：(场所, 活动, 层, 原因)
w.present(place, day, slot); w.cmd_move(...); w.cmd_take(...); w.chronicle(day); w.why(event_id)
w.attach(engine)                   # 接上引擎；engine=None 时与原型逐位相同
```

* `advance(n)` 在日界处自动 `end_day`，但**下一日在要跑它的第一个时辰时才 `begin_day`**；所以停在日界时，哈希与 `step()` 跑完同样日数相同。日内停下时事务保持打开。
* `step()` 若发现日内已走了几个时辰，就补完这一日。
* `where_ex` 的取值次序：引擎（若接了且它管这个人）> 指派（`cmd_move` 落的例外）> 外来香客 > 值守班表 > 作息模板；不在世与游方者返回 `None`，不问引擎。
* 引擎协议里的 `on_person_added / on_person_removed` 在造人（含每年收录）、圆寂、游方、游方归寺时调用；开局的人已在库里，`engine.attach(world)` 时由引擎自己读 `person` 表。
* `World.S` 是装配好的 `Spec`；`w.pl / w.ac / w.cm / w.hk / w.T / w.K / w.G` 是它的常用视图（场所、账户、品类、农户类别、岗位、规则参数、品类表）。

## 6 再写一座寺院

1. 在 `defs/<类别>/` 下仿照少林寺写一组定义，`scope` 换成新名字（如 `tianlong`）：`calendar`、`place`、`account`、`commodity`、`param:*:main/rules/opening/households/labels`、`org`、`post` 与两条 `rule`、`item`。
   最省事的办法是复制少林寺的整套文件，全局把 `:shaolin:` 换成 `:<新名>:`，再改名字与数值。
2. 必须配齐的角色（缺哪个装配时报哪个，见 `spec.REQUIRED_ROLES`）：
   场所 `temple gate main_hall fatang refectory granary store guest grounds road estate estate_granary village town port`；
   账户 `org equity port pilgrims town state neighbor shop_grain shop_gen village`；
   品类 `staple fuel fresh textile lumber`（`role` 字段）；农户类别 `tenant wood`；
   岗位 `abbot supervisor cook stock_keeper manor_head guest_master grounds_keeper disciplinarian almoner discipline_head`。
3. `order` 要自己排：造库、造人的次序即哈希口径。新寺院没有“原型哈希”可对，但必须自己**重跑一致**、**违规 0**（`World(spec=load_spec(scope='<新名>')).run(360*4)`）。
4. 取名池 `names.pool` 至少 `K.pool_min` 个不同的字；各辈 `n` 的总和加要角数就是开局僧数，`P.monks` 是定员（收录补足到它）。
5. `tests/test_b1_defs.py::test_new_scope_runs_identically` 演示了换 scope 的做法（把少林寺的定义整套改名为 `demo`，跑出的世界与原来逐位相同）。

## 7 验收命令

```
python3 -m unittest tests.test_b1_kernel tests.test_b1_defs          # 默认（约 25 秒）
TIANL_SLOW=1 python3 -m unittest tests.test_b1_kernel tests.test_b1_defs   # 十年基准、六个种子、E2/E2b/E5/E6、人物测试、逐类常量复核（约 75 秒）
python3 tools/shaolin_regress.py --all | diff <(sed -E 's/用时 [0-9.]+ 秒/用时 X 秒/' -) <(sed -E 's/用时 [0-9.]+ 秒/用时 X 秒/' reference/logs/shaolin_run_log.txt)   # 无输出即逐字节一致
```

## 8 没做与已知限制

* `cmd_put / cmd_use / cmd_say` 未实现（ARCHITECTURE 5 节：之后由集成代理做）。
* 钱粮闭环的**结构**仍是 v0.2 的写法（见第 4 节），所以新寺院的“规则”只能调参数、品类与岗位，不能增删规则种类；那要等 `rule` 定义有了解释器再说。
* 僧寮 `SH_DORM_n` 只是 `person.home` 里的字符串，不在 `place` 表里（与原型一致；加进去会改变哈希）。
* 原著要角与保留法名“凭记忆，落正式数据前需对照原文”（沿用原型的标注）。
