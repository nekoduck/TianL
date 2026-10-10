"""
[INPUT]: 依赖 copy 做深拷贝
[OUTPUT]: 对外提供 Blackboard（玩家 JSON 状态：坐标/气血/功力/姿态/物品/武学/叙事记忆）
[POS]: world 层的玩家状态黑板；所有写入经 effects 的 id="player" 通道，唯一例外是 remember()——叙事记忆不属于世界真相
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
    "inventory": [],
    "skills": [],
    "journal": [],
}
JOURNAL_CAP = 6  # 只保留最近几拍，给叙事提供连续性而不撑爆上下文


class Blackboard:
    def __init__(self, data: dict | None = None):
        self.data = copy.deepcopy({**DEFAULTS, **(data or {})})

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def add(self, key, delta):
        value = self.data[key] + delta
        if key == "hp":
            value = max(1, min(self.data["max_hp"], value))  # 气血有上限，且主角不在规则层死亡
        self.data[key] = value

    def push(self, key, value):
        if value not in self.data[key]:
            self.data[key].append(value)

    def pull(self, key, value):
        if value in self.data[key]:
            self.data[key].remove(value)

    def remember(self, line: str):
        self.data["journal"] = (self.data["journal"] + [line])[-JOURNAL_CAP:]

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)
