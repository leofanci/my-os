import json, sqlite3, tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db


class CrudTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        root = self.root
        proj = root / "projects" / "acme"
        write(proj / "project.md",
              "---\nname: Acme\nkind: venture\npriority: primary\n"
              "status: idea\nhours_per_week: 5\n---\nour voice")
        prof = proj / "profiles" / "demo"
        write(prof / "profile.md", "---\nname: Demo\ntopic: demo-topic\nproject: acme\n---\nvoice")
        ch = prof / "channels" / "demo-tiktok"
        write(ch / "channel.md", "---\nplatform: tiktok\nhandle: @demo\n---\n")
        write(ch / "guidelines.md", "keep it punchy")
        write(root / "portfolio" / "milestones.json", json.dumps({"milestones": [
            {"id": "ms-1", "title": "Launch", "date": "2026-08-01", "type": "event",
             "entity": "acme", "entity_type": "project"}]}))
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def _con(self):
        return sqlite3.connect(self.root / "database" / "data" / "os.db")

    # ---- project ----------------------------------------------------------- #
    def test_update_project_changes_fields_keeps_slug(self):
        fileops.update_project("acme", {"name": "Acme Inc", "status": "active"})
        ent = db.project("acme")["entity"]
        self.assertEqual(ent["name"], "Acme Inc")
        self.assertEqual(ent["status"], "active")
        # body (voice) preserved
        self.assertIn("our voice", (self.root / "projects/acme/project.md").read_text())

    def test_update_project_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_project("nope", {"name": "X"})

    def test_delete_project_removes_it(self):
        fileops.delete_milestone("ms-1")  # drop the only reference first
        fileops.delete_project("acme")
        self.assertIsNone(db.project("acme"))
        self.assertFalse((self.root / "projects/acme").exists())

    def test_delete_project_refuses_when_referenced(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_project("acme")  # ms-1 still references it
        self.assertTrue((self.root / "projects/acme").exists())

    # ---- channel ----------------------------------------------------------- #
    def test_update_channel_changes_platform_and_handle(self):
        fileops.update_channel("demo-tiktok", {"platform": "instagram", "handle": "@newhandle"})
        self.assertEqual(db.channel("demo-tiktok")["platform"], "instagram")
        self.assertIn("@newhandle", (fileops._channel_dir("demo-tiktok") / "channel.md").read_text())
        # guidelines.md left untouched
        self.assertEqual(fileops.read_channel_guidelines("demo-tiktok"), "keep it punchy")

    def test_update_channel_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_channel("nope", {"platform": "x"})

    # ---- milestone --------------------------------------------------------- #
    def test_update_milestone_changes_title(self):
        fileops.update_milestone("ms-1", {"title": "Big Launch"})
        row = self._con().execute("SELECT title FROM milestones WHERE id='ms-1'").fetchone()
        self.assertEqual(row[0], "Big Launch")

    def test_update_milestone_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_milestone("ms-zzz", {"title": "X"})

    def test_delete_milestone_removes_it(self):
        fileops.delete_milestone("ms-1")
        row = self._con().execute("SELECT title FROM milestones WHERE id='ms-1'").fetchone()
        self.assertIsNone(row)

    def test_delete_milestone_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_milestone("ms-zzz")

    def test_timeline_milestone_carries_ref_id(self):
        ms = [r for r in db.timeline() if r["kind"] == "milestone"]
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0]["ref_id"], "ms-1")

    # ---- memo ---------------------------------------------------------------- #
    def test_update_memo_patches_fields_in_place_same_version(self):
        created = fileops.create_memo("acme", "assessment", {
            "pace_recommendation": "accelerate",
            "riskiest_assumption": "people will pay",
        })
        self.assertEqual(created["version"], 1)
        fileops.update_memo("acme", "assessment", 1, {"pace_recommendation": "validate quietly"})
        proj = db.project("acme")
        memo = next(m for m in proj["memos"] if m["type"] == "assessment" and m["version"] == 1)
        body = json.loads((self.root / memo["file_path"]).read_text())
        self.assertEqual(body["pace_recommendation"], "validate quietly")
        self.assertEqual(body["riskiest_assumption"], "people will pay")

    def test_update_memo_unknown_version_raises(self):
        fileops.create_memo("acme", "assessment", {"pace_recommendation": "accelerate"})
        with self.assertRaises(fileops.ActionError):
            fileops.update_memo("acme", "assessment", 9, {"pace_recommendation": "x"})

    def test_delete_memo_removes_the_version_file(self):
        fileops.create_memo("acme", "assessment", {"pace_recommendation": "accelerate"})
        fileops.delete_memo("acme", "assessment", 1)
        proj = db.project("acme")
        self.assertFalse([m for m in proj["memos"] if m["type"] == "assessment" and m["version"] == 1])

    def test_delete_memo_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_memo("acme", "assessment", 9)

    # ---- experiment ------------------------------------------------------------ #
    def test_update_experiment_patches_fields(self):
        created = fileops.create_experiment("acme", {"assumption": "people will pay", "stem": "will-pay"})
        fileops.update_experiment("acme", "will-pay", {"success_criteria": "10 paid signups"})
        proj = db.project("acme")
        exp = next(x for x in proj["experiments"] if x["stem"] == "will-pay")
        body = json.loads((self.root / exp["file_path"]).read_text())
        self.assertEqual(body["success_criteria"], "10 paid signups")
        self.assertEqual(body["assumption"], "people will pay")
        self.assertEqual(created["stem"], "will-pay")

    def test_update_experiment_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_experiment("acme", "nope", {"success_criteria": "x"})

    def test_delete_experiment_removes_it(self):
        fileops.create_experiment("acme", {"assumption": "people will pay", "stem": "will-pay"})
        fileops.delete_experiment("acme", "will-pay")
        proj = db.project("acme")
        self.assertFalse([x for x in proj["experiments"] if x["stem"] == "will-pay"])

    def test_delete_experiment_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_experiment("acme", "nope")

    # ---- feature ------------------------------------------------------------- #
    def _make_product_with_feature(self):
        fileops.create_product("acme", "app", {"name": "Acme App"})
        fileops.add_feature("app", {"title": "Dark mode", "why": "user request", "priority": "high"})

    def test_update_feature_patches_why_and_priority_in_place(self):
        self._make_product_with_feature()
        out = fileops.update_feature("app", "dark-mode", {"why": "top request", "priority": "critical"})
        self.assertEqual(out["title"], "Dark mode")
        roadmap = (self.root / "projects/acme/products/app/roadmap.md").read_text()
        self.assertIn("Dark mode — top request — priority: critical", roadmap)

    def _section_block(self, roadmap_text, heading):
        after = roadmap_text.split(f"## {heading}", 1)[1]
        return after.split("\n## ", 1)[0]

    def test_update_feature_moves_between_sections(self):
        self._make_product_with_feature()
        fileops.update_feature("app", "dark-mode", {"section": "Later / Ideas"})
        roadmap = (self.root / "projects/acme/products/app/roadmap.md").read_text()
        self.assertIn("Dark mode", self._section_block(roadmap, "Later / Ideas"))
        self.assertNotIn("Dark mode", self._section_block(roadmap, "Next"))
        self.assertNotIn("Dark mode", self._section_block(roadmap, "Shipped"))

    def test_update_feature_moves_into_non_last_section(self):
        # "Next" (default) -> "Now" while "Later / Ideas" and "Shipped" still
        # follow in the file — regression test for a bug where the moved line
        # always landed after whichever section happened to be physically
        # last in the document, instead of under the target heading.
        self._make_product_with_feature()
        fileops.update_feature("app", "dark-mode", {"section": "Now"})
        roadmap = (self.root / "projects/acme/products/app/roadmap.md").read_text()
        self.assertIn("Dark mode", self._section_block(roadmap, "Now"))
        self.assertNotIn("Dark mode", self._section_block(roadmap, "Next"))
        self.assertNotIn("Dark mode", self._section_block(roadmap, "Later / Ideas"))
        self.assertNotIn("Dark mode", self._section_block(roadmap, "Shipped"))

    def test_update_feature_rename_changes_id(self):
        self._make_product_with_feature()
        out = fileops.update_feature("app", "dark-mode", {"title": "Night mode"})
        self.assertIn("Night mode", (self.root / "projects/acme/products/app/roadmap.md").read_text())
        self.assertEqual(out["title"], "Night mode")

    def test_update_feature_unknown_raises(self):
        self._make_product_with_feature()
        with self.assertRaises(fileops.ActionError):
            fileops.update_feature("app", "nope", {"why": "x"})

    def test_delete_feature_removes_the_line(self):
        self._make_product_with_feature()
        fileops.delete_feature("app", "dark-mode")
        roadmap = (self.root / "projects/acme/products/app/roadmap.md").read_text()
        self.assertNotIn("Dark mode", roadmap)

    def test_delete_feature_unknown_raises(self):
        self._make_product_with_feature()
        with self.assertRaises(fileops.ActionError):
            fileops.delete_feature("app", "nope")

    def test_add_feature_rejects_em_dash_in_title(self):
        fileops.create_product("acme", "app", {"name": "Acme App"})
        with self.assertRaises(fileops.ActionError):
            fileops.add_feature("app", {"title": "Do X — Not Y"})

    def test_update_feature_rejects_em_dash_in_why(self):
        self._make_product_with_feature()
        with self.assertRaises(fileops.ActionError):
            fileops.update_feature("app", "dark-mode", {"why": "improves X — breaks Y"})

    # ---- log posted (add_post published path) ------------------------------ #
    def test_add_post_published_lands_published_with_date(self):
        res = fileops.add_post("demo", {"working_title": "Recap",
                                        "date": "2026-07-20", "status": "published"})
        ctx = fileops.find_post(res["id"], "demo")
        self.assertEqual(ctx["post"]["status"], "published")
        self.assertEqual(ctx["post"]["date"], "2026-07-20")

    def test_add_post_published_without_date_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.add_post("demo", {"working_title": "Recap", "status": "published"})

    def test_add_post_defaults_to_planned(self):
        res = fileops.add_post("demo", {"working_title": "Idea"})
        ctx = fileops.find_post(res["id"], "demo")
        self.assertEqual(ctx["post"]["status"], "planned")


if __name__ == "__main__":
    unittest.main()
