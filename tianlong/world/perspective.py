"""
[INPUT]: 依赖 world/lexicon 的 Finding / table / find（实体名的最长匹配）、world/situation 的 around，World 门面（graph / player / aliases / knowledge）
[OUTPUT]: 对外提供 knows()（甲是否知乙姓名）、learn()、seed()（开局相识）、handle()（主角眼中某人的叫法）、by_handle()、surname()、
          audit()（逐拍：听来的名字入认知，叫出不该知道的名字即违例——主角叫错与 NPC 叫出主角姓名交返工，NPC 之间只记一笔，不为旁人称谓耗一轮返工）、mask()（交编剧之前，主角不识名之人换成叫法、不知主角姓名者口中的主角换成泛称）、
          veil()（把玩家视锥译成主角的视角：不识名之人只剩外貌叫法，身份与关系一概不露）
[POS]: world 层的认知视角——「视角即上下文」：每段文字都从某个视角写出，那个视角不知道的名字就不给它。
       识名是认知最表层的一环：主角初见钟灵，只知是「大眼圆脸的少女」；她自报姓名、或认得她的人当面叫她，主角才知道她叫钟灵。
       人物之间：原著里有关系、同一门派即互相识名，戏里听见的另记在人物节点的 knows 上；主角所识之人记在黑板的 acquaintances 上（系统维护，导演写不动）。
       纯规则、零调用：追认只增加认知，从不挪动任何人；查不出的旁白漏名，由 mask 在交编剧之前确定性地换掉——不给即不泄露
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy
import re

from . import lexicon, situation

KNOWS = "knows"                   # 人物节点属性：此人在戏里听来的名字（含 "player"）
COMPOUND = ("慕容", "司空", "南宫", "欧阳", "上官", "东方", "诸葛", "公孙", "皇甫", "令狐", "司马", "独孤", "赫连", "完颜",
            "耶律", "端木", "呼延", "尉迟", "宇文", "长孙", "夏侯", "澹台", "萧远")
TITLE = "兄台|兄弟|兄|大哥|大侠|少侠|公子|姑娘|姐姐|妹子|妹妹|小姐|夫人|先生|前辈|老爷子|老爷|大爷|掌门|帮主|谷主|施主|师兄|师弟|师姐|师妹|娘子|大嫂|伯伯|叔叔|贤弟|贤侄|相公"
QUOTE = re.compile(r"[「“『]([^」”』]*)[」”』]")
APPOSITIVE = re.compile(r"(?:少年|少女|汉子|老者|女子|妇人|僧人|书生|弟子|姑娘|公子|青年|道人|孩童|老汉|大汉|壮汉)$")  # 「东宗少年龚光杰」：前面已有叫法，名字直接去掉
SELF = re.compile(r"(?:小生|在下|我叫|我是|我乃|我便是|俺|老子|洒家|贫僧|老衲|贫道|本姑娘|姑娘我|晚辈|小女子|小人|名叫|叫做|唤作)\s*$")
INTRO = re.compile(r"自报姓名|自报家门|自报来历|通了姓名|互通姓名|报上名号|通报姓名|报了姓名|道出姓名|报出名号")
NOUN = re.compile(r"(?:少年|少女|女子|汉子|老者|妇人|书生|和尚|僧人|番僧|道人|道士|道姑|壮汉|姑娘|公子|老人|老妇|孩童|男子|丫头|童子|大汉|姑子|婢女)$")


# ============================================================
#  识名：谁知道谁叫什么
# ============================================================
def knows(world, a: str, b: str) -> bool:
    """a 是否知道 b 的姓名。主角看黑板；人物之间看原著关系、同门与戏里听来的。"""
    if a == b:
        return True
    g = world.graph
    if a == "player":
        return b in world.player["acquaintances"]
    if g.kind(a) != "person":
        return True
    if b in (g.get(a, KNOWS) or []):
        return True
    if b == "player":
        return False
    fa = g.get(a, "faction")
    if fa and fa == g.get(b, "faction"):
        return True
    return any({e["src"], e["dst"]} == {a, b} for e in g.relations(a))


def learn(world, who: str, target: str) -> bool:
    """who 得知 target 的姓名；返回是否新知。"""
    if knows(world, who, target):
        return False
    if who == "player":
        world.player.push("acquaintances", target)
    else:
        node = world.graph.nodes[who]
        node[KNOWS] = (node.get(KNOWS) or []) + [target]
    return True


HOSTS = re.compile(r"掌门|帮主|谷主|庄主|宫主|岛主|方丈")


def seed(world, also=()):
    """开局相识：出身里写到的人（随从之于马五德、王府小吏之于段誉）与主角互相识名；also 另加（旧档里与主角已有交情的人）。
    开场之地当众主持其事的一派之主（剑会上的左子穆、辛双清），主角与在座诸人都叫得出名字——他们却不识得一个随从。"""
    g, tab = world.graph, lexicon.table(_surfaces(world))
    for p in {pid for pid, _, _ in lexicon.find(world.player["origin"] or "", tab)} | set(also):
        if g.kind(p) == "person":
            learn(world, "player", p)
            learn(world, p, "player")
    present = g.where(type="person", location=world.here)
    for p in present:
        if HOSTS.search(g.get(p, "title") or ""):
            for q in ["player", *present]:
                if q != p:
                    learn(world, q, p)


# ============================================================
#  叫法：主角不识名之人，只叫得出外貌
# ============================================================
def surname(name: str) -> str | None:
    if not isinstance(name, str) or len(name) < 2 or len(name) > 3:
        return None
    return next((c for c in COMPOUND if name.startswith(c) and len(name) > len(c)), name[0])


def _noun(g, pid: str) -> str:
    title, faction = g.get(pid, "title") or "", g.get(pid, "faction") or ""
    if "僧" in title or "方丈" in title or faction == "少林派":
        return "僧人"
    if any(w in title for w in ("幼儿", "幼子", "孩童", "小孩")):
        return "孩童"
    age = g.get(pid, "age")
    female = g.get(pid, "gender") == "女"
    young = (age or 30) < 21 or any(w in title for w in ("少女", "弟子", "婢女", "小姐", "世子", "公子"))
    if female:
        return "少女" if young else "妇人" if any(w in title for w in ("夫人", "王妃", "遗孀", "主人")) else "女子"
    return "少年" if young else "老者" if "老" in (g.get(pid, "appearance") or "") else "汉子"


def handle(world, pid: str) -> str:
    """主角眼中此人的叫法：识名则叫名字；不识名则叫导演起的外号(epithet)，没有就照外貌生成——前后一致。"""
    g = world.graph
    if pid == "player" or g.kind(pid) != "person" or knows(world, "player", pid):
        return pid
    if g.get(pid, "epithet"):
        return g.get(pid, "epithet")
    look = re.split(r"[，。；、]", g.get(pid, "appearance") or "")[0].strip()
    if look and NOUN.search(look) and len(look) <= 6:
        return look
    noun, faction = _noun(g, pid), g.get(pid, "faction")
    return f"{look[:5]}的{noun}" if look else f"{faction}的{noun}" if faction else f"一名{noun}"  # 无外貌可写：衣着门派是看得见的


def address(world, pid: str) -> str:
    """当面称呼一个不知其名的人：姑娘、兄台、前辈。"""
    g = world.graph
    if pid == "player":
        return "兄台"
    if g.get(pid, "gender") == "女":
        return "姑娘" if _noun(g, pid) == "少女" else "这位夫人" if _noun(g, pid) == "妇人" else "姑娘"
    return "大师" if _noun(g, pid) == "僧人" else "前辈" if _noun(g, pid) == "老者" else "兄台"


def by_handle(world, name: str) -> str | None:
    """「绿衫少女」落到在场的那个人：编剧与玩家只知道叫法。"""
    if not isinstance(name, str) or not name:
        return None
    return next((p for p in sorted(situation.around(world)) if not knows(world, "player", p) and handle(world, p) == name), None)


def _surfaces(world) -> dict[str, str]:
    """人名的一切写法 → id：正名、别名、去「·」写法。"""
    g = world.graph
    out = {n: n for n, node in g.nodes.items() if node["type"] == "person"}
    out.update({a: n for a, n in world.aliases.items() if g.kind(n) == "person"})
    return out


def _calls(text: str, pid: str, name: str) -> list[tuple[int, int]]:
    """text 里以「姓 + 称谓」叫 pid 的位置：钟姑娘、王兄、段公子。"""
    s = surname(name)
    if not s:
        return []
    return [(m.start(), m.end()) for m in re.finditer(re.escape(s) + f"(?:{TITLE})", text)]


# ============================================================
#  逐拍体检：听来的名字入认知，叫出不该知道的名字即违例
# ============================================================
def audit(world, beats: list[dict], present: set[str]) -> list:
    """beats: [{who, to, text}]（作废的拍 text 为空）。按拍序：先追认本拍里自报家门、当众点名而让在场者听来的名字，
    再查说话者的台词——叫出在场之人的名字或「姓+称谓」而说话者并不知其名，或不知主角姓名者叫出主角的名号，记一条违例。"""
    tab = lexicon.table(_surfaces(world))
    me = world.player["name"]
    people = set(present) | {"player"}
    out = []
    for i, beat in enumerate(beats, 1):
        text, who = beat.get("text") or "", beat.get("who")
        who = "player" if who in ("player", "主角", me) else who
        if not text or (who != "player" and world.graph.kind(who) != "person"):
            continue
        speech = QUOTE.findall(text)
        _overhear(world, who, beat.get("to"), text, speech, tab, people)
        for q in speech:
            for pid, a, _ in lexicon.find(q, tab):
                if pid != who and pid in people and not knows(world, who, pid):
                    out.append(lexicon.Finding("name", i, pid, f"第{i}拍{_who(who)}叫出了{pid}的名字，可{_who(who)}并不知{pid}姓名",
                                               hard=who == "player"))
            for pid in people - {who, "player"}:
                if not knows(world, who, pid) and _calls(q, pid, pid):
                    out.append(lexicon.Finding("name", i, pid, f"第{i}拍{_who(who)}以姓氏称呼{pid}，可{_who(who)}并不知{pid}姓名",
                                               hard=who == "player"))
            if who != "player" and not knows(world, who, "player") and (me in q or _calls(q, "player", me)):
                out.append(lexicon.Finding("name", i, "player", f"第{i}拍{who}叫出了主角的名号，可{who}并不知主角姓名："
                                                                 f"要他知道，先让主角自报家门或由认得主角的人当面叫出"))
    return out


def _who(pid: str) -> str:
    return "主角" if pid == "player" else pid


def _overhear(world, who, to, text, speech, tab, people):
    """在场者听来的名字：说话者自报姓名（「小生段誉」「我叫钟灵」）、拍里写明自报家门、或认得某人的人当面叫出他。"""
    me = world.player["name"]
    for q in speech:
        for pid, a, _ in lexicon.find(q, tab):
            if pid == who and SELF.search(q[:a]):
                for p in people:
                    learn(world, p, who)
            elif pid in people and pid != who and knows(world, who, pid):
                for p in people:
                    learn(world, p, pid)
        if who == "player" and me in q and SELF.search(q[:q.index(me)]):
            for p in people:
                learn(world, p, "player")
        for pid in people - {who}:
            if knows(world, who, pid) and _calls(q, pid, me if pid == "player" else pid):
                for p in people:
                    learn(world, p, pid)
    if INTRO.search(text):
        for p in people:
            learn(world, p, who)
        mate = "player" if to in ("player", "主角", me) else to
        if mate in people and ("互通" in text or "通了姓名" in text):
            for p in people:
                learn(world, p, mate)


# ============================================================
#  交编剧之前：不给即不泄露
# ============================================================
def mask(world, text: str, speaker: str | None = None) -> str:
    """主角不识名之人：旁白里换成叫法，台词里换成当面的称呼；说话者不知主角姓名，他口中的主角名号与「王兄」换成泛称。"""
    if not text:
        return text
    seen = situation.around(world)
    tab = lexicon.table({s: p for s, p in _surfaces(world).items()  # 当面不识其人，或连其名都未曾听过——久仰的不在眼前，照叫其名
                         if not knows(world, "player", p) and (p in seen or not world.knowledge.knows(p))})
    me = world.player["name"]
    speaker = "player" if speaker in ("player", "主角", me) else speaker

    def speech(q: str) -> str:
        q = _swap(q, tab, lambda p: address(world, p))
        if speaker and speaker != "player" and world.graph.kind(speaker) == "person" and not knows(world, speaker, "player"):
            q = q.replace(me, "兄台")
            for a, b in reversed(_calls(q, "player", me)):
                q = q[:a] + ("兄台" if q[a + len(surname(me)):b] in ("兄", "兄弟", "兄台") else q[a + len(surname(me)):b]) + q[b:]
        for p in situation.around(world):
            if not knows(world, "player", p):
                for a, b in reversed(_calls(q, p, p)):
                    q = q[:a] + q[a + len(surname(p)):b] + q[b:]
        return q

    out, last = [], 0
    for m in QUOTE.finditer(text):
        out.append(_swap(text[last:m.start(1)], tab, lambda p: handle(world, p), APPOSITIVE))
        out.append(speech(m.group(1)))
        last = m.end(1)
    out.append(_swap(text[last:], tab, lambda p: handle(world, p), APPOSITIVE))
    return "".join(out)


def _swap(text: str, tab, word, drop=None) -> str:
    """把名字换成 word(pid)；drop 命中名字之前的文字(已有叫法作同位语)则直接去掉名字。"""
    for pid, a, b in reversed(lexicon.find(text, tab)):
        text = text[:a] + ("" if drop and drop.search(text[:a]) else word(pid)) + text[b:]
    return text


def veil(world, pack: dict) -> dict:
    """玩家视锥译成主角的视角（给编剧）：不识名之人只剩叫法，头衔门派与关系不露；同行、近旁、近事、梗概里的名字一并换掉。"""
    out = copy.deepcopy(pack)
    for p in out["people"]:
        pid = p["name"]
        if not knows(world, "player", pid):
            p.update(name=handle(world, pid), title="来历不明", faction="门派不明",
                     toward_you=[mask(world, t) for t in p["toward_you"]], carrying=p["carrying"])
        p["seen_as"] = None
    out["relations"] = [r for r in out["relations"] if mask(world, r) == r]
    out["party"] = [handle(world, p) for p in out.get("party", [])]
    g, shown = world.graph, {p["name"] for p in pack["people"]}
    out["nearby"] = [f"{handle(world, p)}" + (f"（{g.get(p, 'title')}）" if knows(world, "player", p) else "") + f"在{g.get(p, 'location')}"
                     for p in sorted(situation.around(world) - shown)]
    out["dead"] = [handle(world, p) for p in out.get("dead", [])]
    out["journal"] = [mask(world, j) for j in out["journal"]]
    out["player"] = {**out["player"], "synopsis": mask(world, out["player"]["synopsis"]),
                     "threads": [mask(world, t) for t in out["player"]["threads"]]}
    return out
