import json, subprocess, sys, tempfile, unittest
from pathlib import Path
import dashboard.fileops as fileops
import index
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
    "hashtags": ["#film"],
    "visual_brief": {"description": "x", "mood": "y", "format_specs": "9:16",
                     "text_overlays": [], "genai_prompt_draft": ""},
    "notes_for_human": "",
}


class RevisePostTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        fileops.ROOT = self.root

        proj = self.root / "projects" / "acme"
        prof = proj / "profiles" / "demo"
        write(proj / "project.md", "---\nname: Acme\n---\nvoice")
        write(prof / "profile.md", "---\nname: Demo\n---\nvoice")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---")
        write(prof / "channels" / "demo-tiktok" / "guidelines.md", "be punchy")
        write(prof / "content" / "plan-2026-07.json",
              json.dumps({"posts": [SLOT.copy()]}))
        index.build(self.root)

    def tearDown(self):
        fileops.ROOT = Path(fileops.__file__).resolve().parent.parent
        self.tmp.cleanup()

    def _fake_revise(self, output: dict):
        """Monkeypatch subprocess.run so generate.py revise succeeds without calling claude."""
        orig = subprocess.run

        def mock_run(cmd, **kw):
            if "revise" in cmd:
                # Write the output where do_revise would write it
                post_id = cmd[cmd.index("revise") + 2]
                prof_dir = self.root / "projects" / "acme" / "profiles" / "demo"
                brief_path = prof_dir / "content" / "briefs" / f"{post_id}.json"
                if brief_path.exists():
                    brief_path.write_text(json.dumps(output), encoding="utf-8")
                else:
                    # Update slot in plan file
                    plan = prof_dir / "content" / "plan-2026-07.json"
                    data = json.loads(plan.read_text())
                    for p in data["posts"]:
                        if p["id"] == post_id:
                            p.update({k: v for k, v in output.items() if k != "id"})
                    plan.write_text(json.dumps(data), encoding="utf-8")

                class R:
                    returncode = 0
                    stdout = f"revised for {post_id}"
                    stderr = ""
                return R()
            return orig(cmd, **kw)

        return mock_run

    # ── idea revision ────────────────────────────────────────────────────────

    def test_revise_idea_updates_slot_fields(self):
        revised_slot = {**SLOT, "working_title": "How films distort truth",
                        "concept": "Deep dive into Hollywood revisionism."}
        mock = self._fake_revise(revised_slot)
        orig = subprocess.run
        subprocess.run = mock
        try:
            result = fileops.revise_post("post-001", "make the title more academic")
        finally:
            subprocess.run = orig

        self.assertEqual(result["id"], "post-001")
        self.assertFalse(result["is_draft"])

        plan = json.loads(
            (self.root / "projects/acme/profiles/demo/content/plan-2026-07.json").read_text()
        )
        slot = plan["posts"][0]
        self.assertEqual(slot["working_title"], "How films distort truth")

    # ── draft revision ───────────────────────────────────────────────────────

    def test_revise_draft_bumps_version(self):
        brief_path = self.root / "projects/acme/profiles/demo/content/briefs/post-001.json"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(json.dumps(BRIEF), encoding="utf-8")

        revised_brief = {**BRIEF, "hook": "Cinema lies — here's the evidence."}
        mock = self._fake_revise(revised_brief)
        orig = subprocess.run
        subprocess.run = mock
        try:
            result = fileops.revise_post("post-001", "punchier hook")
        finally:
            subprocess.run = orig

        self.assertTrue(result["is_draft"])
        plan = json.loads(
            (self.root / "projects/acme/profiles/demo/content/plan-2026-07.json").read_text()
        )
        self.assertEqual(plan["posts"][0].get("version"), 2)

    def test_revise_draft_subsequent_bump(self):
        brief_path = self.root / "projects/acme/profiles/demo/content/briefs/post-001.json"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(json.dumps(BRIEF), encoding="utf-8")
        # Simulate already-revised (version = 3)
        plan_path = self.root / "projects/acme/profiles/demo/content/plan-2026-07.json"
        data = json.loads(plan_path.read_text())
        data["posts"][0]["version"] = 3
        plan_path.write_text(json.dumps(data))
        index.build(self.root)

        mock = self._fake_revise({**BRIEF, "hook": "New hook."})
        orig = subprocess.run
        subprocess.run = mock
        try:
            fileops.revise_post("post-001", "another tweak")
        finally:
            subprocess.run = orig

        data = json.loads(plan_path.read_text())
        self.assertEqual(data["posts"][0]["version"], 4)

    def test_revise_empty_instruction_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.revise_post("post-001", "")

    def test_revise_unknown_post_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.revise_post("nonexistent-id", "do something")


if __name__ == "__main__":
    unittest.main()
