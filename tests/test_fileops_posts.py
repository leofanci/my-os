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

    def test_add_unknown_profile(self):
        with self.assertRaises(fileops.ActionError):
            fileops.add_post("nope", {})

if __name__ == "__main__":
    unittest.main()
