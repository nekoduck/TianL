/**
 * [INPUT]: 依赖浏览器 requestAnimationFrame 与 ink.css 的 .ink / .ink.on（墨迹晕开）
 * [OUTPUT]: 对外提供 typewrite(container, paragraphs, { onDone }) → { skip }
 * [POS]: 打字机特效——逐字显影新回合正文，标点处停顿如人换气；随誊写跟随视线，玩家一旦自行滚动即不再牵引；
 *        誊毕后把逐字的 span 收回为纯文本，往事不留 DOM 负担
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

const PAUSE = { '，': 90, '、': 70, '；': 130, '：': 110, '。': 240, '！': 240, '？': 240, '…': 150, '」': 50, '”': 50 };
const PARAGRAPH_PAUSE = 280;
const SETTLE = 700; // 最后一字显影所需，与 .ink 的过渡时长相合

export function typewrite(container, paragraphs, { onDone } = {}) {
  const total = paragraphs.reduce((n, p) => n + p.length, 0);
  const step = total > 600 ? 14 : total > 300 ? 20 : 26; // 长文略快，免得久候

  const spans = [];
  const times = [];
  let t = 0;
  for (const text of paragraphs) {
    const p = document.createElement('p');
    for (const ch of text) {
      const span = document.createElement('span');
      span.className = 'ink';
      span.textContent = ch;
      p.append(span);
      spans.push(span);
      times.push(t);
      t += step + (PAUSE[ch] || 0);
    }
    t += PARAGRAPH_PAUSE;
    container.append(p);
  }

  let i = 0;
  let raf = 0;
  let done = false;
  let follow = true;
  const start = performance.now();
  const release = () => { follow = false; };
  addEventListener('wheel', release, { passive: true });
  addEventListener('touchmove', release, { passive: true });

  function frame(now) {
    while (i < spans.length && times[i] <= now - start) spans[i++].classList.add('on');
    if (follow && i) keepInView(spans[i - 1]);
    if (i < spans.length) raf = requestAnimationFrame(frame);
    else finish();
  }

  function keepInView(span) {
    const limit = innerHeight * 0.78;
    const bottom = span.getBoundingClientRect().bottom;
    if (bottom > limit) scrollBy({ top: bottom - limit, behavior: 'instant' });
  }

  function finish() {
    if (done) return;
    done = true;
    cancelAnimationFrame(raf);
    for (; i < spans.length; i++) spans[i].classList.add('on');
    removeEventListener('wheel', release);
    removeEventListener('touchmove', release);
    setTimeout(() => {
      container.querySelectorAll('p').forEach((p, k) => { p.textContent = paragraphs[k]; });
      onDone?.();
    }, SETTLE);
  }

  raf = requestAnimationFrame(frame);
  return { skip: finish };
}
