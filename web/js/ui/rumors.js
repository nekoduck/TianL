/**
 * [INPUT]: 依赖 store（rumors / notice），cn.js 的 cn()
 * [OUTPUT]: 对外提供 mountRumors({ button, count, ticker, veil }, store) → { open, close, isOpen }
 * [POS]: 江湖传闻——延迟抵达的世界变动。到达时只在页顶浮出一行小笺（誊写完毕才浮出，不打断阅读），
 *        页边留一个朱点计数；玩家查看时展开竖排红格信笺，新到者以朱字"新"标出，展信即视为已读
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { cn } from '../cn.js';

const TICKER_STAY = 6500;
const FADE = 650;

export function mountRumors({ button, count, ticker, veil }, store) {
  const body = veil.querySelector('.letter-body');
  const closer = veil.querySelector('.letter-close');
  let seen = 0;
  let hideTimer = 0;
  let returnFocus = null;

  function flash(n) {
    ticker.textContent = `江湖传闻 · 新至${cn(n)}则`;
    ticker.hidden = false;
    requestAnimationFrame(() => ticker.classList.add('show'));
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hideTicker, TICKER_STAY);
  }

  function hideTicker() {
    clearTimeout(hideTimer);
    ticker.classList.remove('show');
    setTimeout(() => { if (!ticker.classList.contains('show')) ticker.hidden = true; }, FADE);
  }

  /** 竖排自右而左，新者在右——DOM 中最新的排在最前。 */
  function paint(rumors) {
    body.textContent = '';
    if (!rumors.length) {
      const empty = document.createElement('p');
      empty.className = 'letter-empty';
      empty.textContent = '江湖寂静，尚无传闻。';
      body.append(empty);
      return;
    }
    [...rumors].reverse().forEach((r) => {
      const entry = document.createElement('div');
      entry.className = r.unread ? 'rumor unread' : 'rumor';
      const meta = document.createElement('p');
      meta.className = 'rumor-meta';
      meta.textContent = `${r.date}　${r.place}`;
      const text = document.createElement('p');
      text.className = 'rumor-text';
      text.textContent = r.text;
      entry.append(meta, text);
      body.append(entry);
    });
  }

  function open() {
    returnFocus = document.activeElement;
    paint(store.get().rumors);
    hideTicker();
    veil.hidden = false;
    requestAnimationFrame(() => veil.classList.add('open'));
    closer.focus();
    store.readRumors(); // 先以未读之态绘出，再记为已读：这一眼看得见哪些是新的
  }

  function close() {
    veil.classList.remove('open');
    setTimeout(() => { veil.hidden = true; }, 450);
    returnFocus?.focus?.();
  }

  function render(s) {
    const unread = s.rumors.filter((r) => r.unread).length;
    count.hidden = !unread;
    count.textContent = unread ? cn(unread) : '';
    button.setAttribute('aria-label', unread ? `江湖传闻，${cn(unread)}则未读` : '江湖传闻');
    if (s.notice && s.notice.seq !== seen) {
      seen = s.notice.seq;
      flash(s.notice.count);
    }
  }

  button.addEventListener('click', open);
  ticker.addEventListener('click', open);
  closer.addEventListener('click', close);
  veil.addEventListener('click', (e) => { if (e.target === veil) close(); });

  store.subscribe(render);
  render(store.get());
  return { open, close, isOpen: () => !veil.hidden };
}
