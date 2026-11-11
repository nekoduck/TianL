# NPC 引擎（tianl/npc）实现说明

本文由 C 段负责人维护，是 `docs/ARCHITECTURE.md` 第 6 节的细化。计划出处：`docs/PLAN.md` 第 5–11 节；
数字出处：`reference/logs/npc_run_log.txt`（原型 `reference/npc_spike.py`，只读）。

**当前进度（C 段第一步，已完成并经独立验证与三轮修订）**：把 60 僧 30 日原型**忠实**移植成模块化的 `tianl/npc` 包。
本步规格用 Python 数据类（`SiteSpec`）表达，不做 defs 驱动；`scenarios.proto60_spec()` 构造出与原型完全一致的一套。
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
整套默认测试（含别的步骤的）在本机约 48 到 52 秒，其中 `test_b1_kernel` 一个文件就约 22 秒，不在本步名下。

## 1. 模块划分与依赖方向

```
spec.py        规格数据类：SiteSpec 及其子规格。引擎里没有魔数，所有常数都是这里的字段。
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
scenarios.py   proto60_spec() / 名册 / 三个要角 / 脚本 / ProtoRun / 实验 N1。
handlers.py    登记表：按名字找处理器（本步只有 gate：lib_open、bath_day）。
life.py lod.py controller.py persist.py   空壳（带 docstring），之后由 C7/C8/C9/持久化各步接手。
```

依赖方向（只许向下）：`scenarios → engine → {stack, perception, norms, rumor, jobs, freechoice, needs}
→ {facilities, opinion, mood, model} → {spec, events, host}`。同层模块通过 `engine` 对象互相调用，
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

`SiteSpec` 是不可变数据类（`frozen=True`），本步由 `scenarios.proto60_spec()` 构造。主要成分：

* 子规格的类名就是 `spec.py` 里的那些：`OfficeSpec`（岗位）、`GroupAct`（集体日程一条）、`KitchenSpec`、`PatrolSpec`、`GateSpec`、
  `CourtSpec`、`RollCallSpec`、`InventorySpec`、`AdSpec`、`NeedSpec`、`CaseSpec`、`LadderStep`……（ARCHITECTURE 第 6 节写的
  `SiteSpec / PostSpec / PackageSpec` 是示例名，该节明说“文件名可微调，职责不可缺”；以本文与代码为准。）
* 场所与设施：`places`、`capacity`（工位数）、`roam`（巡寮候选）、`dorms`、`ads`（自由时段的设施广告表，`AdSpec`）
* 日程：`night`、`rotate`、`meal_slots`、`group`（集体日程）、`uposatha`（布萨；`by='day'` 原型口径，`'dom'` 按历法月内日）、
  `common`（清众的差事时辰与功课）、`offices`（岗位表）、`library`
* 值守与机构：`kitchen`（厨务、斋食、水柴库存）、`patrol`（僧值巡夜巡寮）、`gate`（山门）、`court`（戒律院）、
  `rollcall`（点名）、`inventory`（清点）、`jobs`（工作板）
* 需求与性格：`needs`（收支、效果、功课加成）、`traits`（性格分布）、`phys`（生理线）、`temptation`、`lazy`、`slack`、`illness`
* 好恶与传闻：`opinion`、`mods`、`thoughts`、`mood`、`chat`、`rumor`（强度、衰减、转述概率）、`salience`（事件显著度）
* 规范：`report`（举报概率）、`cases`（立案与悬案；`via_report / via_confess` 是案卷里定罪依据的两个标签）、`ladder`（处分阶梯）、
  `announce`、`layer_rank`
* 统计口径：`free.choice_key_chars`（“自由时段的选择”统计取原因的前几个字作键，原型口径 2，只入统计）
* `SiteSpec.validate()` 做引用完整性自检（场所、岗位、想法键、修正项键、准入门名都得登记过；`ads` 不得为空、`free.top_k` 至少为 1）；`NpcEngine` 构造时调用，
  不通过抛 `SpecError`。规格里的字段没有默认值，取值全写在场景里，所以“改一个数”只有一个出处。
  `tests/test_npc_spec.py` 还检查：原型源码里出现过的每个数值常数（不豁免任何数）都在规格（或场景的“要角”）里出现——
  注意这条只比“数值集合”，拦不住“数在规格里、却被抄错或不被读”；真正的把关是第 8 节的逐步差分、抽签键多重集、扰动差分与数值普查。
  `tests/test_npc_engine.py` 用 AST 扫 `tianl/npc`：除 `spec.py`、`scenarios.py` 外，数值字面量只能是模块级的具名常量
  （`NEVER`、`FIELD_BITS`、`BASE_DECISION`、`PAIR`、`GOSSIP_SLOT`、`HASH_CHARS`、`PKG_STAT`、`TRACE_DAY`、`PERCENT`、`MICROS`、`FIRST_SLOT`），
  或“结构用”的 0/1/2/3：下标与元组位置（0–3 都行）、计数（`+= 1`、`sum(1 for …)`）、初值 0、±1 偏移、`max/min` 的保底、与 0 或 1 的比较。
  2 和 3 只许做下标；乘除里的 0、赋给字段的 1（比如默认时辰）一律不放行（规则自己有“有毒代码”的反例测试）。
  另有一条：规格里的中文业务词、场所代码、岗位名不得以字符串字面量出现在引擎代码里（`spec.py`、`scenarios.py`、`events.py` 除外）。
  实验参数（传闻实验的日子与人、N1 的日子与两个对照组、90 日、多种子清单）与报告用词（轨迹第四人的岗位、清众称呼、需求中文名、
  观察者的场所）都在 `scenarios.py` 的具名常量里，`report.py` 只引用它们。

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
1. 各人生病抽签（`ill`）；脚本 `ill`。
2. 厨房不足 4 人 → 监院派人代理（按精进降序、编号升序，避开山门值守与病、禁闭者）。
3. 发布当日工作板；清空当日“查寮名单”（`sight`）。

`NpcEngine.run_slot(day, slot)`（`n` 是含已迁单者的总人数）：
1. **各人决定**：起点 `(day*7 + slot*3) % n` 轮转；跳过已迁单者；调用十层栈；巡寮者的决定携带“所巡之处”。
2. **闲谈配对**：打算闲谈的人按随机序排队，队首挑“好恶 + 30×随机”最大者；落单者改散步；转述传闻。
3. **差事结算**（巳时）：工人两两短闲谈（改好恶、补“群”，不产生想法）；每名工人一条内核命令；挑水/打柴入账。
   **斋食**（辰、午）：备斋时辰（卯、巳）厨房的人手与水柴 → 足量或半餐。
4. **需求结算；想法；落轨迹**（统计、行为包占比、哈希在此累积）；预约越界检查。
5. **观察者**所在场所的细节叙述：只读，只计数 `narr`。
6. **偷食 → 见证 → 是否举报**；巡夜查寮记空铺（子、丑）；脚本 `gossip`（丑）。
7. **典座清点**（寅）；**维那点名**（卯、酉）；**怠工被撞见**（巳）；**举报送达**；**裁断**（巳）；**午斋后公告**（午）。

时辰对照：子 0、丑 1、寅 2、卯 3、辰 4、巳 5、午 6、未 7、申 8、酉 9、戌 10、亥 11。上面各时辰都是规格里的字段
（`kitchen.prep`、`common.work_slot`、`court.judge_slot`、`rollcall.slots`、`inventory.slot`、`announce.slot`……）。

`NpcEngine.end_day(day)`：想法到期；见闻按日衰减并裁到 16 条；统计心情低落；修正项到期；传闻曲线；逐日偷食累计。

`ProtoRun.run()` 逐日调用以上三步；`state_hash()` = 每决定一行 `日,时辰,ix,场所,活动;` 累积的 sha256，
最后再并入事件日志每条 `种类中文,actor,日,时辰;`，取前 16 位十六进制。

## 5. 十层行为包栈（`stack.py`）

沿用原型的实际判定次序（与计划表的层号对应见 `spec.layer_rank`）：

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
* `python3 -m unittest tests.test_npc_spec`：规格常数与原型逐项相同；多种子、多规模、含脚本与迁单的逐步差分
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
  五个**原型世界**（N1 无人代理、传闻脚本、90 日、种子 4 的 90 日、种子 34 的 N1），和四个**专门场景**——先把规格换成一个更挤、更累、更记仇的世界，再在这个世界上逐个改字段
  （`tight`：工位稀缺、浴室井台没登记容量、功课挪到未时让申时空出来、夜里更易起念；`weary`：困饿孤的消耗加重；`grudge`：好恶放大、处分阶梯连着杖责；
  `emit`：不跑世界，直接发一遍每种事件看见闻强度）。专门场景只换规格、不改引擎，所以“改一个数、世界就变”在这里仍只说明引擎读了这个数。
  默认验两件事：手挑的十个关键数字（举报概率、认错、立案过期、起念、传闻、清点、怠工、工友闲谈……）；原先碰不到的十个字段各在专门场景里改一次、重跑一次。
  `TIANL_SLOW=1` 对全部 345 个数值字段做普查（多进程，约 1 分钟）：**343 个活着、2 个被 `validate()` 拒绝（`meal_slots`）、0 个无可见效果**。
  只用五个原型世界时，有十个字段是死的（`capacity.zen cap_default library.slots.2 needs.eff.sick.e opinion.lo opinion.hi thoughts.flogged.cap
  thoughts.warned_bed.cap salience.REPORT salience.BED_EMPTY`：容量不吃紧、好恶碰不到上下限、举报没有见证人……）；这份清单与每条原因写在测试的 `PROTOTYPE_DEAD` 里，
  慢测试断言“在原型世界里它们确实死、加上专门场景后确实活”，清单变长变短都要改测试，不许悄悄放过。
  “活着”只说明引擎读了这个数，不说明数值合理；专门场景是人为造的世界，普查仍是有限场景下的结论。`UNREACHED`（加上专门场景后仍看不出变化的字段）目前是空的。
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
    **本步没有为此改任何代码**：本步的场景就是原型世界，短码即钥匙。

### 按计划留给后续步骤的（本步不做，不是遗漏）

这几件事在任务书与 ARCHITECTURE 里明确写了“本步不做”，并且各自有接入点；做它们不应改引擎的主干，但会改哈希基线的要重做基线：

* **defs 驱动**（ARCHITECTURE 第 6 节“`from_defs()` 留给之后的 defs 驱动步骤”）：`SiteSpec.from_defs()`、行为包用 `package:*` 定义声明、
  handler 名登记（本步登记表里只有准入门）。`stack.py` 里层的判定先后仍写死，参数已全部在规格里；接入点见第 10 节。
* **其余七种事件**（`CASE_OPENED CONFESS SUMMON ANNOUNCE ILL RECOVER CHAT`，ARCHITECTURE 6.2：“第一步只发其中七种”）：见第 6 节。
  引擎一发就会改流水号与事件日志、改写基线，所以只能在集成步骤一起做并重立基线。
* **life / lod / controller / persist**：空壳（带 docstring，列了要做什么）。C7、C8、C9 与持久化各步接手。
* **KernelHost**：本步只有 `StandaloneHost`；`Host.cmd` 目前只有差事结算一处调用（唯一的内核命令口，standalone 恒受理）。
  KernelHost 由集成代理写，见第 10 节。

## 10. 给后续步骤的接入说明

* **KernelHost**：实现 `Host.ev`（写 `World.ev`，返回含 `id` 的对象；id 与别的系统共用、不连续都没关系）与 `Host.cmd`
  （接 `cmd_move / cmd_take / cmd_put…`），`seed` 取世界种子，`rng` 用 `tianl.core.rnd`。引擎对外只有这两个口。
  再给 `NpcEngine` 一个 `person_factory(pid) -> PersonSpec`，内核的 `on_person_added(pid)` 就能直接转给 `engine.on_person_added(pid)`。
* **defs 驱动**：写 `SiteSpec.from_defs(defs, site_id)` 即可，引擎代码不用动；`SiteSpec.validate()` 已有，defs 构造出来先过它。
  行为包里需要条件判断的（偷食起念、贪睡、值守轮换）用 `handlers.py` 登记表按名字引用——本步登记表里只有准入门，
  起念等判定仍在 `stack.py`，参数已全部在规格里。
* **场所钥匙**（defs 驱动步骤必读，第 9 节第 14 条）：规格里的场所钥匙既出现在轨迹里，也进随机数键与哈希行。defs 驱动后运行时钥匙是 defs 的 `code`，
  不是原型短码，所以原型场景的基线有三条路：
  ① **原型场景沿用短码**（`from_defs` 之外另保留 `proto60_spec()` 这一套，基线 `e8f8209eeb8ca94a` 原样有效；defs 版是另一套世界、另一份基线）；
  ② **加映射**：场景给一个“钥匙 → 随机键与哈希里用的名字”的映射，引擎在写随机键与哈希行时过一遍（要改 `stack.duty` 的巡寮抽签与 `run_slot` 的哈希行两处；映射为恒等时与现在逐位相同）；
  ③ **重立基线**：直接换成 defs 钥匙，按下一条的规矩更新 `tests/test_npc_proto.py` 里所有哈希并写明原因。
  推荐 ①：原型回归保持原样，defs 驱动的世界另立数字。不论选哪条，先跑 `tests.test_npc_engine.PlaceCodesAreKeys`，它会告诉你这两处是不是真的动了。
* **哈希基线**：任何改动随机键、引擎事件流水号（含多发事件）、决定次序的修改都会改变 `e8f8209eeb8ca94a`。要改，先在本文第 4 节改次序，
  再更新 `tests/test_npc_proto.py` 里的基线并在报告里写明原因；不得为了过测试改基线。
* **新人与离开**：`add_person` 只追加 ix；`on_person_removed(pid, why)` 只标 `gone` 与 `gone_why`，不删档案（事件与见闻还指着它）。
* **持久化**：见 `persist.py` 的 docstring，列了恢复所需的全部状态（现在要加上：事件流水号与 hid 的对应、轨迹的 `nxt`）。

## 11. 本步验收结果（原样数字见 `python3 tools/npc_regress.py --all --diff`）

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
| 数值普查（`TIANL_SLOW=1`） | 345 个数值字段：343 个活着、2 个受校验、0 个无可见效果（九个场景；只用五个原型世界时有十个是死的，清单与原因见 `tests/test_npc_sensitivity.py` 的 `PROTOTYPE_DEAD`） |
| 防御性分支 | 自由时段候选全满、没有藏主、没有清众：`DefensiveBranches` 直接构造世界断言（改坏源码会红） |
| 场所短码 | 进入随机键与基线哈希：`PlaceCodesAreKeys` 钉住（第 9 节第 14 条、第 10 节） |
