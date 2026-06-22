import json, sqlite3, tempfile, unittest
from pathlib import Path
import index

def write(p: Path, text=""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

class TestTreeWalk(unittest.TestCase):
    def _build(self, tmp):
        root = Path(tmp)
        proj = root / "projects" / "acme"
        write(proj / "project.md", "---\nname: Acme\nkind: venture\npriority: primary\nhours_per_week: 12\n---\nvoice")
        prof = proj / "profiles" / "demo"
        write(prof / "profile.md", "---\nname: Demo\ntopic: cinema\n---\nvoice")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---\nrules")
        write(prof / "content" / "plan-2026-07.json", json.dumps({"posts": [
            {"id": "post-001", "date": "2026-07-01", "pillar": "curiosity", "status": "planned",
             "channels": ["demo-tiktok"]}]}))
        write(proj / "products" / "acme-app" / "product.md", "---\nname: Acme App\ntype: app\n---")
        write(proj / "products" / "acme-app" / "roadmap.md", "## Now\n- [ ] Editor — priority: high")
        index.build(root)
        return sqlite3.connect(root / "database" / "data" / "os.db")

    def test_entities_and_nesting(self):
        with tempfile.TemporaryDirectory() as tmp:
            con = self._build(tmp)
            types = dict(con.execute("SELECT slug, type FROM entities"))
            self.assertEqual(types["acme"], "project")
            self.assertEqual(types["demo"], "profile")
            self.assertEqual(types["demo-tiktok"], "channel")
            self.assertEqual(types["acme-app"], "product")
            sub = dict(con.execute("SELECT slug, subtype FROM entities"))
            self.assertEqual(sub["acme"], "venture")
            belongs = set(con.execute("SELECT from_slug, to_slug FROM relationships WHERE kind='belongs_to'"))
            self.assertIn(("demo", "acme"), belongs)
            self.assertIn(("demo-tiktok", "demo"), belongs)
            self.assertIn(("acme-app", "acme"), belongs)

    def test_post_profile_and_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            con = self._build(tmp)
            prof = con.execute("SELECT profile_slug FROM posts WHERE id='post-001'").fetchone()[0]
            self.assertEqual(prof, "demo")
            chans = [r[0] for r in con.execute(
                "SELECT channel_slug FROM post_channels WHERE post_id='post-001'")]
            self.assertEqual(chans, ["demo-tiktok"])

    def test_feature_under_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            con = self._build(tmp)
            row = con.execute("SELECT product_slug, title FROM features").fetchone()
            self.assertEqual(row[0], "acme-app")

    def test_post_carries_working_title_and_concept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build(tmp)
            prof = root / "projects" / "acme" / "profiles" / "demo"
            write(prof / "content" / "plan-2026-07.json", json.dumps({"posts": [
                {"id": "post-001", "date": "2026-07-01", "pillar": "curiosity",
                 "working_title": "Why films matter", "concept": "open strong",
                 "status": "planned", "channels": ["demo-tiktok"]}]}))
            index.build(root)
            con = sqlite3.connect(root / "database" / "data" / "os.db")
            row = con.execute(
                "SELECT working_title, concept FROM posts WHERE id='post-001'").fetchone()
            self.assertEqual(row, ("Why films matter", "open strong"))

    def test_unknown_channel_slug_is_pruned_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build(tmp)
            prof = root / "projects" / "acme" / "profiles" / "demo"
            # A generated plan that names the platform instead of the channel slug
            # must not brick the whole rebuild.
            write(prof / "content" / "plan-bad.json", json.dumps({"posts": [
                {"id": "post-002", "date": "2026-07-02", "pillar": "curiosity",
                 "status": "planned", "channels": ["tiktok"]}]}))
            index.build(root)  # must not raise
            con = sqlite3.connect(root / "database" / "data" / "os.db")
            self.assertIsNotNone(
                con.execute("SELECT 1 FROM posts WHERE id='post-002'").fetchone())
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM post_channels WHERE post_id='post-002'").fetchone()[0], 0)

if __name__ == "__main__":
    unittest.main()
