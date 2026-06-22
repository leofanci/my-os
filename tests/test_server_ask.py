import io, unittest
from unittest import mock
import dashboard.server as server


class FakeSession:
    def ask(self, text):
        yield ("delta", "Hi ")
        yield ("delta", "there")
        yield ("done", {"result": "Hi there"})


def _bare_handler(sink):
    """A Handler with the socket-backed I/O stubbed out, writing to `sink`."""
    h = server.Handler.__new__(server.Handler)  # bypass __init__/socket
    h.wfile = sink
    h.send_response = h.send_header = h.end_headers = lambda *a, **k: None
    return h


def _captured_prompt(body, tree=None):
    """Run _handle_ask with a session that records the prompt; return that prompt."""
    seen = {}

    class CaptureSession:
        def ask(self, text):
            seen["text"] = text
            yield ("done", {"result": "ok"})

    h = _bare_handler(io.BytesIO())
    with mock.patch.object(server, "get_chat_session", return_value=CaptureSession()), \
         mock.patch.object(server.db, "tree", return_value=tree or []):
        h._handle_ask(body)
    return seen["text"]


class SSE(unittest.TestCase):
    def test_handle_ask_streams_sse(self):
        sink = io.BytesIO()
        h = _bare_handler(sink)
        with mock.patch.object(server, "get_chat_session", return_value=FakeSession()):
            h._handle_ask({"messages": [{"role": "user", "content": "hi"}]})
        out = sink.getvalue().decode()
        self.assertIn('data: {"delta": "Hi "}', out)
        self.assertIn('data: [DONE]', out)
        self.assertLess(out.index('"delta": "Hi "'), out.index("[DONE]"))

    def test_handle_ask_prepends_state_snapshot(self):
        tree = [{"slug": "acme", "kind": "brand", "type": "project",
                 "profiles": [{"slug": "demo", "name": "Demo Brand",
                               "channels": [{"slug": "demo-tiktok", "name": "TikTok",
                                             "platform": "tiktok"}]}]}]
        text = _captured_prompt({"messages": [{"role": "user", "content": "do a thing"}]}, tree)
        self.assertIn("## Current GTM OS state", text)
        self.assertIn("acme (brand)", text)
        self.assertIn("## Request\ndo a thing", text)

    def test_handle_ask_includes_client_context(self):
        ctx = "Current view: Profiles · Demo\n## Attached files\n### plan.md\n```\nhello\n```"
        text = _captured_prompt({"messages": [{"role": "user", "content": "summarize"}],
                                 "context": ctx})
        # the client-supplied context (current view + attached file contents)
        # must reach the agent, ahead of the request itself
        self.assertIn("### plan.md", text)
        self.assertIn("Current view: Profiles · Demo", text)
        self.assertLess(text.index("### plan.md"), text.index("## Request\nsummarize"))

    def test_handle_ask_without_context_still_works(self):
        text = _captured_prompt({"messages": [{"role": "user", "content": "hi"}]})
        self.assertIn("## Request\nhi", text)


class StateSnapshot(unittest.TestCase):
    def test_empty_tree(self):
        out = server.state_snapshot([])
        self.assertEqual(out, "## Current GTM OS state\n(no projects yet)")

    def test_nested_outline(self):
        tree = [{"slug": "acme", "kind": "brand", "type": "project",
                 "profiles": [{"slug": "demo", "name": "Demo Brand",
                               "channels": [
                                   {"slug": "demo-tiktok", "name": "TikTok", "platform": "tiktok"},
                                   {"slug": "demo-ig", "name": "Instagram", "platform": "instagram"},
                               ]}]}]
        out = server.state_snapshot(tree)
        self.assertIn("acme (brand)", out)
        self.assertIn('  profile demo "Demo Brand"', out)
        self.assertIn("    channel demo-tiktok (tiktok)", out)
        self.assertIn("    channel demo-ig (instagram)", out)

    def test_project_no_profiles_and_profile_no_channels(self):
        tree = [{"slug": "solo", "type": "project", "profiles": []},
                {"slug": "p2", "kind": "venture", "type": "project",
                 "profiles": [{"slug": "prof", "name": "Prof", "channels": []}]}]
        out = server.state_snapshot(tree)
        self.assertIn("solo (project)", out)        # falls back to type when no kind
        self.assertIn('  profile prof "Prof"', out)
        self.assertNotIn("channel", out)


if __name__ == "__main__":
    unittest.main()
