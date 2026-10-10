"""
[INPUT]: 依赖 http.server 的 ThreadingHTTPServer / SimpleHTTPRequestHandler、threading.Lock、engine.Game、world.World、protocol
[OUTPUT]: 对外提供 make_server()（构建本地 Web 服务）、serve()（阻塞运行）、Hub（单机单局的会话中枢）
[POS]: 传输层——把 protocol 的载荷挂到 HTTP 上，并托管 web/ 静态前端；不含游戏逻辑，也不解释协议字段。
       路由：GET /api/session 续读 · POST /api/session 开卷 · POST /api/action 行动 · 其余路径为静态文件
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import logging
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

from . import protocol
from .engine import Game
from .protocol import ProtocolError
from .world.world import World

WEB = Path(__file__).resolve().parents[1] / "web"
MAX_BODY = 16 * 1024
log = logging.getLogger("tianlong")


# ============================================================
#  会话：一卷书 = 一局游戏 + 它的全部回合载荷（刷新页面即可续读）
# ============================================================
class Session:
    def __init__(self, hero: str | None, llm):
        self.id = uuid.uuid4().hex[:12]
        self.hero = hero or "无名"
        self.game = Game(World.create(hero), llm)
        self.transcript = [protocol.present(self.game.open(), 1, None)]

    def payload(self) -> dict:
        return protocol.session_payload(self.id, self.hero, self.transcript)

    def act(self, body) -> dict:
        deed, text = protocol.resolve(body, self.transcript[-1])
        turn = protocol.present(self.game.act(text), len(self.transcript) + 1, deed)
        self.transcript.append(turn)
        return turn


class Hub:
    """单机单局：同一时刻只有一卷书，且同一时刻只能落一笔——回合涉及多次大模型调用，绝不并发改写世界。"""

    def __init__(self, llm):
        self.llm, self.session, self.lock = llm, None, Lock()

    def _exclusive(self, fn):
        if not self.lock.acquire(blocking=False):
            raise ProtocolError(409, "busy", "说书人尚在落笔，请稍候片刻")
        try:
            return fn()
        finally:
            self.lock.release()

    def current(self, _body=None) -> dict:
        """续读。尚未开卷不是错误：session 为 null、transcript 为空。"""
        return self.session.payload() if self.session else protocol.session_payload(None, None, [])

    def start(self, body) -> dict:
        hero = protocol.hero_name(body)

        def begin():
            self.session = Session(hero, self.llm)
            return self.session.payload()
        return self._exclusive(begin)

    def act(self, body) -> dict:
        if self.session is None:
            raise ProtocolError(404, "no_session", "这一卷已经合上，请重新开卷")
        return self._exclusive(lambda: self.session.act(body))


# ============================================================
#  HTTP：/api/* 走协议，其余交给静态文件
# ============================================================
class Handler(SimpleHTTPRequestHandler):
    hub: Hub  # 由 make_server 绑定

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/session":
            return self._api(200, self.hub.current, read_body=False)
        if path.startswith("/api/"):
            return self._send(404, ProtocolError(404, "not_found", "没有这条路").payload())
        return super().do_GET()

    def do_POST(self):
        routes = {"/api/session": (201, self.hub.start), "/api/action": (200, self.hub.act)}
        route = routes.get(self.path.split("?", 1)[0])
        if route is None:
            return self._send(404, ProtocolError(404, "not_found", "没有这条路").payload())
        self._api(*route)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ProtocolError(413, "bad_request", "这一笔写得太长了")
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ProtocolError(400, "bad_request", "请求不是合法的 JSON") from None

    def _api(self, status: int, fn, read_body: bool = True):
        try:
            self._send(status, fn(self._body() if read_body else None))
        except ProtocolError as e:
            self._send(e.status, e.payload())
        except Exception:
            log.exception("回合处理失败")
            self._send(500, ProtocolError(500, "internal", "说书人一时失神，请再试一次").payload())

    def _send(self, status: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # 本地开发：改了前端刷新即见
        super().end_headers()

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)


def make_server(llm, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"hub": Hub(llm)})
    return ThreadingHTTPServer((host, port), handler)


def serve(llm, host: str = "127.0.0.1", port: int = 8000):
    with make_server(llm, host, port) as httpd:
        httpd.serve_forever()
