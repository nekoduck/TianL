# NPC 引擎（tianl/npc）实现说明

本文由 C 段负责人维护，是 `docs/ARCHITECTURE.md` 第 6 节的细化。计划出处：`docs/PLAN.md` 第 5–11 节；
数字出处：`reference/logs/npc_run_log.txt`（原型 `reference/npc_spike.py`，只读）。

**当前进度（C 段第二步：引擎由 defs 驱动，已完成）**：第一步移植出的模块化引擎，现在的世界描述（`SiteSpec`）与场景（`ScenarioSpec`）
**完全由 `defs/*/proto60*.toml` 构造**（`SiteSpec.from_defs`），行为包（第 7、8、9 层）是数据、条件判断走登记的处理器、需求与性格刻度、想法、好恶修正项、处分阶梯、
传闻参数、心情三道线都来自 defs；第一步的全部哈希与数字一字不差地复现；四个给后续步骤的钩子（`life.pulse`、`controller.decide`、`lod.observe`、`persist.flush`）
已在 `engine.py` 里预留（默认空操作）。第二步的全部内容见**第 12 节（defs 字段、处理器、示范）与第 13 节（钩子）**；第 1–11 节是第一步的记录，涉及 defs 的地方已随第二步改过。

**第二步的修订（针对独立验证者；没有动任何已有的数字与哈希，`python3 tools/npc_regress.py --all --diff` 仍是 55 行全部一致）**：
① 报错“一次报全”此前只在同一阶段内成立（类型、越界错要等结构错修完才出现）：现在行为包与准入门自身的全部问题（层、谁、何时、做什么、处理器与参数的类型 / 取值 / 引用）在读 defs 时就一次查全，
与规格自检共用同一份校验函数（12.3）；② 300 僧名册重名（字池只有 62 字）：超过一圈后名字后缀字（`scenarios.given_name`），第一圈与原型逐字相同（12.10）；
③ 两处写死的场所用词挪进 defs：explain 里的“离寺”（`org:main.leave_word`）、报表标题的“60 僧”量词（`scenario:main.track_suffix`）；
④ `stack.decide` 有副作用——同一个人同一个时辰只算一次、再问原样返回（给 C9 的约束，第 13 节）；⑤ 测试：死代码改成真断言；`DocsInSync` 增加逐表逐行与代码生成的字段表比对（原先只做子串检查）；
`test_npc_spec` 的“原型那一遍”放进 fork 出来的子进程与移植版同时跑，几个只读的运行在各 npc 测试文件之间共用（`test_npc_support.shared_run`）；
⑥ 文档措辞：ARCHITECTURE 6 节的错误类型（`DefsError` / `SpecError`）、本节的测试用时。

**第二步的第二次修订（针对第二位独立验证者；同样没有动任何已有的数字与哈希，55 行日志仍全部一致）**：
① **历法随 scope 走**：此前 `stack.py` 读的是 `tianl.core.cal()` 的全局默认（少林历），给丐帮分舵或庄园写新 defs 时 `when.festival / month / day_of_month` 仍按少林历，文档也没写这条限制。
现在历法是规格的一部分：`rule:<scope>:schedule` 新增必填字段 `calendar`（引用一条 `calendar` 定义），`SiteSpec.calendar`（`SiteCalendar`：核心 `Calendar` 加值相等）喂给日历键；`engine.cal(day)` 给后续步骤用；
`tianl/npc` 里没有任何模块再引入全局 `cal`（有 AST 测试）；节日名写错、月不在 1–12、月内日不在 1–30、季节表的月份越界，读 defs 时就报错（12.2、12.9 第 8 步、12.10）。原型场景引用 `calendar:shaolin:main`，与全局默认同值，所以基准哈希不变。
② 数值普查里“无可见效果”的 13 个字段清零：12 个季节表项用新的专门场景 `seasonal`（四个季节各一个包、每月第一日各跑一日）显形，`traits.lo.R` 用 `lowR`（种子 5 的开局里有人的刚正被夹在下限，跑 N1）显形；
普查变为 409 个字段：380 活、29 受校验、0 无可见效果、0 崩（第 8 节、11.1）。③ 文档对账：测试总数与各文件数、“npc 五个测试文件”（`test_npc_support` 是夹具，没有测试）、慢测试数与用时，以实跑为准（11.1）。

**第一步（C 段，已完成并经独立验证与三轮修订）**：把 60 僧 30 日原型**忠实**移植成模块化的 `tianl/npc` 包。
第一步的规格用 Python 数据类（`SiteSpec`）手写，`scenarios.proto60_spec()` 构造出与原型完全一致的一套（第二步起改为 defs 构造，字段不变）。
哈希、全部汇总数字、逐行日志已由 `tests/test_npc_proto.py` 自动比对；与原型的逐步差分（轨迹、统计、事件序列、终态）
见 `tests/test_npc_spec.py`（第 8 节）。第 9 节记录与原型的刻意差异与已知限制，第 10 节是给后续步骤的接入说明。
第 9 节末尾单列“按计划留给后续步骤的”几件事：defs 驱动、其余七种事件、life/lod/controller/persist、KernelHost。

第二轮修订（针对独立验证者的结论；没有动任何已有的数字与哈希）：
① 自由时段没有正分广告时不再 `IndexError`（第 9 节 12）；② 处分时指认人的遍历次序、工作板优先级 `prio` 的含义写进第 9 节（11、13）；
③ 验证加强（第 8 节）：无魔数规则收紧（0 1 2 3 不再全放行）、业务词不得进引擎代码、每种抽签用途都与原型的抽签键逐一比对、
改动原型常数的“扰动差分”、对原型没走到的分支补差分、规格数值字段普查；④ 速度只记比值（`--speed`），不再写本机绝对数（第 9 节 8）。

第三轮修订（针对第二位独立验证者的结论；同样没有动任何已有的数字与哈希）：
① **原型场所短码**（`hall kit dorm1`……）进入随机数键与基线哈希，此前没写进第 10 节——补上（第 9 节第 14 条、第 10 节），并用 `tests.test_npc_engine.PlaceCodesAreKeys` 把事实钉住；
② 三处从没有对照场景走到的防御性分支（自由时段候选全满、没有藏主、没有清众）现在各有直接构造的测试（`DefensiveBranches`，改坏源码会红，见第 8 节）；
③ 数值普查里原先“没有可见效果”的十个字段，用四个专门场景（只改规格、不改引擎）让它们显形：普查结果由 333/2/10 变为 **343 活、2 受校验、0 无可见效果**（第 8 节），
原型世界单独跑时这十个仍是死的，这一点也有慢测试断言；④ `Profile.id` 作为 `ix` 的只读别名（任务书的验收脚本写 `common[8].id`）；
⑤ 默认测试没有因新增检查而变慢（没有削弱任何比对）：新增了 13 个测试，npc 四个测试文件合计仍是 18 到 20 秒（本机，随负载浮动；修订前 90 个测试 18 到 19 秒）。做法：
`test_npc_engine` 里只读的 90 日与基准运行共用（`shared_run`）；`test_npc_spec` 里同一配置的“原型 + 移植版”运行只跑一次（`both()`：逐步差分与抽签键多重集共用同一次运行）；
`test_npc_sensitivity` 的默认检查用 fork 多进程（没有 fork 的平台退回串行）。新增检查本身很便宜：十个字段的专门场景约 1 秒，防御性分支与场所短码的测试合计不到 1 秒。
整套默认测试（含别的步骤的）如实记录：第一步修订时本机 53 到 55 秒（别的代理同时在跑时 57 到 60 秒，独立验证者三次实测 57.4 / 57.7 / 59.9 秒）；第二步第二次修订后（368 个测试）本机两次实测 54.0 与 52.9 秒（修订前独立验证者测得 359 个、51.8 秒；新增的 9 个测试约 1 秒，其余是机器负载的浮动），**离 60 秒的线只有几秒的余量，不算稳**；
其中 `test_b1_kernel` 一个文件约 20 秒（不是 npc 的）、npc 五个文件各自单独跑约 3 到 7 秒（`test_npc_engine` 6.6、`test_npc_defs` 5.5、`test_npc_spec` 5.1、`test_npc_proto` 3.4、`test_npc_sensitivity` 3.4；合起来在一个进程里因共用只读运行而少几秒），后者是原型逐步差分的必要开销——没有放宽任何比对，也没有把默认检查挪去慢测试。没有哪一个测试特别慢（最慢的 1 秒左右），想再省时间只能一个个去共用只读运行。

## 1. 模块划分与依赖方向

```
spec.py        规格数据类：SiteSpec 及其子规格（不可变）与 SiteCalendar（核心 Calendar 加值相等；历法是规格的一部分）。引擎里没有魔数，所有常数都是这里的字段；from_defs 转给 defsload。
defsload.py    由 defs 构造规格：SiteSpec.from_defs / ScenarioSpec.from_defs，读字段时顺手校验、一次报全；字段表由它生成（第 12 节）。
events.py      NPC 事件类型代码（大写英文）及中文渲染。哈希用中文渲染，所以代码与中文一一对应。
host.py        Host 接口、Event、StandaloneHost（事件存内存列表）。
model.py       PersonSpec（建人用）、Profile（运行档案）、Symbols/Trail（轨迹打包，允许缺格）、Case、EvRec（引擎事件记录：流水号 id 与 Host 的 hid）。
opinion.py     好恶：底数 + 带期限修正项（CK3 式）；好友/不睦。
mood.py        想法（带期限加减分）、心情、第一道线。
needs.py       五项需求：一日收支、惰性求值的结算函数。
facilities.py  设施运行时：工位占用（预约）、广告打分、准入门（gate 登记表）。
freechoice.py  自由时段：打分 → 前三名按分数加权抽 → 占位 → 顺次改选 → 散步。
jobs.py        工作板（JobRow）：每日发布（按 prio 升序，同级按规格次序）、认领即预约、结算（每名工人一条内核命令）。
stack.py       十层行为包栈：自上而下第一个成立的生效；返回 (场所, 活动, 层, 原因)。
perception.py  事件 → 见证人处理：偷食见证、查寮空铺、点名缺课、典座清点、怠工被撞见。
rumor.py       闲谈配对、转述、衰减、传闻实验的追踪（曲线、经手层数）。
norms.py       举报判定、送达、立案、传讯与认错、裁断、处分阶梯、公告与余波。
engine.py      NpcEngine：begin_day / run_slot / end_day 与查询 API。
report.py      汇总与原型输出格式（regress 工具与测试共用）。
scenarios.py   场景装配：加载 defs（缓存）、proto60_spec() / proto60_scenario()、名册、要角、脚本、ProtoRun、实验 N1。没有原型场景的数。
handlers.py    登记表：行为包处理器（13 个）与准入门（2 个：lib_open、bath_day），每个带参数表（Param：类型、默认值、取值范围）。
life.py lod.py controller.py persist.py   四个钩子所在的模块（第 13 节）：默认空操作；之后由 C7/C8/C9/持久化各步只改自己的模块。
```

依赖方向（只许向下）：`scenarios → engine → {stack, perception, norms, rumor, jobs, freechoice, needs}
→ {facilities, opinion, mood, model} → {spec, events, host}`；`spec ⇢ defsload`（`from_defs` 里惰性导入）`→ {handlers, spec, events}`；`handlers → spec`。同层模块通过 `engine` 对象互相调用，
不得互相 import 模块级函数形成环。

## 2. 数据模型

### 2.1 人：ix 与 pid

* `ix`：引擎内部下标（int，从 0 起，**稳定，新人只追加**）。所有内部结构（修正项、见闻、案件、轨迹、随机数键）都用 ix。
* `pid`：外部编号（str，如内核的 `P0001`）。只在 Host 边界与查询 API 的入口出现；查询 API 的参数 ix/pid 都收。
* 随机数键里的“人”一律是 ix。一次抽签只取决于键本身（种子、用途、日、时辰、有关的人的 ix……），所以与调用次序、
  观察者站在哪里、Host 怎么给事件编号都无关。注意 ix 就是加入次序：同一个人换了加入次序，ix 变了，开局性格与之后的抽签也跟着变。
* 事件同理分两层：`EvRec.id` 是引擎自己的流水号（从 0 起，按发出次序；见闻、案卷、待报、随机数键都用它），
  `EvRec.hid` 是 Host 给的事件 id，只在边界出现：交给 Host 的 `cause`、`news_of`、`cases()`、`explain()['state']['pending']`
  的出口都是 hid（`event_of(hid)` 反查记录）。`StandaloneHost` 从 0 顺序编号，所以流水号与 hid 恒等，也等于原型的列表下标。

### 2.2 Profile（运行档案，`model.py`）

| 组 | 字段 |
| --- | --- |
| 身份 | `ix pid name office track dorm`（`id` 是 `ix` 的只读别名：原型的档案叫 `id`，验收脚本写 `common[8].id`；不另存一份） |
| 性格 | `D S G T R`（精进、守戒、合群、馋、刚正，0–100，开局生成，极少变动） |
| 身体 | `need{h,e,c,s,a}`、`ill`（病到第几日，含）、`conf`（禁闭到第几日，含）、`kneel`（跪香到第几日，含）、`gone`（离开的日子）与 `gone_why`（缘由：处分阶梯的文字，或 `on_person_removed` 给的 why） |
| 认知 | `news{事件id → [强度, 经手层数, 来源ix]}`（最多 16 条，弱的先忘）、`thoughts[[值, 止日, 标签]]` |
| 案卷 | `pending`（见证后待报的事件 id）、`offences`（受处分次数）、`absent`、`slackd`（近期缺课/怠工日） |
| 其他 | `duty_day`（代理帮厨的日子）、`lazy_day`（贪睡的日子）、`trail`（轨迹） |

好恶不存在档案上：引擎持有 `mods{(a,b) → [[值, 止日, 种类]]}`；底数由两人档案现算（见 `opinion.py`）。

### 2.3 规格（`spec.py`）

`SiteSpec` 是不可变数据类（`frozen=True`），由 defs 构造：`SiteSpec.from_defs(defs, 'scenario:proto60:main')`（第 12 节）。主要成分：

* 空间与时间：`places`（场所 code → 显示名）、`capacity`（设施登记的工位数）、`cap_default`、`dorms`（寮房）、`roam`（巡寮候选）、`night`、`rotate`、`meal_slots`、`seasons`
* 人群：`offices`（岗位表，`OfficeSpec`）、`office_track_cycle`、`name_pool`、`common_prefix`、`common_tracks`、`groups`、`traits`（性格刻度，`TraitSpec`）
* 行为包栈与交互：`layer_rank`（层标签 → 计划 6.1 的层号）、`stack`（`PackageSpec` 的元组：层、谁 `WhoSpec`、何时 `WhenSpec`、做什么 `DoSpec` 或处理器 + 参数；判定次序）、
  `interactions`（活动 → `InteractionSpec`：所需工位、时长、需求增减、所需物与产出物、触犯的规范、类别、功课加成、想法）、`violations`（活动 → 触犯的规范、事件与场所）
* 机构与规范的参数：`kitchen`、`patrol`、`gate`、`court`、`rollcall`、`inventory`、`slack`、`illness`
* 需求与自由时段：`needs`（`NeedSpec`）、`ads`（`AdSpec`：设施广告，含准入门与参数）、`free`、`jobs`（工作板 `JobSpec`）
* 好恶、心情、闲谈、传闻：`opinion`、`mods`（修正项，`ModSpec`）、`thoughts`（想法，`ThoughtSpec`）、`mood`（`MoodSpec`：权重与三道线）、`chat`、`rumor`、`salience`（事件显著度）
* 规范：`report`（举报概率）、`cases`（案卷；`via_report / via_confess` 是定罪依据的两个标签）、`ladder`（处分阶梯，`LadderStep`）、`announce`

`ScenarioSpec`（`ScenarioSpec.from_defs`）与世界描述分开：种子、人口、要角、传闻实验（`GossipSpec`）、实验 N1（`N1Spec`）与报表用词。
规格里的字段没有默认值，取值全写在 defs 里，所以“改一个数”只有一个出处；`SiteSpec.validate()` 做引用完整性自检（场所、岗位、想法键、修正项键、活动、层标签、
处理器与准入门及其参数、值守包相邻、栈里有 `free` 兜底；`ads` 不得为空、`free.top_k` 至少为 1、`mood.enabled` 现在只能是 1），`NpcEngine` 构造时调用，不通过抛 `SpecError`。

* **数值没有出处就不许出现**：`tests/test_npc_engine.py` 用 AST 扫 `tianl/npc` 的**每个模块**（含 `spec.py`、`scenarios.py`、`defsload.py`）：数值字面量只能是模块级的具名常量
  （`NEVER`、`FIELD_BITS`、`BASE_DECISION`、`PAIR`、`HASH_CHARS`、`PKG_STAT`、`PERCENT`、`MICROS`、`FIRST_SLOT`、`SCALE`、`*_ARITY` 一类“数据格式的元数”……），
  或“结构用”的 0/1/2/3：下标与元组位置（0–3 都行）、计数（`+= 1`、`sum(1 for …)`）、初值 0、±1 偏移、`max/min` 的保底、与 0 或 1 的比较；2 和 3 只许做下标，
  乘除里的 0、赋给字段的 1 一律不放行（规则自己有“有毒代码”的反例测试）；`handlers.py` 另许 `Param(…)` 的默认值与取值范围（处理器的默认参数，原型场景不靠它）。
  另有一条：规格里的中文业务词、场所代码、岗位名不得以字符串字面量出现在引擎代码里（`spec.py`、`events.py` 里结构性的层标签、活动代码、事件渲染除外）。
* 场景参数（传闻实验的日子与人与时辰、N1 的日子与两个对照组、90 日、多种子清单、报表里的用词）都在 `defs/scenario/proto60.toml`，`report.py` 经 `proto60_scenario()` 取用。
* `tests/test_npc_spec.py` 还检查：原型源码里出现过的每个数值常数（不豁免任何数）都在 defs 构造出的规格（或场景的“要角”）里出现——
  注意这条只比“数值集合”，拦不住“数在规格里、却被抄错或不被读”；真正的把关是第 8 节的逐步差分、抽签键多重集、扰动差分与数值普查。
* 统计口径：`free.choice_key_chars`（“自由时段的选择”统计取原因的前几个字作键，原型口径 2，只入统计）。

### 2.4 轨迹与“说得清”

每个决定在落轨迹时打包成一个 64 位整数 `(场所, 活动, 层, 原因)`（`Symbols` 做字符串驻留，`Trail` 是每人一个 `array('Q')`，
四个字段各 16 位，见 `model.FIELD_BITS`），所以 `where(pid, day, slot)` 对任意已跑过的时辰都能答，`explain` 给出生效层、层号（计划 6.1）与原因。
**每个决定都有非空的层与原因**；每起处分的事件 `cause` 指向偷食事件，案卷记录 `via`（举报/认错）与指认人。

`Trail` 按绝对时刻向后追加，**允许缺格**：中间有时辰没记（暂离再回、将来的精度分档）时自动补 `GAP` 占位（四个字段全满，
`Symbols` 不会分配到这个号），`get(t)` 因此永远按时刻对号入座，没有记录的时刻返回 None；时刻回退或重复则抛 `ValueError`。
`places_of` 对缺格给 None，`agree` 只比两人都有记录的时刻。

`where()` 返回 None 的情形：还没跑到、加入之前、离开之后、轨迹中间缺格。**离开之后**可再问 `explain()`：
它对“已离开且此刻没有记录”的时辰返回 `{'gone': 离开日, 'reason': 缘由, 'text': '……已于第 N 日离寺（缘由）', 'place': None, …}`，
而不是 None（例：迁单当日巳时裁断之后的各时辰；原型里该人当日之后不再有决定）。

## 3. Host 接口（`host.py`）

引擎与外界只通过 Host 交互：

```python
class Host:
    seed: int
    rng: Callable[..., float]          # rng(seed, 用途, 日, 时辰, 人…) -> [0,1)；默认 tianl.core.rnd
    def ev(self, kind, actor, place, witnesses, day, slot, cause=None, **data) -> Event   # 返回含 id 的事件对象
    def cmd(self, name, pid, **args) -> CmdResult                                        # 内核命令调用口（stub）
```

* `actor`、`witnesses` 在 Host 边界是**外部 id（pid，str）**，actor 可为 None；引擎内部另存 ix 版本。
  事件 id 由 Host 分配（不要求从 0 起、不要求连续、不要求只有本引擎在写），引擎把它记作 `hid`，只在边界上使用
  （交给 Host 的 `cause` 就是被指事件的 hid）；**见闻、案卷与随机数键用引擎自己的流水号**，所以引擎的行为与 Host 怎么编号无关——
  接内核 `World.ev` 后（id 与别的系统共用、不连续），同一个世界的结果与 `StandaloneHost` 逐位相同
  （`tests/test_npc_engine.py::HostBoundary` 用“从 1000 起每次跳 3”的 Host 验证）。
* `Event` 有 `id kind actor place witnesses day slot cause data`；`event.wit` 是 `witnesses` 的别名，
  `event.payload()` 返回含 `wit` 的字典（架构 6.2：所有 NPC 事件 payload 含 `wit`）。
* `StandaloneHost(seed, rng=rnd)`：事件存内存列表，id 从 0 起顺序编号；`cmd` 恒返回成功（可选记录）。
  之后集成代理另写 `KernelHost`，把 `ev` 接到 `World.ev`、`cmd` 接到 `cmd_*`。
* 复现原型哈希：`StandaloneHost(seed, rng=tianl.core.rnd_b2)`。

内核命令口本步只有一处用法：差事结算时每名工人发一条 `host.cmd('job', pid, job=…, place=…, day=…, slot=…)`，
返回不成功的人该次不计完成、也不产出（standalone 恒成功，与原型一致）。`StandaloneHost(record_cmds=True)` 记录命令，测试用。
`NpcEngine` 还实现 ARCHITECTURE 5.1 的 `attach / on_person_added / on_person_removed / where`（以及 begin_day / run_slot / end_day）。
`on_person_added(pid)` 与契约同形：pid 已在名册里就什么也不做；不在则向 `NpcEngine(..., person_factory=…)` 给的
`person_factory(pid) -> PersonSpec` 要一份说明来建人（没有工厂抛 `LookupError`，工厂给错了人抛 `ValueError`）。
集成层（KernelHost 一侧）负责提供这个工厂：从内核的人员行翻译出岗位、修行方向、寮房。直接给 `PersonSpec` 也行（独立运行与测试用）。

## 4. 时辰 tick 的固定次序（与 ARCHITECTURE 6.1 一致；变更须同时改两处）

`NpcEngine.begin_day(day)`：
0. **钩子 `life.pulse(engine, day)`**：月 / 年脉冲（默认空操作，第 13 节）。
1. 各人生病抽签（`ill`）；脚本 `ill`。
2. 行为包处理器的每日钩子（`begin`）：厨房在岗人手不足 `proxy_cook.target` 人 → 监院派人代理（按精进降序、编号升序，避开山门值守与病、禁闭者；仅当 `acting`）。
3. 发布当日工作板；清空当日“查寮名单”（`sight`）。

`NpcEngine.run_slot(day, slot)`（`n` 是含已迁单者的总人数）：
1. **各人决定**：起点 `(day*rotate[0] + slot*rotate[1]) % n` 轮转（`rule:schedule` 的 `rotate`，原型是 7 与 3）；跳过已迁单者；调用十层栈；巡寮者的决定携带“所巡之处”。
   **钩子 `controller.decide(engine, p, day, slot, ctx)`**：每人每个时辰的“决定”入口——只有 `engine.controllers` 非空才经过，默认直接走栈（第 13 节）。
2. **闲谈配对**：打算闲谈的人按随机序排队，队首挑“好恶 + 30×随机”最大者；落单者改散步；转述传闻。
3. **差事结算**（巳时）：工人两两短闲谈（改好恶、补“群”，不产生想法）；每名工人一条内核命令；挑水/打柴入账。
   **斋食**（辰、午）：备斋时辰（卯、巳）厨房的人手与水柴 → 足量或半餐。
4. **需求结算；想法；落轨迹**（统计、行为包占比、哈希在此累积）；预约越界检查。
5. **观察者**所在场所的细节叙述：**钩子 `lod.observe(engine, ctx, day, slot)`**，只读，现在只计数 `narr`。
6. **偷食 → 见证 → 是否举报**；巡夜查寮记空铺（子、丑）；脚本 `gossip`（场景给的时辰，原型是丑）。
7. **典座清点**（寅）；**维那点名**（卯、酉）；**怠工被撞见**（巳）；**举报送达**；**裁断**（巳）；**午斋后公告**（午）。

时辰对照：子 0、丑 1、寅 2、卯 3、辰 4、巳 5、午 6、未 7、申 8、酉 9、戌 10、亥 11。上面各时辰都是规格里的字段
（`kitchen.prep`、`court.judge_slot`、`rollcall.slots`、`inventory.slot`、`announce.slot`，以及各行为包的 `when.slot`，差事时辰 = 差事包的 `when.slot`）。

`NpcEngine.end_day(day)`：想法到期；见闻按日衰减并裁到 16 条；统计心情低落；修正项到期；传闻曲线；逐日偷食累计；
最后是**钩子 `persist.flush(engine, day)`**：每日落盘（默认空操作，只读）。

`ProtoRun.run()` 逐日调用以上三步；`state_hash()` = 每决定一行 `日,时辰,ix,场所,活动;` 累积的 sha256，
最后再并入事件日志每条 `种类中文,actor,日,时辰;`，取前 16 位十六进制。

## 5. 十层行为包栈（`stack.py`）

沿用原型的实际判定次序（与计划表的层号对应见 `spec.layer_rank`）。**次序、谁适用、何时成立、做什么都是数据**：栈的次序是 `rule:proto60:stack` 的 `packages` 列表，
包与处理器见第 12.5、12.6 节；下表是原型场景的栈：

“判定先后”是代码里 `Stack.decide` 实际的判定次序；“计划层号”是计划 6.1 的层号，即 `spec.layer_rank`（`explain()['layer_rank']`）。
两套数不是一回事：计划把“情节与指派”并入“值守”、把默认作息归入“身份”，越轨与怠工不是一层包，所以记 0。

| 判定先后 | 层（原型里的标签） | 计划层号 | 说明 |
| --- | --- | --- | --- |
| 1 | 强制 | 1 | 卧病（延寿堂）、禁闭（戒律院） |
| 2 | 处分 | 2 | 未时到大殿罚跪香 |
| 3 | 反应 | 3 | 有待报的举报且戒律院开门，巳/申时去举报（值守者除僧值外免） |
| 4 | 值守 | 5 | 厨务、代理帮厨、巡夜/巡寮、山门（计划的“情节与指派”4 并入此层） |
| 5 | 生理 | 6 | 昏沉不支、饿极偷食 |
| — | 越轨 | 0 | 夜里偷食、贪睡不起、午后偷食；怠工的标签是“怠工”（也记 0） |
| 6 | 作息 | 9 | 夜间就寝（计划里归第 9 层“身份”的默认作息） |
| 7 | 集体 | 7 | 晨坐、早课、早斋、午斋、晚课、晚坐、布萨 |
| 8 | 岗位 | 8 | 本职理事时段 |
| 9 | 身份 / 差事 | 9 | 清众：巳时领差事，申时本方向功课 |
| 10 | 自由 | 10 | 按需求挑设施 |

**基准世界里从不生效的两处**（别误以为它们被“基准哈希”验证过了）：
* “反应”层（去戒律院举报）：基准、90 日、种子 1–5 里一次也没有生效——举报全由“当面禀告”送达（`rep_face` 等于举报数）。
  只有 N1 无人代理的个别种子（6、11、34、35、36 的 40 日）才走到它；`test_reaction_layer_branch_is_compared` 用种子 34 与原型逐项比对。
* “生理”层里的“昏沉不支”（困 < `phys.faint_e`）与“贪睡窗口里的困乏未起”（困 < `lazy.tired_e`）：基准里没人困到那个地步。
  `test_perturbed_constants_still_agree_with_the_prototype` 把原型的 `BASE['e']` 在内存里改成 -18，同时改规格，两边逐项一致。

## 6. 事件类型（`events.py`）

本步实际发出的七种，与原型逐条对应（流水号、次序、数量与原型相同，哈希才能复现）：

| 代码 | 中文 | 谁 | 备注 |
| --- | --- | --- | --- |
| `FOOD_THEFT` | 偷食 | 当事人 | 见证人得见闻（强度 80） |
| `THEFT_FOUND` | 失窃 | 无（清点者为见证） | `cause` = 偷食；立案；见闻强度 50 |
| `REPORT` | 举报 | 举报人 | `cause` = 偷食 |
| `SANCTION` | 处分 | 受处分者 | 午斋后表堂，`cause` = 偷食，`data.txt` 是处分；见闻强度 60 |
| `ABSENCE` | 缺课 | 缺课者 | 见证人 = 维那 |
| `SLACK` | 怠工 | 怠工者 | 见证人 = 撞见的巡寮者 |
| `BED_EMPTY` | 夜不在寮 | 空铺者 | 见证人 = 巡夜者 |

架构 6.2 列的其余代码（`CASE_OPENED CONFESS SUMMON ANNOUNCE ILL RECOVER CHAT`）已登记在 `events.py`（含中文渲染），
**本步不发**（ARCHITECTURE 6.2 明文：“第一步只发其中七种”）：原型没有这些事件，多发一条就会改变引擎的事件流水号并因此改写
所有以它为键的随机抽签（`disc`、`report`、`confess`、`share`），事件日志也是哈希的一部分，原型哈希将无法复现。认错、传讯、立案目前记在案卷（`Case.via / asked / opened / acc / sus`）里，`cases()` 可查；
“每起处分都能回溯到一条举报或认错”由 `SANCTION.cause → 偷食事件 → 案卷 via + 指认人` 保证（`tests/test_npc_engine.py` 对
三个种子的 90 日自动检查）。之后的集成步骤要发这些事件时，须同时承担“流水号变了，哈希基线要重做”的代价，并在本表登记。
（事件流水号与 Host 的 id 已经分开，所以 Host 一侧写多少别的事件不会影响基线；只有引擎自己多发才会。）

## 7. 查询 API

`where(pid, day, slot) → (场所code, 活动, 层, 原因) | None`；`present(place)`；`explain(pid, day, slot)`（离开之后也有答案，见 2.4）；
`news_of(pid)`；`opinion(a, b)`；`mood(pid)`；`cases()`；`friends()`；`needs_of(pid)`；`state_hash()`；`event_of(hid)`。
`news_of`、`cases()` 的事件 id 是 Host 的 id（`hid`）。`set_observer(place)` 设观察者；`narr` 是累计叙述条数。

## 8. 验收与回归

* `python3 tools/npc_regress.py [--all] [--diff]`：输出与 `reference/npc_spike.py` 的 `main()` 相同格式，便于逐行比对日志。
  `python3 tools/npc_regress.py --speed [N]`：同一进程里交替跑原型与移植版各 N 次，各取最快，只报每次决策微秒与移植版/原型的比值（写到标准错误）。
* `python3 -m unittest tests.test_npc_proto`：全部数字与哈希（基准、重跑、观察者、N1、90 日、五个种子）与日志逐行比对。
  命令行工具的基准部分默认比对；`--all` 的整份日志比对在 `TIANL_SLOW=1` 下跑（与 `proto_report` 是同一个函数）。
* `python3 -m unittest tests.test_npc_defs`（第二步）：defs 驱动的规格（引用完整性 100%、每条定义都被用到、规格只由 defs 构造、场景来自 defs、内核照常加载）；
  行为包是数据（日历键与匹配次序、栈次序、布萨）；处理器登记表（参数校验、新处理器即插即用、默认值来源）；报错清楚（缺字段、引用不存在的包、未登记的处理器、参数不合法……一次报全）；
  四个钩子（签名、调用点、默认空操作且基准哈希不变）；泛化（同一份 defs 人口 60 → 300 跑 30 日并输出各层占比与时间分配、其他人口、整套 defs 换 scope、只改 defs 里的数、命令行）；文档第 12 节不漏字段。整个文件约 4 秒。
* `python3 -m unittest tests.test_npc_spec`：defs 构造的规格常数与原型逐项相同；多种子、多规模、含脚本与迁单的逐步差分
  （轨迹、统计、事件序列、终态、好恶修正表）；**随机数键的多重集与原型逐一相同**（不多抽、不少抽、不换键），场景有四个：
  传闻脚本、N1 无人代理（举报概率）、种子 4 的 90 日（传讯认错与处分阶梯）、观察者在廊下（细节叙述）；并断言**引擎源码里的每一种抽签用途
  都至少在其中一个场景里被抽到并比对过**（用 AST 从源码读出用途，不靠手写清单）。
  还有三组“补洞”的差分，专门走基准里从不走到的分支：“反应”层（种子 34 的 N1）、裁断时辰戒律院无人能断案与当事人已迁单（首座执事全病倒）、
  **扰动差分**——在内存里把原型的模块级常数（`BASE CAPF EFF BONUS PEN NEWS_DECAY NEWS_MIN SAL NIGHT`）改掉、同时改规格对应字段，
  两边仍逐项一致（原型文件不动，改完恢复）；它把“昏沉不支”“困乏未起”、工位吃紧后的满员改选、成批的举报与处分都逼了出来。
* `python3 -m unittest tests.test_npc_engine`：Host 边界（含编号方式不同的 Host 结果逐位相同）、rng 注入、查询 API（含离开之后的 `explain`）、
  ix/pid（含 `Profile.id` 别名）、`on_person_added(pid)` 与 person_factory、Trail 缺格、观察者无关、自由时段无事可选时的散步、处分对指认人的遍历次序、
  工作板优先级、源码规矩（无 random/墙钟/内置 hash；无未命名的数值常数——规则见 2.3，且规则自带反例测试；业务词不进引擎代码）。
* `python3 -m unittest tests.test_npc_sensitivity`：**规格里的每个数都在起作用**。哈希只管“谁在哪、发生了什么事”，常数抄错或引擎悄悄不读它，
  只要没改变这两样就发现不了。这里把 `SiteSpec` 的数值字段逐个改动（每个试三种改法），在九个场景里重跑，用比哈希细得多的指纹
  （需求、想法、见闻、好恶修正项、**两两好恶的实际值**、案卷、统计、传闻曲线、层号……）比对。九个场景分两类：
  五个**原型世界**（N1 无人代理、传闻脚本、90 日、种子 4 的 90 日、种子 34 的 N1），和六个**专门场景**——先把规格换成一个更挤、更累、更记仇的世界，再在这个世界上逐个改字段
  （`tight`：工位稀缺、浴室井台没登记容量、功课挪到未时让申时空出来、夜里更易起念；`weary`：困饿孤的消耗加重；`grudge`：好恶放大、处分阶梯连着杖责；
  `emit`：不跑世界，直接发一遍每种事件看见闻强度；`seasonal`：四个季节各加一个卯时的包、十二个月各跑一日——日子不连续，轨迹允许缺格；`lowR`：种子 5 的开局里有人的刚正被夹在下限，跑 N1）。
  专门场景只换规格（或种子）、不改引擎，所以“改一个数、世界就变”在这里仍只说明引擎读了这个数。（场景总数因此是 11 个。）
  默认验两件事：手挑的十个关键数字（举报概率、认错、立案过期、起念、传闻、清点、怠工、工友闲谈……）；原先碰不到的 23 个字段（十个，加季节表的 12 个月份，加刚正的下限）各在专门场景里改一次、重跑一次。
  `TIANL_SLOW=1` 对全部数值字段做普查（多进程，约 1.5 分钟）：第一步是 345 个字段、**343 个活着、2 个被 `validate()` 拒绝（`meal_slots`）、0 个无可见效果**；
  **第二步（defs 驱动后，规格多了各行为包的参数、季节表等字段）：第一次是 409 个字段：367 个活着、29 个被规格自检拒绝、13 个无可见效果、0 个崩；第二次修订（加了 `seasonal`、`lowR`）后是 409 个字段：380 个活着、29 个被规格自检拒绝、0 个无可见效果、0 个崩**。
  原先那 13 个无可见效果的是 12 个季节表项（`seasons.<季>.<i>`：原型场景没有包用季节，且 30 日只走到正月）与 `traits.lo.R`（原型这 60 人里没人的刚正低到被夹到下限）：前者由 `seasonal` 显形（把月份改成 13 − 月，这个月就不再属于原来的季节，当月卯时课变回早课），
  后者由 `lowR` 显形（改成 22 才有可见差别；改成 6 或 2 仍看不出，因为被夹到下限的那几个人没轮到举报与认错的场面——这只说明引擎读了这个数）。`when.season` 的行为另由 `tests/test_npc_defs.py` 的 `CalendarKeys` 验证。
  只用五个原型世界时，有 23 个字段是死的（十个：`capacity.zen cap_default library.slots.2 needs.eff.sick.e opinion.lo opinion.hi thoughts.flogged.cap
  thoughts.warned_bed.cap salience.REPORT salience.BED_EMPTY`：容量不吃紧、好恶碰不到上下限、举报没有见证人……；加十二个季节表项，加 `traits.lo.R`）；这份清单与每条原因写在测试的 `PROTOTYPE_DEAD` 里，
  慢测试断言“在原型世界里它们确实死、加上专门场景后确实活”，清单变长变短都要改测试，不许悄悄放过。
  “活着”只说明引擎读了这个数，不说明数值合理；专门场景是人为造的世界，普查仍是有限场景下的结论。`UNREACHED`（加上专门场景后仍看不出变化的字段）第一步是空的，第二步第一次有 13 个，现在又是空的——以后再出现，要么修，要么写在那里并说明为什么。
* `python3 -m unittest tests.test_npc_engine.DefensiveBranches`：三处基准世界与所有对照场景都走不到的防御分支，直接造世界走一遍
  （原型这几处要么 `IndexError` 要么不可达，没法逐项比对，所以断言的是行为合理、不崩、不越界）：自由时段能选的广告都满员 → 去廊下散步
  （`freechoice` 末行；练武场容量 2 与 0 各一个世界，断言“坐满之后别人散步”“占用从不超过容量”“`free_none` 仍是 0”）；没有藏主 → 藏经阁不开（`handlers.lib_open`，
  对照有藏主的世界自由时段有人读经；藏主病了也不开）；清众为空 → 无人值守山门（`engine.guards`），以及反过来只有清众、没有任何岗位的寺也能跑。
  这三条各自用“把那一行改坏、测试变红”验证过（做法：临时改源码、跑、还原）。
* 速度（不是通过线）：见 `tools/npc_regress.py` 的“每次决策 … 微秒”与 `--speed` 的比值。

**已知的验证局限**（如实记在这里，别当成已验证）：
* 对照原型的差分只覆盖原型走得到的分支。几组补洞差分把基准里不生效的分支大多补上了；剩下三处防御性分支（自由时段候选全满、没有藏主、没有清众）
  原型本身走不到或会崩，没有可比对的原型输出，只有上面 `DefensiveBranches` 的直接测试（行为合理，不是“与原型一致”）。
  另有一处是刻意偏离：自由时段没有任何正分广告时，原型 `IndexError`，移植版散步（第 9 节第 12 条）。
* `SiteSpec.validate()` 查的是引用完整性与几处硬约束，不查数值是否“合理”（比如把 `phys.faint_e` 设成 200 它也放行）。
* 普查用的指纹与场景是有限的，且专门场景是人为造的：“没有可见效果”只说明在这些场景里没有，换一个世界可能有；“有可见效果”只说明引擎读了这个数。

## 9. 与原型的刻意差异与已知限制

数字、哈希、轨迹、事件序列、终态与原型逐项相同；下面是**实现上**不同、但对结果没有影响（或只在原型没覆盖的情形下有影响）的地方：

1. **“从未”的哨兵**：`ill / conf / kneel / duty_day / lazy_day` 初值是 `NEVER`（很小的负数），原型是 0。
   原型的日子从 1 起，两者等价；集成世界第 0 日就开跑时，原型的写法会让所有人第 0 日“卧病”。`Case.rep` 同理用 `None`。
2. **好恶底数现算**，不预存 n×n 矩阵（3000 人要 9M 项）。表达式与原型逐字相同，所以浮点结果逐位相同。
3. **事件有两个 id**：引擎流水号（`EvRec.id`，见闻、案卷、随机数键用）与 Host 给的 `hid`（只在边界出现）。原型只有列表下标，
   `StandaloneHost` 从 0 顺序编号，所以三者恒等，哈希与原型一致；换一个编号方式不同的 Host 结果也逐位相同（有测试）。
4. **单巡逻者假设**：同一时辰若有两位僧值同时巡寮，只有最后一位的“所巡之处”生效（原型同）。基准里同一时辰至多一人巡寮。
5. **布萨按模拟日**：`uposatha.by='day'` 是原型口径（只有模拟第 1、15 日）；真正按历法每月初一十五要用 `by='dom'`（已实现并有测试）。
6. **轨迹全存内存**（每决定 8 字节）。300 僧一年约 1.3M 次决定、约 10MB；更长的世界由 `persist` 每日落盘后截断（C 段后续）。
   轨迹允许缺格（见 2.4），所以将来“暂离再回”“精度分档”不需要改 `Trail`。
7. **迁单之后**：该人当日（裁断时辰）之后不再有决定（原型同），`where()` 为 None；`explain()` 说明已离寺及缘由。
   做日报、控制台时要用 `explain()` 而不是把 None 当“不明”。
8. **速度**：移植版每次决策比原型慢约 1.1–1.2 倍（换来规格化与可查询的轨迹；`python3 tools/npc_regress.py --speed 7` 同一进程交替跑、取最快，
   最近一次是 4.91 对 5.70 微秒，比值 1.16）。**绝对微秒数随机器与负载变**（别的机器上基准每次决策可能是 4 到 7 微秒，
   300 僧 360 日的慢测试也会是 5 到 7 微秒），文档里不再写本机的绝对数，只有比值大致可比。速度只记录，不是通过线。
   （优化过三处，都不改语义：决定驻留打包值、统计批量累加、需求增量预先摊开。）
9. **心情只实现第一道线**（低于 35 怠工概率加成）；第二、三道线留给 C7（`life.py`）。
10. **性别、辈分、师承、本事、志向**等档案字段本步没有：原型没有，计划 5.1 的其余字段由后续步骤随 defs 加入。
11. **处分时对指认人按 ix 升序**（`norms.sanction`）：原型遍历的是 `set`，次序是 CPython 的实现细节（`{3, 8, 17, 42}` 遍历成 8、17、42、3）。
    移植版 `sorted()` 之后遍历（ARCHITECTURE 第 0 条第 2 点：遍历 set 前须排序）。每个指认人对应 `mods` 里不同的键，
    所以键集合、每个键下的列表、哈希、事件全部与原型相同；**只有 `Opinions.mods` 这个字典的键插入次序可能与原型不同**
    （无人按次序读它：`opinion` 按键取值，`expire` 保序重建）。`test_npc_spec` 里 `r.mods == eng.opinions.mods` 是字典相等，对次序不敏感；
    次序本身由 `tests.test_npc_engine.SanctionOrder` 钉住。
12. **自由时段没有任何得分为正的广告时散步**（`freechoice.py`）：原型此处 `top[0]` 抛 `IndexError`（设施都没开，或各项增量都不为正）。
    移植版不抽签，直接去 `free.stroll_*` 并记统计 `free_none`。原型世界里这条从不触发（基准 `free_none` = 0，有测试），
    所以不影响任何已有数字、抽签键与哈希；它只是让“换了世界的规格”不致崩溃。`SiteSpec.validate()` 另要求 `ads` 非空、`free.top_k >= 1`。
13. **工作板 `JobSpec.prio` 是真字段**：认领次序按 `prio` 升序，同级保持规格里的次序（`sorted` 稳定）。原型的板本来就是按 1–5 排好的列表、
    不读这个数；基准的规格已按升序排，所以次序与原型相同。移植版让它真的起作用，是为了让“改一个数”总有一个出处与一个后果
    （数值普查发现它原先只是摆设）。

14. **场所短码是随机数键与哈希的一部分**：`proto60_spec()` 的场所钥匙是原型的短码（`hall kit ref zen dorm1 clo……`）。巡寮抽签的键是
    `(种子, 'roam', 日, 时辰, 场所码)`（`stack.duty`），每个决定的哈希行是 `日,时辰,ix,场所码,活动;`（`engine.run_slot`），所以场所码一变，
    随机序列与基线哈希 `e8f8209eeb8ca94a` 都跟着变。显示名（`places` 的值）不参与，随便改（有测试）。ARCHITECTURE 第 3 节与 DECISIONS 第二节规定的运行时场所钥匙是
    defs 的 `code`（如 `SH_HALL`），与这里不是一回事；做法见第 10 节“场所钥匙”。
    **第二步的做法**：defs 的 `place` 有 `code` 字段（运行时钥匙），原型场景的 defs 把 `code` 写成原型短码，所以基线 `e8f8209eeb8ca94a` 原样有效（第 10 节路径 ① 的 defs 版）；
    改 `code` 就是另一个世界（有测试）。换成内核的 `SH_*` 钥匙要另立基线（集成步骤）。整套 defs 换 scope（`proto60` → 别的名字）不改任何结果。

15. **没被引用的定义是错误**（第二步）：同 scope 里的想法、修正项、处分阶梯、没列进栈的包，只要没被任何地方引用就报错（多半是漏了引用）；
    场所、设施、交互、岗位、差事、事件、性格本来就是表，每条都会被取用，不查（第 12.10 节）。
16. **传闻脚本的时辰与说明文字没有缺省**（第二步）：`Script(gossip=…)` 必须同时给 `gossip_slot`（`gossip_script()` 从场景的 `gossip.slot` 取）；第一步代码里的 `GOSSIP_SLOT = 1` 是原型场景的数，已删。
17. **`cast`（要角）超出清众人数时略过**（第二步）：人口等于编制、清众为空的寺也能跑（`ProtoRun(n=28)`）。

### 按计划留给后续步骤的（本步不做，不是遗漏）

这几件事在任务书与 ARCHITECTURE 里明确写了“本步不做”，并且各自有接入点；做它们不应改引擎的主干，但会改哈希基线的要重做基线：

* ~~defs 驱动~~：**第二步已完成**（第 12 节）。行为包的判定先后、谁、何时、做什么、条件判断的处理器都是数据，`stack.py` 里没有原型的层次序。
* **其余七种事件**（`CASE_OPENED CONFESS SUMMON ANNOUNCE ILL RECOVER CHAT`，ARCHITECTURE 6.2：“第一步只发其中七种”）：见第 6 节。
  引擎一发就会改流水号与事件日志、改写基线，所以只能在集成步骤一起做并重立基线。
* **life / lod / controller / persist**：四个钩子已在 `engine.py` 里预留（第 13 节），模块是空壳 / 最小实现（带 docstring，列了要做什么）。C7、C8、C9 与持久化各步只改自己的模块。
* **KernelHost**：本步只有 `StandaloneHost`；`Host.cmd` 目前只有差事结算一处调用（唯一的内核命令口，standalone 恒受理）。
  KernelHost 由集成代理写，见第 10 节。

## 10. 给后续步骤的接入说明

* **KernelHost**：实现 `Host.ev`（写 `World.ev`，返回含 `id` 的对象；id 与别的系统共用、不连续都没关系）与 `Host.cmd`
  （接 `cmd_move / cmd_take / cmd_put…`），`seed` 取世界种子，`rng` 用 `tianl.core.rnd`。引擎对外只有这两个口。
  再给 `NpcEngine` 一个 `person_factory(pid) -> PersonSpec`，内核的 `on_person_added(pid)` 就能直接转给 `engine.on_person_added(pid)`。
* **defs 驱动**（第二步已完成，第 12 节）：另一处场所 = 另一个 scope 的一套 defs（12.9 的清单），引擎代码不用动；新的条件判断写成处理器并登记（12.6），不改 `stack.py` / `engine.py`。
* **场所钥匙**（defs 驱动步骤必读，第 9 节第 14 条）：规格里的场所钥匙既出现在轨迹里，也进随机数键与哈希行。defs 驱动后运行时钥匙是 defs 的 `code`，
  不是原型短码，所以原型场景的基线有三条路：
  ① **原型场景沿用短码**（第二步采用：原型场景的 defs 把 `place.code` 写成原型短码，基线 `e8f8209eeb8ca94a` 原样有效；接内核的世界用 `SH_*` 钥匙，是另一套世界、另一份基线）；
  ② **加映射**：场景给一个“钥匙 → 随机键与哈希里用的名字”的映射，引擎在写随机键与哈希行时过一遍（要改 `stack.duty` 的巡寮抽签与 `run_slot` 的哈希行两处；映射为恒等时与现在逐位相同）；
  ③ **重立基线**：直接换成 defs 钥匙，按下一条的规矩更新 `tests/test_npc_proto.py` 里所有哈希并写明原因。
  推荐 ①：原型回归保持原样，defs 驱动的世界另立数字。不论选哪条，先跑 `tests.test_npc_engine.PlaceCodesAreKeys`，它会告诉你这两处是不是真的动了。
* **哈希基线**：任何改动随机键、引擎事件流水号（含多发事件）、决定次序的修改都会改变 `e8f8209eeb8ca94a`。要改，先在本文第 4 节改次序，
  再更新 `tests/test_npc_proto.py` 里的基线并在报告里写明原因；不得为了过测试改基线。
* **新人与离开**：`add_person` 只追加 ix；`on_person_removed(pid, why)` 只标 `gone` 与 `gone_why`，不删档案（事件与见闻还指着它）。
* **持久化**：见 `persist.py` 的 docstring，列了恢复所需的全部状态（现在要加上：事件流水号与 hid 的对应、轨迹的 `nxt`）。

## 11. 验收结果（第一步；第二步见本节末尾的第二张表。原样数字见 `python3 tools/npc_regress.py --all --diff`）

| 项 | 结果 |
| --- | --- |
| 基准哈希（rnd_b2、种子 20261110、gossip 脚本） | `e8f8209eeb8ca94a` |
| 到课 / 偷食 / 举报 / 处分 / 缺课 / 怠工 / 半餐 / 好友 / 不睦 / 迁单 | 0.993 / 7（被见 1）/ 1 / 1 / 24 / 9 比 24 / 0 比 60 / 35 / 1 / 0 |
| 决策数；差事；闲谈；传话 | 21600；870/870；625 次；156 次 |
| 重跑哈希；观察者在廊下 | 一致；一致且多生成 860 条叙述 |
| N1 无人代理 / 监院派人代理 | `49b736e95bc98576` / `7ea5fd293c81e755` |
| 90 日 | `776dafc4d1ba0e4b` |
| 种子 1–5 | `8042175f53c5ed64 adb39d7cbbaa4ef0 3693cd1af44172e5 8af473c0a39bc539 c76430933afccfb0` |
| 与日志逐行比对 | 55 行全部一致（耗时行只记录） |
| 抽签用途 | 引擎源码里读出 21 种（16 种判定 + 5 项性格），四个场景里全部抽到过，键的多重集与原型逐一相同 |
| 对原型没走到的分支 | “反应”层、戒律院无人断案、当事人已迁单、昏沉不支、困乏未起、工位吃紧：与原型逐项一致（见第 8 节） |
| 数值普查（`TIANL_SLOW=1`，第一步） | 345 个数值字段：343 个活着、2 个受校验、0 个无可见效果（九个场景；只用五个原型世界时有十个是死的，清单与原因见 `tests/test_npc_sensitivity.py` 的 `PROTOTYPE_DEAD`）；第二步（defs 驱动）见下表 |
| 防御性分支 | 自由时段候选全满、没有藏主、没有清众：`DefensiveBranches` 直接构造世界断言（改坏源码会红） |
| 场所短码 | 进入随机键与基线哈希：`PlaceCodesAreKeys` 钉住（第 9 节第 14 条、第 10 节） |

### 11.1 第二步（defs 驱动）验收结果

| 项 | 结果 |
| --- | --- |
| 第一步的全部哈希与数字（基准 `e8f8209eeb8ca94a`、重跑、观察者、N1 两组、90 日、五个种子、55 行日志） | 在 defs 驱动下**一字不差**：`python3 tools/npc_regress.py --all --diff` → `与日志逐行比对：一致（共 55 行，不一致 0 处）`；`tests.test_npc_proto` 全绿 |
| `Defs.load()` 引用完整性 | 100%：整棵 defs 树 233 条定义、300 条引用全部可解析（第二次修订加了 `rule:schedule.calendar` 一条）；原型场景 153 条定义每条都被规格用到 |
| 原型场景完全由 defs 描述 | `SiteSpec.from_defs` / `ScenarioSpec.from_defs`；代码里只有 `defsload.py` 构造 `SiteSpec` / `ScenarioSpec`（AST 测试） |
| 代码里没有原型场景的魔数 | `tests.test_npc_engine.SourceRules` 扫 `tianl/npc` 全部模块（含 `spec.py` `scenarios.py`）：只许具名常量与结构用的 0/1/2/3，`handlers.py` 另许 `Param` 的默认值 |
| 行为包是数据 | 36 个包 + 13 个处理器（`tempted lazy kitchen_duty proxy_cook patrol_duty gate_duty errand slack court_report physiology forced penalty free`）+ 2 个准入门；日历键匹配次序“具体日子 > 天气 > 季节 > 默认”有测试 |
| 钩子 | 四个（`life.pulse` `controller.decide`〔`Controller.choose`〕`lod.observe` `persist.flush`）：存在、签名与调用点有测试、默认空操作且基准哈希不变 |
| 泛化 (a)：同一份 defs 人口 60 → 300 跑 30 日 | 决策数 108000，预约越界 0，每个决定都说得清；各层占比与每日时辰分配见 12.9 与 `python3 -m tianl.npc.report --scale 300 --days 30` |
| 泛化 (b)：缺字段 / 引用不存在的包 / 未登记的处理器 / 参数不合法 | 逐条写明哪条定义的哪个字段，一次报全（12.3 样例；`tests.test_npc_defs.ErrorReporting` 13 项） |
| 数值普查（`TIANL_SLOW=1`，defs 驱动后） | 409 个数值字段：第一次 367 活、29 受校验、13 无可见效果（12 个季节表项 + `traits.lo.R`）、0 崩；第二次修订（加专门场景 `seasonal`、`lowR`）后 **380 活、29 受校验、0 无可见效果、0 崩**（`UNREACHED` 现在是空的） |
| 测试 | 默认整套 `python3 -m unittest discover -s tests -t .`：368 个测试绿（24 个慢测试跳过），本机 53 到 54 秒（离 60 秒线只有几秒，见开头的说明）；`TIANL_SLOW=1 python3 -m unittest tests.test_npc_proto tests.test_npc_spec tests.test_npc_engine tests.test_npc_defs tests.test_npc_sensitivity`：npc **五个测试文件** 171 个测试全绿（14 + 15 + 66 + 65 + 11，约 149 秒；`test_npc_support` 是夹具，没有测试）。内核的慢测试不在这条里 |
| 第二次修订（第二位独立验证者之后） | 历法随 scope 走（`rule:schedule.calendar`，`tests.test_npc_defs.ScopeCalendar` 7 个测试：换历法后节日键跟着变、全局默认被换掉也不受影响、节日名写错 / 月与月内日越界 / 历法字段缺失与不存在都报可读的错、源码里没有模块引入全局 `cal`）；数值普查 13 个“无可见效果”清零（见上行）；文档数字以实跑为准 |

## 12 defs 驱动（C 段第二步）：字段说明、处理器与“为另一处场所写一套 defs”

第二步把第一步的 Python 数据类规格换成 **defs 驱动**：原型场景 `scenario:proto60` 完全由 `defs/*/proto60*.toml` 描述，
`SiteSpec.from_defs()` 读它、校验它、拼成引擎认的规格；基准哈希与第一步的全部数字一字不差（第 11 节）。
本节的字段表由代码生成（`python3 -m tianl.npc.defsload` 重新生成），`tests.test_npc_defs.DocsInSync` 逐表逐行核对本节的字段表与代码生成的完全一致（说明文字、类型、默认值改了而文档没跟着改，都会红），并核对处理器、准入门、钩子都有说明。

### 12.1 总览

* `SiteSpec.from_defs(defs, 'scenario:proto60:main')`（实现在 `defsload.build_site`）：编号的中间一段是 **scope**（这里是 `proto60`），
  同 scope 的全部定义拼成一份不可变的 `SiteSpec`；`ScenarioSpec.from_defs(...)` 读场景本身（种子、人口、要角、脚本与实验、报表用词）。
  `scenarios.proto60_spec()` / `proto60_scenario()` 是 `Defs.load` 一次后缓存的这两样（同一进程里是同一个对象）；换一座寺就换一个 scope，引擎一行不改。
* **引擎里没有原型场景的数**。`tests.test_npc_engine.SourceRules` 用 AST 扫 `tianl/npc` 里的每个模块（含 `spec.py`、`scenarios.py`、`defsload.py`）：
  数值字面量只能是模块级的具名常量（UPPER_CASE = …）、结构用的 0/1/2/3（下标、计数、初值、±1 偏移），以及 `handlers.py` 里 `Param(…)` 的默认值与取值范围。
  最后一项是代码里唯一允许的“参数默认值”；原型场景不靠它（每个值 defs 里都写了，`tests.test_npc_defs.HandlerRegistry.test_defaults_come_from_the_handler_table_not_from_defs` 验证默认值只在 defs 不写时才起作用）。
  具名常量里只有“数据格式的元数”（几项一组）、结构性标识（层标签、活动代码、需求键、性格键）与单位量纲（见 `spec.py` 文件头）。
* 原型场景的八个文件（共 153 条定义，另有 3 个 `_abstract` 父包；`kernel = false` 的场所定义内核不读；内核按 scope 过滤，不读 proto60）：

| 文件 | 内容 |
| --- | --- |
| `defs/space/proto60.toml` | `place` 21 个场所（`code` 沿用原型短码，见 12.9 与第 9 节第 14 条） |
| `defs/facility/proto60.toml` | `facility` 7 处设施（工位数）、`interaction` 19 种活动（交互） |
| `defs/post/proto60.toml` | `post` 14 个岗位、`job` 8 件差事、`trait` 5 项性格刻度，`rule`：`board` `layers` `schedule` `needs` `illness` |
| `defs/post/proto60_packages.toml` | `package` 36 个行为包（另有 3 个 `_abstract` 父包）与 `rule:stack`（包的判定先后） |
| `defs/org/proto60.toml` | `org` 5 个：`main`（寺院整体）、`kitchen` `patrol` `gate` `court`（四个部门） |
| `defs/norm/proto60.toml` | `ladder` 1 条处分阶梯、`norm` 4 条规范：`theft` `absence` `slack` `bed` |
| `defs/knowledge/proto60.toml` | `thought` 8 个想法、`modifier` 4 个好恶修正项、`event` 7 种事件，`rule`：`opinion` `chat` `rumor` `mood` `free` |
| `defs/scenario/proto60.toml` | `scenario` 3 条：`main`（种子、人口、要角、报表用词）、`gossip`（传闻实验）、`n1`（厨房减员实验） |

* **哪些目录内核会加载**（`kernel.spec.KERNEL_CATEGORIES`）：`calendar space economy org post item scenario`。这些目录里的文件（含 proto60 的）
  只许引用这几个目录里的定义；`facility`、`norm`、`knowledge` 三个目录内核不加载，可以引用任何 kind（所以想法、规范、设施在那里引用场所与岗位）。
  `tests.test_npc_defs.DefsDrivenSpec.test_kernel_still_loads_and_ignores_the_npc_scope` 钉住“内核照常加载、proto60 不进内核的场所表”。
* `Defs.load()` 严格加载时引用完整性 100%（整棵 defs 树 233 条定义、300 条引用全部可解析，`tests.test_npc_defs` 开头打印）。

### 12.2 键与约定

* **键一律用 ASCII，中文只放在值里**（TOML 裸键不接受中文）：需求键 `h` 饥 `e` 困 `c` 洁 `s` 群 `a` 志；性格键 `D` 精进 `S` 守戒 `G` 合群 `T` 馋 `R` 刚正（ARCHITECTURE 第 3 节）。
  性格定义的编号最后一段就是性格键（`trait:proto60:D`）；想法、修正项的编号最后一段是引擎里引用的键。
* **引用**：整串恰为已登记 kind 的编号即视为引用（`place:proto60:hall`），`Defs.load()` 查它存不存在；`from_defs` 再查它是不是该字段要求的 kind。
  特例：交互的 `station` 可写 `"$home"`（本人寮房床位，不记容量），行为包 `do.place` 同。
* **单例的角色名**：`org` / `norm` / `rule` 每种角色在一个 scope 里只有一条，角色名是 `role` 字段，没写就取编号最后一段
  （`org:proto60:kitchen` 的角色是 `kitchen`）。引擎认识的角色：`org` 的 `main kitchen patrol gate court`，`norm` 的 `theft absence slack bed`，
  `rule` 的 `stack layers schedule needs illness board opinion chat rumor mood free`，`scenario` 的 `gossip n1`（`main` 是场景本身）。
* **次序**：次序敏感的定义带 `order`（岗位表的次序决定名册——谁排第几、法名与寮房；差事板同级差事的认领先后；自由时段广告平分时先出现的先）；
  行为包的判定先后由 `rule:stack` 的 `packages` 列表决定；同 scope 的包不列进去就报错（不在栈里永远不会生效）。
* 时辰是 0–11（子 0 … 亥 11）；`slot` 可写一个数或一组数；`when.day` 是模拟日序号，`day_of_month` 是历法的月内日（1–30）。
* **历法是这处场所的数据**：`rule:<scope>:schedule` 的 `calendar` 字段引用一条 `calendar` 定义（与内核共用同一种定义：`festivals`、`retreat`、`wheat_doy`、`millet_doy`，`year` 只能是 360），
  `when` 里的 `festival`、`month`、`day_of_month` 与 `rule:schedule.seasons` 的月份都按它算，节日名写错（不在这份历法里）、月不在 1–12、月内日不在 1–30 都在读 defs 时报错。
  原型场景就是少林寺，引用的是 `calendar:shaolin:main`；丐帮分舵或庄园写自己的 calendar 定义并改这一行，**引擎不读 `tianl.core.cal()` 的全局默认历法**（`tests.test_npc_defs.ScopeCalendar` 把全局默认换掉，结果一字不差）。
* `parent` 继承与 `_abstract = true`（只供继承）沿用 ARCHITECTURE 第 4 节：`_forced`、`_kitchen_hours`、`_tempted` 三个抽象包把共用的层、时辰、参数写一处，
  子包只写差别（字典逐层合并——子包 `params` 里写的键盖过父包的键、没写的沿用；列表与标量整体替换）。

### 12.3 加载、校验与报错

`from_defs` 读字段时顺手校验，**把这一阶段的所有问题收集完一起抛 `SpecError`**（`.problems` 是问题列表，每条写明哪条定义的哪个字段），不是撞上第一个就停：

* 缺字段、字段类型不对、未知字段（多半是拼错）、引用不存在的定义、引用了 kind 不对的定义；
* 处理器 / 准入门未登记（报错里列出已登记的名字）、参数缺失 / 未知 / 类型不对 / 越界（按登记表里的 `Param` 校验）；
* **行为包自身的问题在这一阶段就查全**：层标签没登记、`who` 的岗位、`when` 的时辰 / 时段 / 季节、`do` 的场所与活动、`claim` 与 `overflow` 配套、处理器只能带哪些层、
  处理器用到的活动、巡寮包的 `who`——与 `SiteSpec.validate()` 用**同一份**校验函数（`handlers.package_shape_problems` / `package_handler_problems` / `ad_gate_problems`），
  所以“缺字段 + 处理器写错 + 参数类型不对 + 时辰不对 + 活动不存在”同时出现，一次全报（`tests.test_npc_defs.ErrorReporting.test_structural_and_value_mistakes_are_reported_together`）；
  某张表自己读不干净时（比如场所表里有错），依赖它的引用检查跳过，不制造连带的假问题；
* 同 scope 里**没被任何地方引用或使用**的定义（想法、修正项、处分阶梯、没列进栈的包等；多半是漏了引用或拼错了 role）；
* 缺角色（`缺少 org 的角色 'gate'（编号形如 org:proto60:gate，或写 role = "gate"）`）、角色重复。

**一次报全的范围，如实写明**：只在这一阶段内成立。这一阶段**没有问题**之后，才进入第二阶段 `SiteSpec.validate()`（引擎构造时也会调，不通过拒绝开跑），
它再查规格内部的交叉引用：场所、岗位、想法键、修正项键、需求键覆盖、活动、层标签、值守包相邻、栈里有 `free` 兜底、规范与交互的对应……（包与准入门的那部分上面已经提前做了；其余只在第二阶段）。
所以修完第一阶段的问题之后，仍可能冒出第二阶段才查得出的问题——不会有“修了一个又出一个包的类型错”这种情况，但交叉引用类的问题要分两次才报全。

真实报错样例（`tests.test_npc_defs.ErrorReporting` 里每一条都有对应的测试）：

```
package:proto60:penalty：缺少字段 layer：层标签（rule:layers 登记过的）
rule:proto60:stack: 字段 packages 引用了不存在的 package:proto60:nope                      （Defs.load 严格加载时的 DefsError）
package:proto60:tempted_night：处理器 'tempt_ed' 未登记（已登记：court_report、errand、forced、free、gate_duty、kitchen_duty、lazy、patrol_duty、penalty、physiology、proxy_cook、slack、tempted）
package:proto60:tempted_night 的处理器 tempted：缺少参数 th_base（起念的饥门槛底数）
包 package:proto60:tempted_night（处理器 tempted）：参数 k 应是 float，得到 'high'
package:proto60:penalty：未知字段 lyaer（拼错了？）
包 package:proto60:morning_chant.do.act：活动 'fly' 没有对应的交互
interaction:proto60:zazen: 字段 station 引用了不存在的 facility:proto60:zenn                  （DefsError）
thought:proto60:unused：没有被任何地方引用或使用（漏了引用？拼错了 role？）
```

### 12.4 字段表

下面每张表是一种 kind（或一个角色）的字段；“必填 / 默认”一栏：必填 = 缺了报错，缺省 `x` = 不写取 x，可缺省 = 不写就没有这个特性。
`.` 表示子表（`ad.pref.coef` 是 `ad` 表里 `pref` 表里的 `coef`），`[]` 表示表的列表。

#### 12.4.1 场所：`defs/space/proto60.toml`

场所 `place`：`code` 是运行时钥匙（轨迹、随机数键、哈希、事件日志里的场所一律用它），`name` 是显示名（不进哈希，随便改）。
原型场景沿用原型短码（`hall kit dorm1`……）：短码进巡寮抽签的键与基线哈希行，所以改 `code` 就是另一个世界。

**`place`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `code` | str | 必填 | 运行时钥匙；原型场景沿用原型短码（它进随机数键与基线哈希） |
| `name` | str | 必填 | 显示名（不进哈希） |


#### 12.4.2 设施与交互：`defs/facility/proto60.toml`

设施 `facility`：场所里的工位——同一时辰最多几人占用（占位即预约）。交互 `interaction`：**“能做什么”写在设施上，不写在人身上**（计划 4.3）；
一种活动一条，字段固定：所需工位（`station`）、时长（`duration`）、需求增减（`effects`）、所需物（`inputs`）与产出物（`outputs`）、准入条件（`admission`）、
触犯的规范（`norm`）；另有统计类别（`category`）、功课加成（`track_bonus`）、做了就得的想法（`thought`）、克制没做的想法（`refrain_thought`）、自由时段的广告（`ad`）。
没有 `ad` 的交互不进自由时段，只能由行为包（声明式的 `do.act` 或处理器）指派。

**`facility`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `place` | 引用 place | 必填 | 设施所在的场所 |
| `stations` | int | 可缺省 | 工位数：同一时辰最多几人占用（占位即预约）；不写 = 不限 |

**`interaction`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `act` | str | 必填 | 活动代码（轨迹与哈希里的活动名） |
| `ad` | 表 | 可缺省 | 自由时段的广告（Sims）：label、terms 需求项、scale 性格系数、pref 性格偏好 |
| `ad.label` | str | 必填 | 广告名（自由时段的原因） |
| `ad.pref` | 表 | 可缺省 | 性格偏好：kind = trait（按性格）/ track（本方向才加）/ idle（越不精进越想歇），trait、coef、track |
| `ad.pref.coef` | num | 必填 | 系数 |
| `ad.pref.kind` | str | 必填 | trait / track / idle |
| `ad.pref.track` | str | 可缺省 | 方向（kind = track 时） |
| `ad.pref.trait` | str | 必填 | 性格键 |
| `ad.scale` | 表 | 可缺省 | 性格系数：把需求项之和再乘 (off + 性格/div)；trait 性格键 |
| `ad.scale.div` | num | 必填 | 刻度 |
| `ad.scale.off` | num | 必填 | 偏移 |
| `ad.scale.trait` | str | 必填 | 性格键 |
| `ad.terms` | [表] | 必填 | 需求项：need 需求键、w 增量、by_track 按方向区分的增量 |
| `ad.terms[].by_track` | [表] | 可缺省 | 按方向区分的增量：[{ track, w }] |
| `ad.terms[].by_track[].track` | str | 必填 | 修行方向 |
| `ad.terms[].by_track[].w` | num | 必填 | 该方向的增量 |
| `ad.terms[].need` | str | 必填 | 需求键 h e c s a |
| `ad.terms[].w` | num | 必填 | 增量 |
| `admission` | 表 | 可缺省 | 准入条件：gate = "<准入门名>"，其余键是该门的参数（只对有 ad 的交互起作用） |
| `admission.gate` | str | 必填 | 准入门名（handlers.GATES 登记的） |
| `category` | str | 必填 | 时间分配类别（统计口径） |
| `duration` | int | 缺省 `1` | 时长（时辰）；目前只接受 1（见 SiteSpec.validate） |
| `effects` | {键: 数} | 可缺省 | 需求增减（每时辰）：{h,e,c,s,a: 数} |
| `inputs` | {键: 数} | 可缺省 | 所需物：每次服务耗的物 |
| `norm` | 引用 norm | 可缺省 | 触犯的规范：谁做了这件事，就触犯它（对旁人是偷食，对饭头的“厨务”是工作——后者是另一种活动） |
| `outputs` | {键: 数} | 可缺省 | 产出物：做一次得的物 |
| `refrain_thought` | 引用 thought | 可缺省 | 有理由做、却克制没做时得到的想法（饿极而不偷：忍饥） |
| `station` | 引用 facility \| "$home" | 可缺省 | 所需工位：facility 编号；"$home" = 本人寮房床位；不写 = 不占工位 |
| `thought` | 引用 thought | 可缺省 | 做了这件事就得到的想法 |
| `track_bonus` | 表 | 可缺省 | 本方向做此事的志增量：track 方向、own 本方向、other 其余 |
| `track_bonus.other` | num | 必填 | 其余的志增量 |
| `track_bonus.own` | num | 必填 | 本方向的志增量 |
| `track_bonus.track` | str | 必填 | 修行方向 |


#### 12.4.3 岗位、差事、性格与站点规则：`defs/post/proto60.toml`

岗位 `post`（人岗分离：岗位是表上的一行，人是被任命的；日常时段不在这里，在第 8 层的行为包里）、差事 `job`（工作板上的活；认领即预约）、
性格刻度 `trait`（开局按 N(mean, sd) 生成再夹到 [lo, hi]）；`rule` 角色：`layers`（层标签与计划 6.1 的层号）、`schedule`（夜间、轮转、斋食时辰、季节、历法）、
`needs`（五项需求的站点级参数）、`illness`、`board`（工作板的站点参数）。

**`post`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `count` | int | 必填 | 编制 |
| `disc` | bool | 缺省 `False` | 纪律执事：当面禀告的对象、见证必报 |
| `kitchen` | bool | 缺省 `False` | 厨房职事 |
| `name` | str | 必填 | 岗位名 |
| `prefix` | str | 必填 | 法名前缀（建人用） |

**`job`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `count` | int | 必填 | 当日需要几人 |
| `name` | str | 必填 | 差事名 |
| `outputs` | {键: 数} | 可缺省 | 产出物：物 -> 每名完成者入账的量 |
| `place` | 引用 place | 必填 | 干活的场所 |
| `prio` | int | 必填 | 优先级：数字小的先被认领 |

**`trait`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `hi` | num | 必填 | 取值上限 |
| `lo` | num | 必填 | 取值下限 |
| `mean` | num | 必填 | 开局均值（0–100） |
| `name` | str | 必填 | 中文名（说明用） |
| `office_bonus` | num | 缺省 `0` | 有岗位者的均值加成 |
| `sd` | num | 必填 | 开局标准差 |

**`rule:board`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `work_chat_p` | num | 必填 | 同一件差事里两两搭伴的工友闲谈的概率 |

**`rule:layers`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `ranks` | [表] | 必填 | 层标签与计划 6.1 的层号：[{ name, rank }]（越轨与怠工不是一层包，记 0） |
| `ranks[].name` | str | 必填 | 层标签 |
| `ranks[].rank` | int | 必填 | 层号 |

**`rule:schedule`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `calendar` | 引用 calendar | 必填 | 这处场所的历法（calendar 定义的编号）：行为包 when 里的 festival、month、day_of_month、season 键都按它 |
| `meal_slots` | [int] | 必填 | 斋食时辰 |
| `night` | [int] | 必填 | 夜间时辰（子 0 … 亥 11） |
| `rotate` | [int] | 必填 | [日系数, 时辰系数]：各人决定的起点按 (日×a + 时辰×b) % 人数 轮转 |
| `seasons` | [表] | 必填 | 季节与月份：[{ name, months }]（行为包 when.season 用） |
| `seasons[].months` | [int] | 必填 | 这个季节包括哪几个月 |
| `seasons[].name` | str | 必填 | 季节名 |

**`rule:needs`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `base` | {键: 数} | 必填 | 每时辰的基础消耗 |
| `category_default` | str | 必填 | 没有登记类别的活动记入的统计类别 |
| `duty_a` | num | 必填 | 履职补的志 |
| `duty_layers` | [str] | 必填 | 这些层的决定每时辰补 duty_a 点志（履职） |
| `hunger_sleep` | num | 必填 | 睡时的饥消耗（代替 base.h） |
| `hunger_t_div` | num | 必填 | 同上的刻度 |
| `hunger_t_mid` | num | 必填 | 饥消耗随“馋”微调：1 + (T − hunger_t_mid) / hunger_t_div |
| `hungry_line` | num | 必填 | 统计线：饥低于此算饿（只用于报表） |
| `init` | {键: 数} | 必填 | 开局值：{h,e,c,s,a: 数} |
| `morning_c` | num | 必填 | 晨起补的洁 |
| `morning_slot` | int | 必填 | 晨起时辰：不睡就补 morning_c 点洁 |
| `names` | 表 | 必填 | 需求键 -> 中文名（报表） |
| `social_g` | 表 | 必填 | 群的消耗乘 (off + G/div) |
| `social_g.div` | num | 必填 | 刻度 |
| `social_g.off` | num | 必填 | 偏移 |
| `tired_line` | num | 必填 | 统计线：困低于此算乏（只用于报表） |
| `urgency_floor` | num | 必填 | 迫切度 u(x) = ((100 − x)/100)^urgency_pow + urgency_floor |
| `urgency_pow` | num | 必填 | 迫切度的指数 |

**`rule:illness`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `min_days` | int | 必填 | 病几日（最少） |
| `p` | num | 必填 | 每人每日生病的概率 |
| `span` | int | 必填 | 再加 [0, span) 日 |


#### 12.4.4 行为包：`defs/post/proto60_packages.toml`

行为包 `package` 与栈 `rule:stack` 的语义见 12.5，处理器的参数见 12.6。

**`package`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `do` | 表 | 可缺省 | 声明式：place act label [claim overflow] |
| `do.act` | str | 必填 | 活动代码（要有对应的 interaction） |
| `do.claim` | bool | 缺省 `False` | 占一个工位（满员改去 overflow.place） |
| `do.label` | str | 必填 | 原因 |
| `do.overflow` | 表 | 可缺省 | 满员时：place 改去的场所、suffix 原因后缀 |
| `do.overflow.place` | 引用 place | 必填 | 改去的场所 |
| `do.overflow.suffix` | str | 缺省 `` | 原因后缀 |
| `do.place` | 引用 place \| "$home" | 必填 | 场所：place 编号，或 "$home"（本人寮房） |
| `handler` | str | 可缺省 | 需要条件判断的包：登记过的处理器名（与 do 二选一） |
| `layer` | str | 必填 | 层标签（rule:layers 登记过的） |
| `params` | 表 | 可缺省 | 处理器的参数（见处理器的参数表） |
| `when` | 表 | 可缺省 | 何时成立：slot day day_of_month month festival weather season；不写 = 任何时候 |
| `when.day` | int \| [int] | 可缺省 | 模拟日序号（原型口径：布萨在第 1、15 日） |
| `when.day_of_month` | int \| [int] | 可缺省 | 历法的月内日（1–30） |
| `when.festival` | bool \| str \| [str] | 可缺省 | 节日：true = 任一节日，或节日名（一个或一组） |
| `when.month` | int \| [int] | 可缺省 | 月（1–12） |
| `when.period` | str \| [str] | 可缺省 | 时段名：night（夜间）/ meal（斋食时辰），取自 rule:schedule |
| `when.season` | str \| [str] | 可缺省 | 季节（rule:schedule 的 seasons 登记的） |
| `when.slot` | int \| [int] | 可缺省 | 时辰（子 0 … 亥 11） |
| `when.weather` | str \| [str] | 可缺省 | 天气（由 Host 的 weather(day) 提供；没有就永不成立） |
| `who` | 表 | 可缺省 | 谁适用：post 岗位列表 / status = common\|holder / track 方向列表；不写 = 所有人 |
| `who.post` | [引用 post] | 可缺省 | 适用的岗位（任一） |
| `who.status` | str | 可缺省 | common（无岗位的清众）\| holder（有岗位者） |
| `who.track` | [str] | 可缺省 | 适用的修行方向（任一） |

**`rule:stack`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `packages` | [引用 package] | 必填 | 行为包的判定先后：包的编号列表（自上而下第一个成立的生效） |


#### 12.4.5 组织：`defs/org/proto60.toml`

寺院整体 `org:main`（人群构成、寮房、巡寮候选）与四个部门：香积厨 `org:kitchen`、僧值巡寮 `org:patrol`、山门 `org:gate`、戒律院 `org:court`。

**`org:main`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `common_prefix` | str | 必填 | 清众的法名前缀 |
| `common_tracks` | [表] | 必填 | 清众按序分方向：[{ track, count }]（不写 count = 其余全部） |
| `common_tracks[].count` | int | 可缺省 | 人数 |
| `common_tracks[].track` | str | 必填 | 修行方向 |
| `default_stations` | int | 必填 | 没登记工位数的场所按此数算 |
| `dorms` | [引用 place] | 必填 | 寮房（有序：第 i 个人住第 i % 寮数 个）；寮房是私人场所，不记容量 |
| `groups` | [str] | 必填 | 时间分配统计的两组名称（清众，岗位者） |
| `leave_word` | str | 必填 | 人离开本处的说法：explain 写“已于第 N 日离寺（缘由）”里的“离寺” |
| `name` | str | 必填 | 名称 |
| `name_pool` | str | 必填 | 取法名用的字池（前缀 + 池中第 i 个字；超过一圈，名字后再缀池里的字，所以人口再多也不重名） |
| `office_track_cycle` | str | 必填 | 岗位者的修行方向按序号循环 |
| `roam` | [引用 place] | 必填 | 巡寮的候选场所（僧值每次从中按随机序挑几处） |

**`org:kitchen`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `dining` | 引用 place | 必填 | 斋堂：到课（过堂）人数在此统计 |
| `gain_full` | num | 必填 | 足量斋食给的饥 |
| `gain_half` | num | 必填 | 半餐给的饥 |
| `min_staff` | int | 必填 | 足量所需的在厨人手 |
| `place` | 引用 place | 必填 | 厨房 |
| `prep` | [表] | 必填 | 备斋时辰：[{ meal, prep }] |
| `prep[].meal` | int | 必填 | 斋食时辰 |
| `prep[].prep` | int | 必填 | 备斋时辰 |
| `stock_init` | {键: 数} | 必填 | 开局库存：物 -> 量（水、柴） |

**`org:patrol`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `office` | 引用 post | 必填 | 僧值：两人轮流，一人巡夜，一人日间巡寮 |

**`org:gate`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `count` | int | 必填 | 每日从清众里轮值几人 |
| `place` | 引用 place | 必填 | 门禁所在的场所 |

**`org:court`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `judge_slot` | int | 必填 | 裁断的时辰 |
| `judges` | [引用 post] | 必填 | 有资格裁断的岗位（按次序，首座优先） |
| `place` | 引用 place | 必填 | 裁断与立案的场所（法庭所在） |


#### 12.4.6 规范与处分阶梯：`defs/norm/proto60.toml`

规范 `norm`（计划 8.5）写“触犯之后怎么办”；**哪些活动触犯哪条规范，写在交互的 `norm` 字段上**（现在只有 `role = "theft"` 的越轨类规范能被交互触犯，
见 12.8）。`absence`、`slack`、`bed` 三条是引擎的三种“被发现”机制（点名、被巡寮撞见、查寮）的参数。处分阶梯 `ladder`：第 k 次受处分取第 k 级，超出取最后一级。

**`ladder`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `steps` | [表] | 必填 | 阶梯：[{ txt, kneel_days, conf_days, need_hit, thought, gone }]（第 k 次受处分取第 k 级，超出取最后一级） |
| `steps[].conf_days` | int | 缺省 `0` | 禁闭几日 |
| `steps[].gone` | bool | 缺省 `False` | 离开本处（出寺、出帮……） |
| `steps[].kneel_days` | int | 缺省 `0` | 罚跪香几日 |
| `steps[].need_hit` | {键: 数} | 可缺省 | 需求增减 |
| `steps[].thought` | 引用 thought | 可缺省 | 加给受处分者的想法 |
| `steps[].txt` | str | 必填 | 处分名 |

**`norm:theft`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `accuse_mod` | 引用 modifier | 必填 | 受罚者对指认人记的好恶修正项 |
| `announce` | 表 | 必填 | 公告：slot 时辰在 place 表堂，在场者全部得知；守戒高于 s_line 的旁观者对受罚者记 mod |
| `announce.mod` | 引用 modifier | 必填 | 旁观者记的修正项 |
| `announce.place` | 引用 place | 必填 | 表堂的场所 |
| `announce.s_line` | num | 必填 | 守戒线 |
| `announce.slot` | int | 必填 | 公告的时辰 |
| `case` | 表 | 必填 | 案卷：四个状态名、stale_days、confess_base / confess_r、via_report / via_confess |
| `case.closed` | str | 必填 | 状态：结案 |
| `case.cold` | str | 必填 | 状态：悬案 |
| `case.confess_base` | num | 必填 | 被传讯者认错的概率 = confess_base + confess_r×刚正/100 |
| `case.confess_r` | num | 必填 | 刚正的权重 |
| `case.done` | str | 必填 | 状态：已处分 |
| `case.open` | str | 必填 | 状态：在查 |
| `case.stale_days` | int | 必填 | 无人指认的案子几日后成悬案 |
| `case.via_confess` | str | 必填 | 案卷里定罪依据：凭本人认错 |
| `case.via_report` | str | 必填 | 案卷里定罪依据：凭举报 |
| `event` | 引用 event | 必填 | 触犯时发的事件（目击者得见闻，强度见 event 的 salience） |
| `inventory` | 表 | 必填 | 典座清点：slot 时辰清点，发现失窃的概率 p_find（发现即立案） |
| `inventory.p_find` | num | 必填 | 发现的概率 |
| `inventory.slot` | int | 必填 | 清点的时辰 |
| `ladder` | 引用 ladder | 必填 | 处分阶梯 |
| `name` | str | 必填 | 规范名（说明用） |
| `report` | 表 | 必填 | 见证人举报的概率 = base + r_w×刚正/100 − op_w×对当事人的好感，夹在 [lo, hi] |
| `report.base` | num | 必填 | 底数 |
| `report.hi` | num | 必填 | 上限 |
| `report.lo` | num | 必填 | 下限 |
| `report.op_w` | num | 必填 | 好感的权重 |
| `report.r_w` | num | 必填 | 刚正的权重 |
| `sanction_thought` | 引用 thought | 必填 | 每起处分都给受处分者的想法 |

**`norm:absence`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `absent_thought` | 引用 thought | 必填 | 缺课者的想法 |
| `exempt_layers` | [str] | 必填 | 这些层的人不点名 |
| `kneel_days` | int | 必填 | 就罚跪香几日 |
| `kneel_thought` | 引用 thought | 必填 | 被罚跪香者的想法 |
| `kneel_txt` | str | 必填 | 统计里的名目 |
| `limit` | int | 必填 | 缺课几次 |
| `name` | str | 必填 | 规范名（说明用） |
| `office` | 引用 post | 必填 | 点名的岗位（维那） |
| `place` | 引用 place | 必填 | 点名的场所 |
| `slots` | int \| [int] | 必填 | 点名的时辰 |
| `window` | int | 必填 | 近几日内 |

**`norm:slack`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `kneel_days` | int | 必填 | 就罚跪香几日 |
| `limit` | int | 必填 | 被撞见几次 |
| `name` | str | 必填 | 规范名（说明用） |
| `thought` | 引用 thought | 必填 | 被撞见者的想法 |
| `window` | int | 必填 | 近几日内 |

**`norm:bed`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `check_slots` | int \| [int] | 必填 | 巡夜查寮的时辰 |
| `exempt_layers` | [str] | 必填 | 这些层的人不算“夜不在寮” |
| `name` | str | 必填 | 规范名（说明用） |
| `thought` | 引用 thought | 必填 | 被记空铺者的想法 |


#### 12.4.7 想法、好恶修正项、事件与知识类站点规则：`defs/knowledge/proto60.toml`

想法 `thought`（RimWorld 式：带期限的心情加减分，同标签共用叠加上限）与好恶修正项 `modifier`（CK3 式：带期限、带叠加上限、带起因的数据 `[值, 止日, 种类]`；
`cause` 是“情”命令向玩家解释这条修正项从哪来的文字）都是引擎里引用的键；事件 `event` 给每种事件类型的目击显著度（`code` 必须是 `events.py` 登记的）；
`rule`：`opinion`（好恶底数）、`chat`（闲谈）、`rumor`（传闻衰减与转述）、`mood`（心情权重与三道线，见下）、`free`（自由时段）。

**心情三道线**（计划 9.3）：`rule:mood` 的 `lines` 写三道线 35 / 20 / 5 及各自的后果（`slack` 怠工概率加成、`avoid_group` 回避集体、`life_event` 人生事件），
`enabled` 是启用几道（自上而下）。本步与原型一致**只启用第一道**（`enabled = 1`）；`SiteSpec.validate()` 现在拒绝 `enabled` 不是 1 的规格（`spec.MOOD_LINES_ENABLED`），
第二、三道线由 C7（`life.py`）接手时一并放开这个限制。

**`thought`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `cap` | int | 必填 | 同标签最多同时几条 |
| `days` | int | 必填 | 持续几日 |
| `label` | str | 必填 | 标签：同标签共用叠加上限 |
| `value` | num | 必填 | 每条的心情增减 |

**`modifier`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `cap` | int | 必填 | 同种类最多几条（满了只续期最老的一条） |
| `cause` | str | 必填 | 起因（“情”命令向玩家说明） |
| `days` | int | 必填 | 持续几日 |
| `label` | str | 必填 | 种类：同种类共用叠加上限（不叫 kind：kind 是加载器保留字） |
| `value` | num | 必填 | 每条的好恶增减 |

**`event`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `code` | str | 必填 | 事件类型代码（tianl/npc/events.py 登记的） |
| `salience` | num | 必填 | 目击者得到的见闻强度（0 = 不产生见闻） |

**`rule:opinion`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `compat_div` | num | 必填 | 相容度 = 1 − (\|ΔD\|+\|ΔS\|+\|ΔG\|)/compat_div |
| `compat_mid` | num | 必填 | 相容度的中点 |
| `compat_w` | num | 必填 | (相容度 − compat_mid)×compat_w 进底数 |
| `foe_line` | num | 必填 | 双方都不高于此记不睦 |
| `friend_line` | num | 必填 | 双方都不低于此记好友 |
| `hi` | num | 必填 | 好恶上限 |
| `lo` | num | 必填 | 好恶下限 |
| `same_dorm` | num | 必填 | 同寮的底数加成 |
| `same_post` | num | 必填 | 同岗的底数加成（厨房职事视为同岗） |
| `same_track` | num | 必填 | 同方向的底数加成 |

**`rule:chat`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `bad_mod` | 引用 modifier | 必填 | 谈得不投机给的修正项 |
| `gain_when_brief` | num | 必填 | 工友短谈给“群”的补益 |
| `good_base` | num | 必填 | 谈得投机的概率 = good_base + (相容度 − good_mid)×good_w |
| `good_mid` | num | 必填 | 相容度中点 |
| `good_mod` | 引用 modifier | 必填 | 谈得投机给的修正项 |
| `good_thought` | 引用 thought | 必填 | 谈得投机给的想法 |
| `good_w` | num | 必填 | 相容度权重 |
| `lone_label` | str | 必填 | 闲谈落单、改散步的原因 |
| `pair_noise` | num | 必填 | 配对时挑人的噪声 |

**`rule:rumor`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `decay` | num | 必填 | 每日衰减 |
| `g_div` | num | 必填 | 合群的刻度 |
| `g_off` | num | 必填 | 合群的偏移 |
| `keep` | int | 必填 | 每人最多留几条见闻 |
| `min_strength` | num | 必填 | 低于此不再外传 |
| `p_add` | num | 必填 | 转述概率 = min(p_cap, 强度/100 + p_add) × (g_off + 转述者合群/g_div) |
| `p_cap` | num | 必填 | 转述概率上限 |
| `penalty` | num | 必填 | 转述一次强度减多少 |

**`rule:mood`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `enabled` | int | 必填 | 启用几道（自上而下）；本步只能是 1：后两道留给 C7 |
| `lines` | [表] | 必填 | 三道线（自高到低）：[{ value, effect }]；effect = slack / avoid_group / life_event |
| `lines[].effect` | str | 必填 | 后果 |
| `lines[].value` | num | 必填 | 心情低于它就触发 effect |
| `weights` | {键: 数} | 必填 | 五项需求进心情的权重 |

**`rule:free`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `choice_key_chars` | int | 必填 | “自由时段的选择”统计取原因的前几个字作键（只入统计） |
| `stroll` | 引用 interaction | 必填 | 都不成时去做的交互（散步）：场所取它的工位 |
| `stroll_label` | str | 必填 | 散步的原因 |
| `top_k` | int | 必填 | 在得分最高的几项里按分数加权抽一项 |


#### 12.4.8 场景：`defs/scenario/proto60.toml`

场景与世界描述（`SiteSpec`）分开：同一份 `SiteSpec` 可以配不同的种子、人口与实验。`ScenarioSpec` 管“这一次怎么跑”；
`gossip`（传闻实验）与 `n1`（厨房减员实验）是脚本与实验，`main` 里的 `glutton / lazy / trace_* / observer_place / track_suffix / long_days / extra_seeds` 只用于报表与回归。
`cast`（要角）里的清众序号超出人口时略过（人口太小、清众里没有这一位），所以只有岗位者的寺（人口等于编制）也能跑。

**`scenario`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `cast` | [表] | 必填 | 要角：[{ index, traits }]：清众里第 index 位的性格改写（序号从 0 起） |
| `cast[].index` | int | 必填 | 清众序号 |
| `cast[].traits` | {键: 数} | 必填 | 性格改写 {D,S,G,T,R: 值} |
| `days` | int | 必填 | 默认跑几日 |
| `extra_seeds` | [int] | 必填 | 多种子那几行 |
| `glutton` | int | 必填 | 报表里点名的“惯犯”（清众序号） |
| `lazy` | int | 必填 | 报表里点名的“懒人”（清众序号） |
| `long_days` | int | 必填 | “长跑”那一行的日数 |
| `name` | str | 必填 | 场景名 |
| `observer_place` | 引用 place | 必填 | “观察者在廊下”那一行的观察处 |
| `population` | int | 必填 | 人口（岗位者按编制排在前，其余是清众） |
| `seed` | int | 必填 | 随机数种子 |
| `trace_day` | int | 必填 | 报表里“某日四人轨迹”的日子 |
| `trace_post` | 引用 post | 必填 | 轨迹里第四人的岗位 |
| `track_suffix` | str | 必填 | 清众的称呼 = 修行方向 + 此字（报表标题“60 僧 × 30 日”里的量词也用它） |

**`scenario:gossip`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `day` | int | 必填 | 第几日 |
| `heard` | int | 必填 | 唯一的见证人（清众序号） |
| `slot` | int | 必填 | 发生的时辰 |
| `who` | int | 必填 | 偷食者（清众序号） |
| `why` | str | 必填 | 事件里记的原因 |

**`scenario:n1`**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `arms` | [表] | 必填 | 对照组：[{ name, acting }]（监院是否派人代理） |
| `arms[].acting` | bool | 必填 | 监院是否派人代理 |
| `arms[].name` | str | 必填 | 组名 |
| `day` | int | 必填 | 第几日起 |
| `days` | int | 必填 | 病几日 |
| `sick` | [表] | 必填 | 同时病倒的岗位者：[{ post, first }]（first = 只取该岗位的前几位） |
| `sick[].first` | int | 可缺省 | 只取前几位 |
| `sick[].post` | 引用 post | 必填 | 病倒者的岗位 |
| `sick_label` | str | 必填 | 报表标题里对病倒者的称呼 |
| `window` | [int] | 必填 | 逐日偷食累计看第 window[0]–window[1] 日 |


### 12.5 行为包是数据

包的字段：`layer`（层标签；轨迹里的“生效层”、行为包占比的统计口径）、`who`（谁适用）、`when`（何时成立）、`do`（声明式：做什么）或
`handler` + `params`（需要条件判断的：处理器与参数）。**自上而下第一个成立的生效**（《上古卷轴 V》的 Package Stack）；栈的次序是 `rule:stack` 的 `packages` 列表。

* **`who`**：`post`（岗位编号列表，任一）、`status`（`common` 无岗位的清众 / `holder` 有岗位者）、`track`（修行方向列表，任一）；不写 = 所有人。
* **`when`**：`slot`（时辰）、`period`（时段名：`night` 夜间、`meal` 斋食时辰，取自 `rule:schedule`——日程只写一处，改了夜间，包里的就寝跟着变）、
  `day`（模拟日序号）、`day_of_month`（历法的月内日）、`month`、`festival`（`true` = 任一节日，或节日名）、`weather`、`season`；不写 = 任何时候。
  各条件之间是“且”，一个条件的多个取值是“或”。
* **日历键与匹配次序**（计划 6.2，照《星露谷物语》的 schedule key）：同一层里相邻的**声明式**包合成一组，组内按 `when` 的具体程度匹配——
  **先具体日子（`day` / `day_of_month` / `festival`），再天气（`weather`），再季节（`season` / `month`），最后默认（只有时辰或什么都没写）**；
  同一程度按栈里的次序。匹配次序是引擎的规矩，不看包在栈里的先后（`tests.test_npc_defs.CalendarKeys` 故意把最不具体的排在最前验证）。
  布萨（`when = { day = [1, 15], slot = 7 }`）就是“具体日子压过默认”的例子：它排在集体日程的最前，不在布萨日同一时辰没有它。
  日历键由 `stack.Stack.keys(day)` 给：`day dom month festival season`（节日、月、月内日取自**这处场所自己的历法** `SiteSpec.calendar`，即 `rule:schedule` 的 `calendar` 引用的 calendar 定义；季节取自同一条规则的 `seasons`；不读全局默认历法），`weather` 由
  **Host 的可选方法 `weather(day)`** 提供，**没有就永不成立**（`StandaloneHost` 没有它；集成世界的 KernelHost 来给）。
* **声明式 `do`**：`place`（场所编号，或 `"$home"` 本人寮房）、`act`（活动代码，要有对应的交互）、`label`（原因）；`claim = true` 占一个工位，
  满员改去 `overflow.place`、原因加 `overflow.suffix`。
* **处理器**：`handler = "<名>"` + `params`（见 12.6）；处理器包的 `when.slot` / `who` 仍由引擎先筛一遍，处理器函数里只写“条件判断”本身；
  `when` 里带日历条件的处理器包也会先查日历键。
* **层与栈的硬规矩**（`validate` 检查）：层标签要在 `rule:layers` 登记；值守层的包必须在栈里相邻（反应包要先问“此刻有没有值守”）；
  栈里必须有一个 `free` 包兜底；巡寮处理器的 `who` 必须正是 `org:patrol` 的岗位。
* **栈的次序是数据**：`tests.test_npc_defs.HandlerRegistry.test_stack_order_is_data` 把夜里的就寝排到起念偷食之前，夜里就没人偷食了。

原型场景的 36 个包，自上而下（编号省略 `package:proto60:`）：

| 层 | 包 | 做什么 |
| --- | --- | --- |
| 强制 | `forced_ill` `forced_confined` | 卧病（延寿堂）、禁闭（戒律院）：处理器 `forced` |
| 处分 | `penalty` | 未时到大殿罚跪香：处理器 `penalty` |
| 反应 | `court_report` | 有待报的举报且戒律院开门，巳 / 申时去举报：处理器 `court_report` |
| 值守 | `duty_kitchen` `duty_proxy` `duty_patrol` `duty_gate` | 厨务、监院派来的代理帮厨、僧值巡夜与巡寮、山门轮值（相邻成一段） |
| 生理 | `physiology` | 昏沉不支就地昏睡；饿极了守戒低的人去厨房偷吃 |
| 越轨 | `tempted_night`（丑时）| 夜里起念偷食（处理器 `tempted`） |
| 作息 | `night_sleep` | 夜间就寝（声明式，`when.period = "night"`） |
| 越轨 | `lazy` | 晨起贪睡不起 / 困乏未起（处理器 `lazy`） |
| 集体 | `uposatha` `morning_zazen` `morning_chant` `morning_meal` `noon_meal` `evening_chant` `evening_zazen` | 布萨与晨坐、早课、早斋、午斋、晚课、晚坐：声明式，同一条日程给所有人 |
| 岗位 | `post_abbot` … `post_infirm_head`（10 个） | 各岗位的本职理事时段：声明式 |
| 怠工 / 差事 | `slack` `errand` | 清众的差事时辰：怠工则转去自由时段挑，否则认领差事 |
| 身份 | `class_martial` `class_study` `class_zazen` | 清众按修行方向做功课，满员改去讲堂：声明式 + `claim` |
| 越轨 | `tempted_afternoon`（未时）| 午后起念偷食 |
| 自由 | `free` | 兜底：按需求给设施广告打分 |

### 12.6 处理器清单与参数

处理器登记在 `handlers.PACKAGE_HANDLERS`（`@package_handler(name, params=…, layers=…, acts=…, begin=…, who_office=…)`），
一个处理器是函数 `fn(stack, pkg, p, day, slot, ctx) -> (场所, 活动, 层, 原因) | None`（`None` = 不成立，交给栈里的下一个包；巡寮者的决定多带第五项“所巡之处”）。
登记时写明它**只能带哪些层**（`layers`）、**会产出哪些活动**（`acts`；规格自检要求交互里有它们）、有没有**每日开始的钩子** `begin(eng, pkg, day)`
（监院派人代理用）。每个参数登记一张 `Param(名, 类型, 默认值 | 必填, 取值范围, 说明)`：defs 构造时按表补默认值、把引用换成 `code` / 岗位名、列表换元组并校验；
`SiteSpec.validate()` 再按同一张表查一遍。参数类型：`int float str bool slots`（时辰列表）`strs place post posts act`。

| 处理器 | 层 | 产出的活动 | 每日钩子 | 做什么 |
| --- | --- | --- | --- | --- |
| `forced` | 强制 | `sleep` `meal` | — | 卧病、禁闭：别的包都让位；夜间睡、斋食时辰用斋、其余做 `other_act` |
| `penalty` | 处分 | — | — | 档案上还有未执行完的罚跪：时辰由包的 `when.slot` 给 |
| `court_report` | 反应 | — | — | 有待报的举报且戒律院开门：去举报（值守者没空，`free_posts` 的岗位除外） |
| `kitchen_duty` | 值守 | `work` | — | 厨房职事（岗位表里 `kitchen = true`）在厨务时辰去厨房干活 |
| `proxy_cook` | 值守 | `work` | 有 | 当日被监院派来代理帮厨的人在厨务时辰去厨房；每日开始的钩子按精进降序补足在岗人手 |
| `patrol_duty` | 值守 | `patrol` `sleep` | — | 僧值两人轮流：一人巡夜（夜里巡、白天补觉），另一人日间巡寮；每次从 `roam` 里按随机序挑 `pick` 处 |
| `gate_duty` | 值守 | `guard` | — | 山门：每日从清众里轮值 `gate.count` 人 |
| `physiology` | 生理 | `sleep` | — | 困到不支就地昏睡；饿极了守戒低的人去厨房偷吃，其余忍着（得“忍饥”想法） |
| `tempted` | 越轨 | — | — | 越轨起念：性格改的是门槛，不是生理常数；概率 = min(p_cap, (s_line − 守戒)/s_line × (th − 饥)/th × k) |
| `lazy` | 越轨 | `sleep` | — | 晨起：精进低的人今天贪睡不起（越轨）；没贪睡但困乏也起不来（生理） |
| `slack` | 怠工 | — | — | 差事时辰：精进低或心情低的人不去领差事，转去自由时段挑（层记“怠工”） |
| `errand` | 差事 | `work` | — | 差事：从当日工作板按优先级认领第一件还有空额的差事（认领即预约） |
| `free` | 自由 | — | — | 自由：按需求给设施广告打分，前几名里加权抽一项（兜底） |

准入门登记在 `handlers.GATES`（`@gate(name, params=…)`），是函数 `fn(eng, p, day, slot, params) -> bool`，由交互的 `admission = { gate = "<名>", … }` 引用，
只对有 `ad`（自由时段广告）的交互起作用：

| 准入门 | 做什么 |
| --- | --- |
| `lib_open` | 经阁开放：在开阁时辰，且管阁的岗位有人在任、没病 |
| `bath_day` | 开浴日：每 `every` 日一次（日序号 % every == phase），在 `slots` 时辰 |

**加一个新处理器不用改 `stack.py` / `engine.py`**：在 `handlers.py` 里登记它（或在自己的模块里 `from .handlers import package_handler` 登记），defs 里写 `handler = "名"`。
`tests.test_npc_defs.HandlerRegistry.test_a_new_handler_plugs_in_without_touching_the_stack_code` 就是这么做的：

```python
@package_handler('copy_sutra', layers=(L_DEVIANT,),
                 params=(Param('label', 'str'), Param('d_min', 'float', default=0, lo=0, hi=100)))
def copy_sutra(st, pkg, p, day, slot, ctx):
    """日课：精进不低于 d_min 的人抄经。"""
    if p.D >= pkg.params['d_min']:
        return ('lib', 'study', pkg.layer, pkg.params['label'])
    return None
```

处理器函数里的随机一律走 `st.eng.rng(st.eng.seed, '用途', 日, 时辰, ix…)`（计数器式键）；改了抽签键或多抽一次，基线哈希就变（见第 10 节“哈希基线”）。

**处理器 `forced` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `extra_sleep_slots` | slots | 可缺省 | 夜间之外也睡的时辰 |
| `meal` | str | 必填 | 斋食时辰的原因 |
| `other` | str | 必填 | 其余时辰的原因 |
| `other_act` | act | 必填 | 其余时辰的活动（sick / confined） |
| `place` | place | 必填 | 卧病在哪、禁闭在哪 |
| `sleep` | str | 必填 | 夜间（与 extra_sleep_slots）的原因 |
| `state` | str | 必填 | 档案上的哪个状态：ill 卧病 / conf 禁闭（到哪一日，含） |

**处理器 `penalty` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `act` | act | 必填 | 受罚的活动 |
| `label` | str | 必填 | 原因 |
| `place` | place | 必填 | 受罚的场所 |

**处理器 `court_report` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `act` | act | 必填 | 活动 |
| `free_posts` | posts | 可缺省 | 当值也去得了的岗位（僧值）；其余值守者没空去 |
| `label` | str | 必填 | 原因 |
| `place` | place | 必填 | 举报去哪（戒律院） |

**处理器 `kitchen_duty` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `label` | str | 必填 | 原因 |

**处理器 `proxy_cook` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `label` | str | 必填 | 原因 |
| `target` | int | 必填 | 厨房在岗人手不足此数就补 |

**处理器 `patrol_duty` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `day_slots` | slots | 必填 | 另一位日间巡寮的时辰 |
| `label_day` | str | 必填 | 巡寮的原因 |
| `label_night` | str | 必填 | 巡夜的原因 |
| `label_rest` | str | 必填 | 补觉的原因 |
| `night_slots` | slots | 必填 | 巡夜者巡夜的时辰 |
| `pick` | int | 必填 | 每次从 roam 里按随机序挑几处 |
| `rest_slots` | slots | 必填 | 巡夜者白天补觉的时辰 |

**处理器 `gate_duty` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `label` | str | 必填 | 原因 |

**处理器 `physiology` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `act` | act | 必填 | 饿极时做的活动（steal）：场所取该交互的工位，克制时的想法取它的 refrain_thought |
| `faint_e` | float | 必填 | 困低于此，非斋食时辰就地昏睡 |
| `faint_label` | str | 必填 | 昏睡的原因 |
| `starve_h` | float | 必填 | 饥低于此（非斋食、非夜间）：守戒低者偷食，其余忍着 |
| `starve_label` | str | 必填 | 偷食的原因 |
| `starve_s` | float | 必填 | 守戒低于此才偷 |

**处理器 `tempted` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `act` | act | 必填 | 起念去做的活动（steal）；场所取该交互的工位 |
| `k` | float | 必填 | 起念概率的系数 |
| `label` | str | 必填 | 原因 |
| `p_cap` | float | 必填 | 起念概率的上限 |
| `s_line` | float | 必填 | 守戒达到此线的人不起念 |
| `t_mid` | float | 必填 | 馋的中点 |
| `t_slope` | float | 必填 | 馋每高一点，门槛抬高多少 |
| `th_base` | float | 必填 | 起念的饥门槛底数 |

**处理器 `lazy` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `d_div` | float | 必填 | 贪睡概率 = (d_line − 精进)/d_div |
| `d_line` | float | 必填 | 精进低于此才可能贪睡 |
| `label` | str | 必填 | 贪睡的原因 |
| `roll_slot` | int | 必填 | 在这一时辰抽“今天贪睡” |
| `tired_e` | float | 必填 | 晨起窗口里困低于此，起不来（生理层） |
| `tired_label` | str | 必填 | 困乏未起的原因 |

**处理器 `slack` 的参数（package 的 params）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `d_div` | float | 必填 | 怠工概率 = (d_line − 精进)/d_div |
| `d_line` | float | 必填 | 精进低于此才可能怠工 |
| `low_mood_add` | float | 必填 | 心情低于第一道线时加的概率 |


### 12.7 准入门的参数

**准入门 `lib_open` 的参数（interaction 的 admission）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `office` | post | 必填 | 管阁的岗位：它在，经阁才开 |
| `slots` | slots | 必填 | 开阁时辰 |

**准入门 `bath_day` 的参数（interaction 的 admission）**

| 字段 | 类型 | 必填 / 默认 | 说明 |
| --- | --- | --- | --- |
| `every` | int | 必填 | 每几日开浴一次 |
| `phase` | int | 必填 | 日序号除以 every 的余数 |
| `slots` | slots | 必填 | 开浴时辰 |


### 12.8 交互、设施与规范：“同一间厨房，对饭头是工作，对旁人是偷食”

交互的 `norm` 字段说的是“谁做了这件事，就触犯这条规范”：`interaction:proto60:steal`（厨房取食）写 `norm = "norm:proto60:food_theft"`，
引擎在有人做 `steal` 时发该规范 `event` 指定的事件（`FOOD_THEFT`）、让目击者得见闻、之后走举报—立案—裁断—处分的链。
**同一处厨房有两种规范后果，由“活动”区分**：值守包（`kitchen_duty` / `proxy_cook`）给厨房职事与代理帮厨的活动是 `work`（`interaction:proto60:work`，没有 `norm`——对饭头是工作），
越轨起念（`tempted`）与饿极（`physiology`）给的活动是 `steal`（有 `norm`——对旁人是偷食）。所以“同一件事对不同的人性质不同”不是在规范里写人，
而是写“哪个包给这个人这个活动”：包的 `who` 说谁、`do` / 处理器说做什么，交互说这个活动触犯什么。
（饭头自己夜里起念去偷，给的仍是 `steal`，也要受罚——原型的行为，哈希里就有。）

约束：`norm` 引用的规范必须是 `role = "theft"` 的越轨类规范，且该交互必须有 `station`（事件发生在工位所在的场所）；
`SiteSpec.violations` 是由此派生的“活动 → (规范名, 事件, 场所)”表。现在只有这一类规范能被交互触犯；
点名缺课、怠工被撞见、夜不在寮是引擎的三种“被发现”机制，参数写在各自的 `norm` 里（再加一类规范要在 `norms.py` / `perception.py` 里加机制，不在本步范围）。

### 12.9 如何为另一处场所写一套 defs：把 proto60 改成 300 僧少林寺

**先量一量“只改人口”的结果**（同一份 defs，`python3 -m tianl.npc.report --scale 300 --days 30`，规格不动，`ProtoRun(n=300)`）。
引擎不报错、预约越界 0 次、每个决定都说得清（有层有原因）、层占比与时间分配如下；**但这不是一座像样的 300 僧寺**，因为差事板、工位、厨房编制还是 60 人的尺寸：

| 同一份 defs（30 日） | 60 人（基准） | 300 人，只改人口 | 300 人，差事数与工位数 ×5 |
| --- | --- | --- | --- |
| 决定数 | 21600 | 108000 | 108000 |
| 设施满员改选（工位吃紧） | 200 | 26372 | 547 |
| 差事 完成 / 发布 | 870 / 870 | 870 / 870 | 4350 / 4350 |
| 清众每日在“作务”上的时辰 | 0.94 | 0.13 | 0.54 |
| 行为包占比：集体 / 自由 / 越轨 | 48.1% / 7.7% / 0.3% | 49.3% / 14.1% / 0.3% | 49.2% / 10.8% / 0.3% |
| 偷食 / 举报 / 处分 / 缺课 | 7 / 1 / 1 / 24 | 9 / 1 / 3 / 148 | 10 / 2 / 4 / 148 |

读法：集体日程（早晚课、斋食）仍占一半，越轨仍是千分之几——日历上的生活不随人口变形；人口翻五倍而差事板没变，清众的作务时间从 0.94 掉到 0.13、满员改选涨到两万多次
——这正说明“人多了，要改的是定义里的数”。第三列只把 `job` 的 `count` 与 `facility` 的 `stations` 乘 5（只改 defs 里的数、不碰代码；
`tests.test_npc_defs.Generalization.test_editing_only_numbers_in_defs_makes_a_better_300_monk_temple` 用 10 日复现这一列的趋势：差事全部完成、满员改选少一个数量级以上、作务时间占比回升），满员改选降到 547 次、作务回升到 0.54。
这几列的数字是本机的一次运行（种子 20261110），不是通过线；“像不像一座真的少林寺”要等集成步骤按原著与内核的数据校准。

**真要做一套 300 僧少林寺的 defs，按下面的清单改**（别的场所——丐帮分舵、世家庄园——同理；引擎与处理器不动，只有 defs 与必要的新处理器）：

| 步骤 | 改什么 | 怎么验证 |
| --- | --- | --- |
| 1 起一个新 scope | 复制 proto60 的八个文件，文件名与每条编号里的 `proto60` 换成新 scope（如 `shaolin300`；`shaolin` 是内核的，别撞）。 | `Defs.load(root, strict=True)` 引用完整性 100%；换 scope 不改任何结果：`tests.test_npc_defs.Generalization.test_the_same_defs_under_another_scope_reproduce_the_baseline`（同一世界、同一哈希） |
| 2 场景 | `scenario:<scope>:main`：`population = 300`；`seed`、`days`；`cast` 里的清众序号按新的人口重排（或删掉）；`trace_post`、`observer_place` 指向新 scope 的定义；`gossip` / `n1` 的人与岗位同理。 | `ScenarioSpec.from_defs` |
| 3 场所（`space`） | 加寮房与殿堂；`code` 是运行时钥匙：**接内核时用内核的 `SH_*` 钥匙**（ARCHITECTURE 第 3 节），随机数键与哈希行里的场所码随之变化，要另立基线（第 10 节“场所钥匙”）；定义编号仍是 `place:<scope>:名`。 | 规格校验的“场所不在 places 里” |
| 4 设施与交互（`facility`） | `stations` 按人数放大（禅堂、练武场、藏经阁、浴室、井台、廊下）；新设施与新活动：交互里写 `act`（新的活动代码只要在交互里登记就能被声明式的包与广告使用）。 | `SiteSpec.validate()`；预约越界 0 |
| 5 岗位（`post`） | `count` 编制放大；新岗位加一条 `post` 与一个第 8 层的 `package:<scope>:post_*`（`who.post`、`when.slot`、`do`）；`disc`（纪律执事）、`kitchen`（厨房职事）标志；`org:court.judges` 的岗位表。 | 名册按岗位表排：岗位者排在前，其余是清众 |
| 6 差事（`job`） | 每件差事的 `count` 放大，必要时加新差事；`prio` 小的先被认领；`outputs` 的物要在 `org:kitchen.stock_init` 里有库存项。 | 差事完成 / 发布 = 100% |
| 7 部门（`org`） | `org:main.dorms` 加寮房（第 i 个人住第 i % 寮数 个）、`roam` 巡寮候选；`org:kitchen` 的 `min_staff`、`prep`、`stock_init`（斋食耗什么看 `interaction:meal` 的 `inputs`）；`org:gate.count` 山门轮值人数；`proxy_cook.target`（厨房在岗人手的目标）。 | 半餐 / 斋食次数（基准是 0 / 60） |
| 8 历法、包与日历 | **先定历法**：写（或引用）这座寺自己的 `calendar` 定义（节日表、结夏、收成日；`year` 只能是 360），让 `rule:<scope>:schedule` 的 `calendar` 指向它——`when.festival` / `month` / `day_of_month` 都按它，别处的历不会混进来。再加节日、布萨日的包（`when.day_of_month` / `festival`，比默认包优先）；加季节与天气的包（季节月份在 `rule:schedule.seasons`）；新的条件判断写成处理器（12.6）。 | `tests.test_npc_defs.CalendarKeys` 的写法；`tests.test_npc_defs.ScopeCalendar`（换历法、节日名写错、月 / 月内日越界、全局默认被换掉也不受影响） |
| 9 规范与知识 | `norm`、`ladder`（处分阶梯）、`thought`、`modifier`、`rule:rumor` 等按这座寺的规矩调。 | 悬空引用与“没人用的定义”都会被报出来 |
| 10 跑起来 | `spec = SiteSpec.from_defs(defs, 'scenario:<scope>:main')`；`scn = ScenarioSpec.from_defs(...)`；`ProtoRun(spec=spec, scenario=scn).run()`（名册由 `scenarios.proto60_roster` 按岗位表与场景人口排，不含场所特例）；或自己 `NpcEngine(spec, host)` 逐个 `add_person`。 | 看 `report.scale_report` 的各层占比与时间分配 |

### 12.10 第二步的验收与已知限制

* 基准哈希 `e8f8209eeb8ca94a` 与第一步的全部哈希、全部数字在 defs 驱动下**一字不差**地复现（第 11 节）；`python3 tools/npc_regress.py --all --diff` 与 `reference/logs/npc_run_log.txt` 逐行比对 55 行全部一致（只有两行耗时不比）。
* `tests/test_npc_defs.py`：defs 驱动的规格（引用完整性、每条定义都被用到、规格由 defs 唯一构造、场景来自 defs、内核照常加载）；行为包是数据（日历键与匹配次序、栈次序、布萨）；
  处理器登记表（参数校验、新处理器即插即用、默认值来源）；报错清楚（上面各条样例 + 一次报全）；钩子（第 13 节）；泛化（300 僧 30 日、其他人口、换 scope、只改 defs 里的数、命令行）；文档不漏字段。
* 已知限制（如实记）：交互的 `duration` 目前只接受 1（引擎按时辰决定；多时辰的交互留给集成步骤）；心情只启用第一道线（第 13 节之后由 C7）；
  交互只能触犯 `role = "theft"` 的规范（12.8）；`Host.weather(day)` 是可选能力，没有就永不成立；“没被引用”的检查只覆盖想法、修正项、处分阶梯、包与单例角色（场所、设施、交互、岗位、差事、事件、性格本来就是表，每条都会被取用）；
  处理器的参数校验只查类型、引用与范围，不查数值是否“合理”（与 `SiteSpec.validate()` 一样）。
* 历法的限制（如实记）：`calendar` 定义的 `year` 只能是 360（一年 12 个月、每月 30 日，内核与引擎共用 `tianl.core.calendar.YEAR`）；`when` 里没有“朔望”“结夏安居”“收成日”这类键——
  它们是历法的字段（`engine.cal(day)` 的 `shuowang retreat wheat millet`），要按它们排日程就在 defs 里写成 `day_of_month` / `month`，或新写一个处理器读 `engine.cal(day)`。
* 同一套 defs 换成 300 僧只是**不报错、占比合理**，不等于校准过：校准在集成步骤，对照原著与内核数据。
* 名册的名字：字池（`org:main.name_pool`）只有 62 个字，超过一圈后名字后面多缀字池里的字（`scenarios.given_name`；第一圈与原型的取法逐字相同），所以 300 人、数千人都不重名
  （`tests.test_npc_defs.Generalization.test_names_stay_unique_however_large_the_population`）。集成步骤用原著人名时换掉名册来源即可，引擎只认 `ix` 与 `pid`。
* 报表（`report.py`）的各行用词沿用原型日志的格式（“查寮空铺”“过堂人数”“迁单”……），是原型输出格式的一部分，不是引擎行为；换一座场所要换报表时在 `report.py` 里另写一份格式，
  引擎自己的文字（`explain` 里“离寺”之类的说法、报表标题里的“60 僧”的量词）已经来自 defs（`org:main.leave_word`、`scenario:main.track_suffix`）。

## 13 钩子（给后续步骤）：之后的步骤只改自己的模块，不再改 `engine.py`

`engine.py` 里留了四个调用点，**默认都是空操作、不改任何哈希**（`tests.test_npc_defs.Hooks` 钉住签名、调用次序与默认行为；基准哈希在钩子都挂着时照旧）。
引擎通过**模块属性**调用它们（`from . import controller, life, lod, persist` 后调 `life.pulse(self, day)`），所以后续步骤替换模块里的函数体就行；测试里 `mock.patch.object(life, 'pulse', …)` 同样有效。

| 钩子 | 签名 | 调用点（第 4 节次序） | 默认 | 接手 |
| --- | --- | --- | --- | --- |
| 月 / 年脉冲 | `life.pulse(engine, day)` | `begin_day` 的**第一步**：每个模拟日一次，在生病抽签与监院派人之前 | 空操作（返回 `None`） | C7（`life.py`） |
| 操纵者 | `controller.decide(engine, p, day, slot, ctx)` → 决定四元组 | `run_slot` 第 1 步每人每个时辰的“决定”入口；**仅当 `engine.controllers` 非空才经过这里**（默认零开销） | 没有操纵者的档案直接走栈；有就算候选、交给 `Controller.choose(ctx, candidates)` | C9（`controller.py`） |
| 观察者叙述 | `lod.observe(engine, ctx, day, slot)` | `run_slot` 第 5 步：“落轨迹”之后、偷食与见证之前；**只读** | 没有观察者什么也不做；有就只读地数该场所的人（`engine.narr` 累计） | C8（`lod.py`） |
| 每日落盘 | `persist.flush(engine, day)` | `end_day` 的最后一步：想法到期、修正项到期、传闻曲线、逐日流水账之后；**只读** | 空操作 | 集成（`persist.py`） |

### 13.1 各钩子的约定

* **`life.pulse(engine, day)`**：C7 只改本函数体。要不要今天做事（月初、岁首）由它自己判断，历法用 `engine.cal(day)`（这处场所自己的历法，`engine.spec.calendar.cal(day)`，不是全局默认；返回含 `year month dom term festival` 的字典）；引擎不替它判断。
  随机一律走 `engine.rng` 的计数器式键。若在里面收人 / 送人（`engine.add_person` / `on_person_removed`）或发事件，**会改变基线哈希**，按第 10 节“哈希基线”的规矩重立并写明原因。
  心情第二、三道线（低于 20 回避集体、低于 5 触发人生事件）也在这里接：`rule:mood` 的三条线与后果已在 defs 里，`SiteSpec.mood.enabled` 现在是 1，C7 放开 `validate` 的限制。
* **`Controller.choose(ctx, candidates)`**（`controller.py`）：每份档案一个操纵者，只做一件事——在合法候选里选一个。协议：
  * `class Controller: def choose(self, ctx: ChoiceCtx, candidates: list) -> 决定四元组`；`ChoiceCtx(engine, person, day, slot, slot_ctx)`，想读档案、需求、见闻、眼前的人，都从 `engine` 取；
  * `candidates(engine, p, day, slot, ctx)`：此刻对 p 合法的决定列表，**第一个是程序（栈）的选择**；现在只有它，C9 在此加上该层合法的替代选择，并决定哪些层锁死（强制、处分、值守、集体：只给一个候选）；
  * **接手前先读：`stack.decide` 有副作用**（占工位、记统计、改贪睡与代班的状态、认领差事），不是只读的“看一看”。保证与约束：同一个人同一个时辰（同一个 `SlotCtx`）`decide` 只算一次，
    再调用原样返回第一次的结果、不再占位（`tests.test_npc_defs.Hooks.test_stack_decide_is_idempotent_per_person_and_slot`）——所以 `candidates` 与预览可以放心再取“程序的选择”；
    但**替代候选要自己只读地列出**（例如读 `engine.fac.open_ads` / `score` 给自由时段前几名），不得换着参数多次调用 `decide`；操纵者选了程序的选择之外的候选、而程序的选择已占了工位 / 认领了差事时，
    要先放掉那份占用（在 `controller.py` 里加放位的函数），放不了就把这一层锁死、只给一个候选；
  * `PROGRAM`（`Program`：取候选的第一个）：没有操纵者的档案就是它；
  * `engine.set_controller(who, ctl)` 挂上 / 摘下（`None` 回到栈）；**操纵者出错、超时、给了候选之外的东西，都回落到候选的第一个**，世界不等它（计划 11.1）；运行时不调用真实 LLM。
  * `engine.controllers` 为空时 `run_slot` 直接走 `stack.decide`，不经过 `controller.decide`；给每个人都配上 `PROGRAM`，哈希与不配时相同（有测试）。
* **`lod.observe(engine, ctx, day, slot)`**：`ctx` 是 `model.SlotCtx`（`ctx.dec`：各人这个时辰的决定 `ix -> (场所, 活动, 层, 原因)`）。**只读**：不改任何状态、不进任何哈希；
  叙述若要随机，走 `engine.rng(engine.seed, 'narr', 日, 时辰, ix)`。刻（一时辰 8 刻）只用于叙述（ARCHITECTURE 第 2 节）。观察者站在哪里都不改变任何人的决定（`test_npc_proto` 与 `Hooks.test_observe_is_called_every_slot…` 钉住）。
* **`persist.flush(engine, day)`**：**只读**——落盘不能改变世界；调用时当日的流水账已记（`engine.daily[-1][0] == day`），`engine.last` 是当日最后一个时辰。
  `persist.py` 的 docstring 列了恢复所需的全部状态。

### 13.2 接手时的检查单

1. 只改自己的模块（`life.py` / `lod.py` / `controller.py` / `persist.py`）与自己的 defs；需要新字段时往 `defsload.py` 里加（字段会自动进字段表，别忘了更新本文第 12 节）。
2. 默认路径（没有操纵者、没有观察者、没有脉冲）的基准哈希 `e8f8209eeb8ca94a` 不变：`python3 tools/npc_regress.py --all --diff` 与 `python3 -m unittest tests.test_npc_defs.Hooks`。
3. 要改基线（多发事件、多抽一次签、改决定次序）：先改第 4 节与 ARCHITECTURE 6.1，再改 `tests/test_npc_proto.py` 的基线并写明原因（第 10 节）。
