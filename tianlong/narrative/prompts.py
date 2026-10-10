"""
[INPUT]: 消费 world/rag.build() 产出的上下文包（纯 dict），不触碰 World 本体
[OUTPUT]: 对外提供 render()（上下文包→约束文本）与 parser / director / writer / simulator / chronicler 五组 (system, user) 组装器
[POS]: narrative 层的 Prompt 组装器——所有提示词集中于此，agents 只管调用与校验；改文风、改约束只动这一个文件
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json

STATUS = {"alive": "安好", "wounded": "负伤", "dead": "已故"}

# ============================================================
#  上下文包 → 约束文本
# ============================================================
def _section(title: str, lines) -> str:
    lines = [l for l in lines if l]
    return f"【{title}】\n" + "\n".join(f"- {l}" for l in lines) if lines else ""


def render(pack: dict) -> str:
    s, me = pack["scene"], pack["player"]
    people = [f"{p['name']}｜{p['title']}｜{p['faction'] or '无门派'}｜{p['tier']}｜{STATUS.get(p['status'], p['status'])}"
              f"｜性情：{p['persona']}" + (f"｜图谋：{p['agenda']}" if p["agenda"] else "")
              + (f"｜与你：{'；'.join(p['toward_you'])}" if p["toward_you"] else "") for p in pack["people"]]
    carried = [f"{i['name']}：{i['desc']}" for i in me["inventory"]]
    parts = [
        f"【时间】{pack['time']}",
        f"【地点】{s['name']}（{s['region']}）：{s['desc']}" + (f" 现状：{s['state']}" if s["state"] else ""),
        _section("设定·不可违背", s["lore"]),
        _section("景物", [f"{f['name']}：{f['desc']}" for f in pack["features"]]),
        _section("地上器物", [f"{i['name']}：{i['desc']}" for i in pack["items"]]),
        _section("在场人物", people) or "【在场人物】无",
        _section("在场遗体", pack["dead"]),
        _section("关系网·主角所知", pack["relations"]),
        f"【出路】{'、'.join(pack['exits'])}",
        f"【主角】{me['name']}｜气血 {me['hp']}｜{me['tier']}｜姿态：{me['posture']}"
        f"｜武学：{'、'.join(me['skills']) or '无'}",
        _section("随身之物", carried),
        _section("近日传闻", pack["news"]),
        _section("前情", pack["journal"]),
    ]
    return "\n".join(p for p in parts if p)


def _numbered(actions: list[dict]) -> str:
    return "\n".join(f"{i}. {a['label']}" for i, a in enumerate(actions))


IRON_LAWS = ("铁律：①【本回合事实】由规则系统裁定，是唯一真相，不得增删胜负、得失、生死；"
             "②只有【在场人物】能登场，场外人物只能以传闻或回忆出现；"
             "③不得透露【设定】与【关系网】以外的隐情，不得替主角做出其未做的决定。")

# ============================================================
#  LOD0：动作解析 → 导演 → 编剧
# ============================================================
def parser(text: str, actions: list[dict]) -> tuple[str, str]:
    system = ("你是文字冒险的动作解析器，把玩家的自由输入映射为【可选行动】中的一个序号。"
              '输出 JSON：{"i": 序号或-1, "manner": "玩家的方式、语气或台词，不超过30字"}。'
              "只能选列表中存在的序号；若输入不对应任何行动（如吟诗、发呆、自语、对场景的提问），i 取 -1。")
    return system, f"【可选行动】\n{_numbered(actions)}\n【玩家输入】{text}"


def director(pack: dict, act: str, facts: list[str], actions: list[dict]) -> tuple[str, str]:
    system = ("你是《天龙八部》文字冒险的导演，只编排节拍，不写文学描写。" + IRON_LAWS +
              '输出 JSON：{"beats": ["…"], "options": [{"i": 序号, "label": "…"}]}。'
              "beats：3~5 拍，每拍不超过30字，写清动作、对白要点与张力；在场人物可依性情与图谋作出反应，但不得造成伤亡或物品易手。"
              "options：从【可选行动】中挑恰好 3 个方向迥异（探索/人情/冒险）的序号，label 用不超过14字的江湖口吻改写。")
    user = (f"{render(pack)}\n【主角本回合】{act}\n{_section('本回合事实', facts) or '【本回合事实】无新变化'}"
            f"\n【可选行动】\n{_numbered(actions)}")
    return system, user


def writer(pack: dict, act: str, facts: list[str], beats: list[str]) -> tuple[str, str]:
    system = ("你是深谙金庸笔法的武侠小说家，为文字冒险撰写正文。" + IRON_LAWS +
              "以第二人称「你」叙述，白描为主，对话传神，人物言行合乎性情与设定；严格按节拍推进，不新增在场人物。"
              "篇幅 250~400 字；只写正文，不写标题、选项与任何 markdown 符号。")
    user = (f"{render(pack)}\n【主角本回合】{act}\n{_section('本回合事实', facts)}\n"
            f"{_section('导演节拍', beats)}")
    return system, user


# ============================================================
#  LOD1：相邻区推演（只出结构化战报）
# ============================================================
def simulator(time: str, days: int, actors: list[dict]) -> tuple[str, str]:
    system = ("你是武侠世界的推演引擎，只输出结构化战报，不写文学描写。根据人物图谋，推演过去数日他们的作为。"
              '输出 JSON：{"reports": [{"where": "地点", "event": "不超过10字", "result": "不超过20字", "effects": [...]}]}。'
              "至多 2 条，无进展则 reports 为空数组。effects 只允许两种："
              '{"op":"set","id":人物,"key":"location","value":相邻地点} 与 {"op":"set","id":人物,"key":"mood","value":"不超过6字"}。'
              "不得造成伤亡，不得涉及未列出的人物。")
    lines = [f"{a['name']}｜{a['title']}｜身在{a['location']}｜图谋：{a['agenda']}｜心境：{a.get('mood') or '平常'}"
             f"｜相邻：{'、'.join(a['exits'])}" for a in actors]
    return system, f"【时间】{time}\n【已过】{days}日\n{_section('推演人物', lines)}"


# ============================================================
#  LOD2：史官（被因果涟漪污染的原著事件重推演）
# ============================================================
def chronicler(ev: dict, reasons: list[str], actors: list[dict]) -> tuple[str, str]:
    system = ("你是《天龙八部》的史官。一桩原著大事本应发生，但世界已被主角扰动。依据当前真相，重新推演其结局。"
              '输出 JSON：{"happens": true或false, "summary": "不超过60字的客观史笔", "effects": [...]}。'
              "若原著前提已不成立（如关键人物已故），可改写为另一桩合乎情理的事件，或令其不发生。"
              "effects 只能涉及【相关者】与事发地点；op 限 set（key 限 status/location/title/faction/state/mood/hidden/power）、link、unlink；"
              "status 只能取 alive/wounded/dead；不得涉及主角。")
    lines = [f"{a['name']}｜{a['title']}｜{STATUS.get(a['status'], a['status'])}｜身在{a['location']}｜{a['faction'] or '无门派'}"
             for a in actors]
    user = (f"【原著事件】{ev['id']}·{ev['where']}：{ev['summary']}\n"
            f"【原著结果】{json.dumps(ev['effects'], ensure_ascii=False)}\n"
            f"{_section('扰动', reasons)}\n{_section('相关者·当前真相', lines)}")
    return system, user
