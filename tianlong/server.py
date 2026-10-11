"""
[INPUT]: 依赖 http.server 的 ThreadingHTTPServer / SimpleHTTPRequestHandler、threading.Lock、engine.Game、world.World、protocol
[OUTPUT]: 对外提供 make_server()（构建本地 Web 服务，可续卷、可自动存档）、Hub（单机单局的会话中枢）、Session、AUTOSAVE
[POS]: 传输层——把 protocol 的载荷挂到 HTTP 上，并托管 web/ 静态前端；不含游戏逻辑，也不解释协议字段。
       路由：GET /api/session 续读 · POST /api/session 开卷 · POST /api/action 行动 · 其余路径为静态文件；
       POST 只收同源、声明为 JSON 的请求——别的网页无从替玩家开卷落笔（跨站的 JSON 请求须先预检，本服务从不应允）；
       请求头 Accept 含 text/event-stream 时，开卷与行动改以 SSE 逐步推送（stage → head → text… → done）。
       每回合落定即自动存档（与终端 /save 同一格式，外加 web 段），服务重启后续卷
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import logging
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from . import protocol
from .engine import Game
from .protocol import ProtocolError
from .world.world import World

WEB = Path(__file__).resolve().parents[1] / "web"
AUTOSAVE = Path("saves/autosave.json")
MAX_BODY = 16 * 1024
log = logging.getLogger("tianlong")


# ============================================================
#  会话：一卷书 = 一局游戏 + 它的全部回合载荷（刷新页面、重启服务皆可续读）
# ============================================================
class Session:
    def __init__(self, game: Game, hero: str, transcript: list[dict], sid: str | None = None):
        self.game, self.hero, self.transcript = game, hero, transcript
        self.id = sid or uuid.uuid4().hex[:12]
        if transcript:  # 续卷时让编剧接着上回合的末段落笔
            game.last_text = transcript[-1]["narrative"]

    @classmethod
    def begin(cls, hero: str | None, llm, send=None) -> "Session":
        """开卷：新建世界并写出开场回合；send 存在则边写边送。名号与书中人物、地名重名则不收（剧情里分不清是谁）。"""
        try:
            world = World.create(hero)
        except ValueError as e:
            raise ProtocolError(400, "bad_request", str(e)) from None
        session = cls(Game(world, llm), hero or "无名", [])
        on = protocol.relay(send, 1, None) if send else None
        session.transcript.append(protocol.present(session.game.open(on), 1, None))
        return session

    @classmethod
    def resume(cls, path, llm) -> "Session":
        """续卷：读存档——Web 自动存档带回合记录；终端 /save 的存档没有，就补写一个开场。"""
        data = json.loads(Path(path).read_text("utf-8"))
        game = Game(World.from_dump(data), llm)
        web = data.get("web") or {}
        session = cls(game, game.world.player["name"], list(web.get("transcript") or []),
                      (web.get("session") or {}).get("id"))
        if not session.transcript:
            session.transcript.append(protocol.present(game.open(), 1, None))
        return session

    def payload(self) -> dict:
        return protocol.session_payload(self.id, self.hero, self.transcript)

    def act(self, body, send=None) -> dict:
        deed, text = protocol.resolve(body, self.transcript[-1], self.id)
        n = len(self.transcript) + 1
        on = protocol.relay(send, n, deed) if send else None
        turn = protocol.present(self.game.act(text, on), n, deed)
        self.transcript.append(turn)
        return turn

    def save(self, path):
        """与终端 /save 同一格式（World.dump），外加 web 段：终端可直接 --load，Web 可整卷续读。"""
        self.game.world.save(path, {"web": {"session": {"id": self.id, "hero": self.hero},
                                            "transcript": self.transcript}})


class Hub:
    """单机单局：同一时刻只有一卷书，且同一时刻只能落一笔——回合涉及多次大模型调用，绝不并发改写世界。"""

    def __init__(self, llm, autosave: Path | None = None, session: Session | None = None):
        self.llm, self.autosave, self.session, self.lock = llm, autosave, session, Lock()

    def _exclusive(self, fn):
        if not self.lock.acquire(blocking=False):
            raise ProtocolError(409, "busy", "说书人尚在落笔，请稍候片刻")
        try:
            return fn()
        finally:
            self.lock.release()

    def _persist(self):
        if self.autosave and self.session:
            try:
                self.session.save(self.autosave)
            except OSError as e:  # 存不下不该让这一回合作废
                log.warning("自动存档失败：%s", e)

    def current(self, _body=None, _send=None) -> dict:
        """续读。尚未开卷不是错误：session 为 null、transcript 为空。"""
        return self.session.payload() if self.session else protocol.session_payload(None, None, [])

    def start(self, body, send=None) -> dict:
        hero = protocol.hero_name(body)

        def begin():
            self.session = Session.begin(hero, self.llm, send)
            self._persist()
            return self.session.payload()
        return self._exclusive(begin)

    def act(self, body, send=None) -> dict:
        if self.session is None:
            raise ProtocolError(404, "no_session", "这一卷已经合上，请重新开卷")

        def step():
            turn = self.session.act(body, send)
            self._persist()
            return turn
        return self._exclusive(step)


# ============================================================
#  SSE：首个事件出发时才开流——开流之前的错误仍是普通 JSON 错误，开流之后化为 error 事件
# ============================================================
class _Stream:
    def __init__(self, handler: "Handler"):
        self.h, self.open, self.alive = handler, False, True

    def send(self, event: str, data: dict):
        try:
            if not self.open:
                self.open = True
                self.h.send_response(200)
                self.h.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.h.end_headers()
                self.h.close_connection = True
            if self.alive:
                self.h.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.h.wfile.flush()
        except OSError:  # 读者离席（断开、重置、中止，开流前后皆然）：回合照常写完、照常存档，回来续读即可
            self.alive = False

    def fail(self, err: ProtocolError):
        if self.open:
            self.send("error", err.payload())
        else:
            self.h._send(err.status, err.payload())


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
        if not self._own_page():
            return self._send(403, ProtocolError(403, "forbidden", "只收本页发来的笔墨").payload())
        if "text/event-stream" in (self.headers.get("Accept") or ""):
            return self._stream(route[1])
        self._api(*route)

    def _own_page(self) -> bool:
        """同源且声明为 JSON：浏览器跨站发来的请求必带别家的 Origin；表单与 no-cors 请求又写不出 application/json。"""
        origin = self.headers.get("Origin")
        same = origin is None or urlsplit(origin).netloc == self.headers.get("Host")
        return same and (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() == "application/json"

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ProtocolError(400, "bad_request", "Content-Length 不是数字") from None
        if length < 0:
            raise ProtocolError(400, "bad_request", "Content-Length 不能为负")
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

    def _stream(self, fn):
        out = _Stream(self)
        try:
            out.send("done", fn(self._body(), out.send))  # done 与同一请求的非流式响应体一字不差
        except ProtocolError as e:
            out.fail(e)
        except Exception:
            log.exception("回合处理失败")
            out.fail(ProtocolError(500, "internal", "说书人一时失神，请再试一次"))

    def _send(self, status: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # 本地开发：改了前端刷新即见；流式响应也不得缓存
        super().end_headers()

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)


def make_server(llm, host: str = "127.0.0.1", port: int = 8000, autosave: Path | None = None,
                resume: Path | None = None) -> ThreadingHTTPServer:
    """resume 为存档路径时先续卷；autosave 为路径时每回合落定即存档。"""
    session = Session.resume(resume, llm) if resume else None
    handler = type("BoundHandler", (Handler,), {"hub": Hub(llm, autosave, session)})
    return ThreadingHTTPServer((host, port), handler)
