"""
[INPUT]: 依赖 tianlong.protocol / tianlong.server 与离线引擎（llm=None）；经 urllib 走真实 HTTP
[OUTPUT]: unittest 用例——回合载荷形状、行动解析(选择/自由书写/过期/越界)、开卷与续读、忙碌互斥、错误载荷、静态前端托管
[POS]: tests 的契约验证：web/PROTOCOL.md 的每一条，在 Python 实现上都有一个对应的断言
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
import json
import logging
import threading
import unittest
import urllib.error
import urllib.request

from tianlong import protocol
from tianlong.engine import Game
from tianlong.protocol import ProtocolError
from tianlong.server import make_server
from tianlong.world.world import World

logging.disable(logging.WARNING)


class PayloadTest(unittest.TestCase):
    def setUp(self):
        self.turn = protocol.present(Game(World.create("测")).open(), 1, None)

    def test_turn_payload_shape(self):
        t = self.turn
        self.assertEqual(t["protocol"], protocol.VERSION)
        self.assertEqual(set(t), {"protocol", "turn", "deed", "scene", "time", "narrative", "options", "status", "events"})
        self.assertEqual(t["scene"], {"place": "剑湖宫·练武厅", "region": "大理·无量山"})
        self.assertEqual(t["time"], {"year": "元祐六年", "date": "二月初一", "hour": "辰时", "label": "元祐六年二月初一 辰时"})
        self.assertEqual([o["id"] for o in t["options"]], ["t1-1", "t1-2", "t1-3"])
        self.assertTrue(all(tag["tone"] in ("plain", "warn", "alert") for tag in t["status"]))
        self.assertTrue(t["events"] and {e["kind"] for e in t["events"]} <= {"witnessed", "rumor"})
        self.assertNotIn("hp", json.dumps(t))  # 载荷里没有数值，只有文字

    def test_selection_resolves_to_option_text(self):
        deed, text = protocol.resolve({"action_type": "selection", "action_content": "t1-2"}, self.turn)
        self.assertEqual(text, self.turn["options"][1]["label"])
        self.assertEqual(deed, {"action_type": "selection", "action_content": "t1-2", "text": text})

    def test_bad_actions(self):
        cases = [({"action_type": "selection", "action_content": "t0-1"}, 409, "stale_option"),
                 ({"action_type": "free_text", "action_content": "   "}, 400, "bad_request"),
                 ({"action_type": "free_text", "action_content": "走" * 201}, 400, "bad_request"),
                 ({"action_type": "shout", "action_content": "x"}, 400, "bad_request"),
                 ({"action_type": "free_text", "action_content": 3}, 400, "bad_request"),
                 ("not a dict", 400, "bad_request")]
        for body, status, code in cases:
            with self.assertRaises(ProtocolError) as ctx:
                protocol.resolve(body, self.turn)
            self.assertEqual((ctx.exception.status, ctx.exception.code), (status, code), body)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = make_server(None, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.status, res.headers.get("Content-Type"), res.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type"), e.read()

    def api(self, method, path, body=None):
        status, _, raw = self.call(method, path, body)
        return status, json.loads(raw)

    def test_full_volume(self):
        hub = self.httpd.RequestHandlerClass.hub
        hub.session = None
        status, body = self.api("GET", "/api/session")
        self.assertEqual((status, body["session"], body["transcript"]), (200, None, []))  # 未开卷不是错误
        status, body = self.api("POST", "/api/action", {"action_type": "free_text", "action_content": "走"})
        self.assertEqual((status, body["error"]["code"]), (404, "no_session"))

        status, body = self.api("POST", "/api/session", {"name": "萧兰"})
        self.assertEqual((status, body["session"]["hero"], len(body["transcript"])), (201, "萧兰", 1))
        first = body["transcript"][0]
        self.assertIsNone(first["deed"])

        status, turn = self.api("POST", "/api/action", {"action_type": "selection", "action_content": "t1-3"})
        self.assertEqual((status, turn["turn"]), (200, 2))
        self.assertEqual(turn["deed"]["text"], first["options"][2]["label"])

        status, body = self.api("POST", "/api/action", {"action_type": "selection", "action_content": "t1-3"})
        self.assertEqual((status, body["error"]["code"]), (409, "stale_option"))

        status, turn = self.api("POST", "/api/action", {"action_type": "free_text", "action_content": "去剑湖宫"})
        self.assertEqual((status, turn["turn"], turn["deed"]["action_type"]), (200, 3, "free_text"))

        status, body = self.api("GET", "/api/session")  # 刷新页面：整卷续读
        self.assertEqual([t["turn"] for t in body["transcript"]], [1, 2, 3])

    def test_busy_while_a_turn_is_being_written(self):
        hub = self.httpd.RequestHandlerClass.hub
        self.api("POST", "/api/session", {})
        hub.lock.acquire()
        try:
            status, body = self.api("POST", "/api/action", {"action_type": "free_text", "action_content": "等"})
        finally:
            hub.lock.release()
        self.assertEqual((status, body["error"]["code"]), (409, "busy"))

    def test_malformed_requests(self):
        status, _, raw = self.call("POST", "/api/session", None)
        self.assertEqual(status, 201)  # 无名开卷
        req = urllib.request.Request(self.base + "/api/action", data=b"{oops", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(json.loads(ctx.exception.read())["error"]["code"], "bad_request")
        status, body = self.api("POST", "/api/session", {"name": "名" * 13})
        self.assertEqual((status, body["error"]["code"]), (400, "bad_request"))
        status, body = self.api("GET", "/api/nowhere")
        self.assertEqual(status, 404)

    def test_static_front_end(self):
        status, ctype, raw = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("天龍八部", raw.decode())
        status, ctype, _ = self.call("GET", "/js/main.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)


if __name__ == "__main__":
    unittest.main()
