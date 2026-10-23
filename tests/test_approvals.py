"""Step 2: approvals inbox, usage/cost capture, editable bot memory."""
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core import approvals, bots
import dashboard.chat_session as chat_session
import dashboard.server as server


class Marker(unittest.TestCase):
    def test_extract(self):
        clean, s = approvals.extract("Plan:\n- memo to sec04\n\n**APPROVAL:** save positioning memo to sec04")
        self.assertEqual(s, "save positioning memo to sec04")
        self.assertEqual(clean, "Plan:\n- memo to sec04")
        self.assertEqual(approvals.extract("no marker here"), ("no marker here", None))
        self.assertEqual(approvals.extract("APPROVAL: a\nAPPROVAL: b")[1], "b")


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, ws, chat, summary="x"):
        return approvals.add(self.root, ws=ws, room=f"{ws}/general", chat=chat, bot="cmo", summary=summary)

    def test_pending_per_workspace_and_hq_sees_all(self):
        self.add("acme", "c1")
        self.add("demo", "c2")
        self.assertEqual([a["chat"] for a in approvals.pending(self.root, "acme")], ["c1"])
        self.assertEqual(len(approvals.pending(self.root, "hq")), 2)

    def test_new_proposal_supersedes_and_answer_resolves(self):
        self.add("acme", "c1", "first")
        self.add("acme", "c1", "second")
        self.assertEqual([a["summary"] for a in approvals.pending(self.root)], ["second"])
        self.assertEqual(approvals.resolve_chat("c1", "approved", self.root), 1)
        self.assertEqual(approvals.pending(self.root), [])
        self.assertEqual(approvals.load(self.root)[-1]["status"], "approved")


class Usage(unittest.TestCase):
    def test_result_event_carries_tokens_and_cost(self):
        kind, p = chat_session.parse_event({
            "type": "result", "result": "ok", "subtype": "success", "total_cost_usd": 0.0123,
            "usage": {"input_tokens": 10, "cache_read_input_tokens": 1000,
                      "cache_creation_input_tokens": 200, "output_tokens": 90}})
        self.assertEqual((kind, p["tokens"], p["cost"]), ("done", 1300, 0.0123))


class Turn(unittest.TestCase):
    """A proposing reply becomes an approval; the next message in the thread closes it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "projects" / "acme").mkdir(parents=True)
        self.tree = [{"slug": "acme", "name": "Acme", "kind": "venture", "type": "project",
                      "local_folder": None, "profiles": [], "products": []}]
        self._chats = server.chat_store.CHATS_DIR   # the server's own module copy
        server.chat_store.CHATS_DIR = self.root / "chats"

    def tearDown(self):
        server.chat_store.CHATS_DIR = self._chats
        self.tmp.cleanup()

    def ask(self, msg, reply, **body):
        sink = io.BytesIO()
        h = server.Handler.__new__(server.Handler)
        h.wfile = sink
        h.send_response = h.send_header = h.end_headers = lambda *a, **k: None

        class S:
            _started = True
            _turn_count = 1
            _last_skill = None
            _skill_explicit = False
            _last_bot = None
            session_id = "0" * 8 + "-0000-0000-0000-" + "0" * 12

            def is_fresh(self):
                return False

            def note_skill(self, *a, **k):
                pass

            def note_bot(self, *a):
                pass

            def ask(self, text, **kw):
                yield ("delta", reply)
                yield ("done", {"tokens": 1500, "cost": 0.02})

        with mock.patch.object(server, "ROOT", self.root), \
                mock.patch.object(server.db, "tree", return_value=self.tree), \
                mock.patch.object(server, "get_chat_session", return_value=S()):
            h._handle_ask({"messages": [{"role": "user", "content": msg}],
                           "room_id": "acme/general", "chat_id": S.session_id, **body})
        return sink.getvalue().decode(), server.chat_store.load(S.session_id)

    def test_approval_flow_and_usage(self):
        out, rec = self.ask("@cmo positioning for acme", "Two options.\nAPPROVAL: save positioning memo to sec04")
        self.assertIn('"approval"', out)
        self.assertIn('"usage"', out)
        last = rec["messages"][-1]
        self.assertEqual(last["content"], "Two options.")
        self.assertEqual((last["tokens"], last["cost"], last["bot"]), (1500, 0.02, "cmo"))
        pend = approvals.pending(self.root, "acme")
        self.assertEqual(pend[0]["summary"], "save positioning memo to sec04")
        self.assertEqual(last["approval"], pend[0]["id"])
        self.ask("Yes, approved.", "Saved.", approval="approved")
        self.assertEqual(approvals.pending(self.root), [])
        self.assertEqual(approvals.load(self.root)[-1]["status"], "approved")
        costs = server._costs("acme", self.tree)
        self.assertEqual(costs["bots"]["cmo"]["turns"], 1)
        self.assertEqual(costs["total"]["turns"], 2)
        self.assertAlmostEqual(costs["total"]["cost"], 0.04)
        self.assertEqual(server._costs("hq", self.tree)["total"]["tokens"], 3000)


class Memory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "projects" / "acme").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_forget_removes_one_line(self):
        bots.remember("cmo", "B2B only", "acme", self.root)
        bots.remember("cmo", "premium tier", "acme", self.root)
        line = bots.read_memory("cmo", "acme", self.root, tail=0).splitlines()[0]
        self.assertTrue(bots.forget("cmo", line, "acme", self.root))
        self.assertFalse(bots.forget("cmo", line, "acme", self.root))
        self.assertNotIn("B2B only", bots.read_memory("cmo", "acme", self.root))
        self.assertIn("premium tier", bots.read_memory("cmo", "acme", self.root))


if __name__ == "__main__":
    unittest.main()
