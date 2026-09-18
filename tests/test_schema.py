import sqlite3, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class TestSchema(unittest.TestCase):
    def _fresh_db(self, tmp):
        import index
        index.build(Path(tmp))
        return Path(tmp) / "database" / "data" / "os.db"

    def test_entities_type_check_and_subtype(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = self._fresh_db(tmp)
            con = sqlite3.connect(db)
            cols = {r[1] for r in con.execute("PRAGMA table_info(entities)")}
            self.assertIn("subtype", cols)
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("INSERT INTO entities(slug,type,name,updated_at) VALUES('p','project','P','t')")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO entities(slug,type,name,updated_at) VALUES('b','brand','B','t')")
            con.close()

    def test_posts_have_profile_slug_and_join(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = self._fresh_db(tmp)
            con = sqlite3.connect(db)
            pcols = {r[1] for r in con.execute("PRAGMA table_info(posts)")}
            self.assertIn("profile_slug", pcols)
            self.assertNotIn("brand_slug", pcols)
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("post_channels", tables)
            fcols = {r[1] for r in con.execute("PRAGMA table_info(features)")}
            self.assertIn("product_slug", fcols)
            con.close()

if __name__ == "__main__":
    unittest.main()
