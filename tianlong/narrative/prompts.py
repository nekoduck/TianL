"""
[INPUT]: 消费 world/rag 的 build()（玩家视锥：在场/近旁/同行/出路注明关口之类）、backstage()（导演后台：焦点/受制/此地上演的原著/近事/较量与研习预裁/隐情/关口/暗路/研习进度/伏笔/久悬之事/节奏）、
         dossier()（场外档案），均为纯 dict；读 world/clock 的 PACES 作时长措辞表
[OUTPUT]: 对外提供 render() / render_backstage() / PLOT_GUIDE（逐拍挂后果、一拍一事务、气血须有伤疗之据、身体归规则、10 指令、spawn 场景实体与暗藏器物用原名） /
          NAMES（称谓：不识名者只用叫法、听来的名字才可叫、set epithet 立名号） / THREATS / TENSIONS 与
          director / repair / writer / recap / simulator / chronicler 六组 (system, user) 组装器（场外两组可附江湖近闻）
[POS]: narrative 层的 Prompt 组装器——把基础设施的记忆、地图、算盘与原著日程翻译成 LLM 编织剧情的依据，并以 PLOT_GUIDE 教它把后果挂在每一拍上；
       导演只写到此刻为止、不拟选项、标出本幕之问，节拍里不得出现后台术语；返工时原样拿回上一稿与账本对不上之处；
       编剧只看已成立之事、未成立之事与连带，看不见后台，写完正文再拟三个带对象的选项与一条伏笔；改文风、改叙事纲领只动这一个文件
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
              + (f"｜主角不知其名，只叫得出「{p['seen_as']}」" if p.get("seen_as") else "")
              + ("" if p.get("knows_you", True) else "｜不知你姓名")
              for p in pack["people"]]
    parts = [
        f"【时间】{pack['time']}",
        f"【地点】{s['name']}（{s['region']}）：{s['desc']}" + (f" 现状：{s['state']}" if s["state"] else ""),
        _section("设定", s["lore"]),
        _section("景物", [f"{f['name']}：{f['desc']}" for f in pack["features"]]),
        _section("地上器物", [f"{i['name']}：{i['desc']}" for i in pack["items"]]),
        _section("在场人物", people) or "【在场人物】无",
        _section("在场遗体", pack["dead"]),
        _section("近旁·同一处所之内，喊一声就到", pack.get("nearby", [])),
        "【同行】" + "、".join(pack["party"]) if pack.get("party") else "",
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
        broken = "｜前提已破：此事不能照原著发生——canon.unfolds 填 false，若仍有变故，实际后果由你的 effects 写下" \
            if gm["stage"].get("broken") else ""
        parts.append(f"【原著此刻在此上演】{ev['summary']}｜相关者：{'、'.join(ev['actors'])}"
                     f"｜原著结局：{'；'.join(_outcome(ev)) or '无可记之变'}" + (f"｜前提有变：{'；'.join(dirt)}" if dirt else "") + broken
                     + "\n  这是本回合的主干：把它编入节拍，让主角目睹或卷入，相关者的言行须合乎原著；原著结局由系统落账，不必写进 effects。"
                       "若主角的举动使它不能照常发生，canon.unfolds 填 false 并在 why 说明，实际后果由你的 effects 写下。")
    parts += [
        _section("焦点·主角此举所指之物的真相（主角未必知道）", gm.get("focus", [])),
        _section("受制", gm.get("custody", [])),
        _section("原著近事·只可借风声、预兆、传言伏笔，其相关者与其门派人马不得提前登场动手；尚未发生之事，任何人的台词里不得当作已知说出", gm["upcoming"]),
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
        _section("武学机缘·研习进度与研习预裁", gm["grants"]),
        _section("未兑现的伏笔", gm.get("hooks", [])),
        _section("久未推进的未了之事·宜推进或由剧情了结(pull)", gm.get("stale", [])),
        f"【近处去向】{'、'.join(gm['places'])}（更远的原著地点亦可直呼其名，路程由系统结算）",
        f"【节奏】{gm['tempo']}" if gm.get("tempo") else "",
        _section("阻尼·剧情在打转，本回合照此调整", gm.get("fatigue", [])),
    ]
    return "\n".join(p for p in parts if p)


# ============================================================
#  剧情落账：LLM 创造剧情，剧情的后果以指令作用于既有世界（基础设施负责记住、传播、算时日）
# ============================================================
PLOT_GUIDE = """【剧情落账】世界里的人物、地点、器物、道路都由系统掌管，已全部列在上文。你创造剧情，剧情的后果逐拍挂在拍上（ops），系统据此裁决、记账、传开。
一拍写了变化却没有对应的 ops——取得或交出某物、某人离去或随你同行、生死、擒放、吸功——这一拍就不成立，会被退回重写；
一拍的 ops 里有一条落不了（去不了的地方、够不着的东西），整拍都不成立：文字与后果同生共死。气血增减须在这一拍写出伤或疗，被荡开、避过的一击不伤人。
身体归规则：交手的胜负与失血看较量预裁；没人出手、不涉险地，主角一拍至多伤 5 点；研习的顺逆看研习预裁，照演进境，不得自编反噬、走火、扣血。
内伤（内息紊乱→经脉受损→经脉重创）写 push conditions「岔气」之类即由系统加重一级，疗愈写 pull；歇息、服药、有人运功疗伤都会让它好转。
擒人者走，人质随之；要人质随你走，先写明救下（unlink 拘押、link 随行）。指令只能作用于已存在的人、地、物：
- {"op":"set","id":"人物/门派/player","key":"属性","value":值}；{"op":"add","id":…,"key":"hp","value":增减}（主角受伤或疗伤）
- 拾取/丢下：{"op":"push"/"pull","id":"player","key":"inventory","value":"此地或身边的器物"}；器物易手：{"op":"set","id":器物,"key":"holder","value":在场人物或player}
- 境况：{"op":"push"/"pull","id":"player","key":"conditions","value":"中毒/被追杀…"}
- 未了之事：{"op":"push","id":"player","key":"threads","value":{"goal":"一句话","done_when":[["钟灵","~随行","player"]]}}（done_when 可省；了结即自动收束，至多四条）；收束写 pull
- 关系：{"op":"link"/"unlink","src":…,"dst":…,"rel":"…","note":"此人对主角的一句印象(可选)"}；同一人对主角只留最新一条；关系是慢变量（结识、恩、怨、信任），定下之后五回合内不改，一时的焦急恼怒写在拍的 mood 里；
  随你同行写 {"op":"link","src":某人,"dst":"player","rel":"随行"}（之后主角走到哪他跟到哪，过不去的关他会留下）；分道扬镳写 unlink 随行；
  擒人写 {"op":"link","src":擒者,"dst":被擒者,"rel":"扣为人质|囚禁"}，救人写 unlink 这条
- 有人赶来：{"op":"arrive","id":某人}（系统按其所在与路程、本回合光阴裁定赶不赶得到；近旁之人无须 arrive）
- 研习秘籍或向身边人求教武学：{"op":"study","id":"player","value":"秘籍或武学"}；北冥吸人内力：{"op":"drain","id":"player","value":"某人"}——增减多少由系统算，不要写 power
- {"op":"reveal","src":…,"dst":…,"rel":…}（揭开一条既有隐情；发现暗路时 src 为暗路起点、dst 为通往之地、rel 写"通路"）
- 地点与景物只可改现状：{"op":"set","id":…,"key":"state","value":"…"}；暗藏之人或物被发现：{"op":"set","id":…,"key":"hidden","value":false}
- 主角移动：{"op":"set","id":"player","key":"location","value":原著地点}（路程由系统结算，同行者随之；目的地门前有关口则止步关前）
- 败走：让此人 set location 到别处；系统记他新败，数日内不会再来
场景实体：剧情需要一队人马或一件寻常物件（碎银、火折、金创药）时，在顶层 spawn 里立它：{"kind":"group","name":"万劫谷谷丁","faction":"万劫谷","count":8} 或 {"kind":"thing","name":"火折"}；
立了才能在 ops 里用它。群体须属于此地附近有据点或有人的门派，不得属于原著近事里尚未到场的势力；物件不得冒用原著器物之名——此地暗藏的原著器物被发现，直接用它的原名，不要另立。路人龙套只活在叙事里，不写 ops。
不成立之事：新造人物/地点/原著器物、去不了的地方、拿此地没有的器物、死者复生、触碰不在身边的人、替主角做他没选的事（主角只做玩家所选之事；顺手取物、杀人、吸功须是玩家所指）。"""

NAMES = ("【称谓】标了「主角不知其名」的人，主角的台词里不得叫出其名或「姓+称谓」（钟姑娘、段公子），旁白也只写其外貌叫法；"
         "标了「不知你姓名」的人，不得叫出主角名号（王兄、王侠墨）。要让人知道名字，就让他在台词里自报家门（「小生段誉」「我叫钟灵」），"
         "或由认得他的人当面叫出；主角自报家门写「在下某某」。可给不知其名之人定一个外号：{\"op\":\"set\",\"id\":\"钟灵\",\"key\":\"epithet\",\"value\":\"绿衫少女\"}。")

THREATS = "威胁须有来源：打断、堵路、追击主角的，只能是在场或能赶来的人、已立的群体、或此刻上演的原著。"


def _example(pack: dict) -> str:
    """一个只示格式的完整输出，用本场真实 id——小模型照着写，id 才不会出错。"""
    who = pack["people"][0]["name"] if pack["people"] else "段誉"
    ex = {"beats": [{"who": "player", "text": "你拱手自报来历，说明来意", "ops": []},
                    {"who": who, "to": "player", "text": f"{who}冷眼打量你，手按剑柄：「来路不明之人，也敢多问？」",
                     "ops": [{"op": "link", "src": who, "dst": "player", "rel": "疑忌", "note": "你来路不明"}]}],
          "question": {"ask": f"能否取信于{who}", "state": "open", "by": None},
          "spawn": [], "pace": "片刻", "canon": {"unfolds": True, "why": ""}, "tension": "起"}
    return "【示例·只示格式，不示内容】" + json.dumps(ex, ensure_ascii=False)


def _director_system(pack: dict) -> str:
    return (
        "你是《天龙八部》沙盒世界的说书人与导演。玩家选了一件事，你推演它的后果：主角只做玩家所选之事，在场人物依各自性情与图谋作出反应，"
        "制造冲突、转折与悬念；一幕有起有落，不可回回剑拔弩张、回回以追兵或利刃收尾。"
        "剧情必须有根有据：合乎原著人物性情与武学设定，合乎已发生的历史、传闻与未了之事；较量的成败依【较量预裁】，机缘的顺逆依【命运骰】，"
        "但节拍里绝不出现后台术语（命运骰、预裁、档位、功力数字）。高手不会被庸手击败，原著人物不会无端性情大变。"
        "后台若列出【原著此刻在此上演】，它就是本回合的主干。【焦点】是主角所求之物的真相，剧情须与之相符：东西在谁手里就在谁手里。"
        "隐情可以伏笔、可以在合乎情理时揭开（用 reveal），不要平白说破。主角的出身与所求是他行动的理由。"
        "原著之外，不得凭空生出门派覆灭、大批伤亡、大军攻山之类大事。" + THREATS + NAMES +
        "道路并非想走就走：主角要过后台所列的关口，须在节拍里兑现（应付守卫、攀崖涉险、备船渡水……）。"
        "每回合标出本幕之问：主角这一举所求的那件事，结局是了结(resolved)、悬而未决(open)还是被打断(interrupted，须写明 by 是谁)。"
        "选项不归你拟，你只写到此刻为止。\n"
        + PLOT_GUIDE +
        '\n输出 JSON：{"beats":[{"who":"player或人物名","to":"对谁说话(可省；对主角说话写player)","text":"不超过40字，写清动作与对白要点","mood":"此刻情绪两三字(可省；只给编剧渲染，不入账)","ops":[…]}，共3~6拍],'
        '"question":{"ask":"本幕之问","state":"resolved/open/interrupted","by":"打断者，否则 null"},"spawn":[…],'
        f'"pace":"本回合主角举动的时长，只可取 {"/".join(PACES)} 之一（远行路程由系统另算）",'
        '"canon":{"unfolds":true或false,"why":"原著不能照常发生时的缘由，否则留空"},'
        f'"tension":"本回合张力，取 {"/".join(TENSIONS)} 之一"}}\n'
        + _example(pack)
    )


def director(pack: dict, gm: dict, deed: str) -> tuple[str, str]:
    return _director_system(pack), f"{render(pack)}\n{render_backstage(gm)}\n【主角此刻】{deed}"


def repair(pack: dict, gm: dict, deed: str, draft: dict, problems: list[str]) -> tuple[str, str]:
    """导演返工：原样拿回自己的提议与系统查出的问题，只改有问题的拍，输出同一格式。"""
    system = _director_system(pack) + "\n\n你上一稿的提议有几处与世界账本对不上。只改有问题的拍（补上漏写的 ops、改掉做不到的事、删去越权之举），其余照旧，输出完整的同一格式 JSON。"
    user = (f"{render(pack)}\n{render_backstage(gm)}\n【主角此刻】{deed}\n"
            f"【上一稿】{json.dumps(draft, ensure_ascii=False)}\n{_section('账本对不上之处', problems)}")
    return system, user


def writer(pack: dict, frame: dict) -> tuple[str, str]:
    system = ("你是深谙金庸笔法的武侠小说家，为文字冒险撰写正文。以第二人称「你」叙述，白描为主，对话传神，人物言行合乎性情与设定。"
              "【已成立之事】是本回合实际发生的一切，依它铺陈，可补足神态、细节与氛围，但不得添出新的得失、伤亡、去留或擒放；"
              "【未能成立】中的内容不得写成既成事实，可写成未遂或落空；【连带】是系统结算的后果，须自然写进正文；"
              "【上回合末段】只作承接语气，不作事实；正文所述光阴须与【本回合光阴】相符。新到的传闻可借人物之口或环境自然带出。"
              "篇幅 250~450 字，不写标题与任何 markdown 符号。\n"
              "正文写完后另起一行只写 ===，然后写：\n"
              "梗概：本回合实际发生之事的一句话，不超过40字\n"
              "选项：\n1. 下一步｜对象：人物、地点或器物名（用【在场人物】【近旁】【同行】【出路】【随身之物】【地上器物】里的原名，多个用顿号）\n2. …\n3. …\n"
              "伏笔：正文里埋下、日后须兑现的一句悬念｜期限：回合数（多数回合应当写 无；伤病与身体不作伏笔）\n"
              "传言：若此事值得在江湖上传开，一句客观记述（不超过30字，以主角名号称呼主角）；否则写 无\n"
              "选项是三个方向迥异、此情此景下真正诱人的下一步，每个不超过14字，江湖口吻；只能指向主角此刻知道、够得着或走得到的人、地、物，"
              "不得包含主角尚不知道的隐情；若有人刚对主角说了话，至少一项回应他；【可作选项】里的举动优先采用。")
    user = (f"{render(pack)}\n【主角此刻】{frame['deed']}\n【本回合光阴】{frame['span']}\n"
            f"{_section('上回合末段·只作语气参考', [frame['prev']] if frame.get('prev') else [])}\n"
            f"{_section('已成立之事（〔〕里是那一刻的情绪，只作渲染）', frame['beats'])}\n{_section('未能成立', frame['void'])}\n"
            f"{_section('连带', frame.get('notes', []))}\n"
            f"{_section('须回应', [f'{p}刚对你说了话' for p in frame.get('addressed', [])])}\n"
            f"{_section('可作选项', frame.get('candidates', []))}\n"
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
