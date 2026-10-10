/**
 * [INPUT]: 依赖 store（turns 的最新一回合：scene / time / status）
 * [OUTPUT]: 对外提供 mountMasthead(header, store)
 * [POS]: 书眉——当前地点、地域、时辰与主角身况。宽屏竖排于正文左侧，窄屏化为顶栏；
 *        身况只呈文字标签，伤势以暗朱砂示警；换了地方则书眉淡入，如翻到新的一页
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

export function mountMasthead(header, store) {
  const place = header.querySelector('.place');
  const region = header.querySelector('.region');
  const year = header.querySelector('.year');
  const date = header.querySelector('.date');
  const hour = header.querySelector('.hour');
  const status = header.querySelector('.status');
  let last = null;

  function render(s) {
    const turn = s.turns[s.turns.length - 1];
    if (!turn || turn === last) return;
    const moved = last && last.scene.place !== turn.scene.place;
    last = turn;

    place.textContent = turn.scene.place;
    region.textContent = turn.scene.region || '';
    region.hidden = !turn.scene.region;
    year.textContent = turn.time.year;
    date.textContent = turn.time.date;
    hour.textContent = turn.time.hour;

    status.textContent = '';
    turn.status.forEach((tag) => {
      const li = document.createElement('li');
      li.className = tag.tone;
      li.textContent = tag.text;
      status.append(li);
    });

    document.title = `${turn.scene.place} · 天龍八部`;
    if (moved) {
      header.classList.remove('turning');
      void header.offsetWidth; // 重启动画
      header.classList.add('turning');
    }
  }

  store.subscribe(render);
  render(store.get());
}
