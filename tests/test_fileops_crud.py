import json, sqlite3, tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db


class CrudTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        root = self.root
        proj = root / "projects" / "acme"
        write(proj / "project.md",
              "---\nname: Acme\nkind: venture\npriority: primary\n"
              "status: idea\nhours_per_week: 5\n---\nour voice")
        prof = proj / "profiles" / "demo"
        write(prof / "profile.md", "---\nname: Demo\ntopic: cinema\nproject: acme\n---\nvoice")
        ch = prof / "channels" / "demo-tiktok"
        write(ch / "channel.md", "---\nplatform: tiktok\nhandle: @demo\n---\n")
        write(ch / "guidelines.md", "keep it punchy")
        write(root / "portfolio" / "milestones.json", json.dumps({"milestones": [
            {"id": "ms-1", "title": "Launch", "date": "2026-08-01", "type": "event",
             "entity": "acme", "entity_type": "project"}]}))
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def _con(self):
        return sqlite3.connect(self.root / "database" / "data" / "os.db")

    # ---- project ----------------------------------------------------------- #
    def test_update_project_changes_fields_keeps_slug(self):
        fileops.update_project("acme", {"name": "Acme Inc", "status": "active"})
        ent = db.project("acme")["entity"]
        self.assertEqual(ent["name"], "Acme Inc")
        self.assertEqual(ent["status"], "active")
        # body (voice) preserved
        self.assertIn("our voice", (self.root / "projects/acme/project.md").read_text())

    def test_update_project_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_project("nope", {"name": "X"})

    def test_delete_project_removes_it(self):
        fileops.delete_milestone("ms-1")  # drop the only reference first
        fileops.delete_project("acme")
        self.assertIsNone(db.project("acme"))
        self.assertFalse((self.root / "projects/acme").exists())

    def test_delete_project_refuses_when_referenced(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_project("acme")  # ms-1 still references it
        self.assertTrue((self.root / "projects/acme").exists())

    # ---- channel ----------------------------------------------------------- #
    def test_update_channel_changes_platform_and_handle(self):
        fileops.update_channel("demo-tiktok", {"platform": "instagram", "handle": "@newhandle"})
        self.assertEqual(db.channel("demo-tiktok")["platform"], "instagram")
        self.assertIn("@newhandle", (fileops._channel_dir("demo-tiktok") / "channel.md").read_text())
        # guidelines.md left untouched
        self.assertEqual(fileops.read_channel_guidelines("demo-tiktok"), "keep it punchy")

    def test_update_channel_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_channel("nope", {"platform": "x"})

    # ---- milestone --------------------------------------------------------- #
    def test_update_milestone_changes_title(self):
        fileops.update_milestone("ms-1", {"title": "Big Launch"})
        row = self._con().execute("SELECT title FROM milestones WHERE id='ms-1'").fetchone()
        self.assertEqual(row[0], "Big Launch")

    def test_update_milestone_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_milestone("ms-zzz", {"title": "X"})

    def test_delete_milestone_removes_it(self):
        fileops.delete_milestone("ms-1")
        row = self._con().execute("SELECT title FROM milestones WHERE id='ms-1'").fetchone()
        self.assertIsNone(row)

    def test_delete_milestone_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_milestone("ms-zzz")

    def test_timeline_milestone_carries_ref_id(self):
        ms = [r for r in db.timeline() if r["kind"] == "milestone"]
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0]["ref_id"], "ms-1")


if __name__ == "__main__":
    unittest.main()
