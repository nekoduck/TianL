/**
 * [INPUT]: 依赖 contract.js 的 VERSION / ServiceError；可选依赖 sessionStorage（刷新续读）
 * [OUTPUT]: 对外提供 createMock({ latency, flaky }) → Service { kind, connect, start, act }
 * [POS]: 模拟服务，与 api.js 同形、与 tianlong/protocol.py 同载荷——前端脱离后端独立开发时的说书人；
 *        剧本覆盖界面的每一种状态：伤势标签、随身器物、亲见旁注、延迟传闻、选项过期、网络失联
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { VERSION, ServiceError } from './contract.js';

const KEY = 'tianlong.mock.session';
const MAX_TEXT = 200;

// ============================================================
//  剧本：五回合一气呵成，之后进入回声段
// ============================================================
const SCENES = [
  {
    scene: { place: '剑湖宫·练武厅', region: '大理·无量山' },
    time: { year: '元祐六年', date: '二月初一', hour: '辰时' },
    narrative: '练武厅内剑气森森，东西二宗的弟子正斗到第四场。东宗龚光杰脚下一个踉跄，似要跌倒，西宗那姓褚的弟子挺剑急刺，不料龚光杰身形一拧，反手一剑，正削在他腕上，青钢剑当啷落地。\n满厅宾客正要喝彩，席间忽然有人「嗤」的一声笑了出来。笑的是个青衫书生，手里还捧着一盏冷茶，神色坦然，仿佛全不知自己闯了祸。\n左子穆脸色一沉。龚光杰收剑转身，一步一步朝那书生走去。',
    options: ['替那书生解围', '抬头看梁上嗑瓜子的少女', '趁乱悄悄退出大厅'],
    status: [{ text: '安然无恙', tone: 'plain' }, { text: '不会武功', tone: 'plain' }],
    events: [{ id: 1, kind: 'witnessed', date: '元祐六年二月初一', place: '剑湖宫·练武厅', text: '龚光杰刺伤褚师弟，东宗四赛三胜。' }],
  },
  {
    scene: { place: '剑湖宫·练武厅', region: '大理·无量山' },
    time: { year: '元祐六年', date: '二月初一', hour: '辰时一刻' },
    narrative: '你一步跨到书生身前，拱手道：「比剑已毕，何必与读书人计较？」\n龚光杰冷笑一声，竟不答话，左掌横推而来。你只觉胸口如被巨石撞中，踉跄退了三步，喉头一甜。那书生扶住你，连声道：「罪过罪过，此事全因小生而起。」\n梁上忽然落下一颗瓜子壳，不偏不倚打在龚光杰额头。一个少女的声音笑道：「欺负不会武功的人，羞也不羞？」',
    options: ['顺着少女的话讥讽龚光杰', '扶书生退到马五德身后', '强忍伤痛，还他一掌'],
    status: [{ text: '轻伤', tone: 'warn' }, { text: '不会武功', tone: 'plain' }, { text: '戒备', tone: 'plain' }],
    events: [{ id: 2, kind: 'witnessed', date: '元祐六年二月初一', place: '剑湖宫·练武厅', text: '段誉拒比武并讲佛理，龚光杰掌掴他。' }],
  },
  {
    scene: { place: '无量后山', region: '大理·无量山' },
    time: { year: '元祐六年', date: '二月初一', hour: '巳时二刻' },
    narrative: '厅中乱成一团时，你跟着那书生与少女从偏门溜了出来，一路往后山去。山径越走越窄，古木参天，藤萝垂地，回头已望不见剑湖宫的飞檐。\n少女自称钟灵，腰间布囊里不时探出一个小小的貂头。书生说他姓段，是从家里逃出来的，说到这里便讪讪地住了口。\n林中忽有人声。几个短衣汉子扛着药锄自坡下转出，衣襟上都绣着「神农」二字。',
    options: ['上前探问神农帮来意', '拉着二人躲进藤萝', '独自向崖边探路'],
    status: [{ text: '轻伤', tone: 'warn' }, { text: '不会武功', tone: 'plain' }, { text: '风尘仆仆', tone: 'plain' }],
    events: [
      { id: 3, kind: 'rumor', date: '元祐六年二月初一', place: '镇南王府', text: '镇南王府遣出数路人马，四处寻访离家出走的世子。' },
      { id: 4, kind: 'rumor', date: '元祐六年正月廿八', place: '无锡城', text: '丐帮诸长老近日频频聚议，城中乞丐往来如织，似有大事将起。' },
    ],
  },
  {
    scene: { place: '无量山·谷底', region: '大理·无量山' },
    time: { year: '元祐六年', date: '二月初一', hour: '午时' },
    narrative: '山风骤起，你脚下一块青石松动，整个人连同碎石直滑下去。耳边风声呼啸，你抓住崖缝里一株斜生的老松，枝干噼啪断折，一路将你送到谷底。\n不知过了多久，你在一片湿冷的苔藓上醒来，四肢百骸无一处不痛。抬头望去，峭壁如削，云雾在半山缭绕，上去是万万不能了。\n谷底有一泓碧水，水声淙淙。湖畔山壁上隐约有一道石缝，缝中透出幽幽的光。',
    options: ['循光走进石缝', '就地打坐调息', '沿湖寻找出路'],
    status: [{ text: '重伤', tone: 'warn' }, { text: '不会武功', tone: 'plain' }, { text: '跌坐', tone: 'plain' }],
    events: [],
  },
  {
    scene: { place: '琅嬛福地·玉像石室', region: '大理·无量山后山崖底' },
    time: { year: '元祐六年', date: '二月初一', hour: '未时三刻' },
    narrative: '石缝之后别有洞天。一间石室，四壁打磨得光可鉴人，正中立着一尊白玉雕成的宫装美女，眉目流转，竟似要开口说话。\n玉像足边有两个蒲团，前一个已朽得只剩薄薄一层。你跪下细看，蒲团里裹着一卷帛书，卷首写着四个古篆：北冥神功。\n你将帛书揣入怀中，心头怦怦乱跳。石室深处，还有一道向下的石级，不知通往何处。',
    options: ['展开帛书细读', '向玉像叩首', '沿石级向下'],
    status: [{ text: '重伤', tone: 'warn' }, { text: '不会武功', tone: 'plain' }, { text: '持有北冥神功卷轴', tone: 'plain' }],
    events: [{ id: 5, kind: 'rumor', date: '元祐六年二月初一', place: '无量山', text: '无量剑东宗弟子容子矩毒发身亡，左子穆疑是神农帮所为。' }],
  },
];

const ECHO_HOURS = ['申时', '申时二刻', '申时五刻', '酉时', '酉时三刻', '戌时', '戌时四刻', '亥时'];

function echo(n, deed) {
  const last = SCENES[SCENES.length - 1];
  return {
    scene: last.scene,
    time: { year: '元祐六年', date: '二月初一', hour: ECHO_HOURS[(n - SCENES.length - 1) % ECHO_HOURS.length] },
    narrative: `你${deed.text}。\n石室中寂然无声，只有湖水在远处轻轻拍岸。灯影摇曳，玉像依旧含笑不语，仿佛早已料到你会如此。\n（模拟说书人的剧本已尽，此后只作回声。）`,
    options: ['再看一眼玉像', '静坐片刻', '寻路离开'],
    status: last.status,
    events: [],
  };
}

function compose(n, deed) {
  const s = n <= SCENES.length ? SCENES[n - 1] : echo(n, deed);
  return {
    protocol: VERSION,
    turn: n,
    deed,
    scene: { ...s.scene },
    time: { ...s.time, label: `${s.time.year}${s.time.date} ${s.time.hour}` },
    narrative: s.narrative,
    options: s.options.map((label, i) => ({ id: `t${n}-${i + 1}`, label })),
    status: s.status.map((t) => ({ ...t })),
    events: s.events.map((e) => ({ ...e })),
  };
}

// ============================================================
//  服务：与 api.js 同形
// ============================================================
export function createMock({ latency = [700, 1600], flaky = false } = {}) {
  let session = restore();
  const wait = () => new Promise((r) => setTimeout(r, latency[0] + Math.random() * (latency[1] - latency[0])));
  const payload = () => ({ protocol: VERSION, session: { id: session.id, hero: session.hero }, transcript: session.transcript });

  function persist() {
    try { sessionStorage.setItem(KEY, JSON.stringify(session)); } catch { /* 隐私模式：不续读即可 */ }
  }

  return {
    kind: 'mock',
    async connect() {
      await wait();
      return session ? payload() : null;
    },
    async start(name) {
      await wait();
      const hero = (name || '').trim();
      if (hero.length > 12) throw new ServiceError('bad_request', 400, '名号请勿超过12字');
      session = { id: Math.random().toString(16).slice(2, 14), hero: hero || '无名', transcript: [compose(1, null)] };
      persist();
      return payload();
    },
    async act(action) {
      await wait();
      if (flaky && Math.random() < 0.3) throw new ServiceError('network');
      if (!session) throw new ServiceError('no_session', 404);
      const current = session.transcript[session.transcript.length - 1];
      const content = String(action?.action_content ?? '').trim();
      let text;
      if (action?.action_type === 'selection') {
        text = current.options.find((o) => o.id === content)?.label;
        if (!text) throw new ServiceError('stale_option', 409);
      } else if (action?.action_type === 'free_text') {
        if (!content) throw new ServiceError('bad_request', 400, '请写下你想做的事');
        if (content.length > MAX_TEXT) throw new ServiceError('bad_request', 400, `一次行动请勿超过${MAX_TEXT}字`);
        text = content;
      } else {
        throw new ServiceError('bad_request', 400);
      }
      const turn = compose(session.transcript.length + 1, { action_type: action.action_type, action_content: content, text });
      session.transcript.push(turn);
      persist();
      return turn;
    },
  };
}

function restore() {
  try { return JSON.parse(sessionStorage.getItem(KEY)) || null; } catch { return null; }
}
