"""第 1 阶段：提及普查与缺名检测（tools/canon_names.py 的实现）。

  mentions                   用实体登记（census 目录或 entities.jsonl）做别名最长匹配：
                             out/canon/mentions.tsv（实体、回、段、起、止；本地）与 data/canon/mention_counts.tsv（实体、回、次数；入库）
  verify CENSUS_FILE         逐实体、逐别名报告全书命中次数与首见回；标出 0 命中、被更长名字吞掉、单字别名
  candidates --type T        启发式找“全书高频但未登记”的名字（人物看说话归属句式；地点/组织/武学/物看后缀）

所有输出只含名字、编号、回/段编号与计数，不打印原文段落。
称呼歧义（一个称呼指向不止一个同类实体）：普查阶段不猜，计入伪实体 “ambiguous:<称呼>”，由第 2 阶段上下文消歧。
"""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from collections import Counter
from pathlib import Path

from . import merge as M
from . import schema as S
from . import text as T
from . import textcli

_CJK = re.compile(r'[一-鿿㐀-䶿]+')


# ----------------------------------------------------------------------------------------------------------------------
# 登记表
# ----------------------------------------------------------------------------------------------------------------------
def load_registry_records(canon_dir=None, explicit=None):
    """-> [(来源, 登记行)]。explicit（文件/目录）优先；否则 census 目录；否则 entities.jsonl；都没有返回 []。"""
    if explicit:
        return M.read_census(explicit)[0]
    base = Path(canon_dir or S.CANON_DIR)
    if S.list_jsonl_files(base / 'census'):
        return M.read_census(base / 'census')[0]
    f = base / 'entities.jsonl'
    return M.read_census(f)[0] if f.is_file() else []


def load_registry(canon_dir=None, explicit=None):
    """-> 合并后的实体行列表（冲突的行被丢弃，不报错；报错是 canon_merge 的事）。"""
    return M.merge_rows(load_registry_records(canon_dir, explicit)).entities


def attribute(m):
    """一条提及归到哪些“实体”：唯一候选/已消歧 -> 该实体；同名孪生组 -> 各成员；其余歧义 -> ambiguous:<称呼>。"""
    if m.entity:
        return [m.entity]
    if m.twin:
        return list(m.cands)
    return [f'ambiguous:{m.surface}']


# ----------------------------------------------------------------------------------------------------------------------
# mentions
# ----------------------------------------------------------------------------------------------------------------------
def run_mentions(store, rows):
    """-> (提及列表, 称呼索引, 取回校验错误列表)。"""
    index = T.SurfaceIndex(rows)
    mentions = T.census_mentions(store, index)
    return mentions, index, T.verify_mentions(store, mentions)


def count_rows(mentions):
    """-> [(实体, 回, 次数)]，按实体、回排序。"""
    c = Counter()
    for m in mentions:
        for e in attribute(m):
            c[(e, m.ch)] += 1
    return sorted(((e, ch, n) for (e, ch), n in c.items()), key=lambda r: (r[0], r[1]))


def write_tsv(path, header, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\t'.join(header) + '\n')
        for r in rows:
            f.write('\t'.join(str(x) for x in r) + '\n')


def cmd_mentions(a, out):
    st = textcli.open_store(a)
    rows = load_registry(a.canon_dir, a.entities)
    if not rows:
        print('没有实体登记（data/canon/census/*.jsonl 或 entities.jsonl；也可 --entities 指定）：先让普查代理产出登记行。', file=out)
        return 2
    mentions, index, errs = run_mentions(st, rows)
    mrows = sorted(((e, m.ch, m.para, m.start, m.end) for m in mentions for e in attribute(m)),
                   key=lambda r: (r[1], r[2], r[3], r[0]))
    crows = count_rows(mentions)
    write_tsv(Path(a.out) / 'mentions.tsv', ('entity', 'ch', 'para', 'start', 'end'), mrows)
    write_tsv(a.counts, ('entity', 'ch', 'count'), crows)
    tot = Counter()
    for e, _, n in crows:
        tot[e] += n
    named = {e for e in tot if not e.startswith('ambiguous:')}
    amb = sum(n for e, n in tot.items() if e.startswith('ambiguous:'))
    never = sorted(r['id'] for r in rows if r['id'] not in tot)
    print(f'登记 {len(rows)} 个实体，称呼 {len(index.cands)} 个（单字称呼 {len(index.skipped)} 个不参与匹配）', file=out)
    print(f'提及 {len(mentions)} 条，涉及 {len(named)} 个实体；歧义称呼提及 {amb} 条（计入 ambiguous:<称呼>）；'
          f'字位取回校验错误 {len(errs)}', file=out)
    print(f'-> {Path(a.out) / "mentions.tsv"}（本地）、{a.counts}（入库）', file=out)
    for e in errs[:10]:
        print(f'  错误：{e}', file=out)
    top = sorted(((n, e) for e, n in tot.items()), key=lambda x: (-x[0], x[1]))[:10]
    print('提及最多的 10 项：' + '；'.join(f'{e} {n}' for n, e in top), file=out)
    if never:
        print(f'全书 0 提及的实体 {len(never)} 个：' + '、'.join(never[:20]) + (' ……' if len(never) > 20 else ''), file=out)
    return 1 if errs else 0


# ----------------------------------------------------------------------------------------------------------------------
# verify
# ----------------------------------------------------------------------------------------------------------------------
def surface_stats(store, index, surfaces):
    """逐称呼统计：{称呼: {'raw': 全书子串出现数, 'eff': 最长匹配命中数, 'first': 首见回|None, 'swallow': Counter}}。
    raw 是子串出现次数（不重叠）；eff 是最长匹配普查里它自己被匹配的次数；被更长称呼盖住的出现记在 swallow。"""
    flat = store.flat_index()[0]
    spans = {}                                  # (回, 段) -> [(起, 止, 称呼)]
    eff = Counter()
    for p in store.iter_paragraphs():
        ms = index.scan(p.text)
        if ms:
            spans[(p.ch, p.idx)] = ms
            for _, _, sf in ms:
                eff[sf] += 1
    res = {}
    for sf in surfaces:
        raw = flat.count(sf) if sf else 0
        first, swallow = None, Counter()
        if raw:
            pos = flat.find(sf)
            first = store.locate(pos)[0]
            if len(sf) >= index.min_len and eff[sf] < raw:
                while pos != -1:
                    ch, para, off = store.locate(pos)
                    ms = spans.get((ch, para), ())
                    if not any(i == off and s == sf for i, _, s in ms):
                        cover = next((s for i, j, s in ms if i <= off < j), None)
                        swallow[cover or '(未覆盖)'] += 1
                    pos = flat.find(sf, pos + len(sf))
        res[sf] = {'raw': raw, 'eff': eff[sf], 'first': first, 'swallow': swallow}
    return res


def cmd_verify(a, out):
    st = textcli.open_store(a)
    if not Path(a.census_file).exists():
        print(f'错误：路径不存在：{a.census_file}', file=out)
        return 2
    recs = M.read_census(a.census_file)[0]
    mine = M.merge_rows(recs)
    scope = {r['id']: r for r in mine.entities}
    ctx = [] if a.only else load_registry_records(a.canon_dir, a.registry)
    allrows = M.merge_rows(recs + ctx).entities
    if not scope:
        print('登记文件里没有合格的登记行。', file=out)
        for c in mine.conflicts[:10]:
            print('  ' + c.line(), file=out)
        return 1
    index = T.SurfaceIndex(allrows)
    surfaces = sorted({sf for r in scope.values() for sf in [r['name']] + list(r['aliases'])})
    stats = surface_stats(st, index, surfaces)
    zero_names, zero_aliases, swallowed, single, shared = [], [], [], [], []
    n_alias = 0
    for eid in sorted(scope):
        r = scope[eid]
        s0 = stats[r['name']]
        flag = ' ← 规范名 0 命中' if s0['raw'] == 0 else ''
        if s0['raw'] == 0:
            zero_names.append((eid, r['name']))
        if not a.quiet or flag:
            print(f'{eid} {r["name"]}：全书 {s0["raw"]} 处，首见 {_ch(s0["first"])}{flag}', file=out)
        for sf in r['aliases']:
            n_alias += 1
            s = stats[sf]
            marks = []
            if len(sf) < index.min_len:
                marks.append('单字别名（不参与匹配，书里也不该收）')
                single.append((eid, sf))
            if s['raw'] == 0:
                marks.append('0 命中')
                zero_aliases.append((eid, sf))
            elif len(sf) >= index.min_len and s['eff'] == 0:
                top = s['swallow'].most_common(1)
                marks.append('被更长名字吞掉' + (f'（主要被“{top[0][0]}”）' if top else ''))
                swallowed.append((eid, sf, top[0][0] if top else ''))
            elif len(sf) >= index.min_len and s['eff'] < s['raw']:
                top = s['swallow'].most_common(1)
                marks.append(f'部分被吞 {s["raw"] - s["eff"]}/{s["raw"]}' + (f'（主要被“{top[0][0]}”）' if top else ''))
            if len(index.cands.get(sf, ())) > 1:
                shared.append((eid, sf))
                marks.append(f'称呼同时指 {len(index.cands[sf])} 个实体')
            if not a.quiet or marks:
                print(f'    别名 {sf}：全书 {s["raw"]} 处，首见 {_ch(s["first"])}' + (' ← ' + '；'.join(marks) if marks else ''),
                      file=out)
    print('== 汇总', file=out)
    print(f'实体 {len(scope)} 个，别名 {n_alias} 个；登记合并冲突 {len(mine.conflicts)} 条', file=out)
    print(f'规范名 0 命中 {len(zero_names)}：' + '、'.join(f'{n}({e})' for e, n in zero_names[:30]), file=out)
    print(f'别名 0 命中 {len(zero_aliases)}：' + '、'.join(f'{sf}({e.split(":")[-1]})' for e, sf in zero_aliases[:30]), file=out)
    print(f'别名被更长名字吞掉 {len(swallowed)}：' + '、'.join(f'{sf}←{by}' for _, sf, by in swallowed[:30]), file=out)
    print(f'单字别名 {len(single)}：' + '、'.join(f'{sf}({e.split(":")[-1]})' for e, sf in single[:30]), file=out)
    n_err = len(zero_names) + len(zero_aliases) + len(mine.conflicts)
    n_warn = len(swallowed) + len(single)
    print(f'错误 {n_err}（0 命中的名字/别名、登记冲突），警告 {n_warn}（被吞、单字）'
          f' -> ' + ('通过' if n_err == 0 and (not a.strict or n_warn == 0) else '有问题，见上'), file=out)
    return 0 if n_err == 0 and (not a.strict or n_warn == 0) else 1


def _ch(n):
    return '—' if n is None else f'第 {n} 回'


# ----------------------------------------------------------------------------------------------------------------------
# candidates
# ----------------------------------------------------------------------------------------------------------------------
_STEMS = sorted(['冷笑', '低声', '大声', '高声', '沉声', '厉声', '朗声', '柔声', '轻声', '微笑', '苦笑', '大笑', '淡淡', '冷冷',
                 '恨恨', '缓缓', '悠悠', '喃喃', '长叹', '叹息', '接着', '怒喝', '笑骂', '低语', '说', '笑', '叹', '喝', '问',
                 '答', '叫', '怒', '骂', '哼', '喊', '嚷', '呼', '吼', '劝', '斥', '接', '续', '插', '又', '便', '却', '再',
                 '忙', '的', '地', '着', '得', '不禁', '终于', '忽然', '突然', '慢慢', '连忙', '随即', '于是', '立即',
                 '点了点头', '摇了摇头', '叹了口气', '叹了一口气', '微微一笑', '哈哈一笑', '哈哈大笑', '嘿嘿一笑', '一笑',
                 '点头', '摇头', '转身', '回头', '转头', '抬头', '低头', '皱眉', '沉吟', '心下', '心中', '心', '暗', '齐声',
                 '纷纷', '同声', '忍不住', '一声', '躬身', '合十', '拍手', '拱手', '抱拳', '颤声', '大惊', '恭恭敬敬', '欠身',
                 '点点头', '摇摇头', '行礼', '作揖', '一揖', '叹气', '冷冷的', '怒声', '尖声', '高叫', '大叫', '大喝', '断喝'],
                key=lambda s: (-len(s), s))
_BOUNDARY = set('的了得着是在和与及把被将向对让便就又也却才那这只听见说问答道叫笑')
_PERSON_STOP = {'老者', '少年', '大汉', '汉子', '老妇', '妇人', '青年', '和尚', '僧人', '道人', '女子', '女郎', '少女', '姑娘',
                '中年', '老人', '书生', '老头', '少妇', '那人', '此人', '来人', '对方', '旁人', '众人', '群雄', '大家', '二人',
                '两人', '三人', '诸人', '其他', '自己', '他们', '我们', '你们', '咱们', '师父', '师兄', '师弟', '师姊', '师妹',
                '公子', '小姐', '夫人', '相公', '爷爷', '奶奶', '妈妈', '姑姑', '爹爹', '官人', '首领', '主人', '客人', '掌柜',
                '掌门', '帮主', '长老', '老爷', '太太', '娘子', '那汉', '大师', '前辈', '晚辈', '大王', '陛下', '皇上', '殿下',
                '女孩', '男子', '丫鬟', '仆人', '老僧', '老道', '头陀', '少侠', '壮士', '先生', '兄弟', '姊姊', '妹妹', '哥哥',
                '弟弟', '父亲', '母亲', '儿子', '女儿', '王爷', '将军', '士兵', '官兵', '船夫', '老板', '伙计', '大夫', '郎中',
                '不知', '心中', '当即', '当下', '哈哈', '口气', '轻轻', '同时', '转身', '口中', '忍不住', '纷纷', '齐声',
                '转头', '回头', '声音', '弟子', '女童', '婆婆', '方丈', '神山', '室里', '以彼之', '矮子', '胖子', '舵主', '酒保', '宫女'}
_NOT_SPEECH_BEFORE_DAO = set('知难报味街公')       # 知道/难道/报道/味道/街道/公道 不是说话归属
_PERSON_BAD_END = set('人者汉妇')
_FINALS = {
    'place': '山城寺庄谷岛宫府关洞江河湖林村镇州国峰岭崖坡庙观院殿堂阁楼桥渡堡寨洲海泽原亭塔',
    'org': '帮派宗教会门盟寨堡庄府宫阁馆院寺社营军团堂',
    'martial': '掌拳剑功指法刀腿爪步',
    'item': '丹散膏丸令牌符珠印图谱帖笺琴镜匣盒鼎环簪佩玉刀剑枪鞭杖棍锤斧针钩弓箭囊匙瓶壶酒药经书',
}
_FUNC_FIRST = set('是也个之见的了在和与及把被将向对让')
_STEM_BAD = set('一二三四五六七八九十百千万两半这那每各某其另的了在又只便就才却还再很太最没他她我你咱它与和及把被将向对让'
                '上下前后左右中内外出入进来去到')
_STEM_BAD_NUM_OK = set('上下前后左右中内外出入进来去到的了在又只便就才却还再很太最没他她我你咱它与和及把被将向对让这那每各某其另')
_GENERIC = {
    'place': {'山山', '大山', '小山', '高山', '深山', '荒山', '满山', '全城', '大城', '小城', '城城', '江湖', '天下', '本国', '外国',
              '全国', '中国', '各国', '一国', '大国', '小国', '这国', '该国', '满城', '全村', '一座', '大海', '水泊'},
    'org': {'不会', '理会', '也不会', '决不会', '怎会', '待会', '竟会', '过了一会', '定会', '不理会', '学会', '相会', '聚会',
            '误会', '也会', '领教', '请教', '成一团', '团团', '祖宗', '面门', '旁门', '法门', '怎么会', '马副帮', '一会', '开会',
            '大帮', '小帮', '本帮', '帮会', '帮派', '门派', '宗派', '教派', '本派', '本门', '各派', '各门', '各帮', '本教', '各会',
            '大会', '小会', '集会', '教会', '宴会', '开会', '本会', '大军', '大营', '军营', '本宫', '本寺', '大寺', '大堂', '厅堂',
            '大殿', '本庄', '本府', '王府', '官府', '宫门', '大门', '同门', '师门', '掌门', '山门', '寺门', '庙门', '各寺', '诸寺'},
    'martial': {'手指', '脚步', '无法', '几步', '快步', '双掌', '设法', '执法', '之法', '拇指', '食指', '伸指', '挥掌', '派掌',
                '伸掌', '小指', '大拇指', '指指', '停步', '双腿', '运功', '传功', '化功', '没法', '不会武功', '人武功', '派武功',
                '门功', '大功', '抱拳', '拱拳', '握拳', '出拳', '挥拳', '一拳', '武功', '内功', '轻功', '功夫', '用功', '成功', '剑法', '刀法', '掌法', '拳法', '指法', '招法', '身法', '步法',
                '心法', '方法', '办法', '想法', '说法', '手法', '做法', '用法', '章法', '练功', '神功', '大法', '本事', '手掌',
                '巴掌', '耳光', '兵刀', '宝剑', '长剑', '短剑', '佩剑', '单刀', '钢刀', '大刀', '小刀', '腿法', '少林', '功力',
                '功劳', '功德', '内力', '外功', '硬功', '气功', '武法', '妙法', '佛法', '法门', '剑术', '刀术'},
    'item': {'宝剑', '长剑', '短剑', '佩剑', '单刀', '钢刀', '大刀', '小刀', '宝刀', '毒药', '药酒', '美酒', '酒药', '饮酒', '喝酒',
             '好酒', '烈酒', '药物', '解药', '毒酒', '图书', '书信', '读书', '经书', '佛经', '诗书', '文书', '圣贤书', '战书', '请帖',
             '令牌', '金牌', '铁牌', '腰牌', '符咒', '图谱', '地图', '画图', '拳谱', '剑谱', '刀谱', '谱', '琴弦', '宝玉', '白玉', '美玉'},
}


def _build_cover(store, index):
    """已登记称呼在平铺文本里的覆盖区间：(起点数组, 终点数组)，已按起点排序。"""
    flat, starts, keys = store.flat_index()
    cs, ce = [], []
    for pi, (ch, para) in enumerate(keys):
        p = store.chapters[ch].paragraphs[para - 1]
        for i, j, _ in index.scan(p.text):
            cs.append(starts[pi] + i)
            ce.append(starts[pi] + j)
    return cs, ce


def _covered(cs, ce, pos, ln):
    k = bisect.bisect_right(cs, pos + ln - 1) - 1
    return k >= 0 and ce[k] > pos


def _left_maximal(counter, min_ratio=0.6):
    """返回满足“没有左扩展串的次数 >= min_ratio × 本串次数”的串集合（左扩展 = 前面再加一个字）。"""
    ext = {}
    for ng, n in counter.items():
        if len(ng) >= 3:
            par = ng[1:]
            if n > ext.get(par, 0):
                ext[par] = n
    return {ng for ng, n in counter.items() if ext.get(ng, 0) < min_ratio * n}


def person_candidates(store):
    """说话归属句式：“X(…)道：/，”。返回 {候选: {'pat': 句式次数, 'ex': 首个示例 (回, 段)}}（尚未过滤已登记、未设下限）。"""
    cnt, ex = Counter(), {}
    for p in store.iter_paragraphs():
        t = p.text
        k = t.find('道')
        while k != -1:
            if k + 1 < len(t) and t[k + 1] in '：，' and k > 0 and t[k - 1] not in _NOT_SPEECH_BEFORE_DAO:
                run = t[max(0, k - 14):k]
                m = list(_CJK.finditer(run))
                run = m[-1].group(0) if m and m[-1].end() == len(run) else ''
                changed = True
                while run and changed:
                    changed = False
                    for st in _STEMS:
                        if run.endswith(st):
                            run = run[:-len(st)]
                            changed = True
                            break
                cut = max((i for i, c in enumerate(run) if c in _BOUNDARY), default=-1)
                run = run[cut + 1:]
                for ln in range(2, min(4, len(run)) + 1):
                    ng = run[-ln:]
                    cnt[ng] += 1
                    ex.setdefault(ng, (p.ch, p.idx))
            k = t.find('道', k + 1)
    keep = _left_maximal(cnt)
    return {ng: {'pat': n, 'ex': ex[ng]} for ng, n in cnt.items()
            if ng in keep and ng not in _PERSON_STOP and ng[-1] not in _PERSON_BAD_END and ng[0] not in _STEM_BAD}


def suffix_candidates(store, typ):
    """按类型后缀找候选：以该类后缀字结尾的 2–7 字串。返回 {候选: {'pat': 次数, 'ex': 首个示例}}。"""
    finals = set(_FINALS[typ])
    cnt, ex, right = Counter(), {}, {}
    for p in store.iter_paragraphs():
        for m in _CJK.finditer(p.text):
            run = m.group(0)
            for e, c in enumerate(run, 1):
                if c in finals and e >= 2:
                    for s in range(max(0, e - 7), e - 1):
                        ng = run[s:e]
                        cnt[ng] += 1
                        right.setdefault(ng, Counter())[run[e] if e < len(run) else ''] += 1
                        ex.setdefault(ng, (p.ch, p.idx))
    keep = _left_maximal(cnt)
    bad = _STEM_BAD if typ != 'martial' else _STEM_BAD_NUM_OK
    out = {}
    for ng, n in cnt.items():
        if ng not in keep or ng in _GENERIC[typ] or ng[0] in _FUNC_FIRST:
            continue
        rc = right.get(ng)
        if rc:
            ch1, n1 = rc.most_common(1)[0]
            if ch1 and n1 >= 0.6 * n:               # 右边几乎总跟同一个字（如“乔帮|主”“丐帮帮|主”）：不是完整的名字
                continue
        stem = ng[:-1]
        if all(c in _STEM_BAD for c in stem) or ng[0] in bad or stem[-1] in '的了':
            continue
        out[ng] = {'pat': n, 'ex': ex[ng]}
    return out


def find_candidates(store, index, typ, min_hits=10, min_pat=3, min_ratio=0.03):
    """-> [(候选, 未登记处命中数, 句式/后缀次数, 首见回, 示例段编号)]，按命中降序。
    已登记（名或别名，含被登记称呼覆盖的出现）不再计入：命中数只数没被登记称呼盖住的出现。
    人物另要求 句式次数 / 全书出现数 >= min_ratio（滤掉“点头”“当即”这类副词动词）。"""
    cand = person_candidates(store) if typ == 'person' else suffix_candidates(store, typ)
    cs, ce = _build_cover(store, index)
    flat = store.flat_index()[0]
    reg = set(index.cands)
    rows = []
    for ng, info in cand.items():
        if ng in reg or info['pat'] < min_pat:
            continue
        hits, first, pos = 0, None, flat.find(ng)
        ex = info['ex']
        while pos != -1:
            if not _covered(cs, ce, pos, len(ng)):
                hits += 1
                if first is None:
                    first = store.locate(pos)
            pos = flat.find(ng, pos + len(ng))
        if typ == 'person' and info['pat'] < min_ratio * max(1, flat.count(ng)):
            continue
        if hits >= min_hits:
            rows.append((ng, hits, info['pat'], first[0], f'c{ex[0]}p{ex[1]}'))
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows


def cmd_candidates(a, out):
    st = textcli.open_store(a)
    rows = load_registry(a.canon_dir, a.entities)
    index = T.SurfaceIndex(rows)
    res = find_candidates(st, index, a.type, a.min)
    top = res if not a.top else res[:a.top]
    kind = {'person': '人物（说话归属句式）', 'place': '地点（后缀）', 'org': '组织（后缀）', 'martial': '武学（后缀）',
            'item': '物（后缀）'}[a.type]
    print(f'类型 {kind}：登记 {len(rows)} 个实体；全书高频但未登记的候选 {len(res)} 个（命中 >= {a.min}），'
          f'列出前 {len(top)} 个。命中 = 没被已登记称呼盖住的出现数；示例段只给编号，用 show/export 查看。', file=out)
    print(f'{"候选":<10}{"命中":>7}{"句式":>7}{"首见回":>8}  示例段', file=out)
    for ng, hits, pat, first, ex in top:
        print(f'{textcli._pad(ng, 10)}{hits:>7}{pat:>7}{first:>8}  {ex}', file=out)
    return 0


# ----------------------------------------------------------------------------------------------------------------------
def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='canon_names', description='第 1 阶段：提及普查与缺名检测（docs/CANON_SCHEMA.md 第 14 节）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('mentions', help='别名最长匹配 -> mentions.tsv 与 mention_counts.tsv')
    textcli.add_source_args(sp)
    sp.add_argument('--entities', help='登记表（普查文件/目录或 entities.jsonl）；缺省 data/canon/census，其次 entities.jsonl')
    sp.add_argument('--out', default=str(S.REPO_ROOT / 'out' / 'canon'), help='本地输出目录（mentions.tsv；被 .gitignore 忽略）')
    sp.add_argument('--counts', default=str(S.CANON_DIR / 'mention_counts.tsv'), help='入库的汇总（实体、回、次数）')
    sp.set_defaults(fn=cmd_mentions)

    sp = sub.add_parser('verify', help='逐实体逐别名报告全书命中与首见回')
    textcli.add_source_args(sp)
    sp.add_argument('census_file', metavar='CENSUS_FILE', help='普查登记文件（或目录）')
    sp.add_argument('--registry', help='用来判断“被吞”的整体登记表（缺省 data/canon/census）')
    sp.add_argument('--only', action='store_true', help='只用该文件自己的实体判断“被吞”')
    sp.add_argument('--strict', action='store_true', help='被吞与单字别名也算失败')
    sp.add_argument('--quiet', action='store_true', help='只打印有问题的行与汇总')
    sp.set_defaults(fn=cmd_verify)

    sp = sub.add_parser('candidates', help='找全书高频但未登记的名字')
    textcli.add_source_args(sp)
    sp.add_argument('--type', required=True, choices=['person', 'place', 'org', 'martial', 'item'])
    sp.add_argument('--min', type=int, default=10, help='至少命中多少次（默认 10）')
    sp.add_argument('--top', type=int, default=80, help='最多列出多少个（0 = 全部）')
    sp.add_argument('--entities', help='登记表（缺省 data/canon/census，其次 entities.jsonl）')
    sp.set_defaults(fn=cmd_candidates)

    a = ap.parse_args(argv)
    try:
        return a.fn(a, out)
    except BrokenPipeError:
        return 0
    except FileNotFoundError as ex:
        print(f'错误：{ex}', file=out)
        return 2
    except T.TextFormatError as ex:
        print(f'错误：原文版面不符：{ex}', file=out)
        return 2


if __name__ == '__main__':
    sys.exit(main())
