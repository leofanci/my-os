import json, tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write   # reuse the tree writer

class TestTree(unittest.TestCase):
    def _db(self, tmp):
        root = Path(tmp)
        proj = root / "projects" / "acme"
        write(proj / "project.md", "---\nname: Acme\nkind: venture\npriority: primary\n---")
        prof = proj / "profiles" / "demo"
        write(prof / "profile.md", "---\nname: Demo\n---")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---")
        write(prof / "content" / "plan-x.json", json.dumps({"posts": [
            {"id": "p1", "status": "planned", "channels": ["demo-tiktok"]}]}))
        write(proj / "products" / "app" / "product.md", "---\nname: App\ntype: app\n---")
        index.build(root)
        import dashboard.db as db
        db.DB_PATH = root / "database" / "data" / "os.db"
        return db

    def test_tree_nests_profiles_channels_products(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp)
            tree = db.tree()
            self.assertEqual(len(tree), 1)
            p = tree[0]
            self.assertEqual(p["slug"], "acme")
            self.assertEqual(p["kind"], "venture")
            self.assertEqual([x["slug"] for x in p["profiles"]], ["demo"])
            self.assertEqual([c["slug"] for c in p["profiles"][0]["channels"]],
                             ["demo-tiktok"])
            self.assertEqual([a["slug"] for a in p["products"]], ["app"])
            self.assertEqual(p["profiles"][0]["posts"], 1)

class TestPostsIndex(unittest.TestCase):
    def test_posts_returns_all_with_profile_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = TestTree()._db(tmp)
            rows = db.posts()
            self.assertEqual(len(rows), 1)
            r = rows[0]
            self.assertEqual(r["id"], "p1")
            self.assertEqual(r["profile_slug"], "demo")
            self.assertEqual(r["profile_name"], "Demo")
            for key in ("pillar", "working_title", "status"):
                self.assertIn(key, r)


if __name__ == "__main__":
    unittest.main()
