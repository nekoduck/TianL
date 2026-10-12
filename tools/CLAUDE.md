# tools/
> L2 | 父级: /CLAUDE.md

开发工具，不随游戏运行。只读世界与样本，不调用模型、不改世界。

成员清单
replay.py: 量尺——读 tests/fixtures/replay80.json（80 回实录的逐回合样本），以 world/lexicon 的词表体检旧对局的导演节拍与编剧正文，按违例种类统计并列出例子，另量身体两项(无伤扣血 baseless、研习伤身 study_hurt)与打转(逐回合重放节奏账，报出阻尼器会在哪些回合喊停)；python -m tools.replay [--show 种类|all]；每一批重构都拿它对比基线、校准误报与漏报
__init__.py: 包标记，空

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
