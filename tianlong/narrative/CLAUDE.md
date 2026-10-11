# narrative/
> L2 | 父级: /tianlong/CLAUDE.md

剧情层。读 world/rag 的视锥与后台，编织剧情、自由拟定选项，剧情后果以 effects 指令落账到既有世界；不新造人、地、物，不必记忆、不必算账、不必裁决、不必报时——那是基础设施的事，它只选措辞、只演出。换模型只动 llm.py，换文风与叙事纲领只动 prompts.py。

成员清单
llm.py: Gemini REST 网关(urllib 直连，text/json/stream 三种调用，stream 走 streamGenerateContent?alt=sse，sse_texts 为可单测的解析器；连不上、超时、断流(IncompleteRead)、回包不是 JSON 一律化为 LLMError 交兜底；thinkingBudget=0 省 token，累计 tokens，可选 trace 把每次调用记成 JSONL 供提示词迭代)，from_env 读取 GEMINI_API_KEY/GEMINI_MODEL
prompts.py: 提示词组装器，render/render_backstage 把视锥(人物外貌/性情/言谈/随身/印象、主角出身所求/境况/未了之事/梗概、注明关口之类的出路)与后台(此地上演的原著及其原著结局/近事/较量预裁/隐情/此地关口(过法风险须兑现、阶段由导演裁定)/近处暗路/节奏)压成文本，PLOT_GUIDE 教 LLM 剧情落账(含 reveal 发现暗路、门前之关止步)，_example 用本场真实 id 给一个只示格式的输出；另有 director/writer/recap/simulator/chronicler 五组 (system,user)
agents.py: 五个 Agent 的 组装→调用→整形→兜底——direct(节拍+后果+时长措辞 pace+原著去留 canon.unfolds+张力 tension+3 自由选项)、write(正文+分隔线之后只记已成立之事的梗概与可传之事；给 on_text 即边写边送、分隔线后不送读者，半途失声则已写出者即正文)、recap(把挤出的近事折叠进梗概)、simulate(LOD1 场外剧情)、chronicle(LOD2 改写原著)；整形只保形状不审内容，llm=None 或失败即走朴素 fallback
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
