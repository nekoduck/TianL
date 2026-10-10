/**
 * [INPUT]: 依赖 store（phase / stage / error / start），contract.js 的 STAGES
 * [OUTPUT]: 对外提供 mountTitle(section, store)
 * [POS]: 扉页——竖排书名与一方朱印；填写名号即开卷。开卷需说书人先写开场，期间报出他此刻的进度（构思、推演）
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

import { STAGES } from '../contract.js';

export function mountTitle(section, store) {
  const form = section.querySelector('.name-form');
  const input = form.querySelector('input');
  const button = form.querySelector('button');
  const status = section.querySelector('.title-status');

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    store.start(input.value.trim());
  });

  function render(s) {
    const opening = s.phase === 'opening';
    input.disabled = button.disabled = opening;
    status.className = 'title-status';
    status.textContent = '';
    if (opening) {
      const dots = document.createElement('span');
      dots.className = 'dots';
      dots.append(document.createElement('i'), document.createElement('i'), document.createElement('i'));
      status.append(dots, `　${STAGES[s.stage] || '说书人正在铺纸研墨'}`);
    } else if (s.phase === 'title' && s.error) {
      status.classList.add('error');
      status.textContent = s.error.message;
    }
  }

  store.subscribe(render);
  render(store.get());
}
