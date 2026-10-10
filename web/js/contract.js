/**
 * [INPUT]: 无外部依赖；条文以 web/PROTOCOL.md 为准
 * [OUTPUT]: 对外提供 VERSION、MESSAGES（错误码→措辞）、ServiceError、Service 接口说明
 * [POS]: 前端的契约镜像——api.js（真实对接）与 mock.js（独立开发）共同遵守的版本号、错误语汇与服务接口
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

export const VERSION = 'tianlong/1';

/** 错误码 → 面向玩家的措辞。服务端若给出更具体的 message，以服务端为准。 */
export const MESSAGES = {
  bad_request: '这一笔没有写清楚，请再写一次。',
  no_session: '这一卷已经合上，请重新开卷。',
  busy: '说书人尚在落笔，请稍候片刻。',
  stale_option: '这个选项已随时势而去，请依眼下情形重新抉择。',
  internal: '说书人一时失神，请再试一次。',
  network: '与说书人失了联络，请确认服务仍在运行。',
  timeout: '说书人沉吟太久，请再试一次。',
  version: '前后端契约版本不一致，请刷新页面。',
};

export class ServiceError extends Error {
  constructor(code, status = 0, message = '') {
    super(message || MESSAGES[code] || MESSAGES.internal);
    this.code = MESSAGES[code] ? code : 'internal';
    this.status = status;
  }
}

/**
 * Service —— 真实服务与模拟服务的共同形状：
 *   connect()        → Promise<SessionPayload | null>   续读；尚未开卷则为 null
 *   start(name)      → Promise<SessionPayload>          开卷
 *   act(action)      → Promise<TurnPayload>             action = { action_type, action_content }
 * 失败一律抛出 ServiceError。
 */
