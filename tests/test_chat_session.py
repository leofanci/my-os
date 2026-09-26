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

    def test_session_meta_and_skill_tracking(self):
        sess = cs.ChatSession(repo_dir=self.tmp.name, rail="RAIL", claude_bin=self.stub)
        self.assertTrue(sess.is_fresh())
        sess.note_skill("workspace")
        list(sess.ask("hi"))
        self.assertEqual(sess._turn_count, 1)
        self.assertEqual(sess._last_skill, "workspace")
        self.assertFalse(sess.is_fresh())
        meta = sess.session_meta()
        self.assertEqual(meta["turn_count"], 1)

    def test_linked_workspace_tools_are_loaded_only_when_needed(self):
        sess = cs.ChatSession(repo_dir=self.tmp.name, rail="RAIL", claude_bin=self.stub)
        ordinary = sess._base_cmd()
        linked = sess._base_cmd(workspace_dir="/tmp/My App", file_search_mode=True)
        graph = sess._base_cmd(workspace_dir="/tmp/My App")

        ordinary_tools = ordinary[ordinary.index("--tools") + 1:ordinary.index("--allowedTools")]
        linked_tools = linked[linked.index("--tools") + 1:linked.index("--allowedTools")]
        ordinary_allowed = ordinary[ordinary.index("--allowedTools") + 1:
                                    ordinary.index("--strict-mcp-config")]
        linked_allowed = linked[linked.index("--allowedTools") + 1:
                                linked.index("--strict-mcp-config")]
        graph_allowed = graph[graph.index("--allowedTools") + 1:
                              graph.index("--strict-mcp-config")]
        self.assertNotIn("Glob", ordinary_tools)
        self.assertNotIn("Grep", ordinary_tools)
        self.assertNotIn("--add-dir", ordinary)
        self.assertIn("Glob", linked_tools)
        self.assertIn("Grep", linked_tools)
        self.assertNotIn("Glob", ordinary_allowed)
        self.assertIn("Glob", linked_allowed)
        self.assertFalse(any("tokensave_bridge" in item for item in ordinary_allowed))
        self.assertFalse(any("tokensave_bridge" in item for item in linked_allowed))
        self.assertFalse(any("tokensave_bridge" in item for item in graph_allowed))
        self.assertEqual(linked[linked.index("--add-dir") + 1], "/tmp/My App")
        self.assertNotIn("Glob", graph[graph.index("--tools") + 1:
                                       graph.index("--allowedTools")])
        self.assertNotIn("--add-dir", graph)
        self.assertIn("--restricted", ordinary)
        self.assertIn("--restricted", linked)


class WebAndSecretPolicy(unittest.TestCase):
    def test_user_web_domains_only_takes_typed_hosts(self):
        got = cs.user_web_domains(
            "see https://www.acme.example/x and demo.example; not notes.md, app.py or a@example.com")
        self.assertEqual(got, ["acme.example", "demo.example"])

    def test_webfetch_scoped_to_typed_domains(self):
        sess = cs.ChatSession(repo_dir=".", rail="R")
        cmd = sess._base_cmd(with_web=True, web_domains=["acme.example"])
        allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
        self.assertIn("WebSearch", allowed)
        self.assertNotIn("WebFetch", allowed)
        self.assertIn("WebFetch(domain:acme.example)", allowed)
        self.assertFalse([a for a in sess._base_cmd(with_web=True)
                          if a.startswith("WebFetch(")])

    def test_secret_files_denied_in_repo_and_linked_folder(self):
        sess = cs.ChatSession(repo_dir=".", rail="R")
        cmd = sess._base_cmd(workspace_dir="/tmp/app", file_search_mode=True)
        denied = cmd[cmd.index("--disallowedTools") + 1:cmd.index("--strict-mcp-config")]
        self.assertIn("Read(**/.env)", denied)
        self.assertIn("Read(//tmp/app/**/.env)", denied)


if __name__ == "__main__":
    unittest.main()
