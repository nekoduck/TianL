/**
 * [INPUT]: 依赖 store（turns / busy / typing / error / lastAction），cn.js 的 cn()
 * [OUTPUT]: 对外提供 mountActions(section, store) → { choose(i), focusFree() }
 * [POS]: 行动区——三条去路与一支自由之笔。焦点互斥：书写时去路退后，择路时笔退后；
 *        誊写未毕不放出选项，等待回应时全区静默；失败时给出朱字与"再试一次"
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { cn } from '../cn.js';

const hasKeyboard = matchMedia('(hover: hover) and (pointer: fine)');
const NO_RETRY = new Set(['stale_option', 'bad_request', 'no_session']);

export function mountActions(section, store) {
  const list = section.querySelector('.options');
  const form = section.querySelector('.free');
  const input = form.querySelector('input');
  const submit = form.querySelector('button');
  const hint = section.querySelector('.hint');
  const error = section.querySelector('.error');
  const errorText = error.querySelector('.error-text');
  const retry = error.querySelector('.retry');
  let builtFor = null;

  const ready = (s) => s.phase === 'reading' && !s.busy && !s.typing;

  function build(turn) {
    list.textContent = '';
    turn.options.forEach((o, i) => {
      const li = document.createElement('li');
      li.style.setProperty('--i', i);
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.id = o.id;
      button.dataset.label = o.label;
      const num = document.createElement('span');
      num.className = 'num';
      num.textContent = cn(i + 1);
      const label = document.createElement('span');
      label.className = 'label';
      label.textContent = o.label;
      button.append(num, label);
      li.append(button);
      list.append(li);
    });
  }

  function render(s) {
    const current = s.turns[s.turns.length - 1];
    if (current && current !== builtFor) {
      builtFor = current;
      build(current);
    }
    const ok = ready(s);
    section.dataset.state = s.busy ? 'busy' : s.typing ? 'typing' : ok ? 'ready' : 'idle';
    list.querySelectorAll('button').forEach((b) => { b.disabled = !ok; });
    input.disabled = !ok;
    submit.disabled = !ok || !input.value.trim();
    if (!ok) section.classList.remove('choosing');

    hint.textContent = s.typing ? '点击正文或按空格，可略过誊写'
      : ok && hasKeyboard.matches ? '按一、二、三键择路，或按 / 落笔' : '';

    const showError = s.error && s.phase === 'reading';
    error.hidden = !showError;
    errorText.textContent = showError ? s.error.message : '';
    retry.hidden = !showError || !s.lastAction || NO_RETRY.has(s.error.code);
  }

  list.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b || b.disabled) return;
    store.act({ action_type: 'selection', action_content: b.dataset.id }, b.dataset.label);
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || !ready(store.get())) return;
    input.value = '';
    section.classList.remove('composing');
    store.act({ action_type: 'free_text', action_content: text }, text);
  });

  input.addEventListener('input', () => {
    const writing = !!input.value.trim();
    section.classList.toggle('composing', writing);
    submit.disabled = !writing || !ready(store.get());
  });

  const choosing = (on) => () => section.classList.toggle('choosing', on && ready(store.get()));
  list.addEventListener('pointerenter', choosing(true));
  list.addEventListener('pointerleave', choosing(false));
  list.addEventListener('focusin', choosing(true));
  list.addEventListener('focusout', choosing(false));
  retry.addEventListener('click', () => store.retry());

  store.subscribe(render);
  render(store.get());

  return {
    choose(i) {
      const b = list.querySelectorAll('button')[i];
      if (b && !b.disabled) b.click();
    },
    focusFree() {
      if (!input.disabled) input.focus();
    },
  };
}
