import json, tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db

class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        prof = root / "projects" / "acme" / "profiles" / "demo"
        write(root / "projects" / "acme" / "project.md", "---\nname: Acme\n---")
        write(prof / "profile.md", "---\nname: Demo\n---")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---rules")
        (prof / "content").mkdir(parents=True, exist_ok=True)
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_crud(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        posts = db.profile_posts("demo")
        self.assertEqual(len(posts), 1)
        pid = posts[0]["id"]
        self.assertEqual(posts[0]["channels"], ["demo-tiktok"])
        fileops.update_post(pid, {"pillar": "curiosity"})
        fileops.delete_post(pid)
        self.assertEqual(db.profile_posts("demo"), [])

    def test_working_title_and_concept_surface(self):
        fileops.add_post("demo", {"working_title": "Idea A",
                                  "concept": "why this now", "channels": "demo-tiktok"})
        post = db.profile_posts("demo")[0]
        self.assertEqual(post["working_title"], "Idea A")
        self.assertEqual(post["concept"], "why this now")

    def test_delete_works_at_scheduled_stage(self):
        # Deletion must work at any phase, not just on fresh ideas.
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved", "scheduled"):
            fileops.set_status(pid, to)
        self.assertEqual(db.profile_posts("demo")[0]["status"], "scheduled")
        fileops.delete_post(pid)
        self.assertEqual(db.profile_posts("demo"), [])

    def test_brief_spec_roundtrip(self):
        fileops.update_profile("demo", {"name": "Demo", "brief_spec": "Captions under 100 words."})
        self.assertEqual(fileops.read_profile("demo")["brief_spec"].strip(),
                         "Captions under 100 words.")

    def test_brief_file_reconciles_status_for_review(self):
        # A brief written directly (batch/terminal) leaves status at 'planned'
        # but the UI shows it as a Draft and offers "Review →" (briefed->approved).
        # set_status must reconcile, not raise an illegal-transition error.
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        briefs = fileops.find_post(pid)["plan"].parent / "briefs"
        briefs.mkdir(parents=True, exist_ok=True)
        (briefs / f"{pid}.json").write_text(json.dumps({"id": pid}), encoding="utf-8")
        fileops.set_status(pid, "approved")  # must not raise
        self.assertEqual(db.profile_posts("demo")[0]["status"], "approved")

    def test_bulk_delete(self):
        for name in ("A", "B", "C"):
            fileops.add_post("demo", {"working_title": name, "channels": "demo-tiktok"})
        ids = [p["id"] for p in db.profile_posts("demo")]
        # give one a brief file so we confirm it's removed too
        briefs = fileops.find_post(ids[0])["plan"].parent / "briefs"
        briefs.mkdir(parents=True, exist_ok=True)
        (briefs / f"{ids[0]}.json").write_text("{}", encoding="utf-8")
        res = fileops.delete_posts([ids[0], ids[1], "does-not-exist"])
        self.assertEqual(res["count"], 2)
        left = [p["id"] for p in db.profile_posts("demo")]
        self.assertEqual(left, [ids[2]])
        self.assertFalse((briefs / f"{ids[0]}.json").exists())

    def test_add_unknown_profile(self):
        with self.assertRaises(fileops.ActionError):
            fileops.add_post("nope", {})

if __name__ == "__main__":
    unittest.main()
