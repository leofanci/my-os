import json, tempfile, unittest
from pathlib import Path
import generate
from tests.test_index_projects import write


class DoPlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        prof = self.root / "projects" / "acme" / "profiles" / "demo"
        write(self.root / "projects" / "acme" / "project.md", "---\nname: Acme\n---\nproject voice")
        write(prof / "profile.md", "---\nname: Demo\n---\nprofile voice")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---")
        write(prof / "channels" / "demo-tiktok" / "guidelines.md", "be punchy")
        self._orig = generate.run_job

    def tearDown(self):
        generate.run_job = self._orig
        self.tmp.cleanup()

    def _plan_file(self):
        files = list((self.root / "projects/acme/profiles/demo/content").glob("plan-*.json"))
        return json.loads(files[0].read_text())

    def test_forces_planned_and_normalizes_channels(self):
        # Model emits an advanced status + a platform name instead of a slug.
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [{"id": "draft-001", "date": "2026-07-01", "pillar": "curiosity",
                       "channels": ["tiktok"], "status": "scheduled",
                       "working_title": "T", "concept": "C"}],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        post = self._plan_file()["posts"][0]
        self.assertEqual(post["status"], "planned")
        self.assertEqual(post["channels"], ["demo-tiktok"])


if __name__ == "__main__":
    unittest.main()
