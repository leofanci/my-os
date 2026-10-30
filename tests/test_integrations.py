"""Connected apps store: write-only Composio key, per-person sessions, per-bot grants."""
import json
import tempfile
import unittest
from pathlib import Path

from core import integrations


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_key_write_only(self):
        integrations.set_key("ak_testkey", self.root)
        pub = integrations.public(self.root)
        self.assertTrue(pub["configured"])
        self.assertIsInstance(pub["saved"], float)
        self.assertNotIn("ak_testkey", json.dumps(pub))
        self.assertEqual(integrations.api_key(self.root), "ak_testkey")

    def test_unconfigured(self):
        self.assertEqual(integrations.public(self.root), {"configured": False, "saved": None})
        self.assertIsNone(integrations.api_key(self.root))

    def test_empty_key_rejected(self):
        for bad in ("", "   ", None):
            with self.assertRaises(ValueError):
                integrations.set_key(bad, self.root)

    def test_file_mode_0600(self):
        integrations.set_key("ak_testkey", self.root)
        path = self.root / "team" / "integrations.json"
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")

    def test_person_id_random_and_stable(self):
        a = integrations.person("ceo", self.root)["composio_user_id"]
        self.assertTrue(a.startswith("myos-"))
        self.assertNotIn("ceo", a)
        self.assertEqual(integrations.person("ceo", self.root)["composio_user_id"], a)

    def test_save_session(self):
        integrations.save_session("ceo", "sess1", "https://mcp.acme.example/x", self.root)
        row = integrations.person("ceo", self.root)
        self.assertEqual((row["session_id"], row["mcp_url"]), ("sess1", "https://mcp.acme.example/x"))

    def test_default_and_explicit_empty_grant(self):
        self.assertEqual(integrations.grant("hq", "cos", self.root),
                         {"gmail": "write", "googlecalendar": "write"})
        self.assertEqual(integrations.grant("acme", "cos", self.root), {})
        self.assertEqual(integrations.grant("hq", "cmo", self.root), {})
        integrations.set_grant("hq", "cos", {}, self.root)
        self.assertEqual(integrations.grant("hq", "cos", self.root), {})

    def test_set_grant_round_trip(self):
        integrations.set_grant("acme", "social", {"instagram": "write", "googledrive": "read"}, self.root)
        self.assertEqual(integrations.grant("acme", "social", self.root),
                         {"instagram": "write", "googledrive": "read"})

    def test_set_grant_validates(self):
        for bad in ({"firecrawl": "write"}, {"gmail": "all"}, {"Bad Slug": "read"}, ["gmail"]):
            with self.assertRaises(ValueError):
                integrations.set_grant("hq", "cos", bad, self.root)

    def test_remove_key_drops_sessions_keeps_grants(self):
        integrations.set_key("ak_testkey", self.root)
        integrations.save_session("ceo", "sess1", "https://mcp.acme.example/x", self.root)
        integrations.set_grant("acme", "social", {"instagram": "read"}, self.root)
        integrations.remove_key(self.root)
        self.assertIsNone(integrations.api_key(self.root))
        self.assertNotIn("session_id", integrations.person("ceo", self.root))
        self.assertEqual(integrations.grant("acme", "social", self.root), {"instagram": "read"})


if __name__ == "__main__":
    unittest.main()
