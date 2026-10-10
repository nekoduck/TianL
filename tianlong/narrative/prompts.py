"""
[INPUT]: 消费 world/rag 的 build()（玩家视锥）、backstage()（导演后台）、dossier()（场外档案），均为纯 dict
[OUTPUT]: 对外提供 render() / render_backstage() / PLOT_GUIDE 与 director / writer / simulator / chronicler 四组 (system, user) 组装器
[POS]: narrative 层的 Prompt 组装器——把基础设施的记忆、地图与算盘翻译成 LLM 编织剧情的依据，
       并以 PLOT_GUIDE 教它把剧情后果落账到既有世界；改文风、改叙事纲领只动这一个文件
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
              + "".join(f"｜{label}：{p[key]}" for label, key in (("外貌", "appearance"), ("性情", "persona"),
                                                                  ("言谈", "speech")) if p.get(key))
              + (f"｜随身：{'、'.join(p['carrying'])}" if p["carrying"] else "")
              + (f"｜与你：{'；'.join(p['toward_you'])}" if p["toward_you"] else "")
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
        _section("在场武学", gm["arts"]),
        _section("武学机缘", gm["grants"]),
        f"【近处去向】{'、'.join(gm['places'])}（更远的原著地点亦可直呼其名，路程由系统结算）",
    ]
    return "\n".join(p for p in parts if p)


# ============================================================
#  剧情落账：LLM 创造剧情，剧情的后果以指令作用于既有世界（基础设施负责记住、传播、算时日）
# ============================================================
PLOT_GUIDE = """【剧情落账】世界里的人物、地点、器物、道路都由系统掌管，已全部列在上文；你创造的是剧情——言行、冲突、转折、悬念与后果。
剧情若改变了世界，就在 effects 中写下，系统会永久记住并让江湖传开。只能作用于已存在的人、地、物：
- {"op":"set","id":"人物/门派/player","key":"属性","value":值}　{"op":"add","id":…,"key":"hp|power","value":增减}
- {"op":"push"/"pull","id":"player","key":"inventory","value":"此地或随身的器物"}（拾取/丢下）；{"op":"push","id":"player","key":"skills","value":"武学"}
- {"op":"link"/"unlink","src":…,"dst":…,"rel":"恩怨/结义/师承等","secret":可选true}　{"op":"reveal","src":…,"dst":…,"rel":…}（揭开一条既有隐情）
- 地点与景物只可改其现状：{"op":"set","id":"地点或景物","key":"state","value":"…"}；暗藏之人或物被发现：{"op":"set","id":…,"key":"hidden","value":false}
主角(player)可写属性：location/hp/power/posture/inventory/skills；人物 status 取 alive/wounded/dead；
主角移动即 set player.location 为原著中的地点（跋涉时日由系统按道路结算）；器物易手用 {"op":"set","id":器物,"key":"holder","value":在场人物}。
不成立之事（会被系统驳回）：新造人物/地点/器物、前往不存在之地、拿取此地没有的器物、死者复生、触碰不在此地的人。
剧情所需的路人龙套（店小二、巡山弟子之流）可以在节拍里出场，但他们只活在叙事中，不写入 effects。"""


def director(pack: dict, gm: dict, deed: str) -> tuple[str, str]:
    system = (
        "你是《天龙八部》沙盒世界的说书人与导演。你的职责是创造剧情与选项：主角无论做什么，都由你依据世界真相推演其后果，"
        "让在场人物依各自性情与图谋作出反应，制造冲突、转折与悬念。"
        "剧情必须有根有据：合乎原著人物性情与武学设定，合乎已发生的历史与传闻，合乎功力对比与命运骰；"
        "高手不会被庸手轻易击败，原著人物不会无端性情大变。隐情可以伏笔、可以在合乎情理时揭开（用 reveal），不要平白说破。"
        "选项由你自由拟定：3 个方向迥异、此情此景下真正诱人的下一步，而不是千篇一律的行走与交谈。\n"
        + PLOT_GUIDE +
        '\n输出 JSON：{"beats":["3~6拍，每拍不超过40字，写清动作、对白要点与张力"],'
        '"effects":[...],"elapsed":本回合耗费的时辰数(整数，1时辰=2小时),'
        '"event":{"summary":"值得在江湖上传开的客观事件，不超过40字","weight":1或2} 或 null,'
        '"options":["3个方向迥异的下一步，每个不超过14字，江湖口吻"],'
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
#  LOD1：相邻区推演（结构化战报）
# ============================================================
def simulator(time: str, days: int, actors: list[dict]) -> tuple[str, str]:
    system = ("你是武侠世界的场外推演者，主角不在这些地方。依人物性情、功力与图谋，推演过去数日这些人之间发生的剧情。"
              "只输出结构化战报，不写文学描写。\n" + PLOT_GUIDE +
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
              "可以照旧发生、可以变形、可以由其他既有人物代行，也可以不发生。\n" + PLOT_GUIDE +
              "\n场外限制：不得改动主角本人，只能触碰【相关者】与事发地点。"
              '\n输出 JSON：{"happens":true或false,"summary":"不超过60字的客观史笔","effects":[...]}')
    lines = [f"{a['name']}｜{a['title']}｜{a['tier']}｜{STATUS.get(a['status'], a['status'])}"
             f"｜身在{a['location']}｜{a['faction'] or '无门派'}｜性情：{a['persona']}" for a in actors]
    user = (f"【原著事件】{ev['id']}·{ev['where']}：{ev['summary']}\n"
            f"【原著结果】{json.dumps(ev['effects'], ensure_ascii=False)}\n"
            f"{_section('扰动', reasons)}\n{_section('相关者·当前真相', lines)}")
    return system, user
