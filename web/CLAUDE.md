# web/
> L2 | 父级: /CLAUDE.md

Web 表现层。新中式极简：页面即一本数字纸书——纸白、墨黑、水墨灰为底，仅伤势、未读、印章点一抹暗朱砂，焦点处一缕淡天青；
不用面板、阴影与 3D，全凭排版与微交互。原生 ES Modules + 单一样式表，无框架、无构建步骤，由 `python main.py --web` 托管；
正文经 SSE 边写边送，打字机边到边誊。楷体自托管（fonts/），宋体取 Google Fonts。
依赖方向：main → store → (api | mock) → contract；ui/* 只读 store、只经 store 的动作改状态，彼此不相识。

成员清单
PROTOCOL.md: 前后端通信协议 tianlong/1.3 的契约正文(head 的选项为空，随 done 放出)——三个接口、同源 JSON、行动请求(可写明所应答的卷与回合)、回合/会话/错误载荷、错误码与前端应对、SSE 流式(stage/head/text/done/error)、时序与修订；三处实现(protocol.py/api.js/mock.js)以它为准
index.html: 唯一页面骨架——扉页、书眉、叙事卷、行动区、页边、传闻小笺、信笺、读屏播报节点；结构即语义
css/ink.css: 全部视觉——自托管楷体 @font-face、色彩令牌与夜读配色、宽屏三栏(竖排书眉·正文·竖排页边)/窄屏顶栏、墨迹晕开、焦点互斥、八行红格信笺、减弱动效
js/main.js: 入口与装配——择服务(?mock 用模拟，?mock=flaky 模拟失联；ES Modules 须经 http 托管)、挂组件、扉页⇄书页转场、另起一卷二次确认、全局键位
js/contract.js: 前端契约镜像——协议版本与主版本兼容判定、进度措辞(STAGES)、错误码→措辞、ServiceError、Service 接口(connect/start/act 可带流式监听)
js/api.js: 真实对接层，全前端唯一的 fetch；有流式监听则请求 SSE 并逐帧分发(stage/head/text)、以 done 为终值，否则收普通 JSON；超时 180 秒，失败统一译为 ServiceError
js/mock.js: 模拟说书人，与 api.js 同形、与 protocol.py 同载荷(head 不带选项)；五回合剧本覆盖伤势、器物、亲见、传闻，仿 Gemini 节奏流式分块，回合先入卷再开讲(?mock=flaky 可半途断流)，校验选项过期，sessionStorage 续读
js/store.js: 唯一状态源——phase/turns/stream/stage/pending/busy/typing/rumors/notice/error；开卷与行动走同一条流式通路(head 立回合、text 累进、done 以终稿替换)，抬头后断流则重新同步；重试、过期重同步、传闻已读与"誊毕方提示"
js/typewriter.js: 打字机——push 边到边誊、end 与终稿对账；逐字墨迹显影、标点换气停顿、积压多则加快、空等后不追赶、跟随视线(玩家滚动即放手)、可略过、誊毕收回为纯文本；paragraphs 为全前端统一的分段规则
js/cn.js: 汉字数字工具，界面里不出现阿拉伯数字
js/ui/title.js: 扉页——竖排书名与朱印，填名号开卷，开卷时报出说书人此刻的进度
js/ui/masthead.js: 书眉——地点、地域、时辰、身况标签(伤势朱字)，换地方时淡入
js/ui/story.js: 叙事卷——跑团日志式生长，往事淡墨当下浓墨；落笔先显影举动与说书人进度(构思/推演)，抬头一到即立回合、正文边到边誊，亲眼所见附"记"于文末
js/ui/actions.js: 行动区——三条去路(汉字序号、笔划下划线)与自由之笔，焦点互斥，誊写未毕不放选项，朱字报错与再试
fonts/: 自托管楷体（霞鹜文楷常用字子集 + 构建脚本 + OFL 许可，见 fonts/CLAUDE.md）
js/ui/rumors.js: 江湖传闻——誊毕浮出一行小笺、页边朱点计数、展开竖排信笺(新者朱字"新")，展信即已读

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
