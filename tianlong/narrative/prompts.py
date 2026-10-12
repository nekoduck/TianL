"""
[INPUT]: 消费 world/rag 的 build()（玩家视锥：在场/近旁/同行/途中去向与余程/出路按方向措辞、注明关口之类与来路）、backstage()（导演后台：焦点/受制/此地上演的原著/近事/较量与研习预裁/隐情/关口/暗路/研习进度/伏笔/久悬之事/节奏）、
         dossier()（场外档案），均为纯 dict；读 world/clock 的 PACES 作时长措辞表
[OUTPUT]: 对外提供 render() / render_backstage() / TIME_GUIDE（光阴分戏内 pace 与幕间省略 cut(可等到某一刻)，clock 立时限） / SHAPES（示例的场况、时长、幕间省略轮换） / PLOT_GUIDE（逐拍挂后果、一拍一事务、气血须有伤疗之据、身体归规则、10 指令、spawn 场景实体与暗藏器物用原名） /
          OFFSTAGE（场外落账：说法只许写指令里有的变化、不写主角、只碰列出的人与地） /
          NAMES（称谓：不识名者只用叫法、听来的名字才可叫、set epithet 立名号） / THREATS / TENSIONS 与
          director / repair / writer / recap / simulator / chronicler 六组 (system, user) 组装器（场外两组用 OFFSTAGE 而非 PLOT_GUIDE，可附江湖近闻）
[POS]: narrative 层的 Prompt 组装器——把基础设施的记忆、地图、算盘与原著日程翻译成 LLM 编织剧情的依据，并以 PLOT_GUIDE 教它把后果挂在每一拍上；
       v4：导演上下文第一节是【场记】(story/brief 写的焦点：主干、场况、试过的路数、最急的时限、主角线)，导演报场况 scene(开/转/合/断)；
       一时的看法由系统从 ops 记进恩怨账，link 只立结构性关系，人物自身可伤可病可改眼下之事；人物行带伤势、神色、眼下之事与对你的立场，主角武学以研习账为准；
       编剧按【选项槽位】各拟一项并标尺度，进境不得越过账上那一阶；
       导演只写到此刻为止、不拟选项，节拍里不得出现后台术语；返工时原样拿回上一稿与账本对不上之处；
       编剧只看已成立之事、未成立之事与连带，看不见后台，写完正文再拟三个带对象的选项与一条伏笔；
       v5：场外推演与史官另有 OFFSTAGE 纲领(它们没有拍、没有主角，说法与指令逐句对账，见 world/lod)，史官另看【相关者此后的原著】及其前提(_premise 译成人话)；
       主角眼前的原著可在近旁上演、或要把身边之人带往别处(交导演演出这一别)；改文风、改叙事纲领只动这一个文件
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json

from ..world.clock import PACES
from ..world.pacing import CUTS, UNTIL

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
    people = [f"{p['name']}｜{p['title']}｜{p['faction'] or '无门派'}｜{p['tier']}｜{p.get('wound') or STATUS.get(p['status'], p['status'])}"
              + "".join(f"｜{label}：{p[key]}" for label, key in (("外貌", "appearance"), ("性情", "persona"),
                                                                  ("言谈", "speech"), ("此刻神色", "mood"), ("眼下之事", "intent")) if p.get(key))
              + (f"｜境况：{'、'.join(p['conditions'])}" if p.get("conditions") else "")
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
        "【出路】" + ("、".join(f"{e.get('way', '往')}→{e['name']}（{e['days']}日" + (f"·{e['kind']}" if e.get("kind") else "")
                              + ("·来路" if e.get("back") else "") + "）" for e in pack["exits"]) or "无"),
        (f"【途中】主角正赶往{me['en_route']['to']}，尚余{me['en_route']['left']}日路程，此地只是途中歇脚之处" if me.get("en_route") else ""),
        f"【主角】{me['name']}｜{me['origin'] or '来历不明'}｜所求：{me['goal'] or '尚无'}｜气血 {me['hp']}"
        + (f"（{me['wound']}）" if me.get("wound") else "") + f"｜{me['tier']}｜姿态：{me['posture']}",
        _section("主角武学与进境·以此为准，未列「已会」或阶名的功夫主角使不出来", me.get("arts") or [f"{s}：已会" for s in me["skills"]]) or "【主角武学与进境】无",
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
        door, away = gm["stage"].get("next_door"), gm["stage"].get("away")
        place = f"在近旁的{door}（同一处所之内，喊一声就到：主角或闻其声、或循声可见）" if door else \
            f"在{ev['where']}（{'、'.join(away)}此刻正在主角身边：原著里要往那里去）" if away else "在此"
        parts.append(f"【原著此刻{place}上演】{ev['summary']}｜相关者：{'、'.join(ev['actors'])}"
                     f"｜原著结局：{'；'.join(_outcome(ev)) or '无可记之变'}" + (f"｜前提有变：{'；'.join(dirt)}" if dirt else "") + broken
                     + "\n  这是本回合的主干：把它编入节拍，让主角目睹或卷入，相关者的言行须合乎原著；原著结局由系统落账，不必写进 effects。"
                     + (f"{'、'.join(away)}要离开主角身边：把这一别演出来(去意、告别、被人带走)，主角可以拦阻、同去或目送；" if away else "")
                     + "若主角的举动使它不能照常发生，canon.unfolds 填 false 并在 why 说明，实际后果由你的 effects 写下。")
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
        _section("上回合正文的偏差·正文写了账上没有的事(进境、得失、去留、生死、擒放)，本回合由剧情交代或圆回(只是错觉、未遂、另有缘故)，不得顺着写成真的",
                 gm.get("drift", [])),
        _section("未兑现的伏笔", gm.get("hooks", [])),
        _section("久未推进的未了之事·宜推进或由剧情了结(pull)", gm.get("stale", [])),
        f"【近处去向】{'、'.join(gm['places'])}（更远的原著地点亦可直呼其名，路程由系统结算）",
        f"【节奏】{gm['tempo']}" if gm.get("tempo") and not gm.get("brief") else "",  # 有场记时，节奏由场记统管
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
- {"op":"set","id":"人物/门派/player","key":"属性","value":值}；{"op":"add","id":…,"key":"hp","value":增减}（主角或在场之人受伤、疗伤）
- 拾取/丢下：{"op":"push"/"pull","id":"player","key":"inventory","value":"此地或身边的器物"}；器物易手：{"op":"set","id":器物,"key":"holder","value":在场人物或player}
- 境况：{"op":"push"/"pull","id":"player","key":"conditions","value":"中毒/被追杀…"}
- 未了之事：{"op":"push","id":"player","key":"threads","value":{"goal":"一句话","done_when":[["钟灵","~随行","player"]]}}（done_when 可省；了结即自动收束，至多四条）；收束写 pull
- 关系：{"op":"link"/"unlink","src":…,"dst":…,"rel":"…","note":"缘由(可选)"}只立结构性关系（结义、师徒、随行、拘押、效忠……）。
  某人对主角的看法不必下结论：救人、赠物、夺物、伤人、擒拿都由系统从 ops 里记进他的恩怨账，折叠成【在场人物】里的「对你…」；
  一件 ops 表达不了的大事（当众折辱、替他扬名、背弃承诺）可写 {"op":"link","src":某人,"dst":"player","rel":"感激/记恨/敬佩…","note":"缘由"}，系统按轻重记一笔；一时的焦急恼怒写在拍的 mood 里；
- 人物自身：{"op":"add","id":某人,"key":"hp","value":-15}（伤人，须拍里有伤；他负不负伤由气血推出）；{"op":"push","id":某人,"key":"conditions","value":"中毒/被点穴…"}；
  {"op":"set","id":某人,"key":"intent","value":"他眼下要做的事，一句话"}（他改了主意、有了新打算时写）；
  随你同行写 {"op":"link","src":某人,"dst":"player","rel":"随行"}（之后主角走到哪他跟到哪，过不去的关他会留下）；分道扬镳写 unlink 随行；
  擒人写 {"op":"link","src":擒者,"dst":被擒者,"rel":"扣为人质|囚禁"}，救人写 unlink 这条
- 有人赶来：{"op":"arrive","id":某人}（系统按其所在与路程、本回合光阴裁定赶不赶得到；近旁之人无须 arrive）
- 研习秘籍或向身边人求教武学：{"op":"study","id":"player","value":"秘籍或武学"}；北冥吸人内力：{"op":"drain","id":"player","value":"某人"}——增减多少由系统算，不要写 power
- {"op":"reveal","src":…,"dst":…,"rel":…}（揭开一条既有隐情；发现暗路时 src 为暗路起点、dst 为通往之地、rel 写"通路"）
- 地点与景物只可改现状：{"op":"set","id":…,"key":"state","value":"…"}；暗藏之人或物被发现：{"op":"set","id":…,"key":"hidden","value":false}
- 主角移动：{"op":"set","id":"player","key":"location","value":原著地点}（路程由系统结算，同行者随之；目的地门前有关口则止步关前；
  一回合的光阴走不完的远路，会在途中的地点歇脚，下回合续行或在途中生事；拍文按【出路】里的方向写「出…」「往…」，不必报地名全称）
- 败走：让此人 set location 到别处；系统记他新败，数日内不会再来
场景实体：剧情需要一队人马或一件寻常物件（碎银、火折、金创药）时，在顶层 spawn 里立它：{"kind":"group","name":"万劫谷谷丁","faction":"万劫谷","count":8} 或 {"kind":"thing","name":"火折"}；
立了才能在 ops 里用它。群体须属于此地附近有据点或有人的门派，不得属于原著近事里尚未到场的势力；物件不得冒用原著器物之名——此地暗藏的原著器物被发现，直接用它的原名，不要另立。路人龙套只活在叙事里，不写 ops。
不成立之事：新造人物/地点/原著器物、去不了的地方、拿此地没有的器物、死者复生、触碰不在身边的人、替主角做他没选的事（主角只做玩家所选之事；顺手取物、杀人、吸功须是玩家所指）。"""

TIME_GUIDE = ("【光阴】时长分两段，都只选措辞、由系统换算。pace 是本回合拍里的事耗了多久：瞬息(一招一式、一句话)、片刻(几句对答、走几步、看一处)、"
              "一顿饭(一场较量、一番长谈、细细搜寻、包扎伤口)、半日(练功、疗伤、等候、四处打听)、一夜(歇宿、守夜、彻夜长谈)、一日(整日练功或劳作)——照拍里的事如实取；"
              "研习、求教、歇息养伤的时长由规则补足，写短了系统会按规则算长。"
              "cut 是幕间省略：本场合上、无人相逼时，最后一拍写成收束或过场，光阴随即跳到下一处有戏的时刻——写一段长度（" + "/".join(CUTS) + "），"
              "或写 {\"until\":\"" + "/".join(UNTIL) + "/场记里某个时限\"} 跳到那一刻；说书人不逐刻细磨平静的光阴，一场合了就该跳。"
              "本场未合、主角受制或命悬一线、仍有人拦阻追杀时写 无——系统会核对，不成立的 cut 作废。"
              "时限：剧情里有人立下期限（「明日启程」「天明之前」「三日之内」），在顶层 clock 里记下 {\"what\":\"一句话\",\"in\":\"一日/三个时辰/半日\"}，系统替你记着、到期提醒。")

NAMES = ("【称谓】标了「主角不知其名」的人，主角的台词里不得叫出其名或「姓+称谓」（钟姑娘、段公子），旁白也只写其外貌叫法；"
         "标了「不知你姓名」的人，不得叫出主角名号（王兄、王侠墨）。要让人知道名字，就让他在台词里自报家门（「小生段誉」「我叫钟灵」），"
         "或由认得他的人当面叫出；主角自报家门写「在下某某」。可给不知其名之人定一个外号：{\"op\":\"set\",\"id\":\"钟灵\",\"key\":\"epithet\",\"value\":\"绿衫少女\"}。")

THREATS = "威胁须有来源：打断、堵路、追击主角的，只能是在场或能赶来的人、已立的群体、或此刻上演的原著。"


# 示例的场况、时长与幕间省略轮换着给：写死一组值，小模型就回回照抄(43 回实录里 55 次导演输出有 45 次「片刻」、从无「收」)
SHAPES = (("转", "片刻", "无"), ("合", "一顿饭", "半日"), ("断", "瞬息", "无"), ("合", "片刻", {"until": "入夜"}), ("开", "一顿饭", "无"))


def _example(pack: dict) -> str:
    """一个只示格式的完整输出，用本场真实 id——小模型照着写，id 才不会出错；取值随时辰轮换，不给它一个可抄的默认值。"""
    who = pack["people"][0]["name"] if pack["people"] else "段誉"
    state, pace, cut = SHAPES[sum(map(ord, pack.get("time", ""))) % len(SHAPES)]
    ex = {"beats": [{"who": "player", "text": "你拱手自报来历，说明来意", "ops": []},
                    {"who": who, "to": "player", "text": f"{who}冷眼打量你，手按剑柄：「来路不明之人，也敢多问？」", "mood": "戒备",
                     "ops": [{"op": "set", "id": who, "key": "intent", "value": "要弄清你的来路"}]}],
          "scene": {"state": state, "ask": f"能否取信于{who}", "by": who if state == "断" else None},
          "spawn": [], "pace": pace, "cut": cut, "clock": [], "canon": {"unfolds": True, "why": ""}}
    return "【示例·只示格式，不示内容】" + json.dumps(ex, ensure_ascii=False)


def _director_system(pack: dict) -> str:
    return (
        "你是《天龙八部》沙盒世界的说书人与导演。玩家选了一件事，你推演它的后果：主角只做玩家所选之事，在场人物依各自性情与图谋作出反应，"
        "制造冲突、转折与悬念；一幕有起有落，不可回回剑拔弩张、回回以追兵或利刃收尾。"
        "剧情必须有根有据：合乎原著人物性情与武学设定，合乎已发生的历史、传闻与未了之事；较量的成败依【较量预裁】，机缘的顺逆依【命运骰】，"
        "但节拍里绝不出现后台术语（命运骰、预裁、档位、功力数字）。高手不会被庸手击败，原著人物不会无端性情大变。"
        "后台若列出【原著此刻在此上演】（或在近旁上演），它就是本回合的主干。【焦点】是主角所求之物的真相，剧情须与之相符：东西在谁手里就在谁手里。"
        "隐情可以伏笔、可以在合乎情理时揭开（用 reveal），不要平白说破。主角的出身与所求是他行动的理由。"
        "原著之外，不得凭空生出门派覆灭、大批伤亡、大军攻山之类大事。" + THREATS + NAMES +
        "道路并非想走就走：主角要过后台所列的关口，须在节拍里兑现（应付守卫、攀崖涉险、备船渡水……）。"
        "【场记】是本回合的焦点：主干是什么、这一场在问什么、试过哪些路数、什么最急——依它编排，后台其余各节只是参考资料。"
        "每回合报场况 scene：这一场的问题(ask，开场时定下，之后可改写措辞)此刻是 开(刚起)、转(推进中)、合(有了结果：得、失或变)，还是 断(被打断，须写明 by 是谁)。"
        "一场的问题是此时此地几个回合内就能见分晓的具体之事（能否取信于左子穆、能否把钟灵从神农帮手里救下），不是主角的长远所求；见了分晓就写 合，下一场再起新问。"
        "选项不归你拟，你只写到此刻为止。\n"
        + PLOT_GUIDE + "\n" + TIME_GUIDE +
        '\n输出 JSON：{"beats":[{"who":"player或人物名","to":"对谁说话(可省；对主角说话写player)","text":"不超过40字，写清动作与对白要点","mood":"此刻情绪两三字(可省；只给编剧渲染，不入账)","ops":[…]}，共3~6拍],'
        '"scene":{"state":"开/转/合/断","ask":"这一场的问题","by":"打断者，否则 null"},"spawn":[…],'
        f'"pace":"本回合拍里的事耗时，只可取 {"/".join(PACES)} 之一（见【光阴】；远行路程由系统另算）",'
        f'"cut":"幕间省略：{"/".join(CUTS)} 之一，或 {{\\"until\\":\\"入夜\\"}} 之类；本场未合写 无",'
        '"clock":[{"what":"有人立下的期限","in":"一日"}](没有就空),'
        '"canon":{"unfolds":true或false,"why":"原著不能照常发生时的缘由，否则留空"}}\n'
        + _example(pack)
    )


def _brief(gm: dict) -> str:
    return f"【场记】\n{gm['brief']}\n" if gm.get("brief") else ""


def director(pack: dict, gm: dict, deed: str) -> tuple[str, str]:
    return _director_system(pack), f"{_brief(gm)}{render(pack)}\n{render_backstage(gm)}\n【主角此刻】{deed}"


def repair(pack: dict, gm: dict, deed: str, draft: dict, problems: list[str]) -> tuple[str, str]:
    """导演返工：原样拿回自己的提议与系统查出的问题，只改有问题的拍，输出同一格式。"""
    system = _director_system(pack) + "\n\n你上一稿的提议有几处与世界账本对不上。只改有问题的拍（补上漏写的 ops、改掉做不到的事、删去越权之举），其余照旧，输出完整的同一格式 JSON。"
    user = (f"{_brief(gm)}{render(pack)}\n{render_backstage(gm)}\n【主角此刻】{deed}\n"
            f"【上一稿】{json.dumps(draft, ensure_ascii=False)}\n{_section('账本对不上之处', problems)}")
    return system, user


def writer(pack: dict, frame: dict) -> tuple[str, str]:
    system = ("你是深谙金庸笔法的武侠小说家，为文字冒险撰写正文。以第二人称「你」叙述，白描为主，对话传神，人物言行合乎性情与设定。"
              "【已成立之事】是本回合实际发生的一切，依它铺陈，可补足神态、细节与氛围，但不得添出新的得失、伤亡、去留、擒放或进境；"
              "主角武功练到哪一步以【主角武学与进境】与【连带】为准：账上未入门就只是在习练、摸索、略有所感，不得写成练成、学会、身如游龙、功力大进；"
              "【未能成立】中的内容不得写成既成事实，可写成未遂或落空；【连带】是系统结算的后果，须自然写进正文；"
              "【上回合末段】只作承接语气，不作事实；正文所述光阴须与【本回合光阴】相符。新到的传闻可借人物之口或环境自然带出。"
              "篇幅 250~450 字，不写标题与任何 markdown 符号。\n"
              "正文写完后另起一行只写 ===，然后写：\n"
              "梗概：本回合实际发生之事的一句话，不超过40字\n"
              "选项：\n1. 下一步｜对象：人物、地点或器物名（用【在场人物】【近旁】【同行】【出路】【随身之物】【地上器物】里的原名，多个用顿号）｜尺度：此刻\n2. …｜尺度：此后\n3. …｜尺度：机缘\n"
              "伏笔：正文里埋下、日后须兑现的一句悬念｜期限：回合数（多数回合应当写 无；伤病与身体不作伏笔）\n"
              "传言：若此事值得在江湖上传开，一句客观记述（不超过30字，以主角名号称呼主角）；否则写 无\n"
              "选项是三个方向迥异、此情此景下真正诱人的下一步，按【选项槽位】各拟一项（尺度写那一槽的名字），每个不超过18字，江湖口吻，此后一项在末尾括号里写出代价或耗时（如「连夜赶往大理（两日路程）」）；只能指向主角此刻知道、够得着或走得到的人、地、物，"
              "不得包含主角尚不知道的隐情；若有人刚对主角说了话，至少一项回应他；【可作选项】里的举动优先采用。")
    user = (f"{render(pack)}\n【主角此刻】{frame['deed']}\n【本回合光阴】{frame['span']}\n"
            f"{_section('上回合末段·只作语气参考', [frame['prev']] if frame.get('prev') else [])}\n"
            f"{_section('已成立之事（〔〕里是那一刻的情绪，只作渲染）', frame['beats'])}\n{_section('未能成立', frame['void'])}\n"
            f"{_section('连带', frame.get('notes', []))}\n"
            f"{_section('须回应', [f'{p}刚对你说了话' for p in frame.get('addressed', [])])}\n"
            f"{_section('可作选项', frame.get('candidates', []))}\n"
            f"{_section('选项槽位', frame.get('slots', []))}\n"
            f"{_section('刚刚传到的消息', frame['news'])}")
    return system, user


def recap(synopsis: str, lines: list[str]) -> tuple[str, str]:
    system = ("你是说书人的书记。把【旧梗概】与【新近事】合为一段不超过 200 字的前情梗概：保留人物恩怨、承诺、未了之事与主角处境，"
              '删去细节与形容，按时间先后叙述。输出 JSON：{"synopsis":"…"}')
    return system, f"【旧梗概】{synopsis or '（无）'}\n{_section('新近事', lines)}"


# ============================================================
#  场外落账(v5)：场外推演与史官专用——没有拍、没有主角、没有场景实体；说法只许写指令里有的变化
# ============================================================
OFFSTAGE = """【场外落账】主角不在这些地方。你写的每一桩变化都要写进 effects，系统据此裁决、记账、传开：
说法(result/summary)只许写 effects 里有的变化——写了某人去了哪里、受了伤、死了、被擒或获救、得了什么东西，effects 里却没有，这句说法便作废，只记系统核实过的后果。
说法里不写主角；指令只作用于下面列出的人物与地点，不得新造人物、地点、器物：
- 去向：{"op":"set","id":人物,"key":"location","value":地点}
- 伤病生死：{"op":"add","id":人物,"key":"hp","value":-15}（须有交手或意外）；{"op":"set","id":人物,"key":"status","value":"wounded/dead/alive"}
- 擒放与恩怨：{"op":"link"/"unlink","src":人物,"dst":人物,"rel":"扣为人质/囚禁/结仇/结义/效忠……"}
- 打算与心境：{"op":"set","id":人物,"key":"intent","value":"他眼下要做的事，一句话"}；{"op":"set","id":人物,"key":"mood","value":"两三字"}
- 器物易手：{"op":"set","id":器物,"key":"holder","value":人物}"""


# ============================================================
#  LOD1：相邻区推演（结构化战报）
# ============================================================
def simulator(time: str, days: int, actors: list[dict], heard=()) -> tuple[str, str]:
    system = ("你是武侠世界的场外推演者。依人物性情、功力与图谋，推演过去数日【推演人物】之间发生的事——"
              "多半只是心思与打算有了变化，真正动手、易手、远行的是少数；只输出结构化战报，不写文学描写。\n" + OFFSTAGE +
              "\n场外限制：人物一日只走一程，只能去【相邻】所列之地；原著里另有安排的人不在推演人物之列，战报里不得写到他们。"
              '\n输出 JSON：{"reports":[{"where":"地点","event":"不超过10字","result":"不超过24字","effects":[...]}]}，'
              "至多 2 条，无进展则为空数组。")
    lines = [f"{a['name']}｜{a['title']}｜{a['tier']}｜身在{a['location']}｜图谋：{a['agenda']}"
             f"｜心境：{a.get('mood') or '平常'}｜相邻：{'、'.join(a['exits'])}" for a in actors]
    return system, f"【时间】{time}\n【已过】{days}日\n{_section('推演人物', lines)}\n{_section('已传到此处的江湖近闻', heard)}"


# ============================================================
#  LOD2：史官（被因果涟漪污染的原著事件重推演）
# ============================================================
PREMISE = {"wounded": "负伤", "dead": "已死", "alive": "安好"}


def _premise(nid: str, key: str, want) -> str:
    """原著前提译成人话：给史官看后面几桩原著靠什么成立。"""
    if key[:1] in ("~", "!"):
        return f"{nid}与{want}之间{'仍有' if key[0] == '~' else '没有'}「{key[1:]}」"
    if key == "status":
        return f"{nid}{PREMISE.get(want, want)}"
    if key == "holder":
        return f"{nid}在{want}手中"
    if key == "location":
        return f"{nid}在{want}"
    return f"{nid}的{key}为{want}"


def chronicler(ev: dict, reasons: list[str], actors: list[dict], heard=(), ahead=()) -> tuple[str, str]:
    system = ("你是《天龙八部》的史官。一桩原著大事本应发生，但世界已被主角扰动。依据当前真相，重新推演其结局："
              "可以照旧发生、可以变形、可以由其他既有人物代行，也可以不发生。\n" + OFFSTAGE +
              "\n场外限制：只能触碰【相关者】与事发地点；这桩事是一个整体，effects 里有一条落不了(人不在、物已不存)，整桩便不入账。"
              '\n输出 JSON：{"happens":true或false,"summary":"不超过60字的客观史笔，只写 effects 里有的变化","effects":[...]}')
    lines = [f"{a['name']}｜{a['title']}｜{a['tier']}｜{STATUS.get(a['status'], a['status'])}"
             f"｜身在{a['location']}｜{a['faction'] or '无门派'}｜性情：{a['persona']}" for a in actors]
    later = [f"{e['where']}：{e['summary']}" + (f"（须{'、'.join(_premise(*r) for r in e['requires'])}）" if e["requires"] else "")
             for e in ahead]
    user = (f"【原著事件】{ev['id']}·{ev['where']}：{ev['summary']}\n"
            f"【原著结果】{json.dumps(ev['effects'], ensure_ascii=False)}\n"
            f"{_section('扰动', reasons)}\n{_section('相关者·当前真相', lines)}\n"
            f"{_section('相关者此后的原著·改写这一桩时尽量不断了它们的前提', later)}\n{_section('已传到此处的江湖近闻', heard)}")
    return system, user
