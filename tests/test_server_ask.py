import io, unittest
from unittest import mock
import dashboard.server as server


class FakeSession:
    def ask(self, text):
        yield ("delta", "Hi ")
        yield ("delta", "there")
        yield ("done", {"result": "Hi there"})


class SSE(unittest.TestCase):
    def test_handle_ask_streams_sse(self):
        h = server.Handler.__new__(server.Handler)  # bypass __init__/socket
        sink = io.BytesIO()
        h.wfile = sink
        h.send_response = lambda *a, **k: None
        h.send_header = lambda *a, **k: None
        h.end_headers = lambda *a, **k: None
        with mock.patch.object(server, "get_chat_session", return_value=FakeSession()):
            h._handle_ask({"messages": [{"role": "user", "content": "hi"}]})
        out = sink.getvalue().decode()
        self.assertIn('data: {"delta": "Hi "}', out)
        self.assertIn('data: [DONE]', out)
        self.assertLess(out.index('"delta": "Hi "'), out.index("[DONE]"))

    def test_handle_ask_prepends_state_snapshot(self):
        h = server.Handler.__new__(server.Handler)
        sink = io.BytesIO()
        h.wfile = sink
        h.send_response = lambda *a, **k: None
        h.send_header = lambda *a, **k: None
        h.end_headers = lambda *a, **k: None
        seen = {}

        class CaptureSession:
            def ask(self, text):
                seen["text"] = text
                yield ("done", {"result": "ok"})

        tree = [{"slug": "acme", "kind": "brand", "type": "project",
                 "profiles": [{"slug": "demo", "name": "Demo Brand",
                               "channels": [{"slug": "mt-tiktok", "name": "TikTok",
                                             "platform": "tiktok"}]}]}]
        with mock.patch.object(server, "get_chat_session", return_value=CaptureSession()), \
             mock.patch.object(server.db, "tree", return_value=tree):
            h._handle_ask({"messages": [{"role": "user", "content": "do a thing"}]})
        self.assertIn("## Current GTM OS state", seen["text"])
        self.assertIn("acme (brand)", seen["text"])
        self.assertIn("## Request\ndo a thing", seen["text"])


class StateSnapshot(unittest.TestCase):
    def test_empty_tree(self):
        out = server.state_snapshot([])
        self.assertEqual(out, "## Current GTM OS state\n(no projects yet)")

    def test_nested_outline(self):
        tree = [{"slug": "acme", "kind": "brand", "type": "project",
                 "profiles": [{"slug": "demo", "name": "Demo Brand",
                               "channels": [
                                   {"slug": "mt-tiktok", "name": "TikTok", "platform": "tiktok"},
                                   {"slug": "mt-ig", "name": "Instagram", "platform": "instagram"},
                               ]}]}]
        out = server.state_snapshot(tree)
        self.assertIn("acme (brand)", out)
        self.assertIn('  profile demo "Demo Brand"', out)
        self.assertIn("    channel mt-tiktok (tiktok)", out)
        self.assertIn("    channel mt-ig (instagram)", out)

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
