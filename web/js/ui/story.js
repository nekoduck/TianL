/**
 * [INPUT]: 依赖 store（turns / pending / typing），typewriter.js 的 typewrite()，读屏播报节点 live
 * [OUTPUT]: 对外提供 mountStory(el, store, live) → { skip }
 * [POS]: 叙事卷——跑团日志式向下生长：往事淡墨、当下浓墨；玩家落笔即先显影其举动与"研墨"之态；
 *        新回合交打字机誊写，亲眼所见的世界变动作为"记"附于文末
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { typewrite } from '../typewriter.js';

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

const paragraphs = (narrative) => narrative.split('\n').map((s) => s.trim()).filter(Boolean);

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

export function mountStory(el, store, live) {
  let shown = 0;
  let pendingEl = null;
  let writer = null;

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

    const seen = turn.events.filter((e) => e.kind === 'witnessed');
    const annals = () => {
      if (!seen.length) return;
      const list = h('ul', 'annals');
      seen.forEach((e) => list.append(noted('li', '', '记', e.text)));
      article.append(list);
    };

    if (!turn.fresh) {
      paragraphs(turn.narrative).forEach((p) => prose.append(h('p', '', p)));
      annals();
      return;
    }
    live.textContent = turn.narrative; // 读屏一次读完整段，不受逐字干扰
    const done = () => {
      writer = null;
      article.classList.remove('typing');
      annals();
      queueMicrotask(() => store.typingDone());
    };
    if (reducedMotion.matches) {
      paragraphs(turn.narrative).forEach((p) => prose.append(h('p', '', p)));
      done();
      return;
    }
    article.classList.add('typing');
    article.addEventListener('click', () => writer?.skip());
    writer = typewrite(prose, paragraphs(turn.narrative), { onDone: done });
  }

  function syncPending(pending) {
    if (pending && !pendingEl) {
      pendingEl = h('div', 'turn');
      const waiting = h('p', 'pending');
      const dots = h('span', 'dots');
      dots.append(h('i'), h('i'), h('i'));
      waiting.append(dots, h('span', '', '说书人研墨中'));
      pendingEl.append(noted('p', 'deed', '你', pending.text), waiting);
      el.append(pendingEl);
      pendingEl.scrollIntoView({ behavior: reducedMotion.matches ? 'auto' : 'smooth', block: 'center' });
    } else if (!pending && pendingEl) {
      pendingEl.remove();
      pendingEl = null;
    }
  }

  function render(s) {
    if (s.turns.length < shown) { // 另起一卷
      el.textContent = '';
      shown = 0;
      pendingEl = null;
    }
    while (shown < s.turns.length) {
      const i = shown++; // 先记账再排版：排版途中可能触发新一轮 render
      append(s.turns[i], s.turns[i - 1]);
    }
    syncPending(s.pending);
  }

  store.subscribe(render);
  render(store.get());
  return { skip: () => writer?.skip() };
}
