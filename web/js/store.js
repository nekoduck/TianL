/**
 * [INPUT]: 依赖 contract.js 的 ServiceError；依赖一个 Service（api.js 或 mock.js，形状见 contract.js）
 * [OUTPUT]: 对外提供 createStore(service) → { get, subscribe, boot, start, act, retry, typingDone, readRumors, anew }
 * [POS]: 前端状态层——唯一的状态源。组件只读 get()、只经动作改状态；与服务的往来、错误归类、传闻已读都在这里
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { ServiceError } from './contract.js';

const BLANK = {
  phase: 'boot',      // boot 启动 · title 扉页 · opening 开卷中 · reading 阅读与行动
  hero: '',
  turns: [],          // 回合载荷；新到者带 fresh=true，交给打字机誊写
  pending: null,      // { text } 已落笔、待说书人回应的举动
  busy: false,        // 正在等服务
  typing: false,      // 打字机正在誊写最新回合
  rumors: [],         // { id, date, place, text, unread }
  notice: null,       // { seq, count } 誊写完毕后待提示的新传闻
  error: null,        // { code, message }
  lastAction: null,   // { action, text } 供"再试一次"
};

const rumorsIn = (turns, unread) =>
  turns.flatMap((t) => t.events.filter((e) => e.kind === 'rumor').map((e) => ({ ...e, unread })));

export function createStore(service) {
  let state = { ...BLANK };
  let unannounced = 0;
  const subs = new Set();

  function set(patch) {
    state = { ...state, ...patch };
    subs.forEach((fn) => fn(state));
  }

  /** 以会话载荷重建全书；fresh 表示最后一回合是刚刚开卷所得，需要誊写。 */
  function restore(payload, fresh) {
    const turns = payload.transcript.map((t, i, all) => ({ ...t, fresh: fresh && i === all.length - 1 }));
    unannounced = fresh ? rumorsIn(turns.slice(-1), true).length : 0;
    set({
      ...BLANK, phase: 'reading', hero: payload.session.hero, turns, typing: fresh,
      rumors: rumorsIn(turns, false).map((r, i, all) => ({ ...r, unread: fresh && i >= all.length - unannounced })),
    });
  }

  async function fail(e, resync) {
    const err = e instanceof ServiceError ? e : new ServiceError('internal');
    const error = { code: err.code, message: err.message };
    if (err.code === 'no_session') return set({ ...BLANK, phase: 'title', error });
    if (err.code === 'stale_option' && resync) {
      try { restore(await service.connect(), false); } catch { /* 拉不回来就保持原样 */ }
    }
    set({ busy: false, pending: null, error });
  }

  return {
    get: () => state,

    subscribe(fn) {
      subs.add(fn);
      return () => subs.delete(fn);
    },

    async boot() {
      try {
        const payload = await service.connect();
        payload ? restore(payload, false) : set({ phase: 'title' });
      } catch (e) {
        set({ phase: 'title', error: { code: e.code || 'internal', message: e.message } });
      }
    },

    async start(name) {
      if (state.busy) return;
      set({ phase: 'opening', busy: true, error: null });
      try {
        restore(await service.start(name), true);
      } catch (e) {
        set({ phase: 'title', busy: false, error: { code: e.code || 'internal', message: e.message } });
      }
    },

    async act(action, text) {
      if (state.busy || state.typing || state.phase !== 'reading') return;
      set({ busy: true, pending: { text }, error: null, lastAction: { action, text } });
      try {
        const turn = await service.act(action);
        const arrived = rumorsIn([turn], true);
        unannounced += arrived.length;
        set({
          turns: [...state.turns, { ...turn, fresh: true }],
          rumors: [...state.rumors, ...arrived],
          busy: false, pending: null, typing: true,
        });
      } catch (e) {
        await fail(e, true);
      }
    },

    retry() {
      if (state.lastAction) this.act(state.lastAction.action, state.lastAction.text);
    },

    /** 打字机誊写完毕：放出选项，并在此刻（而非誊写途中）提示新传闻，免得打断阅读。 */
    typingDone() {
      const notice = unannounced ? { seq: (state.notice?.seq || 0) + 1, count: unannounced } : state.notice;
      unannounced = 0;
      set({ typing: false, notice });
    },

    readRumors() {
      if (state.rumors.some((r) => r.unread)) set({ rumors: state.rumors.map((r) => ({ ...r, unread: false })) });
    },

    anew() {
      unannounced = 0;
      set({ ...BLANK, phase: 'title' });
    },
  };
}
