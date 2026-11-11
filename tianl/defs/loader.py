"""定义加载器（计划 4.1）：defs 目录下的 TOML 文本文件 → 稳定编号索引。

约定
----
* 一个 TOML 文件里，每个顶层表就是一条定义，表名是稳定编号：  ["place:shaolin:library"]
  （表名含冒号，必须加引号）。编号形如 kind:scope:name，kind 必须登记在 kinds.py。
* 可选 parent = "<编号>"：先取父定义，再用本条覆盖。字典逐层合并，列表与标量整体替换。
* 可选 _abstract = true：只供继承，不出现在 by_kind 的默认结果里（也不要求引用完整）。
* 引用完整性：任何字符串，若整串恰为“已登记 kind 开头的编号”，就必须能解析到某条定义
  （键名为 note/notes/text/desc/doc/comment 或以下划线开头的字段除外）。
* 运行时的钥匙：place 定义必须有 code（如 SH_LIBRARY），内核/引擎/数据库只认 code；
  编号只用在定义之间互相引用与控制台别名查找。by_code() 给出反查。

加载出的定义是只读的 dict（已展开继承），附带 id、kind、_file 三个键。
"""
from __future__ import annotations

import copy
import re
import tomllib
from pathlib import Path

from .kinds import ALL_KINDS

ID_RE = re.compile(r'^([a-z_]+):([^\s:"\']+(?::[^\s:"\']+)*)$')
NOTE_KEYS = frozenset({'note', 'notes', 'text', 'desc', 'doc', 'comment'})


class DefsError(Exception):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__('定义加载失败：\n  ' + '\n  '.join(self.problems))


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class Defs:
    def __init__(self, extra_kinds=()):
        self.kinds = set(ALL_KINDS) | set(extra_kinds)
        self._raw: dict[str, dict] = {}
        self._file: dict[str, str] = {}
        self._res: dict[str, dict] = {}
        self.problems: list[str] = []
        self._code: dict[tuple, str] = {}

    # ------------------------------------------------------------ 载入
    @classmethod
    def load(cls, *roots, extra_kinds=(), strict=True) -> 'Defs':
        d = cls(extra_kinds)
        for r in roots:
            r = Path(r)
            files = [r] if r.is_file() else sorted(r.rglob('*.toml'))
            for f in files:
                d.add_file(f)
        d.validate()
        if strict and d.problems:
            raise DefsError(d.problems)
        return d

    def add_file(self, path):
        path = Path(path)
        try:
            data = tomllib.loads(path.read_text(encoding='utf-8'))
        except (tomllib.TOMLDecodeError, OSError) as e:
            self.problems.append(f'{path}: 无法解析 ({e})')
            return
        for key, body in data.items():
            if key == 'meta' and isinstance(body, dict):
                continue
            m = ID_RE.match(key)
            if not m or m.group(1) not in self.kinds or not isinstance(body, dict):
                self.problems.append(f'{path}: 顶层键 {key!r} 不是合法定义编号（kind:scope:name，kind 须登记）')
                continue
            if key in self._raw:
                self.problems.append(f'{path}: 编号 {key} 重复，另见 {self._file[key]}')
                continue
            k = body.get('kind')
            if k is not None and k != m.group(1):
                self.problems.append(f'{path}: {key} 的 kind 字段 {k!r} 与编号前缀不符')
            self._raw[key] = body
            self._file[key] = str(path)
        self._res.clear()

    def add(self, id, body, file='<code>'):
        """代码里直接登记一条定义（测试与生成式定义用）。"""
        m = ID_RE.match(id)
        if not m or m.group(1) not in self.kinds:
            raise DefsError([f'{id!r} 不是合法定义编号'])
        if id in self._raw:
            raise DefsError([f'编号 {id} 重复'])
        self._raw[id] = dict(body)
        self._file[id] = file
        self._res.clear()

    # ------------------------------------------------------------ 解析与查询
    def _resolve(self, id, stack=()):
        if id in self._res:
            return self._res[id]
        if id in stack:
            raise DefsError([f'继承成环：{" -> ".join(stack + (id,))}'])
        raw = self._raw[id]
        parent = raw.get('parent')
        if parent is not None:
            if parent not in self._raw:
                raise DefsError([f'{id} 的 parent {parent} 不存在'])
            merged = _merge(self._resolve(parent, stack + (id,)), raw)
            if '_abstract' not in raw:
                merged.pop('_abstract', None)
        else:
            merged = copy.deepcopy(raw)
        merged['id'] = id
        merged['kind'] = id.split(':', 1)[0]
        merged['_file'] = self._file[id]
        self._res[id] = merged
        return merged

    def __contains__(self, id):
        return id in self._raw

    def __len__(self):
        return len(self._raw)

    def get(self, id) -> dict:
        if id not in self._raw:
            raise KeyError(id)
        return self._resolve(id)

    def ids(self):
        return sorted(self._raw)

    def by_kind(self, kind, include_abstract=False):
        out = []
        for i in sorted(self._raw):
            if i.startswith(kind + ':'):
                d = self._resolve(i)
                if include_abstract or not d.get('_abstract'):
                    out.append(d)
        return out

    def by_code(self, kind, code):
        if not self._code:
            for i in sorted(self._raw):
                d = self._resolve(i)
                if 'code' in d and not d.get('_abstract'):
                    self._code[(d['kind'], d['code'])] = i
        i = self._code.get((kind, code))
        return self._resolve(i) if i else None

    # ------------------------------------------------------------ 校验
    def _refs(self, v, key=None):
        """递归产出 (字段名, 编号) —— 整串恰为已登记 kind 的编号才算引用。"""
        if isinstance(v, str):
            if key in NOTE_KEYS or (key and key.startswith('_')):
                return
            m = ID_RE.match(v)
            if m and m.group(1) in self.kinds:
                yield key, v
        elif isinstance(v, dict):
            for k, x in v.items():
                yield from self._refs(x, k)
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from self._refs(x, key)

    def validate(self):
        probs = []
        codes: dict[tuple, str] = {}
        for i in sorted(self._raw):
            try:
                d = self._resolve(i)
            except DefsError as e:
                probs.extend(e.problems)
                continue
            if d.get('_abstract'):
                continue
            if d['kind'] == 'place' and 'code' not in d:
                probs.append(f'{i}: place 定义必须有 code（运行时钥匙）')
            if 'code' in d:
                ck = (d['kind'], d['code'])
                if ck in codes:
                    probs.append(f'{i}: code {d["code"]!r} 与 {codes[ck]} 重复')
                codes[ck] = i
            for key, ref in self._refs({k: v for k, v in d.items() if k not in ('id', 'kind', '_file', 'parent')}):
                if ref not in self._raw:
                    probs.append(f'{i}: 字段 {key} 引用了不存在的 {ref}')
        self.problems.extend(p for p in probs if p not in self.problems)
        return self.problems
