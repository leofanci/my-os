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

    def test_update_post_patches_brief_fields(self):
        fileops.add_post("demo", {
            "working_title": "Idea A",
            "format": "reel",
            "channels": "demo-tiktok",
        })
        pid = db.profile_posts("demo")[0]["id"]
        fileops.set_brief(pid, {
            "channels": ["demo-tiktok"],
            "caption": "original caption",
            "gen_prompts": ["prompt one"],
        })
        fileops.update_post(pid, {
            "objective": "conversion",
            "brief": {"caption": "edited caption", "gen_prompts": ["prompt two"]},
        })
        post = db.profile_posts("demo")[0]
        self.assertEqual(post["version"], 2)
        detail = fileops.read_detail(pid)
        self.assertEqual(detail["slot"]["objective"], "conversion")
        self.assertEqual(detail["brief"]["caption"], "edited caption")
        self.assertEqual(detail["brief"]["gen_prompts"], ["prompt two"])
        self.assertEqual(detail["brief"]["format"], "reel")

    def test_working_title_and_concept_surface(self):
        fileops.add_post("demo", {"working_title": "Idea A",
                                  "concept": "why this now", "channels": "demo-tiktok"})
        post = db.profile_posts("demo")[0]
        self.assertEqual(post["working_title"], "Idea A")
        self.assertEqual(post["concept"], "why this now")

    def test_post_defaults_brief_and_voice_ids(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        slot = fileops.read_detail(pid)["slot"]
        self.assertEqual(slot["brief_id"], "br1")
        self.assertEqual(slot["voice_id"], "vc1")

    def test_post_can_specify_brief_and_voice_ids(self):
        fileops.add_post("demo", {
            "working_title": "Idea A", "channels": "demo-tiktok",
            "brief_id": "br2", "voice_id": "vc2",
        })
        pid = db.profile_posts("demo")[0]["id"]
        slot = fileops.read_detail(pid)["slot"]
        self.assertEqual(slot["brief_id"], "br2")
        self.assertEqual(slot["voice_id"], "vc2")

    def test_delete_works_at_approved_stage(self):
        # Deletion must work at any phase, not just on fresh ideas.
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved"):
            fileops.set_status(pid, to)
        self.assertEqual(db.profile_posts("demo")[0]["status"], "approved")
        fileops.delete_post(pid)
        self.assertEqual(db.profile_posts("demo"), [])

    def test_brief_spec_roundtrip(self):
        fileops.write_brief_spec("demo", "Captions under 100 words.")
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(),
                         "Captions under 100 words.")

    def test_set_brief_creates_file_and_briefs_post(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        res = fileops.set_brief(pid, {"caption": "hello", "hook": "stop scrolling",
                                      "channels": ["demo-tiktok"]})
        self.assertEqual(res["status"], "briefed")
        self.assertFalse(res["rebrief"])
        post = db.profile_posts("demo")[0]
        self.assertEqual(post["status"], "briefed")
        self.assertTrue(post["brief_path"])
        bf = fileops.ROOT.joinpath(post["brief_path"])
        self.assertTrue(bf.exists())
        data = json.loads(bf.read_text())
        self.assertEqual(data["id"], pid)          # id forced, never trusted
        self.assertEqual(data["caption"], "hello")

    def test_set_brief_again_bumps_version_rebrief(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        fileops.set_brief(pid, {"caption": "v1"})
        res = fileops.set_brief(pid, {"caption": "v2"})
        self.assertTrue(res["rebrief"])
        self.assertEqual(db.profile_posts("demo")[0]["version"], 2)

    def test_set_brief_unknown_post_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.set_brief("nope-123", {"caption": "x"})

    def test_set_brief_non_dict_raises(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        with self.assertRaises(fileops.ActionError):
            fileops.set_brief(pid, ["not", "a", "dict"])

    def test_set_brief_rejects_missing_spec_fields(self):
        fileops.write_brief_spec("demo", "- cover_overlay\n- caption")
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        with self.assertRaises(fileops.ActionError) as ctx:
            fileops.set_brief(pid, {"channels": ["demo-tiktok"], "caption": "only caption"})
        self.assertIn("cover_overlay", str(ctx.exception))

    def test_existing_brief_grandfathered_when_spec_changes(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        fileops.set_brief(pid, {"channels": ["demo-tiktok"], "caption": "old style"})
        fileops.write_brief_spec("demo", "- cover_overlay\n- catchy_title")
        # Re-save same old-shaped brief — must not fail after spec got stricter
        res = fileops.set_brief(pid, {"channels": ["demo-tiktok"], "caption": "old style v2"})
        self.assertTrue(res["rebrief"])

    def test_brief_spec_is_per_profile(self):
        write(fileops.ROOT / "projects/acme/profiles/other/profile.md", "---\nname: Other\n---")
        (fileops.ROOT / "projects/acme/profiles/other/content").mkdir(parents=True, exist_ok=True)
        fileops.write_brief_spec("demo", "Demo rules.")
        fileops.write_brief_spec("other", "Other rules.")
        self.assertEqual(fileops.read_brief_spec("demo").strip(), "Demo rules.")
        self.assertEqual(fileops.read_brief_spec("other").strip(), "Other rules.")

    def test_brief_file_reconciles_status_for_review(self):
        # A brief written directly (batch/terminal) leaves status at 'planned'
        # but the UI shows it as a Draft and offers "Review →" (briefed->approved).
        # set_status must reconcile, not raise an illegal-transition error.
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        briefs = fileops.find_post(pid)["plan"].parent / "briefs"
        briefs.mkdir(parents=True, exist_ok=True)
        (briefs / f"{pid}.json").write_text(json.dumps({"id": pid}), encoding="utf-8")
        fileops.set_status(pid, "approved")  # must not raise
        self.assertEqual(db.profile_posts("demo")[0]["status"], "approved")

    def test_bulk_delete(self):
        for name in ("A", "B", "C"):
            fileops.add_post("demo", {"working_title": name, "channels": "demo-tiktok"})
        ids = [p["id"] for p in db.profile_posts("demo")]
        # give one a brief file so we confirm it's removed too
        briefs = fileops.find_post(ids[0])["plan"].parent / "briefs"
        briefs.mkdir(parents=True, exist_ok=True)
        (briefs / f"{ids[0]}.json").write_text("{}", encoding="utf-8")
        res = fileops.delete_posts([ids[0], ids[1], "does-not-exist"])
        self.assertEqual(res["count"], 2)
        left = [p["id"] for p in db.profile_posts("demo")]
        self.assertEqual(left, [ids[2]])
        self.assertFalse((briefs / f"{ids[0]}.json").exists())

    def test_add_unknown_profile(self):
        with self.assertRaises(fileops.ActionError):
            fileops.add_post("nope", {})

    def test_find_post_disambiguates_duplicate_ids_across_profiles(self):
        root = fileops.ROOT
        alpha = root / "projects" / "acme" / "profiles" / "alpha"
        beta = root / "projects" / "acme" / "profiles" / "beta"
        write(beta / "profile.md", "---\nname: Beta\n---")
        for prof, title in (("alpha", "Alpha title"), ("beta", "Beta title")):
            content = root / "projects" / "acme" / "profiles" / prof / "content"
            content.mkdir(parents=True, exist_ok=True)
            (content / "plan-manual.json").write_text(json.dumps({
                "posts": [{"id": "post-001", "working_title": title, "channels": ["demo-tiktok"]}]
            }), encoding="utf-8")
        index.build(root)
        # Indexer keeps the later profile folder (beta) when ids collide.
        ctx = fileops.find_post("post-001")
        self.assertEqual(ctx["profile_slug"], "beta")
        self.assertEqual(ctx["post"]["working_title"], "Beta title")
        alpha_ctx = fileops.find_post("post-001", "alpha")
        self.assertEqual(alpha_ctx["profile_slug"], "alpha")
        self.assertEqual(alpha_ctx["post"]["working_title"], "Alpha title")

    def test_publish_without_date_raises(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved"):
            fileops.set_status(pid, to)
        with self.assertRaises(fileops.ActionError) as ctx:
            fileops.set_status(pid, "published")
        self.assertIn("add a date first", str(ctx.exception))
        self.assertEqual(db.profile_posts("demo")[0]["status"], "approved")

    def test_publish_with_date_succeeds(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved"):
            fileops.set_status(pid, to)
        fileops.set_status(pid, "published")
        self.assertEqual(db.profile_posts("demo")[0]["status"], "published")

    def test_non_publish_transitions_unaffected_by_missing_date(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved", "rejected"):
            fileops.set_status(pid, to)  # must not raise at any step
        self.assertEqual(db.profile_posts("demo")[0]["status"], "rejected")

    def test_clear_date_on_non_published_post_succeeds(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        fileops.update_post(pid, {"date": ""})
        slot = fileops.read_detail(pid)["slot"]
        self.assertNotIn("date", slot)

    def test_clear_date_on_published_post_raises(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved", "published"):
            fileops.set_status(pid, to)
        with self.assertRaises(fileops.ActionError) as ctx:
            fileops.update_post(pid, {"date": ""})
        self.assertIn("must keep a date", str(ctx.exception))
        self.assertEqual(fileops.read_detail(pid)["slot"]["date"], "2026-07-15")

    def test_change_date_on_published_post_is_allowed(self):
        # a post may actually go out on a different day than scheduled — allow the fix.
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved", "published"):
            fileops.set_status(pid, to)
        fileops.update_post(pid, {"date": "2026-07-18"})
        self.assertEqual(fileops.read_detail(pid)["slot"]["date"], "2026-07-18")

    def test_unchanged_date_on_published_post_does_not_raise(self):
        # The edit form always submits the date field, even when the user only
        # touched another field — an unchanged value must not trip the guard.
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved", "published"):
            fileops.set_status(pid, to)
        fileops.update_post(pid, {"date": "2026-07-15", "pillar": "curiosity"})
        slot = fileops.read_detail(pid)["slot"]
        self.assertEqual(slot["date"], "2026-07-15")
        self.assertEqual(slot["pillar"], "curiosity")

if __name__ == "__main__":
    unittest.main()
