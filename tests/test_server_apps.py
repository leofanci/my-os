"""Connected apps over HTTP: relay route, integrations API, approve/reject."""
import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import dashboard.server as server
from core import approvals, composio, integrations

PORT = 8765
ORIGIN = f"http://127.0.0.1:{PORT}"
CAT = [{"slug": s, "name": s, "logo": None, "auth": "managed"}
       for s in ("gmail", "googlecalendar", "googledrive", "instagram")]


def request(method, path, body=None, *, cookie=True, origin=True, host=f"127.0.0.1:{PORT}", headers=None):
    h = server.Handler.__new__(server.Handler)
    out = {"headers": {}}
    h.wfile = io.BytesIO()
    h.send_response = lambda code, *a: out.setdefault("code", code)
    h.send_header = lambda k, v: out["headers"].__setitem__(k, v)
    h.end_headers = lambda: None
    h.log_message = lambda *a: None
    raw = b"" if body is None else json.dumps(body).encode()
    msg = Message()
    msg["Host"] = host
    if raw:
        msg["Content-Type"] = "application/json"
    msg["Content-Length"] = str(len(raw))
    if cookie:
        msg["Cookie"] = f"{server.AUTH_COOKIE}={server.AUTH_TOKEN}"
    if origin:
        msg["Origin"] = ORIGIN
    for k, v in (headers or {}).items():
        msg[k] = v
    h.headers, h.rfile, h.path = msg, io.BytesIO(raw), path
    h.client_address = ("127.0.0.1", 50000)
    h.server = SimpleNamespace(server_address=("127.0.0.1", PORT))
    getattr(h, "do_" + method)()
    payload = h.wfile.getvalue()
    try:
        data = json.loads(payload) if payload else None
    except ValueError:
        data = payload
    return out["code"], data, out["headers"], payload


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "chats").mkdir()
        for p in (mock.patch.object(server, "ROOT", self.root),
                  mock.patch.object(server.chat_store, "CHATS_DIR", self.root / "chats"),
                  mock.patch.object(server.db, "db_exists", return_value=True),
                  mock.patch.object(server.composio, "catalog", return_value=CAT),
                  mock.patch.object(server.composio, "connections", return_value={"gmail"})):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)


class Relay(Base):
    PATH = "/api/internal/apps/mcp"
    FRAME = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}

    def setUp(self):
        super().setUp()
        self.token = server.apps_relay.TOKENS.mint(
            {"ws": "hq", "bot": "cos", "chat": "c1", "room": "hq/general", "person": "ceo"})
        self.addCleanup(server.apps_relay.TOKENS.revoke, self.token)
        up = mock.patch.object(server.apps_relay.ComposioUpstream, "forward",
                               return_value=({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}, "m-1"))
        up.start()
        self.addCleanup(up.stop)

    def test_relay_reachable_without_cookie_with_token(self):
        code, data, hdrs, _ = request("POST", self.PATH, self.FRAME, cookie=False, origin=False,
                                      headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(code, 200)
        self.assertEqual(data["result"], {"tools": []})
        self.assertEqual(hdrs.get("mcp-session-id"), "m-1")

    def test_relay_refuses_cookie_only(self):
        self.assertEqual(request("POST", self.PATH, self.FRAME)[0], 403)

    def test_relay_refuses_bad_token(self):
        self.assertEqual(request("POST", self.PATH, self.FRAME, cookie=False,
                                 headers={"Authorization": "Bearer nope"})[0], 403)

    def test_relay_refuses_bad_host(self):
        self.assertEqual(request("POST", self.PATH, self.FRAME, cookie=False, host="evil.example",
                                 headers={"Authorization": f"Bearer {self.token}"})[0], 403)

    def test_relay_get_is_405(self):
        self.assertEqual(request("GET", self.PATH, cookie=False)[0], 405)


class IntegrationsApi(Base):
    def test_integrations_never_return_key(self):
        code, _, _, _ = request("POST", "/api/integrations/key", {"api_key": "ak_topsecret999"})
        self.assertEqual(code, 200)
        self.assertEqual(integrations.api_key(self.root), "ak_topsecret999")
        for method, path, body in (("GET", "/api/integrations", None),
                                   ("GET", "/api/integrations/catalog?q=gm", None),
                                   ("POST", "/api/integrations/grants",
                                    {"ws": "hq", "bot": "cos", "apps": {"gmail": "read"}})):
            code, data, _, raw = request(method, path, body)
            self.assertEqual(code, 200, path)
            self.assertNotIn(b"ak_topsecret999", raw, path)
        code, data, _, _ = request("GET", "/api/integrations")
        self.assertEqual((data["configured"], data["connected"]), (True, ["gmail"]))
        self.assertTrue(any("instagram" in g["apps"] for g in data["pinned"]))
        self.assertEqual(data["grants"]["hq"]["cos"], {"gmail": "read"})

    def test_key_requires_origin(self):
        self.assertEqual(request("POST", "/api/integrations/key", {"api_key": "ak_x"}, origin=False)[0], 403)

    def test_delete_key(self):
        integrations.set_key("ak_x", self.root)
        self.assertEqual(request("DELETE", "/api/integrations/key")[0], 200)
        self.assertIsNone(integrations.api_key(self.root))

    def test_catalog_search(self):
        code, data, _, _ = request("GET", "/api/integrations/catalog?q=insta")
        self.assertEqual([a["slug"] for a in data["apps"]], ["instagram"])

    def test_connect_blocked_400(self):
        integrations.set_key("ak_x", self.root)
        self.assertEqual(request("POST", "/api/integrations/connect", {"toolkit": "firecrawl"})[0], 400)

    def test_connect_returns_url(self):
        integrations.set_key("ak_x", self.root)
        with mock.patch.object(server.composio, "connect_link", return_value="https://backend.composio.dev/l/1"):
            code, data, _, _ = request("POST", "/api/integrations/connect", {"toolkit": "gmail"})
        self.assertEqual((code, data["url"]), (200, "https://backend.composio.dev/l/1"))

    def test_grants_invalid_400(self):
        self.assertEqual(request("POST", "/api/integrations/grants",
                                 {"ws": "hq", "bot": "cos", "apps": {"firecrawl": "write"}})[0], 400)


class Approve(Base):
    def setUp(self):
        super().setUp()
        integrations.set_key("ak_x", self.root)
        server.chat_store.save({"id": "0" * 8 + "-0000-0000-0000-" + "0" * 12, "messages": []})
        self.chat = "0" * 8 + "-0000-0000-0000-" + "0" * 12
        self.rec = approvals.add_app_action(self.root, ws="hq", room="hq/general", chat=self.chat, bot="cos",
                                            person="ceo", toolkit="gmail", slug="GMAIL_SEND_EMAIL",
                                            arguments={"recipient_email": "a@example.com", "body": "hi"})
        self.path = f"/api/approvals/{self.rec['id']}"

    def test_approve_executes_once(self):
        with mock.patch.object(server.composio, "execute", return_value={"successful": True, "data": {}}) as ex:
            code, data, _, _ = request("POST", self.path + "/approve", {})
            again = request("POST", self.path + "/approve", {})[0]
        self.assertEqual((code, data["status"]), (200, "done"))
        self.assertEqual(again, 409)
        ex.assert_called_once_with("ceo", "GMAIL_SEND_EMAIL", {"recipient_email": "a@example.com", "body": "hi"},
                                   self.root)
        notes = server.chat_store.load(self.chat)["messages"]
        self.assertEqual(notes[-1], {**notes[-1], "role": "assistant", "bot": "cos", "content": "Sent."})

    def test_approve_requires_origin(self):
        with mock.patch.object(server.composio, "execute") as ex:
            self.assertEqual(request("POST", self.path + "/approve", {}, origin=False)[0], 403)
        ex.assert_not_called()

    def test_reject_no_call(self):
        with mock.patch.object(server.composio, "execute") as ex:
            code, data, _, _ = request("POST", self.path + "/reject", {})
        self.assertEqual((code, data["status"]), (200, "rejected"))
        ex.assert_not_called()

    def test_approve_refused_after_grant_removed(self):
        integrations.set_grant("hq", "cos", {}, self.root)
        with mock.patch.object(server.composio, "execute") as ex:
            code, data, _, _ = request("POST", self.path + "/approve", {})
        self.assertEqual(code, 409)
        ex.assert_not_called()
        self.assertEqual(approvals.get(self.rec["id"], self.root)["status"], "pending")

    def test_approve_refused_when_not_connected(self):
        with mock.patch.object(server.composio, "connections", return_value=set()), \
                mock.patch.object(server.composio, "execute") as ex:
            self.assertEqual(request("POST", self.path + "/approve", {})[0], 409)
        ex.assert_not_called()

    def test_approve_refused_without_key(self):
        integrations.remove_key(self.root)
        with mock.patch.object(server.composio, "execute") as ex:
            self.assertEqual(request("POST", self.path + "/approve", {})[0], 409)
        ex.assert_not_called()

    def test_approve_with_edit_uses_edited_args(self):
        edited = {"recipient_email": "z@example.com", "body": "edited"}
        with mock.patch.object(server.composio, "execute", return_value={"successful": True}) as ex:
            request("POST", self.path + "/approve", {"arguments": edited})
        self.assertEqual(ex.call_args[0][2], edited)

    def test_approve_timeout_marks_failed(self):
        with mock.patch.object(server.composio, "execute",
                               side_effect=composio.ComposioError("Composio unreachable (TimeoutError)")):
            code, data, _, _ = request("POST", self.path + "/approve", {})
        self.assertEqual((code, data["status"]), (200, "failed"))
        self.assertEqual(data["result"], approvals.STALE_NOTE)

    def test_approve_unsuccessful_marks_failed(self):
        with mock.patch.object(server.composio, "execute", return_value={"successful": False, "error": "bad to"}):
            code, data, _, _ = request("POST", self.path + "/approve", {})
        self.assertEqual((data["status"], data["result"]), ("failed", "Failed: bad to"))


if __name__ == "__main__":
    unittest.main()
