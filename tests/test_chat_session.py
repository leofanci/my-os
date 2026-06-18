import os, stat, tempfile, textwrap, unittest
from pathlib import Path
import dashboard.chat_session as cs


class ParseEvent(unittest.TestCase):
    def test_text_delta(self):
        ev = {"type": "stream_event",
              "event": {"type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": "Hello"}}}
        self.assertEqual(cs.parse_event(ev), ("delta", "Hello"))

    def test_tool_use_start(self):
        ev = {"type": "stream_event",
              "event": {"type": "content_block_start",
                        "content_block": {"type": "tool_use", "name": "Bash"}}}
        self.assertEqual(cs.parse_event(ev), ("tool", "Bash"))

    def test_result(self):
        ev = {"type": "result", "subtype": "success", "result": "done"}
        kind, payload = cs.parse_event(ev)
        self.assertEqual(kind, "done")

    def test_ignored(self):
        self.assertEqual(cs.parse_event({"type": "system"}), (None, None))


class AskWithStub(unittest.TestCase):
    """Drive ChatSession against a fake `claude` that emits stream-json."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        stub = Path(self.tmp.name) / "fakeclaude"
        stub.write_text(textwrap.dedent('''\
            #!/usr/bin/env python3
            import sys, json
            sys.stdin.readline()  # consume the user turn
            for t in ["He", "llo"]:
                print(json.dumps({"type":"stream_event","event":{
                    "type":"content_block_delta",
                    "delta":{"type":"text_delta","text":t}}}), flush=True)
            print(json.dumps({"type":"result","subtype":"success","result":"Hello"}), flush=True)
        '''))
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.stub = str(stub)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ask_streams_then_done(self):
        sess = cs.ChatSession(repo_dir=self.tmp.name, rail="RAIL", claude_bin=self.stub)
        events = list(sess.ask("hi"))
        deltas = "".join(p for k, p in events if k == "delta")
        self.assertEqual(deltas, "Hello")
        self.assertTrue(any(k == "done" for k, _ in events))


if __name__ == "__main__":
    unittest.main()
