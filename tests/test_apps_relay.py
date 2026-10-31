"""The connected-apps relay: turn tokens, method allowlist, tool filter, read/hold/refuse gate."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import approvals, composio, integrations
from dashboard import apps_relay

CAT = ["gmail", "googlecalendar", "googledrive", "instagram"]
CTX = {"ws": "hq", "bot": "cos", "chat": "c1", "room": "hq/general", "person": "ceo"}


class FakeUpstream:
    def __init__(self, result=None):
        self.frames = []
        self.result = result if result is not None else {"content": [{"type": "text", "text": "upstream ok"}]}

    def forward(self, frame, mcp_session_id):
        self.frames.append(frame)
        if frame.get("method", "").startswith("notifications/"):
            return None, "m-1"
        return {"jsonrpc": "2.0", "id": frame.get("id"), "result": self.result}, "m-1"


def call(name, arguments, rid=7):
    return {"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def multi(*items):
    return call("COMPOSIO_MULTI_EXECUTE_TOOL", {"tools": list(items)})


def text_of(reply):
    return "\n".join(c.get("text", "") for c in reply["result"]["content"])


class Tokens(unittest.TestCase):
    def test_token_lifecycle(self):
        toks = apps_relay.Tokens()
        t = toks.mint(dict(CTX))
        self.assertEqual(len(t), 64)
        self.assertEqual(toks.lookup(t)["bot"], "cos")
        self.assertIsNone(toks.lookup("wrong"))
        self.assertIsNone(toks.lookup(""))
        toks.revoke(t)
        self.assertIsNone(toks.lookup(t))
        t2 = toks.mint(dict(CTX))
        with mock.patch("dashboard.apps_relay.time.time", return_value=apps_relay.time.time() + apps_relay.MAX_AGE + 1):
            self.assertIsNone(toks.lookup(t2))


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        integrations.set_grant("hq", "cos", {"gmail": "write", "googledrive": "read"}, self.root)
        self.up = FakeUpstream()

    def tearDown(self):
        self.tmp.cleanup()

    def handle(self, frame):
        reply, _ = apps_relay.handle(frame, CTX, None, self.up, self.root, catalog=CAT)
        return reply

    def test_methods_allowlist(self):
        self.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertIsNone(self.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(len(self.up.frames), 2)
        bad = self.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        self.assertIn("error", bad)
        self.assertEqual(len(self.up.frames), 2)

    def test_tools_list_filtered(self):
        names = ["COMPOSIO_SEARCH_TOOLS", "COMPOSIO_GET_TOOL_SCHEMAS", "COMPOSIO_MULTI_EXECUTE_TOOL",
                 "COMPOSIO_MANAGE_CONNECTIONS", "COMPOSIO_WAIT_FOR_CONNECTIONS", "COMPOSIO_REMOTE_WORKBENCH",
                 "COMPOSIO_REMOTE_BASH_TOOL", "COMPOSIO_PROXY_EXECUTE"]
        self.up.result = {"tools": [{"name": n} for n in names]}
        reply = self.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual([t["name"] for t in reply["result"]["tools"]],
                         ["COMPOSIO_SEARCH_TOOLS", "COMPOSIO_GET_TOOL_SCHEMAS", "COMPOSIO_MULTI_EXECUTE_TOOL"])

    def test_search_and_schema_pass_through(self):
        f = call("COMPOSIO_SEARCH_TOOLS", {"queries": [{"use_case": "read inbox"}]})
        self.handle(f)
        self.assertEqual(self.up.frames[-1], f)

    def test_pass_through_rebuilt_from_name_and_arguments_only(self):
        # Like a read: no extra fields (_meta, task hints, ...) reach Composio.
        args = {"queries": [{"use_case": "read inbox"}]}
        f = call("COMPOSIO_SEARCH_TOOLS", args)
        f["params"]["_meta"] = {"progressToken": 1}
        f["extra"] = True
        self.handle(f)
        self.assertEqual(self.up.frames[-1], call("COMPOSIO_SEARCH_TOOLS", args))

    def test_read_forwarded_rebuilt(self):
        read = {"tool_slug": "GMAIL_FETCH_EMAILS", "arguments": {"max_results": 5}}
        f = multi(read)
        f["params"]["arguments"]["sync_response_to_workbench"] = True
        reply = self.handle(f)
        self.assertEqual(self.up.frames[-1]["params"]["arguments"], {"tools": [read]})
        self.assertIn("upstream ok", text_of(reply))

    def test_write_held_not_forwarded(self):
        reply = self.handle(multi({"tool_slug": "GMAIL_SEND_EMAIL",
                                   "arguments": {"recipient_email": "a@example.com", "body": "hi"}}))
        self.assertEqual(self.up.frames, [])
        rows = approvals.pending(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["kind"], rows[0]["bot"], rows[0]["ws"], rows[0]["chat"]),
                         ("app_action", "cos", "hq", "c1"))
        self.assertEqual(rows[0]["action"]["arguments"]["body"], "hi")
        self.assertEqual(text_of(reply), f"Held for approval ({rows[0]['id']}): Send email. It has not run. "
                                         "Tell the user it is waiting in Approvals.")

    def test_mixed_call(self):
        reply = self.handle(multi({"tool_slug": "GMAIL_FETCH_EMAILS", "arguments": {}},
                                  {"tool_slug": "GMAIL_SEND_EMAIL", "arguments": {"recipient_email": "a@example.com"}}))
        self.assertEqual([t["tool_slug"] for t in self.up.frames[-1]["params"]["arguments"]["tools"]],
                         ["GMAIL_FETCH_EMAILS"])
        out = text_of(reply)
        self.assertIn("upstream ok", out)
        self.assertIn("Held for approval", out)

    def test_ungranted_and_blocked_refused(self):
        for slug in ("INSTAGRAM_GET_USER_INFO", "FIRECRAWL_SCRAPE", "NOPE_DO_IT"):
            reply = self.handle(multi({"tool_slug": slug, "arguments": {}}))
            self.assertEqual(text_of(reply), f'"{slug}" is not available to this bot. This call was not performed.')
        self.assertEqual(self.up.frames, [])
        self.assertEqual(approvals.pending(self.root), [])

    def test_read_grant_refuses_write(self):
        reply = self.handle(multi({"tool_slug": "GOOGLEDRIVE_UPLOAD_FILE", "arguments": {}}))
        self.assertIn("not available", text_of(reply))
        self.assertEqual(approvals.pending(self.root), [])

    def test_hidden_meta_tool_refused(self):
        for name in ("COMPOSIO_REMOTE_BASH_TOOL", "COMPOSIO_MANAGE_CONNECTIONS", "GMAIL_SEND_EMAIL"):
            reply = self.handle(call(name, {}))
            self.assertIn("not available", text_of(reply))
        self.assertEqual(self.up.frames, [])

    def test_malformed_multi_execute_refused(self):
        reply = self.handle(call("COMPOSIO_MULTI_EXECUTE_TOOL", {"tools": [{"arguments": {}}]}))
        self.assertIn("not performed", text_of(reply))
        self.assertEqual(self.up.frames, [])

    def test_grant_reread_each_call(self):
        integrations.set_grant("hq", "cos", {}, self.root)
        reply = self.handle(multi({"tool_slug": "GMAIL_FETCH_EMAILS", "arguments": {}}))
        self.assertIn("not available", text_of(reply))


class ComposioUpstreamRetry(unittest.TestCase):
    def test_resets_session_once_on_404(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        self.addCleanup(tmp.cleanup)
        sessions = iter([{"session_id": "s1", "mcp_url": "u1"}, {"session_id": "s2", "mcp_url": "u2"}])
        seen = []

        def fwd(url, frame, sid, r):
            seen.append(url)
            if url == "u1":
                raise composio.ComposioError("gone", status=404)
            return {"result": {}}, None
        with mock.patch.object(composio, "ensure_session", side_effect=lambda p, r: next(sessions)), \
                mock.patch.object(composio, "reset_session") as reset, \
                mock.patch.object(composio, "forward", side_effect=fwd):
            reply, _ = apps_relay.ComposioUpstream("ceo", root).forward({"id": 1}, None)
        self.assertEqual(seen, ["u1", "u2"])
        reset.assert_called_once()
        self.assertEqual(reply, {"result": {}})


if __name__ == "__main__":
    unittest.main()
