/**
 * [INPUT]: 依赖 store（turns / stream / pending / stage），typewriter.js 的 createTypewriter / paragraphs，contract.js 的 STAGES，读屏节点 live
 * [OUTPUT]: 对外提供 mountStory(el, store, live) → { skip }
 * [POS]: 叙事卷——跑团日志式向下生长：往事淡墨、当下浓墨；玩家落笔即先显影其举动与说书人此刻的进度（构思/推演）；
 *        新回合一到即立抬头，正文随流式增量边到边誊，终稿落定后与之对账；亲眼所见的世界变动作为"记"附于文末
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { STAGES } from '../contract.js';
import { createTypewriter, paragraphs } from '../typewriter.js';

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

function h(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function noted(tag, className, mark, text) {
  const node = h(tag, className);
  node.append(h('span', 'mark', mark), text);
  return node;
}

/** 回合抬头：时辰必记，日期与地点只在变化时记，免得满纸重复。 */
function stamp(turn, prev) {
  const parts = [];
  if (!prev || prev.time.year !== turn.time.year || prev.time.date !== turn.time.date) {
    parts.push(turn.time.year + turn.time.date);
  }
  parts.push(turn.time.hour);
  if (!prev || prev.scene.place !== turn.scene.place) parts.push(turn.scene.place);
  return parts.join(' · ');
}

function annals(article, turn) {
  const seen = turn.events.filter((e) => e.kind === 'witnessed');
  if (!seen.length) return;
  const list = h('ul', 'annals');
  seen.forEach((e) => list.append(noted('li', '', '记', e.text)));
  article.append(list);
}

export function mountStory(el, store, live) {
  let shown = 0;
  let pendingEl = null;
  let current = null; // 正在誊写的回合：{ turn, article, writer, consumed }

  function append(turn, prev) {
    pendingEl?.remove();
    pendingEl = null;
    el.querySelector('.turn.live')?.classList.replace('live', 'past');

    const article = h('article', 'turn live');
    if (turn.deed) article.append(noted('p', 'deed', '你', turn.deed.text));
    article.append(h('p', 'stamp', stamp(turn, prev)));
    const prose = h('div', 'prose');
    article.append(prose);
    el.append(article);

    if (!turn.fresh) {
      paragraphs(turn.narrative).forEach((p) => prose.append(h('p', '', p)));
      annals(article, turn);
      return;
    }
    const record = { turn, article, consumed: 0 };
    record.writer = createTypewriter(prose, {
      instant: reducedMotion.matches,
      onDone() {
        article.classList.remove('typing');
        annals(article, record.turn);
        live.textContent = record.turn.narrative; // 读屏在终稿落定后整段读出，不受逐字干扰
        if (current === record) current = null;
        queueMicrotask(() => store.typingDone());
      },
    });
    current = record;
    article.classList.add('typing');
    article.addEventListener('click', () => record.writer.skip());
    if (!turn.streaming) record.writer.end(turn.narrative); // 整段到达：一次交给打字机
  }

  /** 流式途中：把尚未誊过的增量交给打字机；终稿替换了抬头时，宣告完稿。 */
  function feed(s) {
    if (!current) return;
    if (typeof s.stream === 'string' && s.stream.length > current.consumed) {
      current.writer.push(s.stream.slice(current.consumed));
      current.consumed = s.stream.length;
    }
    const last = s.turns[s.turns.length - 1];
    if (last && last !== current.turn && last.turn === current.turn.turn) {
      current.turn = last;
      if (!last.streaming) current.writer.end(last.narrative);
    }
  }

  function syncPending(pending, stage) {
    if (pending && !pendingEl) {
      pendingEl = h('div', 'turn');
      const waiting = h('p', 'pending');
      const dots = h('span', 'dots');
      dots.append(h('i'), h('i'), h('i'));
      waiting.append(dots, h('span', 'pending-text'));
      pendingEl.append(noted('p', 'deed', '你', pending.text), waiting);
      el.append(pendingEl);
      pendingEl.scrollIntoView({ behavior: reducedMotion.matches ? 'auto' : 'smooth', block: 'center' });
    } else if (!pending && pendingEl) {
      pendingEl.remove();
      pendingEl = null;
    }
    if (pendingEl) pendingEl.querySelector('.pending-text').textContent = STAGES[stage] || STAGES.direct;
  }

  function render(s) {
    if (s.turns.length < shown) { // 另起一卷，或重新同步后卷子变短
      current?.writer.cancel();
      current = null;
      el.textContent = '';
      shown = 0;
      pendingEl = null;
    }
    while (shown < s.turns.length) {
      const i = shown++; // 先记账再排版：排版途中可能触发新一轮 render
      append(s.turns[i], s.turns[i - 1]);
    }
    feed(s);
    syncPending(s.pending, s.stage);
  }

  store.subscribe(render);
  render(store.get());
  return { skip: () => current?.writer.skip() };
}
