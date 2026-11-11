# 实现契约（ARCHITECTURE）

本文是 `docs/PLAN.md` 的**工程落地契约**：计划说“做什么、为什么”，本文说“代码怎么摆、接口怎么接、怎么算过”。
各模块的负责代理只改自己名下的章节与文件；跨模块的接口变更必须先改本文再改代码。

## 0. 硬规矩（所有代码适用）

1. **Python ≥ 3.12，只用标准库。** 测试用 `unittest`：`python3 -m unittest discover -s tests -t .`
   （慢测试用环境变量 `TIANL_SLOW=1` 打开；默认整套测试应在 60 秒内跑完）。
2. **确定性。** 每次随机都是 `rnd(seed, 用途, 日, 时辰, 人…)`（`tianl.core.rng`），与调用次序无关。
   禁用 `random`、墙钟时间、对 `str` 的内置 `hash()`；对 `set` 迭代前必须排序；不得依赖未排序的 SQL 结果。
   性能计时只用于报告，不得进入任何决定或哈希。
3. **一切状态变化走内核原语或命令**：钱 `pay`、物 `produce/consume/move`、人动 `cmd_*`。
   v0.2 的每日不变量（钱守恒、物守恒、无透支、无负库存、无无主在途货物、关键岗位空缺≤3 日……）永远成立。
4. **事件日志是感知、记忆、传闻的唯一数据源**；见闻只存指向事件的指针，不复制内容。
5. **定义/实例/状态分开**（计划 4.1）：定义在 `defs/*.toml`，实例在开局快照 `data/snapshot/`，状态在 SQLite。
6. **运行时不调用 LLM。** 建造期 LLM 只出现在 `tianl/canon/`，且必须有离线桩，测试不联网。
7. 所有面向玩家的文字是中文；标识符用英文/拼音；事件类型是大写英文代码，中文由 `chronicle()` 渲染。
8. **原著原文永不入库**（`sources/` 被 .gitignore 忽略）；仓库里不得出现原著的长段引文，说话特征只存标签。
9. 每个里程碑的验收必须是**一条可自动判定的命令**，结果写进 `docs/ACCEPTANCE.md`（由 `tools/acceptance.py` 生成）。
   通过线沿用计划 12.1/12.2；不达标就如实记“未达标”，不许改通过线糊弄。

## 1. 目录与归属

```
docs/PLAN.md            计划原文（只读）
docs/ARCHITECTURE.md    本文
docs/DECISIONS.md       八个待定问题的默认答案与偏离计划之处
docs/CANON_SCHEMA.md    [A]   断言表/事件/秘密的字段与封闭属性清单
docs/KERNEL_DEFS.md     [B1]  内核定义文件的字段说明
docs/NPC_ENGINE.md      [C]   引擎与 NPC 定义文件的字段说明
docs/WORLD_MAP.md       [B3/B4] 全图骨架与展开处
docs/CONSOLE.md         [控制台] 命令说明
docs/GAPS.md            缺口清单（A 段生成）与“未跑通/需原文”的诚实清单
docs/ACCEPTANCE.md      验收报告（自动生成）
reference/              原型与日志（只读；回归基线，不得修改）
defs/                   定义（TOML），按十类分子目录
data/canon/             A 段产出：实体、断言、时间线、事件库、秘密、缺口、问答
data/snapshot/          开局快照（实例）
sources/                原著文本（本地，不入库）
tianl/core/             rng、历法与时间
tianl/defs/             加载器
tianl/kernel/           [B1]  v0.2 内核移植（少林寺钱粮闭环）
tianl/npc/              [C]   NPC 引擎
tianl/canon/            [A]   原著→数据 流水线
tianl/world/            [B3/B4] 全图骨架、展开处、世界装配、情节事件库
tianl/console/          控制台
tests/  tools/
```

## 2. 时间

* 一年 360 日，每月 30 日；第 0 年是预热年。一日十二时辰（子丑寅卯辰巳午未申酉戌亥）。
* 绝对时刻 `t = day*12 + slot`（`tianl.core.t_of / day_slot`）。**时辰是全局时间单位。**
* 一时辰分 8 刻，**刻只用于观察者所在场所的细节叙述，不参与任何决定、不进入任何哈希。**
* 开局：世界第 0 日，对应原著第一回之前；原著中更早的事（旧案）取负日数。

## 3. 稳定编号与运行时钥匙

* 定义编号 `kind:scope:name`（`place:shaolin:library`）。`kind` 登记在 `tianl/defs/kinds.py`。
* **运行时钥匙**：`place` 定义必须有 `code`（如 `SH_LIBRARY`）。内核、引擎、数据库、事件日志里的场所一律用 `code`；
  编号只用于定义之间互相引用与控制台别名查找。`Defs.by_code('place', code)` 反查。
* 人的运行时编号：内核 `person.id`（`P0001`…）。原著人物另有 `canon_link(pid, canon_id)` 表，`canon_id` 形如 `person:canon:xiaofeng`。
* **定义文件里的键一律用 ASCII（TOML 裸键不接受中文），中文只放在值里。**
  需求键固定为 `h` 饥、`e` 困、`c` 洁、`s` 群、`a` 志；性格键固定为 `D` 精进、`S` 守戒、`G` 合群、`T` 馋、`R` 刚正。

## 4. 定义（defs/）

TOML；每个顶层表是一条定义，表名即编号（含冒号须加引号）。`parent` 继承，`_abstract = true` 只供继承。
引用完整性由 `Defs.load()` 在加载时检查（整串恰为已登记 kind 的编号即视为引用）。

十类与 kind（`tianl/defs/kinds.py`）：

| 类别 | kind |
| --- | --- |
| 历法 | calendar |
| 空间 | place, route, region |
| 设施与交互 | facility, interaction |
| 物 | item, commodity |
| 武学 | martial |
| 组织 | archetype, org, site |
| 岗位与规则 | post, rule, package, job, trait |
| 规范 | norm, ladder |
| 经济 | account, process, price, param |
| 知识与事件 | secret, document, event, flag, pulse, thought, modifier, scenario |

目录约定：`defs/<类别英文>/<scope>.toml`，如 `defs/space/shaolin.toml`、`defs/facility/shaolin.toml`。
新增 kind 只追加不改名，并在本节补一行用途。**各 kind 的字段说明写在各负责人的文档里**（见第 1 节）。

## 5. 内核（tianl/kernel）——B1 负责

`tianl.kernel.World` 是 `reference/shaolin_spike.py` 的 World 的移植。移植的验收是**逐字节相同**：

* 基准 `World(); run(360*4)` 的 `state_hash()` 必须是 `49f6ddde04dfa7f5`；
* `reference/logs/shaolin_run_log.txt` 里 E1–E6、十年基准、六个种子、人物与独有物测试的数字全部复现；
* 常量（品类、地点、要角、参数 P、历法节日、岗位站点……）全部来自 `defs/`，代码里不再出现少林寺专有常量。

时间指针与分步接口（`step()` 在未接引擎时必须与原型逐位相同）：

```python
class World:
    day: int; slot: int            # 下一个要跑的时辰（0..11）
    def begin_day(self):  # BEGIN；hooks；weather→arrivals→production→visitors→rules→orders→consumption
    def run_slot(self):   # 引擎存在时调用 engine.run_slot(day, slot)；然后 slot += 1
    def end_day(self):    # people（死亡、继任、收录、班表 make_roster(d+1)）→ check → COMMIT → day += 1
    def advance(self, n_slots): ...   # 走 n 个时辰，自动处理跨日边界（控制台“等 n”用）
    def step(self): ...               # = begin_day(); 12×run_slot(); end_day()
    def run(self, days): ...
    engine: Optional[Engine]          # 见 5.1
```

事务：与原型一致，每日一个 `BEGIN…COMMIT`；日内停在时辰边界时事务保持打开，控制台读同一连接。

内核保留 v0.2 的全部原语与命令（`pay/produce/consume/move/ship/open_order…`、`cmd_move/cmd_take`），并新增命令
`cmd_put / cmd_use / cmd_say`（C 段与控制台提需求，B1 之后由集成代理实现），所有命令仍是“物理约束拒绝、规范约束放行但记违规”。

### 5.1 内核 ⇄ 引擎边界

```python
class Engine(Protocol):
    def attach(self, world): ...
    def begin_day(self, day): ...                 # 在内核 begin_day 的经济阶段之后
    def run_slot(self, day, slot): ...            # 十二时辰循环
    def end_day(self, day): ...                   # 在内核 people 阶段之前
    def on_person_added(self, pid): ...           # 收录、选角、迁入
    def on_person_removed(self, pid, why): ...    # 圆寂、迁单、游方
    def where(self, pid, day, slot):              # -> (场所 code, 活动, 层, 原因) | None
```

* **班表仍由内核 `make_roster` 物化**（山门、藏经阁、夜巡、粮库）；引擎的第 5 层“值守”读这张表，另外自己补厨务、巡寮等岗位。
* **经济中立性测试**：接上引擎、基准里没有触发任何耦合时，纯经济表（`account/ledger/stock/shipment/work_order/household/arrears/route_closure`）
  的哈希 `econ_hash()` 必须与未接引擎时相同。耦合只有两处，且必须有开关与事件：(a) 厨房人手不足 → 半餐 → 当日口粮减量；
  (b) 偷食扣厨房粮。基准里 (b) 关闭；(a) 在基准里应从不触发。
* **耦合的内核入口**（B1 已实现，`tianl/kernel/coupling.py`）：开关 `World.couplings = {'half_meal': True, 'food_theft': False}`；
  (a) 引擎调 `world.set_meal_ration(day, factor, why)`，内核在 `day` 日消耗阶段把斋粮按 `factor` 减量并发 `MEAL_HALVED`；
  (b) 引擎调 `world.cmd_steal_food(actor, q, slot, cause)`，开关开着时内核从寺库粮仓扣粮并发 `GRAIN_STOLEN`。
  **时序约束**：内核的消耗阶段早于 `engine.begin_day`，所以 (a) 只能为明日及以后的日子登记（引擎在 `end_day(d)` 里为 `d+1` 登记），登记当日抛 `ValueError`；
  要当日生效须把消耗阶段挪到 `engine.begin_day` 之后（改本节契约，不是改内核入口）。两个入口缺省都不触发，econ_hash 与未接引擎时相同。
* `on_person_added` 回调时那个人的库里一行已定稿（含 `home`）；`on_person_removed(pid, '游方')` 之后 `world.where(pid, …)` 为 `None`。
* 引擎的随机数函数由构造参数注入：集成世界用 `rnd`（sha256）；复现原型哈希的测试用 `rnd_b2`。

## 6. NPC 引擎（tianl/npc）——C 段负责

模块划分（计划第 5–11 节；文件名可微调，职责不可缺）：

```
spec.py        SiteSpec / OfficeSpec / PackageSpec …（不可变数据类）：引擎只认这些对象；SiteSpec.from_defs(defs, 'scenario:<scope>:main') 由 defs 构造
defsload.py    from_defs 的实现：读字段时校验、一次报全；字段表生成（docs/NPC_ENGINE.md 第 12 节）                （第二步新增）
model.py       Profile（身份/归属/性格/需求/想法/见闻…）与引擎状态容器
stack.py       十层行为包栈（强制 处分 反应 情节与指派 值守 生理 集体 岗位 身份 自由 + 越轨）
needs.py       五项需求、一日收支、惰性求值
facilities.py  设施运行时：工位、预约、广告、准入
freechoice.py  自由时段打分，前三名按分数加权抽一项
jobs.py        工作板：认领即预约；差事 = 固定步骤，每步一条内核命令
perception.py  事件 → 见证人处理函数；点名、清点、查寮、公告
rumor.py       闲谈配对、转述、衰减
norms.py       越轨、举报、送达、立案、传讯、裁断、处分阶梯、公告、余波
opinion.py     CK3 式带期限修正项；好友/不睦
mood.py        想法、心情、三道线
life.py        月/年脉冲与事件池、人口调节器；钩子 life.pulse(engine, day)                      （C7）
lod.py         眼前/个体/批三档、观察者、刻级叙述；钩子 lod.observe(engine, ctx, day, slot)       （C8）
controller.py  Controller 协议；Program / Player / LLMStub；钩子 controller.decide(engine, p, day, slot, ctx)   （C9）
engine.py      NpcEngine：把以上串成一个时辰的 tick
persist.py     每日落盘到 npc_* 表；可从表恢复；钩子 persist.flush(engine, day)
scenarios.py   原型场景（60 僧 30 日）与实验 N1
events.py      NPC 事件类型代码与中文渲染                       （第一步新增）
host.py        Host 接口、Event、StandaloneHost；之后集成代理写 KernelHost（第一步新增）
handlers.py    行为包处理器与准入门的登记表（每个带参数表：类型、默认值、取值范围）（第一步新增，第二步补全）
report.py      汇总与原型输出格式（tools/npc_regress.py 与测试共用）（第一步新增）
```

引擎与外界只通过 **Host** 交互（细节与各模块说明见 `docs/NPC_ENGINE.md`）：
`host.ev(kind, actor, place, witnesses, day, slot, cause=None, **data) -> 含 id 的 Event`（actor 与 witnesses 在边界上是外部 id）、
`host.seed`、`host.rng`、`host.cmd(name, pid, **args) -> CmdResult`（内核命令口，本步是 stub）。
规格对象 `SiteSpec` 是不可变数据类，`SiteSpec.validate()` 做引用完整性自检；由 `SiteSpec.from_defs(defs, 'scenario:<scope>:main')` 从 defs 构造
（第二步；`scenarios.proto60_spec()` 是原型场景加载一次后的缓存）。出错都带逐条说明：引用不存在的定义（含包），严格加载时由 `Defs.load()` 抛 `DefsError`，非严格加载时在 `from_defs` 里汇入 `SpecError`；缺字段、处理器未登记、参数缺失或类型取值不合法、包与准入门的引用对不上，由 `from_defs` 读字段时**一次报全**，抛 `SpecError`；规格内部的交叉核对（`SiteSpec.validate()`）在这一步没有问题之后才做，不通过同样抛 `SpecError`。人的内部下标 `ix`（int，稳定，新人追加）与外部编号 `pid`（str）分开，随机数键里用 `ix`。

**行为包是数据**（计划 6.2）：第 7、8、9 层的包由 `package:*` 定义声明（`layer / who / when / do`，`when` 可写日历键），
需要条件判断的包（偷食起念、贪睡、值守轮换……）用 `handler = "<名>"` + `params` 引用 `tianl/npc` 里登记的处理器。
**原型场景必须完全由 defs 描述**，并复现 `npc_spike.py` 的基准哈希 `e8f8209eeb8ca94a`（`rnd_b2`）；
之后同一引擎换一套 defs 扩到 300 僧、再换一套 defs 展开丐帮分舵与庄园。

### 6.1 时辰 tick 的固定次序（沿用原型 step_slot；变更须改本节）

0. `begin_day` 的第一步：**钩子 `life.pulse(engine, day)`**（月 / 年脉冲，默认空操作）。
1. 各人决定（起点按 `(day*7+slot*3)%n` 轮转，保证工位预约公平且确定；系数是 `rule:schedule` 的 `rotate`）；每人每个时辰的入口是
   **钩子 `controller.decide(engine, p, day, slot, ctx)`**（有操纵者才经过：`Controller.choose(ctx, candidates)`；默认走程序的栈）。
2. 闲谈配对（按好恶挑人，落单改散步）；转述传闻。
3. 差事结算（工作板产出）；斋食（厨房人手 → 足量/半餐；内核粮账的半餐减量按 5.1 的时序约束次日生效）。
4. 需求结算；想法；落轨迹。
5. 观察者所在场所的细节叙述——**只读**，不得改任何状态（**钩子 `lod.observe(engine, ctx, day, slot)`**）。
6. 偷食 → 见证 → 是否举报；巡夜查寮记空铺；脚本事件。
7. 典座清点（寅）；维那点名（卯、酉）；怠工被巡寮撞见；举报送达；裁断；午斋后公告。
8. `end_day` 的最后一步：**钩子 `persist.flush(engine, day)`**（每日落盘，只读，默认空操作）。

四个钩子的签名、调用点与约定见 `docs/NPC_ENGINE.md` 第 13 节；之后的步骤（C7 / C8 / C9 / 集成）只改各自的模块，不再改 `engine.py`。

### 6.2 NPC 事件类型（大写英文代码；负责人在 NPC_ENGINE.md 登记完整清单并给出中文渲染）

最少包含：`FOOD_THEFT`（偷食）、`THEFT_FOUND`（失窃）、`REPORT`、`CASE_OPENED`、`SANCTION`（处分）、`ABSENCE`（缺课）、
`SLACK`（怠工）、`BED_EMPTY`（夜不在寮）、`CONFESS`、`SUMMON`、`ANNOUNCE`、`ILL`、`RECOVER`、`CHAT`（可抽样记录）。
所有 NPC 事件的 payload 含 `wit`（见证人 id 列表）；`cause` 列串起因果链，供“为何”回溯。
**第一步只发其中七种**（偷食、失窃、举报、处分、缺课、怠工、夜不在寮）：多发一条会改变事件编号、进而改写以事件编号为键的随机抽签，
原型哈希就无法复现；其余代码已在 `events.py` 登记，何时发见 `docs/NPC_ENGINE.md` 第 6 节。

### 6.3 持久化

引擎状态常驻内存；**每日 end_day 落盘**到 `npc_*` 表（档案、需求、想法、见闻、好恶修正、案件、轨迹打包行），
控制台的历史查询（迹/闻/情/案）读这些表，“此刻”的查询读内存。
`persist.load` 能从表恢复引擎，且“跑 30 日 → 存 → 读 → 再跑 30 日”与“直接跑 60 日”哈希相同。

## 7. 原著 → 数据（tianl/canon，data/canon）——A 负责

九个阶段（计划 3.2）与产物格式见 `docs/CANON_SCHEMA.md`（A 负责人**第一件事**是写它，其余模块依赖它）。固定的几点：

* 断言 = 主体、属性、值 + 限定词 + 等级 + 出处 + 来源标签 + 复核（Wikidata 陈述模型）；属性清单封闭，取自计划 3.4。
* 来源标签四种：原著明文 / 原著推断（须写理由）/ 史料先验 / 种子生成。另加字段 `basis`：`text`（有原文指针）或 `recall`（凭模型记忆补的缺口，无原文可指）。
  **用户已提供三联版全文**（本地 `sources/tianlong.txt`，永不入库，见 DECISIONS 第三节）：第 3–4 阶段按回做滑动窗口抽取，每条断言带原文指针（`basis = text`）；
  只有缺口填补与开局状态推断才允许 `basis = recall` / `tag = infer`。验收报告里“证据指针有效率”“抽样精度”分别统计两类。
  证据只存指针（回、段、段内起止字位、段落哈希），**不存引文**；`tests/test_no_text_leak.py` 抽样断言原文长片段不出现在任何入库文件里。
* 人物的话只记成“某人这么说过”（叙述方式 = 人物之口），不直接当事实；真相与各人认知分两处存。
* 事件的 `time` 用世界日数（开局为 0，旧案为负）；前提与结果用封闭的操作词表（`at / alive / knows / flag / has` 等），
  情节事件库、按书重放、条件触发都吃这套词表。
* 流水线第 3、4 阶段的 LLM 调用封装在 `tianl/canon/llm.py`，带离线桩；可用环境变量 `ANTHROPIC_API_KEY`（及可选 `ANTHROPIC_BASE_URL`）。

## 8. 世界装配与全图（tianl/world）——B3/B4/控制台负责

* 全图骨架：所有抽取地点建成**端口**或**节点**，路线连通；十年运行钱守恒、物守恒（库存加在途）。与少林寺相邻的节点共用其边界账户。
* 展开处：少林寺、丐帮一处分舵、一处世家庄园。三处共用同一个 NpcEngine，差别只在 defs；来自原型（archetype）的定义不低于七成。
* 情节事件库：条件事件（沙盒模式下条件满足才触发）；“按书重放”模式把事件按时间线灌进世界，验证不违反物理规则。
* 玩家是世界里的一份普通档案，操纵者栏填 `player`；起点在少林寺。

## 9. 控制台（tianl/console）

`python3 -m tianl [--seed N] [--warm 日数] [--script 文件] [--db 文件]`。命令见计划 11.2：
`看 去 取 放 用 说 | 等 n | 谁在 | 查 | 迹 | 闻 | 情 | 案 | 为何 | 日报 | 跟`，另加 `帮助 我 时 图 退出`。
**控制台不存状态**：每条输出都由库里或引擎里的数据重新生成。`--script` 逐行执行并回显，用于文档与测试。

## 10. 里程碑 → 验收命令

| 里程碑 | 验收（均写入 docs/ACCEPTANCE.md） |
| --- | --- |
| M0 | `python3 -m unittest tests.test_core_defs` |
| A1–A4 | `python3 tools/canon_check.py`（指针有效率仅统计 basis=text；30 人召回；时间线无环/无人两地/死后不出场/路程可行；必填字段有来源） |
| B1 | 默认 `python3 -m unittest tests.test_b1_kernel tests.test_b1_defs tests.test_b1_branches tests.test_b1_params`：基准哈希 49f6ddde04dfa7f5、E1 与 E3 的日志数字、日志里没走到的分支与原型逐位对照、规则参数清单完备；`TIANL_SLOW=1` 再验 E2/E2b/E5/E6、十年基准、六个种子、人物与独有物测试、45 个参数各在其场景里起作用；与日志逐行比对用 `tools/shaolin_regress.py --all`（命令见 KERNEL_DEFS 第 7 节） |
| B2 | 各项需求月末均值 ≥ 20；设施容量按“人数×频次”反推 |
| B3 | 十年全图运行不变量违规 0 |
| B4 | 原型复用率 ≥ 70%；按书重放不违反任何物理规则 |
| C1 | 与 v0.2 的在场人数逐日一致；经济中立性（econ_hash 相同） |
| C2 | 预约越界 0；时间分配落在区间内（计划 6.6） |
| C3 | 实验 N1 两种结局可复现（无人代理 vs 监院派人代理） |
| C4 | 事发那个时辰只有见证人知情；传播曲线落在计划 12.2 区间 |
| C5 | 每起处分都能回溯到一条举报或认错 |
| C6 | 好友对里同寮/同方向/同岗的比例高于随机配对 |
| C7 | 十年后僧数在目标区间；岗位无长期空缺 |
| C8 | 观察者无关哈希相同；300 人一年 ≤ 60 秒 |
| C9 | LLM 桩返回非法输出时世界照常运行 |
| 总 | 计划 12.2 的九条“像真人”指标 |

## 11. 工作规则（给执行代理）

* 只改自己名下的文件；要改别人的文件，先在报告里写明原因再小改，并保证对方的测试仍绿。
* **不要执行 git 命令**（add/commit/push 由总控统一做）。
* 先读 `docs/PLAN.md` 相关章节与本文，再动手；动手前先把自己负责的文档骨架写出来。
* 每完成一块就跑相关测试；最终报告包含：做了什么、验收数字（原样贴）、没做/做不到/需要原文的部分、改动文件清单。
* 数字不好看时如实报告，不得调宽通过线、不得为过测试硬编码结果。
