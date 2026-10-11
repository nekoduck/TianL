"""
[INPUT]: 依赖 copy 做深拷贝
[OUTPUT]: 对外提供 Blackboard（玩家 JSON 状态：坐标/气血/功力/姿态/出身与所求/物品/武学/境况/未了之事及其元数据 quests/研习进度 study/伏笔 hooks/回合数 turn/两层叙事记忆）、ORIGINS、JOURNAL_CAP
[POS]: world 层的玩家状态黑板；所有写入经 effects 的 id="player" 通道，唯一例外是 remember()——叙事记忆不属于世界真相；
       quests/study/hooks/turn 由系统(situation、growth、engine)维护，导演写不动。
       气血无论 set 还是 add 都夹在 [1, max_hp]：主角不在规则层死亡。
       记忆分两层：journal 是近事(工作记忆)，满 JOURNAL_CAP 行即挤出最早 FOLD 行交上层折叠进 synopsis(情节梗概)，上下文有界而记忆无界
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
    "skills": [],
    "conditions": [],    # 境况（中毒、被扣押、被追杀……）：导演以 push/pull 维护，不再只活在一句梗概里
    "threads": [],       # 未了之事：导演埋下的线头，须续写或收束
    "quests": {},        # 未了之事的元数据（对象、了结谓词、最近推进的回合）：由 situation 维护，threads 是它给人读的一面
    "study": {},         # 研习进度（秘籍/武学 → 累计分钟、所至之阶）：由 growth 维护
    "hooks": [],         # 编剧埋下、尚未兑现的伏笔（至多四条）
    "turn": 0,           # 第几回合：未了之事据此判断久未推进
    "synopsis": "",      # 情节梗概：长期记忆
    "journal": [],       # 近事：工作记忆
}
JOURNAL_CAP, FOLD = 10, 5  # 近事满十行，最早五行折叠进梗概

# 开局出身：给主角一个站在剑湖宫的理由与一条所求。原著里马五德正是带客人来观剑会之人
ORIGINS = {
    "随从": {"origin": "普洱茶商马五德的随从，随他来无量山观五年一度的剑会", "goal": "在江湖上挣得一个名字", "power": 10},
    "武师": {"origin": "落魄的外家武师，受马五德接济，随行充作护院", "goal": "求一门真正的武学", "power": 22},
    "小吏": {"origin": "镇南王府的小吏，奉命暗中照看出游的世子段誉", "goal": "护世子周全，回府复命", "power": 10},
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
