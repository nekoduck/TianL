# 逐回抽取与复核规程（A-2；抽取代理与复核代理必读）

格式契约在 `docs/CANON_SCHEMA.md`（第 4、5、6 节最要紧），本文只讲**怎么做**。原著只在本地 `sources/`；任何入库文件里**不得出现原著原文**。

## 1 谁做什么

| 角色 | 读 | 写 |
| --- | --- | --- |
| 抽取代理（每回一个） | `out/canon/chapters/chNN.txt`、`out/canon/digest/chNN.tsv`、`out/canon/registry.tsv`、`data/canon/trait_words.json` | `data/canon/assertions/chNN.jsonl`、`data/canon/identities/chNN.jsonl`（有才写）、`data/canon/census/add_chNN.jsonl`（有才写） |
| 复核代理（另一个代理，每回一个） | `tools/canon_review.py prep` 生成的复核单 | 判决文件 `out/canon/review/verdicts_*.jsonl`，再 `canon_review apply` 写回 `rv/rb` |

任何代理**不执行 git**，不改 `reference/`，不改自己名下之外的文件。秘密、事件、缺口、问答由后面的 A-3 阶段做，**本阶段不写**。

## 2 抽取代理的步骤

1. 读 `out/canon/chapters/chNN.txt`（每行 `[c回p段] 段落文字`，行号 = 段号）。**整回从头读到尾**，大文件分段用 Read 的 offset/limit。
2. 读 `out/canon/digest/chNN.tsv`（本回出场的已登记实体：编号、名、次数、别名）。要找别的实体编号用 `grep` 查 `out/canon/registry.tsv`。**主体、值里的实体必须是已登记编号**。
3. 写 `data/canon/assertions/chNN.jsonl`：紧凑 JSONL，一行一条（格式见 CANON_SCHEMA 4.2）。证据写**锚点** `[回,段,"锚点"]`（锚点 = 该段里原样抄下的 ≤ 20 字，用来定位，必须与 `chNN.txt` 里的字一字不差，含标点；段内不唯一时用 `[回,段,"锚点",第几次]`）。
4. 运行 `python3 tools/canon_resolve.py data/canon/assertions/chNN.jsonl`：锚点被改写成指针；有错的行一字未改，按报错修到全部成功。
5. 运行 `python3 tools/canon_check.py --assertions data/canon/assertions/chNN.jsonl --evidence`，**错误清零**（警告看一遍，重复断言的警告可以接受）。
6. 返回报告：条数、按属性计数、新登记实体数、没把握的地方。

## 3 抽什么（“内核要什么才抽什么”）

**人物**：`gender`、`age_hint`/`age_at_open`（原文明说才写）、`native`、`ethnic`、`org`（门派，`from/to` 限定）、`generation`、`post`（`org` 必写）、`father`、`mother`、`spouse`、`sibling`、`half_sibling`、`kin_other`（`rel` 写关系词）、`master`（师承）、`sworn`、`feud`（`rel` 写由头）、`trait`（只用 `trait_words.json` 里的词，一个断言一个词）、`ambition`（`target`）、`martial`（`grade`）、`might`、`speech`（说话特征标签 ≤ 12 字，**不抄对白**）、`home`、`trade`。
**地点**：`place_kind`、`parent`、`route`（`slots` 常人最少时辰数、`rel` 地形）、`func`、`owner_org`、`access`（转述，≤ 40 字）。
**组织**：`org_kind`、`parent_org`、`post_def`（`lv`）、`rule`、`punish`、`seat`、`org_rel`。
**物与文书**：`item_kind`/`doc_kind`、`holder`、`location`、`use`、`reveals`/`teaches`/`author`。
**武学**：`m_kind`、`of_org`、`creator`、`power`、`limit`、`counter`、`taboo`。

不抽：姓名与别名（在登记表里）、派生属性（`apprentice` `child` `holds` `knows` `knowers`）、**`at_open` `alive_at_open` `death_day`**（开局状态由后面的汇总阶段按全书统一推；只有本回正文**明确**交代“某人在故事开始前已死/某人开局在某处”时才写，并标 `t=text`）。

## 4 精度第一

* 一条断言一件事。**原文明说**或**由原文直接推出**才写；推出的写 `"t":"infer"` 并在 `w` 里用一句话说清理由（≤ 120 字，转述，不引原文）。
* 不凭记忆补。书里没写的就是没写；记忆里“应该是这样”的不写。
* 叙述方式：叙述者的话 `m` 缺省（narrator）；某人说的话写 `"m":"speech","q":{"speaker":"…"}`，且等级只能 `norm`/`dep`（`"r":"norm"`）；回忆 `memory`、传闻 `hearsay` 同理。
  **人物自己的说法与叙述者陈述冲突时，叙述者为准**；本回内就被揭穿的说法写 `"r":"dep"`。
* 同名异人、称呼歧义（“段公子”“王夫人”“老爷子”）要按上下文判清是谁，拿不准就不写。
* 易容、化名、假身份：见闻按“看到的身份”记，真身写在 `identities/chNN.jsonl`（CANON_SCHEMA 第 6 节）。**不要**把易容者的行为写成他所扮之人的属性。
* 数量：一回大约 60–250 条；宁缺毋滥，但**本回戏份重的人物、地点、物、武学都要覆盖**。重要的人物关系、门派师承、武学来历、地点路线、物的转手是重点。
* 限定词用封闭键集（CANON_SCHEMA 4.3）。时间 `from/to` 是世界日数（开局 = 第 0 日，往前取负，一年 360 日，约数）——拿不准时间就不写 `from/to`。
* 文字字段（`w` `n` `rel` `func` `access` `rule` `punish` `limit` `taboo` `speech` 等）一律**转述**，**不得出现原文超过 6 个字的连续片段**，不得含引号对白。

## 5 新实体

遇到重要但没登记的人物、地点、组织、物、武学、文书：

1. 先 `grep` `out/canon/registry.tsv`（名与别名）确认真的没有，别和已有实体重复；
2. 登记到 `data/canon/census/add_chNN.jsonl`：`{"id":"类型:canon:拼音","type":"…","name":"…","aliases":[…],"note":"≤120 字转述"}`，编号规则见 CANON_SCHEMA 第 1 节（拼音连写；重名加数字后缀，先到先得，所以后缀前先查 registry）；
3. 运行 `python3 tools/canon_merge.py --dry-run`（如无该选项则看 `canon_check --census` 零错误）确认无冲突，再在断言里使用；
4. 无名无姓的路人不登记。

## 6 复核代理的步骤

1. `python3 tools/canon_review.py prep data/canon/assertions/chNN.jsonl [data/canon/identities/chNN.jsonl]`，读 `out/canon/review/assertions_chNN.txt`（每条：断言的中文渲染 + 它引用的那段原文，证据字位用【】标出）。
2. 对**每一条**判断：**这段原文是否支持这条断言**？
   * `sup`：原文明说，或由原文直接推出（`infer` 的要看理由是否站得住）；主体、属性、值、限定词（时间、说话人、地点）、叙述方式、等级全都对。
   * `rej`：原文与断言矛盾；或原文不支持；或主体/宾语是错的人（同名异人、称呼指错）；或模式错（人物自己的说法写成了叙述者陈述）；或值明显错。
   * `doubt`：原文含糊，或要靠上下文远处才定得下来；或你拿不准。
   证据片段不够判断时，用 `python3 tools/canon_text.py show 回号 --from 段 --to 段` 看整段及前后几段。
3. 写判决文件 `out/canon/review/verdicts_<名>.jsonl`，**每行**：`{"n":行号,"v":"sup|rej|doubt","why":"≤60 字转述（sup 可空）"}`，行号 = 复核单里 `#` 后的数字。覆盖**所有**行，没看的不许默认 sup。
4. `python3 tools/canon_review.py apply <被复核文件> <判决文件> --by <你的名字>` 写回。
5. 返回统计：sup/rej/doubt 条数，rej 的典型错误类型。**你不改断言内容**；认为该补充的写进报告。

复核代理要像怀疑者：默认怀疑，除非原文能支撑。**不要因为条数多就放水**；也不要把不重要的细枝末节当作错误。

## 7 通过线（不放宽）

* 抽取阶段：每个文件 `canon_check --assertions … --evidence` 零错误；证据指针有效率 100%。
* 复核后：`rej` 的断言只能是 `dep`，不进入后续阶段；`doubt` 进入待审队列。
* A2 验收（独立抽样）：随机 200 条首选断言，判对率 ≥ 95%，抽样者是**第三批**代理，不是抽取者也不是复核者。不到 95% 如实报，不改线。
