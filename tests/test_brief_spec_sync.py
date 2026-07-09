"""Integration: brief-spec.md is one file, per-profile, read live on every path."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import index
from core.brief_spec_util import read_spec_text, SPEC_DIR
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db
import dashboard.osctl as osctl


class BriefSpecSyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        fileops.ROOT = self.root
        db.DB_PATH = self.root / "database" / "data" / "os.db"
        prof = self.root / "projects" / "acme" / "profiles" / "demo"
        write(self.root / "projects" / "acme" / "project.md", "---\nname: Acme\n---")
        write(prof / "profile.md", "---\nname: Demo\n---")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---")
        (prof / "content").mkdir(parents=True, exist_ok=True)
        index.build(self.root)

    def tearDown(self):
        fileops.ROOT = Path(fileops.__file__).resolve().parent.parent
        self.tmp.cleanup()

    def _spec_path(self):
        return self.root / "projects/acme/profiles/demo" / SPEC_DIR / "br1.md"

    def test_write_brief_spec_hits_canonical_file(self):
        text = "Rules from write_brief_spec."
        fileops.write_brief_spec("demo", text)
        self.assertIn(text, self._spec_path().read_text())

    def test_all_read_paths_match_disk(self):
        text = "Caption max 120 chars.\n- slides\n- caption"
        fileops.write_brief_spec("demo", text)

        prof_dir = self.root / "projects/acme/profiles/demo"
        self.assertEqual(read_spec_text(prof_dir).strip(), text)
        self.assertEqual(fileops.read_brief_spec("demo").strip(), text)
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(), text)
        self.assertEqual(fileops.brief_spec_relpath("demo"),
                         "projects/acme/profiles/demo/brief-specs/br1.md")

    def test_spec_change_does_not_touch_existing_brief_files(self):
        fileops.write_brief_spec("demo", "- caption")
        fileops.add_post("demo", {"working_title": "A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        fileops.set_brief(pid, {"channels": ["demo-tiktok"], "caption": "legacy body"})

        fileops.write_brief_spec("demo", "- cover_overlay\n- catchy_title\n- caption")
        brief = json.loads(
            (self.root / "projects/acme/profiles/demo/content/briefs" / f"{pid}.json").read_text()
        )
        self.assertEqual(brief["caption"], "legacy body")
        self.assertNotIn("cover_overlay", brief)

    def test_write_brief_does_not_copy_slot_identity_when_spec_omits_them(self):
        spec = """
        {
          "id": "post-001",
          "cover_overlay": "...",
          "slide_overlays": [],
          "catchy_title": "...",
          "caption": "..."
        }
        """
        fileops.write_brief_spec("demo", spec)
        created = fileops.add_post(
            "demo",
            {"working_title": "A", "channels": "demo-tiktok", "pillar": "curiosity"},
        )
        pid = created["id"]
        ctx = fileops.find_post(pid)
        data = json.loads(ctx["plan"].read_text())
        for post in data["posts"]:
            if post.get("id") == pid:
                post.update({
                    "platform": "tiktok",
                    "format": "reel",
                    "objective": "engage",
                    "pillar": "curiosity",
                })
        ctx["plan"].write_text(json.dumps(data), encoding="utf-8")

        fileops.set_brief(
            pid,
            {
                "channels": ["demo-tiktok"],
                "cover_overlay": "Hook",
                "slide_overlays": [{"slide": 1, "overlay": "Line one\nLine two\nLine three"}],
                "catchy_title": "Title 🎬",
                "caption": "Body",
            },
        )
        brief = json.loads(
            (self.root / "projects/acme/profiles/demo/content/briefs" / f"{pid}.json").read_text()
        )
        self.assertNotIn("platform", brief)
        self.assertNotIn("objective", brief)
        self.assertNotIn("pillar", brief)

    def test_new_brief_strict_after_spec_tightens(self):
        fileops.write_brief_spec("demo", "- cover_overlay\n- caption")
        fileops.add_post("demo", {"working_title": "B", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        with self.assertRaises(fileops.ActionError):
            fileops.set_brief(pid, {"channels": ["demo-tiktok"], "caption": "only"})

    def test_generate_reads_live_spec_at_job_time(self):
        fileops.write_brief_spec("demo", "LIVE SPEC LINE")
        captured = {}

        import generate
        orig = generate.run_job
        pid_holder = []

        def fake_run_job(prompt, voice, validate, **k):
            captured["prompt"] = prompt
            return {"id": pid_holder[0], "channels": ["demo-tiktok"], "caption": "c",
                    "cover_overlay": "h"}

        generate.run_job = fake_run_job
        try:
            fileops.add_post("demo", {"working_title": "C", "channels": "demo-tiktok"})
            pid_holder.append(db.profile_posts("demo")[0]["id"])
            generate.do_brief(self.root, "demo", pid_holder[0])
        finally:
            generate.run_job = orig

        self.assertIn("LIVE SPEC LINE", captured["prompt"])

    def test_osctl_get_matches_fileops(self):
        fileops.write_brief_spec("demo", "Osctl read check.")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            osctl.main(["get-brief-spec", "--profile", "demo"])
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertTrue(out["ok"])
        self.assertEqual(out["brief_spec"].strip(), "Osctl read check.")


if __name__ == "__main__":
    unittest.main()