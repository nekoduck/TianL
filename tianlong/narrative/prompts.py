"""
[INPUT]: 消费 world/rag 的 build()（玩家视锥，出路注明关口之类）、backstage()（导演后台：此地上演的原著/近事/预裁/隐情/关口/暗路/节奏）、dossier()（场外档案），均为纯 dict；
         读 world/clock 的 PACES 作时长措辞表
[OUTPUT]: 对外提供 render() / render_backstage() / PLOT_GUIDE（含"effects 即真相"） / TENSIONS 与 director / writer / recap / simulator / chronicler 五组 (system, user) 组装器（场外两组可附江湖近闻）
[POS]: narrative 层的 Prompt 组装器——把基础设施的记忆、地图、算盘与原著日程翻译成 LLM 编织剧情的依据，
       并以 PLOT_GUIDE 教它把剧情后果落账到既有世界；改文风、改叙事纲领只动这一个文件
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json

from ..world.clock import PACES

STATUS = {"alive": "安好", "wounded": "负伤", "dead": "已故"}
TENSIONS = ("平", "起", "高潮", "收")


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
        "【出路】" + ("、".join(f"{e['name']}（{e['days']}日" + (f"·{e['kind']}" if e.get("kind") else "") + "）"
                              for e in pack["exits"]) or "无"),
        f"【主角】{me['name']}｜{me['origin'] or '来历不明'}｜所求：{me['goal'] or '尚无'}｜气血 {me['hp']}｜{me['tier']}"
        f"｜姿态：{me['posture']}｜武学：{'、'.join(me['skills']) or '无'}",
        _section("主角境况", me["conditions"]),
        _section("随身之物", [f"{i['name']}：{i['desc']}" for i in me["inventory"]]),
        _section("未了之事", me["threads"]),
        _section("近日传闻", pack["news"]),
        f"【前情梗概】{me['synopsis']}" if me["synopsis"] else "",
        _section("近来", pack["journal"]),
    ]
    return "\n".join(p for p in parts if p)


def _outcome(ev: dict) -> list[str]:
    """原著结局（effects）译成人话，供导演知道这桩事在原著里落在何处。"""
    words, out = {"wounded": "负伤", "dead": "身亡", "alive": "无恙"}, []
    for op in ev["effects"]:
        kind, nid, key, v = op.get("op"), op.get("id"), op.get("key"), op.get("value")
        if kind == "set" and key == "status":
            out.append(f"{nid}{words.get(v, v)}")
        elif kind == "set" and key == "location" and v != ev["where"]:
            out.append(f"{nid}离去，往{v}")
        elif kind == "set" and key == "holder":
            out.append(f"{nid}归{v}")
        elif kind == "set" and key == "state":
            out.append(f"{nid}现状：{v}")
        elif kind == "push" and key == "skills":
            out.append(f"{nid}习得{v}")
        elif kind == "link":
            out.append(f"{op['src']}—{op['rel']}—{op['dst']}")
    return out


def render_backstage(gm: dict) -> str:
    parts = ["═══ 以下为后台，主角不知 ═══"]
    if gm.get("stage"):
        ev, dirt = gm["stage"]["event"], gm["stage"]["dirt"]
        parts.append(f"【原著此刻在此上演】{ev['summary']}｜相关者：{'、'.join(ev['actors'])}"
                     f"｜原著结局：{'；'.join(_outcome(ev)) or '无可记之变'}" + (f"｜前提有变：{'；'.join(dirt)}" if dirt else "")
                     + "\n  这是本回合的主干：把它编入节拍，让主角目睹或卷入，相关者的言行须合乎原著；原著结局由系统落账，不必写进 effects。"
                       "若主角的举动使它不能照常发生，canon.unfolds 填 false 并在 why 说明，实际后果由你的 effects 写下。")
    parts += [
        _section("原著近事·只可借风声、预兆、传言伏笔，其相关者不得提前登场动手", gm["upcoming"]),
        f"【命运骰】{gm['fate']}（1~100，越高越顺遂；用于机缘、巧合、寻物、言辞打动人心的顺逆）",
        _section("较量预裁·主角若与之动手、斗智或潜行，结局须依此，不得顺从主角（未列者为孩童或无力之人，不入较量）", gm["ruling"]),
        f"【主角濒危】{gm['peril']}" if gm.get("peril") else "",
        _section("功力对比", gm["odds"]),
        _section("各怀图谋", gm["agendas"]),
        _section("此地隐匿之人与暗藏之物", gm["hidden"]),
        _section("未揭隐情·可伏笔，合乎情理方可揭开", gm["secrets"]),
        _section("关口·此地出发：主角要过，须在节拍里兑现其过法与风险；所述是原著某一阶段的情形，此刻是否仍然如此由你依剧情裁定；"
                 "注明过不去者，主角过不去", gm["passes"]),
        _section("近处暗路·主角尚未发现：剧情中被发现或由知情人领路，才可通行", gm["secret_ways"]),
        _section("在场武学", gm["arts"]),
        _section("武学机缘", gm["grants"]),
        f"【近处去向】{'、'.join(gm['places'])}（更远的原著地点亦可直呼其名，路程由系统结算）",
        f"【节奏】{gm['tempo']}" if gm.get("tempo") else "",
    ]
    return "\n".join(p for p in parts if p)


# ============================================================
#  剧情落账：LLM 创造剧情，剧情的后果以指令作用于既有世界（基础设施负责记住、传播、算时日）
# ============================================================
PLOT_GUIDE = """【剧情落账】世界里的人物、地点、器物、道路都由系统掌管，已全部列在上文；你创造的是剧情——言行、冲突、转折、悬念与后果。
剧情若改变了世界，就在 effects 中写下，系统会永久记住并让江湖传开。只能作用于已存在的人、地、物：
- {"op":"set","id":"人物/门派/player","key":"属性","value":值}　{"op":"add","id":…,"key":"hp|power","value":增减}
- {"op":"push"/"pull","id":"player","key":"inventory","value":"此地或随身的器物"}（拾取/丢下）；{"op":"push","id":"player","key":"skills","value":"武学"}
- {"op":"push"/"pull","id":"player","key":"conditions","value":"中毒/被扣押/被追杀…"}（境况起落）；{"op":"push"/"pull","id":"player","key":"threads","value":"一句未了之事"}（埋下或收束线头，至多四条）
- {"op":"link"/"unlink","src":…,"dst":…,"rel":"恩怨/结义/师承等","note":"此人对主角的一句印象(可选)","secret":可选true}；同一人对主角只留最新一条关系，写新即覆盖旧
- {"op":"reveal","src":…,"dst":…,"rel":…}（揭开一条既有隐情；发现暗路时 src 为暗路起点、dst 为通往之地、rel 写"通路"）
- 地点与景物只可改其现状：{"op":"set","id":"地点或景物","key":"state","value":"…"}；暗藏之人或物被发现：{"op":"set","id":…,"key":"hidden","value":false}
主角(player，写主角名号亦可)可写属性：location/hp/power/posture/inventory/skills/conditions/threads；人物 status 取 alive/wounded/dead；
主角移动即 set player.location 为原著中的地点（跋涉时日由系统按道路结算；目的地门前若有关口，系统让主角止步关前，留待下一回合过关）；
器物易手用 {"op":"set","id":器物,"key":"holder","value":在场人物}。
不成立之事（会被系统驳回）：新造人物/地点/器物、前往不存在之地、走不通的路（此路不通、条件未备、未被发现的暗路）、拿取此地没有的器物、死者复生、触碰不在此地的人。
剧情所需的路人龙套（店小二、巡山弟子之流）可以在节拍里出场，但他们只活在叙事中，不写入 effects。
effects 即真相：节拍里写到的每一处伤亡、易手、器物落地、去留、地点现状之变，都必须有对应的 effects；没写进 effects 的变化不曾发生，下一回合世界会按原样呈现。"""


def _example(pack: dict) -> str:
    """一个只示格式的完整输出，用本场真实 id——小模型照着写，id 才不会出错。"""
    who = pack["people"][0]["name"] if pack["people"] else "段誉"
    ex = {"beats": [f"{who}冷眼打量你，手按剑柄", "你拱手自报来历，他哼了一声"],
          "effects": [{"op": "link", "src": who, "dst": "player", "rel": "疑忌", "note": "你来路不明"},
                      {"op": "push", "id": "player", "key": "threads", "value": f"{who}对你起了疑心"}],
          "pace": "片刻", "canon": {"unfolds": True, "why": ""}, "tension": "起",
          "options": ["向他讨教剑法", "退到人群之后", "直言来意"]}
    return "【示例·只示格式，不示内容】" + json.dumps(ex, ensure_ascii=False)


def director(pack: dict, gm: dict, deed: str) -> tuple[str, str]:
    system = (
        "你是《天龙八部》沙盒世界的说书人与导演。主角无论做什么，都由你依据世界真相推演其后果，让在场人物依各自性情与图谋作出反应，"
        "制造冲突、转折与悬念；一幕有起有落，不可回回剑拔弩张、回回以利刃指喉收尾。"
        "剧情必须有根有据：合乎原著人物性情与武学设定，合乎已发生的历史、传闻与未了之事；较量的成败依【较量预裁】，机缘的顺逆依【命运骰】；"
        "高手不会被庸手击败，原著人物不会无端性情大变。后台若列出【原著此刻在此上演】，它就是本回合的主干，主角可旁观、可卷入。"
        "隐情可以伏笔、可以在合乎情理时揭开（用 reveal），不要平白说破。主角的出身与所求是他行动的理由，让剧情围着它转。"
        "原著之外，不得凭空生出门派覆灭、大批伤亡、大军攻山之类大事——超出主角一人之力的变故须有原著依据，世界的尺度由系统掌管。"
        "道路并非想走就走：主角要过后台所列的关口，须在节拍里兑现（应付守卫、攀崖涉险、备船渡水、破解机关……），代价落进 effects。"
        "选项由你自由拟定：3 个方向迥异、此情此景下真正诱人的下一步，而不是千篇一律的行走与交谈。\n"
        + PLOT_GUIDE +
        '\n输出 JSON：{"beats":["3~6拍，每拍不超过40字，写清动作、对白要点与张力"],"effects":[...],'
        f'"pace":"本回合主角举动的时长，只可取 {"/".join(PACES)} 之一（远行路程由系统另算，不必计入）",'
        '"canon":{"unfolds":true或false,"why":"原著不能照常发生时的缘由，否则留空"},'
        f'"tension":"本回合张力，取 {"/".join(TENSIONS)} 之一",'
        '"options":["3个方向迥异的下一步，每个不超过14字，江湖口吻"]}\n'
        + _example(pack)
    )
    user = f"{render(pack)}\n{render_backstage(gm)}\n【主角此刻】{deed}"
    return system, user


def writer(pack: dict, frame: dict) -> tuple[str, str]:
    system = ("你是深谙金庸笔法的武侠小说家，为文字冒险撰写正文。以第二人称「你」叙述，白描为主，对话传神，人物言行合乎性情与设定。"
              "依导演节拍铺陈，可补足细节与氛围，承接【上回合末段】的语气与悬念而不重复它；"
              "【未能成立】中的内容不得写成既成事实；正文所述光阴须与【本回合光阴】相符，不得凭空过夜、过日；"
              "新到的传闻可借人物之口或环境自然带出。篇幅 250~450 字，不写标题、选项与任何 markdown 符号。\n"
              "正文写完后另起一行只写 ===，再写两行：\n梗概：本回合实际发生之事的一句话，不超过40字，只记已成立之事"
              "\n传言：若此事值得在江湖上传开，一句客观记述（不超过30字，以主角名号称呼主角）；否则写 无")
    user = (f"{render(pack)}\n【主角此刻】{frame['deed']}\n【本回合光阴】{frame['span']}\n"
            f"{_section('上回合末段', [frame['prev']] if frame.get('prev') else [])}\n"
            f"{_section('导演节拍', frame['beats'])}\n{_section('未能成立', frame['void'])}\n"
            f"{_section('刚刚传到的消息', frame['news'])}")
    return system, user


def recap(synopsis: str, lines: list[str]) -> tuple[str, str]:
    system = ("你是说书人的书记。把【旧梗概】与【新近事】合为一段不超过 200 字的前情梗概：保留人物恩怨、承诺、未了之事与主角处境，"
              '删去细节与形容，按时间先后叙述。输出 JSON：{"synopsis":"…"}')
    return system, f"【旧梗概】{synopsis or '（无）'}\n{_section('新近事', lines)}"


# ============================================================
#  LOD1：相邻区推演（结构化战报）
# ============================================================
def simulator(time: str, days: int, actors: list[dict], heard=()) -> tuple[str, str]:
    system = ("你是武侠世界的场外推演者，主角不在这些地方。依人物性情、功力与图谋，推演过去数日这些人之间发生的剧情。"
              "只输出结构化战报，不写文学描写。\n" + PLOT_GUIDE +
              "\n场外限制：不得改动主角本人，人物一次只能移动到相邻地点。"
              '\n输出 JSON：{"reports":[{"where":"地点","event":"不超过10字","result":"不超过24字","effects":[...]}]}，'
              "至多 2 条，无进展则为空数组。")
    lines = [f"{a['name']}｜{a['title']}｜{a['tier']}｜身在{a['location']}｜图谋：{a['agenda']}"
             f"｜心境：{a.get('mood') or '平常'}｜相邻：{'、'.join(a['exits'])}" for a in actors]
    return system, f"【时间】{time}\n【已过】{days}日\n{_section('推演人物', lines)}\n{_section('已传到此处的江湖近闻', heard)}"


# ============================================================
#  LOD2：史官（被因果涟漪污染的原著事件重推演）
# ============================================================
def chronicler(ev: dict, reasons: list[str], actors: list[dict], heard=()) -> tuple[str, str]:
    system = ("你是《天龙八部》的史官。一桩原著大事本应发生，但世界已被主角扰动。依据当前真相，重新推演其结局："
              "可以照旧发生、可以变形、可以由其他既有人物代行，也可以不发生。\n" + PLOT_GUIDE +
              "\n场外限制：不得改动主角本人，只能触碰【相关者】与事发地点。"
              '\n输出 JSON：{"happens":true或false,"summary":"不超过60字的客观史笔","effects":[...]}')
    lines = [f"{a['name']}｜{a['title']}｜{a['tier']}｜{STATUS.get(a['status'], a['status'])}"
             f"｜身在{a['location']}｜{a['faction'] or '无门派'}｜性情：{a['persona']}" for a in actors]
    user = (f"【原著事件】{ev['id']}·{ev['where']}：{ev['summary']}\n"
            f"【原著结果】{json.dumps(ev['effects'], ensure_ascii=False)}\n"
            f"{_section('扰动', reasons)}\n{_section('相关者·当前真相', lines)}\n{_section('已传到此处的江湖近闻', heard)}")
    return system, user
