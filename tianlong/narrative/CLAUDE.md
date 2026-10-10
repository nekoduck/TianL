# narrative/
> L2 | 父级: /tianlong/CLAUDE.md

大模型创作层。读 world/rag 的视锥与后台，自由裁定与创造，以 effects 指令写回世界；它不必记忆、不必算账，那是基础设施的事。换模型只动 llm.py，换文风与创作纲领只动 prompts.py。

成员清单
llm.py: Gemini REST 网关(urllib 直连，text/json 两种调用，thinkingBudget=0 省 token，累计 tokens)，from_env 读取 GEMINI_API_KEY/GEMINI_MODEL
prompts.py: 提示词组装器，render/render_backstage 把视锥与后台压成文本，CREATION_GUIDE 教 LLM 落笔成真，另有 director/writer/simulator/chronicler 四组 (system,user)
agents.py: 四个 Agent 的 组装→调用→整形→兜底——direct(裁定+创造+时辰+事件+3建议)、write(正文)、simulate(LOD1 场外创造)、chronicle(LOD2 改写原著)；整形只保形状不审内容，llm=None 或失败即走朴素 fallback
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
