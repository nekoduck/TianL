"""
[INPUT]: 依赖 copy 做深拷贝
[OUTPUT]: v12 另有 met(见过的人：{人: 最后见到的日子}，系统维护)、offered(P2-2 近三回合入选选项的对象，系统维护)；v11 tags 主角干哪一行(出身带来：消息与知者的行当标签)、lore 主角听来的消息；
           对外提供 Blackboard（玩家 JSON 状态：坐标/气血/功力/姿态/出身与所求/物品/武学/境况/未了之事及其元数据 quests/所识之人 acquaintances/眼前的名册 cast(v5)/节奏账 pacing/研习进度 study/伏笔 hooks/回合数 turn/两层叙事记忆；
          v4 另有账文分歧 drift(v6：正文与账本对不上的几句，结算记下、下回合交导演圆回) 与故事账 scene/clocks/arc/spines/setups；v9 另有身上的零钱 money(两)，三种出身各带一点）、ORIGINS、JOURNAL_CAP
[POS]: world 层的玩家状态黑板；所有写入经 effects 的 id="player" 通道，唯一例外是 remember()——叙事记忆不属于世界真相；
       quests/study/hooks/turn/acquaintances/cast/pacing/came_from/en_route/drift 由系统(situation、growth、engine、perspective、pacing)维护，scene/clocks/arc/spines/setups 由 story/ 维护；内伤是境况里的分级词，由 body 升降，导演写不动。
       气血无论 set 还是 add 都夹在 [1, max_hp]：主角不在规则层死亡。银两(v9)只经事码(拿取、交给、偷取、夺取)由 world/stock 记账，导演写不动。
       记忆分两层：journal 是近事(工作记忆)，满 JOURNAL_CAP 行即挤出最早 FOLD 行交上层折叠进 synopsis(情节梗概)，上下文有界而记忆无界
       v13：poison(主角身上规则登记的毒，body)、drift_seen(分歧交给导演过几回)；study 的账键改为武学(src/minutes/credit/stage/since)；clocks 带 then(到期由规则兑现的事码)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import copy

DEFAULTS = {
    "name": "无名",
    "location": None,
    "hp": 100,
    "max_hp": 100,
    "power": 10,
    "posture": "站立",
    "origin": "",        # 出身：主角为何站在此地
    "goal": "",          # 所求：主角为何而动——剧情的张力轴
    "inventory": [],
    "money": 0.0,        # 身上的零钱(两)：只经事码拿取、交给、偷取、夺取流转(v9 world/stock)，导演写不动
    "skills": [],
    "conditions": [],    # 境况（中毒、被扣押、被追杀……）：导演以 push/pull 维护，不再只活在一句梗概里
    "threads": [],       # 未了之事：导演埋下的线头，须续写或收束
    "quests": {},        # 未了之事的元数据（对象、了结谓词、最近推进的回合）：由 situation 维护，threads 是它给人读的一面
    "study": {},         # 研习进度（武学 → 来源 src、真实光阴 minutes、功候 credit、所至之阶 stage、since；v13 账键是武学，旧档按秘籍记的读到时并入第一门）：由 growth 维护
    "poison": {},        # 主角身上规则登记的毒（毒名 → 发作的节奏与解法，v13 world/body）：导演写不动，只有对症的药或医治解得了
    "hooks": [],         # 编剧埋下、尚未兑现的伏笔（至多两条）
    "acquaintances": [], # 主角识得其名的人：出身带来的、戏里自报家门或被人当面叫出的（由 perspective 维护）
    "tags": [],          # 主角干哪一行(v11)：消息与知者的行当标签(江湖、行情、官府…)，出身带来
    "lore": [],          # 主角听来的消息(v11)：25 的 id，照原样记(可以是假的)，由 lore 维护
    "cast": [],          # 眼前的名册：片区里被剧情带到主角跟前的人（赶来、原著带上台；由 situation 维护，走出近旁即清空）
    "identified": [],    # 识底的人(v12)：主角知其底细(头衔、门派、关系)——识名不等于识底；出身带来的、当众主持的掌门、江湖闻名之人开局即识底，戏里有人说破来历才添(perspective 维护)
    "met": {},           # 见过的人(v12)：{人: 最后见到的日子}——回合末由 situation.meet 记下本回合见过、耳边听过的人，只留三十日内的；望见不算见过
    "offered": [],       # 近三回合入选选项的对象(v12 P2-2)：每回合一列，menu.offer 记下；只指着琐物碎银的选项据此衰减
    "came_from": None,   # 来路：主角上一程从哪里来（出路标出来路，兜底选项不给回头路）
    "en_route": None,    # 途中：{to 去向, left 余程日数}，光阴走满在途中歇脚时记下，到达或改道即清
    "pacing": [],        # 节奏账：最近几回合的主题、谁对主角说了什么、局面动没动（由 pacing 维护）
    "scene": None,       # 此场：{id, where 地点簇, ask 问题, state 开/转/合/断, turns, tried 试过的路数, since}（story/scene 维护）
    "clocks": [],        # 时限：[{id, what, due, turn, then}]，带后果的至多三个、只是伏笔的至多两个（story/stakes 维护；v13 then 是到期由规则兑现的事码）
    "arc": None,         # 主角线：{goal, stage 起意→了结, since}（story/arc 维护）
    "spines": [],        # 近几回合场记主干的来源（story/brief 轮转用）
    "setups": {},        # 系统伏笔提过几回（story/setups 维护）
    "drift": [],         # 账文分歧(v6)：正文写了、账上却不成立的事(规则之事、落不了的变化、没有的进境)——结算记下，下回合交导演圆回；v13 技术性的失败不入此列，规则性的交导演两回（导演写出碰到点名之人的后果即算圆回）
    "drift_seen": {},    # 每条分歧已交导演几回(v13，系统维护；settle.age)
    "turn": 0,           # 第几回合：未了之事据此判断久未推进
    "synopsis": "",      # 情节梗概：长期记忆
    "journal": [],       # 近事：工作记忆
}
JOURNAL_CAP, FOLD = 10, 5  # 近事满十行，最早五行折叠进梗概

# 开局出身：给主角一个站在剑湖宫的理由与一条所求。原著里马五德正是带客人来观剑会之人
ORIGINS = {
    "随从": {"origin": "普洱茶商马五德的随从，随他来无量山观五年一度的剑会", "goal": "在江湖上挣得一个名字", "power": 10, "money": 0.5,
           "tags": ["行情", "过客"]},
    "武师": {"origin": "落魄的外家武师，受马五德接济，随行充作护院", "goal": "求一门真正的武学", "power": 22, "money": 0.3,
           "tags": ["江湖"]},
    "小吏": {"origin": "镇南王府的小吏，奉命暗中照看出游的世子段誉", "goal": "护世子周全，回府复命", "power": 10, "money": 2.0,
           "tags": ["官府"]},
}


class Blackboard:
    def __init__(self, data: dict | None = None):
        self.data = copy.deepcopy({**DEFAULTS, **(data or {})})

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        if key == "hp":
            value = max(1, min(self.data["max_hp"], value))  # 气血有上限，且主角不在规则层死亡
        self.data[key] = value

    def add(self, key, delta):
        self.set(key, self.data[key] + delta)

    def push(self, key, value):
        if value not in self.data[key]:
            self.data[key].append(value)

    def pull(self, key, value):
        if value in self.data[key]:
            self.data[key].remove(value)

    def remember(self, line: str) -> list[str]:
        """记一行近事；满额时挤出最早的几行并返回，由上层折叠进梗概。"""
        journal = self.data["journal"] + [line]
        evicted = journal[:FOLD] if len(journal) > JOURNAL_CAP else []
        self.data["journal"] = journal[len(evicted):]
        return evicted

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)
