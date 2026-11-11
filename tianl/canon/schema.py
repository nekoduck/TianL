"""原著 -> 数据的格式契约的代码实现（docs/CANON_SCHEMA.md）。

内容：
  * 稳定编号、枚举（等级/叙述方式/来源标签……）与中文标签
  * 封闭属性注册表 PROPS、限定词 QUALIFIERS、事件前提/结果的操作词表
  * 各结构的校验函数：返回错误列表（字符串），不抛异常
  * 断言的紧凑 JSONL <-> 完整格式互转（expand_assertion / compact_assertion）
  * JSONL 读写助手
  * 30 人召回名单

取证口径（docs/CANON_SCHEMA.md 第 0 节）：有原文的行 basis = text、evidence 至少一条能取回的指针；
只有缺口填补与开局状态推断才 basis = recall、evidence = []（docs/DECISIONS.md 第三节）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANON_DIR = REPO_ROOT / 'data' / 'canon'

# ----------------------------------------------------------------------------------------------------------------------
# 编号
# ----------------------------------------------------------------------------------------------------------------------
ENTITY_TYPES = ('person', 'place', 'org', 'item', 'martial', 'document')
ENTITY_ID_RE = re.compile(r'^(person|place|org|item|martial|document):canon:[a-z][a-z0-9]*$')
EVENT_ID_RE = re.compile(r'^event:canon:[a-z][a-z0-9_]*$')
SECRET_ID_RE = re.compile(r'^secret:canon:[a-z][a-z0-9_]*$')
ASSERTION_ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,40}$')
FLAG_RE = re.compile(r'^[a-z][a-z0-9_]*$')
ASCII_KEY_RE = re.compile(r'^[a-z_][a-z0-9_]*$')
HASH_RE = re.compile(r'^[0-9a-f]{16}$')

# 分区名（文件名的主干）。普查分区：人物按“首见回”分 p1–p4，其余 c5 地点、c6a 组织、c6b 武学、c6c 物与文书；
# 断言/事件/秘密/身份按回产出 chNN（ch00 卷首、ch01–ch50 正文、ch51 后记、ch52 附录）。
# c1–c6 是上一版（无原文时）的人物/类型分区，仍然认（只追加不改名）。
CENSUS_PARTS = ('p1', 'p2', 'p3', 'p4', 'c5', 'c6a', 'c6b', 'c6c')
PART_NAMES = ('c1', 'c2', 'c3', 'c4', 'c5', 'c6') + ('p1', 'p2', 'p3', 'p4', 'c6a', 'c6b', 'c6c')
PART_CHAPTERS = {'p1': (0, 12), 'p2': (13, 25), 'p3': (26, 38), 'p4': (39, 52)}   # 首见回范围（含两端）
CHAPTER_PART_RE = re.compile(r'^ch(\d{2})$')
MAX_CHAPTER = 52


def is_part_name(name):
    """分区名或按回文件名（ch00–ch52）。"""
    if name in PART_NAMES:
        return True
    m = CHAPTER_PART_RE.match(name) if isinstance(name, str) else None
    return bool(m) and int(m.group(1)) <= MAX_CHAPTER


def part_of_chapter(ch):
    """回号 -> 人物普查分区 p1–p4。"""
    for k, (lo, hi) in PART_CHAPTERS.items():
        if lo <= ch <= hi:
            return k
    return None


def stem_in_part(stem, part):
    """文件主干 stem 是否属于分区 part：同名，或 part 是 p1–p4 而 stem 是落在其回范围内的 chNN。"""
    if stem == part:
        return True
    m = CHAPTER_PART_RE.match(stem)
    rng = PART_CHAPTERS.get(part)
    if m and rng:
        return rng[0] <= int(m.group(1)) <= rng[1]
    return False

MAX_TEXT = 120        # 任何自由文字字段的上限（防止把原著长段引文写进库）
MAX_NAME = 30


def id_type(s):
    """'person:canon:x' -> 'person'；不是编号返回 None。"""
    if not isinstance(s, str):
        return None
    if ENTITY_ID_RE.match(s) or EVENT_ID_RE.match(s) or SECRET_ID_RE.match(s):
        return s.split(':', 1)[0]
    return None


def is_entity_id(s, types=None):
    if not isinstance(s, str) or not ENTITY_ID_RE.match(s):
        return False
    return types is None or s.split(':', 1)[0] in types


def make_id(typ, name):
    """由类型与拼音名拼编号（不做拼音转换，只校验）。"""
    s = f'{typ}:canon:{name}'
    if id_type(s) != typ:
        raise ValueError(f'非法编号: {s}')
    return s


# ----------------------------------------------------------------------------------------------------------------------
# 枚举与中文标签
# ----------------------------------------------------------------------------------------------------------------------
RANKS = {'pref': '首选', 'norm': '普通', 'dep': '作废'}
MODES = {'narrator': '叙述者陈述', 'speech': '人物之口', 'memory': '回忆', 'hearsay': '传闻'}
TAGS = {'text': '原著明文', 'infer': '原著推断', 'prior': '史料先验', 'seed': '种子生成'}
BASES = {'text': '有原文指针', 'recall': '凭记忆'}
VERDICTS = {'sup': '支持', 'rej': '不支持', 'doubt': '存疑'}
FILLS = {'prior': '史料先验', 'seed': '种子生成', 'ask': '问你'}
IDENT_KINDS = {'alias': '化名', 'disguise': '易容', 'title': '头衔', 'false_identity': '假身份'}
EVENT_KINDS = {'plot': '情节', 'history': '历史'}
ROLES = {'actor': '主动', 'target': '受事', 'victim': '受害', 'ally': '助力', 'witness': '见证', 'leader': '带头',
         'mastermind': '主谋', 'other': '其他'}
GRADES = ('peak', 'top', 'mid', 'low', 'partial', 'unk')
RELATION_KINDS = ('affinity', 'trust', 'feud', 'love', 'master', 'sworn', 'kin')
ORG_RELS = ('ally', 'hostile', 'rival', 'subordinate', 'kin', 'neutral')
GAP_TABLES = ('archive', 'relation', 'trait', 'cognition', 'placetree', 'route', 'org', 'post', 'norm',
              'unique_item', 'document', 'martial', 'secret', 'event')
GENDERS = ('male', 'female')
MIGHTS = ('peak', 'top', 'mid', 'low', 'none')
AMBITIONS = ('revenge', 'seek_kin', 'seek_art', 'seek_item', 'restore', 'keep_precept', 'pursue', 'dominate',
             'protect', 'reconcile', 'other')
PLACE_KINDS = ('region', 'city', 'town', 'mountain', 'valley', 'water', 'temple', 'manor', 'palace', 'pass',
               'building', 'cave', 'island', 'road', 'other')
ORG_KINDS = ('temple', 'gang', 'manor', 'yamen', 'sect', 'shop', 'other')
ITEM_KINDS = ('weapon', 'medicine', 'token', 'treasure', 'tool', 'food', 'other')
DOC_KINDS = ('letter', 'manual', 'ledger', 'certificate', 'map', 'scroll', 'other')
MARTIAL_KINDS = ('palm', 'fist', 'finger', 'blade', 'sword', 'weapon', 'neigong', 'qinggong', 'dugong', 'misc')
POWERS = ('peak', 'top', 'mid', 'low')
BELIEF_SPECIAL = ('truth', 'suspect')
FROM_SPECIAL = ('self', 'rumor')

_ENUM_TABLES = {'rank': RANKS, 'mode': MODES, 'tag': TAGS, 'basis': BASES, 'verdict': VERDICTS, 'fill': FILLS,
                'kind_ident': IDENT_KINDS, 'kind_event': EVENT_KINDS, 'role': ROLES}


def _label_map(table):
    return {v: k for k, v in table.items()}


_LABEL2CODE = {name: _label_map(t) for name, t in _ENUM_TABLES.items()}
_ENTITY_TYPE_LABELS = {'人物': 'person', '地点': 'place', '组织': 'org', '物': 'item', '武学': 'martial',
                       '文书': 'document'}


def norm_enum(kind, v):
    """中文标签 -> 代码；已是代码或未知值原样返回。"""
    if isinstance(v, str):
        m = _LABEL2CODE.get(kind)
        if m and v in m:
            return m[v]
    return v


# ----------------------------------------------------------------------------------------------------------------------
# 限定词
# ----------------------------------------------------------------------------------------------------------------------
# 键 -> 值类型。'short' 为 <=12 字的转述标签；'via' 为 人物/文书编号 或 self/rumor
QUALIFIERS = {
    'from': 'day', 'to': 'day', 'at': 'place', 'speaker': 'person', 'via': 'via', 'grade': 'grade',
    'org': 'org', 'rel': 'short', 'target': 'entity', 'slots': 'posint', 'lv': 'posint',
}


# ----------------------------------------------------------------------------------------------------------------------
# 封闭属性注册表（docs/CANON_SCHEMA.md 第 5 节）
# ----------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Prop:
    key: str
    label: str
    subjects: tuple
    vtype: str                  # entity / string / int / day / bool / derived
    targets: tuple = ()         # vtype=entity 时允许的值类型（可含 'secret'）
    enum: tuple | None = None
    multi: bool = False
    feeds: tuple = ()
    none_ok: bool = False
    derived: bool = False
    maxlen: int = 80
    tagonly: bool = False       # 只许短标签：<=maxlen 字，无引号与句读
    vocab: str | None = None    # 'trait'：取自 trait_words.json
    req_quals: tuple = ()
    qual_enums: tuple = ()      # ((限定词, 取值元组), ...)


def _p(key, label, subjects, vtype, **kw):
    return Prop(key, label, tuple(subjects), vtype, **kw)


_PERSON = ('person',)

_PROP_LIST = [
    # ---- 人物 ----
    _p('gender', '性别', _PERSON, 'string', enum=GENDERS, feeds=('archive',)),
    _p('age_at_open', '开局年龄', _PERSON, 'int', feeds=('archive',)),
    _p('age_hint', '年龄线索', _PERSON, 'string', feeds=('archive',), maxlen=12, tagonly=True),
    _p('native', '籍贯', _PERSON, 'entity', targets=('place',), feeds=('archive',)),
    _p('ethnic', '族属', _PERSON, 'string', feeds=('archive',), maxlen=12, tagonly=True),
    _p('org', '门派/所属组织', _PERSON, 'entity', targets=('org',), multi=True, none_ok=True,
       feeds=('archive', 'org')),
    _p('generation', '辈分', _PERSON, 'string', feeds=('archive', 'org'), maxlen=12),
    _p('post', '职位', _PERSON, 'string', multi=True, feeds=('post',), maxlen=20, req_quals=('org',)),
    _p('father', '父', _PERSON, 'entity', targets=('person',), feeds=('relation',)),
    _p('mother', '母', _PERSON, 'entity', targets=('person',), feeds=('relation',)),
    _p('spouse', '配偶', _PERSON, 'entity', targets=('person',), multi=True, feeds=('relation',)),
    _p('sibling', '同胞兄弟姊妹', _PERSON, 'entity', targets=('person',), multi=True, feeds=('relation',)),
    _p('half_sibling', '异母/异父兄弟姊妹', _PERSON, 'entity', targets=('person',), multi=True, feeds=('relation',)),
    _p('kin_other', '其他亲属', _PERSON, 'entity', targets=('person',), multi=True, none_ok=True,
       feeds=('relation',)),
    _p('master', '师承', _PERSON, 'entity', targets=('person',), multi=True, none_ok=True, feeds=('relation',)),
    _p('sworn', '结义', _PERSON, 'entity', targets=('person',), multi=True, feeds=('relation',)),
    _p('feud', '仇怨', _PERSON, 'entity', targets=('person',), multi=True, feeds=('relation',)),
    _p('trait', '性格词', _PERSON, 'string', multi=True, feeds=('trait',), maxlen=12, tagonly=True, vocab='trait'),
    _p('ambition', '志向', _PERSON, 'string', enum=AMBITIONS, multi=True, feeds=('trait', 'cognition')),
    _p('martial', '会的武学', _PERSON, 'entity', targets=('martial',), multi=True, feeds=('martial',)),
    _p('might', '武功总评', _PERSON, 'string', enum=MIGHTS, feeds=('martial',)),
    _p('speech', '说话特征', _PERSON, 'string', multi=True, feeds=('archive',), maxlen=12, tagonly=True),
    _p('at_open', '开局时所在地', _PERSON, 'entity', targets=('place',), feeds=('archive',)),
    _p('alive_at_open', '开局时是否在世', _PERSON, 'bool', feeds=('archive',)),
    _p('death_day', '卒日', _PERSON, 'day', feeds=('archive', 'cognition')),
    _p('home', '常驻场所', _PERSON, 'entity', targets=('place',), feeds=('archive',)),
    _p('trade', '营生/修行方向', _PERSON, 'string', multi=True, feeds=('archive',), maxlen=12, tagonly=True),
    _p('apprentice', '徒弟', _PERSON, 'derived', derived=True, feeds=('relation',)),
    _p('child', '子女', _PERSON, 'derived', derived=True, feeds=('relation',)),
    _p('holds', '持有物', _PERSON, 'derived', derived=True, feeds=('unique_item',)),
    _p('knows', '所知', _PERSON, 'derived', derived=True, feeds=('cognition',)),
    # ---- 地点 ----
    _p('place_kind', '地点类型', ('place',), 'string', enum=PLACE_KINDS, feeds=('placetree',)),
    _p('parent', '上级', ('place',), 'entity', targets=('place',), feeds=('placetree',)),
    _p('route', '通往', ('place',), 'entity', targets=('place',), multi=True, feeds=('route',)),
    _p('func', '功能', ('place',), 'string', multi=True, feeds=('placetree',), maxlen=12, tagonly=True),
    _p('owner_org', '归属', ('place',), 'entity', targets=('org',), multi=True, feeds=('placetree', 'org')),
    _p('access', '出入限制', ('place',), 'string', multi=True, feeds=('placetree',), maxlen=40),
    # ---- 组织 ----
    _p('org_kind', '类型（原型）', ('org',), 'string', enum=ORG_KINDS, feeds=('org',)),
    _p('parent_org', '上级组织', ('org',), 'entity', targets=('org',), feeds=('org',)),
    _p('post_def', '职位', ('org',), 'string', multi=True, feeds=('post',), maxlen=20),
    _p('rule', '规矩', ('org',), 'string', multi=True, feeds=('norm',), maxlen=60),
    _p('punish', '处罚', ('org',), 'string', multi=True, feeds=('norm',), maxlen=60),
    _p('seat', '据点', ('org',), 'entity', targets=('place',), multi=True, feeds=('org',)),
    _p('org_rel', '与别派的关系', ('org',), 'entity', targets=('org',), multi=True, feeds=('org',),
       qual_enums=(('rel', ORG_RELS),)),
    # ---- 物与文书 ----
    _p('item_kind', '物的类别', ('item',), 'string', enum=ITEM_KINDS, feeds=('unique_item',)),
    _p('doc_kind', '文书的类别', ('document',), 'string', enum=DOC_KINDS, feeds=('document',)),
    _p('holder', '归属与转手', ('item', 'document'), 'entity', targets=('person', 'org', 'place'), multi=True,
       feeds=('unique_item', 'document')),
    _p('location', '藏处', ('item', 'document'), 'entity', targets=('place',), multi=True,
       feeds=('unique_item', 'document')),
    _p('use', '功用', ('item', 'document'), 'string', multi=True, feeds=('unique_item',), maxlen=12, tagonly=True),
    _p('reveals', '读到即知', ('document',), 'entity', targets=('secret',), multi=True,
       feeds=('document', 'cognition')),
    _p('teaches', '记载武学', ('document',), 'entity', targets=('martial',), multi=True,
       feeds=('document', 'martial')),
    _p('author', '作者/来源', ('document',), 'entity', targets=('person',), feeds=('document',)),
    # ---- 武学 ----
    _p('m_kind', '类别', ('martial',), 'string', enum=MARTIAL_KINDS, feeds=('martial',)),
    _p('of_org', '所属', ('martial',), 'entity', targets=('org',), multi=True, feeds=('martial',)),
    _p('creator', '创制者', ('martial',), 'entity', targets=('person',), multi=True, feeds=('martial',)),
    _p('power', '层级', ('martial',), 'string', enum=POWERS, feeds=('martial',)),
    _p('limit', '传授限制', ('martial',), 'string', multi=True, feeds=('martial',), maxlen=60),
    _p('counter', '相克', ('martial',), 'entity', targets=('martial',), multi=True, feeds=('martial',)),
    _p('taboo', '禁忌', ('martial',), 'string', multi=True, feeds=('martial',), maxlen=60),
    _p('knowers', '谁会', ('martial',), 'derived', derived=True, feeds=('martial',)),
]

PROPS = {p.key: p for p in _PROP_LIST}
assert len(PROPS) == len(_PROP_LIST), '属性键重复'
WRITABLE_PROPS = tuple(k for k, p in PROPS.items() if not p.derived)
DERIVED_PROPS = tuple(k for k, p in PROPS.items() if p.derived)

KIN_PROPS = ('father', 'mother', 'spouse', 'sibling', 'half_sibling', 'kin_other')
CORE_PERSON_PROPS = ('at_open', 'alive_at_open')   # 人物必含


# ----------------------------------------------------------------------------------------------------------------------
# 事件前提/结果的封闭操作词表（docs/CANON_SCHEMA.md 7.2、7.3）
# ----------------------------------------------------------------------------------------------------------------------
# 参数种类：person place org item(物或文书) what(秘密或事件) flagname flagvalue int belief src holder relkind delta
PRE_OPS = {
    'at': ({'person': 'person', 'place': 'place'}, {'not': 'bool'}),
    'alive': ({'person': 'person'}, {}),
    'dead': ({'person': 'person'}, {}),
    'knows': ({'person': 'person', 'what': 'what'}, {'belief': 'belief', 'not': 'bool'}),
    'flag': ({'name': 'flagname'}, {'value': 'flagvalue', 'not': 'bool'}),
    'has': ({'person': 'person', 'item': 'item'}, {'not': 'bool'}),
    'in_org': ({'person': 'person', 'org': 'org'}, {'not': 'bool'}),
    'day_ge': ({'n': 'int'}, {'not': 'bool'}),
    'day_le': ({'n': 'int'}, {'not': 'bool'}),
}
EFF_OPS = {
    'move': ({'person': 'person', 'place': 'place'}, {}),
    'die': ({'person': 'person'}, {'by': 'person'}),
    'learn': ({'person': 'person', 'secret': 'what', 'belief': 'belief'}, {'from': 'src'}),
    'give_item': ({'item': 'item', 'to': 'holder'}, {}),
    'set_flag': ({'name': 'flagname'}, {'value': 'flagvalue'}),
    'join_org': ({'person': 'person', 'org': 'org'}, {}),
    'leave_org': ({'person': 'person', 'org': 'org'}, {}),
    'relation': ({'a': 'person', 'b': 'person', 'kind': 'relkind', 'delta': 'delta'}, {}),
}

ENTITY_KEYS = ('id', 'type', 'name', 'aliases', 'note', 'amb')
ASSERTION_KEYS = ('id', 'subject', 'property', 'value', 'qualifiers', 'rank', 'mode', 'tag', 'why', 'basis',
                  'evidence', 'reviewed', 'note')
EVENT_KEYS = ('id', 'name', 'kind', 'participants', 'place', 'time', 'pre', 'eff', 'after', 'ev', 'tag', 'why',
              'basis', 'rv', 'rb', 'note')
SECRET_KEYS = ('id', 'truth', 'versions', 'knowers_at_open', 'evidence_items', 'note', 'ev', 'tag', 'why', 'basis',
               'rv', 'rb')
IDENT_KEYS = ('id', 'person', 'as_name', 'kind', 'when', 'where', 'believed_by', 'as_person', 'ch', 'ev', 'tag',
              'why', 'basis', 'rv', 'rb', 'note')
GAP_KEYS = ('table', 'field', 'subject', 'fill', 'note')
QA_KEYS = ('id', 'q', 'a', 'support')

# 紧凑键 <-> 完整键
COMPACT_TO_FULL = {'i': 'id', 's': 'subject', 'p': 'property', 'v': 'value', 'q': 'qualifiers', 'r': 'rank',
                   'm': 'mode', 't': 'tag', 'w': 'why', 'b': 'basis', 'e': 'evidence', 'n': 'note'}
FULL_TO_COMPACT = {v: k for k, v in COMPACT_TO_FULL.items()}
COMPACT_ORDER = ('i', 's', 'p', 'v', 'q', 'r', 'm', 't', 'w', 'b', 'e', 'rv', 'rb', 'n')
DEFAULTS = {'rank': 'pref', 'mode': 'narrator', 'tag': 'text', 'basis': 'recall'}


# ----------------------------------------------------------------------------------------------------------------------
# 校验上下文
# ----------------------------------------------------------------------------------------------------------------------
class Ctx:
    """校验时可选的外部信息。某项为 None 表示“不检查引用是否存在”，只做形状检查。"""

    def __init__(self, entities=None, secrets=None, events=None, trait_words=None, strict_traits=False):
        self.entities = entities        # dict 编号 -> 类型 | None
        self.secrets = secrets          # set | None
        self.events = events            # set | None
        self.trait_words = trait_words  # set | None
        self.strict_traits = strict_traits
        self.warnings = []

    def warn(self, msg):
        self.warnings.append(msg)

    def entity_exists(self, eid):
        return self.entities is None or eid in self.entities


def _ctx(ctx):
    return ctx if ctx is not None else Ctx()


# ----------------------------------------------------------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------------------------------------------------------
_PUNCT = set('，。！？；：、“”‘’「」『』（）()[]【】《》"\'…—,.!?;:')


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _short_text_err(v, maxlen, what):
    if not isinstance(v, str) or not v.strip():
        return f'{what} 须为非空字符串'
    if len(v) > maxlen:
        return f'{what} 超过 {maxlen} 字（{len(v)}）；这里只许转述，不许引原文'
    return None


def _tag_err(v, maxlen, what):
    e = _short_text_err(v, maxlen, what)
    if e:
        return e
    if any(c in _PUNCT for c in v) or any(c.isspace() for c in v):
        return f'{what} 只许短标签，不得含引号、句读或空白：{v!r}'
    return None


def _day_of(a, key):
    v = a.get(key)
    return v if _is_int(v) else None


# ----------------------------------------------------------------------------------------------------------------------
# 证据指针
# ----------------------------------------------------------------------------------------------------------------------
POINTER_KEYS = ('ch', 'para', 'start', 'end', 'hash')


def expand_pointer(p):
    """[回,段,起,止,哈希] -> dict；dict 原样复制；其余原样返回（交给校验报错）。"""
    if isinstance(p, (list, tuple)) and len(p) == 5:
        return dict(zip(POINTER_KEYS, p))
    if isinstance(p, dict):
        return dict(p)
    return p


def compact_pointer(p):
    return [p[k] for k in POINTER_KEYS]


def validate_pointer(p, where='evidence'):
    errs = []
    if not isinstance(p, dict):
        hint = ''
        if isinstance(p, (list, tuple)) and len(p) in (3, 4) and isinstance(p[2], str):
            hint = '（这是未解析的锚点：先运行 tools/canon_resolve.py 改写成指针；终稿不得残留锚点）'
        return [f'{where}: 指针须为 {{ch,para,start,end,hash}} 或 [回,段,起,止,哈希]{hint}']
    extra = set(p) - set(POINTER_KEYS)
    if extra:
        errs.append(f'{where}: 指针含未知键 {sorted(extra)}')
    for k in POINTER_KEYS:
        if k not in p:
            errs.append(f'{where}: 指针缺 {k}')
    if errs:
        return errs
    if not _is_int(p['ch']) or p['ch'] < 0:
        errs.append(f'{where}: ch 须为 >=0 的整数')
    if not _is_int(p['para']) or p['para'] < 1:
        errs.append(f'{where}: para 须为 >=1 的整数')
    if not _is_int(p['start']) or not _is_int(p['end']) or p['start'] < 0 or p['end'] < p['start']:
        errs.append(f'{where}: 须 0 <= start <= end')
    if not isinstance(p['hash'], str) or not HASH_RE.match(p['hash']):
        errs.append(f'{where}: hash 须为 16 位小写十六进制')
    return errs


def _expand_evidence(ev):
    if ev is None:
        return []
    if isinstance(ev, (list, tuple)):
        return [expand_pointer(p) for p in ev]
    return ev


def _validate_provenance(rec, where, ctx, errs, check_review=True, ev_name='ev'):
    """tag / why / basis / ev / rv / rb 这组“出处字段”，事件、秘密、身份表共用（rec 已展开）。"""
    tag = rec.get('tag')
    if tag not in TAGS:
        errs.append(f'{where}: tag 须为 {sorted(TAGS)}，得到 {tag!r}')
    why = rec.get('why', '')
    if not isinstance(why, str):
        errs.append(f'{where}: why 须为字符串')
    else:
        if tag == 'infer' and not why.strip():
            errs.append(f'{where}: tag=infer（原著推断）必须写 why（理由）')
        if len(why) > MAX_TEXT:
            errs.append(f'{where}: why 超过 {MAX_TEXT} 字')
    basis = rec.get('basis')
    if basis not in BASES:
        errs.append(f'{where}: basis 须为 text 或 recall，得到 {basis!r}')
    ev = rec.get('ev')
    if not isinstance(ev, list):
        errs.append(f'{where}: {ev_name} 须为数组')
        ev = []
    for i, p in enumerate(ev):
        errs.extend(validate_pointer(p, f'{where}.{ev_name}[{i}]'))
    if basis == 'recall' and ev:
        errs.append(f'{where}: basis=recall（凭记忆）时 {ev_name} 必须为空；有原文指针请把 basis 改为 text')
    if basis == 'text' and not ev:
        errs.append(f'{where}: basis=text 必须至少有一条 {ev_name} 指针')
    if check_review:
        rv = rec.get('rv')
        if rv is not None and rv not in VERDICTS:
            errs.append(f'{where}: rv 须为 sup/rej/doubt，得到 {rv!r}')
        rb = rec.get('rb')
        if rb is not None and not isinstance(rb, str):
            errs.append(f'{where}: rb 须为字符串')
    note = rec.get('note', '')
    if not isinstance(note, str) or len(note) > MAX_TEXT:
        errs.append(f'{where}: note 须为 <= {MAX_TEXT} 字的字符串')


def _expand_provenance(rec):
    """就地补默认并规范中文标签（rec 是浅拷贝）。紧凑键 b（= basis）、e（= ev）也接受（canon_resolve 统一写 b）。"""
    if 'b' in rec and 'basis' not in rec:
        rec['basis'] = rec.pop('b')
    if 'e' in rec and 'ev' not in rec:
        rec['ev'] = rec.pop('e')
    rec['tag'] = norm_enum('tag', rec.get('tag', 'text'))
    rec['basis'] = norm_enum('basis', rec.get('basis', 'recall'))
    rec['ev'] = _expand_evidence(rec.get('ev', []))
    rec.setdefault('why', '')
    rec.setdefault('note', '')
    if 'rv' in rec and rec['rv'] is not None:
        rec['rv'] = norm_enum('verdict', rec['rv'])
        rec.setdefault('rb', 'machine')


# ----------------------------------------------------------------------------------------------------------------------
# 实体登记行
# ----------------------------------------------------------------------------------------------------------------------
def normalize_entity_row(row):
    """登记行规范化：别名里的对象形式 {"name":..,"ambiguous":true} 拆成 aliases(字符串) 与 amb(数组)。
    返回 (新行, 错误列表)。"""
    errs = []
    if not isinstance(row, dict):
        return None, ['登记行须为 JSON 对象']
    out = {k: row[k] for k in row}
    t = out.get('type')
    if t in _ENTITY_TYPE_LABELS:
        out['type'] = t = _ENTITY_TYPE_LABELS[t]
    aliases, amb = [], []
    raw = out.get('aliases', [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        errs.append('aliases 须为数组')
        raw = []
    for a in raw:
        if isinstance(a, str):
            aliases.append(a)
        elif isinstance(a, dict):
            nm = a.get('name', a.get('n'))
            if not isinstance(nm, str):
                errs.append(f'别名对象缺 name：{a!r}')
                continue
            aliases.append(nm)
            if a.get('ambiguous'):
                amb.append(nm)
        else:
            errs.append(f'别名须为字符串或对象：{a!r}')
    for nm in out.get('amb', []) or []:
        if isinstance(nm, str):
            amb.append(nm)
            if nm not in aliases and nm != out.get('name'):
                aliases.append(nm)
    seen, ded = set(), []
    for a in aliases:
        if a not in seen:
            seen.add(a)
            ded.append(a)
    out['aliases'] = ded
    out['amb'] = sorted(set(amb)) if amb else []
    out.setdefault('note', '')
    if not out['amb']:
        out.pop('amb')
    return out, errs


def validate_entity_row(row, ctx=None):
    """校验一条登记行（先规范化）。返回错误列表。"""
    ctx = _ctx(ctx)
    row, errs = normalize_entity_row(row)
    if row is None:
        return errs
    extra = set(row) - set(ENTITY_KEYS)
    if extra:
        errs.append(f'登记行含未知键 {sorted(extra)}')
    t, i, name = row.get('type'), row.get('id'), row.get('name')
    if t not in ENTITY_TYPES:
        errs.append(f'type 须为 {list(ENTITY_TYPES)}，得到 {t!r}')
    if not isinstance(i, str) or not ENTITY_ID_RE.match(i):
        errs.append(f'id 不合规（须形如 type:canon:pinyin，仅 a-z0-9）：{i!r}')
    elif t in ENTITY_TYPES and i.split(':', 1)[0] != t:
        errs.append(f'id 的类型前缀与 type 不一致：{i} vs {t}')
    if not isinstance(name, str) or not name.strip():
        errs.append('name 须为非空字符串')
    elif len(name) > MAX_NAME:
        errs.append(f'name 过长（{len(name)}）')
    for a in row.get('aliases', []):
        if not a or not a.strip():
            errs.append('别名不得为空')
        elif len(a) > MAX_NAME:
            errs.append(f'别名过长：{a[:10]}…')
        elif a == name:
            errs.append(f'别名与 name 重复：{a}')
        elif len(a) == 1:
            ctx.warn(f'{i}: 单字别名 {a!r} 太泛，普查会产生大量误匹配')
    for a in row.get('amb', []):
        if a not in row.get('aliases', []):
            errs.append(f'amb 里的 {a!r} 不在 aliases 中')
    note = row.get('note', '')
    if not isinstance(note, str) or len(note) > MAX_TEXT:
        errs.append(f'note 须为 <= {MAX_TEXT} 字的字符串')
    return errs


# ----------------------------------------------------------------------------------------------------------------------
# 断言：紧凑 <-> 完整
# ----------------------------------------------------------------------------------------------------------------------
def assertion_id(a):
    """内容派生的断言编号：a: + sha256(主体、属性、值、限定词、叙述方式)前 12 位。"""
    key = json.dumps([a.get('subject'), a.get('property'), a.get('value'), a.get('qualifiers') or {},
                      a.get('mode', 'narrator')], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'a:' + hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]


def expand_assertion(raw):
    """任意（紧凑/完整/混合）断言行 -> 完整格式（补默认、规范中文枚举、补 id）。未知键原样保留，交给校验报错。
    不是 dict 时原样返回。"""
    if not isinstance(raw, dict):
        return raw
    full = {}
    for k, v in raw.items():
        if k in COMPACT_TO_FULL and COMPACT_TO_FULL[k] not in raw:
            full[COMPACT_TO_FULL[k]] = v
        elif k == 'rv':
            full.setdefault('reviewed', {})
            if isinstance(full['reviewed'], dict) or full['reviewed'] is None:
                full['reviewed'] = {**(full['reviewed'] or {}), 'verdict': v}
        elif k == 'rb':
            full.setdefault('reviewed', {})
            if isinstance(full['reviewed'], dict) or full['reviewed'] is None:
                full['reviewed'] = {**(full['reviewed'] or {}), 'by': v}
        else:
            full[k] = v
    full['rank'] = norm_enum('rank', full.get('rank', 'pref'))
    full['mode'] = norm_enum('mode', full.get('mode', 'narrator'))
    full['tag'] = norm_enum('tag', full.get('tag', 'text'))
    full['basis'] = norm_enum('basis', full.get('basis', 'recall'))
    full['qualifiers'] = dict(full.get('qualifiers') or {})
    full['evidence'] = _expand_evidence(full.get('evidence', []))
    full.setdefault('why', '')
    full.setdefault('note', '')
    rv = full.get('reviewed')
    if isinstance(rv, dict):
        rv = dict(rv)
        if 'verdict' in rv:
            rv['verdict'] = norm_enum('verdict', rv['verdict'])
        rv.setdefault('by', 'machine')
        full['reviewed'] = rv
    else:
        full['reviewed'] = rv if rv is not None else None
    if 'id' not in full or full['id'] in (None, ''):
        full['id'] = assertion_id(full)
    return full


def compact_assertion(full):
    """完整格式 -> 紧凑格式（省略取默认值的字段与内容派生的 id）。往返无损：
    expand_assertion(compact_assertion(x)) == expand_assertion(x)。"""
    c = {}
    if full.get('id') and full['id'] != assertion_id(full):
        c['i'] = full['id']
    c['s'] = full.get('subject')
    c['p'] = full.get('property')
    c['v'] = full.get('value')
    if full.get('qualifiers'):
        c['q'] = full['qualifiers']
    if full.get('rank', 'pref') != 'pref':
        c['r'] = full['rank']
    if full.get('mode', 'narrator') != 'narrator':
        c['m'] = full['mode']
    if full.get('tag', 'text') != 'text':
        c['t'] = full['tag']
    if full.get('why'):
        c['w'] = full['why']
    if full.get('basis', 'recall') != 'recall':
        c['b'] = full['basis']
    if full.get('evidence'):
        c['e'] = [compact_pointer(p) if isinstance(p, dict) and all(k in p for k in POINTER_KEYS) else p
                  for p in full['evidence']]
    rv = full.get('reviewed')
    if isinstance(rv, dict) and rv.get('verdict'):
        c['rv'] = rv['verdict']
        if rv.get('by', 'machine') != 'machine':
            c['rb'] = rv['by']
    if full.get('note'):
        c['n'] = full['note']
    known = set(ASSERTION_KEYS) | set(COMPACT_TO_FULL) | {'rv', 'rb'}
    for k, v in full.items():          # 未知键保留（让校验器报错，而不是悄悄吞掉）
        if k not in known:
            c[k] = v
    return {k: c[k] for k in COMPACT_ORDER if k in c} | {k: v for k, v in c.items() if k not in COMPACT_ORDER}


# ----------------------------------------------------------------------------------------------------------------------
# 断言校验
# ----------------------------------------------------------------------------------------------------------------------
def _entity_value_err(v, targets, what, ctx):
    """值/限定词是实体编号：形状 + 类型 + （若有上下文）存在性。"""
    if not isinstance(v, str):
        return f'{what} 须为编号字符串，得到 {v!r}'
    t = id_type(v)
    if t is None:
        return f'{what} 不是合规编号：{v!r}'
    if targets and t not in targets:
        return f'{what} 类型须为 {list(targets)}，得到 {t}（{v}）'
    if t == 'secret':
        if ctx.secrets is not None and v not in ctx.secrets:
            return f'{what} 引用了未登记的秘密 {v}'
    elif t == 'event':
        if ctx.events is not None and v not in ctx.events:
            return f'{what} 引用了未登记的事件 {v}'
    elif ctx.entities is not None:
        if v not in ctx.entities:
            return f'{what} 引用了未登记的实体 {v}'
    return None


def _validate_qualifiers(q, prop, ctx, where):
    errs = []
    if not isinstance(q, dict):
        return [f'{where}: qualifiers 须为对象']
    for k, v in q.items():
        kind = QUALIFIERS.get(k)
        if kind is None:
            errs.append(f'{where}: 未知限定词 {k!r}（封闭键集：{sorted(QUALIFIERS)}）')
            continue
        w = f'{where}.q.{k}'
        if kind == 'day':
            if not _is_int(v):
                errs.append(f'{w} 须为整数日数')
        elif kind == 'posint':
            if not _is_int(v) or v < 1:
                errs.append(f'{w} 须为 >=1 的整数')
        elif kind == 'grade':
            if v not in GRADES:
                errs.append(f'{w} 须为 {list(GRADES)}')
        elif kind == 'short':
            e = _short_text_err(v, 12, w)
            if e:
                errs.append(e)
        elif kind == 'via':
            if isinstance(v, str) and v in FROM_SPECIAL:
                pass
            else:
                e = _entity_value_err(v, ('person', 'document'), w, ctx)
                if e:
                    errs.append(e)
        elif kind == 'entity':
            e = _entity_value_err(v, ENTITY_TYPES, w, ctx)
            if e:
                errs.append(e)
        else:   # place / person / org
            e = _entity_value_err(v, (kind,), w, ctx)
            if e:
                errs.append(e)
    if _is_int(q.get('from')) and _is_int(q.get('to')) and q['from'] > q['to']:
        errs.append(f'{where}: 限定词 from 晚于 to')
    if prop is not None:
        for rq in prop.req_quals:
            if rq not in q:
                errs.append(f'{where}: 属性 {prop.key} 必须带限定词 {rq}')
        for qk, enum in prop.qual_enums:
            if qk in q and q[qk] not in enum:
                errs.append(f'{where}: 属性 {prop.key} 的限定词 {qk} 须为 {list(enum)}')
    return errs


def _validate_value(a, prop, ctx, where):
    v = a.get('value')
    s = a.get('subject')
    if v is None:
        return [f'{where}: 缺 value']
    if prop.vtype == 'entity':
        if v == 'none':
            return [] if prop.none_ok else [f'{where}: 属性 {prop.key} 不允许 "none"']
        e = _entity_value_err(v, prop.targets, f'{where}.value', ctx)
        if e:
            return [e]
        if v == s and prop.key not in ('route',):
            return [f'{where}: 值不得与主体相同（{s}）']
        return []
    if prop.vtype == 'int':
        if not _is_int(v) or v < 0:
            return [f'{where}.value 须为 >=0 的整数']
        return []
    if prop.vtype == 'day':
        return [] if _is_int(v) else [f'{where}.value 须为整数日数']
    if prop.vtype == 'bool':
        return [] if isinstance(v, bool) else [f'{where}.value 须为布尔']
    if prop.vtype == 'string':
        e = _tag_err(v, prop.maxlen, f'{where}.value') if prop.tagonly else _short_text_err(v, prop.maxlen,
                                                                                         f'{where}.value')
        if e:
            return [e]
        if prop.enum is not None and v not in prop.enum:
            return [f'{where}.value 须为 {list(prop.enum)}，得到 {v!r}']
        if prop.vocab == 'trait' and ctx.trait_words is not None and v not in ctx.trait_words:
            msg = f'{where}: 性格词 {v!r} 不在 data/canon/trait_words.json 词表里'
            if ctx.strict_traits:
                return [msg]
            ctx.warn(msg)
        return []
    return [f'{where}: 内部错误：未知值类型 {prop.vtype}']


def validate_assertion(a, ctx=None, where='断言'):
    """校验一条**完整格式**的断言。返回错误列表。"""
    ctx = _ctx(ctx)
    if not isinstance(a, dict):
        return [f'{where}: 须为 JSON 对象']
    errs = []
    w = f'{where}[{a.get("id", "?")}]'
    extra = set(a) - set(ASSERTION_KEYS)
    if extra:
        errs.append(f'{w}: 未知字段 {sorted(extra)}（紧凑键请用 i s p v q r m t w b e rv rb n）')
    if not isinstance(a.get('id'), str) or not ASSERTION_ID_RE.match(a['id']):
        errs.append(f'{w}: id 不合规（[A-Za-z0-9_.:-]{{1,40}}）')
    s, p = a.get('subject'), a.get('property')
    stype = None
    if not isinstance(s, str) or not ENTITY_ID_RE.match(s):
        errs.append(f'{w}: subject 须为实体编号，得到 {s!r}')
    else:
        stype = s.split(':', 1)[0]
        if ctx.entities is not None and s not in ctx.entities:
            errs.append(f'{w}: subject {s} 未在登记表里（先在普查里登记）')
    prop = PROPS.get(p)
    if prop is None:
        errs.append(f'{w}: 属性 {p!r} 不在封闭清单内')
    elif prop.derived:
        errs.append(f'{w}: 属性 {p} 是派生属性，不得写断言（由编译推出）')
    else:
        if stype and stype not in prop.subjects:
            errs.append(f'{w}: 属性 {p} 只用于 {list(prop.subjects)}，主体是 {stype}')
        errs.extend(_validate_value(a, prop, ctx, w))
    errs.extend(_validate_qualifiers(a.get('qualifiers', {}), prop if (prop and not prop.derived) else None, ctx, w))
    rank, mode = a.get('rank'), a.get('mode')
    if rank not in RANKS:
        errs.append(f'{w}: rank 须为 pref/norm/dep，得到 {rank!r}')
    if mode not in MODES:
        errs.append(f'{w}: mode 须为 narrator/speech/memory/hearsay，得到 {mode!r}')
    q = a.get('qualifiers') if isinstance(a.get('qualifiers'), dict) else {}
    if mode in ('speech', 'memory') and 'speaker' not in q:
        errs.append(f'{w}: mode={mode} 必须带限定词 speaker（谁这么说/回忆的）')
    if mode in MODES and mode != 'narrator' and rank == 'pref':
        errs.append(f'{w}: 非叙述者陈述（mode={mode}）不得是首选；人物的话只记成“某人这么说过”')
    # 来源与证据
    flat = {'tag': a.get('tag'), 'why': a.get('why', ''), 'basis': a.get('basis'), 'ev': a.get('evidence'),
            'note': a.get('note', '')}
    _validate_provenance(flat, w, ctx, errs, check_review=False, ev_name='evidence')
    rv = a.get('reviewed')
    if rv is not None:
        if not isinstance(rv, dict) or rv.get('verdict') not in VERDICTS:
            errs.append(f'{w}: reviewed 须为 null 或 {{"verdict":"sup|rej|doubt","by":..}}')
        else:
            if not isinstance(rv.get('by', ''), str):
                errs.append(f'{w}: reviewed.by 须为字符串')
            if rv['verdict'] == 'rej' and rank != 'dep':
                errs.append(f'{w}: 复核“不支持”的断言只能是 dep（作废），不进入后续阶段')
    if rank == 'pref' and a.get('basis') == 'text' and not a.get('evidence'):
        errs.append(f'{w}: 首选断言（basis=text）至少一条证据')
    return errs


def validate_assertion_raw(raw, ctx=None, where='断言'):
    """紧凑/完整都行：先展开再校验。返回 (完整格式或 None, 错误列表)。"""
    if not isinstance(raw, dict):
        return None, [f'{where}: 须为 JSON 对象']
    full = expand_assertion(raw)
    return full, validate_assertion(full, ctx, where)


def _span(q):
    lo = q.get('from') if _is_int(q.get('from')) else float('-inf')
    hi = q.get('to') if _is_int(q.get('to')) else float('inf')
    return lo, hi


def check_assertion_set(items, ctx=None):
    """集合级检查。items: [(where, 完整格式断言)]。返回错误列表：
    同编号却内容不同、单值属性首选断言的时间重叠冲突。
    **“重复”只是警告**（经 ctx.warn 报告，不进错误列表）：同编号同内容、或不同编号但内容相同（相同主体、属性、值、限定词、
    叙述方式）——同一事实可在多回里各出现一次，第 6 阶段合并证据。"""
    ctx = _ctx(ctx)
    errs = []
    by_id, by_content = {}, {}
    groups = {}
    for where, a in items:
        if not isinstance(a, dict):
            continue
        i = a.get('id')
        ck = assertion_id({**a, 'id': None})
        if i in by_id:
            w0, ck0 = by_id[i]
            if ck0 == ck:
                ctx.warn(f'{where}: 断言编号 {i} 与 {w0} 重复（内容相同；第 6 阶段合并证据）')
            else:
                errs.append(f'{where}: 断言编号 {i} 与 {w0} 相同但内容不同（编号冲突）')
        else:
            by_id[i] = (where, ck)
            if ck in by_content and by_content[ck][1] != i:
                ctx.warn(f'{where}: 与 {by_content[ck][0]} 内容重复（相同主体、属性、值、限定词、叙述方式；第 6 阶段合并证据）')
            else:
                by_content.setdefault(ck, (where, i))
        prop = PROPS.get(a.get('property'))
        if prop is None or prop.multi or prop.derived:
            continue
        if a.get('rank') == 'pref' and a.get('mode', 'narrator') == 'narrator':
            groups.setdefault((a.get('subject'), a.get('property')), []).append((where, a))
    for (s, p), lst in sorted(groups.items(), key=lambda kv: str(kv[0])):
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                (w1, a1), (w2, a2) = lst[x], lst[y]
                if a1.get('value') == a2.get('value'):
                    continue
                l1, h1 = _span(a1.get('qualifiers') or {})
                l2, h2 = _span(a2.get('qualifiers') or {})
                if l1 <= h2 and l2 <= h1:
                    errs.append(f'{w2}: 单值属性 {p} 在 {s} 上有两条时间重叠的首选断言（{w1} 与此条），'
                                f'请把被揭穿的一条改为 dep，或加 from/to 区分')
    return errs


# ----------------------------------------------------------------------------------------------------------------------
# 事件、前提、结果
# ----------------------------------------------------------------------------------------------------------------------
def _param_err(kind, v, ctx, what):
    if kind == 'bool':
        return None if isinstance(v, bool) else f'{what} 须为布尔'
    if kind == 'int':
        return None if _is_int(v) else f'{what} 须为整数'
    if kind == 'delta':
        return None if _is_int(v) and -100 <= v <= 100 else f'{what} 须为 -100 到 100 的整数'
    if kind in ('person', 'place', 'org'):
        return _entity_value_err(v, (kind,), what, ctx)
    if kind == 'item':
        return _entity_value_err(v, ('item', 'document'), what, ctx)
    if kind == 'holder':
        return _entity_value_err(v, ('person', 'org', 'place'), what, ctx)
    if kind == 'what':
        return _entity_value_err(v, ('secret', 'event'), what, ctx)
    if kind == 'flagname':
        return None if isinstance(v, str) and FLAG_RE.match(v) else f'{what} 须为 [a-z][a-z0-9_]* 的标志名'
    if kind == 'flagvalue':
        if isinstance(v, bool) or _is_int(v):
            return None
        if isinstance(v, str) and v and len(v) <= 20 and not any(c.isspace() for c in v):
            return None
        return f'{what} 须为布尔、整数或不含空白的短字符串'
    if kind == 'belief':
        if isinstance(v, str) and v and (v in BELIEF_SPECIAL or ASCII_KEY_RE.match(v)):
            return None
        return f'{what} 须为 truth/suspect 或秘密 versions 里的 ASCII 版本键'
    if kind == 'src':
        if isinstance(v, str) and v in FROM_SPECIAL:
            return None
        return _entity_value_err(v, ('person', 'document'), what, ctx)
    if kind == 'relkind':
        return None if v in RELATION_KINDS else f'{what} 须为 {list(RELATION_KINDS)}'
    return f'{what}: 内部错误：未知参数种类 {kind}'


def validate_op(op, table, ctx, where):
    """校验一个前提/结果。table 是 PRE_OPS 或 EFF_OPS。"""
    if not isinstance(op, dict):
        return [f'{where}: 须为对象']
    name = op.get('op')
    if name not in table:
        return [f'{where}: 操作 {name!r} 不在封闭词表内（{sorted(table)}）']
    req, opt = table[name]
    errs = []
    extra = set(op) - {'op'} - set(req) - set(opt)
    if extra:
        errs.append(f'{where}: {name} 含未知参数 {sorted(extra)}')
    for k, kind in req.items():
        if k not in op:
            errs.append(f'{where}: {name} 缺参数 {k}')
        else:
            e = _param_err(kind, op[k], ctx, f'{where}.{k}')
            if e:
                errs.append(e)
    for k, kind in opt.items():
        if k in op:
            e = _param_err(kind, op[k], ctx, f'{where}.{k}')
            if e:
                errs.append(e)
    return errs


def expand_event(raw):
    """补默认值、规范中文标签。不是 dict 原样返回。"""
    if not isinstance(raw, dict):
        return raw
    e = dict(raw)
    e['kind'] = norm_enum('kind_event', e.get('kind'))
    e.setdefault('participants', [])
    e['participants'] = [dict(p, role=norm_enum('role', p.get('role', 'other'))) if isinstance(p, dict) else p
                         for p in e['participants']] if isinstance(e['participants'], list) else e['participants']
    e.setdefault('place', None)
    t = e.get('time')
    if isinstance(t, dict):
        t = dict(t)
        if 'start' in t:
            t.setdefault('end', t['start'])
        t.setdefault('approx', False)
        e['time'] = t
    e.setdefault('pre', [])
    e.setdefault('eff', [])
    e.setdefault('after', [])
    _expand_provenance(e)
    return e


def validate_event(e, ctx=None, where='事件'):
    """校验一条（已展开的）事件。"""
    ctx = _ctx(ctx)
    if not isinstance(e, dict):
        return [f'{where}: 须为 JSON 对象']
    errs = []
    w = f'{where}[{e.get("id", "?")}]'
    extra = set(e) - set(EVENT_KEYS)
    if extra:
        errs.append(f'{w}: 未知字段 {sorted(extra)}')
    if not isinstance(e.get('id'), str) or not EVENT_ID_RE.match(e['id']):
        errs.append(f'{w}: id 须形如 event:canon:短语（[a-z][a-z0-9_]*）')
    e_name = e.get('name')
    if not isinstance(e_name, str) or not e_name.strip() or len(e_name) > 40:
        errs.append(f'{w}: name 须为 1–40 字的字符串')
    kind = e.get('kind')
    if kind not in EVENT_KINDS:
        errs.append(f'{w}: kind 须为 plot 或 history，得到 {kind!r}')
    parts = e.get('participants')
    if not isinstance(parts, list):
        errs.append(f'{w}: participants 须为数组')
        parts = []
    seen = set()
    for i, p in enumerate(parts):
        pw = f'{w}.participants[{i}]'
        if not isinstance(p, dict):
            errs.append(f'{pw}: 须为 {{person, role}}')
            continue
        if set(p) - {'person', 'role'}:
            errs.append(f'{pw}: 含未知键 {sorted(set(p) - {"person", "role"})}')
        er = _entity_value_err(p.get('person'), ('person',), f'{pw}.person', ctx)
        if er:
            errs.append(er)
        if p.get('role') not in ROLES:
            errs.append(f'{pw}: role 须为 {sorted(ROLES)}，得到 {p.get("role")!r}')
        if p.get('person') in seen:
            errs.append(f'{pw}: 同一人物重复出现')
        seen.add(p.get('person'))
    pl = e.get('place')
    if pl is not None:
        er = _entity_value_err(pl, ('place',), f'{w}.place', ctx)
        if er:
            errs.append(er)
    t = e.get('time')
    st = en = None
    if not isinstance(t, dict):
        errs.append(f'{w}: time 须为 {{"start":日,"end":日}}')
    else:
        if set(t) - {'start', 'end', 'approx'}:
            errs.append(f'{w}.time: 含未知键 {sorted(set(t) - {"start", "end", "approx"})}')
        st, en = t.get('start'), t.get('end', t.get('start'))
        if not _is_int(st) or not _is_int(en):
            errs.append(f'{w}.time: start/end 须为整数日数（开局=0，旧案为负）')
            st = en = None
        elif en < st:
            errs.append(f'{w}.time: end 早于 start')
            st = en = None
        if 'approx' in t and not isinstance(t['approx'], bool):
            errs.append(f'{w}.time.approx 须为布尔')
    if st is not None:
        if kind == 'plot' and st < 0:
            errs.append(f'{w}: kind=plot（情节）的 time.start 须 >= 0；开局之前的事是 history')
        if kind == 'history' and en > -1:
            errs.append(f'{w}: kind=history（历史）的 time.end 须 <= -1；开局之后的事是 plot')
    for key, table in (('pre', PRE_OPS), ('eff', EFF_OPS)):
        lst = e.get(key)
        if not isinstance(lst, list):
            errs.append(f'{w}: {key} 须为数组')
            continue
        for i, op in enumerate(lst):
            errs.extend(validate_op(op, table, ctx, f'{w}.{key}[{i}]'))
    af = e.get('after')
    if not isinstance(af, list):
        errs.append(f'{w}: after 须为数组')
    else:
        for i, x in enumerate(af):
            if not isinstance(x, str) or not EVENT_ID_RE.match(x):
                errs.append(f'{w}.after[{i}]: 须为事件编号')
            elif ctx.events is not None and x not in ctx.events:
                errs.append(f'{w}.after[{i}]: 引用了未登记的事件 {x}')
            elif x == e.get('id'):
                errs.append(f'{w}.after[{i}]: 事件不能先于自己')
    _validate_provenance(e, w, ctx, errs)
    return errs


def expand_secret(raw):
    if not isinstance(raw, dict):
        return raw
    s = dict(raw)
    s.setdefault('versions', [])
    s.setdefault('knowers_at_open', [])
    s.setdefault('evidence_items', [])
    _expand_provenance(s)
    return s


def validate_secret(s, ctx=None, where='秘密'):
    ctx = _ctx(ctx)
    if not isinstance(s, dict):
        return [f'{where}: 须为 JSON 对象']
    errs = []
    w = f'{where}[{s.get("id", "?")}]'
    extra = set(s) - set(SECRET_KEYS)
    if extra:
        errs.append(f'{w}: 未知字段 {sorted(extra)}')
    if not isinstance(s.get('id'), str) or not SECRET_ID_RE.match(s['id']):
        errs.append(f'{w}: id 须形如 secret:canon:短语')
    e = _short_text_err(s.get('truth'), MAX_TEXT, f'{w}.truth')
    if e:
        errs.append(e)
    vkeys = set()
    vs = s.get('versions')
    if not isinstance(vs, list):
        errs.append(f'{w}: versions 须为数组')
        vs = []
    for i, v in enumerate(vs):
        if not isinstance(v, dict) or set(v) != {'key', 'text'}:
            errs.append(f'{w}.versions[{i}]: 须为 {{"key","text"}}')
            continue
        if not isinstance(v['key'], str) or not ASCII_KEY_RE.match(v['key']) or v['key'] in BELIEF_SPECIAL:
            errs.append(f'{w}.versions[{i}].key: 须为 ASCII 键，且不得是 truth/suspect')
        elif v['key'] in vkeys:
            errs.append(f'{w}.versions[{i}].key: 版本键重复')
        vkeys.add(v['key'])
        e = _short_text_err(v['text'], MAX_TEXT, f'{w}.versions[{i}].text')
        if e:
            errs.append(e)
    ks = s.get('knowers_at_open')
    if not isinstance(ks, list):
        errs.append(f'{w}: knowers_at_open 须为数组')
        ks = []
    seen = set()
    for i, k in enumerate(ks):
        kw = f'{w}.knowers_at_open[{i}]'
        if not isinstance(k, dict):
            errs.append(f'{kw}: 须为对象')
            continue
        if set(k) - {'person', 'believes', 'from', 'since'}:
            errs.append(f'{kw}: 含未知键 {sorted(set(k) - {"person", "believes", "from", "since"})}')
        er = _entity_value_err(k.get('person'), ('person',), f'{kw}.person', ctx)
        if er:
            errs.append(er)
        if k.get('person') in seen:
            errs.append(f'{kw}: 同一人物重复')
        seen.add(k.get('person'))
        b = k.get('believes')
        if not (isinstance(b, str) and (b in BELIEF_SPECIAL or b in vkeys)):
            errs.append(f'{kw}.believes 须为 truth/suspect 或本秘密 versions 里的键，得到 {b!r}')
        fr = k.get('from')
        if not (isinstance(fr, str) and fr in FROM_SPECIAL):
            er = _entity_value_err(fr, ('person', 'document'), f'{kw}.from', ctx)
            if er:
                errs.append(er)
        if 'since' in k and not _is_int(k['since']):
            errs.append(f'{kw}.since 须为整数日数')
    items = s.get('evidence_items')
    if not isinstance(items, list):
        errs.append(f'{w}: evidence_items 须为数组')
        items = []
    for i, it in enumerate(items):
        er = _entity_value_err(it, ('item', 'document'), f'{w}.evidence_items[{i}]', ctx)
        if er:
            errs.append(er)
    _validate_provenance(s, w, ctx, errs)
    return errs


def expand_identity(raw):
    if not isinstance(raw, dict):
        return raw
    r = dict(raw)
    r['kind'] = norm_enum('kind_ident', r.get('kind'))
    r.setdefault('when', None)
    r.setdefault('where', None)
    r.setdefault('believed_by', [])
    _expand_provenance(r)
    return r


def validate_identity(r, ctx=None, where='身份'):
    ctx = _ctx(ctx)
    if not isinstance(r, dict):
        return [f'{where}: 须为 JSON 对象']
    errs = []
    w = f'{where}[{r.get("person", "?")}/{r.get("as_name", "?")}]'
    extra = set(r) - set(IDENT_KEYS)
    if extra:
        errs.append(f'{w}: 未知字段 {sorted(extra)}')
    if r.get('id') is not None and not (isinstance(r['id'], str) and ASSERTION_ID_RE.match(r['id'])):
        errs.append(f'{w}: id 不合规')
    er = _entity_value_err(r.get('person'), ('person',), f'{w}.person', ctx)
    if er:
        errs.append(er)
    e = _short_text_err(r.get('as_name'), MAX_NAME, f'{w}.as_name')
    if e:
        errs.append(e)
    if r.get('kind') not in IDENT_KINDS:
        errs.append(f'{w}: kind 须为 {sorted(IDENT_KINDS)}')
    wh = r.get('when')
    if wh is not None:
        if not isinstance(wh, dict) or set(wh) - {'start', 'end'} or not _is_int(wh.get('start')) \
                or not _is_int(wh.get('end', wh.get('start'))):
            errs.append(f'{w}: when 须为 null 或 {{"start":日,"end":日}}')
        elif wh.get('end', wh['start']) < wh['start']:
            errs.append(f'{w}: when.end 早于 start')
    if r.get('where') is not None:
        er = _entity_value_err(r['where'], ('place',), f'{w}.where', ctx)
        if er:
            errs.append(er)
    bb = r.get('believed_by')
    if not isinstance(bb, list):
        errs.append(f'{w}: believed_by 须为数组')
        bb = []
    for i, x in enumerate(bb):
        if x == '*':
            continue
        er = _entity_value_err(x, ('person',), f'{w}.believed_by[{i}]', ctx)
        if er:
            errs.append(er)
    if r.get('as_person') is not None:
        er = _entity_value_err(r['as_person'], ('person',), f'{w}.as_person', ctx)
        if er:
            errs.append(er)
        elif r['as_person'] == r.get('person'):
            errs.append(f'{w}: as_person 不得是真身自己')
    ch = r.get('ch')
    if ch is not None:
        if not (isinstance(ch, list) and len(ch) == 2 and all(_is_int(x) and x >= 0 for x in ch) and ch[0] <= ch[1]):
            errs.append(f'{w}: ch 须为 [起回, 止回]')
    _validate_provenance(r, w, ctx, errs)
    return errs


def expand_gap(raw):
    if not isinstance(raw, dict):
        return raw
    g = dict(raw)
    if isinstance(g.get('fill'), list):
        g['fill'] = [norm_enum('fill', x) for x in g['fill']]
    g.setdefault('subject', None)
    g.setdefault('note', '')
    return g


def validate_gap(g, ctx=None, where='缺口'):
    ctx = _ctx(ctx)
    if not isinstance(g, dict):
        return [f'{where}: 须为 JSON 对象']
    errs = []
    w = f'{where}[{g.get("table", "?")}.{g.get("field", "?")}]'
    extra = set(g) - set(GAP_KEYS)
    if extra:
        errs.append(f'{w}: 未知字段 {sorted(extra)}')
    if g.get('table') not in GAP_TABLES:
        errs.append(f'{w}: table 须为 {list(GAP_TABLES)}')
    if not isinstance(g.get('field'), str) or not ASCII_KEY_RE.match(g['field']):
        errs.append(f'{w}: field 须为 ASCII 键')
    sub = g.get('subject')
    if sub is not None:
        if isinstance(sub, str) and re.match(r'^(person|place|org|item|martial|document):\*$', sub):
            pass
        else:
            er = _entity_value_err(sub, ENTITY_TYPES + ('secret', 'event'), f'{w}.subject', ctx)
            if er:
                errs.append(er)
    fl = g.get('fill')
    if not isinstance(fl, list) or not fl:
        errs.append(f'{w}: fill 须为非空数组，元素取自 {sorted(FILLS)}')
    else:
        for x in fl:
            if x not in FILLS:
                errs.append(f'{w}: fill 的 {x!r} 须为 {sorted(FILLS)}')
    note = g.get('note', '')
    if not isinstance(note, str) or len(note) > MAX_TEXT:
        errs.append(f'{w}: note 须为 <= {MAX_TEXT} 字的字符串')
    return errs


def validate_qa(r, ctx=None, assertion_ids=None, where='问答'):
    if not isinstance(r, dict):
        return [f'{where}: 须为 JSON 对象']
    errs = []
    w = f'{where}[{r.get("id", "?")}]'
    extra = set(r) - set(QA_KEYS)
    if extra:
        errs.append(f'{w}: 未知字段 {sorted(extra)}')
    if r.get('id') is not None and not (isinstance(r['id'], str) and ASSERTION_ID_RE.match(r['id'])):
        errs.append(f'{w}: id 不合规')
    for k in ('q', 'a'):
        e = _short_text_err(r.get(k), MAX_TEXT, f'{w}.{k}')
        if e:
            errs.append(e)
    sup = r.get('support')
    if not isinstance(sup, list) or not sup:
        errs.append(f'{w}: support 须为非空的断言编号数组')
    else:
        for x in sup:
            if not isinstance(x, str) or not ASSERTION_ID_RE.match(x):
                errs.append(f'{w}: support 里的 {x!r} 不是断言编号')
            elif assertion_ids is not None and x not in assertion_ids:
                errs.append(f'{w}: support 引用了不存在的断言 {x}')
    return errs


# ----------------------------------------------------------------------------------------------------------------------
# JSONL 读写
# ----------------------------------------------------------------------------------------------------------------------
def dumps_line(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def read_jsonl(path):
    """读一个 JSONL 文件。返回 ([(行号, 对象)], [错误])。空行与 # 开头的行忽略。"""
    rows, errs = [], []
    p = Path(path)
    try:
        text = p.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeDecodeError) as ex:
        return rows, [f'{p}: 无法读取（{ex}）']
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as ex:
            errs.append(f'{p}:{n}: JSON 解析失败（{ex.msg}，列 {ex.colno}）')
            continue
        rows.append((n, obj))
    return rows, errs


def list_jsonl_files(path):
    """文件 -> [它]；目录 -> 其中所有 *.jsonl（按文件名排序）；不存在 -> []。"""
    p = Path(path)
    if p.is_dir():
        return sorted(q for q in p.glob('*.jsonl') if q.is_file())
    if p.is_file():
        return [p]
    return []


def read_records(path):
    """读文件或目录。返回 ([(文件, 行号, 对象)], [错误])。"""
    out, errs = [], []
    for f in list_jsonl_files(path):
        rows, e = read_jsonl(f)
        errs.extend(e)
        out.extend((str(f), n, obj) for n, obj in rows)
    return out, errs


def write_jsonl(path, objs):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        for o in objs:
            f.write(dumps_line(o) + '\n')


def read_assertions(path):
    """读断言文件/目录（紧凑、完整可混）。返回 ([(位置, 完整格式)], [解析错误])。位置形如 文件名:行号。"""
    recs, errs = read_records(path)
    out = []
    for f, n, obj in recs:
        out.append((f'{Path(f).name}:{n}', expand_assertion(obj)))
    return out, errs


def write_assertions(path, fulls, compact=True):
    write_jsonl(path, [compact_assertion(a) if compact else a for a in fulls])


# ----------------------------------------------------------------------------------------------------------------------
# 性格词表
# ----------------------------------------------------------------------------------------------------------------------
TRAIT_SCALES = ('D', 'S', 'G', 'T', 'R')


def trait_words_path():
    return CANON_DIR / 'trait_words.json'


def load_trait_words(path=None):
    """读性格词表，返回 dict（无文件返回 None）。"""
    p = Path(path) if path else trait_words_path()
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding='utf-8'))


def validate_trait_words(data):
    errs = []
    if not isinstance(data, dict) or not isinstance(data.get('words'), dict):
        return ['trait_words.json 须有对象字段 words']
    if set(data.get('scales', {})) != set(TRAIT_SCALES):
        errs.append(f'scales 的键须恰为 {list(TRAIT_SCALES)}')
    for w, m in data['words'].items():
        if not isinstance(m, dict):
            errs.append(f'词 {w}: 须为对象')
            continue
        if len(w) > 12:
            errs.append(f'词 {w}: 过长')
        for k, v in m.items():
            if k == 'note':
                if not isinstance(v, str) or len(v) > 60:
                    errs.append(f'词 {w}: note 须为 <= 60 字的字符串')
            elif k in TRAIT_SCALES:
                if not _is_int(v) or not -30 <= v <= 30:
                    errs.append(f'词 {w}: {k} 须为 -30..30 的整数')
            else:
                errs.append(f'词 {w}: 未知键 {k}')
        if not any(_is_int(m.get(k)) and m.get(k) != 0 for k in TRAIT_SCALES):
            errs.append(f'词 {w}: 至少要有一项非零增减')
    return errs


def apply_traits(words, table):
    """把一组性格词折成五项刻度（基线 50，夹到 0..100）。供编译与测试用。"""
    scale = {k: 50 for k in TRAIT_SCALES}
    for w in words:
        for k, d in table['words'].get(w, {}).items():
            if k in scale:
                scale[k] += d
    return {k: max(0, min(100, v)) for k, v in scale.items()}


# ----------------------------------------------------------------------------------------------------------------------
# 30 人召回名单（固定）。第三列是人物普查分区：按“首见回”（姓名或所列别名在正文第 1–50 回里第一次出现的回）：
# p1 = 第 1–12 回，p2 = 13–25，p3 = 26–38，p4 = 39–52（见 docs/CANON_SCHEMA.md 第 11、12 节）
# ----------------------------------------------------------------------------------------------------------------------
RECALL_30 = (
    ('乔峰', 'person:canon:qiaofeng', 'p1'),
    ('段誉', 'person:canon:duanyu', 'p1'),
    ('虚竹', 'person:canon:xuzhu', 'p3'),
    ('慕容复', 'person:canon:murongfu', 'p1'),
    ('王语嫣', 'person:canon:wangyuyan', 'p1'),
    ('阿朱', 'person:canon:azhu', 'p1'),
    ('阿紫', 'person:canon:azi', 'p2'),
    ('木婉清', 'person:canon:muwanqing', 'p1'),
    ('钟灵', 'person:canon:zhongling', 'p1'),
    ('段正淳', 'person:canon:duanzhengchun', 'p1'),
    ('保定帝', 'person:canon:baodingdi', 'p1'),
    ('刀白凤', 'person:canon:daobaifeng', 'p1'),
    ('段延庆', 'person:canon:duanyanqing', 'p1'),
    ('叶二娘', 'person:canon:yeerniang', 'p1'),
    ('云中鹤', 'person:canon:yunzhonghe', 'p1'),
    ('南海鳄神', 'person:canon:nanhaieshen', 'p1'),
    ('鸠摩智', 'person:canon:jiumozhi', 'p1'),
    ('游坦之', 'person:canon:youtanzhi', 'p2'),
    ('天山童姥', 'person:canon:tianshantonglao', 'p1'),
    ('李秋水', 'person:canon:liqiushui', 'p3'),
    ('无崖子', 'person:canon:wuyazi', 'p3'),
    ('丁春秋', 'person:canon:dingchunqiu', 'p1'),
    ('苏星河', 'person:canon:suxinghe', 'p3'),
    ('玄慈', 'person:canon:xuanci', 'p1'),
    ('萧远山', 'person:canon:xiaoyuanshan', 'p2'),
    ('慕容博', 'person:canon:murongbo', 'p1'),
    ('康敏', 'person:canon:kangmin', 'p2'),
    ('全冠清', 'person:canon:quanguanqing', 'p2'),
    ('包不同', 'person:canon:baobutong', 'p2'),
    ('风波恶', 'person:canon:fengboe', 'p2'),
)
RECALL_IDS = tuple(r[1] for r in RECALL_30)
assert len(RECALL_IDS) == 30 and len(set(RECALL_IDS)) == 30
