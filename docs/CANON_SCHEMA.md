# 原著 → 数据：格式契约（CANON_SCHEMA）

本文是 A 段（`tianl/canon/`、`data/canon/`）的**格式契约**，其余模块与 A 段后续代理都依赖它。
计划见 `docs/PLAN.md` 第 3 节、4.6 节；工程规矩见 `docs/ARCHITECTURE.md` 第 0、7 节；原文（三联版，本地、永不入库）的处理见 `docs/DECISIONS.md` 第三节。
本文的格式由 `tianl/canon/schema.py` 实现并校验（`tests/test_canon_schema.py` 会核对本文第 5 节的属性表与代码里的注册表一致）。
**改格式必须先改本文再改代码，且只追加不改名。**（v2 有了原文：第 0、2、11、12、14 节按“按回抽取”改写，新增第 15、16 节“文本版面与规范化”“工具用法”；格式本身只追加。）

## 0. 取证方式与诚实声明（所有产出适用）

1. **有原文了。** 用户提供了《天龙八部》三联版全文（本地 `sources/tianlong.txt`，UTF-8、LF，永不入库；见 DECISIONS 第三节与第 15 节的版面约定）。
   第 3–4 阶段**按回做滑动窗口**：每次只读一个窗口（几段）原文，产出的每条断言、事件、秘密、身份都带原文指针（`basis = text`）。
2. **证据只存指针，不存引文。** 指针 = `[回,段,起,止,哈希]`（4.4）。抽取代理写证据时**不必算字位与哈希**，写**锚点**：
   `[回,段,"锚点"]` 或（锚点在段内不唯一时）`[回,段,"锚点",第几次]`——锚点是该段里的一小段原文（1–20 字），只用来定位；
   写完运行 `tools/canon_resolve.py FILE…`，它把锚点**原地改写成指针并丢弃锚点**，同时给有证据的行补 `"b":"text"`（第 16 节）。
   终稿里**不得残留锚点形式**（`canon_check --evidence` 与 `canon_text verify-evidence` 会拦）。
3. **`basis = recall` 只用于缺口填补与开局状态推断**（计划 3.5：原著没给、靠模型对原著或史料的记忆补的字段；开局第 0 日的状态）。
   这类行的 `evidence` 必须为空（`tag = infer` 的要写 `why`）。其余一律 `basis = text`，`text` 的行必须有 ≥ 1 条能在原文取回的有效指针。
   验收时分开统计：“证据指针有效率”与“抽样精度”只统计 `basis = text` 的行，`recall` 的另列，不混入通过线。
4. **诚实声明保留**：抽取与复核都是**模型代理**做的判断（计划里的“人工复核”由独立代理代替，报告里照实写）；原文没有明说、只能推断的写 `tag = infer` + `why`；
   记不准或原文含糊就标 `rv = doubt`（存疑）并降到 `r = norm`，或者干脆不写、进缺口表；**宁可存疑，不要编造**。
   年龄、日数、路程这类数字尤其如此：原文没给就进缺口表（`fill = ["prior"]` 或 `["ask"]`），不要硬凑。
5. **仓库里不得出现原著原文**：证据只存指针、说话特征只存标签（≤ 12 字，不含引号与句读）；任何字符串字段不超过 120 个字，校验器会拦；
   `tests/test_no_text_leak.py` 从规范化原文随机取 400 个 16 字窗口，断言它们不出现在仓库任何入库文件里（长期保留的硬防护）。
   `out/`（导出的各回文本、提及表）与 `sources/` 被 .gitignore 忽略，不入库。
6. 人物嘴里说的事只记成“某人这么说过”（`m = speech`），不直接当事实；真相与各人认知分两处存（断言表 / 秘密登记表）。

## 1. 稳定编号

形如 `类型:canon:名`。**同一实体在所有分区、所有文件里必须是同一个编号。**

| 类型 | 编号 | 例 |
| --- | --- | --- |
| 人物 | `person:canon:<拼音连写，无声调>` | `person:canon:qiaofeng` |
| 地点 | `place:canon:<拼音>` | `place:canon:shaolinsi` |
| 组织 | `org:canon:<拼音>` | `org:canon:gaibang` |
| 物 | `item:canon:<拼音>` | `item:canon:daoyin`（示意） |
| 武学 | `martial:canon:<拼音>` | `martial:canon:liumaishenjian` |
| 文书 | `document:canon:<拼音>` | `document:canon:yijinjing` |
| 事件 | `event:canon:<短语>` | `event:canon:yanmenguan_jiu_an` |
| 秘密 | `secret:canon:<短语>` | `secret:canon:qiaofeng_shishi` |

规则：

* **实体编号**（前六类）：名字部分只含 `a-z0-9`，不含下划线；用**最常用称呼**的拼音连写。乔峰与萧峰是同一人，只有一个编号 `person:canon:qiaofeng`，“萧峰”记作别名。
  ü 一律写 `v`（吕 → `lv`），轻声、儿化不写，多音字按书中读法（童姥 → `tonglao`）。
* **重名/拼音冲突**加数字后缀，先登记者保持原样：第二个 → `…:wang2`，第三个 → `…:wang3`。后缀由**普查产物里先出现的那条**定下，之后任何文件都沿用。
* **事件/秘密编号**的“短语”是几个拼音词用下划线连起来（`[a-z][a-z0-9_]*`），要能一眼看出是哪件事。
* 类型前缀必须与登记行的 `type` 一致；不同类型可以同名（少林寺既是 `org` 又是 `place`），各有各的编号。
* 编号一经发布不改名；要废弃就在登记行 `note` 里写“并入 X”，并保留旧行直到所有引用改完。

## 2. 文件布局与按回产出

```
data/canon/
  census/p1.jsonl p2 p3 p4 c5 c6a c6b c6c   普查登记行（第 3 节）。分区见第 12 节
  entities.jsonl                  canon_merge 的合并结果（第 3.3 节）。不手写
  census_conflicts.txt            合并冲突报告。不手写
  mention_counts.tsv              canon_names mentions 的汇总：实体、回、次数（按实体与回排序；不含原文）
  text_manifest.json              文本清单：规范化文本的哈希与各回计数（第 15 节；不含原文）
  assertions/ch00.jsonl … ch52.jsonl   断言，紧凑 JSONL（第 4 节），按回产出
  events/chNN.jsonl …             事件（第 7 节）
  secrets/chNN.jsonl …            秘密登记（第 8 节）
  identities/chNN.jsonl …         “以某身份出现”（第 6 节）
  gaps/*.jsonl                    缺口（第 9 节）：文件名自定（chNN.jsonl 或按阶段命名）
  qa/*.jsonl                      标准问答（第 10 节）
  routes.jsonl                    可选：路线表，行 {"a":地点,"b":地点,"slots":时辰数}（也可直接写成地点的 route 断言）
  trait_words.json                性格词映射（第 13 节）
```

* 每个目录也可以是单个文件 `data/canon/<name>.jsonl`（`canon_check` 两种都认）。目录里的所有 `*.jsonl` 按文件名排序后合并读取。
  上一版的 `census/c1…c6.jsonl`、`assertions/c1…c6.jsonl` 文件名仍然认（只追加不改名）。
* **JSONL 约定**：一行一个 JSON 对象；空行与以 `#` 开头的行忽略；UTF-8；不要 BOM。
* **按回产出**：从第 N 回的窗口里抽到的断言、事件、秘密、身份写进 `…/chNN.jsonl`（回号两位，`ch00` 卷首、`ch01`–`ch50` 正文、`ch51` 后记、`ch52` 附录）；
  证据指针指向本回（也可指向相邻回）。**同一事实可以在多回里各出现一次**：重复（相同主体、属性、值、限定词、叙述方式，或同编号同内容）
  **只是警告**，第 6 阶段合并证据；同编号但内容不同才是错误。事件、秘密编号全库唯一。
* **谁写什么**：普查按第 12 节分区（人物按首见回）；断言不再按“主体的归属分区”写，而是**谁读到哪回谁写哪回**。
* 提及表等由原文生成的中间产物放 `out/canon/`（被 .gitignore 忽略），不入库；入库的只有 `mention_counts.tsv` 与 `text_manifest.json`。

## 3. 实体登记行（提及普查产物）

```json
{"id":"person:canon:qiaofeng","type":"person","name":"乔峰","aliases":["萧峰","北乔峰","乔帮主"],"note":"丐帮前任帮主；契丹人萧峰"}
```

| 字段 | 含义 |
| --- | --- |
| `id` | 编号（第 1 节），类型前缀必须与 `type` 一致 |
| `type` | `person` 人物 / `place` 地点 / `org` 组织 / `item` 物 / `martial` 武学 / `document` 文书 |
| `name` | 规范名（最常用称呼），同类型内唯一 |
| `aliases` | 别名、称呼、称号、法名、外号；字符串数组；不含 `name` 本身 |
| `note` | 一句话说明（≤ 120 字），用于人工区分重名 |

* 别名可以写成对象 `{"name":"老爷子","ambiguous":true}`：表示这个称呼在书里本来就指不止一个实体（如“王夫人”“老爷子”“大哥”）。
  普查合并时，**别名同时指向多个实体 = 冲突，除非该别名在某个实体上带 `ambiguous: true`**。合并产物里这些别名仍在 `aliases` 中，另有 `amb` 数组列出带歧义标记的别名。
* 冲突的判定范围是（类型，称呼）：不同类型之间同名不算冲突。
* **别名只收书里真有的称呼**，不收单字（“峰”“誉”），不收泛称（“少年”“老者”），不确定的不写。

### 3.3 合并规则（`tools/canon_merge.py`）

`data/canon/census/*.jsonl` → `data/canon/entities.jsonl`（按 `id` 排序）：

1. 同编号：别名取并集，`note` 去重后用“；”连接；**名字不一致 = 冲突**；类型不一致 = 冲突。
2. 同名（同类型）不同编号 = 冲突。
3. 一个称呼（名或别名）同时指向多个实体 = 冲突，除非它在某实体上带 `ambiguous`。
4. 格式错误的行也计入冲突。
5. 冲突写 `data/canon/census_conflicts.txt`；退出码 0 = 无冲突，1 = 有冲突。

## 4. 断言

### 4.1 完整格式（内存与程序用）

```json
{"id":"a:3f9c1e07b2aa","subject":"person:canon:duanyu","property":"father","value":"person:canon:duanyanqing",
 "qualifiers":{},"rank":"pref","mode":"narrator","tag":"text","why":"","basis":"recall","evidence":[],
 "reviewed":null,"note":""}
```

| 字段 | 含义 | 取值 |
| --- | --- | --- |
| `id` | 断言编号 | 缺省时由内容算出：`a:` + sha256(主体、属性、值、限定词、叙述方式)前 12 位；也可手写 `[A-Za-z0-9_.:-]{1,40}`（问答集要引用的断言建议手写） |
| `subject` | 主体 | 已登记实体的编号 |
| `property` | 属性 | 封闭清单（第 5 节），不得用“派生”属性 |
| `value` | 值 | 类型由属性决定：entity / string / int / day / bool；表示“明确没有”写 `"none"`（仅限 `org`、`master`、`kin_other`） |
| `qualifiers` | 限定词 | 封闭键集（4.3） |
| `rank` | 等级 | `pref` 首选 / `norm` 普通 / `dep` 作废（后文揭穿的说法，保留不删） |
| `mode` | 叙述方式 | `narrator` 叙述者陈述 / `speech` 人物之口 / `memory` 回忆 / `hearsay` 传闻 |
| `tag` | 来源标签 | `text` 原著明文 / `infer` 原著推断（**须写 `why`**）/ `prior` 史料先验 / `seed` 种子生成 |
| `why` | 推断理由 | `tag = infer` 时必填，≤ 120 字 |
| `basis` | 依据 | `text`：有原文指针（抽取的默认）；`recall`：凭记忆补缺口或推断开局状态，无原文可指（第 0 节第 3 条） |
| `evidence` | 出处，可多条 | 原文指针（4.4）；`basis = recall` 时必须为空，`basis = text` 时至少一条 |
| `reviewed` | 复核 | `null` 或 `{"verdict":"sup|rej|doubt","by":"machine|human:名|model:名"}`：sup 支持 / rej 不支持 / doubt 存疑 |
| `note` | 备注 | ≤ 120 字，写存疑原因之类 |

**一致性规则**（校验器逐条检查）：

* `mode` 不是 `narrator` 的断言，等级只能是 `norm` 或 `dep`，不得是 `pref`；`speech`、`memory` 必须带限定词 `speaker`。
* 裁决次序：叙述者陈述 > 多人一致的说法 > 单人说法；后文揭穿的真相 > 早先的表象（被揭穿的那条改 `dep`，不删）。
* 单值属性：同一主体同一属性的 `narrator` 模式、`pref` 等级断言，限定词（时间段）重叠就是冲突。
* 首选断言须有证据——对 `basis = text` 的行成立（至少一条能在原文取回的有效指针）；`basis = recall` 的行（缺口填补、开局状态推断）无原文可指，不受此限，验收时另列。
* `rv = rej` 的断言只能是 `dep`，且不进入后续阶段。

### 4.2 紧凑 JSONL（写文件用，几千行）

键名短、全 ASCII，**省略的字段取默认值**：`r`=`pref`、`t`=`text`、`b`=`recall`、`e`=`[]`、`m`=`narrator`、`q`=`{}`。

| 完整键 | 紧凑键 | 省略时 | 备注 |
| --- | --- | --- | --- |
| `id` | `i` | 由内容算出 | |
| `subject` | `s` | 必填 | |
| `property` | `p` | 必填 | |
| `value` | `v` | 必填 | |
| `qualifiers` | `q` | `{}` | |
| `rank` | `r` | `pref` | 值 `pref` `norm` `dep` |
| `mode` | `m` | `narrator` | 值 `narrator` `speech` `memory` `hearsay` |
| `tag` | `t` | `text` | 值 `text` `infer` `prior` `seed` |
| `why` | `w` | 空 | |
| `basis` | `b` | `recall` | 值 `text` `recall` |
| `evidence` | `e` | `[]` | 数组的数组 `[[回,段,起,止,"哈希"],…]` |
| `reviewed.verdict` | `rv` | 未复核 | 值 `sup` `rej` `doubt` |
| `reviewed.by` | `rb` | `machine`（有 `rv` 时） | |
| `note` | `n` | 空 | |

例（紧凑，一行一条；数字仅演示格式）：

```jsonl
{"s":"person:canon:qiaofeng","p":"org","v":"org:canon:gaibang","q":{"from":-3600}}
{"s":"person:canon:qiaofeng","p":"master","v":"person:canon:wangjiantong"}
{"s":"person:canon:duanyu","p":"father","v":"person:canon:duanzhengchun","m":"speech","q":{"speaker":"person:canon:duanyu"},"r":"dep","n":"段誉自以为；后文揭穿"}
{"s":"person:canon:duanyu","p":"father","v":"person:canon:duanyanqing","t":"infer","w":"后文刀白凤的交代与叙述者的印证","i":"dy_father"}
{"s":"person:canon:zhongling","p":"master","v":"none","rv":"doubt","n":"记忆中无明确师承，待核"}
```

**证据写锚点**：`e` 里的每一项既可以是指针 `[回,段,起,止,"哈希"]`，也可以是锚点 `[回,段,"锚点"]` / `[回,段,"锚点",第几次]`；
`tools/canon_resolve.py` 把锚点原地改写成指针并补 `"b":"text"`（第 16 节）。事件、秘密、身份行也接受紧凑键 `b`（= `basis`）与 `e`（= `ev`）。
程序里用 `tianl.canon.schema.expand_assertion / compact_assertion` 互转，往返不丢信息。读文件时每行若含键 `subject` 视为完整格式，否则视为紧凑格式；两种可以混在一个文件里。
也接受用中文标签写枚举值（“首选”“原著推断”“人物之口”“支持”……），读入时规范成代码。

### 4.3 限定词（封闭键集）

| 键 | 值类型 | 含义 |
| --- | --- | --- |
| `from` | day | 起始日（世界日数，见 7.4） |
| `to` | day | 终止日 |
| `at` | entity(place) | 发生地点 |
| `speaker` | entity(person) | 说话人/回忆者（`mode = speech/memory` 必填） |
| `via` | entity 或字符串 | 得知途径：人物、文书编号，或 `self`（亲历）/`rumor`（传闻） |
| `grade` | string | 武学高下：`peak` 登峰造极 / `top` 一流 / `mid` 二流 / `low` 粗浅 / `partial` 学而未全 / `unk` 不详 |
| `org` | entity(org) | 职位所属的组织（`post` 用） |
| `rel` | string | 关系词/地形词，≤ 12 字，如“舅父”“杀父之仇”“山路” |
| `target` | entity | 志向的对象（`ambition` 用） |
| `slots` | int | 路程：常人最少需要的时辰数（`route` 用） |
| `lv` | int | 层级序，1 最高（`post_def` 用） |

### 4.4 证据指针

```json
{"ch":3,"para":12,"start":5,"end":9,"hash":"0f3a9c2b7d41e8a6"}
```

紧凑写法 `[3,12,5,9,"0f3a9c2b7d41e8a6"]`。含义：第 `ch` 回第 `para` 段（均从 1 起；第 0 回是正文前的卷首文字），**段内**第 `start` 到 `end` 个字（0 起，左闭右开，按规范化后的字符计），`hash` 是该段规范化文本 sha256 的前 16 位。
`tianl.canon.text.TextStore.get_span(ptr)` 取回原字并校验哈希；哈希或范围不符即报错。句子的稳定编号是 `c{回}p{段}s{句}`（如 `c3p12s2`）。
回、段、句的切法与规范化规则见第 15 节；**指针的“回、段、字位”只对规范化后的文本有意义**，所以 `text_manifest.json` 记着建指针时那份原文的指纹，换版本会被发现。

## 5. 封闭属性清单

“内核要什么字段才抽什么”（计划 3.1）：每个属性写明它喂给内核的哪张表。
表头：键（ASCII）｜中文标签｜值类型｜多值｜喂给｜说明。值类型里的 `entity(…)` 给出值允许的实体类型。**标“派生”的属性由编译推出，不得写断言。**
“喂给”的缩写：档案 / 关系 / 性格 / 认知 / 地点树 / 路线 / 组织 / 岗位 / 规范 / 独有物 / 文书 / 武学条目。

人物的**姓名、别名**在登记行里（第 3 节），不重复写断言。

### 5.1 人物（主体 `person`）

| 键 | 中文 | 值类型 | 多值 | 喂给 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `gender` | 性别 | string：`male` `female` | 否 | 档案 | |
| `age_at_open` | 开局年龄 | int（岁，约数） | 否 | 档案 | 不确定就进缺口表，别硬填；生年 = 开局日数 − 年龄×360 |
| `age_hint` | 年龄线索 | string 标签 | 否 | 档案 | 如“少年”“中年”“老者”，≤ 12 字 |
| `native` | 籍贯 | entity(place) | 否 | 档案 | |
| `ethnic` | 族属 | string 标签 | 否 | 档案 | 如“汉”“契丹”“党项”“吐蕃”“鲜卑”，≤ 12 字（辽人、宋人之别靠它） |
| `org` | 门派/所属组织 | entity(org)，可 `none` | 是 | 档案、组织 | 限定词 `from` `to`；已离开的写 `to` |
| `generation` | 辈分 | string | 否 | 档案、组织 | ≤ 12 字 |
| `post` | 职位 | string | 是 | 岗位 | 限定词 `org`（必写）`from` `to` |
| `father` | 父 | entity(person) | 否 | 关系 | 亲生父；养父等写 `kin_other` + `rel` |
| `mother` | 母 | entity(person) | 否 | 关系 | |
| `spouse` | 配偶 | entity(person) | 是 | 关系 | 限定词 `from` `to` |
| `sibling` | 同胞兄弟姊妹 | entity(person) | 是 | 关系 | 同父同母 |
| `half_sibling` | 异母/异父兄弟姊妹 | entity(person) | 是 | 关系 | |
| `kin_other` | 其他亲属 | entity(person)，可 `none` | 是 | 关系 | 限定词 `rel` 写关系词（“舅父”“养父”“表妹”） |
| `master` | 师承 | entity(person)，可 `none` | 是 | 关系 | 限定词 `from` `to`；徒弟由它反推，不另写 |
| `sworn` | 结义 | entity(person) | 是 | 关系 | 对称，写一边即可 |
| `feud` | 仇怨 | entity(person) | 是 | 关系 | 限定词 `rel` 写由头（“杀父之仇”），`from` |
| `trait` | 性格词 | string（词表见第 13 节） | 是 | 性格 | 一个断言一个词；映射成五项刻度的增减 |
| `ambition` | 志向 | string：`revenge` 寻仇 `seek_kin` 寻亲 `seek_art` 求艺 `seek_item` 求物 `restore` 复国/复兴 `keep_precept` 守戒 `pursue` 追随或痴恋 `dominate` 称霸求名 `protect` 守护 `reconcile` 止战 `other` | 是 | 性格、认知 | 限定词 `target` 写对象；志向会变成一个常驻的行为包 |
| `martial` | 会的武学 | entity(martial) | 是 | 武学条目 | 限定词 `grade`；高下按 4.3 的枚举 |
| `might` | 武功总评 | string：`peak` `top` `mid` `low` `none` | 否 | 武学条目 | 结果级打斗用（计划 13 第 7 问） |
| `speech` | 说话特征 | string 标签（≤ 12 字，无引号句读） | 是 | 档案 | 如“文绉绉”“自称老衲”；**不存对白原文** |
| `at_open` | 开局时所在地 | entity(place) | 否 | 档案 | **必含。** 开局 = 世界第 0 日，第一回之前 |
| `alive_at_open` | 开局时是否在世 | bool | 否 | 档案 | **必含。** |
| `death_day` | 卒日 | day | 否 | 档案、认知 | 开局前去世者必写（旧案取负） |
| `home` | 常驻场所 | entity(place) | 否 | 档案 | |
| `trade` | 营生/修行方向 | string 标签 | 是 | 档案 | 如“习武”“读经”“经商”，≤ 12 字 |
| `apprentice` | 徒弟 | 派生 | — | 关系 | 由 `master` 反推 |
| `child` | 子女 | 派生 | — | 关系 | 由 `father` `mother` 反推 |
| `holds` | 持有物 | 派生 | — | 独有物 | 由物的 `holder` 反推 |
| `knows` | 所知 | 派生 | — | 认知 | 由秘密登记（`knowers_at_open`）与事件的 `learn` 结果推出 |

### 5.2 地点（主体 `place`）

| 键 | 中文 | 值类型 | 多值 | 喂给 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `place_kind` | 地点类型 | string：`region` `city` `town` `mountain` `valley` `water` `temple` `manor` `palace` `pass` `building` `cave` `island` `road` `other` | 否 | 地点树 | |
| `parent` | 上级 | entity(place) | 否 | 地点树 | 层级：天下 → 国/路 → 城/山 → 院/殿 |
| `route` | 通往 | entity(place) | 是 | 路线 | 限定词 `slots`（常人最少时辰数）、`rel`（地形）；无向，写一边即可 |
| `func` | 功能 | string 标签 | 是 | 地点树 | 如“集会”“隐居”“囚禁”，≤ 12 字 |
| `owner_org` | 归属 | entity(org) | 是 | 地点树、组织 | 限定词 `from` `to` |
| `access` | 出入限制 | string（≤ 40 字的转述） | 是 | 地点树 | 如“女子不得入内”“须持令”；转述，不引原话 |

### 5.3 组织（主体 `org`）

| 键 | 中文 | 值类型 | 多值 | 喂给 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `org_kind` | 类型（原型） | string：`temple` 寺院 `gang` 帮会 `manor` 世家庄园 `yamen` 王府官衙 `sect` 隐居门派 `shop` 店铺行商 `other` | 否 | 组织 | 计划 4.4 的六种原型 |
| `parent_org` | 上级组织 | entity(org) | 否 | 组织 | |
| `post_def` | 职位 | string | 是 | 岗位 | 限定词 `lv`（层级序，1 最高） |
| `rule` | 规矩 | string（≤ 60 字的转述） | 是 | 规范 | |
| `punish` | 处罚 | string（≤ 60 字的转述） | 是 | 规范 | 按轻重一条一个 |
| `seat` | 据点 | entity(place) | 是 | 组织 | 限定词 `from` `to` |
| `org_rel` | 与别派的关系 | entity(org) | 是 | 组织 | 限定词 `rel`：`ally` `hostile` `rival` `subordinate` `kin` `neutral` |

### 5.4 物与文书（主体 `item` 或 `document`）

| 键 | 中文 | 值类型 | 多值 | 喂给 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `item_kind` | 物的类别 | string：`weapon` `medicine` `token` `treasure` `tool` `food` `other`（仅 `item`） | 否 | 独有物 | |
| `doc_kind` | 文书的类别 | string：`letter` `manual` `ledger` `certificate` `map` `scroll` `other`（仅 `document`） | 否 | 文书 | |
| `holder` | 归属与转手 | entity(person、org、place) | 是 | 独有物、文书 | 限定词 `from` `to`；转手一次一条，开局持有人是 `to` 缺省或晚于 0 的那条 |
| `location` | 藏处 | entity(place) | 是 | 独有物、文书 | 限定词 `from` `to` |
| `use` | 功用 | string 标签 | 是 | 独有物 | ≤ 12 字 |
| `reveals` | 读到即知 | entity(secret) | 是 | 文书、认知 | 仅 `document`：读到它就得知相应的秘密 |
| `teaches` | 记载武学 | entity(martial) | 是 | 文书、武学条目 | 仅 `document` |
| `author` | 作者/来源 | entity(person) | 否 | 文书 | 仅 `document` |

### 5.5 武学（主体 `martial`）

| 键 | 中文 | 值类型 | 多值 | 喂给 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `m_kind` | 类别 | string：`palm` `fist` `finger` `blade` `sword` `weapon` `neigong` `qinggong` `dugong` `misc` | 否 | 武学条目 | |
| `of_org` | 所属 | entity(org) | 是 | 武学条目 | 门派武学 |
| `creator` | 创制者 | entity(person) | 是 | 武学条目 | |
| `power` | 层级 | string：`peak` `top` `mid` `low` | 否 | 武学条目 | |
| `limit` | 传授限制 | string（≤ 60 字的转述） | 是 | 武学条目 | |
| `counter` | 相克 | entity(martial) | 是 | 武学条目 | |
| `taboo` | 禁忌 | string（≤ 60 字的转述） | 是 | 武学条目 | |
| `knowers` | 谁会 | 派生 | — | 武学条目 | 由人物的 `martial` 反推 |

### 5.6 事件与认知（不走断言表）

* **事件**（计划 3.4：参与者及角色、地点、时间区间、前提、结果）→ 第 7 节的事件表 → 情节事件库。
* **认知**（谁在何时得知何事、信真还是信假、从谁那里得知）→ 第 8 节的秘密登记表（开局状态）+ 事件的 `learn` 结果（运行中追加）→ 秘密登记、各人见闻。`knows` 是派生的。
* **易容与化名**→ 第 6 节。

## 6. “以某身份出现”表

易容者做的事，目击者记在他扮的那个人头上；见闻存“看见的身份”，事件日志存真身，两者由这张表连接（计划 8.4）。

```json
{"person":"person:canon:azhu","as_name":"某某","kind":"disguise","when":{"start":120,"end":130},"where":"place:canon:xxx",
 "believed_by":["person:canon:a","*"],"as_person":"person:canon:b","ch":[20,21],"ev":[],"tag":"text","basis":"recall"}
```

| 字段 | 含义 |
| --- | --- |
| `person` | 真身（人物编号），必填 |
| `as_name` | 以什么名号/面目出现，必填 |
| `kind` | `alias` 化名别称（无欺瞒）/ `disguise` 易容化装 / `title` 头衔称号 / `false_identity` 隐瞒真实身份的假身份 |
| `when` | `{"start":日,"end":日}`，可为 `null`（不详） |
| `where` | 地点编号，可为 `null` |
| `believed_by` | 把这个身份当真的人物编号数组；`"*"` 表示当时在场的所有人 |
| `as_person` | 可选：所扮的是另一个已登记人物时写它的编号 |
| `ch` | 可选：`[起回, 止回]`，限定第 2 阶段消歧时这个称呼生效的回数范围 |
| `ev` `tag` `basis` `rv` `note` | 同断言（缺省 `ev=[]`、`tag=text`、`basis=recall`） |

## 7. 事件

事件是**情节事件库、按书重放、条件触发**三者共同的输入。每行一个事件，写在 `events/*.jsonl`：

```json
{"id":"event:canon:yanmenguan_jiu_an","name":"雁门关旧案","kind":"history",
 "participants":[{"person":"person:canon:xuanci","role":"leader"},{"person":"person:canon:xiaoyuanshan","role":"victim"}],
 "place":"place:canon:yanmenguan","time":{"start":-10800,"end":-10800,"approx":true},
 "pre":[{"op":"alive","person":"person:canon:xiaoyuanshan"}],
 "eff":[{"op":"die","person":"person:canon:xiaoyuanshan"}],
 "after":[],"ev":[],"tag":"text","basis":"recall","rv":"doubt","note":"示例，数字与参与者待核"}
```

### 7.1 字段

| 字段 | 含义 |
| --- | --- |
| `id` | `event:canon:<短语>`，全库唯一 |
| `name` | 事件名，≤ 40 字 |
| `kind` | `plot` 情节（开局之后，`time.start ≥ 0`）/ `history` 历史（开局之前，`time.end ≤ -1`，只用来交代现状，引擎不触发） |
| `participants` | `[{"person":人物编号,"role":角色}]`；角色 `actor` 主动 / `target` 受事 / `victim` 受害 / `ally` 助力 / `witness` 见证 / `leader` 带头 / `mastermind` 主谋 / `other` |
| `place` | 地点编号，可为 `null` |
| `time` | `{"start":日,"end":日,"approx":bool}`；`end` 缺省 = `start`，`approx` 缺省 = `false`；世界日数，见 7.4 |
| `pre` | 前提数组（7.2），全部成立才可触发（与）；可为空 |
| `eff` | 结果数组（7.3），按顺序一次性生效；可为空 |
| `after` | 可选：必须先于本事件发生的事件编号数组（先后关系；全库须无环） |
| `ev` `tag` `why` `basis` `rv` `rb` `note` | 同断言（`ev`=证据，缺省 `[]`） |

### 7.2 前提的封闭操作词表

形状：`{"op": 操作名, …参数}`。任何一个前提都可以加 `"not": true` 取反（`alive`/`dead` 本身互补，不必加）。

| op | 参数 | 成立条件 |
| --- | --- | --- |
| `at` | `person`, `place` | 此人此刻在该地点**或其任一下级地点**内（按地点树包含） |
| `alive` | `person` | 此人在世 |
| `dead` | `person` | 此人已死 |
| `knows` | `person`, `what`, 可选 `belief` | 此人知道 `what`（`secret:canon:…` 或 `event:canon:…`，后者表示“知道那件事发生过”）；给 `belief` 时还要信的版本相符 |
| `flag` | `name`, `value` | 世界状态标志 `name` 的当前值等于 `value`；`value` 缺省 `true`；标志名 `[a-z][a-z0-9_]*` |
| `has` | `person`, `item` | 此人持有该物（`item:canon:…` 或 `document:canon:…`） |
| `in_org` | `person`, `org` | 此人是该组织成员 |
| `day_ge` | `n` | 当前世界日数 ≥ n |
| `day_le` | `n` | 当前世界日数 ≤ n |

### 7.3 结果的封闭操作词表

| op | 参数 | 效果 |
| --- | --- | --- |
| `move` | `person`, `place` | 此人移动到该地点 |
| `die` | `person`, 可选 `by` | 此人死亡；`by` 是凶手人物编号 |
| `learn` | `person`, `secret`, `belief`, 可选 `from` | 此人得知秘密（或事件）；`belief` 是 `truth`、该秘密 `versions` 里的版本键、或 `suspect`；`from` 是人物编号、文书编号、`self` 或 `rumor` |
| `give_item` | `item`, `to` | 物转到 `to`（人物、组织或地点编号） |
| `set_flag` | `name`, `value` | 设置世界状态标志；`value` 缺省 `true`（可为布尔、整数或不含空白的短字符串） |
| `join_org` | `person`, `org` | 入组织 |
| `leave_org` | `person`, `org` | 离组织 |
| `relation` | `a`, `b`, `kind`, `delta` | 好恶修正：`kind` ∈ `affinity` 好恶 / `trust` 信任 / `feud` 仇怨 / `love` 情愫 / `master` 师徒 / `sworn` 结义 / `kin` 亲属；`delta` 为 −100 到 100 的整数 |

词表只追加不改名；加新操作须先改本节。所有编号参数必须是已登记实体（`knows`/`learn` 的秘密须在秘密表里，事件须在事件表里）。

### 7.4 时间约定

* 世界日数：**开局 = 第 0 日**（对应原著第一回之前）；原著里更早的事（旧案）取负；一年 360 日，一月 30 日。
* 换算：N 年前 ≈ −360×N；生年 ≈ −360×年龄。书里多半没有确切日期，**一律在 `time.approx` 里标 `true`**，数字别装精确。
* 同一事件跨多日写 `start`/`end`；一日内的事 `end = start`。

### 7.5 时间线校验（`canon_check --timeline`）

1. `after` 构成的先后关系无环；若两端都有时间，`前者.start ≤ 后者.start`。
2. 无人在重叠的时间段出现在两个互不包含的地点：重叠超过一天一律报错；仅共享一天时，若路线表说明一日内走得到则放行，说明走不到则报错，没有路线信息则只警告。开局位置（`at_open`）按第 0 日算。
3. 死后不再出场：`die` 结果或 `death_day` 之后开始的事件里不得出现此人；`alive_at_open = false` 者不得出现在 `start ≥ 0` 的事件里；同一人不得有两次 `die`。
4. 有路线表时路程可行：同一人按时间排序的相邻两件事，若地点不同且路线表给出最短路程 `slots`，则间隔的时辰数（按 (后.start − 前.end + 1)×12 宽算）不得小于它。
5. 秘密的知情人都已登记：`knowers_at_open[].person`、`evidence_items`、事件里引用的人物、地点、物、秘密全部存在。

## 8. 秘密登记表

天龙世界里“谁知道什么”是硬数据。真相与各人认知分两处存；开局时 NPC 的见闻由这张表初始化，运行中由事件的 `learn` 追加。

```json
{"id":"secret:canon:qiaofeng_shishi","truth":"乔峰实为契丹人萧峰，萧远山之子",
 "versions":[{"key":"han","text":"乔峰是汉人，被丐帮前任帮主收养"}],
 "knowers_at_open":[{"person":"person:canon:xiaoyuanshan","believes":"truth","from":"self"},
                    {"person":"person:canon:qiaofeng","believes":"han","from":"self"}],
 "evidence_items":["document:canon:xxx"],"note":"","tag":"text","basis":"recall"}
```

| 字段 | 含义 |
| --- | --- |
| `id` | `secret:canon:<短语>` |
| `truth` | 真相，一句话（≤ 120 字），是转述不是引文 |
| `versions` | 可选：虚假或片面的版本 `[{"key":ASCII 键,"text":一句话}]`；键不得为 `truth`/`suspect` |
| `knowers_at_open` | 开局时的知情人 `[{"person":编号,"believes":"truth"｜版本键｜"suspect","from":人物编号｜文书编号｜"self"｜"rumor","since":可选日数}]` |
| `evidence_items` | 能证明它的物证（物或文书编号） |
| `note` `ev` `tag` `why` `basis` `rv` | 同断言 |

## 9. 缺口表（计划 3.5）

原著没给的字段逐项登记，写明填补办法：

```json
{"table":"archive","field":"age_at_open","subject":"person:canon:xxx","fill":["prior","ask"],"note":"原著只说“中年”"}
```

| 字段 | 含义 |
| --- | --- |
| `table` | 内核表：`archive` 档案 `relation` 关系 `trait` 性格 `cognition` 认知 `placetree` 地点树 `route` 路线 `org` 组织 `post` 岗位 `norm` 规范 `unique_item` 独有物 `document` 文书 `martial` 武学条目 `secret` 秘密 `event` 事件 |
| `field` | 属性键或字段名（ASCII） |
| `subject` | 可选：某个实体编号，或 `person:*` 这样的整类通配 |
| `fill` | 非空数组，取自 `prior` 史料先验 / `seed` 种子生成 / `ask` 问你（前两种都定不了、又影响玩法的才进“问你”） |
| `note` | ≤ 120 字 |

## 10. 标准问答集

用来回归：`{q, a, support:[断言编号]}`。

```json
{"id":"qa001","q":"乔峰是哪里人？","a":"契丹人","support":["qf_ethnic"]}
```

`support` 里的编号必须能在断言库里找到（所以被引用的断言要手写 `i`）；`q`、`a` 各 ≤ 120 字。

## 11. 30 人召回名单（固定）

`canon_check --recall` 逐个检查：这 30 人是否在登记表里；是否各有**门派**（`org`）、**师承**（`master`，作为主体）、**亲属**（`father` `mother` `spouse` `sibling` `half_sibling` `kin_other`，作主体或作值均可）的**叙述者模式、非作废**断言；明确没有的写 `"none"`（`org` `master` `kin_other`）。缺了列出，退出码 1。
“首见分区”按首见回划分（第 12 节）：姓名（或所列别名）在正文第 1–50 回里第一次出现的回，落在 p1 = 第 1–12 回、p2 = 第 13–25 回、p3 = 第 26–38 回、p4 = 第 39–52 回。
“首见回”是用姓名（及括号里的别名）在规范化原文里做字符串检索得到的，`tests/test_canon_realtext.py` 会复核。

| 人物 | 编号 | 首见分区 | 首见回 |
| --- | --- | --- | --- |
| 乔峰（萧峰） | `person:canon:qiaofeng` | p1 | 9 |
| 段誉 | `person:canon:duanyu` | p1 | 1 |
| 虚竹 | `person:canon:xuzhu` | p3 | 29 |
| 慕容复 | `person:canon:murongfu` | p1 | 12 |
| 王语嫣 | `person:canon:wangyuyan` | p1 | 12 |
| 阿朱 | `person:canon:azhu` | p1 | 11 |
| 阿紫 | `person:canon:azi` | p2 | 22 |
| 木婉清 | `person:canon:muwanqing` | p1 | 3 |
| 钟灵 | `person:canon:zhongling` | p1 | 1 |
| 段正淳 | `person:canon:duanzhengchun` | p1 | 2 |
| 保定帝（段正明） | `person:canon:baodingdi` | p1 | 6 |
| 刀白凤 | `person:canon:daobaifeng` | p1 | 7 |
| 段延庆 | `person:canon:duanyanqing` | p1 | 9 |
| 叶二娘 | `person:canon:yeerniang` | p1 | 4 |
| 云中鹤 | `person:canon:yunzhonghe` | p1 | 4 |
| 南海鳄神（岳老三） | `person:canon:nanhaieshen` | p1 | 2 |
| 鸠摩智 | `person:canon:jiumozhi` | p1 | 10 |
| 游坦之 | `person:canon:youtanzhi` | p2 | 19 |
| 天山童姥 | `person:canon:tianshantonglao` | p1 | 1 |
| 李秋水 | `person:canon:liqiushui` | p3 | 36 |
| 无崖子 | `person:canon:wuyazi` | p3 | 35 |
| 丁春秋 | `person:canon:dingchunqiu` | p1 | 10 |
| 苏星河 | `person:canon:suxinghe` | p3 | 29 |
| 玄慈 | `person:canon:xuanci` | p1 | 9 |
| 萧远山 | `person:canon:xiaoyuanshan` | p2 | 21 |
| 慕容博 | `person:canon:murongbo` | p1 | 9 |
| 康敏 | `person:canon:kangmin` | p2 | 23 |
| 全冠清 | `person:canon:quanguanqing` | p2 | 14 |
| 包不同 | `person:canon:baobutong` | p2 | 13 |
| 风波恶 | `person:canon:fengboe` | p2 | 14 |

共 30 人：p1 十九人、p2 七人、p3 四人、p4 零人。

## 12. 分区计划（普查）与按回抽取

普查先分区、并行；断言等随后**按回**抽取（第 2 节）。人物按**首见回**分区，其余按实体类型分区：

| 分区 | 范围 | 主要产出 |
| --- | --- | --- |
| **p1 人物·第 1–12 回首见** | 正文第 1–12 回里第一次出现的人物（含第 0 回卷首里出现的） | `census/p1.jsonl` 人物登记行（含上表 p1 十九人） |
| **p2 人物·第 13–25 回首见** | 第 13–25 回里第一次出现的人物 | `census/p2.jsonl`（含 p2 七人） |
| **p3 人物·第 26–38 回首见** | 第 26–38 回里第一次出现的人物 | `census/p3.jsonl`（含 p3 四人） |
| **p4 人物·第 39–52 回首见** | 第 39–50 回与后记（51）、附录（52）里第一次出现的人物 | `census/p4.jsonl` |
| **c5 地点** | **全部地名**，含层级（`parent`）、路线（`route`）、类型、功能、归属、出入限制 | 地点普查；地点主体的断言；`routes` |
| **c6a 组织** | 全部组织（门派、帮会、官府、世家……） | 组织普查；组织主体的断言；缺口表中的组织、规范类条目 |
| **c6b 武学** | 全部武学（招式、内功、绝技、毒功……） | 武学普查；武学主体的断言 |
| **c6c 物与文书** | 全部物（兵刃、药、信物、宝物）与文书（秘籍、书信、账簿……） | 物与文书普查；这两类主体的断言 |

约定：

* 普查先行（p1–p4、c5、c6a–c6c 并行），随后 `canon_merge` 合并；断言、事件、秘密在合并后的 `entities.jsonl` 上写，引用到别区的实体直接用统一编号。
* 某人物究竟算 p几，看他**第一次被提到的回**（姓名或任一别名；`canon_names mentions` 的提及表给得出）；拿不准的以 `mention_counts.tsv` 里该实体的最小回号为准。
* c5/c6a/c6b/c6c 是地点与其余实体类型的权威登记处；p1–p4 里用到而它们还没有的，可以登记同号同名的行（合并时去重，名字不一致会报冲突）。
* 缺口表、问答集写进 `gaps/*.jsonl`、`qa/*.jsonl`（文件名自定）。
* `canon_check --part p1` 同时圈住 `census/p1.jsonl` 与第 0–12 回的按回文件（`chNN.jsonl`）；`--part ch07` 只圈住第 7 回的文件。
* 抽取（第 3–4 阶段）的单位是“回”：一个回一个窗口序列（`tianl.canon.llm.iter_windows`，默认 4 段一窗、重叠 1 段），抽取代理用 `tools/canon_text.py export` 导出的 `chNN.txt` 阅读。

## 13. 性格词表 `data/canon/trait_words.json`

```json
{"version":1,
 "scales":{"D":"精进","S":"守戒","G":"合群","T":"馋","R":"刚正"},
 "words":{"鲁莽":{"D":0,"S":-10,"G":0,"T":0,"R":-5,"note":"…"}}}
```

* 五项刻度 0–100，基线 50；每个词是一组增减（整数，各项在 −30 到 +30 之间，缺省 0）。内核把某人所有性格词的增减加到基线上并夹到 0–100。
* 键固定为 `D` 精进、`S` 守戒、`G` 合群、`T` 馋、`R` 刚正（见 ARCHITECTURE 第 3 节）。注意 `T` 的含义是**起念的门槛低**（欲念重、易受诱惑），不是“饿得快”（计划 6.3）。
* `trait` 属性的值应取自这张表；不在表里的词，`canon_check` 会警告（`--strict` 时报错）。要加词请在报告里提出，由 A 段负责人加。

## 14. 校验与工具

| 工具 | 用途 |
| --- | --- |
| `python3 tools/canon_text.py info\|export\|show\|find\|ptr\|verify-evidence\|manifest` | 原文与证据锚点工具（第 16 节） |
| `python3 tools/canon_resolve.py FILE…` | 把 JSONL 里的锚点 `[回,段,"锚点"]` 原地改写成指针，补 `"b":"text"`（第 16 节） |
| `python3 tools/canon_names.py mentions\|verify\|candidates` | 提及普查（`mention_counts.tsv`）、登记核对（0 命中/被吞/单字别名）、缺名检测（第 16 节） |
| `python3 tools/canon_merge.py` | 合并普查（第 3.3 节），退出码 = 冲突数是否为 0 |
| `python3 tools/canon_check.py --census DIR_OR_FILE` | 登记行格式、编号、重名 |
| `python3 tools/canon_check.py --assertions FILE_OR_DIR` | 断言：属性在封闭清单内、主体与值都是已登记实体、规则 4.1；重复只警告 |
| `python3 tools/canon_check.py --events FILE` / `--secrets FILE` | 事件（前提结果词表、引用完整）/ 秘密 |
| `python3 tools/canon_check.py --timeline` | 7.5 的五项综合检查 |
| `python3 tools/canon_check.py --recall` | 第 11 节的 30 人召回 |
| `python3 tools/canon_check.py --evidence` | 有原文时逐条核对指针：能取回、哈希相符；`basis=text` 的行须有 ≥ 1 条有效证据，`basis=recall` 的行证据须为空；统计指针有效率。没有原文只给提示（该节“跳过”，不算失败） |
| `python3 tools/canon_check.py --all` | 全部，汇总计数；`--part p1`/`--part ch07` 只跑某分区或某回的文件 |
| `python3 tools/canon_run.py --source FILE` | 第 0–2 阶段：规范化、各回统计、核对文本清单、提及普查、消歧、提及排名前 20；没有原文时给出提示，退出码 0 |

退出码：0 全部通过，1 有错误。警告不影响退出码。每个子命令都打印汇总计数（行数、错误数、警告数）。

## 15. 文本版面与规范化（第 0 阶段；实现 `tianl/canon/text.py`）

**输入**：`sources/tianlong.txt`（总控已从 GB18030 转成 UTF-8、LF；三联版全文）。载入时仍自动判别编码：UTF-8 严格解码（去 BOM），失败回退 GB18030（UTF-16 带 BOM 也认）。

**规范化规则（写死；改动须升 `NORMALIZER_ID` 并重生成清单）**，规则 id `canon-text-v2`：

1. CRLF / CR / 换页 / 垂直制表 → LF；去 BOM、零宽字符与其余控制字符（对三联版实测 0 处）。
2. **不做 NFKC，也不做 NFC**：全角字母数字、标点、异体字原样保留，字数口径因此稳定。
3. **去水印与分隔行**：论坛页分隔水印标记（全角星号夹字母的那一串）无论独立成行还是嵌在行尾，一律删去该标记（三联版共 178 处：177 行独立、1 处在行尾）；
   以 ☆/★ 开头并以 ☆/★ 结尾的整行（站点头尾，共 6 行）删去；由 `-` 或 `=` 组成、长度 ≥ 4 的分隔行删去（共 4 行）。
4. 每行去两端空白（含全角空格）。**段 = 非空行**，空行丢弃；段内字符不动。
5. 切回（三联版面，严格）：
   * 第 0 回 = 第一个回标题之前的卷首文字（“新序”“释名”，标题记作“卷首”）；
   * 回标题是**顶格**单独一行，形如“`<汉字数字> <标题>`”（数字与标题之间是空格，标题内部可有空格，如“十五 杏子林中 商略平生义”），序号必须依次为 1、2、……，
     **缺跳、重复或乱序一律报错**（`TextFormatError`），整本书必须正好 50 回（载入时 `--expect`，默认 50）；标题行本身不算段；
   * 顶格单独一行“后记” = 第 51 回；顶格以“附录”开头的行 = 第 52 回（标题取整行，如“附录 陈世骧先生书函”）；
   * 没有三联版标题时回退到旧的“第X回”版面（测试夹具用）；再没有则整篇当作第 1 回并警告。
6. **段、句编号都从 1 起**：段 `c{回}p{段}`，句 `c{回}p{段}s{句}`。
7. **句子切分**（固定；句号编号依赖它）：以 `。` `！` `？` 为句末（连续的算一个），其后紧跟的右引号/括号（`” ’ 」 』 ） ) 》 】 " '`）并入本句；
   省略号 `…`（含连续的 `……`）只在其后紧跟右引号/括号或位于段末时才算句末，句中停顿不切；末尾没有句末符的残余算一句。
8. **字数口径** = 各段字符数之和（不含换行与段首空白）。**段落哈希** = 规范化段落文本 UTF-8 的 sha256 前 16 位（十六进制小写）。
9. 性能：整书载入约 0.15 秒（目标 < 2 秒）；句子惰性切分。

**回的约定**：第 0 回卷首；第 1–50 回正文；第 51 回后记；第 52 回附录。三联版实测：正文 50 回，共 10922 段、40147 句、1248951 字（含卷首、后记、附录）。

**文本清单** `data/canon/text_manifest.json`（入库，**不含任何原文**，只有标题、哈希与计数）：

```json
{"format":1,"edition":"三联版","normalizer":"canon-text-v2","layout":"sanlian","text_sha256":"<64 位>",
 "totals":{"chapters":50,"paragraphs":10922,"chars":1248951},
 "removed":{"watermark_tokens":178,"site_lines":6,"separator_lines":4},
 "chapters":[{"ch":0,"title":"卷首","paras":43,"chars":7622,"sha16":"<16 位>"}, …]}
```

* `text_sha256` = 全书规范化文本的 sha256：全书文本 = 依回号升序，每回先一行 `#回号 标题`，再各段（每段以 LF 结尾）。
* 每回 `sha16` = 该回各段（每段以 LF 结尾，不含标题行）连成的文本的 sha256 前 16 位；`paras`、`chars` 是该回段数与字数（口径见上）。
* `TextStore.from_file(path, manifest='auto')` 与工具统一的载入入口 `text.load_book()` 载入时**核对清单**：不符时给出清晰提示（哪一回的段数/字数/哈希不符、是不是换了版本或规范化规则），
  并提醒已有证据指针的哈希可能失效；没有清单时提示用 `canon_text manifest --write` 生成。核对不符只警告，不中断（指针自己的哈希仍会逐条校验）。

## 16. 工具用法

所有工具默认读 `sources/tianlong.txt`（`--source` 改），按三联版面严格载入（`--expect 50`，测试夹具用 `--expect 0`），并核对 `data/canon/text_manifest.json`。
原文只在本地，工具的输出除 `export` 写进 `out/` 的文件与 `show` 外**不打印整段原文**。

### 16.1 `tools/canon_text.py`（读原文、造指针）

| 子命令 | 作用 |
| --- | --- |
| `info` | 各回标题 / 段数 / 句数 / 字数，规范化统计（去了多少水印、分隔行），全书规范化文本哈希 |
| `export [--ch SPEC \| --all] --out DIR` | 把各回导出成 `DIR/chapters/chNN.txt`（`DIR` 自己叫 `chapters` 时直接用它；默认 `out/canon/chapters`）。每行形如 `[c12p34] 段落文字`，行号即段号，供抽取代理用 Read 工具阅读。`SPEC` 写 `3` / `1-5` / `1,3,7-9`；`--all` 含第 0、51、52 回 |
| `show CH [--from P --to Q]` | 终端打印某回（或第 P 到 Q 段），格式同上 |
| `find 字符串 [--ch N]` | 全书（或某回）命中数、每回计数与命中位置 `c回p段@段内偏移`；**不打印整段**。`--limit N` / `--all` 控制每回列出多少 |
| `ptr CH PARA 锚点 [--nth K]` | 把一个 ≤ 20 字的锚点解析成指针 `[回,段,起,止,哈希]`（紧凑 JSON 打到 stdout）。锚点在段内不唯一时报错并列出各起点，用 `--nth K`（从 1 起，重叠的算不同次）指定 |
| `verify-evidence FILE\|DIR` | 核对文件里**全部**证据指针（`e` / `evidence` / `ev`）：能取回、哈希相符、取回非空；未解析的锚点算无效；汇总有效率；有无效则退出码 1 |
| `manifest [--write] [--check]` | 生成 / 核对 `data/canon/text_manifest.json` |

### 16.2 `tools/canon_resolve.py FILE…`（锚点 → 指针）

* 任何带证据的 JSONL（断言、事件、秘密、身份……）都适用；证据项允许写成 `[回,段,"锚点"]` 或 `[回,段,"锚点",第几次]`，与已解析的指针 `[回,段,起,止,"哈希"]` 可混写。
* 解析成功：整行原地改写，证据项换成指针（`[回,段,起,止,哈希]`，指针恰好覆盖锚点那几个字），**锚点丢弃，不留存引文**；重复的指针去重；给有证据的行补 `"b":"text"`（行里已有 `basis` 就改它）。
* 解析失败（锚点找不到 / 不唯一又没给第几次 / 锚点超过 20 字 / 回段不存在 / 已有指针取不回 / JSON 解析失败）：**该行一个字都不改**，列进错误清单（文件名:行号:原因，原因里列出出现次数与各起点），退出码 1。其余行照常改写。
* 空行与 `#` 注释行原样保留；未改动的行逐字节不变；`--dry-run` 只检查。重复运行是幂等的。

推荐工作流（抽取代理）：`export --ch N` → 读 `chNN.txt` → 写 `assertions/chNN.jsonl`（证据写锚点）→ `canon_resolve assertions/chNN.jsonl` → 修错误清单 → `canon_check --assertions … --evidence`。

### 16.3 `tools/canon_names.py`（提及普查与缺名检测）

| 子命令 | 作用 |
| --- | --- |
| `mentions [--entities PATH]` | 用实体登记（缺省 `data/canon/census/*.jsonl`，其次 `entities.jsonl`）的名与别名做**最长匹配**（从左到右、互不重叠；单字称呼不参与）。输出本地 `out/canon/mentions.tsv`（实体、回、段、起、止）与入库的 `data/canon/mention_counts.tsv`（实体、回、次数，按实体与回排序，带表头）。同名不同类型（少林寺的组织与地点）各计一份；真歧义称呼计入伪实体 `ambiguous:<称呼>` |
| `verify CENSUS_FILE [--only] [--strict]` | 逐实体、逐别名报告全书命中次数与首见回；标出：0 命中的名字/别名（**错误**，退出码 1）、被更长名字吞掉的别名（警告，给出主要被谁吞）、单字别名（警告）。“被吞”按整体登记表判断（`--only` 只用该文件自己的实体） |
| `candidates --type person\|place\|org\|martial\|item [--min N]` | 启发式找“全书高频但未登记”的名字，列出候选、没被已登记称呼盖住的命中数、句式/后缀次数、首见回、一个示例段编号（**不打印原文**）。人物用说话归属句式（X道/说道/笑道/叹道/喝道/问道/答道/叫道/冷笑道/低声道……后接冒号或逗号）；其余用常见后缀字（山 城 寺 庄 谷 岛 宫 府 关 洞 江 河 湖 林 村 镇 州 国 / 帮 派 宗 教 会 门 / 掌 拳 剑 功 指 法 刀 腿 神功 大法 / 丹 散 令 牌 符 珠 图 谱 琴 ……）。已登记的（含别名）不再列出；结果是线索不是结论，要人看 |

### 16.4 `tools/canon_run.py --source FILE`

第 0–2 阶段：规范化 → 打印各回段数/字数表并核对文本清单（`--write-manifest` 重新生成）→（有实体登记时）提及普查、消歧、全书提及排名前 20 的已登记实体、30 人召回 →
对已有断言核对指针、给凭记忆的断言找候选证据段。没有实体登记时只输出文本统计。不加 `--write` 一律不改 `data/` 下任何文件（除 `--write-manifest`）。

## 17. 变更记录

* v1：首次发布（无原文假设下的格式契约、校验器、文本流水线）。
* v2（本版，有原文）：第 0 节重写（按回做滑动窗口、证据指针与锚点书写法、`recall` 只用于缺口与开局状态、诚实声明保留）；
  第 2 节分区产物改成按回产出（`assertions/chNN.jsonl` 等；普查分区 p1–p4 / c5 / c6a / c6b / c6c）；第 11、12 节人物归属改成按首见回；
  新增第 15 节（文本版面与规范化、文本清单）与第 16 节（工具用法）；断言“重复”改为警告；事件/秘密/身份行也接受紧凑键 `b`、`e`；
  `canon_check` 增加 `--evidence`；分区名增加 p1–p4、c6a–c6c、ch00–ch52（c1–c6 仍认）。格式本身只追加不改名。
