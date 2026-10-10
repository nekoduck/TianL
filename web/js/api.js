/**
 * [INPUT]: 依赖 contract.js 的 compatible / ServiceError；依赖浏览器 fetch、AbortController、TextDecoderStream
 * [OUTPUT]: 对外提供 createApi(base) → Service { kind, connect, start, act }
 * [POS]: 真实对接层，全前端唯一发出网络请求的地方。给了流式监听就以 Accept: text/event-stream 请求，
 *        逐帧解析 SSE（stage / head / text / done / error）；服务端回的若是普通 JSON，照常收下——两种回应同一终值
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
import { compatible, ServiceError } from './contract.js';

const TIMEOUT = 180_000; // 一回合可能串起导演、编剧、推演、史官多次大模型调用

function verify(data, status) {
  if (!data) throw new ServiceError('internal', status);
  if (!compatible(data.protocol)) throw new ServiceError('version', status);
  if (data.error) throw new ServiceError(data.error.code, status, data.error.message);
  return data;
}

function frameOf(text) {
  let event = 'message';
  let data = '';
  for (const line of text.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data += line.slice(5).trim();
  }
  return { event, data: data ? JSON.parse(data) : null };
}

/** 读完一条 SSE 流：沿途分发 stage/head/text，返回 done 的载荷；流在 done 之前断了视为失联。 */
async function readStream(res, on) {
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let cut;
    while ((cut = buffer.indexOf('\n\n')) >= 0) {
      const { event, data } = frameOf(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 2);
      if (event === 'done') return verify(data, res.status);
      if (event === 'error') verify(data, res.status);
      else if (event === 'stage') on.stage?.(data.stage);
      else if (event === 'head') on.head?.(data);
      else if (event === 'text') on.text?.(data.delta);
    }
  }
  throw new ServiceError('network');
}

export function createApi(base = '') {
  async function call(method, path, body, on) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT);
    try {
      const res = await fetch(base + path, {
        method,
        headers: {
          Accept: on ? 'text/event-stream, application/json' : 'application/json',
          ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
      if (on && res.ok && (res.headers.get('Content-Type') || '').startsWith('text/event-stream')) {
        return await readStream(res, on);
      }
      return verify(await res.json().catch(() => null), res.status);
    } catch (e) {
      if (e instanceof ServiceError) throw e;
      throw new ServiceError(e.name === 'AbortError' ? 'timeout' : 'network');
    } finally {
      clearTimeout(timer);
    }
  }

  return {
    kind: 'api',
    async connect() {
      const payload = await call('GET', '/api/session');
      return payload.session ? payload : null;
    },
    start: (name, on) => call('POST', '/api/session', { name }, on),
    act: (action, on) => call('POST', '/api/action', action, on),
  };
}
