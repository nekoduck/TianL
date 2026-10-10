/**
 * [INPUT]: 依赖 contract.js 的 VERSION / ServiceError；依赖浏览器 fetch 与 AbortController
 * [OUTPUT]: 对外提供 createApi(base) → Service { kind, connect, start, act }
 * [POS]: 真实对接层，全前端唯一发出网络请求的地方；把 HTTP 状态与错误载荷统一翻译成 ServiceError
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { VERSION, ServiceError } from './contract.js';

const TIMEOUT = 180_000; // 一回合可能串起导演、编剧、推演、史官多次大模型调用

export function createApi(base = '') {
  async function call(method, path, body) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT);
    let res;
    try {
      res = await fetch(base + path, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
    } catch (e) {
      throw new ServiceError(e.name === 'AbortError' ? 'timeout' : 'network');
    } finally {
      clearTimeout(timer);
    }
    const data = await res.json().catch(() => null);
    if (!data) throw new ServiceError('internal', res.status);
    if (data.protocol !== VERSION) throw new ServiceError('version', res.status);
    if (!res.ok || data.error) throw new ServiceError(data.error?.code, res.status, data.error?.message);
    return data;
  }

  return {
    kind: 'api',
    async connect() {
      const payload = await call('GET', '/api/session');
      return payload.session ? payload : null;
    },
    start: (name) => call('POST', '/api/session', { name }),
    act: (action) => call('POST', '/api/action', action),
  };
}
