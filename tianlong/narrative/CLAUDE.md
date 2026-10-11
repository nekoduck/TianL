# narrative/
> L2 | 父级: /tianlong/CLAUDE.md

剧情层。LLM 提议，世界裁决：导演读 world/rag 的视锥与后台逐拍提议(每拍挂着自己的后果 ops)，由 world/adjudicate 裁决，账本对不上就返工一次；编剧只凭已成立之事成文，写完再拟三个带对象的选项与一条伏笔，由 world/menu 验收。不新造原著的人、地、物，不必记忆、不必算账、不必裁决、不必报时——那是基础设施的事，它只选措辞、只演出。换模型只动 llm.py，换文风与叙事纲领只动 prompts.py。

成员清单
llm.py: Gemini REST 网关(urllib 直连，text/json/stream 三种调用，stream 走 streamGenerateContent?alt=sse，sse_texts 为可单测的解析器并记下收尾缘由；连不上、超时、断流(IncompleteRead)、回包不是 JSON、被安全策略半途截断一律化为 LLMError 交兜底；thinkingBudget=0 省 token，累计 tokens 与 trace 加锁(场外推演、梗概折叠与编剧并行)，可选 trace 把每次调用记成 JSONL(含 finishReason)供提示词迭代)，from_env 读取 GEMINI_API_KEY/GEMINI_MODEL
prompts.py: 提示词组装器，render/render_backstage(此地原著前提已破则明告不得照演) 把视锥(人物外貌/性情/言谈/随身/印象、近旁与同行、主角出身所求/境况/未了之事/梗概、注明关口之类的出路)与后台(焦点/受制/此地上演的原著及其原著结局/近事(其人马不得先行登场)/较量预裁/隐情/此地关口/近处暗路/研习进度/未兑现伏笔/久悬之事/节奏)压成文本，PLOT_GUIDE 教 LLM 把后果挂在每一拍上(10 指令、随行与拘押的关系边、带了结谓词的未了之事、spawn 场景实体、主角只做玩家所选之事)，THREATS 要求威胁有来源，_example 用本场真实 id 给一个只示格式的输出；另有 director(不拟选项、标出本幕之问、节拍不得出现后台术语)/repair(原样拿回上一稿与账本对不上之处，只改有问题的拍)/writer(看不见后台，只凭已成立之事、未成立之事与连带成文，再写 梗概/选项(文字｜对象)/伏笔/传言)/recap/simulator/chronicler 六组 (system,user)
agents.py: Agent 的 组装→调用→整形→兜底——direct(逐拍{who,to,text,ops}+本幕之问 question+场景实体 spawn+时长措辞 pace+原著去留 canon.unfolds+张力 tension；一句话的旧拍与顶层 effects 也收)、repair(返工一次，离线或失败返回 None 交系统作废)、write(正文+分隔线之后的梗概/选项(文字｜对象)/伏笔(期限)/可传之事，宽松读取、没写即 None 或空；给 on_text 即边写边送、分隔线后不送读者，半截分隔线先扣下，半途失声则已写出者即正文，被拦腰截断只得只言片语则以已成立之事续成，一字未得才兜底)、plain_options(离线朴素选项)、recap(把挤出的近事折叠进梗概，超长留新近一端)、simulate(LOD1 场外剧情)、chronicle(LOD2 改写原著)；整形只保形状不审内容(单个字串当清单、单条指令当一批、"false"当否，绝不逐字拆散)，llm=None 或失败即走朴素 fallback(离线说书人按全名认去处)
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
