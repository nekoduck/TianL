/**
 * [INPUT]: 依赖 contract.js 的 ServiceError；依赖一个 Service（api.js 或 mock.js，形状见 contract.js）
 * [OUTPUT]: 对外提供 createStore(service) → { get, subscribe, boot, start, act, retry, typingDone, readRumors, anew }
 * [POS]: 前端状态层——唯一的状态源。组件只读 get()、只经动作改状态；与服务的往来（含流式）、错误归类、传闻已读都在这里。
 *        流式回合：head 一到即立回合(streaming)、text 累进 stream、done 以终稿替换抬头；抬头已到而流断了，就向服务端重新同步
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { ServiceError } from './contract.js';

const BLANK = {
  phase: 'boot',      // boot 启动 · title 扉页 · opening 开卷中 · reading 阅读与行动
  hero: '',
  turns: [],          // 回合载荷；新到者带 fresh=true 交给打字机，流式途中的抬头另带 streaming=true
  stream: null,       // 流式途中已收到的正文
  stage: null,        // 说书人此刻的进度：direct / settle / write
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

const errorOf = (e) => {
  const err = e instanceof ServiceError ? e : new ServiceError('internal');
  return { code: err.code, message: err.message };
};

export function createStore(service) {
  let state = { ...BLANK };
  let unannounced = 0;
  const subs = new Set();

  function set(patch) {
    state = { ...state, ...patch };
    subs.forEach((fn) => fn(state));
  }

  /** 以会话载荷重建全书；fresh 表示最后一回合是刚刚所得，需要誊写。 */
  function restore(payload, fresh) {
    const turns = payload.transcript.map((t, i, all) => ({ ...t, fresh: fresh && i === all.length - 1 }));
    unannounced = fresh ? rumorsIn(turns.slice(-1), true).length : 0;
    set({
      ...BLANK, phase: 'reading', hero: payload.session.hero, turns, typing: fresh,
      rumors: rumorsIn(turns, false).map((r, i, all) => ({ ...r, unread: fresh && i >= all.length - unannounced })),
    });
  }

  /** 一条流的监听：head 立回合，text 累进正文，stage 报进度。 */
  function streaming(onHead) {
    const flow = { headSeen: false };
    flow.on = {
      stage: (stage) => set({ stage }),
      head: (head) => {
        flow.headSeen = true;
        onHead({ ...head, fresh: true, streaming: true });
      },
      text: (delta) => set({ stream: (state.stream ?? '') + delta }),
    };
    return flow;
  }

  /** 终稿落定：替换流式抬头（或直接追加），收下传闻，留待誊毕再提示。 */
  function settle(turn, headSeen) {
    const arrived = rumorsIn([turn], true);
    unannounced += arrived.length;
    const base = headSeen ? state.turns.slice(0, -1) : state.turns;
    set({
      turns: [...base, { ...turn, fresh: true }], rumors: [...state.rumors, ...arrived],
      busy: false, pending: null, stage: null, stream: null, typing: true,
    });
  }

  /** 抬头已到而流断了：回合多半已在服务端写完并存档——重新拉回整卷，正在誊写的那回合以终稿收尾。 */
  async function resync(e, liveTurn) {
    try {
      const payload = await service.connect();
      if (payload && payload.transcript.some((t) => t.turn === liveTurn)) {
        restore(payload, false);
        set({ typing: true }); // 打字机仍在誊这一回合，誊毕自会收起
        return;
      }
    } catch { /* 连续读也不成，就按失败处理 */ }
    unannounced = 0;
    set({ turns: state.turns.filter((t) => t.turn !== liveTurn), busy: false, typing: false,
      pending: null, stage: null, stream: null, error: errorOf(e) });
  }

  async function fail(e) {
    const error = errorOf(e);
    if (error.code === 'no_session') return set({ ...BLANK, phase: 'title', error });
    if (error.code === 'stale_option') {
      try { restore(await service.connect(), false); } catch { /* 拉不回来就保持原样 */ }
    }
    set({ busy: false, pending: null, stage: null, stream: null, error });
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
        set({ phase: 'title', error: errorOf(e) });
      }
    },

    async start(name) {
      if (state.busy) return;
      set({ phase: 'opening', busy: true, stage: 'direct', error: null });
      const flow = streaming((head) => {
        unannounced = 0;
        set({ ...BLANK, phase: 'reading', hero: name || '无名', turns: [head], busy: true, typing: true, stream: '' });
      });
      try {
        const payload = await service.start(name, flow.on);
        if (!flow.headSeen) return restore(payload, true);
        set({ hero: payload.session.hero });
        settle(payload.transcript[payload.transcript.length - 1], true);
      } catch (e) {
        if (flow.headSeen) return resync(e, 1);
        set({ phase: 'title', busy: false, stage: null, error: errorOf(e) });
      }
    },

    async act(action, text) {
      if (state.busy || state.typing || state.phase !== 'reading') return;
      set({ busy: true, pending: { text }, stage: 'direct', error: null, lastAction: { action, text } });
      const flow = streaming((head) => set({
        turns: [...state.turns, head], pending: null, stage: null, typing: true, stream: '',
      }));
      try {
        settle(await service.act(action, flow.on), flow.headSeen);
      } catch (e) {
        if (flow.headSeen) return resync(e, state.turns[state.turns.length - 1].turn);
        await fail(e);
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
