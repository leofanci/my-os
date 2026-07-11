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

    def test_plan_prompt_includes_brief_spec(self):
        # The planner must see the per-profile brief spec, so the calendar matches
        # how posts are actually produced (e.g. one slot targeting both channels).
        write(self.root / "projects/acme/profiles/demo/brief-spec.md",
              "One carousel reused as a reel across both channels.")
        captured = {}
        def fake_run_job(prompt, voice, validate, **k):
            captured["prompt"] = prompt
            return {"period": "p", "profile": "demo",
                    "posts": [{"id": "draft-001", "date": "2026-07-01",
                               "pillar": "curiosity", "channels": ["demo-tiktok"]}]}
        generate.run_job = fake_run_job
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        self.assertIn("PROFILE BRIEF SPEC", captured["prompt"])
        self.assertIn("reused as a reel", captured["prompt"])

    def test_forces_planned_and_normalizes_channels(self):
        # Model emits an advanced status + a platform name instead of a slug.
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [{"id": "draft-001", "date": "2026-07-01", "pillar": "curiosity",
                       "channels": ["tiktok"], "status": "approved",
                       "working_title": "T", "concept": "C"}],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        post = self._plan_file()["posts"][0]
        self.assertEqual(post["status"], "planned")
        self.assertEqual(post["channels"], ["demo-tiktok"])

    def test_brief_and_voice_counts_split_across_minted_posts(self):
        write(self.root / "projects/acme/profiles/demo/brief-specs/br1.md", "---\nplatforms: all\n---\nDefault.")
        write(self.root / "projects/acme/profiles/demo/brief-specs/br2.md", "---\nplatforms: tiktok\n---\nTikTok only.")
        write(self.root / "projects/acme/profiles/demo/voices/vc1.md", "---\nplatforms: all\n---\nDefault voice.")
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [
                {"id": f"draft-{i:03d}", "date": "2026-07-01", "pillar": "curiosity",
                 "channels": ["demo-tiktok"], "working_title": f"T{i}", "concept": "C"}
                for i in range(5)
            ],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None,
                          brief_counts={"br1": 3, "br2": 2})
        posts = self._plan_file()["posts"]
        self.assertEqual([p["brief_id"] for p in posts], ["br1", "br1", "br1", "br2", "br2"])
        self.assertEqual([p["voice_id"] for p in posts], ["vc1"] * 5)  # only one voice exists — no split needed

    def test_no_split_requested_uses_first_brief_and_voice_for_everyone(self):
        write(self.root / "projects/acme/profiles/demo/brief-specs/br2.md", "---\nplatforms: tiktok\n---\nSecond.")
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [{"id": "draft-001", "date": "2026-07-01", "pillar": "curiosity",
                       "channels": ["demo-tiktok"], "working_title": "T", "concept": "C"}],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        post = self._plan_file()["posts"][0]
        self.assertEqual(post["brief_id"], "br1")
        self.assertEqual(post["voice_id"], "vc1")

    def test_default_strips_dates_even_if_model_emits_them(self):
        # assign_dates defaults to False — a fresh plan must come out unscheduled
        # even if the model ignores the instruction and includes a date anyway.
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [{"id": "draft-001", "date": "2026-07-01", "pillar": "curiosity",
                       "channels": ["tiktok"], "working_title": "T", "concept": "C"}],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        post = self._plan_file()["posts"][0]
        self.assertNotIn("date", post)

    def test_assign_dates_true_keeps_model_dates(self):
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [{"id": "draft-001", "date": "2026-07-01", "pillar": "curiosity",
                       "channels": ["tiktok"], "working_title": "T", "concept": "C"}],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None,
                          assign_dates=True)
        post = self._plan_file()["posts"][0]
        self.assertEqual(post["date"], "2026-07-01")

    def test_prompt_reflects_date_assignment_flag(self):
        captured = {}
        def fake_run_job(prompt, voice, validate, **k):
            captured["prompt"] = prompt
            return {"period": "p", "profile": "demo", "posts": []}
        generate.run_job = fake_run_job
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        self.assertIn("Do NOT include a \"date\" field", captured["prompt"])
        captured.clear()
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None,
                          assign_dates=True)
        self.assertIn("Assign each post a realistic date", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
