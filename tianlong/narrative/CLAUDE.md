# narrative/
> L2 | 父级: /tianlong/CLAUDE.md

大模型生成层。只读 world/rag 的上下文包，只产出文本或结构化提案；从不持有、也从不直接修改世界状态。换模型只动 llm.py，换文风只动 prompts.py。

成员清单
llm.py: Gemini REST 网关(urllib 直连，text/json 两种调用，thinkingBudget=0 省 token，累计 tokens)，from_env 读取 GEMINI_API_KEY/GEMINI_MODEL
prompts.py: 提示词组装器，render 把上下文包压成带「设定·不可违背」的约束文本，另有 parser/director/writer/simulator/chronicler 五组 (system,user)
agents.py: 五个 Agent 的 组装→调用→校验→兜底——parse(自由文本→合法动作序号)、direct(节拍+3选项)、write(正文)、simulate(LOD1 战报)、chronicle(LOD2 改写)；llm=None 或失败即走确定性 fallback
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
