/**
 * [INPUT]: 依赖浏览器 requestAnimationFrame 与 ink.css 的 .ink / .ink.on（墨迹晕开）
 * [OUTPUT]: 对外提供 createTypewriter(container, { onDone, instant }) → { push, end, skip, cancel }、paragraphs()
 * [POS]: 打字机——正文边到边誊：push 收字、按节奏逐字显影，标点处停顿如人换气；积压多了自动加快，空等之后不追赶；
 *        end 宣告终稿并与之对账；可略过；随誊写跟随视线（玩家自行滚动即放手）；誊毕把逐字 span 收回为纯文本
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

const PAUSE = { '，': 90, '、': 70, '；': 130, '：': 110, '。': 240, '！': 240, '？': 240, '…': 150, '」': 50, '”': 50 };
const PARAGRAPH_PAUSE = 280;
const SETTLE = 700; // 最后一字显影所需，与 .ink 的过渡时长相合

/** 正文分段：与流式途中的切分规则一致（按换行分段、段首段尾去空白、空段不计），收墨时版面才不会跳。 */
export const paragraphs = (text) => text.split('\n').map((s) => s.trim()).filter(Boolean);

/** 积压越多，落笔越快：誊写永远跟得上说书人。 */
const pace = (backlog) => (backlog > 240 ? 8 : backlog > 120 ? 14 : backlog > 40 ? 20 : 26);

export function createTypewriter(container, { onDone, instant = false } = {}) {
  const spans = [];
  const times = [];
  let shown = 0;
  let received = '';
  let paragraph = null;
  let cursor = performance.now();
  let raf = 0;
  let ended = false;
  let finished = false;
  let replacement = null;
  let follow = true;

  const release = () => { follow = false; };
  addEventListener('wheel', release, { passive: true });
  addEventListener('touchmove', release, { passive: true });

  function push(text) {
    if (finished || !text) return;
    received += text;
    cursor = Math.max(cursor, performance.now()); // 空等之后从此刻起按节奏走，不一口气追赶
    for (const ch of text) {
      if (ch === '\n') {
        if (paragraph) cursor += PARAGRAPH_PAUSE;
        paragraph = null;
        continue;
      }
      if (!paragraph && /\s/.test(ch)) continue; // 段首空白交给 text-indent
      if (!paragraph) {
        paragraph = document.createElement('p');
        container.append(paragraph);
      }
      const span = document.createElement('span');
      span.className = 'ink';
      span.textContent = ch;
      paragraph.append(span);
      spans.push(span);
      times.push(instant ? 0 : cursor);
      cursor += pace(spans.length - shown) + (PAUSE[ch] || 0);
    }
    wake();
  }

  function wake() {
    if (!raf && !finished) raf = requestAnimationFrame(frame);
  }

  function frame(now) {
    raf = 0;
    while (shown < spans.length && times[shown] <= now) spans[shown++].classList.add('on');
    if (follow && shown) keepInView(spans[shown - 1]);
    if (shown < spans.length) wake();
    else if (ended) finish();
  }

  function keepInView(span) {
    const limit = innerHeight * 0.78;
    const bottom = span.getBoundingClientRect().bottom;
    if (bottom > limit) scrollBy({ top: bottom - limit, behavior: 'instant' });
  }

  /** 宣告终稿：终稿若接得上已收文字，补足余下；接不上（如服务端另有定稿），收墨时以终稿为准。 */
  function end(final) {
    if (finished) return;
    if (typeof final === 'string') {
      const sofar = received.trim(); // 终稿两端去过空白，流里的首尾换行不算分歧
      if (final.startsWith(sofar)) push(final.slice(sofar.length));
      else replacement = final;
    }
    ended = true;
    if (shown >= spans.length) finish();
    else wake();
  }

  function skip() {
    instant = true;
    for (; shown < spans.length; shown++) spans[shown].classList.add('on');
    if (ended) finish();
  }

  function cleanup() {
    finished = true;
    cancelAnimationFrame(raf);
    removeEventListener('wheel', release);
    removeEventListener('touchmove', release);
  }

  function finish() {
    if (finished) return;
    cleanup();
    for (; shown < spans.length; shown++) spans[shown].classList.add('on');
    setTimeout(() => {
      container.textContent = '';
      for (const text of paragraphs(replacement ?? received)) {
        const p = document.createElement('p');
        p.textContent = text;
        container.append(p);
      }
      onDone?.();
    }, instant ? 0 : SETTLE);
  }

  return { push, end, skip, cancel: cleanup };
}
