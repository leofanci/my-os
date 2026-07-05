"""Data model — parent/child cascade, categorization, cross-module sync."""
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestDataModel(unittest.TestCase):
    def test_project_section_keys_aligned(self):
        from core.ids import PROJECT_SECTIONS, PROJECT_SECTION_LAYOUT, PROJ_SEC_NUM

        keys_py = [k for k, _ in PROJECT_SECTIONS]
        self.assertEqual(set(keys_py), set(PROJECT_SECTION_LAYOUT.keys()))
        self.assertEqual(len(keys_py), 6)
        for i, (k, _) in enumerate(PROJECT_SECTIONS, 1):
            self.assertEqual(PROJ_SEC_NUM[k], f"{i:02d}")

    def test_memo_types_single_canonical_section(self):
        from core.project_schemas import MEMO_SECTION, MEMO_TYPES, canonical_memo_types_by_section
        from core.ids import PROJECT_SECTION_LAYOUT

        seen: dict[str, str] = {}
        for sec, types in canonical_memo_types_by_section().items():
            for mtype in types:
                self.assertIn(mtype, MEMO_TYPES)
                self.assertNotIn(mtype, seen, f"{mtype} duplicated across sections")
                seen[mtype] = sec
                self.assertEqual(MEMO_SECTION[mtype], sec)
        self.assertEqual(set(seen.keys()), set(MEMO_TYPES))

        for sec, types in canonical_memo_types_by_section().items():
            layout_types = tuple(PROJECT_SECTION_LAYOUT.get(sec, {}).get("memo_types") or ())
            self.assertEqual(layout_types, types)

    def test_problem_validation_not_in_overview_layout(self):
        from core.ids import PROJECT_SECTION_LAYOUT

        overview_memos = PROJECT_SECTION_LAYOUT["overview"].get("memo_types") or []
        self.assertNotIn("problem-validation", overview_memos)
        self.assertIn("assessment", overview_memos)

    def test_doc_files_map_to_valid_sections(self):
        from core.ids import PROJECT_DOC_FILES, PROJECT_SECTION_LAYOUT

        for _rel, sec_key, doc_key in PROJECT_DOC_FILES:
            self.assertIn(sec_key, PROJECT_SECTION_LAYOUT)
            self.assertTrue(doc_key)

    def test_registry_memo_parent_matches_memo_section(self):
        from core.ids import build_id_registry, lk_memo

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memo_dir = root / "projects" / "acme" / "strategy" / "memos"
            memo_dir.mkdir(parents=True)
            for name in (
                "problem-validation-v1.json",
                "assessment-v1.json",
                "positioning-v1.json",
                "launch-v1.json",
            ):
                (memo_dir / name).write_text("{}", encoding="utf-8")
            tree = [{"slug": "acme", "profiles": [], "products": []}]
            reg = build_id_registry(tree, [], root=root)

            from core.project_schemas import MEMO_SECTION
            from core.ids import PROJ_SEC_NUM as SEC_NUM

            for mtype, sec_key in MEMO_SECTION.items():
                cid = reg.get(lk_memo("acme", mtype, 1))
                if not cid:
                    continue
                ent = reg.resolve(cid)
                expected_parent = f"pr1.sec{SEC_NUM[sec_key]}"
                self.assertEqual(ent["parent"], expected_parent)
                self.assertEqual(ent["ref"]["section"], sec_key)

    def test_registry_parent_chains_are_contiguous(self):
        from core.ids import build_id_registry

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "projects" / "acme"
            (proj / "strategy" / "memos").mkdir(parents=True)
            (proj / "strategy" / "memos" / "assessment-v1.json").write_text("{}", encoding="utf-8")
            (proj / "strategy" / "experiments").mkdir(parents=True)
            (proj / "strategy" / "experiments" / "exp-a.json").write_text("{}", encoding="utf-8")
            prod = proj / "products" / "app"
            prod.mkdir(parents=True)
            (prod / "product.md").write_text("# App\n", encoding="utf-8")
            (prod / "roadmap.md").write_text("# Roadmap\n\n## Next\n\n- Feature — why\n", encoding="utf-8")
            tree = [{
                "slug": "acme",
                "profiles": [{"slug": "demo", "name": "Demo", "channels": []}],
                "products": [{"slug": "app", "name": "App"}],
            }]
            posts = [{"id": "po-1", "profile_slug": "demo", "working_title": "Post"}]
            features = [{"product_slug": "app", "title": "Feature", "status": "planned"}]
            reg = build_id_registry(tree, posts, root=root, features=features)

            for cid, ent in reg.by_id.items():
                parent = ent.get("parent")
                if not parent:
                    self.assertTrue(cid.startswith("pr") or cid.startswith("vw"))
                    continue
                self.assertTrue(
                    cid.startswith(parent + "."),
                    f"{cid} parent {parent} not direct ancestor",
                )
                self.assertIn(parent, reg.by_id)

    def test_feature_cascade_under_product_not_section(self):
        from core.ids import build_id_registry, lk_feature

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod = root / "projects" / "acme" / "products" / "app"
            prod.mkdir(parents=True)
            (prod / "product.md").write_text("# App\n", encoding="utf-8")
            tree = [{"slug": "acme", "profiles": [], "products": [{"slug": "app"}]}]
            feats = [{"product_slug": "app", "title": "Auth", "status": "planned"}]
            reg = build_id_registry(tree, [], root=root, features=feats)
            fid = reg.get(lk_feature("app", "auth"))
            self.assertRegex(fid, r"^pr1\.sec05\.pd1\.ft\d+$")
            ent = reg.resolve(fid)
            self.assertEqual(ent["parent"], "pr1.sec05.pd1")
            self.assertEqual(reg.resolve(ent["parent"])["parent"], "pr1.sec05")

    def test_schemas_api_exports_cascade_and_sections(self):
        from core.project_schemas import MEMO_SECTION, canonical_memo_types_by_section, schemas_for_api

        api = schemas_for_api()
        self.assertIn("id_cascade", api)
        self.assertIn("project_sections", api)
        self.assertIn("section_layout", api)
        self.assertIn("subsections", api)
        self.assertIn("intake", api["subsections"]["docs"])
        self.assertEqual(api["memo_types_by_section"], {k: list(v) for k, v in canonical_memo_types_by_section().items()})
        for mtype, sec in MEMO_SECTION.items():
            self.assertIn(mtype, api["memo_types_by_section"][sec])

    def test_schemas_api_section_layout_memo_types(self):
        from core.project_schemas import canonical_memo_types_by_section, schemas_for_api

        api = schemas_for_api()
        for sec, types in canonical_memo_types_by_section().items():
            self.assertEqual(tuple(api["section_layout"][sec]["memo_types"]), types)


if __name__ == "__main__":
    unittest.main()