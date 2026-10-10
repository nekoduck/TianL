"""
[INPUT]: 消费 world/rag 的 build()（玩家视锥）、backstage()（导演后台）、dossier()（场外档案），均为纯 dict
[OUTPUT]: 对外提供 render() / render_backstage() 与 director / writer / simulator / chronicler 四组 (system, user) 组装器
[POS]: narrative 层的 Prompt 组装器——把基础设施的记忆、地图与算盘翻译成 LLM 的创作依据，
       并教会它用 CREATION_GUIDE 中的指令把自己的创造写回世界；改文风、改创作纲领只动这一个文件
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json

STATUS = {"alive": "安好", "wounded": "负伤", "dead": "已故"}


# ============================================================
#  上下文包 → 文本
# ============================================================
def _section(title: str, lines) -> str:
    lines = [l for l in lines if l]
    return f"【{title}】\n" + "\n".join(f"- {l}" for l in lines) if lines else ""


def render(pack: dict) -> str:
    s, me = pack["scene"], pack["player"]
    people = [f"{p['name']}｜{p['title']}｜{p['faction'] or '无门派'}｜{p['tier']}｜{STATUS.get(p['status'], p['status'])}"
              f"｜性情：{p['persona']}" + (f"｜与你：{'；'.join(p['toward_you'])}" if p["toward_you"] else "")
              for p in pack["people"]]
    parts = [
        f"【时间】{pack['time']}",
        f"【地点】{s['name']}（{s['region']}）：{s['desc']}" + (f" 现状：{s['state']}" if s["state"] else ""),
        _section("设定", s["lore"]),
        _section("景物", [f"{f['name']}：{f['desc']}" for f in pack["features"]]),
        _section("地上器物", [f"{i['name']}：{i['desc']}" for i in pack["items"]]),
        _section("在场人物", people) or "【在场人物】无",
        _section("在场遗体", pack["dead"]),
        _section("关系网·主角所知", pack["relations"]),
        "【出路】" + "、".join(f"{e['name']}（{e['days']}日）" for e in pack["exits"]),
        f"【主角】{me['name']}｜气血 {me['hp']}｜{me['tier']}｜姿态：{me['posture']}｜武学：{'、'.join(me['skills']) or '无'}",
        _section("随身之物", [f"{i['name']}：{i['desc']}" for i in me["inventory"]]),
        _section("近日传闻", pack["news"]),
        _section("前情", pack["journal"]),
    ]
    return "\n".join(p for p in parts if p)


def render_backstage(gm: dict) -> str:
    parts = [
        "═══ 以下为后台，主角不知 ═══",
        f"【命运骰】{gm['fate']}（1~100，越高越顺遂；用它决定成败的分寸，而非一味顺从主角）",
        _section("功力对比", gm["odds"]),
        _section("各怀图谋", gm["agendas"]),
        _section("此地隐匿之人与暗藏之物", gm["hidden"]),
        _section("未揭隐情", gm["secrets"]),
        _section("武学机缘", gm["grants"]),
        f"【天下道路】{'、'.join(gm['places'])}",
    ]
    return "\n".join(p for p in parts if p)


# ============================================================
#  创作指令：LLM 把自己的创造写回世界的方式（基础设施负责记住、传播、算时间）
# ============================================================
CREATION_GUIDE = """【落笔成真】你在 effects 中写下的一切，都会成为世界的永久真相，被记住、被传播、在后续回合中重现。可用指令：
- {"op":"create","id":"名字","type":"person|location|item|feature|faction","attrs":{...}}
  人物 attrs 可含 title/faction/power(0~100)/persona/agenda/location/hidden；器物与景物可含 desc/location/hidden，器物可含 grants:{"skill":"武学名","power":增益}；
  新地点用 "road":{"to":"已有地点","days":路程日数} 接入地图（不写则视为与此地相邻），attrs 可含 region/desc/lore(列表)。
- {"op":"set","id":"节点或player","key":"属性","value":值}　{"op":"add","id":…,"key":"hp|power",…,"value":增减}
- {"op":"push"/"pull","id":"player","key":"inventory|skills","value":名}（拾取/丢下/习得/失去）
- {"op":"link"/"unlink","src":…,"dst":…,"rel":"关系","secret":可选true}　{"op":"reveal","src":…,"dst":…,"rel":…}（让主角得知一条隐情）
主角(player)可写属性：location/hp/power/posture/inventory/skills；人物 status 取 alive/wounded/dead；
主角移动即 set player.location（可填地点，或填某人某物以前往其所在），跋涉时日由系统按道路自动结算；新造器物 location 填 "player" 即直接随身。
世界物理（违者不成立）：死者不能复生；只能触碰此地之人与物；地点与人物须先存在或先 create。"""


def director(pack: dict, gm: dict, deed: str) -> tuple[str, str]:
    system = (
        "你是《天龙八部》沙盒世界的主宰与说书人。主角的任何举动都由你裁定其后果，你可以自由创造新人物、新地点、新器物、"
        "新恩怨与出人意料的转折——这正是这个世界的生命所在。"
        "你的创造必须有根有据：合乎原著人物性情与武学设定，合乎已发生的历史与传闻，合乎功力对比与命运骰。"
        "高手不会被庸手轻易击败，原著人物不会无端性情大变；但江湖辽阔，原著未写之处正是你落笔之地。"
        "隐情可以伏笔、可以在合乎情理时揭开（用 reveal），不要在节拍里平白说破。\n"
        + CREATION_GUIDE +
        '\n输出 JSON：{"beats":["3~6拍，每拍不超过40字，写清动作、对白要点与张力"],'
        '"effects":[...],"elapsed":本回合耗费的时辰数(整数，1时辰=2小时),'
        '"event":{"summary":"值得在江湖上传开的客观事件，不超过40字","weight":1或2} 或 null,'
        '"options":["3个方向迥异的下一步建议，每个不超过14字，江湖口吻"],'
        '"memory":"本回合一句话梗概，不超过40字"}'
    )
    user = f"{render(pack)}\n{render_backstage(gm)}\n【主角此刻】{deed}"
    return system, user


def writer(pack: dict, deed: str, beats: list[str], void: list[str], news: list[str]) -> tuple[str, str]:
    system = ("你是深谙金庸笔法的武侠小说家，为文字冒险撰写正文。以第二人称「你」叙述，白描为主，对话传神，"
              "人物言行合乎性情与设定。依导演节拍铺陈，可补足细节与氛围；【未能成立】中的内容不得写成既成事实；"
              "近日抵达的传闻可借人物之口或环境自然带出。篇幅 250~450 字；只写正文，不写标题、选项与任何 markdown 符号。")
    user = (f"{render(pack)}\n【主角此刻】{deed}\n{_section('导演节拍', beats)}\n"
            f"{_section('未能成立', void)}\n{_section('刚刚传到的消息', news)}")
    return system, user


# ============================================================
#  LOD1：相邻区推演（结构化战报，可创造）
# ============================================================
def simulator(time: str, days: int, actors: list[dict]) -> tuple[str, str]:
    system = ("你是武侠世界的场外推演者，主角不在这些地方。依人物性情、功力与图谋，推演过去数日的进展，可以创造新人物、新事件、新恩怨。"
              "只输出结构化战报，不写文学描写。\n" + CREATION_GUIDE +
              "\n场外限制：不得改动主角本人，人物一次只能移动到相邻地点。"
              '\n输出 JSON：{"reports":[{"where":"地点","event":"不超过10字","result":"不超过24字","effects":[...]}]}，'
              "至多 2 条，无进展则为空数组。")
    lines = [f"{a['name']}｜{a['title']}｜{a['tier']}｜身在{a['location']}｜图谋：{a['agenda']}"
             f"｜心境：{a.get('mood') or '平常'}｜相邻：{'、'.join(a['exits'])}" for a in actors]
    return system, f"【时间】{time}\n【已过】{days}日\n{_section('推演人物', lines)}"


# ============================================================
#  LOD2：史官（被因果涟漪污染的原著事件重推演）
# ============================================================
def chronicler(ev: dict, reasons: list[str], actors: list[dict]) -> tuple[str, str]:
    system = ("你是《天龙八部》的史官。一桩原著大事本应发生，但世界已被主角扰动。依据当前真相，重新推演其结局："
              "可以照旧发生、可以变形、可以由他人代行、可以引出全新的人物与事件，也可以不发生。\n" + CREATION_GUIDE +
              "\n场外限制：不得改动主角本人，只能触碰【相关者】与事发地点。"
              '\n输出 JSON：{"happens":true或false,"summary":"不超过60字的客观史笔","effects":[...]}')
    lines = [f"{a['name']}｜{a['title']}｜{a['tier']}｜{STATUS.get(a['status'], a['status'])}"
             f"｜身在{a['location']}｜{a['faction'] or '无门派'}｜性情：{a['persona']}" for a in actors]
    user = (f"【原著事件】{ev['id']}·{ev['where']}：{ev['summary']}\n"
            f"【原著结果】{json.dumps(ev['effects'], ensure_ascii=False)}\n"
            f"{_section('扰动', reasons)}\n{_section('相关者·当前真相', lines)}")
    return system, user
