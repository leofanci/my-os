import tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db


class MigrationEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        prof = root / "projects" / "acme" / "profiles" / "demo"
        write(root / "projects" / "acme" / "project.md", "---\nname: Acme\n---")
        write(prof / "profile.md", "---\nname: Demo\ntopic: film\nproject: acme\n---\nLegacy voice.\n")
        write(prof / "brief-spec.md", "Legacy brief rules.")
        (prof / "content").mkdir(parents=True, exist_ok=True)
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_profile_reads_correctly_pre_and_post_migration(self):
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(), "Legacy brief rules.")
        self.assertEqual(fileops.list_voices("demo")[0]["text"].strip(), "Legacy voice.")
        # legacy files gone, new structure present
        prof_dir = fileops.ROOT / "projects" / "acme" / "profiles" / "demo"
        self.assertFalse((prof_dir / "brief-spec.md").exists())
        self.assertTrue((prof_dir / "brief-specs" / "br1.md").is_file())
        self.assertTrue((prof_dir / "voices" / "vc1.md").is_file())
        # idempotent re-read
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(), "Legacy brief rules.")

    def test_adding_second_brief_and_regenerating_ids_is_stable(self):
        fileops.create_brief_spec("demo", "Second.", platforms="all")
        self.assertEqual(fileops.list_brief_specs("demo")[1]["id"], "br2")
        fileops.delete_brief_spec("demo", "br2")
        fileops.create_brief_spec("demo", "Third.", platforms="all")
        self.assertEqual(fileops.list_brief_specs("demo")[1]["id"], "br3")  # never reuses br2


if __name__ == "__main__":
    unittest.main()
