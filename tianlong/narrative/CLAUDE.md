# narrative/
> L2 | 父级: /tianlong/CLAUDE.md

剧情层。读 world/rag 的视锥与后台，编织剧情、自由拟定选项，剧情后果以 effects 指令落账到既有世界；不新造人、地、物，不必记忆、不必算账，那是基础设施的事。换模型只动 llm.py，换文风与叙事纲领只动 prompts.py。

成员清单
llm.py: Gemini REST 网关(urllib 直连，text/json/stream 三种调用，stream 走 streamGenerateContent?alt=sse，sse_texts 为可单测的解析器；thinkingBudget=0 省 token，累计 tokens)，from_env 读取 GEMINI_API_KEY/GEMINI_MODEL
prompts.py: 提示词组装器，render/render_backstage 把视锥(人物外貌/性情/言谈/随身)与后台(含在场武学)压成文本，PLOT_GUIDE 教 LLM 剧情落账，另有 director/writer/simulator/chronicler 四组 (system,user)
agents.py: 四个 Agent 的 组装→调用→整形→兜底——direct(剧情节拍+后果+时辰+事件+3自由选项)、write(正文，给 on_text 即边写边送，半途失声则已写出者即正文)、simulate(LOD1 场外剧情)、chronicle(LOD2 改写原著)；整形只保形状不审内容，llm=None 或失败即走朴素 fallback
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
