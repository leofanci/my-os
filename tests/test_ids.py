import json
import tempfile
import unittest
from pathlib import Path

from core.ids import (
    IdRegistry,
    bare_slug,
    build_catalog,
    build_id_registry,
    build_project_sections,
    is_canonical_id,
    lk_post,
    lk_tab_proj,
    next_activity_id,
    next_milestone_id,
    next_post_id,
    parse_id,
    renumber_plan_posts,
    resolve_section,
    section_tally,
)


class TestIds(unittest.TestCase):
    def test_composed_parse(self):
        self.assertEqual(parse_id("pr1.sec02")["segments"], ("pr1", "sec02"))
        self.assertTrue(is_canonical_id("pr1.pf2.sec00.po3.br1.fd02"))
        self.assertFalse(is_canonical_id("proj:acme"))
        self.assertFalse(is_canonical_id("not-an-id"))

    def test_registry_project_and_sections(self):
        tree = [{
            "slug": "acme", "name": "Acme", "kind": "venture",
            "profiles": [], "products": [],
        }]
        reg = build_id_registry(tree, [])
        self.assertEqual(reg.get("proj:acme"), "pr1")
        self.assertEqual(reg.get(lk_tab_proj("acme", "validation")), "pr1.sec02")
        self.assertEqual(reg.get(lk_tab_proj("acme", "overview")), "pr1.sec01")

    def test_registry_profile_posts_and_fields(self):
        tree = [{
            "slug": "acme", "name": "Acme",
            "profiles": [{
                "slug": "demo", "name": "Demo", "channels": [],
            }],
            "products": [],
        }]
        posts = [{"id": "draft-001", "profile_slug": "demo", "working_title": "A"}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief_dir = root / "projects" / "acme" / "profiles" / "demo" / "content" / "briefs"
            brief_dir.mkdir(parents=True)
            (brief_dir / "draft-001.json").write_text(
                '{"cover_overlay":"Hook","slide_overlays":[{"slide":1,"overlay":"One"}]}',
                encoding="utf-8",
            )
            reg = build_id_registry(tree, posts, root=root)
            self.assertEqual(reg.get("prof:demo"), "pr1.pf1")
            self.assertEqual(reg.get("post:draft-001"), "pr1.pf1.sec00.po1")
            self.assertEqual(reg.get("brief:post:draft-001"), "pr1.pf1.sec00.po1.br1")
            self.assertEqual(reg.get("fld:brief:draft-001:cover_overlay"), "pr1.pf1.sec00.po1.br1.fd01")
            self.assertEqual(reg.get("fld:brief:draft-001:slide-1"), "pr1.pf1.sec00.po1.br1.fd02")

    def test_registry_profile_and_slot_fields(self):
        tree = [{
            "slug": "acme", "name": "Acme",
            "profiles": [{"slug": "demo", "name": "Demo", "channels": [
                {"slug": "demo-ig", "name": "IG", "platform": "instagram"},
            ]}],
            "products": [],
        }]
        posts = [{"id": "post-001", "profile_slug": "demo", "date": "2026-07-01"}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "projects" / "acme" / "profiles" / "demo" / "content"
            plan_dir.mkdir(parents=True)
            (plan_dir / "plan-2026-07.json").write_text(
                '{"posts":[{"id":"post-001","format":"carousel","working_title":"T","concept":"c"}]}',
                encoding="utf-8",
            )
            reg = build_id_registry(tree, posts, root=root)
            self.assertIsNone(reg.get("fld:prof:demo:name"))
            self.assertIsNone(reg.get("fld:chan:demo-ig:platform"))
            self.assertEqual(reg.get("prof:demo"), "pr1.pf1")
            self.assertEqual(reg.get("tab:prof:demo:setup"), "pr1.pf1.sec01")
            self.assertEqual(reg.get("brief-spec:prof:demo"), "pr1.pf1.sec01.br1")
            self.assertEqual(reg.get("voice:prof:demo"), "pr1.pf1.sec01.vc1")
            self.assertEqual(reg.get("chan:demo-ig"), "pr1.pf1.ch1")
            self.assertEqual(reg.get("sl:post:post-001:working_title"), "pr1.pf1.sec00.po1.sl01")
            self.assertEqual(reg.get("sl:post:post-001:concept"), "pr1.pf1.sec00.po1.sl02")
            self.assertIsNone(reg.get("sl:post:post-001:format"))
            self.assertIsNone(reg.get("sl:post:post-001:channels"))

    def test_post_channels_bind_to_channel_entity_not_field_id(self):
        tree = [{
            "slug": "acme", "name": "Acme",
            "profiles": [{"slug": "demo", "name": "Demo", "channels": [
                {"slug": "demo-ig", "name": "IG", "platform": "instagram"},
                {"slug": "demo-tt", "name": "TT", "platform": "tiktok"},
            ]}],
            "products": [],
        }]
        posts = [{"id": "post-001", "profile_slug": "demo"}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "projects" / "acme" / "profiles" / "demo" / "content"
            plan_dir.mkdir(parents=True)
            (plan_dir / "plan-2026-07.json").write_text(
                '{"posts":[{"id":"post-001","channels":["demo-ig","demo-tt"],"date":"2026-07-01"}]}',
                encoding="utf-8",
            )
            reg = build_id_registry(tree, posts, root=root)
            self.assertIsNone(reg.get("sl:post:post-001:channels"))
            self.assertEqual(reg.get("post:post-001:ref:chan:demo-ig"), "pr1.pf1.ch1")
            self.assertEqual(reg.get("post:post-001:ref:chan:demo-tt"), "pr1.pf1.ch2")

    def test_registry_gen_prompts_per_slide(self):
        tree = [{
            "slug": "acme", "name": "Acme",
            "profiles": [{"slug": "demo", "name": "Demo", "channels": []}],
            "products": [],
        }]
        posts = [{"id": "post-001", "profile_slug": "demo"}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief_dir = root / "projects" / "acme" / "profiles" / "demo" / "content" / "briefs"
            brief_dir.mkdir(parents=True)
            (brief_dir / "post-001.json").write_text(
                '{"title":"T","gen_prompts":["prompt one","prompt two"]}',
                encoding="utf-8",
            )
            reg = build_id_registry(tree, posts, root=root)
            self.assertEqual(reg.get("brief:post:post-001"), "pr1.pf1.sec00.po1.br1")
            self.assertEqual(reg.get("fld:brief:post-001:gen-prompt-1"), "pr1.pf1.sec00.po1.br1.fd02")
            self.assertEqual(reg.get("fld:brief:post-001:gen-prompt-2"), "pr1.pf1.sec00.po1.br1.fd03")
            self.assertIsNone(reg.get("fld:brief:post-001:gen_prompts"))

    def test_bare_slug_via_registry(self):
        tree = [{"slug": "acme", "profiles": [{"slug": "demo", "channels": []}], "products": []}]
        posts = [{"id": "draft-001", "profile_slug": "demo"}]
        reg = build_id_registry(tree, posts)
        self.assertEqual(bare_slug("pr1.pf1.sec00.po1", reg), "draft-001")
        self.assertEqual(bare_slug("pr1", reg), "acme")

    def test_registry_section_artifacts_cascade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp_dir = root / "projects" / "acme" / "strategy" / "experiments"
            exp_dir.mkdir(parents=True)
            (exp_dir / "exp-001-design.json").write_text("{}", encoding="utf-8")
            prod_dir = root / "projects" / "acme" / "products" / "app"
            prod_dir.mkdir(parents=True)
            (prod_dir / "product.md").write_text("# App\n", encoding="utf-8")
            tree = [{"slug": "acme", "profiles": [], "products": []}]
            reg = build_id_registry(tree, [], root=root)
            self.assertEqual(reg.get("exp:proj:acme:exp-001-design"), "pr1.sec03.ex1")
            self.assertEqual(reg.get("prod:app"), "pr1.sec05.pd1")
            exp = reg.resolve("pr1.sec03.ex1")
            self.assertEqual(exp["parent"], "pr1.sec03")
            pd = reg.resolve("pr1.sec05.pd1")
            self.assertEqual(pd["parent"], "pr1.sec05")

    def test_registry_memos_nested_under_section_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memo_dir = root / "projects" / "acme" / "strategy" / "memos"
            memo_dir.mkdir(parents=True)
            (memo_dir / "problem-validation-v1.json").write_text("{}", encoding="utf-8")
            (memo_dir / "positioning-v1.json").write_text("{}", encoding="utf-8")
            (memo_dir / "pricing-v1.json").write_text("{}", encoding="utf-8")
            tree = [{"slug": "acme", "profiles": [], "products": []}]
            reg = build_id_registry(tree, [], root=root)
            self.assertEqual(reg.get("memo:proj:acme:problem-validation-v1"), "pr1.sec02.mm1")
            self.assertEqual(reg.get("memo:proj:acme:positioning-v1"), "pr1.sec04.mm1")
            self.assertEqual(reg.get("memo:proj:acme:pricing-v1"), "pr1.sec04.mm2")
            pos = reg.resolve("pr1.sec04.mm1")
            self.assertEqual(pos["parent"], "pr1.sec04")
            self.assertEqual(pos["ref"]["section"], "pricing")

    def test_resolve_section_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj_dir = root / "projects" / "acme" / "strategy"
            proj_dir.mkdir(parents=True)
            (proj_dir / "intake.md").write_text("# intake\n", encoding="utf-8")
            (proj_dir / "memos").mkdir()
            (proj_dir / "memos" / "problem-validation-v1.json").write_text("{}", encoding="utf-8")
            tree = [{"slug": "acme", "profiles": [], "products": []}]
            reg = build_id_registry(tree, [], root=root)
            pdata = {
                "memos": [{
                    "type": "problem-validation",
                    "version": 1,
                    "status": "proposed",
                    "file_path": "projects/acme/strategy/memos/problem-validation-v1.json",
                }],
            }
            sec = resolve_section("acme", "validation", root, project_data=pdata, registry=reg)
            self.assertEqual(sec["id"], "pr1.sec02")
            self.assertFalse(sec["empty"])
            self.assertEqual(sec["skill"], "problem-validation")

    def test_build_project_sections_and_tally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = [{"slug": "solo", "profiles": [], "products": []}]
            reg = build_id_registry(tree, [], root=root)
            sections = build_project_sections("solo", root, {"memos": [], "experiments": [], "products": [], "features": []}, registry=reg)
            self.assertIn("validation", sections)
            self.assertTrue(sections["validation"]["empty"])
            self.assertEqual(sections["validation"]["id"], "pr1.sec02")
            self.assertEqual(section_tally("solo", "validation", root), "empty")

    def test_file_artifacts_include_md_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "projects" / "acme"
            intake = proj / "strategy" / "intake.md"
            intake.parent.mkdir(parents=True)
            intake.write_text("# Venture intake\n\n## What it is\n\nB2B SaaS.\n", encoding="utf-8")
            tree = [{"slug": "acme", "profiles": [], "products": []}]
            reg = build_id_registry(tree, [], root=root)
            sec = resolve_section("acme", "validation", root, registry=reg)
            files = [a for a in sec["artifacts"] if a["kind"] == "file"]
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["text"], intake.read_text(encoding="utf-8"))
            self.assertEqual(files[0]["id"], "pr1.sec02.doc1")

    def test_resolve_section_technical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "projects" / "acme"
            technical = proj / "technical.md"
            proj.mkdir(parents=True)
            technical.write_text("# Technical\n\n## Stack\n\nPython.\n", encoding="utf-8")
            tree = [{"slug": "acme", "profiles": [], "products": []}]
            reg = build_id_registry(tree, [], root=root)
            sec = resolve_section("acme", "technical", root, registry=reg)
            self.assertEqual(sec["id"], "pr1.sec06")
            self.assertFalse(sec["empty"])
            files = [a for a in sec["artifacts"] if a["kind"] == "file"]
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["text"], technical.read_text(encoding="utf-8"))
            self.assertEqual(section_tally("acme", "technical", root), "technical ✓")

    def test_technical_doc_subsections_get_composed_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "projects" / "demo"
            proj.mkdir(parents=True)
            (proj / "technical.md").write_text(
                "# Technical\n\n## Stack\n\nPython.\n\n## Architecture\n\nServices.\n",
                encoding="utf-8",
            )
            (proj / "subsections.json").write_text(
                json.dumps({
                    "version": 1,
                    "docs": {
                        "intake": ["What it is"],
                        "technical": ["Stack", "Architecture"],
                        "roadmap": ["Next"],
                    },
                    "validation_tab": ["What it is"],
                }),
                encoding="utf-8",
            )
            tree = [{"slug": "demo", "profiles": [], "products": []}]
            reg = build_id_registry(tree, [], root=root)
            self.assertEqual(reg.get("doc:proj:demo:technical"), "pr1.sec06.doc1")
            self.assertEqual(reg.get("sub:proj:demo:technical:stack"), "pr1.sec06.doc1.ss1")
            self.assertEqual(reg.get("sub:proj:demo:technical:architecture"), "pr1.sec06.doc1.ss2")
            stack = reg.resolve("pr1.sec06.doc1.ss1")
            self.assertEqual(stack["kind"], "subsection")
            self.assertEqual(stack["parent"], "pr1.sec06.doc1")
            self.assertEqual(stack["ref"]["subsection"], "Stack")
            from core.ids import subsection_id_map
            smap = subsection_id_map(reg, "demo")
            self.assertEqual(smap["technical"]["Stack"], "pr1.sec06.doc1.ss1")
            self.assertEqual(smap["technical"]["Architecture"], "pr1.sec06.doc1.ss2")

    def test_next_post_id_manual(self):
        existing = {"post-m-20260701-120000"}
        pid = next_post_id(existing, manual=True)
        self.assertTrue(pid.startswith("post-m-"))
        self.assertNotIn(pid, existing)

    def test_renumber_plan_posts(self):
        existing = {"post-001", "post-002"}
        slots = [{"id": "draft-001"}, {"id": "draft-002"}]
        renumber_plan_posts(slots, existing)
        self.assertEqual(slots[0]["id"], "post-003")
        self.assertEqual(slots[1]["id"], "post-004")

    def test_generated_stamp_ids(self):
        ms = next_milestone_id(set())
        self.assertTrue(ms.startswith("ms-"))
        act = next_activity_id(set())
        self.assertTrue(act.startswith("act-"))

    def test_live_catalog_from_tree(self):
        tree = [{
            "slug": "acme", "name": "Acme", "kind": "venture",
            "profiles": [{
                "slug": "demo", "name": "Demo", "channels": [
                    {"slug": "demo-tiktok", "platform": "tiktok", "name": "TikTok"},
                ],
            }],
            "products": [],
        }]
        entries = build_catalog(tree)
        ids = {e["id"] for e in entries}
        self.assertIn("pr1", ids)
        self.assertIn("pr1.pf1", ids)
        self.assertIn("pr1.pf1.ch1", ids)
        self.assertIn("pr1.sec01", ids)


if __name__ == "__main__":
    unittest.main()