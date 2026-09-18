import tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db


class BriefsVoicesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        prof = root / "projects" / "acme" / "profiles" / "demo"
        write(root / "projects" / "acme" / "project.md", "---\nname: Acme\n---")
        write(prof / "profile.md", "---\nname: Demo\n---")
        write(prof / "channels" / "demo-ig" / "channel.md", "---\nplatform: instagram\n---")
        write(prof / "channels" / "demo-tt" / "channel.md", "---\nplatform: tiktok\n---")
        (prof / "content").mkdir(parents=True, exist_ok=True)
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_profile_platforms_lists_channel_platforms(self):
        self.assertEqual(sorted(fileops.profile_platforms("demo")), ["instagram", "tiktok"])

    def test_create_brief_spec_mints_br2_and_validates_platform(self):
        res = fileops.create_brief_spec("demo", "TikTok only rules.", platforms="tiktok")
        self.assertEqual(res["brief_id"], "br2")
        with self.assertRaises(fileops.ActionError):
            fileops.create_brief_spec("demo", "bad", platforms="youtube")

    def test_update_brief_spec_defaults_to_br1(self):
        fileops.update_brief_spec("demo", "Default rules.")
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(), "Default rules.")

    def test_list_brief_specs(self):
        fileops.create_brief_spec("demo", "second", platforms="tiktok")
        specs = fileops.list_brief_specs("demo")
        self.assertEqual([s["id"] for s in specs], ["br1", "br2"])
        self.assertEqual(specs[1]["platforms"], "tiktok")

    def test_delete_brief_spec_guards_last_one(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_brief_spec("demo", "br1")

    def test_create_and_list_voice(self):
        fileops.create_voice("demo", "Faster cuts.", platforms="tiktok")
        voices = fileops.list_voices("demo")
        self.assertEqual([v["id"] for v in voices], ["vc1", "vc2"])

    def test_read_profile_no_longer_returns_voice_or_brief_spec(self):
        prof = fileops.read_profile("demo")
        self.assertNotIn("voice", prof)
        self.assertNotIn("brief_spec", prof)


if __name__ == "__main__":
    unittest.main()
