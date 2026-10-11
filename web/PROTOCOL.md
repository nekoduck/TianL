# 天龍八部 · 前后端通信协议 `tianlong/1.3`

> 契约正文。Python 实现：`tianlong/protocol.py`（载荷）+ `tianlong/server.py`（传输）；
> 前端镜像：`web/js/api.js`（真实对接）与 `web/js/mock.js`（独立开发）。三者任何一处变更，先改本文。

## 一、约定

- 传输：HTTP + JSON（UTF-8）；开卷与行动另可走 SSE 流式（见第四节）。每个响应体都带 `"protocol": "tianlong/1.3"`。
- 版本：次版本只做向后兼容的增补，**客户端只比对主版本**（`tianlong/1` 与 `tianlong/1.3` 彼此相通），主版本不符即提示刷新。
- 单机单局：服务端同一时刻只持有一卷书（一局游戏），同一时刻只处理一笔行动。
- 同源：`POST` 只收本页发来、`Content-Type: application/json` 的请求；别家网页（带别家 `Origin`）或写不出 JSON 的跨站表单一律 `403 forbidden`。
- 存档：服务端每回合落定即自动存档；服务重启后续读到的仍是同一卷书。
- 文字优先：载荷里没有气血数值、坐标、内部 id 等"界面感"信息，只有可直接排版的文字；数值隐于身况标签之后。

## 二、接口

| 方法 | 路径 | 用途 | 成功 |
|---|---|---|---|
| `GET` | `/api/session` | 续读：取回当前这卷书的全部回合（刷新页面后恢复）；尚未开卷时 `session` 为 `null` | `200` 会话载荷 |
| `POST` | `/api/session` | 开卷：以名号开始新的一局（会替换旧卷） | `201` 会话载荷 |
| `POST` | `/api/action` | 行动：提交玩家这一回合的举动 | `200` 回合载荷 |

### 开卷请求

```json
{ "name": "萧兰" }
```

`name` 可省略或为空串（以「无名」行走江湖），至多 12 字。

### 行动请求（前端 → 后端）

```json
{ "action_type": "selection", "action_content": "t3-2", "session": "9f1c2a7b3d4e", "turn": 3 }
{ "action_type": "free_text", "action_content": "趁乱溜去后山禁地，看看玉璧的传说", "session": "9f1c2a7b3d4e", "turn": 3 }
```

| 字段 | 说明 |
|---|---|
| `action_type` | `selection`：选择当前回合给出的选项；`free_text`：玩家自由书写 |
| `action_content` | `selection` 时为**当前回合**某个选项的 `id`；`free_text` 时为玩家原话（1～200 字），一字不改交给说书人 |
| `session` | （1.2，可省）这一笔应答的是哪一卷：会话 `id` |
| `turn` | （1.2，可省）这一笔应答的是哪一回合：玩家眼前最新那一回的 `turn` |

选项 `id` 形如 `t{回合}-{序号}`，只在它所属的那一回合有效；提交旧回合的选项会得到 `409 stale_option`。
写明了 `session` / `turn` 而与服务端眼下的卷、最新回合不符（刷新时恰有一回合在写、另开了一卷、超时后重试……）会得到 `409 stale_turn`：
旧笔不会落在翻过的书页上。网页前端总是写明二者；省略则不作此核对（向后兼容）。

## 三、响应

### 回合载荷（后端 → 前端）

```json
{
  "protocol": "tianlong/1.3",
  "turn": 3,
  "deed": { "action_type": "selection", "action_content": "t2-1", "text": "替那书生解围" },
  "scene": { "place": "剑湖宫·练武厅", "region": "大理·无量山" },
  "time": { "year": "元祐六年", "date": "二月初一", "hour": "辰时三刻", "label": "元祐六年二月初一 辰时三刻" },
  "narrative": "你一步跨到书生身前……\n龚光杰冷笑一声……",
  "options": [
    { "id": "t3-1", "label": "顺着少女的话讥讽龚光杰" },
    { "id": "t3-2", "label": "扶书生退到马五德身后" },
    { "id": "t3-3", "label": "强忍伤痛，还他一掌" }
  ],
  "status": [
    { "text": "轻伤", "tone": "warn" },
    { "text": "不会武功", "tone": "plain" },
    { "text": "持有北冥神功卷轴", "tone": "plain" }
  ],
  "events": [
    { "id": 12, "kind": "witnessed", "date": "元祐六年二月初一", "place": "剑湖宫·练武厅", "text": "龚光杰刺伤褚师弟，东宗四赛三胜。" },
    { "id": 15, "kind": "rumor", "date": "元祐六年二月初一", "place": "大理城", "text": "镇南王府遣出数路人马，寻访离家的世子。" }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `turn` | 回合序，开场为 1 |
| `deed` | 引出本回合的玩家举动；开场回合为 `null`。`text` 是交给说书人的原话（选择时即选项文字） |
| `scene` | 当前所在：`place` 地点（子区域以「·」相连），`region` 所属地域（可能为 `null`） |
| `time` | 历法分段，`hour` 精确到刻；`label` 为整句，便于直接显示 |
| `narrative` | 本回合正文，以 `\n` 分段 |
| `options` | 说书人拟定、系统验收过的 3 个下一步（对象够得着、不说破隐情、有人刚开口则必有一项回应他）；玩家也可无视它们，自由书写 |
| `status` | 主角身况的文字标签，`tone` 为 `plain` / `warn`（伤势等需留意）/ `alert`（性命攸关） |
| `events` | 本回合抵达主角的世界变动：`witnessed` 为亲眼所见（正文已写到，宜作旁注）；`rumor` 为远方延迟传来的**江湖传闻**（宜作无侵入通知，玩家查看时以信笺呈现）。`id` 全局唯一，可用于已读标记 |

### 会话载荷

```json
{
  "protocol": "tianlong/1.3",
  "session": { "id": "9f1c2a7b3d4e", "hero": "萧兰" },
  "transcript": [ /* 回合载荷，按回合先后排列；最后一个即当前回合 */ ]
}
```

尚未开卷时：`{ "protocol": "tianlong/1.3", "session": null, "transcript": [] }`——这不是错误，前端据此显示扉页。

### 错误载荷

```json
{ "protocol": "tianlong/1.3", "error": { "code": "stale_option", "message": "这个选项已随时势而去，请依眼下情形重新抉择" } }
```

| HTTP | `code` | 含义 | 前端宜 |
|---|---|---|---|
| 400 | `bad_request` | 请求格式不对（含 `Content-Length` 非法、开卷请求不是对象）、自由书写为空或过长、名号过长 | 提示后让玩家改写 |
| 403 | `forbidden` | 不是本页发来的请求（跨站、或未声明 JSON） | 不应出现于本页 |
| 404 | `no_session` | 行动时尚无书卷（如服务重启后旧卷已失） | 回到扉页 |
| 404 | `not_found` | 没有这个接口 | 不应出现于本页 |
| 409 | `busy` | 上一笔尚未落定（一回合可能需要数十秒） | 稍候重试 |
| 409 | `stale_option` | 选了已过期的选项 | 重新拉取会话、按最新回合重选 |
| 409 | `stale_turn` | 这一笔应答的卷或回合已不是眼下这一页 | 重新拉取会话，按最新回合再落笔 |
| 413 | `bad_request` | 请求体过大 | 提示 |
| 500 | `internal` | 服务端异常 | 允许重试 |

前端另有三个本地错误码（不来自服务端）：`network`（连不上服务，或流在 `done` 之前断了）、`timeout`（等待超时）、`version`（协议主版本不符）。

## 四、流式推送（1.1 新增）

一回合要串起导演、推演、编剧多次大模型调用，常需二三十秒。客户端在 `POST /api/session` 或 `POST /api/action`
的请求头里写 `Accept: text/event-stream`，服务端即以 SSE 边写边送：

```
event: stage
data: {"stage":"direct"}          ← 说书人构思（导演）

event: stage
data: {"stage":"settle"}          ← 江湖推演（结算后果、场外 LOD1/LOD2）

event: stage
data: {"stage":"write"}           ← 落笔

event: head
data: { 回合载荷，narrative 为空串、options 为空数组 }   ← 除正文与选项外此回合已全部落定

event: text
data: {"delta":"练武厅内剑气森森，"}      ← 正文增量，可有多条；依次拼接即为正文

event: done
data: { 与同一请求的非流式响应体一字不差 }  ← 开卷为会话载荷，行动为回合载荷；以此为准
```

| 规则 | 说明 |
|---|---|
| 终值唯一 | `done` 与不走流式时的响应体完全相同；`text` 拼接若与 `done.narrative` 有出入，以 `done` 为准 |
| 开流之前的错误 | 校验不过、忙碌、选项过期等，仍以普通 JSON 错误载荷与 HTTP 状态回应（不开流） |
| 开流之后的错误 | 以 `event: error`（错误载荷）告知，随即关流 |
| 读者半途离席 | 服务端照常写完这一回合并存档；客户端重连后 `GET /api/session` 即可取回 |
| 不支持流式的服务端 | 直接回普通 JSON；客户端应两者皆可接受 |

## 五、时序

```
打开页面 ──GET /api/session──▶ session=null → 扉页 ──POST /api/session──▶ 开场回合（流式或整段）
                              session≠null → 恢复全部回合（不重放打字机）
玩家行动 ──POST /api/action──▶ stage… → head（立回合抬头）→ text…（边到边誊）→ done（对账、放出选项）
                              若含 rumor → 誊毕方浮出传闻提示
流在 head 之后中断 ──GET /api/session──▶ 取回服务端已写完的回合，以终稿收尾
行动遭 409 stale_turn / stale_option ──GET /api/session──▶ 按最新一页重新落笔
一回合中途失败（500 / error 事件）  ──▶ 服务端整回合作废、世界回到这一笔之前；"再试一次"不会把一件事做两遍
```

## 修订

- 1.3：选项在落账之后、正文写成之后才拟定并经规则验收，故 `head` 的 `options` 为空数组，选项随 `done` 放出（前端本就"誊毕方放选项"，无须改动）。

- 1.2：行动可写明所应答的卷与回合（`session` / `turn`），不符即 `409 stale_turn`；`POST` 只收同源 JSON（`403 forbidden`）；
  `Content-Length` 非法、开卷请求不是对象一律 `400`；一回合中途失败则整回合作废（服务端回滚），重试不会重复落账；
  `free_text` 一字不改交给说书人（"2"就是"2"，不再被当成第二个选项）。
- 1.1：新增流式推送（第四节）；服务端每回合自动存档；未开卷的 `GET /api/session` 为 `200` + `session=null`。
- 1：初版——三个接口；回合、会话、错误三种载荷；选项编号带回合序。
