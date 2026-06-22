import io, json, tempfile, unittest, contextlib
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db
import dashboard.osctl as osctl


def run(argv):
    """Invoke osctl.main, capture the single JSON line it prints."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = osctl.main(argv)
    line = buf.getvalue().strip().splitlines()[-1]
    return code, json.loads(line)


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        fileops.ROOT = self.root
        db.DB_PATH = self.root / "database" / "data" / "os.db"
        # minimal indexable workspace
        write(self.root / "projects" / ".keep", "")
        index.build(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_project_ok(self):
        code, out = run(["create-project", "--slug", "acme", "--name", "Acme"])
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["slug"], "acme")
        self.assertTrue((self.root / "projects" / "acme" / "project.md").exists())

    def test_create_project_duplicate_errors(self):
        run(["create-project", "--slug", "dup"])
        code, out = run(["create-project", "--slug", "dup"])
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertIn("already exists", out["error"])

    def test_create_profile_and_channel_and_post(self):
        run(["create-project", "--slug", "acme", "--name", "Acme"])
        c, out = run(["create-profile", "--project", "acme",
                      "--slug", "demo", "--name", "Demo"])
        self.assertEqual(c, 0); self.assertTrue(out["ok"])
        self.assertTrue((self.root / "projects" / "acme" / "profiles"
                         / "demo" / "profile.md").exists())

        c, out = run(["create-channel", "--profile", "demo",
                      "--slug", "demo-tiktok", "--platform", "tiktok"])
        self.assertEqual(c, 0); self.assertEqual(out["platform"], "tiktok")

        c, out = run(["add-post", "--profile", "demo",
                      "--working-title", "Idea A", "--channels", "demo-tiktok"])
        self.assertEqual(c, 0); self.assertTrue(out["id"].startswith("m-"))
        self.assertEqual(len(db.profile_posts("demo")), 1)

    def test_create_profile_unknown_project_errors(self):
        c, out = run(["create-profile", "--project", "nope", "--slug", "x"])
        self.assertEqual(c, 1); self.assertIn("not found", out["error"])

    def test_activity_and_milestone(self):
        run(["create-project", "--slug", "acme"])
        c, out = run(["create-activity", "--entity", "acme",
                      "--title", "Draft hook", "--type", "task"])
        self.assertEqual(c, 0); self.assertEqual(out["title"], "Draft hook")
        c, out = run(["mark-done", "--entity", "acme", "--title", "Draft hook"])
        self.assertEqual(c, 0); self.assertTrue(out["done"])

        c, out = run(["create-milestone", "--title", "Launch", "--date", "2026-07-01",
                      "--entity", "acme"])
        self.assertEqual(c, 0); self.assertTrue(out["id"].startswith("ms-"))

    def test_create_activity_requires_title(self):
        c, out = run(["create-activity", "--entity", "acme"])
        self.assertEqual(c, 1); self.assertIn("title is required", out["error"])

    def test_update_project(self):
        run(["create-project", "--slug", "acme", "--name", "Acme"])
        c, out = run(["update-project", "--slug", "acme", "--name", "Acme Inc",
                      "--status", "live"])
        self.assertEqual(c, 0); self.assertTrue(out["ok"])
        self.assertEqual(db.project("acme")["entity"]["name"], "Acme Inc")

    def test_update_channel(self):
        run(["create-project", "--slug", "acme"])
        run(["create-profile", "--project", "acme", "--slug", "demo"])
        run(["create-channel", "--profile", "demo", "--slug", "demo-tt", "--platform", "tiktok"])
        c, out = run(["update-channel", "--slug", "demo-tt", "--platform", "instagram"])
        self.assertEqual(c, 0); self.assertTrue(out["ok"])
        self.assertEqual(db.channel("demo-tt")["platform"], "instagram")

    def test_update_milestone(self):
        run(["create-project", "--slug", "acme"])
        _, ms = run(["create-milestone", "--title", "Launch", "--date", "2026-07-01",
                     "--entity", "acme"])
        c, out = run(["update-milestone", "--id", ms["id"], "--title", "Big Launch"])
        self.assertEqual(c, 0); self.assertTrue(out["ok"])


if __name__ == "__main__":
    unittest.main()
