"""Rooms (Slack channels + DMs): listing, topic CRUD, thread placement, routing."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import bots, rooms
import dashboard.server as server

PROJECTS = [{"slug": "acme", "name": "Acme"}, {"slug": "demo", "name": "Demo"}]


class Rooms(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ids(self):
        return [r["id"] for r in rooms.list_rooms(bots.team(self.root), PROJECTS, self.root)]

    def test_default_rooms(self):
        ids = self.ids()
        self.assertEqual(ids[:3], ["hq", "p-acme", "p-demo"])
        self.assertIn("dm-cmo", ids)

    def test_topic_crud(self):
        rid = rooms.save_topic("acme-launch", "acme", ["gtm", "social"], "gtm", PROJECTS, self.root)
        room = rooms.get_room(rid, bots.team(self.root), PROJECTS, self.root)
        self.assertEqual((room["project"], room["lead"], room["members"]), ("acme", "gtm", ["gtm", "social"]))
        rooms.save_topic("launch", None, ["cmo"], "cos", PROJECTS, self.root, replace="acme-launch")
        room = rooms.get_room("t-launch", bots.team(self.root), PROJECTS, self.root)
        self.assertEqual((room["project"], room["members"]), (None, ["cos", "cmo"]))
        rooms.delete_topic("launch", self.root)
        self.assertNotIn("t-launch", self.ids())

    def test_topic_validation(self):
        for name, project, lead in (("Bad Name", None, "cos"), ("acme", None, "cos"),
                                    ("hq", None, "cos"), ("x", "nope", "cos"), ("x", None, "nobody")):
            with self.assertRaises(ValueError):
                rooms.save_topic(name, project, [], lead, PROJECTS, self.root)
        rooms.save_topic("x", None, [], "cos", PROJECTS, self.root)
        with self.assertRaises(ValueError):
            rooms.save_topic("x", None, [], "cos", PROJECTS, self.root)

    def test_switched_off_lead_resolves_to_manager(self):
        rooms.save_topic("posts", "acme", ["social"], "social", PROJECTS, self.root)
        bots.set_active("social", False, self.root)
        room = rooms.get_room("t-posts", bots.team(self.root), PROJECTS, self.root)
        self.assertEqual(room["lead"], "cmo")
        self.assertNotIn("dm-social", self.ids())

    def test_old_and_orphan_threads_find_a_room(self):
        ids = set(self.ids())
        self.assertEqual(rooms.room_of_chat({"scope": ["acme", ""]}, ids), "p-acme")
        self.assertEqual(rooms.room_of_chat({"room": "t-gone", "scope": None}, ids), "hq")
        self.assertEqual(rooms.room_of_chat({"room": "dm-cmo"}, ids), "dm-cmo")


class RoomRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.team = bots.team(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def _sess(self, last_bot=None):
        class S:
            _last_skill = None
            _skill_explicit = False
        s = S()
        s._last_bot = last_bot
        return s

    def test_untagged_goes_to_room_lead(self):
        r = server._route_bot(self.team, "ideas for the launch?", self._sess(), default_bot="gtm")
        self.assertEqual(r[0], "gtm")

    def test_dm_ignores_last_speaker(self):
        r = server._route_bot(self.team, "and pricing?", self._sess("research"),
                              default_bot="cmo", sticky=False)
        self.assertEqual(r[0], "cmo")

    def test_project_room_forces_project_and_members_trim_roster(self):
        tmp = Path(self.tmp.name)
        rooms.save_topic("launch", "acme", ["gtm", "social"], "gtm", PROJECTS, tmp)
        sink = io.BytesIO()
        h = server.Handler.__new__(server.Handler)
        h.wfile = sink
        h.send_response = h.send_header = h.end_headers = lambda *a, **k: None
        seen = {}

        class S:
            _started = False
            _turn_count = 0
            _last_skill = None
            _skill_explicit = False
            _last_bot = None
            session_id = None

            def is_fresh(self):
                return True

            def note_skill(self, *a, **k):
                pass

            def note_bot(self, bot_id):
                seen["bot"] = bot_id

            def ask(self, text, **kw):
                seen["text"] = text
                yield ("done", {})

        def fake_session(scope, *a, **k):
            seen["scope"] = scope
            return S()

        tree = [dict(p, local_folder="", profiles=[], products=[]) for p in PROJECTS]
        with mock.patch.object(server, "ROOT", tmp), \
                mock.patch.object(server.db, "tree", return_value=tree), \
                mock.patch.object(server, "get_chat_session", side_effect=fake_session), \
                mock.patch.object(server, "state_snapshot", return_value=""):
            h._handle_ask({"messages": [{"role": "user", "content": "what next?"}],
                           "room_id": "t-launch", "project_slug": "demo"})
        self.assertEqual(seen["scope"][0], "acme")
        self.assertEqual(seen["bot"], "gtm")
        self.assertIn("@social", seen["text"])
        self.assertNotIn("@cmo", seen["text"])


if __name__ == "__main__":
    unittest.main()
