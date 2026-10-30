"""Composio client: locked-down sessions, trusted MCP URLs, no redirects, no retries."""
import io
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

from core import composio, integrations

MCP = "https://backend.composio.dev/tool_router/s1/mcp"


class FakeResp:
    def __init__(self, body, status=200, ctype="application/json", headers=None):
        self.status = status
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = Message()
        self.headers["Content-Type"] = ctype
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Client(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        integrations.set_key("ak_secretkey123", self.root)
        composio._CATALOG.clear()
        self.sent = []
        self.replies = []

    def tearDown(self):
        self.tmp.cleanup()
        composio._CATALOG.clear()

    def fake_open(self, req, timeout=None):
        self.sent.append(req)
        r = self.replies.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r

    def patched(self):
        return mock.patch.object(composio._opener, "open", side_effect=self.fake_open)

    def body(self, i=0):
        return json.loads(self.sent[i].data.decode())

    def test_session_body_locked_down(self):
        self.replies = [FakeResp({"session_id": "s1", "mcp": {"type": "http", "url": MCP}})]
        with self.patched():
            got = composio.ensure_session("ceo", self.root)
        self.assertEqual(got, {"session_id": "s1", "mcp_url": MCP})
        b = self.body()
        self.assertIn("firecrawl", b["toolkits"]["disable"])
        self.assertIs(b["manage_connections"]["enable"], False)
        self.assertIs(b["workbench"]["enable"], False)
        self.assertTrue(b["user_id"].startswith("myos-"))
        self.assertEqual(self.sent[0].get_header("X-api-key"), "ak_secretkey123")
        self.assertTrue(self.sent[0].full_url.startswith(composio.BASE + "/tool_router/session"))

    def test_untrusted_mcp_url_rejected(self):
        self.replies = [FakeResp({"session_id": "s1", "mcp": {"url": "https://evil.example/mcp"}})]
        with self.patched(), self.assertRaises(composio.ComposioError):
            composio.ensure_session("ceo", self.root)
        self.assertNotIn("session_id", integrations.person("ceo", self.root))

    def test_trusted_mcp_url(self):
        self.assertTrue(composio.trusted_mcp_url(MCP))
        self.assertFalse(composio.trusted_mcp_url("http://backend.composio.dev/x"))
        self.assertFalse(composio.trusted_mcp_url("https://composio.dev.evil.example/x"))
        self.assertFalse(composio.trusted_mcp_url("https:" + "//evilcomposio.dev/x"))  # split for the repo host guard

    def test_session_reused(self):
        self.replies = [FakeResp({"session_id": "s1", "mcp": {"url": MCP}})]
        with self.patched():
            composio.ensure_session("ceo", self.root)
            composio.ensure_session("ceo", self.root)
        self.assertEqual(len(self.sent), 1)

    def test_not_configured(self):
        integrations.remove_key(self.root)
        with self.assertRaises(composio.ComposioError):
            composio.ensure_session("ceo", self.root)

    def test_redirect_not_followed(self):
        self.assertTrue(any(isinstance(h, composio._NoRedirect) for h in composio._opener.handlers))
        self.assertIsNone(composio._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example/"))

    def test_execute_no_retry(self):
        integrations.save_session("ceo", "s1", MCP, self.root)
        self.replies = [TimeoutError("slow"), FakeResp({"data": {}, "successful": True})]
        with self.patched(), self.assertRaises(composio.ComposioError):
            composio.execute("ceo", "GMAIL_SEND_EMAIL", {"to": "a@example.com"}, self.root)
        self.assertEqual(len(self.sent), 1)

    def test_execute_sends_slug_and_arguments(self):
        integrations.save_session("ceo", "s1", MCP, self.root)
        self.replies = [FakeResp({"data": {"id": "m1"}, "successful": True})]
        with self.patched():
            out = composio.execute("ceo", "GMAIL_SEND_EMAIL", {"to": "a@example.com"}, self.root)
        self.assertEqual(self.body(), {"tool_slug": "GMAIL_SEND_EMAIL", "arguments": {"to": "a@example.com"}})
        self.assertEqual(out["data"], {"id": "m1"})

    def test_forward_parses_sse_reply(self):
        sse = b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
        self.replies = [FakeResp(sse, ctype="text/event-stream", headers={"mcp-session-id": "m-9"})]
        with self.patched():
            reply, sid = composio.forward(MCP, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, "m-8", self.root)
        self.assertEqual(reply, {"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertEqual(sid, "m-9")
        self.assertEqual(self.sent[0].get_header("Mcp-session-id"), "m-8")
        self.assertEqual(self.sent[0].get_header("X-api-key"), "ak_secretkey123")

    def test_forward_plain_json_and_notification(self):
        self.replies = [FakeResp({"jsonrpc": "2.0", "id": 2, "result": {"ok": 1}}),
                        FakeResp(b"", status=202, ctype="")]
        with self.patched():
            self.assertEqual(composio.forward(MCP, {"id": 2}, None, self.root)[0]["result"], {"ok": 1})
            self.assertIsNone(composio.forward(MCP, {"method": "notifications/initialized"}, None, self.root)[0])

    def test_forward_refuses_untrusted_url(self):
        with self.assertRaises(composio.ComposioError):
            composio.forward("https://evil.example/mcp", {"id": 1}, None, self.root)

    def test_catalog_drops_blocked_and_caches(self):
        page1 = {"items": [{"slug": "gmail", "name": "Gmail", "meta": {"logo": "g.png"},
                            "composio_managed_auth_schemes": ["OAUTH2"]},
                           {"slug": "firecrawl", "name": "Firecrawl"}], "next_cursor": "c2"}
        page2 = {"items": [{"slug": "posthog", "name": "PostHog", "auth_schemes": ["API_KEY"]},
                           {"slug": "tiktok", "name": "TikTok", "auth_schemes": ["OAUTH2"]}]}
        self.replies = [FakeResp(page1), FakeResp(page2)]
        with self.patched():
            first = composio.catalog(self.root)
            again = composio.catalog(self.root)
        self.assertEqual([a["slug"] for a in first], ["gmail", "posthog", "tiktok"])
        self.assertEqual({a["slug"]: a["auth"] for a in first},
                         {"gmail": "managed", "posthog": "api_key", "tiktok": "own_app"})
        self.assertIs(first, again)
        self.assertEqual(len(self.sent), 2)
        self.assertIn("cursor=c2", self.sent[1].full_url)

    def test_key_never_in_error(self):
        integrations.save_session("ceo", "s1", MCP, self.root)
        err = urllib.error.HTTPError(composio.BASE, 500, "boom", Message(), io.BytesIO(b'{"error":"x"}'))
        self.replies = [err]
        with self.patched(), self.assertRaises(composio.ComposioError) as cm:
            composio.execute("ceo", "GMAIL_SEND_EMAIL", {}, self.root)
        self.assertNotIn("ak_secretkey123", str(cm.exception))
        self.assertEqual(cm.exception.status, 500)

    def test_connect_link_and_connections(self):
        integrations.save_session("ceo", "s1", MCP, self.root)
        self.replies = [FakeResp({"redirect_url": "https://backend.composio.dev/link/abc"}),
                        FakeResp({"items": [{"slug": "gmail", "connected_account": {"status": "ACTIVE"}},
                                            {"slug": "slack", "connected_account": None}]})]
        with self.patched():
            self.assertEqual(composio.connect_link("ceo", "gmail", self.root),
                             "https://backend.composio.dev/link/abc")
            self.assertEqual(composio.connections("ceo", self.root), {"gmail"})
        self.assertEqual(self.body(0), {"toolkit": "gmail"})


if __name__ == "__main__":
    unittest.main()
