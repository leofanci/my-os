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


if __name__ == "__main__":
    unittest.main()
