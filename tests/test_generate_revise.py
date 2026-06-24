import json, tempfile, unittest
from pathlib import Path
import generate
from tests.test_index_projects import write

SLOT = {
    "id": "post-001", "status": "planned", "date": "2026-07-01",
    "pillar": "curiosity", "channels": ["demo-tiktok"],
    "working_title": "Why films lie", "concept": "Explores how cinema distorts history.",
}

BRIEF = {
    "id": "post-001", "channels": ["demo-tiktok"], "platform": "tiktok",
    "format": "reel", "objective": "educate", "pillar": "curiosity",
    "hook": "Films lie — here's proof.",
    "structure": ["scene 1", "scene 2"],
    "caption": "Did you know movies distort history?",
    "cta": "Follow for more.",
    "hashtags": ["#film", "#history"],
    "visual_brief": {"description": "archival clips", "mood": "serious",
                     "format_specs": "9:16", "text_overlays": [], "genai_prompt_draft": ""},
    "notes_for_human": "",
}


class DoReviseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        prof = self.root / "projects" / "acme" / "profiles" / "demo"
        write(self.root / "projects" / "acme" / "project.md", "---\nname: Acme\n---\nproject voice")
        write(prof / "profile.md", "---\nname: Demo\n---\nprofile voice")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---")
        write(prof / "channels" / "demo-tiktok" / "guidelines.md", "be punchy")
        plan = {"posts": [SLOT.copy()]}
        write(prof / "content" / "plan-2026-07.json", json.dumps(plan))
        self._orig = generate.run_job

    def tearDown(self):
        generate.run_job = self._orig
        self.tmp.cleanup()

    def _read_slot(self):
        f = self.root / "projects/acme/profiles/demo/content/plan-2026-07.json"
        return json.loads(f.read_text())["posts"][0]

    def _read_brief(self):
        f = self.root / "projects/acme/profiles/demo/content/briefs/post-001.json"
        return json.loads(f.read_text())

    # ── ideas path ──────────────────────────────────────────────────────────

    def test_revise_idea_updates_slot(self):
        captured = {}
        def fake_run_job(prompt, voice, validate, **k):
            captured["prompt"] = prompt
            return {"id": "post-001", "working_title": "How films lie to you",
                    "concept": "Explores deliberate distortion.", "date": "2026-07-01",
                    "pillar": "curiosity", "channels": ["demo-tiktok"]}
        generate.run_job = fake_run_job

        generate.do_revise(self.root, "demo", "post-001", "make the title more provocative")

        slot = self._read_slot()
        self.assertEqual(slot["working_title"], "How films lie to you")
        self.assertIn("REVISION INSTRUCTION", captured["prompt"])
        self.assertIn("make the title more provocative", captured["prompt"])
        self.assertIn("CURRENT SLOT", captured["prompt"])
        self.assertIn("Why films lie", captured["prompt"])

    def test_revise_idea_voice_cascade_in_stdin(self):
        voices = {}
        def fake_run_job(prompt, voice, validate, **k):
            voices["voice"] = voice
            return {"id": "post-001", "working_title": "T", "concept": "C",
                    "date": "2026-07-01", "pillar": "p", "channels": ["demo-tiktok"]}
        generate.run_job = fake_run_job

        generate.do_revise(self.root, "demo", "post-001", "shorter title")
        self.assertIn("profile voice", voices["voice"])
        self.assertIn("project voice", voices["voice"])

    def test_revise_idea_injects_brief_spec(self):
        write(self.root / "projects/acme/profiles/demo/brief-spec.md",
              "Caption max 120 chars.")
        captured = {}
        def fake_run_job(prompt, voice, validate, **k):
            captured["prompt"] = prompt
            return {"id": "post-001", "working_title": "T", "concept": "C",
                    "date": "2026-07-01", "pillar": "p", "channels": ["demo-tiktok"]}
        generate.run_job = fake_run_job

        generate.do_revise(self.root, "demo", "post-001", "tweak concept")
        self.assertIn("Caption max 120 chars", captured["prompt"])

    # ── drafts path ─────────────────────────────────────────────────────────

    def test_revise_draft_overwrites_brief(self):
        brief_path = self.root / "projects/acme/profiles/demo/content/briefs/post-001.json"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(json.dumps(BRIEF), encoding="utf-8")

        revised = {**BRIEF, "hook": "Cinema rewrites history — here's the proof."}
        captured = {}
        def fake_run_job(prompt, voice, validate, **k):
            captured["prompt"] = prompt
            return revised
        generate.run_job = fake_run_job

        generate.do_revise(self.root, "demo", "post-001", "punchier hook")

        saved = self._read_brief()
        self.assertEqual(saved["hook"], "Cinema rewrites history — here's the proof.")
        self.assertIn("CURRENT BRIEF", captured["prompt"])
        self.assertIn("punchier hook", captured["prompt"])
        self.assertIn("Films lie", captured["prompt"])  # original hook present in prompt

    def test_revise_draft_prompt_includes_platform_constraints(self):
        brief_path = self.root / "projects/acme/profiles/demo/content/briefs/post-001.json"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(json.dumps(BRIEF), encoding="utf-8")

        captured = {}
        generate.run_job = lambda p, v, validate, **k: (captured.update({"p": p}) or {**BRIEF})
        generate.do_revise(self.root, "demo", "post-001", "shorten caption")
        self.assertIn("PLATFORM CONSTRAINTS", captured["p"])


if __name__ == "__main__":
    unittest.main()
