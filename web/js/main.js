/**
 * [INPUT]: 依赖 api.js / mock.js（服务）、store.js（状态）、ui/*（组件）
 * [OUTPUT]: 启动流程：择服务 → 建状态 → 挂组件 → 续读或扉页；全局键位；扉页与书页之间的转场
 * [POS]: web 前端的入口与装配处；带 ?mock 时改用模拟说书人（?mock=flaky 另模拟三成失联）。
 *        ES Modules 须经 http(s) 加载，故模拟模式也要由任一静态服务托管
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { createApi } from './api.js';
import { createMock } from './mock.js';
import { createStore } from './store.js';
import { mountActions } from './ui/actions.js';
import { mountMasthead } from './ui/masthead.js';
import { mountRumors } from './ui/rumors.js';
import { mountStory } from './ui/story.js';
import { mountTitle } from './ui/title.js';

const $ = (selector) => document.querySelector(selector);
const params = new URLSearchParams(location.search);
const useMock = params.has('mock');
const service = useMock ? createMock({ flaky: params.get('mock') === 'flaky' }) : createApi();
document.documentElement.dataset.service = service.kind;

const store = createStore(service);
mountTitle($('#title-page'), store);
mountMasthead($('#masthead'), store);
const story = mountStory($('#story'), store, $('#live'));
const actions = mountActions($('#actions'), store);
const rumors = mountRumors({
  button: $('.rumor-btn'), count: $('.rumor-count'), ticker: $('#ticker'), veil: $('#letter'),
}, store);
mountAnew($('.anew-btn'), store);

// ============================================================
//  扉页 ⇄ 书页
// ============================================================
let phase = null;
store.subscribe(syncPhase);

function syncPhase(s) {
  if (s.phase === phase) return;
  const from = phase;
  phase = s.phase;
  const title = $('#title-page');
  const book = $('#book');
  if (phase === 'title' || phase === 'opening') {
    book.hidden = true;
    title.classList.remove('leaving');
    title.hidden = false;
    if (phase === 'title') $('#hero').focus({ preventScroll: true });
  } else if (phase === 'reading') {
    const show = () => { title.hidden = true; book.hidden = false; };
    if (from === 'opening') {
      title.classList.add('leaving');
      setTimeout(show, 700);
    } else {
      show();
      requestAnimationFrame(() => scrollTo({ top: document.body.scrollHeight }));
    }
  }
}

// ============================================================
//  另起一卷：二次确认，三秒内再点方才作数
// ============================================================
function mountAnew(button, store) {
  let armed = 0;
  const tail = button.querySelector('.anew-tail');
  const label = (head, rest, confirming) => {
    button.firstChild.textContent = head;
    tail.textContent = rest;
    button.classList.toggle('confirming', confirming);
  };
  const disarm = () => { clearTimeout(armed); armed = 0; label('另起', '一卷', false); };
  button.addEventListener('click', () => {
    if (armed) {
      disarm();
      store.anew();
    } else {
      label('确定', '另起', true);
      armed = setTimeout(disarm, 3000);
    }
  });
}

// ============================================================
//  键位：一二三择路 · / 落笔 · 空格略过誊写 · Esc 阖信或离笔
// ============================================================
document.addEventListener('keydown', (e) => {
  if (rumors.isOpen()) {
    if (e.key === 'Escape') rumors.close();
    return;
  }
  if (e.target.matches('input, textarea')) {
    if (e.key === 'Escape') e.target.blur();
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const s = store.get();
  if (s.typing && (e.key === ' ' || e.key === 'Enter')) {
    e.preventDefault();
    story.skip();
  } else if (['1', '2', '3'].includes(e.key)) {
    actions.choose(Number(e.key) - 1);
  } else if (e.key === '/') {
    e.preventDefault();
    actions.focusFree();
  }
});

store.boot();
